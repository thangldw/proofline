from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from proofline import __version__
from proofline.config import get_settings, provider_config_path
from proofline.database import make_engine
from proofline.main import create_app


def _wait_for_ready(process: subprocess.Popen[str], ready_file: Path) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if ready_file.is_file():
            return json.loads(ready_file.read_text(encoding="utf-8"))
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"server exited before ready\nstdout={stdout}\nstderr={stderr}")
        time.sleep(0.02)
    raise AssertionError("server did not publish readiness within 10 seconds")


def test_home_scopes_default_database_and_provider_config(monkeypatch, tmp_path):
    home = tmp_path / "Proofline State"
    monkeypatch.setenv("PROOFLINE_HOME", str(home))
    monkeypatch.delenv("PROOFLINE_DATABASE_URL", raising=False)
    monkeypatch.delenv("PROOFLINE_PROVIDER_CONFIG_PATH", raising=False)

    assert get_settings().database_url == f"sqlite:///{home / 'proofline.db'}"
    assert provider_config_path() == home / "providers.json"


def test_embedded_server_publishes_dynamic_port_serves_bundled_web_and_cleans_readiness(tmp_path):
    data_dir = tmp_path / "state"
    ready_file = tmp_path / "runtime" / "ready.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "proofline.runtime",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--data-dir",
            str(data_dir),
            "--ready-file",
            str(ready_file),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = _wait_for_ready(process, ready_file)
        assert ready == {
            "event": "ready",
            "host": "127.0.0.1",
            "port": ready["port"],
            "version": __version__,
        }
        assert isinstance(ready["port"], int) and ready["port"] > 0
        base_url = f"http://127.0.0.1:{ready['port']}"
        assert httpx.get(f"{base_url}/health").json() == {
            "status": "ok",
            "version": __version__,
        }
        web_response = httpx.get(base_url)
        assert web_response.status_code == 200
        assert '<div id="root"></div>' in web_response.text
        assert (data_dir / "proofline.db").is_file()
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert process.returncode == 0
    assert not ready_file.exists()
    stdout = process.stdout.read() if process.stdout else ""
    assert json.loads(stdout.strip().splitlines()[-1]) == ready


def test_api_only_mode_does_not_mount_bundled_web(monkeypatch, tmp_path):
    monkeypatch.setenv("PROOFLINE_DISABLE_WEB", "true")
    engine = make_engine(f"sqlite:///{tmp_path / 'api-only.db'}")
    try:
        with TestClient(create_app(engine)) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/").status_code == 404
    finally:
        engine.dispose()

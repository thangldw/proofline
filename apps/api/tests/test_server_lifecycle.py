from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from proofline import __version__
from proofline.config import get_settings, provider_config_path


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


def test_embedded_server_publishes_dynamic_port_serves_web_and_cleans_readiness(tmp_path):
    data_dir = tmp_path / "state"
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<main>Proofline embedded web</main>", encoding="utf-8")
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
            "--web-dir",
            str(web_dir),
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
        assert "Proofline embedded web" in httpx.get(base_url).text
        assert (data_dir / "proofline.db").is_file()
    finally:
        process.terminate()
        process.wait(timeout=10)

    assert process.returncode == 0
    assert not ready_file.exists()
    stdout = process.stdout.read() if process.stdout else ""
    assert json.loads(stdout.strip().splitlines()[-1]) == ready

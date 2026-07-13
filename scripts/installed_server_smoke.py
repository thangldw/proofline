#!/usr/bin/env python3
"""Smoke-test the installed Proofline executable and its bundled web UI."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def wait_for_ready(process: subprocess.Popen[str], ready_file: Path) -> dict[str, object]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ready_file.is_file():
            return json.loads(ready_file.read_text(encoding="utf-8"))
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"installed server exited before readiness: stdout={stdout!r} stderr={stderr!r}"
            )
        time.sleep(0.02)
    raise RuntimeError("installed server did not become ready within 15 seconds")


def read_url(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - loopback URL
        return response.status, response.read().decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proofline", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="proofline-installed-server-") as directory:
        root = Path(directory)
        ready_file = root / "ready.json"
        process = subprocess.Popen(
            [
                str(args.proofline),
                "serve",
                "--port",
                "0",
                "--data-dir",
                str(root / "state"),
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
            ready = wait_for_ready(process, ready_file)
            base_url = f"http://127.0.0.1:{ready['port']}"
            health_status, health_body = read_url(f"{base_url}/health")
            web_status, web_body = read_url(base_url)
            health = json.loads(health_body)
            if health_status != 200 or health.get("status") != "ok":
                raise RuntimeError("installed server health check failed")
            if web_status != 200 or '<div id="root"></div>' not in web_body:
                raise RuntimeError("installed bundled web check failed")
        finally:
            process.terminate()
            process.wait(timeout=10)
        if process.returncode != 0 or ready_file.exists():
            raise RuntimeError("installed server did not shut down cleanly")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "version": health["version"],
                    "bundled_web": True,
                    "graceful_shutdown": True,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()

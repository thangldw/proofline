from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import sys
import tempfile
import webbrowser
from pathlib import Path

import uvicorn

from . import __version__


def _open_local_ui(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except Exception:
        return False


def _write_ready_file(path: Path, payload: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="proofline-ready-", dir=path.parent)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def _serve(
    host: str,
    port: int,
    *,
    ready_file: Path | None,
    shutdown_file: Path | None,
    log_level: str,
    open_browser: bool,
) -> None:
    # Pass the ASGI object directly so frozen desktop binaries do not depend on
    # Uvicorn's string-based dynamic module import.
    from .main import app

    resolved_shutdown_file = shutdown_file.expanduser().resolve() if shutdown_file else None
    if resolved_shutdown_file is not None:
        resolved_shutdown_file.parent.mkdir(parents=True, exist_ok=True)
        resolved_shutdown_file.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen(2048)
    actual_port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=actual_port,
            log_level=log_level,
            reload=False,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    shutdown_task: asyncio.Task[None] | None = None
    previous_handlers: dict[signal.Signals, object] = {}
    try:
        while not server.started and not task.done():
            await asyncio.sleep(0.01)
        if task.done():
            await task
            raise RuntimeError("server stopped before readiness")

        def request_shutdown(_signal_number, _frame) -> None:
            server.should_exit = True

        for signal_name in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signal_name] = signal.getsignal(signal_name)
            signal.signal(signal_name, request_shutdown)

        async def watch_shutdown_file() -> None:
            if resolved_shutdown_file is None:
                return
            while not server.should_exit:
                if resolved_shutdown_file.is_file():
                    server.should_exit = True
                    return
                await asyncio.sleep(0.1)

        if resolved_shutdown_file is not None:
            shutdown_task = asyncio.create_task(watch_shutdown_file())
        payload: dict[str, object] = {
            "event": "ready",
            "host": host,
            "port": actual_port,
            "version": __version__,
        }
        if ready_file is not None:
            _write_ready_file(ready_file, payload)
        print(json.dumps(payload, sort_keys=True), flush=True)
        if open_browser:
            url = f"http://{host}:{actual_port}/"
            if not _open_local_ui(url):
                print(
                    json.dumps({"event": "browser_open_failed", "url": url}, sort_keys=True),
                    file=sys.stderr,
                    flush=True,
                )
        await task
    finally:
        if shutdown_task is not None:
            shutdown_task.cancel()
            await asyncio.gather(shutdown_task, return_exceptions=True)
        for signal_name, previous_handler in previous_handlers.items():
            signal.signal(signal_name, previous_handler)
        listener.close()
        if ready_file is not None:
            ready_file.expanduser().resolve().unlink(missing_ok=True)
        if resolved_shutdown_file is not None:
            resolved_shutdown_file.unlink(missing_ok=True)


def run_server(
    host: str,
    port: int,
    *,
    ready_file: Path | None = None,
    shutdown_file: Path | None = None,
    log_level: str = "info",
    open_browser: bool = False,
) -> None:
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    asyncio.run(
        _serve(
            host,
            port,
            ready_file=ready_file,
            shutdown_file=shutdown_file,
            log_level=log_level,
            open_browser=open_browser,
        )
    )

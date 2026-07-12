import asyncio
import threading
import time
from dataclasses import asdict

import proofline.folder_scanning as folder_scanning
import pytest
from fastapi.testclient import TestClient
from proofline.config import get_settings
from proofline.database import get_session, make_engine
from proofline.folder_scanning import FolderScanCoordinator
from proofline.folder_watching import FolderWatcher
from proofline.main import create_app
from proofline.schemas import FolderScanResponse
from sqlalchemy.orm import sessionmaker


def _empty_report(root: str) -> FolderScanResponse:
    return FolderScanResponse(
        root=root,
        path=".",
        delete_missing_requested=False,
        discovered_count=0,
        created_count=0,
        updated_count=0,
        unchanged_count=0,
        renamed_count=0,
        failed_count=0,
        missing_count=0,
        missing_source_ids=[],
        files=[],
    )


def _wait_for_cycle(client: TestClient, minimum: int = 1) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get("/api/v1/folder-watch").json()
        if status["completed_cycles"] >= minimum:
            return status
        time.sleep(0.02)
    pytest.fail("folder watcher did not complete in time")


def test_folder_watch_interval_is_bounded_and_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS", raising=False)
    assert get_settings().folder_watch_interval_seconds == 0

    for invalid in ("-1", "3601", "1.5", "enabled"):
        monkeypatch.setenv("PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS", invalid)
        with pytest.raises(ValueError, match="must be 0 or an integer from 1 to 3600"):
            get_settings()

    for valid in ("0", "1", "3600"):
        monkeypatch.setenv("PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS", valid)
        assert get_settings().folder_watch_interval_seconds == int(valid)


def test_disabled_watcher_exposes_safe_idle_status(client):
    response = client.get("/api/v1/folder-watch")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "running": False,
        "scan_in_progress": False,
        "interval_seconds": 0,
        "registered_root_count": 0,
        "completed_cycles": 0,
        "last_started_at": None,
        "last_completed_at": None,
        "last_error_code": None,
        "last_root_error_count": 0,
        "last_discovered_count": 0,
        "last_created_count": 0,
        "last_updated_count": 0,
        "last_unchanged_count": 0,
        "last_renamed_count": 0,
        "last_failed_count": 0,
        "last_missing_count": 0,
    }


def test_enabled_watcher_scans_immediately_and_only_previews_deletion(monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    source_path = root / "decision.md"
    source_path.write_text("Decision: Use SQLite", encoding="utf-8")
    monkeypatch.setenv("PROOFLINE_IMPORT_ROOTS", str(root))
    monkeypatch.setenv("PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS", "1")
    engine = make_engine(f"sqlite:///{tmp_path / 'watch.db'}")
    application = create_app(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_session] = override_session

    with TestClient(application) as client:
        first = _wait_for_cycle(client)
        sources = client.get("/api/v1/sources").json()
        assert first["running"] is True
        assert first["last_created_count"] == 1
        assert first["last_error_code"] is None
        assert len(sources) == 1

        source_path.unlink()
        second = _wait_for_cycle(client, 2)
        assert second["last_missing_count"] == 1
        assert len(client.get("/api/v1/sources").json()) == 1

    assert application.state.folder_watcher.snapshot().running is False
    application.dependency_overrides.clear()
    engine.dispose()


def test_each_root_uses_a_fresh_session_and_preview_payload(monkeypatch, tmp_path):
    roots = (tmp_path / "one", tmp_path / "two")
    for root in roots:
        root.mkdir()
    engine = make_engine(f"sqlite:///{tmp_path / 'sessions.db'}")
    seen_sessions = []
    seen_payloads = []

    def fake_scan(session, payload, registered_roots):
        seen_sessions.append(session)
        seen_payloads.append(payload)
        assert registered_roots == roots
        return _empty_report(payload.root)

    coordinator = FolderScanCoordinator()
    monkeypatch.setattr(coordinator, "scan", fake_scan)
    watcher = FolderWatcher(engine, roots, 1, coordinator)

    asyncio.run(watcher._scan_cycle())

    assert len(seen_sessions) == 2
    assert seen_sessions[0] is not seen_sessions[1]
    assert all(payload.delete_missing is False for payload in seen_payloads)
    assert all(payload.confirmed_missing_source_ids is None for payload in seen_payloads)
    assert watcher.snapshot().completed_cycles == 1
    engine.dispose()


def test_scan_failures_publish_only_a_stable_error_code(monkeypatch, tmp_path):
    root = tmp_path / "private-vault"
    root.mkdir()
    engine = make_engine(f"sqlite:///{tmp_path / 'failure.db'}")
    watcher = FolderWatcher(engine, (root,), 1)

    def fail(_root):
        raise RuntimeError("secret source contents and /private/path")

    monkeypatch.setattr(watcher, "_scan_root", fail)
    asyncio.run(watcher._scan_cycle())
    serialized = str(asdict(watcher.snapshot()))

    assert watcher.snapshot().last_error_code == "folder_watch_scan_failed"
    assert watcher.snapshot().last_root_error_count == 1
    assert "secret source" not in serialized
    assert "/private/path" not in serialized
    assert str(root) not in serialized
    engine.dispose()


def test_one_root_failure_does_not_block_later_roots(monkeypatch, tmp_path):
    roots = (tmp_path / "unavailable", tmp_path / "healthy")
    for root in roots:
        root.mkdir()
    engine = make_engine(f"sqlite:///{tmp_path / 'isolation.db'}")
    watcher = FolderWatcher(engine, roots, 1)
    scanned = []

    def scan(root):
        scanned.append(root)
        if root == roots[0]:
            raise RuntimeError("private root failure")
        return _empty_report(str(root)).model_copy(update={"created_count": 2})

    monkeypatch.setattr(watcher, "_scan_root", scan)
    asyncio.run(watcher._scan_cycle())

    assert scanned == list(roots)
    assert watcher.snapshot().last_created_count == 2
    assert watcher.snapshot().last_root_error_count == 1
    assert watcher.snapshot().last_error_code == "folder_watch_scan_failed"
    engine.dispose()


def test_polling_cycles_never_overlap(monkeypatch, tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'sequential.db'}")
    watcher = FolderWatcher(engine, (), 1)
    watcher._interval_seconds = 0.01
    active = 0
    maximum_active = 0
    calls = 0

    async def slow_cycle():
        nonlocal active, maximum_active, calls
        active += 1
        maximum_active = max(maximum_active, active)
        calls += 1
        await asyncio.sleep(0.03)
        active -= 1
        if calls == 3:
            watcher._stop.set()

    monkeypatch.setattr(watcher, "_scan_cycle", slow_cycle)

    async def exercise():
        await watcher.start()
        assert watcher._task is not None
        await watcher._task
        await watcher.stop()

    asyncio.run(exercise())

    assert calls == 3
    assert maximum_active == 1
    assert watcher.snapshot().running is False
    engine.dispose()


def test_manual_scan_waits_for_in_progress_watcher_scan(monkeypatch, tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("PROOFLINE_IMPORT_ROOTS", str(root))
    monkeypatch.setenv("PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS", "1")
    engine = make_engine(f"sqlite:///{tmp_path / 'coordinated.db'}")
    application = create_app(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    entered = threading.Event()
    release_first = threading.Event()
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0
    calls = 0

    def override_session():
        with factory() as session:
            yield session

    def controlled_scan(_session, payload, _registered_roots):
        nonlocal active, maximum_active, calls
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
            calls += 1
            call_number = calls
        entered.set()
        if call_number == 1:
            assert release_first.wait(timeout=3)
        with state_lock:
            active -= 1
        return _empty_report(payload.root or str(root))

    monkeypatch.setattr(folder_scanning, "scan_registered_folder", controlled_scan)
    application.dependency_overrides[get_session] = override_session

    with TestClient(application) as client:
        assert entered.wait(timeout=3)
        response_holder = []
        manual = threading.Thread(
            target=lambda: response_holder.append(client.post("/api/v1/folder-scans", json={})),
            daemon=True,
        )
        manual.start()
        time.sleep(0.1)
        assert calls == 1
        assert manual.is_alive()

        release_first.set()
        manual.join(timeout=3)
        assert not manual.is_alive()
        assert response_holder[0].status_code == 200
        assert calls == 2
        assert maximum_active == 1

    application.dependency_overrides.clear()
    engine.dispose()

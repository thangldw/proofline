from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from . import __version__
from .api import router
from .config import get_settings
from .database import engine, initialize_database
from .folder_scanning import FolderScanCoordinator
from .folder_watching import FolderWatcher
from .ingestion import recover_orphaned_ingestion_jobs


def create_app(database_engine: Engine = engine) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_database(database_engine)
        with Session(database_engine) as recovery_session:
            recover_orphaned_ingestion_jobs(recovery_session)
        settings = get_settings()
        folder_scan_coordinator = FolderScanCoordinator()
        folder_watcher = FolderWatcher(
            database_engine,
            settings.import_roots,
            settings.folder_watch_interval_seconds,
            folder_scan_coordinator,
        )
        _app.state.folder_scan_coordinator = folder_scan_coordinator
        _app.state.folder_watcher = folder_watcher
        await folder_watcher.start()
        try:
            yield
        finally:
            await folder_watcher.stop()

    application = FastAPI(
        title="Proofline API",
        version=__version__,
        description="Evidence-first engineering decision memory",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(get_settings().cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    web_dir_value = os.getenv("PROOFLINE_WEB_DIR")
    if web_dir_value:
        web_dir = Path(web_dir_value).expanduser().resolve()
        if not (web_dir / "index.html").is_file():
            raise RuntimeError("PROOFLINE_WEB_DIR must contain index.html")
        application.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return application


app = create_app()

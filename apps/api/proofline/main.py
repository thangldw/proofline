from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .api import router
from .config import get_settings
from .database import engine, initialize_database
from .ingestion import recover_orphaned_ingestion_jobs


def create_app(database_engine: Engine = engine) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        initialize_database(database_engine)
        with Session(database_engine) as recovery_session:
            recover_orphaned_ingestion_jobs(recovery_session)
        yield

    application = FastAPI(
        title="Proofline API",
        version="0.1.0",
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
        return {"status": "ok"}

    return application


app = create_app()

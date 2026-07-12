from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from proofline.database import get_session, initialize_database, make_engine
from proofline.main import create_app
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(autouse=True)
def disabled_external_models(monkeypatch):
    monkeypatch.setenv("PROOFLINE_AI_PROVIDER", "disabled")
    monkeypatch.setenv("PROOFLINE_EMBEDDING_PROVIDER", "disabled")
    monkeypatch.setenv("PROOFLINE_ALLOW_REMOTE_AI", "false")


@pytest.fixture()
def session(tmp_path) -> Generator[Session, None, None]:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        yield value
    engine.dispose()


@pytest.fixture()
def client(session: Session) -> Generator[TestClient, None, None]:
    def override_session():
        yield session

    application = create_app(session.get_bind())
    application.dependency_overrides[get_session] = override_session
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()

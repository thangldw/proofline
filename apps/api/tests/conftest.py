from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from proofline.database import get_session, initialize_database, make_engine
from proofline.main import app
from sqlalchemy.orm import Session, sessionmaker


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

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

"""Fixtures compartidas para pruebas unitarias, de integración y E2E."""

import os

# Desactivar exportación OTLP externa durante las pruebas para rapidez y determinismo
os.environ["OTEL_ENABLED"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest-suite-32chars"

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Provee una base de datos SQLite en memoria aislada por test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provee un TestClient de FastAPI conectado a la BD en memoria."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


_PRECOMPUTED_TEST_HASH = hash_password("StrongPass#2026")


@pytest.fixture()
def users_and_tokens(db_session: Session) -> dict[str, dict]:
    """Crea usuarios admin, operador y auditor con sus respectivos JWT."""
    roles_data = {}
    for role in ("admin", "operador", "auditor"):
        user = User(
            username=f"user_{role}",
            email=f"{role}@erp.test",
            hashed_password=_PRECOMPUTED_TEST_HASH,
            role=role,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        token = create_access_token(data={"sub": str(user.id), "role": user.role})
        roles_data[role] = {
            "user": user,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    return roles_data

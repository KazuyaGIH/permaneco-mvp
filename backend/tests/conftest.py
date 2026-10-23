from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.clock import FixedClock
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine, get_db
from app.core.dependencies import get_clock
from app.main import app
from app.security.auth import login_rate_limiter

FIXED_NOW = datetime(2025, 3, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean_database():
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} CASCADE"))
    login_rate_limiter.attempts.clear()
    yield
    login_rate_limiter.attempts.clear()


@pytest.fixture
def db_session():
    with SessionLocal() as db:
        yield db
        db.rollback()


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", False)

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_clock] = lambda: FixedClock(FIXED_NOW)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

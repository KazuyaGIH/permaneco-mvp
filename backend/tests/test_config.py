import pytest

from app.core.config import normalize_database_url


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        (
            "postgres://user:pass@db.example/permaneco",
            "postgresql+psycopg://user:pass@db.example/permaneco",
        ),
        (
            "postgresql://user:pass@db.example/permaneco?sslmode=require",
            "postgresql+psycopg://user:pass@db.example/permaneco?sslmode=require",
        ),
        (
            "postgresql+psycopg://user:pass@db.example/permaneco",
            "postgresql+psycopg://user:pass@db.example/permaneco",
        ),
        (
            "sqlite:///permaneco.db",
            "sqlite:///permaneco.db",
        ),
    ],
)
def test_normalize_database_url(database_url, expected):
    assert normalize_database_url(database_url) == expected

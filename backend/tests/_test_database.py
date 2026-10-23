import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_DEFAULT_DATABASE_URL = "postgresql+psycopg://permaneco@localhost:5432/permaneco"
_main_url = make_url(os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL))
_test_url = make_url(
    os.getenv("TEST_DATABASE_URL")
    or _main_url.set(database="permaneco_test").render_as_string(hide_password=False)
)

if _test_url.database != "permaneco_test":
    raise RuntimeError("TEST_DATABASE_URL must target the permaneco_test database.")
if _test_url.database == _main_url.database:
    raise RuntimeError("Tests must use a database separate from DATABASE_URL.")

os.environ["TEST_DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

_admin_engine = create_engine(
    _test_url.set(database="postgres"),
    isolation_level="AUTOCOMMIT",
)
try:
    with _admin_engine.connect() as _connection:
        _database_exists = _connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :database"),
            {"database": _test_url.database},
        )
        if not _database_exists:
            _database_name = _connection.dialect.identifier_preparer.quote(_test_url.database)
            _connection.exec_driver_sql(f"CREATE DATABASE {_database_name}")
finally:
    _admin_engine.dispose()

_backend_root = Path(__file__).resolve().parents[1]
_alembic_config = Config(str(_backend_root / "alembic.ini"))
_alembic_config.set_main_option("script_location", str(_backend_root / "migrations"))
command.upgrade(_alembic_config, "head")

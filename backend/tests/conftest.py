"""Test harness: a separate `pensionz_test` database in the same Postgres,
rebuilt from the Alembic migrations once per run (so migrations are tested
too). Each test runs inside a transaction that is rolled back afterwards;
service-layer `db.commit()` calls become savepoint releases inside it.

Run (from backend/): .venv\\Scripts\\pytest -q   or   docker compose exec backend pytest -q
"""
import os

from sqlalchemy.engine import make_url

from app.core.config import settings

# Point the app at the test database *before* anything imports app.core.database
# (the dev URL comes from env or backend/.env, whichever the settings resolved).
_dev_url = make_url(settings.database_url)
TEST_DB_NAME = "pensionz_test"
settings.database_url = _dev_url.set(database=TEST_DB_NAME).render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = settings.database_url
settings.smtp_host = ""  # never send real email from tests
os.environ["SMTP_HOST"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    admin_engine = create_engine(_dev_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.upgrade(config, "head")
    yield
    engine.dispose()


@pytest.fixture
def db():
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)

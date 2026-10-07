"""Test fixtures.

Runs against a dedicated PostGIS database (``meetings_manager_test`` on the
docker-compose Postgres by default; override with TEST_DATABASE_URL). The
schema is built with the real Alembic migrations, and every test runs inside
a transaction that is rolled back afterwards, so tests never touch dev data
and never leak into each other.

No test makes a real network call: Geoapify is replaced by a fake client and
the map provider has no credentials (distance-estimate fallback).
"""

import os
from pathlib import Path

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://meetings_manager:meetings_manager@localhost:5433/meetings_manager_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["GEOAPIFY_API_KEY"] = ""
os.environ["MAP_PROVIDER"] = "mapbox"
os.environ["MAPBOX_ACCESS_TOKEN"] = ""
os.environ["GOOGLE_MAPS_API_KEY"] = ""
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    engine = create_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    engine.dispose()


@pytest.fixture(scope="session")
def engine():
    _ensure_database()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app(db):
    from app.db.session import get_db
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[get_db] = lambda: db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


def _make_user(db, name: str, email: str, role: UserRole) -> User:
    user = User(name=name, email=email, password_hash=hash_password("Test@123"), role=role)
    db.add(user)
    db.commit()  # commits into the per-test savepoint; still rolled back after the test
    return user


@pytest.fixture
def admin_user(db) -> User:
    return _make_user(db, "Test Admin", "admin@samtest.com", UserRole.ADMIN)


@pytest.fixture
def sales_user(db) -> User:
    return _make_user(db, "Sam Sales", "sales@samtest.com", UserRole.SALESPERSON)


@pytest.fixture
def other_sales_user(db) -> User:
    return _make_user(db, "Olive Other", "other@samtest.com", UserRole.SALESPERSON)


def client_for(app, user: User | None) -> TestClient:
    client = TestClient(app)
    if user is not None:
        client.cookies.set("access_token", create_access_token(str(user.id), extra_claims={"role": user.role.value}))
    return client


@pytest.fixture
def admin_client(app, admin_user):
    return client_for(app, admin_user)


@pytest.fixture
def sales_client(app, sales_user):
    return client_for(app, sales_user)


@pytest.fixture
def other_sales_client(app, other_sales_user):
    return client_for(app, other_sales_user)


@pytest.fixture
def anon_client(app):
    return TestClient(app)

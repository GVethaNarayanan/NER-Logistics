"""
Shared test fixtures for Phase 3 auth tests and beyond.

Uses an in-memory SQLite database so tests are isolated and fast.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.auth_service import create_user


# ── In-memory SQLite for tests ────────────────────────────────────────────────
SQLALCHEMY_TEST_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_database():
    """Create fresh tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Direct database session for test setup."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def field_user(db_session):
    """Pre-created field_official user for tests."""
    return create_user(
        db=db_session,
        username="testfield",
        email="field@test.com",
        plain_password="fieldpass123",
        role="field_official",
    )


@pytest.fixture
def admin_user(db_session):
    """Pre-created admin user for tests."""
    return create_user(
        db=db_session,
        username="testadmin",
        email="admin@test.com",
        plain_password="adminpass123",
        role="admin",
    )


def get_auth_header(client: TestClient, username: str, password: str) -> dict:
    """Helper: login and return Authorization header dict."""
    resp = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

import os
import tempfile

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-32-bytes-long!!")
os.environ.setdefault("LINKEDIN_CLIENT_ID", "test-linkedin-client-id")
os.environ.setdefault("LINKEDIN_CLIENT_SECRET", "test-linkedin-client-secret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("WTF_CSRF_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app import app, init_db, get_db  # noqa: E402
from models import User  # noqa: E402


@pytest.fixture
def test_app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["ENVIRONMENT"] = "test"
    app.config["SERVER_NAME"] = "localhost"

    with app.app_context():
        init_db()

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def db_session(test_app):
    with test_app.app_context():
        session = next(get_db())
        yield session
        session.close()


@pytest.fixture
def logged_in_client(client, db_session):
    """Return a test client authenticated as a freshly-created user."""
    import uuid

    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"test-{suffix}@example.com",
        linkedin_id=f"test-{suffix}",
        name="Test User",
        is_verified=1,
        is_active=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    with client.session_transaction() as session:
        session["user_id"] = user.id
    return client

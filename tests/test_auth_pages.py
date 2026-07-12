import uuid

from models import User


def test_register_redirects_to_verify(client, db_session):
    email = f"register-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/register",
        data={
            "name": "New User",
            "email": email,
            "password": "password123",
            "confirm_password": "password123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/verify" in response.headers["Location"]

    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    assert user.is_verified == 0
    assert user.verification_code is not None


def test_verify_logs_in_user(client, db_session):
    from utils import utc_now

    email = f"verify-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        name="Verify User",
        password_hash="unused",
        is_active=1,
        is_verified=0,
        verification_code="123456",
        verification_sent_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    with client.session_transaction() as session:
        session["pending_verification_email"] = email

    response = client.post(
        "/verify",
        data={"email": email, "code": "123456"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session.get("user_id") == user.id


def test_login_blocks_unverified_user(client, db_session):
    from werkzeug.security import generate_password_hash

    email = f"unverified-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    user = User(
        email=email,
        name="Unverified User",
        password_hash=generate_password_hash(password),
        is_active=1,
        is_verified=0,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/verify" in response.headers["Location"]


def test_login_allows_verified_user(client, db_session):
    from werkzeug.security import generate_password_hash

    email = f"verified-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        name="Verified User",
        password_hash=generate_password_hash("password123"),
        is_active=1,
        is_verified=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    response = client.post(
        "/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/" in response.headers["Location"]
    with client.session_transaction() as session:
        assert session.get("user_id") == user.id


def test_logout_redirects_to_login(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session

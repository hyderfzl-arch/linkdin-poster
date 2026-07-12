import pytest
from freezegun import freeze_time

from linkedin_auth import (
    build_auth_url,
    exchange_code_for_token,
    fetch_userinfo,
    get_or_create_user,
    get_valid_access_token,
    load_tokens,
    refresh_access_token,
    save_tokens,
)
from models import User


def test_build_auth_url():
    url = build_auth_url(state="random-state-123")
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization")
    assert "client_id=test-linkedin-client-id" in url
    assert "state=random-state-123" in url


def test_build_auth_url_missing_config(monkeypatch):
    monkeypatch.setattr("config.LINKEDIN_CLIENT_ID", "")
    with pytest.raises(RuntimeError):
        build_auth_url(state="random-state-123")


def test_exchange_code_for_token(responses):
    responses.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        json={
            "access_token": "access-123",
            "refresh_token": "refresh-123",
            "expires_in": "3600",
        },
        status=200,
    )
    tokens = exchange_code_for_token("code-123")
    assert tokens["access_token"] == "access-123"


def test_refresh_access_token(responses):
    responses.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        json={
            "access_token": "new-access-123",
            "refresh_token": "new-refresh-123",
            "expires_in": "7200",
        },
        status=200,
    )
    tokens = refresh_access_token("refresh-123")
    assert tokens["access_token"] == "new-access-123"


def test_fetch_userinfo(responses):
    responses.get(
        "https://api.linkedin.com/v2/userinfo",
        json={"sub": "user-123", "email": "user@example.com", "name": "Test User"},
        status=200,
    )
    info = fetch_userinfo("token")
    assert info["sub"] == "user-123"


def test_get_or_create_user(db_session):
    user = get_or_create_user(db_session, "linkedin-1", email="a@example.com", name="A")
    assert user.id is not None
    assert user.linkedin_id == "linkedin-1"

    # Fetch existing user
    user2 = get_or_create_user(db_session, "linkedin-1")
    assert user2.id == user.id


def test_save_and_load_tokens(db_session):
    user = get_or_create_user(db_session, "linkedin-2")
    save_tokens(
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        user,
    )
    loaded = load_tokens(user)
    assert loaded["access_token"] == "tok"
    assert loaded["refresh_token"] == "ref"


def test_get_valid_access_token_unexpired(db_session):
    user = get_or_create_user(db_session, "linkedin-3")
    save_tokens(
        {"access_token": "valid-tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        user,
    )
    token = get_valid_access_token(db_session, user)
    assert token == "valid-tok"


@freeze_time("2026-01-01 12:00:00")
def test_get_valid_access_token_refreshes(db_session, responses):
    user = get_or_create_user(db_session, "linkedin-4")
    # Set token to expire in 1 minute -> within 5-minute window -> expired
    save_tokens(
        {"access_token": "old-tok", "refresh_token": "ref-1", "expires_in": 61},
        db_session,
        user,
    )
    responses.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        json={
            "access_token": "fresh-tok",
            "refresh_token": "ref-2",
            "expires_in": 3600,
        },
        status=200,
    )
    token = get_valid_access_token(db_session, user)
    assert token == "fresh-tok"


def test_get_valid_access_token_no_refresh(db_session):
    user = User(linkedin_id="no-refresh")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    with pytest.raises(RuntimeError, match="no refresh token"):
        get_valid_access_token(db_session, user)

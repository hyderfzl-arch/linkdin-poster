import uuid

import pytest
from app import (
    _ensure_demo_user,
    _seed_demo_data,
    _linkedin_format,
)
from models import Draft, InspirationPost, Setting, User
from security import encrypt


@pytest.fixture
def logged_in_user(client, db_session):
    suffix = uuid.uuid4().hex[:8]
    email = f"route-{suffix}@example.com"
    linkedin_id = f"route-{suffix}"
    db_session.query(User).filter(User.email == email).delete(synchronize_session=False)
    user = User(
        email=email,
        linkedin_id=linkedin_id,
        name="Route User",
        is_verified=1,
        is_active=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    with client.session_transaction() as session:
        session["user_id"] = user.id
    return user


def test_linkedin_format_urls_and_hashtags():
    text = "Hello #world, check https://example.com and #python"
    out = _linkedin_format(text)
    s = str(out)
    assert 'class="lp-hashtag"' in s
    assert 'href="https://example.com"' in s
    assert "#world" in s
    assert "#python" in s


def test_ensure_demo_user_inserts_demo_user(db_session):
    db_session.query(User).filter(User.id == 1).delete(synchronize_session=False)
    db_session.commit()

    user = _ensure_demo_user(db_session)
    assert user.id == 1
    assert user.email == "demo@example.com"
    assert user.access_token == "demo-access-token"
    assert user.linkedin_id == "demo-linkedin-user"


def test_seed_demo_data_inserts_sample_rows(db_session):
    user = _ensure_demo_user(db_session)
    _seed_demo_data(db_session, user.id)

    posts = db_session.query(InspirationPost).filter_by(user_id=user.id).all()
    drafts = db_session.query(Draft).filter_by(user_id=user.id).all()
    assert len(posts) >= 4
    assert len(drafts) >= 4

    # Calling again should not duplicate seeded data.
    existing_draft_count = db_session.query(Draft).filter_by(user_id=user.id).count()
    _seed_demo_data(db_session, user.id)
    assert db_session.query(Draft).filter_by(user_id=user.id).count() == existing_draft_count


def test_profile_get_decrypts_secret_fields(client, db_session, logged_in_user):
    logged_in_user.openai_api_key = encrypt("openai-secret")
    logged_in_user.linkedin_client_secret = encrypt("linkedin-secret")
    db_session.commit()

    response = client.get("/profile")
    assert response.status_code == 200
    # sensitive values should not be rendered in plain text
    assert b"openai-secret" not in response.data
    assert b"linkedin-secret" not in response.data


def test_profile_post_updates_user_fields(client, db_session, logged_in_user):
    response = client.post(
        "/profile",
        data={
            "name": "New Name",
            "headline": "New Headline",
            "linkedin_url": "https://linkedin.com/in/test",
            "linkedin_org_urn": "urn:li:company:12345",
            "timezone": "UTC",
            "language": "en",
            "email_notifications": "y",
            "openai_api_key": "new-openai-key",
            "linkedin_client_id": "clientid",
            "linkedin_client_secret": "new-secret",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Profile and credentials saved" in response.data

    db_session.expire_all()
    updated_user = db_session.query(User).filter_by(id=logged_in_user.id).one()
    updated_setting = db_session.query(Setting).filter_by(user_id=logged_in_user.id).one()
    assert updated_user.name == "New Name"
    assert updated_user.linkedin_url == "https://linkedin.com/in/test"
    assert updated_user.linkedin_org_urn == "urn:li:company:12345"
    assert updated_setting.timezone == "UTC"
    assert updated_setting.language == "en"
    assert updated_setting.email_notifications == 1
    assert updated_user.linkedin_client_id == "clientid"
    assert updated_user.openai_api_key != ""
    assert updated_user.linkedin_client_secret != ""


def test_users_route_denies_non_admin(client, logged_in_user):
    response = client.get("/users", follow_redirects=True)
    assert response.status_code == 200
    assert b"Admins only" in response.data


def test_users_route_allows_admin(client, db_session):
    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        linkedin_id=f"admin-{uuid.uuid4().hex[:6]}",
        name="Admin User",
        is_admin=1,
        is_active=1,
        is_verified=1,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    with client.session_transaction() as session:
        session["user_id"] = admin.id

    response = client.get("/users")
    assert response.status_code == 200
    assert admin.email.encode() in response.data


def test_inspiration_rss_missing_url_shows_error(client, logged_in_user):
    response = client.post(
        "/inspiration",
        data={"source": "rss", "rss_url": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Provide an RSS feed URL" in response.data


def test_inspiration_linkedin_api_missing_urn_shows_error(client, logged_in_user):
    response = client.post(
        "/inspiration",
        data={"source": "linkedin_api", "linkedin_urn": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Provide a LinkedIn author URN" in response.data


def test_generate_manual_requires_text(client, logged_in_user):
    response = client.post(
        "/generate",
        data={
            "model": "gpt-4o",
            "target": "profile",
            "inspiration_source": "manual",
            "manual_text": "",
            "csrf_token": "test",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Paste an example post to generate from manual inspiration" in response.data


def test_generate_rss_requires_url(client, logged_in_user):
    response = client.post(
        "/generate",
        data={
            "model": "gpt-4o",
            "target": "profile",
            "inspiration_source": "rss",
            "rss_url": "",
            "csrf_token": "test",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Provide an RSS feed URL" in response.data

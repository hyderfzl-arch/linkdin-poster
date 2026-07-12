import pytest
import responses

from models import Draft, InspirationPost, Setting, User


@pytest.fixture
def logged_in_user(client, db_session):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    linkedin_id = f"route-user-{suffix}"
    email = f"route-{suffix}@example.com"
    # Remove any leftover row in the shared test DB so unique constraints pass.
    db_session.query(User).filter(User.email == email).delete(synchronize_session=False)
    user = User(linkedin_id=linkedin_id, email=email, name="Route User")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    with client.session_transaction() as session:
        session["user_id"] = user.id
    return user


def test_settings_post_saves(client, logged_in_user, db_session):
    response = client.post(
        "/settings",
        data={
            "company_name": "Acme Inc",
            "company_context": "We make widgets",
            "default_model": "gpt-4o",
            "default_target": "profile",
            "default_inspiration": "manual",
            "post_time": "14:30",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db_session.expire_all()
    setting = db_session.query(Setting).filter_by(user_id=logged_in_user.id).first()
    assert setting is not None
    assert setting.company_name == "Acme Inc"
    assert setting.post_time == "14:30"


def test_inspiration_post_manual(client, logged_in_user, db_session):
    response = client.post(
        "/inspiration",
        data={"source": "manual", "manual_text": "Example post"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    posts = db_session.query(InspirationPost).filter_by(user_id=logged_in_user.id).all()
    assert any(p.content == "Example post" for p in posts)


def test_inspiration_post_context(client, logged_in_user, db_session):
    response = client.post(
        "/inspiration",
        data={"source": "context"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    posts = db_session.query(InspirationPost).filter_by(user_id=logged_in_user.id).all()
    assert any("company context only" in p.content for p in posts)


def test_inspiration_post_missing_manual_text(client, logged_in_user):
    response = client.post(
        "/inspiration",
        data={"source": "manual", "manual_text": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"example post" in response.data.lower()


def test_generate_post_manual(client, logged_in_user, db_session, monkeypatch):
    monkeypatch.setattr(
        "app.gather_inspiration", lambda db, uid, **kwargs: ["Example inspiration"]
    )
    monkeypatch.setattr(
        "app.generate_post",
        lambda examples, **kwargs: "Generated LinkedIn post",
    )
    response = client.post(
        "/generate",
        data={
            "model": "gpt-4o",
            "target": "profile",
            "inspiration_source": "manual",
            "manual_text": "Example inspiration",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    draft = db_session.query(Draft).filter_by(user_id=logged_in_user.id).first()
    assert draft.content == "Generated LinkedIn post"


def test_generate_post_context(client, logged_in_user, db_session, monkeypatch):
    monkeypatch.setattr("app.gather_inspiration", lambda db, uid, **kwargs: [])
    monkeypatch.setattr(
        "app.generate_post", lambda examples, **kwargs: "Context-only post"
    )
    response = client.post(
        "/generate",
        data={
            "model": "gpt-4o",
            "target": "profile",
            "inspiration_source": "context",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    draft = db_session.query(Draft).filter_by(user_id=logged_in_user.id).first()
    assert draft.content == "Context-only post"


def test_review_draft_renders(client, logged_in_user, db_session):
    draft = Draft(user_id=logged_in_user.id, content="Review me", target="profile")
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)
    response = client.get(f"/draft/{draft.id}")
    assert response.status_code == 200
    assert b"Review me" in response.data


def test_publish_draft_success(client, logged_in_user, db_session, monkeypatch):
    from linkedin_auth import save_tokens

    save_tokens(
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        logged_in_user,
    )
    db_session.commit()

    draft = Draft(user_id=logged_in_user.id, content="Publish me", target="profile")
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    monkeypatch.setattr(
        "app.create_post", lambda user, text, db, target="profile": "urn:li:share:1"
    )

    response = client.post(
        f"/publish/{draft.id}",
        data={"content": "Updated content", "csrf_token": "test"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db_session.refresh(draft)
    assert draft.status == "published"
    assert draft.linkedin_post_id == "urn:li:share:1"


def test_publish_draft_requires_linkedin(client, logged_in_user, db_session):
    draft = Draft(user_id=logged_in_user.id, content="Publish me", target="profile")
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    response = client.post(
        f"/publish/{draft.id}",
        data={"content": "Publish me", "csrf_token": "test"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Connect LinkedIn" in response.data


def test_reject_draft(client, logged_in_user, db_session):
    draft = Draft(user_id=logged_in_user.id, content="Reject me", target="profile")
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    response = client.post(
        f"/reject/{draft.id}",
        data={"csrf_token": "test"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db_session.refresh(draft)
    assert draft.status == "rejected"


def test_drafts_pagination(client, logged_in_user, db_session):
    for i in range(25):
        db_session.add(Draft(user_id=logged_in_user.id, content=f"Draft {i}"))
    db_session.commit()

    response = client.get("/drafts?page=2")
    assert response.status_code == 200
    assert b"page 2" in response.data.lower()


def test_connect_linkedin_redirects(client, logged_in_user):
    response = client.get("/connect-linkedin")
    assert response.status_code == 302
    assert "linkedin.com" in response.location


@responses.activate
def test_callback_success(client, db_session, monkeypatch):
    responses.add(
        responses.POST,
        "https://www.linkedin.com/oauth/v2/accessToken",
        json={"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.linkedin.com/v2/userinfo",
        json={"sub": "cb-user", "email": "cb@example.com", "name": "CB"},
        status=200,
    )

    with client.session_transaction() as session:
        session["linkedin_oauth_state"] = "linkedin-auto-poster"
    response = client.get(
        "/callback?code=auth-code&state=linkedin-auto-poster", follow_redirects=True
    )
    assert response.status_code == 200
    user = db_session.query(User).filter_by(linkedin_id="cb-user").first()
    assert user is not None


def test_callback_missing_code(client):
    with client.session_transaction() as session:
        session["linkedin_oauth_state"] = "linkedin-auto-poster"
    response = client.get(
        "/callback?state=linkedin-auto-poster", follow_redirects=True
    )
    assert response.status_code == 200


def test_callback_oauth_error(client):
    with client.session_transaction() as session:
        session["linkedin_oauth_state"] = "linkedin-auto-poster"
    response = client.get(
        "/callback?error=user_cancelled&state=linkedin-auto-poster",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"error" in response.data.lower()


def test_paginate_invalid_page(client, logged_in_user, db_session):
    for i in range(5):
        db_session.add(Draft(user_id=logged_in_user.id, content=f"Draft {i}"))
    db_session.commit()

    response = client.get("/drafts?page=notanumber")
    assert response.status_code == 200


def test_enforce_https_redirect(client, monkeypatch):
    monkeypatch.setattr("config.FORCE_HTTPS", True)
    response = client.get(
        "/health",
        headers={"X-Forwarded-Proto": "http"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.location.startswith("https://")

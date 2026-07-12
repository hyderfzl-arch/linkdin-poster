import pytest
from sqlalchemy.orm import Session

from models import Draft, InspirationPost, Setting, User


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_dependencies_endpoint(client):
    response = client.get("/health/dependencies")
    assert response.status_code in (200, 503)
    data = response.get_json()
    assert "checks" in data


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")


def test_index_redirects_anonymous_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_generate_page_redirects_anonymous(client):
    response = client.get("/generate")
    assert response.status_code == 302


def test_inspiration_page_redirects_anonymous(client):
    response = client.get("/inspiration")
    assert response.status_code == 302


def test_settings_page_redirects_anonymous(client):
    response = client.get("/settings")
    assert response.status_code == 302


def test_drafts_page_redirects_anonymous(client):
    response = client.get("/drafts")
    assert response.status_code == 302


def test_logout_clears_session(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_404_handler(client):
    response = client.get("/not-a-route")
    assert response.status_code == 404


def test_create_setting(db_session: Session):
    user = User(linkedin_id="test_user", email="test@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # settings are auto-created by get_or_create_settings; delete first
    existing = db_session.query(Setting).filter(Setting.user_id == user.id).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()

    setting = Setting(user_id=user.id, company_name="Acme")
    db_session.add(setting)
    db_session.commit()

    assert setting.id is not None
    assert setting.company_name == "Acme"


def test_create_draft(db_session: Session):
    user = User(linkedin_id="draft_user")
    db_session.add(user)
    db_session.commit()

    draft = Draft(
        user_id=user.id, content="Hello world", model="gpt-4o", target="profile"
    )
    db_session.add(draft)
    db_session.commit()

    assert draft.status == "draft"
    assert draft.user_id == user.id


def test_create_inspiration_post(db_session: Session):
    user = User(linkedin_id="inspiration_user")
    db_session.add(user)
    db_session.commit()

    post = InspirationPost(user_id=user.id, source="manual", content="Inspiration text")
    db_session.add(post)
    db_session.commit()

    assert post.source == "manual"
    assert post.user_id == user.id


@pytest.mark.parametrize("source", ["manual", "rss", "linkedin_api", "context"])
def test_inspiration_source_enum(logged_in_client, source):
    response = logged_in_client.get("/generate")
    assert response.status_code == 200
    assert source.encode() in response.data


def test_reject_draft_redirects(client, db_session):
    # create a draft for the default user id
    user = User(linkedin_id="reject_user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # ensure the session user matches
    with client.session_transaction() as session:
        session["user_id"] = user.id

    draft = Draft(
        user_id=user.id, content="Reject me", model="gpt-4o", target="profile"
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    response = client.post(f"/reject/{draft.id}", follow_redirects=True)
    assert response.status_code == 200

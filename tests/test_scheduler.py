from scheduler import parse_post_time, run_daily_post


def test_parse_post_time():
    import config

    original = config.POST_TIME
    try:
        config.POST_TIME = "14:30"
        assert parse_post_time() == (14, 30)
    finally:
        config.POST_TIME = original


def test_run_daily_post_publishes(db_session, monkeypatch):
    from linkedin_auth import get_or_create_user, save_tokens
    from models import Draft

    user = get_or_create_user(db_session, "scheduler-user")
    save_tokens(
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        user,
    )
    db_session.commit()

    # Mock dependencies so no network calls happen
    monkeypatch.setattr(
        "scheduler.gather_inspiration",
        lambda db, uid, source: ["Example inspiration"],
    )
    monkeypatch.setattr(
        "scheduler.generate_post",
        lambda examples, **kwargs: "Scheduled generated post",
    )
    monkeypatch.setattr(
        "scheduler.create_post",
        lambda user, text, db, target="profile": "urn:li:share:scheduler-1",
    )

    run_daily_post()

    drafts = db_session.query(Draft).filter(Draft.user_id == user.id).all()
    assert len(drafts) == 1
    assert drafts[0].content == "Scheduled generated post"
    assert drafts[0].status == "published"
    assert drafts[0].linkedin_post_id == "urn:li:share:scheduler-1"


def test_run_daily_post_handles_errors(db_session, monkeypatch):
    from linkedin_auth import get_or_create_user, save_tokens
    from models import Draft

    user = get_or_create_user(db_session, "scheduler-user-err")
    save_tokens(
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        user,
    )
    db_session.commit()

    monkeypatch.setattr(
        "scheduler.gather_inspiration",
        lambda db, uid, source: ["Example inspiration"],
    )
    monkeypatch.setattr(
        "scheduler.generate_post",
        lambda examples, **kwargs: "Scheduled generated post",
    )
    monkeypatch.setattr(
        "scheduler.create_post",
        lambda user, text, db, target="profile": (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )

    run_daily_post()
    # No drafts should be persisted on failure
    drafts = db_session.query(Draft).filter(Draft.user_id == user.id).all()
    assert drafts == []

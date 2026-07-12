import pytest

from inspiration import gather_inspiration
from models import InspirationPost


def test_gather_manual_inspiration(db_session):
    result = gather_inspiration(
        db_session, user_id=42, source="manual", manual_text="Example post"
    )
    assert result == ["Example post"]
    stored = (
        db_session.query(InspirationPost).filter_by(user_id=42, source="manual").all()
    )
    assert len(stored) == 1
    assert stored[0].content == "Example post"


def test_gather_context_inspiration(db_session):
    result = gather_inspiration(db_session, user_id=43, source="context")
    assert result == ["Generate from company context only."]
    stored = (
        db_session.query(InspirationPost).filter_by(user_id=43, source="context").all()
    )
    assert len(stored) == 1


def test_gather_inspiration_invalid_source(db_session):
    result = gather_inspiration(db_session, user_id=44, source="manual")
    assert result == []


def test_gather_inspiration_rss_without_feedparser(db_session, monkeypatch):
    def _import(*args, **kwargs):
        if args and args[0] == "feedparser":
            raise ImportError("No module named 'feedparser'")
        return __builtins__["__import__"](*args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _import)
    with pytest.raises(RuntimeError, match="feedparser is not installed"):
        gather_inspiration(
            db_session, user_id=45, source="rss", rss_url="http://example.com/feed"
        )


def test_gather_inspiration_rss_with_mocked_feedparser(db_session, monkeypatch):
    import sys
    import types

    class MockEntry:
        def __init__(self, title, summary, link):
            self.title = title
            self.summary = summary
            self.link = link

        def get(self, key, default=None):
            return getattr(self, key, default)

    class MockFeed:
        entries = [
            MockEntry("Post 1", "Summary 1", "http://example.com/1"),
            MockEntry("Post 2", "Summary 2", "http://example.com/2"),
        ]

    fake_feedparser = types.ModuleType("feedparser")
    fake_feedparser.parse = lambda url: MockFeed()
    monkeypatch.setitem(sys.modules, "feedparser", fake_feedparser)

    result = gather_inspiration(
        db_session, user_id=46, source="rss", rss_url="http://example.com/feed"
    )
    assert len(result) == 2
    assert result[0] == "Summary 1"
    assert result[1] == "Summary 2"


def test_gather_inspiration_rss_empty_feed(db_session, monkeypatch):
    import sys
    import types

    class MockFeed:
        entries = []

    fake_feedparser = types.ModuleType("feedparser")
    fake_feedparser.parse = lambda url: MockFeed()
    monkeypatch.setitem(sys.modules, "feedparser", fake_feedparser)

    result = gather_inspiration(
        db_session, user_id=47, source="rss", rss_url="http://example.com/feed"
    )
    assert result == []


def test_gather_inspiration_linkedin_api(responses, db_session, monkeypatch):
    from linkedin_auth import get_or_create_user, save_tokens

    user = get_or_create_user(db_session, "insp-li-user")
    save_tokens(
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        user,
    )
    responses.add(
        responses.GET,
        "https://api.linkedin.com/rest/posts",
        json={
            "elements": [
                {"commentary": "LinkedIn post 1"},
                {"commentary": "LinkedIn post 2"},
            ]
        },
        status=200,
    )
    result = gather_inspiration(
        db_session,
        user_id=user.id,
        source="linkedin_api",
        linkedin_access_token="tok",
        linkedin_author_urn="urn:li:person:123",
    )
    assert result == ["LinkedIn post 1", "LinkedIn post 2"]

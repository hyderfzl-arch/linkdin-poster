import pytest
import responses

from linkedin_poster import create_post, get_profile_urn, get_headers


def _user_with_token(db_session):
    from linkedin_auth import get_or_create_user, save_tokens

    user = get_or_create_user(db_session, "poster-1")
    save_tokens(
        {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
        db_session,
        user,
    )
    return user


def test_get_headers(db_session):
    user = _user_with_token(db_session)
    headers = get_headers(user, db_session)
    assert headers["Authorization"] == "Bearer tok"
    assert headers["Linkedin-Version"] == "202501"


@responses.activate
def test_get_profile_urn(db_session):
    user = _user_with_token(db_session)
    responses.add(
        responses.GET,
        "https://api.linkedin.com/v2/userinfo",
        json={"sub": "abc-123"},
        status=200,
    )
    urn = get_profile_urn(user, db_session)
    assert urn == "urn:li:person:abc-123"


@responses.activate
def test_get_profile_urn_401(db_session):
    user = _user_with_token(db_session)
    responses.add(
        responses.GET,
        "https://api.linkedin.com/v2/userinfo",
        json={"error": "unauthorized"},
        status=401,
    )
    with pytest.raises(RuntimeError, match="authentication expired"):
        get_profile_urn(user, db_session)


@responses.activate
def test_create_post_profile(db_session):
    user = _user_with_token(db_session)
    responses.add(
        responses.GET,
        "https://api.linkedin.com/v2/userinfo",
        json={"sub": "abc-123"},
        status=200,
    )
    responses.add(
        responses.POST,
        "https://api.linkedin.com/rest/posts",
        headers={"x-restli-id": "urn:li:share:12345"},
        status=201,
    )
    post_id = create_post(
        user, "This is a LinkedIn post text that is long enough.", db_session
    )
    assert post_id == "urn:li:share:12345"


@responses.activate
def test_create_post_company(db_session):
    user = _user_with_token(db_session)
    responses.add(
        responses.POST,
        "https://api.linkedin.com/rest/posts",
        headers={"x-restli-id": "urn:li:share:67890"},
        status=201,
    )
    post_id = create_post(
        user,
        "This is a LinkedIn post text that is long enough.",
        db_session,
        target="company",
        organization_urn="urn:li:organization:999",
    )
    assert post_id == "urn:li:share:67890"


def test_create_post_too_short(db_session):
    user = _user_with_token(db_session)
    with pytest.raises(ValueError, match="too short"):
        create_post(user, "short", db_session)


def test_create_post_missing_company_urn(db_session):
    user = _user_with_token(db_session)
    with pytest.raises(ValueError, match="organization URN"):
        create_post(
            user,
            "This is a LinkedIn post text that is long enough.",
            db_session,
            target="company",
        )


@responses.activate
def test_create_post_linkedin_error(db_session):
    user = _user_with_token(db_session)
    responses.add(
        responses.GET,
        "https://api.linkedin.com/v2/userinfo",
        json={"sub": "abc-123"},
        status=200,
    )
    responses.add(
        responses.POST,
        "https://api.linkedin.com/rest/posts",
        json={"message": "bad request"},
        status=400,
    )
    with pytest.raises(RuntimeError, match="post creation failed"):
        create_post(
            user, "This is a LinkedIn post text that is long enough.", db_session
        )

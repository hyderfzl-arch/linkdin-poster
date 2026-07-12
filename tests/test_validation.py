import pytest

from validation import is_valid_time_format, validate_environment


def test_validate_environment_all_present(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "a-very-long-secret-key-32")
    monkeypatch.setattr("config.LINKEDIN_CLIENT_ID", "client-id")
    monkeypatch.setattr("config.LINKEDIN_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("config.OPENAI_API_KEY", "openai-key")
    monkeypatch.setattr("config.LINKEDIN_REDIRECT_URI", "https://example.com/callback")
    monkeypatch.setattr("config.LINKEDIN_API_VERSION", "202501")
    issues = validate_environment()
    assert issues == []


def test_validate_environment_missing_secret_key(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "")
    issues = validate_environment()
    assert any("SECRET_KEY is required" in issue for issue in issues)


def test_validate_environment_missing_optional(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "a-very-long-secret-key-32")
    monkeypatch.setattr("config.LINKEDIN_CLIENT_ID", "")
    monkeypatch.setattr("config.LINKEDIN_CLIENT_SECRET", "")
    monkeypatch.setattr("config.OPENAI_API_KEY", "")
    monkeypatch.setattr("config.LINKEDIN_REDIRECT_URI", "https://example.com/callback")
    issues = validate_environment()
    assert len([i for i in issues if "not set" in i]) == 3


def test_validate_environment_http_redirect_warning(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "a-very-long-secret-key-32")
    monkeypatch.setattr("config.LINKEDIN_REDIRECT_URI", "http://example.com/callback")
    issues = validate_environment()
    assert any("HTTP on a public domain" in issue for issue in issues)


def test_validate_environment_bad_api_version(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "a-very-long-secret-key-32")
    monkeypatch.setattr("config.LINKEDIN_API_VERSION", "bad")
    issues = validate_environment()
    assert any("YYYYMM" in issue for issue in issues)


def test_validate_environment_short_secret_key(monkeypatch):
    monkeypatch.setattr("config.SECRET_KEY", "short")
    issues = validate_environment()
    assert any("at least 16" in issue for issue in issues)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("09:00", True),
        ("23:59", True),
        ("24:00", False),
        ("9:00", True),
        ("not-a-time", False),
        ("", False),
    ],
)
def test_is_valid_time_format(value, expected):
    assert is_valid_time_format(value) is expected

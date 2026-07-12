import re

from app import (
    _linkedin_format,
    _safe_company_name,
    _safe_company_context,
    _safe_model,
    _safe_target,
    _safe_inspiration,
    get_db,
)


def test_linkedin_format_basic():
    text = "Hello #world\n\nVisit https://example.com"
    out = _linkedin_format(text)
    assert "lp-hashtag" in str(out)
    assert "https://example.com" in str(out)


def test_safe_helpers_defaults():
    assert _safe_company_name("  Acme ") == "Acme"
    assert _safe_company_context(" ctx ") == "ctx"
    assert _safe_model("invalid-model") == "gpt-4o"
    assert _safe_target("bad") == "profile"
    assert _safe_inspiration("unknown") == "manual"


def test_get_db_generator_and_session(db_session):
    # Ensure get_db() yields a usable session (conftest provides db_session)
    gdb = next(get_db())
    try:
        # basic query should run without error
        r = gdb.execute("SELECT 1").scalar()
        assert int(r) == 1
    finally:
        gdb.close()

import logging
import urllib.parse
from datetime import timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

import config
from http_client import get_http_session, get_timeout
from models import User
from security import decrypt, encrypt
from utils import utc_now

logger = logging.getLogger(__name__)
_http = get_http_session()


def build_auth_url(state: str) -> str:
    if not state:
        raise RuntimeError("A non-empty OAuth state parameter is required.")
    if not config.LINKEDIN_CLIENT_ID or not config.LINKEDIN_REDIRECT_URI:
        raise RuntimeError("LinkedIn OAuth credentials are not configured.")
    params = {
        "response_type": "code",
        "client_id": config.LINKEDIN_CLIENT_ID,
        "redirect_uri": config.LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": config.LINKEDIN_OAUTH_SCOPES,
    }
    return f"{config.AUTH_URL}?{urllib.parse.urlencode(params)}"


def _post_token(data: dict) -> dict:
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = _http.post(config.TOKEN_URL, data=data, headers=headers, timeout=get_timeout())
    try:
        resp.raise_for_status()
    except Exception as e:
        logger.error(
            "LinkedIn token request failed: %s - %s", resp.status_code, resp.text
        )
        raise RuntimeError(f"LinkedIn token request failed: {resp.text}") from e
    return resp.json()


def exchange_code_for_token(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.LINKEDIN_REDIRECT_URI,
        "client_id": config.LINKEDIN_CLIENT_ID,
        "client_secret": config.LINKEDIN_CLIENT_SECRET,
    }
    return _post_token(data)


def refresh_access_token(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.LINKEDIN_CLIENT_ID,
        "client_secret": config.LINKEDIN_CLIENT_SECRET,
    }
    return _post_token(data)


def fetch_userinfo(access_token: str) -> dict:
    url = "https://api.linkedin.com/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = _http.get(url, headers=headers, timeout=get_timeout())
    try:
        resp.raise_for_status()
    except Exception as e:
        logger.error("LinkedIn userinfo fetch failed: %s - %s", resp.status_code, resp.text)
        raise RuntimeError(f"LinkedIn userinfo fetch failed: {resp.text}") from e
    return resp.json()


def save_tokens(tokens: dict, db: Session, user: User):
    user.access_token = encrypt(tokens.get("access_token", ""))
    user.refresh_token = encrypt(tokens.get("refresh_token", ""))
    expires_in = tokens.get("expires_in", 3600)
    user.token_expires_at = utc_now() + timedelta(seconds=int(expires_in))
    db.commit()


def load_tokens(user: User) -> dict:
    return {
        "access_token": decrypt(user.access_token or ""),
        "refresh_token": decrypt(user.refresh_token or ""),
    }


def get_or_create_user(
    db: Session,
    linkedin_id: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> User:
    user = db.query(User).filter(User.linkedin_id == linkedin_id).first()
    if not user:
        # If a password-registered user already has this email, link the LinkedIn account to it.
        if email:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                existing.linkedin_id = linkedin_id
                existing.name = name or existing.name
                db.commit()
                db.refresh(existing)
                return existing
        user = User(linkedin_id=linkedin_id, email=email, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_valid_access_token(db: Session, user: User) -> str:
    """Return a non-expired, decrypted access token, refreshing it if possible."""
    tokens = load_tokens(user)
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")

    # Treat tokens as expired 5 minutes before the recorded expiry to avoid edge cases.
    now = utc_now() + timedelta(minutes=5)
    token_expires_at = user.token_expires_at
    if token_expires_at is not None and token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
    is_expired = token_expires_at is None or token_expires_at <= now

    if access_token and not is_expired:
        return access_token

    if not refresh_token:
        raise RuntimeError(
            "LinkedIn access token expired and no refresh token is available. "
            "Please reconnect LinkedIn."
        )

    logger.info("Refreshing LinkedIn access token for user %s", user.id)
    new_tokens = refresh_access_token(refresh_token)
    save_tokens(new_tokens, db, user)
    new_access = new_tokens.get("access_token", "")
    if not new_access:
        raise RuntimeError(
            "LinkedIn token refresh did not return an access token. Please reconnect LinkedIn."
        )
    return new_access

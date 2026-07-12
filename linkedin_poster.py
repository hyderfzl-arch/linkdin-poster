import logging

import config
import requests
from http_client import get_http_session, get_timeout
from linkedin_auth import get_valid_access_token
from models import User

logger = logging.getLogger(__name__)
_http = get_http_session()


def get_headers(user: User, db):
    access_token = get_valid_access_token(db, user)
    if not access_token:
        raise RuntimeError(
            "No LinkedIn access token found. Please connect LinkedIn first."
        )
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Linkedin-Version": config.LINKEDIN_API_VERSION,
        "Content-Type": "application/json",
    }


def get_profile_urn(user: User, db) -> str:
    url = "https://api.linkedin.com/v2/userinfo"
    resp = _http.get(url, headers=get_headers(user, db), timeout=get_timeout())
    if resp.status_code == 401:
        raise RuntimeError(
            "LinkedIn authentication expired. Please reconnect LinkedIn."
        )
    try:
        resp.raise_for_status()
    except Exception:
        _handle_linkedin_error(resp, "userinfo")
        raise
    data = resp.json()
    sub = data.get("sub", "")
    if not sub:
        raise RuntimeError("LinkedIn userinfo did not return a valid user ID.")
    return f"urn:li:person:{sub}"


def _handle_linkedin_error(resp: requests.Response, action: str):
    try:
        data = resp.json()
        message = data.get("message", data.get("error", resp.text))
    except Exception:
        message = resp.text or f"HTTP {resp.status_code}"
    logger.error("LinkedIn %s failed: %s - %s", action, resp.status_code, message)
    raise RuntimeError(f"LinkedIn {action} failed ({resp.status_code}): {message}")


def create_post(
    user: User, text: str, db, target: str = "profile", organization_urn: str = ""
) -> str:
    if config.DEMO_MODE:
        import uuid

        return f"urn:li:share:DEMO-{uuid.uuid4().hex[:12].upper()}"

    if not text or len(text.strip()) < 10:
        raise ValueError("Post text is too short.")

    org_urn = organization_urn or user.linkedin_org_urn or ""

    if target == "company":
        author = org_urn
        if not author:
            raise ValueError("Company posting requires an organization URN.")
    else:
        author = get_profile_urn(user, db)

    payload = {
        "author": author,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    resp = _http.post(
        config.POSTS_API_URL, headers=get_headers(user, db), json=payload, timeout=get_timeout()
    )
    if resp.status_code not in (200, 201):
        _handle_linkedin_error(resp, "post creation")
    return resp.headers.get("x-restli-id", resp.text)

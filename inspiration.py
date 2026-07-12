"""Inspiration input module.

LinkedIn's member post search API is restricted and scraping is against the ToS.
This module supports multiple sources:
1. Manual paste (always works)
2. Public RSS feeds of company pages (best effort)
3. LinkedIn Community Management API (requires approved access)
4. No inspiration: generate from company context only
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from http_client import get_http_session, get_timeout
from models import InspirationPost

logger = logging.getLogger(__name__)
_http = get_http_session()


def fetch_rss_inspiration(feed_url: str, limit: int = 5) -> list[dict]:
    try:
        import feedparser
    except ImportError:
        raise RuntimeError(
            "feedparser is not installed. Add it to requirements.txt for RSS support."
        )

    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries[:limit]:
        items.append(
            {
                "source": "rss",
                "title": entry.get("title", ""),
                "content": entry.get("summary", entry.get("description", "")),
                "url": entry.get("link", ""),
            }
        )
    if not items:
        logger.warning("RSS feed returned no entries: %s", feed_url)
    return items


def fetch_linkedin_api_inspiration(
    access_token: str, author_urn: str, limit: int = 5
) -> list[dict]:
    import config

    if getattr(config, "DEMO_MODE", False):
        return [
            {
                "source": "linkedin_api",
                "title": "",
                "content": "Demo LinkedIn API inspiration post: AI is transforming how small teams build and share content.",
                "url": "",
            }
            for _ in range(min(limit, 3))
        ]

    # This requires approved r_organization_social or r_member_social.
    url = "https://api.linkedin.com/rest/posts"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Linkedin-Version": "202501",
        "Content-Type": "application/json",
    }
    params = {
        "author": author_urn,
        "q": "author",
        "count": limit,
        "sortBy": "LAST_MODIFIED",
    }
    resp = _http.get(url, headers=headers, params=params, timeout=get_timeout())
    try:
        resp.raise_for_status()
    except Exception as e:
        logger.error(
            "LinkedIn inspiration fetch failed: %s - %s", resp.status_code, resp.text
        )
        raise RuntimeError(f"LinkedIn inspiration fetch failed: {resp.text}") from e
    data = resp.json()
    items = []
    for element in data.get("elements", []):
        items.append(
            {
                "source": "linkedin_api",
                "title": "",
                "content": element.get("commentary", ""),
                "url": "",
            }
        )
    return items


def gather_inspiration(
    db: Session,
    user_id: int,
    source: str = "manual",
    manual_text: Optional[str] = None,
    rss_url: Optional[str] = None,
    linkedin_access_token: Optional[str] = None,
    linkedin_author_urn: Optional[str] = None,
) -> list[str]:
    raw_posts: list[InspirationPost] = []

    if source == "manual" and manual_text:
        raw_posts.append(
            InspirationPost(
                user_id=user_id, source="manual", content=manual_text.strip()
            )
        )

    elif source == "rss" and rss_url:
        items = fetch_rss_inspiration(rss_url)
        for item in items:
            item_source = item.pop("source", "rss")
            raw_posts.append(
                InspirationPost(user_id=user_id, source=item_source, **item)
            )

    elif source == "linkedin_api" and linkedin_access_token and linkedin_author_urn:
        items = fetch_linkedin_api_inspiration(
            linkedin_access_token, linkedin_author_urn
        )
        for item in items:
            item_source = item.pop("source", "linkedin_api")
            raw_posts.append(
                InspirationPost(user_id=user_id, source=item_source, **item)
            )

    elif source == "context":
        raw_posts.append(
            InspirationPost(
                user_id=user_id,
                source="context",
                content="Generate from company context only.",
            )
        )

    if raw_posts:
        db.add_all(raw_posts)
        db.commit()

    return [post.content for post in raw_posts if post.content]

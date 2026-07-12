"""Shared HTTP client with production-safe timeouts and retries.

All outbound calls use a single requests.Session configured to tolerate
transient network failures without retrying dangerous non-idempotent work
based on HTTP status codes.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30  # seconds


def _make_retry_strategy() -> Retry:
    """Retry on connection/read/redirect errors, but not on HTTP status codes.

    Application-level handling of 4xx/5xx remains the responsibility of the
    caller so that error messages and retry policies can stay domain-specific.
    """
    return Retry(
        total=3,
        connect=3,
        read=3,
        redirect=3,
        backoff_factor=0.5,
        raise_on_status=False,
        status_forcelist=None,
        allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]),
    )


def get_http_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_make_retry_strategy())
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_timeout() -> int:
    return _DEFAULT_TIMEOUT

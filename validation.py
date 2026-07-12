"""Startup validation helpers."""

import re

import config

REQUIRED_ENVS = [
    "SECRET_KEY",
]

OPTIONAL_BUT_WARN = [
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "OPENAI_API_KEY",
]


def validate_environment() -> list[str]:
    """Return a list of human-readable issues found at startup."""
    issues: list[str] = []

    for name in REQUIRED_ENVS:
        if not getattr(config, name, None):
            issues.append(f"{name} is required but not set.")

    for name in OPTIONAL_BUT_WARN:
        if not getattr(config, name, None):
            issues.append(
                f"{name} is not set. LinkedIn/OpenAI features will be unavailable."
            )

    if config.LINKEDIN_REDIRECT_URI.startswith(
        "http://"
    ) and not config.LINKEDIN_REDIRECT_URI.startswith("http://localhost"):
        issues.append(
            "LINKEDIN_REDIRECT_URI uses HTTP on a public domain. LinkedIn OAuth may require HTTPS."
        )

    if not re.fullmatch(r"\d{6}", config.LINKEDIN_API_VERSION):
        issues.append("LINKEDIN_API_VERSION should be a YYYYMM value like 202501.")

    if config.SECRET_KEY and len(config.SECRET_KEY) < 16:
        issues.append("SECRET_KEY is too short. Use at least 16 random characters.")

    if config.ENVIRONMENT == "production" and config.RATE_LIMIT_STORAGE_URI == "memory://":
        issues.append(
            "RATE_LIMIT_STORAGE_URI is 'memory://'. Production deployments with more than one worker should use Redis (e.g. redis://localhost:6379)."
        )

    if config.ENVIRONMENT == "production" and config.MAX_CONTENT_LENGTH > 16 * 1024 * 1024:
        issues.append("MAX_CONTENT_LENGTH is very large (>16 MB). Verify this is intentional.")

    return issues


def is_valid_time_format(value: str) -> bool:
    return bool(re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value))

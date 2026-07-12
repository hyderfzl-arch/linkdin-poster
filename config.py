import os
from dotenv import load_dotenv

load_dotenv()

LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv(
    "LINKEDIN_REDIRECT_URI", "http://localhost:5000/callback"
)
LINKEDIN_API_VERSION = os.getenv("LINKEDIN_API_VERSION", "202501")
LINKEDIN_OAUTH_SCOPES = os.getenv(
    "LINKEDIN_OAUTH_SCOPES", "openid profile email w_member_social"
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local.db")

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

POST_TIME = os.getenv("POST_TIME", "09:00")
COMPANY_NAME = os.getenv("COMPANY_NAME", "")
COMPANY_CONTEXT = os.getenv("COMPANY_CONTEXT", "")

# Production toggles
FORCE_HTTPS = os.getenv("FORCE_HTTPS", "false").lower() in ("1", "true", "yes")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("1", "true", "yes")

if ENVIRONMENT == "production" and len(SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY must be at least 32 characters long in production. "
        "Generate a strong random key and set it via the SECRET_KEY environment variable."
    )

# Optional admin seeding. Set both ADMIN_EMAIL and ADMIN_PASSWORD to create the
# initial admin user on startup. If unset, no admin account is seeded.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Dedicated Fernet encryption key (URL-safe base64, 32 raw bytes).
# Strongly recommended in production so token encryption is independent of SECRET_KEY.
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Security / session
WTF_CSRF_ENABLED = os.getenv("WTF_CSRF_ENABLED", "true").lower() not in (
    "0",
    "false",
    "no",
)
WTF_CSRF_TIME_LIMIT = int(os.getenv("WTF_CSRF_TIME_LIMIT", "3600"))
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() not in (
    "0",
    "false",
    "no",
)
SESSION_COOKIE_HTTPONLY = os.getenv("SESSION_COOKIE_HTTPONLY", "true").lower() not in (
    "0",
    "false",
    "no",
)
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", "86400"))
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024)))  # 2 MB

# Rate limiting
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() not in (
    "0",
    "false",
    "no",
)
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

# Background scheduler. Disable in serverless/web containers (e.g. Vercel,
# Docker web service) and run the scheduler as a separate process/service.
SCHEDULER_ENABLED = os.getenv(
    "SCHEDULER_ENABLED", "true"
).lower() not in ("0", "false", "no")

# Content Security Policy for Talisman.
# Inline scripts/styles must carry a nonce generated per request; see
# Talisman's content_security_policy_nonce_in setting in app.py.
CSP = {
    "default-src": "'self'",
    "script-src": ["'self'", "https://cdn.tailwindcss.com"],
    "style-src": ["'self'", "https://fonts.googleapis.com"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'", "https://fonts.gstatic.com"],
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "upgrade-insecure-requests": "",
}

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Email / SMTP configuration
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
EMAIL_VERIFICATION_REQUIRED = os.getenv(
    "EMAIL_VERIFICATION_REQUIRED", "true"
).lower() in ("1", "true", "yes")
VERIFICATION_CODE_TTL_SECONDS = int(
    os.getenv("VERIFICATION_CODE_TTL_SECONDS", "600")
)

# Demo mode is convenient for local evaluation but must never be enabled in
# production because it creates a hardcoded, fully-authenticated user.
if ENVIRONMENT == "production" and DEMO_MODE:
    raise RuntimeError(
        "DEMO_MODE must not be enabled in production. "
        "Set DEMO_MODE=false or use a non-production ENVIRONMENT."
    )

POSTS_API_URL = "https://api.linkedin.com/rest/posts"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
TOKEN_FILE = "tokens.json"

import atexit
import logging
import os
import secrets
from datetime import datetime, timedelta

from utils import as_utc, utc_now

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session as flask_session,
    make_response,
    g,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from prometheus_client import (
    CollectorRegistry,
    generate_latest,
    Counter,
    Histogram,
    Info,
)
from sqlalchemy.orm import Session

import config
from content_generator import generate_post
from forms import (
    GenerateForm,
    InspirationForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
    SettingsForm,
    VerifyForm,
)
from email_sender import generate_verification_code, send_verification_email
from inspiration import gather_inspiration
from linkedin_auth import (
    build_auth_url,
    exchange_code_for_token,
    fetch_userinfo,
    get_or_create_user,
    save_tokens,
)
from linkedin_poster import create_post
from models import Draft, InspirationPost, SessionLocal, Setting, User, get_db, init_db
from security import decrypt, encrypt
import re
from scheduler import shutdown_scheduler, start_scheduler
from validation import validate_environment
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["WTF_CSRF_ENABLED"] = config.WTF_CSRF_ENABLED
app.config["WTF_CSRF_TIME_LIMIT"] = config.WTF_CSRF_TIME_LIMIT
app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_HTTPONLY"] = config.SESSION_COOKIE_HTTPONLY
app.config["SESSION_COOKIE_SAMESITE"] = config.SESSION_COOKIE_SAMESITE
app.config["PERMANENT_SESSION_LIFETIME"] = config.PERMANENT_SESSION_LIFETIME
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

# Production extensions
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=config.RATE_LIMIT_STORAGE_URI,
    enabled=config.RATE_LIMIT_ENABLED,
)
talisman = Talisman(
    app,
    force_https=config.FORCE_HTTPS,
    strict_transport_security=config.FORCE_HTTPS,
    content_security_policy=config.CSP,
    content_security_policy_nonce_in=["script-src", "style-src"],
)

# Prometheus metrics
registry = CollectorRegistry()
http_requests_total = Counter(
    "app_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry,
)
http_request_duration_seconds = Histogram(
    "app_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    registry=registry,
)
app_info = Info("app_info", "Application info", registry=registry)
app_info.info({"version": config.APP_VERSION, "environment": config.ENVIRONMENT})

# Validate environment at startup.
startup_issues = validate_environment()
for issue in startup_issues:
    logger.warning("Startup validation: %s", issue)

def _linkedin_format(text: str) -> str:
    """Convert plain post text into LinkedIn-like HTML: paragraphs + linked hashtags.

    Escapes all user-supplied content before injecting markup so that the
    resulting HTML can be safely rendered with Jinja's ``| safe`` filter.
    """
    if not text:
        return ""
    text = escape(text.strip())
    paragraphs = re.split(r"\n\s*\n", text)
    out = ""
    for p in paragraphs:
        p_html = re.sub(
            r"#(\w+)",
            r'<a href="https://www.linkedin.com/feed/hashtag/?keywords=\1" class="lp-hashtag" target="_blank">#\1</a>',
            p.replace("\n", "<br>"),
        )
        # Link bare URLs lightly
        p_html = re.sub(
            r"(https?://[^\s\)]+)",
            r'<a href="\1" target="_blank" rel="noopener">\1</a>',
            p_html,
        )
        out += f'<p class="mb-3 last:mb-0">{p_html}</p>'
    return Markup(out)


@app.template_filter("linkedin_format")
def linkedin_format_filter(text):
    return _linkedin_format(text)


init_db()

app.debug = config.ENVIRONMENT != "production"

scheduler = None
if config.ENVIRONMENT != "test" and config.SCHEDULER_ENABLED:
    # Avoid starting the scheduler twice when Werkzeug's reloader spawns a
    # parent watchdog process. Run only in the actual application process.
    # Serverless/web containers should set SCHEDULER_ENABLED=false and run the
    # scheduler as a separate process (see cli.py run-scheduler).
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler = start_scheduler()
        atexit.register(lambda: shutdown_scheduler(scheduler))


@app.after_request
def after_request(response):
    http_requests_total.labels(
        method=request.method,
        endpoint=request.endpoint or "unknown",
        status=str(response.status_code)[:3],
    ).inc()
    return response


@app.before_request
def enforce_https():
    """Redirect HTTP to HTTPS when FORCE_HTTPS is enabled in production."""
    if (
        config.FORCE_HTTPS
        and request.headers.get("X-Forwarded-Proto", request.scheme) == "http"
    ):
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)


@app.errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    logger.exception("Unhandled 500 error: %s", error)
    return render_template("errors/500.html"), 500


@app.route("/health")
@limiter.exempt
def health():
    return {
        "status": "ok",
        "environment": config.ENVIRONMENT,
        "version": config.APP_VERSION,
        "timestamp": utc_now().isoformat(),
    }


@app.route("/health/dependencies")
@limiter.exempt
def health_dependencies():
    checks = {}
    # Database
    try:
        db = get_db_session()
        db.execute("SELECT 1")
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}

    # LinkedIn token presence (not a live API call to avoid rate limits)
    try:
        db = get_db_session()
        user = db.query(User).filter(User.id == current_user_id()).first()
        checks["linkedin_token"] = {
            "status": "ok" if (user and user.access_token) else "missing",
        }
    except Exception as e:
        checks["linkedin_token"] = {"status": "error", "message": str(e)}

    # OpenAI key configured
    checks["openai"] = {
        "status": "ok" if config.OPENAI_API_KEY else "missing",
    }

    all_ok = all(c.get("status") == "ok" for c in checks.values())
    response = make_response(
        {"status": "ok" if all_ok else "degraded", "checks": checks}
    )
    response.status_code = 200 if all_ok else 503
    return response


@app.route("/metrics")
@limiter.exempt
def metrics():
    return generate_latest(registry), 200, {"Content-Type": "text/plain; charset=utf-8"}


def current_user_id() -> int | None:
    return flask_session.get("user_id")


def _require_login():
    """Redirect anonymous users to the login page, unless demo mode is active."""
    if config.DEMO_MODE:
        return
    if not current_user_id():
        flash("Please log in to continue.", "info")
        return redirect(url_for("login"))


def get_current_user(db: Session) -> User | None:
    uid = current_user_id()
    if not uid:
        return None
    return db.query(User).filter(User.id == uid).first()


def get_db_session() -> Session:
    """Return a request-scoped database session, creating one if needed.

    The session is closed automatically at the end of each request via
    teardown_appcontext.
    """
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def _close_db_session(exc: BaseException | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_admin_user(db: Session) -> User | None:
    """Seed an admin account from environment variables if configured.

    Set ADMIN_EMAIL and ADMIN_PASSWORD to create the initial admin user on
    startup. The password is hashed with Werkzeug before storage. If either
    variable is unset, no admin account is seeded.
    """
    email = config.ADMIN_EMAIL.strip()
    password = config.ADMIN_PASSWORD
    if not email or not password:
        return None

    user = db.query(User).filter(User.email == email).first()
    password_hash = generate_password_hash(password)
    if user:
        user.is_admin = 1
        user.is_verified = 1
        user.is_active = 1
        user.password_hash = password_hash
        db.commit()
        return user

    user = User(
        email=email,
        name="Admin User",
        password_hash=password_hash,
        is_active=1,
        is_admin=1,
        is_verified=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Admin user seeded: %s", email)
    return user


# Seed the admin user once at startup only when explicitly configured.
if config.ENVIRONMENT != "test" and config.ADMIN_EMAIL and config.ADMIN_PASSWORD:
    _admin_db = SessionLocal()
    try:
        _ensure_admin_user(_admin_db)
    finally:
        _admin_db.close()


def _ensure_demo_user(db: Session) -> User:
    """Create a fake connected user so demo mode works end-to-end."""
    demo_password_hash = generate_password_hash("password123")
    user = db.query(User).filter(User.id == 1).first()
    if user:
        if not user.access_token:
            user.access_token = "demo-access-token"
        if not user.password_hash:
            user.password_hash = demo_password_hash
        db.commit()
        return user
    user = User(
        id=1,
        linkedin_id="demo-linkedin-user",
        email="demo@example.com",
        name="Demo User",
        password_hash=demo_password_hash,
        headline="Building LinkedIn Auto-Poster · AI-powered content workflow",
        avatar_url="https://i.pravatar.cc/150?u=demo",
        access_token="demo-access-token",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_demo_data(db: Session, user_id: int) -> None:
    """Insert realistic mock inspiration and draft rows once."""
    existing_inspiration = db.query(InspirationPost).filter(InspirationPost.user_id == user_id).first()
    if existing_inspiration:
        return

    sample_inspiration = [
        (
            "manual",
            "We just shipped a feature that cuts reporting time in half — small teams deserve big tooling too. "
            "The real win wasn't the code; it was the 6 hours a week our customers get back.",
        ),
        (
            "manual",
            "The best AI tools don’t replace people; they remove the busywork so people can focus on what matters. "
            "That difference shows up in morale, speed, and ultimately revenue.",
        ),
        (
            "rss",
            "LinkedIn algorithm update: comments in the first hour still matter more than likes. "
            "If you want reach, design posts that start conversations, not just applause.",
        ),
        (
            "context",
            "Generate from company context only.",
        ),
    ]
    for source, content in sample_inspiration:
        db.add(InspirationPost(user_id=user_id, source=source, content=content))

    sample_drafts = [
        (
            "🚀 Just shipped: a smarter way for small teams to stay active on LinkedIn.\n\n"
            "We built Auto-Poster so founders can turn a few example posts into a week of ready-to-publish drafts — "
            "no copywriting block, no late-night scheduling.\n\n"
            "The first draft takes under a minute. The rest run on autopilot.\n\n"
            "#FounderLife #LinkedIn #ContentAutomation #SmallBusiness",
            "draft",
            "gpt-4o",
            "profile",
        ),
        (
            "🔍 3 signs your LinkedIn strategy is leaking opportunities:\n\n"
            "1. You post only when inspiration strikes.\n"
            "2. Every draft starts from a blank page.\n"
            "3. Great ideas sit in notes apps and never ship.\n\n"
            "Consistent presence beats viral moments. Build a system that writes while you sleep.\n\n"
            "#LinkedInStrategy #B2BMarketing #Consistency",
            "draft",
            "gpt-4o-mini",
            "profile",
        ),
        (
            "✅ Published: our first demo post via LinkedIn Auto-Poster.\n\n"
            "The app generated the draft from saved inspiration, let me edit in one screen, and published in a single click.\n\n"
            "If you're building in public, this is the kind of leverage you want.\n\n"
            "#BuildInPublic #Automation #Productivity",
            "published",
            "gpt-4o",
            "profile",
        ),
        (
            "💡 The best AI content tools don't replace your voice — they amplify it.\n\n"
            "We feed the model example posts that already sound like us, then let it draft variations that stay on brand.\n\n"
            "Result: more posts, same voice, less burnout.\n\n"
            "#AI #ContentMarketing #BrandVoice",
            "rejected",
            "o4-mini",
            "profile",
        ),
    ]
    for content, status, model, target in sample_drafts:
        db.add(
            Draft(
                user_id=user_id,
                content=content,
                status=status,
                model=model,
                target=target,
            )
        )

    db.commit()


def get_or_create_settings(db: Session, user_id: int) -> Setting:
    setting = db.query(Setting).filter(Setting.user_id == user_id).first()
    if not setting:
        setting = Setting(user_id=user_id)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def _safe_company_context(value: str) -> str:
    return value.strip()[:2000]


def _safe_company_name(value: str) -> str:
    return value.strip()[:255]


def _safe_model(value: str) -> str:
    allowed = {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "o3",
        "o4-mini",
    }
    return value if value in allowed else "gpt-4o"


def _safe_target(value: str) -> str:
    return value if value in {"profile", "company", "choose"} else "profile"


def _safe_inspiration(value: str) -> str:
    return value if value in {"manual", "rss", "linkedin_api", "context"} else "manual"


def _paginate(query, page_param: str = "page", per_page: int = 20):
    try:
        page = max(1, int(request.args.get(page_param, 1)))
    except (ValueError, TypeError):
        page = 1
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, page, per_page, total


def _csrf_valid() -> bool:
    """Manually validate the Flask-WTF CSRF token for non-WTForms POST routes."""
    if not config.WTF_CSRF_ENABLED:
        return True
    from flask_wtf.csrf import validate_csrf

    token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    if not token:
        return False
    try:
        validate_csrf(token)
        return True
    except Exception:
        return False


@app.route("/")
def index():
    db = get_db_session()
    if config.DEMO_MODE:
        _ensure_demo_user(db)
        _seed_demo_data(db, 1)
        flask_session["user_id"] = 1
    elif not current_user_id():
        return redirect(url_for("login"))
    user = get_current_user(db)
    settings = get_or_create_settings(db, current_user_id() or 1)
    connected = bool(user and user.access_token)
    return render_template("index.html", connected=connected, settings=settings, user=user)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def register():
    if current_user_id():
        return redirect(url_for("index"))
    form = RegisterForm()
    if form.validate_on_submit():
        db = get_db_session()
        if db.query(User).filter(User.email == form.email.data.lower()).first():
            flash("An account with that email already exists. Please log in.", "error")
            return redirect(url_for("login"))
        user = User(
            email=form.email.data.lower(),
            name=form.name.data.strip(),
            password_hash=generate_password_hash(form.password.data),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        get_or_create_settings(db, user.id)

        # Require email verification before first login
        if config.EMAIL_VERIFICATION_REQUIRED:
            user.verification_code = generate_verification_code()
            user.verification_sent_at = utc_now()
            db.commit()
            send_verification_email(
                to_email=user.email,
                to_name=user.name or user.email,
                code=user.verification_code,
                subject="Verify your LinkedIn Auto-Poster account",
            )
            flask_session["pending_verification_email"] = user.email
            flash("Check your email for a verification code.", "info")
            return redirect(url_for("verify"))

        # Regenerate session after account creation to prevent fixation.
        flask_session.clear()
        flask_session["user_id"] = user.id
        flask_session.permanent = True
        flash("Account created! Welcome to LinkedIn Auto-Poster.", "success")
        return redirect(url_for("index"))
    return render_template("register.html", form=form)


@app.route("/verify", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def verify():
    if current_user_id():
        return redirect(url_for("index"))

    email = flask_session.get("pending_verification_email")
    form = VerifyForm()
    if form.email.data:
        pass
    elif email:
        form.email.data = email
    else:
        flash("Please register first.", "error")
        return redirect(url_for("register"))

    if form.validate_on_submit():
        db = get_db_session()
        user = (
            db.query(User)
            .filter(
                User.email == form.email.data.lower(),
                User.verification_code == form.code.data.strip().upper(),
                User.is_active == 1,
            )
            .first()
        )
        if not user:
            flash("Invalid or expired verification code.", "error")
            return render_template("verify.html", form=form)

        sent_at = as_utc(user.verification_sent_at)
        if sent_at is None or utc_now() > sent_at + timedelta(
            seconds=config.VERIFICATION_CODE_TTL_SECONDS
        ):
            flash("Verification code has expired. Please request a new one.", "error")
            return render_template("verify.html", form=form)

        user.is_verified = 1
        user.verification_code = None
        user.verified_at = utc_now()
        user.last_login_at = utc_now()
        db.commit()

        # Regenerate session on identity elevation (email verified → logged in).
        flask_session.clear()
        flask_session["user_id"] = user.id
        flask_session.permanent = True
        flash("Email verified! Welcome to LinkedIn Auto-Poster.", "success")
        return redirect(url_for("index"))

    return render_template("verify.html", form=form)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("30 per hour")
def login():
    if current_user_id():
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        db = get_db_session()
        user = (
            db.query(User)
            .filter(User.email == form.email.data.lower(), User.is_active == 1)
            .first()
        )
        if user and user.password_hash and check_password_hash(
            user.password_hash, form.password.data
        ):
            if config.EMAIL_VERIFICATION_REQUIRED and not user.is_verified:
                user.verification_code = generate_verification_code()
                user.verification_sent_at = utc_now()
                db.commit()
                send_verification_email(
                    to_email=user.email,
                    to_name=user.name or user.email,
                    code=user.verification_code,
                    subject="Verify your LinkedIn Auto-Poster account",
                )
                flask_session["pending_verification_email"] = user.email
                flash("Please verify your email before logging in. A new code has been sent.", "error")
                return redirect(url_for("verify"))
            user.last_login_at = utc_now()
            db.commit()
            # Prevent session fixation by clearing the session before storing
            # the authenticated user identifier.
            flask_session.clear()
            flask_session["user_id"] = user.id
            flask_session.permanent = True
            flash("Welcome back!", "success")
            return redirect(url_for("index"))
        flash("Invalid email or password.", "error")
    return render_template("login.html", form=form)


@app.route("/connect-linkedin")
@limiter.limit("10 per hour")
def connect_linkedin():
    require = _require_login()
    if require:
        return require
    state = secrets.token_urlsafe(32)
    flask_session["linkedin_oauth_state"] = state
    return redirect(build_auth_url(state=state))


@app.route("/callback")
@limiter.limit("20 per hour")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")
    returned_state = request.args.get("state", "")
    expected_state = flask_session.pop("linkedin_oauth_state", None)
    if expected_state is None or returned_state != expected_state:
        logger.warning("LinkedIn OAuth state mismatch")
        flash("Invalid or expired LinkedIn auth request. Please try again.", "error")
        return redirect(url_for("index"))

    if error:
        logger.warning("LinkedIn OAuth error: %s", error)
        flash(f"LinkedIn auth error: {error}", "error")
        return redirect(url_for("index"))
    if not code:
        flash("Missing authorization code", "error")
        return redirect(url_for("index"))

    try:
        tokens = exchange_code_for_token(code)
    except Exception as e:
        logger.exception("LinkedIn token exchange failed")
        flash(f"Failed to connect LinkedIn: {e}", "error")
        return redirect(url_for("index"))

    access_token = tokens.get("access_token")
    if not access_token:
        flash("LinkedIn did not return an access token.", "error")
        return redirect(url_for("index"))

    try:
        userinfo = fetch_userinfo(access_token)
    except Exception as e:
        logger.exception("LinkedIn userinfo fetch failed")
        flash(f"Failed to fetch LinkedIn profile: {e}", "error")
        return redirect(url_for("index"))

    linkedin_id = userinfo.get("sub")
    if not linkedin_id:
        flash("LinkedIn did not return a user ID.", "error")
        return redirect(url_for("index"))

    db = get_db_session()
    try:
        user = get_or_create_user(
            db, linkedin_id, email=userinfo.get("email"), name=userinfo.get("name")
        )
        save_tokens(tokens, db, user)
    except Exception as e:
        logger.exception("Failed to save LinkedIn tokens")
        flash(f"Failed to save credentials: {e}", "error")
        return redirect(url_for("index"))

    flask_session["user_id"] = user.id
    flash("LinkedIn connected successfully!", "success")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@limiter.limit("100 per hour")
def profile():
    require = _require_login()
    if require:
        return require
    db = get_db_session()
    user = get_current_user(db)
    if not user:
        flash("Please log in again.", "error")
        return redirect(url_for("login"))
    form = ProfileForm(obj=user)
    if request.method == "GET":
        if user.openai_api_key:
            form.openai_api_key.data = decrypt(user.openai_api_key)
        if user.linkedin_client_secret:
            form.linkedin_client_secret.data = decrypt(user.linkedin_client_secret)
        if user.linkedin_org_urn:
            form.linkedin_org_urn.data = user.linkedin_org_urn

    if form.validate_on_submit():
        user.name = (form.name.data or "").strip()[:255]
        user.headline = (form.headline.data or "").strip()[:255]
        user.linkedin_url = (form.linkedin_url.data or "").strip()[:1000]
        user.linkedin_org_urn = (form.linkedin_org_urn.data or "").strip()[:255]
        user.timezone = form.timezone.data or "UTC"
        user.language = form.language.data or "en"
        user.email_notifications = 1 if form.email_notifications.data else 0
        user.openai_api_key = encrypt(form.openai_api_key.data or "")
        user.linkedin_client_id = (form.linkedin_client_id.data or "").strip()
        user.linkedin_client_secret = encrypt(form.linkedin_client_secret.data or "")
        try:
            db.commit()
            flash("Profile and credentials saved.", "success")
        except Exception as e:
            db.rollback()
            logger.exception("Failed to save profile")
            flash(f"Failed to save profile: {e}", "error")
        return redirect(url_for("profile"))

    return render_template("profile.html", form=form, user=user)


@app.route("/settings", methods=["GET", "POST"])
@limiter.limit("100 per hour")
def settings():
    require = _require_login()
    if require:
        return require
    db = get_db_session()
    setting = get_or_create_settings(db, current_user_id())
    form = SettingsForm(obj=setting)
    # WTForms TimeField stores a datetime.time object; convert for the HTML input HH:MM.
    if request.method == "GET" and setting.post_time:
        form.post_time.data = setting.post_time

    if form.validate_on_submit():
        setting.company_name = _safe_company_name(form.company_name.data or "")
        setting.company_context = _safe_company_context(form.company_context.data or "")
        setting.default_model = _safe_model(form.default_model.data)
        setting.default_target = _safe_target(form.default_target.data)
        setting.default_inspiration = _safe_inspiration(form.default_inspiration.data)
        setting.post_time = str(form.post_time.data)[:5]
        try:
            db.commit()
            flash("Settings saved", "success")
        except Exception as e:
            db.rollback()
            logger.exception("Failed to save settings")
            flash(f"Failed to save settings: {e}", "error")
        return redirect(url_for("settings"))

    return render_template("settings.html", form=form, settings=setting)


@app.route("/users")
@limiter.limit("100 per hour")
def users():
    require = _require_login()
    if require:
        return require
    db = get_db_session()
    user = get_current_user(db)
    if not user or not user.is_admin:
        flash("Admins only.", "error")
        return redirect(url_for("index"))
    all_users = db.query(User).order_by(User.id.desc()).all()
    return render_template("users.html", users=all_users)


@app.route("/inspiration", methods=["GET", "POST"])
@limiter.limit("100 per hour")
def inspiration_page():
    require = _require_login()
    if require:
        return require
    db = get_db_session()
    form = InspirationForm()

    if form.validate_on_submit():
        source = _safe_inspiration(form.source.data)
        manual_text = (form.manual_text.data or "").strip()
        rss_url = (form.rss_url.data or "").strip()
        linkedin_urn = (form.linkedin_urn.data or "").strip()

        if source == "manual" and not manual_text:
            flash("Paste an example post to save manual inspiration.", "error")
            return redirect(url_for("inspiration_page"))
        if source == "rss" and not rss_url:
            flash("Provide an RSS feed URL.", "error")
            return redirect(url_for("inspiration_page"))
        if source == "linkedin_api" and not linkedin_urn:
            flash("Provide a LinkedIn author URN.", "error")
            return redirect(url_for("inspiration_page"))

        user = db.query(User).filter(User.id == current_user_id()).first()
        access_token = user.access_token if user else ""

        try:
            gather_inspiration(
                db,
                current_user_id(),
                source=source,
                manual_text=manual_text,
                rss_url=rss_url,
                linkedin_access_token=access_token,
                linkedin_author_urn=linkedin_urn,
            )
            flash("Inspiration saved", "success")
        except Exception as e:
            db.rollback()
            logger.exception("Failed to gather inspiration")
            flash(f"Failed to gather inspiration: {e}", "error")
        return redirect(url_for("inspiration_page"))

    query = (
        db.query(InspirationPost)
        .filter(InspirationPost.user_id == current_user_id())
        .order_by(InspirationPost.created_at.desc())
    )
    posts, page, per_page, total = _paginate(query)
    return render_template(
        "inspiration.html",
        form=form,
        posts=posts,
        page=page,
        per_page=per_page,
        total=total,
    )


@app.route("/generate", methods=["GET", "POST"])
@limiter.limit("100 per hour")
def generate_draft():
    require = _require_login()
    if require:
        return require
    db = get_db_session()
    setting = get_or_create_settings(db, current_user_id())
    form = GenerateForm(
        model=setting.default_model,
        target=setting.default_target,
        inspiration_source=setting.default_inspiration,
    )

    if form.validate_on_submit():
        model = _safe_model(form.model.data)
        target = _safe_target(form.target.data)
        inspiration_source = _safe_inspiration(form.inspiration_source.data)
        manual_text = (form.manual_text.data or "").strip()
        rss_url = (form.rss_url.data or "").strip()
        linkedin_urn = (form.linkedin_urn.data or "").strip()

        if inspiration_source == "manual" and not manual_text:
            flash("Paste an example post to generate from manual inspiration.", "error")
            return redirect(url_for("generate_draft"))
        if inspiration_source == "rss" and not rss_url:
            flash("Provide an RSS feed URL.", "error")
            return redirect(url_for("generate_draft"))
        if inspiration_source == "linkedin_api" and not linkedin_urn:
            flash("Provide a LinkedIn author URN.", "error")
            return redirect(url_for("generate_draft"))

        user = db.query(User).filter(User.id == current_user_id()).first()
        access_token = user.access_token if user else ""

        try:
            examples = gather_inspiration(
                db,
                current_user_id(),
                source=inspiration_source,
                manual_text=manual_text,
                rss_url=rss_url,
                linkedin_access_token=access_token,
                linkedin_author_urn=linkedin_urn,
            )
        except Exception as e:
            db.rollback()
            logger.exception("Failed to gather inspiration for draft generation")
            flash(f"Failed to gather inspiration: {e}", "error")
            return redirect(url_for("generate_draft"))

        if inspiration_source in ("manual", "context"):
            stored = (
                db.query(InspirationPost)
                .filter(
                    InspirationPost.user_id == current_user_id(),
                    InspirationPost.source == "manual",
                )
                .all()
            )
            examples.extend([p.content for p in stored])

        user = db.query(User).filter(User.id == current_user_id()).first()
        try:
            content = generate_post(
                examples,
                company_name=setting.company_name,
                company_context=setting.company_context,
                model=model,
                api_key=(decrypt(user.openai_api_key) if user and user.openai_api_key else ""),
                language=setting.language if setting and setting.language else "en",
            )
        except Exception as e:
            logger.exception("Draft generation failed")
            flash(f"Failed to generate draft: {e}", "error")
            return redirect(url_for("generate_draft"))

        draft = Draft(
            user_id=current_user_id(), content=content, model=model, target=target
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return redirect(url_for("review_draft", draft_id=draft.id))

    return render_template("generate.html", form=form, settings=setting)


@app.route("/draft/<int:draft_id>")
def review_draft(draft_id: int):
    require = _require_login()
    if require:
        return require
    db = get_db_session()
    draft = (
        db.query(Draft)
        .filter(Draft.id == draft_id, Draft.user_id == current_user_id())
        .first()
    )
    if not draft:
        flash("Draft not found", "error")
        return redirect(url_for("drafts"))
    user = get_current_user(db)
    return render_template("review.html", draft=draft, user=user)


@app.route("/publish/<int:draft_id>", methods=["POST"])
@limiter.limit("30 per hour")
def publish_draft(draft_id: int):
    require = _require_login()
    if require:
        return require

    if not _csrf_valid():
        flash("Invalid or missing CSRF token", "error")
        return redirect(url_for("review_draft", draft_id=draft_id))

    db = get_db_session()
    draft = (
        db.query(Draft)
        .filter(Draft.id == draft_id, Draft.user_id == current_user_id())
        .first()
    )
    if not draft:
        flash("Draft not found", "error")
        return redirect(url_for("drafts"))

    new_content = request.form.get("content", "").strip()
    if new_content:
        draft.content = new_content[:4000]

    user = db.query(User).filter(User.id == current_user_id()).first()
    if not user or not user.access_token:
        flash("Connect LinkedIn first", "error")
        return redirect(url_for("index"))

    try:
        post_id = create_post(user, draft.content, db, target=draft.target)
        draft.status = "published"
        draft.published_at = utc_now()
        draft.linkedin_post_id = post_id
        db.commit()
        flash(f"Published successfully! Post ID: {post_id}", "success")
        logger.info(
            "User %s published draft %s as LinkedIn post %s",
            current_user_id(),
            draft.id,
            post_id,
        )
    except Exception as e:
        db.rollback()
        logger.exception("Failed to publish draft %s", draft.id)
        flash(f"Failed to publish: {e}", "error")
    return redirect(url_for("drafts"))


@app.route("/reject/<int:draft_id>", methods=["POST"])
@limiter.limit("30 per hour")
def reject_draft(draft_id: int):
    if not _csrf_valid():
        flash("Invalid or missing CSRF token", "error")
        return redirect(url_for("review_draft", draft_id=draft_id))

    require = _require_login()
    if require:
        return require

    db = get_db_session()
    draft = (
        db.query(Draft)
        .filter(Draft.id == draft_id, Draft.user_id == current_user_id())
        .first()
    )
    if not draft:
        flash("Draft not found", "error")
        return redirect(url_for("drafts"))

    draft.status = "rejected"
    db.commit()
    flash("Draft rejected.", "info")
    return redirect(url_for("drafts"))


@app.route("/delete_draft/<int:draft_id>", methods=["POST"])
@limiter.limit("30 per hour")
def delete_draft(draft_id: int):
    if not _csrf_valid():
        flash("Invalid or missing CSRF token", "error")
        return redirect(url_for("drafts"))

    require = _require_login()
    if require:
        return require

    db = get_db_session()
    draft = (
        db.query(Draft)
        .filter(Draft.id == draft_id, Draft.user_id == current_user_id())
        .first()
    )
    if not draft:
        flash("Draft not found", "error")
        return redirect(url_for("drafts"))

    db.delete(draft)
    db.commit()
    flash("Draft deleted.", "info")
    return redirect(url_for("drafts"))


@app.route("/drafts")
@limiter.limit("100 per hour")
def drafts():
    require = _require_login()
    if require:
        return require

    db = get_db_session()
    query = (
        db.query(Draft)
        .filter(Draft.user_id == current_user_id())
        .order_by(Draft.created_at.desc())
    )
    items, page, per_page, total = _paginate(query)
    user = get_current_user(db)
    return render_template(
        "drafts.html",
        drafts=items,
        page=page,
        per_page=per_page,
        total=total,
        user=user,
    )


@app.route("/scheduled")
@limiter.limit("100 per hour")
def scheduled_posts():
    require = _require_login()
    if require:
        return require

    db = get_db_session()
    query = (
        db.query(Draft)
        .filter(Draft.user_id == current_user_id())
        .order_by(Draft.created_at.desc())
    )
    drafts = query.all()
    user = get_current_user(db)
    return render_template("scheduled.html", drafts=drafts, user=user)


@app.route("/resend-code", methods=["POST"])
@limiter.limit("10 per hour")
def resend_code():
    email = flask_session.get("pending_verification_email")
    if not email:
        flash("Please register first.", "error")
        return redirect(url_for("register"))

    db = get_db_session()
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("register"))

    user.verification_code = generate_verification_code()
    user.verification_sent_at = utc_now()
    db.commit()
    send_verification_email(
        to_email=user.email,
        to_name=user.name or user.email,
        code=user.verification_code,
        subject="Verify your LinkedIn Auto-Poster account",
    )
    flash("A new verification code has been sent to your email.", "info")
    return redirect(url_for("verify"))


@app.route("/logout")
@limiter.exempt
def logout():
    flask_session.clear()
    response = redirect(url_for("login"))
    # Instruct the browser to clear stored credentials and site data on logout.
    response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    flash("You have been logged out.", "success")
    return response


@app.route("/signin", methods=["GET", "POST"])
@limiter.limit("30 per hour")
def signin():
    return login()


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def signup():
    return register()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port)

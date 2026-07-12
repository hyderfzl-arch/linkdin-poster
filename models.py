import logging

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Index,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker

import config
from utils import utc_now

logger = logging.getLogger(__name__)

engine = create_engine(config.DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)
Base = declarative_base()


def get_db_session():
    """Return a new database session. Useful for non-request contexts like the scheduler."""
    db = SessionLocal()
    return db


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    linkedin_id = Column(String(255), unique=True, nullable=True)
    email = Column(String(255), nullable=True, unique=True)
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1)
    is_admin = Column(Integer, default=0)
    is_verified = Column(Integer, default=0)
    verification_code = Column(String(8), nullable=True)
    verification_sent_at = Column(DateTime, nullable=True)
    headline = Column(String(255), nullable=True)
    avatar_url = Column(String(1000), nullable=True)
    linkedin_url = Column(String(1000), nullable=True)

    # Encrypted credentials (per-user; can override env defaults)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    openai_api_key = Column(Text, nullable=True)
    linkedin_client_id = Column(Text, nullable=True)
    linkedin_client_secret = Column(Text, nullable=True)
    linkedin_org_urn = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=utc_now)
    verified_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_linkedin_id", "linkedin_id"),
    )


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    company_name = Column(String(255), nullable=True)
    company_context = Column(Text, nullable=True)
    default_model = Column(String(50), default="gpt-4o")
    default_target = Column(String(50), default="profile")  # profile, company, choose
    default_inspiration = Column(
        String(50), default="manual"
    )  # manual, rss, linkedin_api, context
    post_time = Column(String(10), default="09:00")

    # User-level toggles
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")
    email_notifications = Column(Integer, default=1)

    __table_args__ = (Index("ix_settings_user_id", "user_id"),)


class InspirationPost(Base):
    __tablename__ = "inspiration_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source = Column(String(50), default="manual")  # manual, rss, linkedin_api, context
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    url = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        Index("ix_inspiration_user_id_created", "user_id", "created_at"),
        Index("ix_inspiration_user_id_source", "user_id", "source"),
    )


class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    model = Column(String(50), nullable=True)
    target = Column(String(50), nullable=True)
    status = Column(String(20), default="draft")  # draft, published, rejected
    created_at = Column(DateTime, default=utc_now)
    published_at = Column(DateTime, nullable=True)
    linkedin_post_id = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_drafts_user_id_created", "user_id", "created_at"),
        Index("ix_drafts_user_id_status", "user_id", "status"),
    )


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized.")
    except Exception:
        logger.exception("Failed to initialize database tables")
        raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Initial migration - full schema for Supabase Postgres

Revision ID: 6a34de6ddd0e
Revises:
Create Date: 2026-07-12 00:38:45.320126

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6a34de6ddd0e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the full schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("linkedin_id", sa.String(255), unique=True, nullable=True),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Integer(), default=1),
        sa.Column("is_admin", sa.Integer(), default=0),
        sa.Column("headline", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(1000), nullable=True),
        sa.Column("linkedin_url", sa.String(1000), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("openai_api_key", sa.Text(), nullable=True),
        sa.Column("linkedin_client_id", sa.Text(), nullable=True),
        sa.Column("linkedin_client_secret", sa.Text(), nullable=True),
        sa.Column("linkedin_org_urn", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_linkedin_id", "users", ["linkedin_id"], unique=False)

    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("company_context", sa.Text(), nullable=True),
        sa.Column("default_model", sa.String(50), default="gpt-4o"),
        sa.Column("default_target", sa.String(50), default="profile"),
        sa.Column("default_inspiration", sa.String(50), default="manual"),
        sa.Column("post_time", sa.String(10), default="09:00"),
        sa.Column("timezone", sa.String(50), default="UTC"),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("email_notifications", sa.Integer(), default=1),
    )
    op.create_index("ix_settings_user_id", "settings", ["user_id"], unique=False)

    op.create_table(
        "inspiration_posts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(50), default="manual"),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )
    op.create_index("ix_inspiration_user_id_created", "inspiration_posts", ["user_id", "created_at"], unique=False)
    op.create_index("ix_inspiration_user_id_source", "inspiration_posts", ["user_id", "source"], unique=False)

    op.create_table(
        "drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(50), nullable=True),
        sa.Column("target", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), default="draft"),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("linkedin_post_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_drafts_user_id_created", "drafts", ["user_id", "created_at"], unique=False)
    op.create_index("ix_drafts_user_id_status", "drafts", ["user_id", "status"], unique=False)


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("drafts")
    op.drop_table("inspiration_posts")
    op.drop_table("settings")
    op.drop_table("users")

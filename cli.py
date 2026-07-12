"""Operational CLI for the LinkedIn Auto-Poster."""

import argparse
import getpass
import logging
import re
import sys

from werkzeug.security import generate_password_hash

import config
from models import SessionLocal, User, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _create_admin(db, email: str, password: str) -> User:
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address.")
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long.")

    user = db.query(User).filter(User.email == email).first()
    password_hash = generate_password_hash(password)
    if user:
        user.is_admin = 1
        user.is_verified = 1
        user.is_active = 1
        user.password_hash = password_hash
        db.commit()
        logger.info("Updated existing user as admin: %s", email)
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
    logger.info("Created admin user: %s", email)
    return user


def cmd_create_admin(args: argparse.Namespace) -> int:
    email = args.email or input("Admin email: ").strip()
    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            logger.error("Passwords do not match.")
            return 1

    db = SessionLocal()
    try:
        init_db()
        _create_admin(db, email, password)
        return 0
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create admin: %s", exc)
        return 1
    finally:
        db.close()


def cmd_run_scheduler(args: argparse.Namespace) -> int:
    from scheduler import run_daily_post, start_scheduler

    scheduler = start_scheduler()
    try:
        if args.now:
            run_daily_post()
        while True:
            import time

            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")
    finally:
        from scheduler import shutdown_scheduler

        shutdown_scheduler(scheduler)
    return 0


def cmd_run_server(args: argparse.Namespace) -> int:
    from app import app

    host = args.host or config.ENVIRONMENT == "development" and "127.0.0.1" or "0.0.0.0"
    port = args.port
    app.run(host=host, port=port, debug=args.debug)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LinkedIn Auto-Poster CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    admin_parser = subparsers.add_parser(
        "create-admin", help="Create or update the initial admin user"
    )
    admin_parser.add_argument("--email", help="Admin email address")
    admin_parser.add_argument("--password", help="Admin password (use prompt in production)")
    admin_parser.set_defaults(func=cmd_create_admin)

    scheduler_parser = subparsers.add_parser(
        "run-scheduler", help="Start the background daily-post scheduler"
    )
    scheduler_parser.add_argument(
        "--now", action="store_true", help="Run one cycle immediately on startup"
    )
    scheduler_parser.set_defaults(func=cmd_run_scheduler)

    server_parser = subparsers.add_parser(
        "run-server", help="Run the Flask development server"
    )
    server_parser.add_argument("--host", default="", help="Bind host")
    server_parser.add_argument("--port", type=int, default=5000, help="Bind port")
    server_parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    server_parser.set_defaults(func=cmd_run_server)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

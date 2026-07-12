import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

import config
from content_generator import generate_post
from inspiration import gather_inspiration
from linkedin_poster import create_post
from models import Draft, Setting, User, get_db_session
from utils import utc_now

logger = logging.getLogger(__name__)

scheduled_times = []


def run_daily_post():
    """Generate and publish one post for each user with valid settings and tokens."""
    db: Session = get_db_session()
    try:
        now = utc_now()
        logger.info("Running daily scheduled post job at %s", now)

        users = db.query(User).filter(User.access_token.isnot(None)).all()
        for user in users:
            try:
                setting = db.query(Setting).filter(Setting.user_id == user.id).first()
                company_name = setting.company_name if setting else config.COMPANY_NAME
                company_context = (
                    setting.company_context if setting else config.COMPANY_CONTEXT
                )
                target = setting.default_target if setting else "profile"
                model = setting.default_model if setting else "gpt-4o"
                inspiration_source = (
                    setting.default_inspiration if setting else "context"
                )

                examples = gather_inspiration(
                    db,
                    user.id,
                    source=inspiration_source,
                )
                post_text = generate_post(
                    examples,
                    company_name=company_name,
                    company_context=company_context,
                    model=model,
                )
                post_id = create_post(user, post_text, db, target=target)
                draft = Draft(
                    user_id=user.id,
                    content=post_text,
                    model=model,
                    target=target,
                    status="published",
                    published_at=utc_now(),
                    linkedin_post_id=post_id,
                )
                db.add(draft)
                db.commit()
                logger.info(
                    "Scheduled post published for user %s: %s", user.id, post_id
                )
                scheduled_times.append(dt.datetime.now(dt.timezone.utc))
            except Exception:
                db.rollback()
                logger.exception("Failed scheduled post for user %s", user.id)
    finally:
        db.close()


def parse_post_time():
    parts = config.POST_TIME.split(":")
    return int(parts[0]), int(parts[1])


def start_scheduler():
    hour, minute = parse_post_time()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_post, "cron", hour=hour, minute=minute)
    scheduler.start()
    logger.info("Scheduler started. Next post at %02d:%02d daily.", hour, minute)
    return scheduler


def shutdown_scheduler(scheduler: BackgroundScheduler):
    scheduler.shutdown(wait=False)

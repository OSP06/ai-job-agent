"""
followup_scheduler.py
─────────────────────
APScheduler-based daily follow-up engine.

Schedule:
  Day 0  → Job captured + initial outreach stored
  Day 7  → Follow-up #1 message generated and stored
  Day 14 → Follow-up #2 / final message generated and stored
  Day 14 → Application status → "no_response"

Follow-up messages are stored in the followups table.
Users can view them via GET /api/applications/{id}.
"""

import json

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.agents.outreach_generator import generate_followup
from backend.config import settings
from backend.models.job_model import JobData
from backend.storage.database import (
    SessionLocal,
    create_followup,
    get_application,
    get_applications_due_followup,
    update_application_status,
)
from backend.utils.logger import logger

_scheduler: BackgroundScheduler | None = None


# ─── Core follow-up logic ────────────────────────────────────────────────────

def _process_followup_for_application(application_id: int, followup_number: int) -> None:
    """Generate and store a follow-up message for a single application."""
    db = SessionLocal()
    try:
        app = get_application(db, application_id)
        if not app:
            logger.warning(f"Application {application_id} not found during follow-up check")
            return

        requirements = json.loads(app.requirements_json or "[]")
        job = JobData(
            title=app.job_title,
            company=app.company,
            description=app.description or "",
            requirements=requirements,
            location=app.location,
        )

        original_subject = f"Re: {app.job_title} at {app.company}"
        contact_name: str | None = None
        outreach_id: int | None = None

        if app.outreach_messages:
            first = app.outreach_messages[0]
            original_subject = first.message_subject or original_subject
            contact_name = first.contact_name
            outreach_id = first.id

        followup_msg = generate_followup(
            job=job,
            original_subject=original_subject,
            followup_number=followup_number,
            contact_name=contact_name,
        )

        if outreach_id:
            create_followup(
                db=db,
                outreach_id=outreach_id,
                application_id=application_id,
                message_body=followup_msg.body,
                followup_number=followup_number,
            )
            logger.info(f"Follow-up {followup_number} stored for application {application_id}")

        if followup_number == 2:
            update_application_status(db, application_id, "no_response")
            logger.info(
                f"Application {application_id} ({app.job_title} @ {app.company}) "
                f"marked as no_response after final follow-up"
            )

    except Exception as e:
        logger.error(f"Error processing follow-up for application {application_id}: {e}")
    finally:
        db.close()


def check_day7_followups() -> None:
    logger.info("Running Day-7 follow-up check...")
    db = SessionLocal()
    try:
        apps = get_applications_due_followup(db, followup_number=1)
        app_ids = [a.id for a in apps]
        logger.info(f"Found {len(app_ids)} application(s) due for Day-7 follow-up")
    finally:
        db.close()
    for app_id in app_ids:
        _process_followup_for_application(app_id, followup_number=1)


def check_day14_followups() -> None:
    logger.info("Running Day-14 (final) follow-up check...")
    db = SessionLocal()
    try:
        apps = get_applications_due_followup(db, followup_number=2)
        app_ids = [a.id for a in apps]
        logger.info(f"Found {len(app_ids)} application(s) due for Day-14 follow-up")
    finally:
        db.close()
    for app_id in app_ids:
        _process_followup_for_application(app_id, followup_number=2)


# ─── Scheduler lifecycle ─────────────────────────────────────────────────────

def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    tz = settings.scheduler_timezone
    _scheduler = BackgroundScheduler(timezone=tz)

    _scheduler.add_job(
        check_day7_followups,
        trigger=CronTrigger(hour=9, minute=0),
        id="day7_followup",
        replace_existing=True,
        name="Day-7 follow-up check",
    )
    _scheduler.add_job(
        check_day14_followups,
        trigger=CronTrigger(hour=9, minute=5),
        id="day14_followup",
        replace_existing=True,
        name="Day-14 final follow-up check",
    )

    _scheduler.start()
    logger.info(f"Follow-up scheduler started (tz={tz}, Day-7 @ 09:00, Day-14 @ 09:05)")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Follow-up scheduler stopped")

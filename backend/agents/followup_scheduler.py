"""
followup_scheduler.py
─────────────────────
APScheduler-based daily follow-up engine.

Schedule:
  Day 0  → Apply + initial outreach created
  Day 7  → Follow-up #1 (Gmail draft created)
  Day 14 → Follow-up #2 / final (Gmail draft created)
  Day 14 → After final follow-up, application status → "no_response"

The scheduler runs two jobs:
  1. check_day7_followups  — fired daily at 09:00
  2. check_day14_followups — fired daily at 09:05
"""

from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.agents.outreach_generator import generate_followup
from backend.models.job_model import JobData
from backend.services.email_service import create_gmail_draft
from backend.storage.database import (
    SessionLocal,
    create_followup,
    get_applications_due_followup,
    get_application,
    update_application_status,
)
from backend.utils.logger import logger

_scheduler: BackgroundScheduler | None = None


# ─── Core follow-up logic ────────────────────────────────────────────────────

def _process_followup_for_application(application_id: int, followup_number: int) -> None:
    """Generate a follow-up draft for a single application."""
    db = SessionLocal()
    try:
        app = get_application(db, application_id)
        if not app:
            logger.warning(f"Application {application_id} not found during follow-up check")
            return

        # Reconstruct minimal JobData for the generator
        import json
        requirements = json.loads(app.requirements_json or "[]")
        job = JobData(
            title=app.job_title,
            company=app.company,
            description=app.description or "",
            requirements=requirements,
            location=app.location,
        )

        # Get original outreach subject (use first outreach record if available)
        original_subject = f"Re: {app.job_title} at {app.company}"
        contact_name: str | None = None
        outreach_id: int | None = None

        if app.outreach_messages:
            first_outreach = app.outreach_messages[0]
            original_subject = first_outreach.message_subject or original_subject
            contact_name = first_outreach.contact_name
            outreach_id = first_outreach.id

        # Generate follow-up message via Claude
        followup_msg = generate_followup(
            job=job,
            original_subject=original_subject,
            followup_number=followup_number,
            contact_name=contact_name,
        )

        # Create Gmail draft
        gmail_draft_id: str | None = None
        if app.outreach_messages and app.outreach_messages[0].contact_email:
            to_email = app.outreach_messages[0].contact_email
            gmail_draft_id = create_gmail_draft(
                to=to_email,
                subject=followup_msg.subject,
                body=followup_msg.body,
            )

        # Store follow-up record
        if outreach_id:
            fu = create_followup(
                db=db,
                outreach_id=outreach_id,
                application_id=application_id,
                message_body=followup_msg.body,
                followup_number=followup_number,
                gmail_draft_id=gmail_draft_id,
            )
            logger.info(
                f"Follow-up {followup_number} created for app {application_id} "
                f"(draft_id={gmail_draft_id})"
            )

        # After Day-14 follow-up, mark application as no_response
        if followup_number == 2:
            update_application_status(db, application_id, "no_response")
            logger.info(
                f"Application {application_id} ({app.job_title} @ {app.company}) "
                f"marked as no_response after final follow-up"
            )

    except Exception as e:
        logger.error(f"Error processing follow-up for app {application_id}: {e}")
    finally:
        db.close()


def check_day7_followups() -> None:
    """Scheduled job: fire Day-7 follow-ups for all due applications."""
    logger.info("Running Day-7 follow-up check...")
    db = SessionLocal()
    try:
        apps = get_applications_due_followup(db, followup_number=1)
        logger.info(f"Found {len(apps)} application(s) due for Day-7 follow-up")
        app_ids = [a.id for a in apps]
    finally:
        db.close()

    for app_id in app_ids:
        _process_followup_for_application(app_id, followup_number=1)


def check_day14_followups() -> None:
    """Scheduled job: fire Day-14 final follow-ups for all due applications."""
    logger.info("Running Day-14 (final) follow-up check...")
    db = SessionLocal()
    try:
        apps = get_applications_due_followup(db, followup_number=2)
        logger.info(f"Found {len(apps)} application(s) due for Day-14 follow-up")
        app_ids = [a.id for a in apps]
    finally:
        db.close()

    for app_id in app_ids:
        _process_followup_for_application(app_id, followup_number=2)


# ─── Scheduler lifecycle ─────────────────────────────────────────────────────

def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="America/New_York")

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
    logger.info("Follow-up scheduler started (Day-7 @ 09:00, Day-14 @ 09:05)")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Follow-up scheduler stopped")

"""
main.py — AI Job Application Agent API
────────────────────────────────────────
Endpoints:
  POST /api/jobs/process              Full pipeline: parse → match → outreach → store
  GET  /api/applications              List all applications (optional ?status= filter)
  GET  /api/applications/{id}         Single application detail
  PATCH /api/applications/{id}/status Update application status
  POST /api/applications/{id}/apply   Mark as applied (sets follow-up dates)
  GET  /api/followups/pending         List applications due for follow-up
  POST /api/followups/{id}/process    Manually trigger follow-up generation
  GET  /api/export/csv                Download all applications as CSV
"""

import csv
import io
import json
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from sqlalchemy.orm import Session

from backend.agents.followup_scheduler import start_scheduler, stop_scheduler
from backend.agents.job_parser import parse_job
from backend.agents.outreach_generator import generate_followup, generate_outreach
from backend.agents.recruiter_finder import find_contacts
from backend.agents.resume_matcher import match_resume
from backend.config import settings
from backend.models.job_model import JobInput, ProcessJobResponse
from backend.services.email_service import create_gmail_draft
from backend.services.notion_service import sync_to_notion
from backend.storage.database import (
    Application,
    create_application,
    create_contact,
    create_followup,
    create_outreach,
    get_application,
    get_application_by_url,
    get_applications,
    get_applications_due_followup,
    init_db,
    mark_applied,
    update_application_status,
    get_db,
)
from backend.utils.logger import logger


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Job Agent backend...")
    init_db()
    scheduler = start_scheduler()
    yield
    stop_scheduler()
    logger.info("Backend shutdown complete.")


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Job Application Agent",
    description="Local AI agent that captures jobs, matches resumes, generates outreach, and tracks follow-ups.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome extension origin
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ─── POST /api/jobs/process ───────────────────────────────────────────────────

@app.post("/api/jobs/process", response_model=ProcessJobResponse, tags=["Pipeline"])
async def process_job(job_input: JobInput, db: Session = Depends(get_db)):
    """
    Full pipeline triggered by the Chrome extension:
    1. Parse job with GPT-4o
    2. Match resume (sentence-transformers)
    3. Confidence gate: skip outreach if match_score < threshold
    4. Generate outreach with Claude Sonnet (if above threshold)
    5. Look up recruiter via Hunter.io (optional)
    6. Create Gmail draft (optional)
    7. Store in SQLite
    8. Sync to Notion (optional)
    """
    logger.info(f"Processing job from: {job_input.url}")

    # Duplicate check
    existing = get_application_by_url(db, job_input.url)
    if existing:
        raise HTTPException(status_code=409, detail=f"duplicate:{existing.id}")

    # Step 1 — Parse
    job = await parse_job(job_input)

    # Step 2 — Match resume
    resume_match = match_resume(job, db=db)
    if not resume_match:
        raise HTTPException(
            status_code=422,
            detail="No resumes found. Add PDF files to backend/resumes/ and restart.",
        )

    # Step 3 — Confidence gate + outreach generation
    score = resume_match.score
    try:
        outreach_msg, skip_reason = generate_outreach(job, resume_match)
    except Exception as e:
        logger.error(f"Outreach generation failed: {e}")
        outreach_msg, skip_reason = None, f"Outreach generation error: {e}"

    # Step 4 — Contact discovery (Hunter.io: LinkedIn name + HR dept + management)
    contacts: list[dict] = []
    if job.company_domain:
        contacts = await find_contacts(
            company_domain=job.company_domain,
            linkedin_name=job_input.linkedin_recruiter_name,
        )

    # Step 5 — Store application
    app_record = create_application(
        db=db,
        job_title=job.title,
        company=job.company,
        url=job_input.url,
        description=job.description,
        requirements=job.requirements,
        resume_used=resume_match.resume_name,
        match_score=score,
        location=job.location,
        salary=job.salary,
        job_type=job.job_type,
        status="captured",
        missing_skills=resume_match.missing_skills,
    )

    # Step 6 — Store all contacts found
    for c in contacts:
        create_contact(
            db=db,
            application_id=app_record.id,
            name=c.get("name"),
            email=c.get("email"),
            title=c.get("title"),
            linkedin_url=c.get("linkedin_url"),
        )

    # Step 7 — Create outreach record + Gmail draft to best verified contact
    gmail_draft_id: str | None = None
    best_contact = contacts[0] if contacts else None
    if outreach_msg:
        contact_email = best_contact.get("email") if best_contact else None
        contact_name  = best_contact.get("name")  if best_contact else None

        if contact_email:
            gmail_draft_id = create_gmail_draft(
                to=contact_email,
                subject=outreach_msg.subject,
                body=outreach_msg.body,
            )

        create_outreach(
            db=db,
            application_id=app_record.id,
            message_subject=outreach_msg.subject,
            message_body=outreach_msg.body,
            contact_name=contact_name,
            contact_email=contact_email,
            gmail_draft_id=gmail_draft_id,
        )

    # Step 8 — Notion sync (optional)
    await sync_to_notion(
        job_title=job.title,
        company=job.company,
        url=job_input.url,
        status="captured",
        match_score=score,
        resume_used=resume_match.resume_name,
        location=job.location,
    )

    logger.info(
        f"Job processed: {job.title} @ {job.company} | "
        f"score={score:.0%} | outreach={'yes' if outreach_msg else 'skipped'}"
    )

    return ProcessJobResponse(
        application_id=app_record.id,
        job_title=job.title,
        company=job.company,
        match_score=score,
        resume_used=resume_match.resume_name,
        all_resume_scores=resume_match.all_scores,
        matched_skills=resume_match.matched_skills,
        missing_skills=resume_match.missing_skills,
        contacts_found=[
            {"name": c.get("name"), "email": c.get("email"),
             "title": c.get("title"), "verified": c.get("verified", False),
             "source": c.get("source"), "linkedin_url": c.get("linkedin_url")}
            for c in contacts
        ],
        outreach_generated=outreach_msg is not None,
        outreach_skipped_reason=skip_reason,
        outreach_subject=outreach_msg.subject if outreach_msg else None,
        outreach_body=outreach_msg.body if outreach_msg else None,
        gmail_draft_id=gmail_draft_id,
        message=(
            f"Application captured. Match score: {score:.0%}. "
            + ("Outreach draft created." if outreach_msg else f"Outreach skipped: {skip_reason}")
        ),
    )


# ─── GET /api/applications ────────────────────────────────────────────────────

@app.get("/api/applications", tags=["Applications"])
def list_applications(
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
):
    apps = get_applications(db, status=status)
    return [_serialize_application(a) for a in apps]


# ─── GET /api/applications/{id} ───────────────────────────────────────────────

@app.get("/api/applications/{application_id}", tags=["Applications"])
def get_application_detail(application_id: int, db: Session = Depends(get_db)):
    app = get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    result = _serialize_application(app)
    result["outreach"] = [
        {
            "id": o.id,
            "subject": o.message_subject,
            "body": o.message_body,
            "status": o.status,
            "gmail_draft_id": o.gmail_draft_id,
            "contact_name": o.contact_name,
            "contact_email": o.contact_email,
            "followups": [
                {
                    "id": f.id,
                    "followup_number": f.followup_number,
                    "body": f.message_body,
                    "status": f.status,
                    "gmail_draft_id": f.gmail_draft_id,
                }
                for f in o.followups
            ],
        }
        for o in app.outreach_messages
    ]
    result["contacts"] = [
        {"id": c.id, "name": c.name, "email": c.email, "title": c.title}
        for c in app.contacts
    ]
    return result


# ─── PATCH /api/applications/{id}/status ─────────────────────────────────────

@app.patch("/api/applications/{application_id}/status", tags=["Applications"])
def update_status(
    application_id: int,
    status: str = Query(..., description="New status: applied|interviewing|rejected|offer|no_response"),
    db: Session = Depends(get_db),
):
    valid_statuses = {"captured", "applied", "interviewing", "rejected", "offer", "no_response"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {valid_statuses}")
    app = update_application_status(db, application_id, status)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"id": application_id, "status": app.status}


# ─── POST /api/applications/{id}/apply ───────────────────────────────────────

@app.post("/api/applications/{application_id}/apply", tags=["Applications"])
def mark_as_applied(application_id: int, db: Session = Depends(get_db)):
    """
    Mark application as 'applied' and set Day-7 / Day-14 follow-up dates.
    """
    app = mark_applied(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        "id": application_id,
        "status": "applied",
        "applied_date": str(app.applied_date),
        "follow_up_due_1": str(app.follow_up_due_1),
        "follow_up_due_2": str(app.follow_up_due_2),
    }


# ─── GET /api/followups/pending ───────────────────────────────────────────────

@app.get("/api/followups/pending", tags=["Follow-ups"])
def list_pending_followups(db: Session = Depends(get_db)):
    """List all applications with overdue follow-ups."""
    day7 = get_applications_due_followup(db, followup_number=1)
    day14 = get_applications_due_followup(db, followup_number=2)
    return {
        "day7_due": [_serialize_application(a) for a in day7],
        "day14_due": [_serialize_application(a) for a in day14],
        "total": len(day7) + len(day14),
    }


# ─── POST /api/followups/{id}/process ────────────────────────────────────────

@app.post("/api/followups/{application_id}/process", tags=["Follow-ups"])
async def process_followup(
    application_id: int,
    followup_number: int = Query(1, description="1 = Day-7, 2 = Day-14"),
    db: Session = Depends(get_db),
):
    """Manually trigger follow-up generation for a specific application."""
    app = get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    requirements = json.loads(app.requirements_json or "[]")
    from backend.models.job_model import JobData
    job = JobData(
        title=app.job_title,
        company=app.company,
        description=app.description or "",
        requirements=requirements,
        location=app.location,
    )

    original_subject = f"Re: {app.job_title} at {app.company}"
    contact_name: str | None = None
    contact_email: str | None = None
    outreach_id: int | None = None

    if app.outreach_messages:
        first = app.outreach_messages[0]
        original_subject = first.message_subject or original_subject
        contact_name = first.contact_name
        contact_email = first.contact_email
        outreach_id = first.id

    followup_msg = generate_followup(
        job=job,
        original_subject=original_subject,
        followup_number=followup_number,
        contact_name=contact_name,
    )

    gmail_draft_id: str | None = None
    if contact_email:
        gmail_draft_id = create_gmail_draft(
            to=contact_email,
            subject=followup_msg.subject,
            body=followup_msg.body,
        )

    if outreach_id:
        fu = create_followup(
            db=db,
            outreach_id=outreach_id,
            application_id=application_id,
            message_body=followup_msg.body,
            followup_number=followup_number,
            gmail_draft_id=gmail_draft_id,
        )

    if followup_number == 2:
        update_application_status(db, application_id, "no_response")

    return {
        "application_id": application_id,
        "followup_number": followup_number,
        "subject": followup_msg.subject,
        "body": followup_msg.body,
        "gmail_draft_id": gmail_draft_id,
        "status": "no_response" if followup_number == 2 else "applied",
    }


# ─── GET /api/export/csv ──────────────────────────────────────────────────────

@app.get("/api/export/csv", tags=["Export"])
def export_csv(db: Session = Depends(get_db)):
    """Stream all applications as a CSV download."""
    apps = get_applications(db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "job_title", "company", "url", "location", "salary", "job_type",
        "match_score", "resume_used", "status", "applied_date",
        "follow_up_due_1", "follow_up_due_2", "created_at",
    ])
    for a in apps:
        writer.writerow([
            a.id, a.job_title, a.company, a.url, a.location, a.salary, a.job_type,
            f"{a.match_score:.2f}" if a.match_score else "",
            a.resume_used, a.status, a.applied_date,
            a.follow_up_due_1, a.follow_up_due_2, a.created_at,
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


# ─── POST /api/resumes/upload ────────────────────────────────────────────────

@app.post("/api/resumes/upload", tags=["Resumes"])
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload a PDF resume. Text and embedding are stored in the database so they
    survive across server restarts (no persistent filesystem required).
    """
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    from backend.agents.resume_matcher import ingest_pdf
    contents = await file.read()
    try:
        record = ingest_pdf(contents, file.filename, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"filename": file.filename, "resume_name": record.name, "size_bytes": len(contents)}


# ─── GET /api/resumes ─────────────────────────────────────────────────────────

@app.get("/api/resumes", tags=["Resumes"])
def list_resumes(db: Session = Depends(get_db)):
    """List all uploaded resumes."""
    from backend.storage.database import get_all_resumes
    rows = get_all_resumes(db)
    return {"resumes": [r.name for r in rows], "count": len(rows)}


# ─── GET /api/resumes/gaps ────────────────────────────────────────────────────

@app.get("/api/resumes/gaps", tags=["Resumes"])
def resume_gaps(db: Session = Depends(get_db)):
    """Aggregate missing skills across all processed jobs, sorted by frequency."""
    from collections import Counter
    apps = get_applications(db)
    counter: Counter = Counter()
    for a in apps:
        skills = json.loads(a.missing_skills_json or "[]")
        counter.update(skills)
    return {
        "total_jobs": len(apps),
        "gaps": [{"skill": s, "count": c} for s, c in counter.most_common(20)],
    }


# ─── GET /dashboard ───────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Application dashboard rendered from backend/templates/dashboard.html."""
    apps = get_applications(db)

    STATUS_COLORS = {
        "captured":     "#8888aa",
        "applied":      "#5b8dee",
        "interviewing": "#f59e0b",
        "offer":        "#22c55e",
        "rejected":     "#ef4444",
        "no_response":  "#44445a",
    }

    def score_class(s):
        if s is None: return "score-none"
        if s >= 0.70: return "score-high"
        if s >= 0.50: return "score-mid"
        return "score-low"

    stats = {s: 0 for s in STATUS_COLORS}
    for a in apps:
        stats[a.status] = stats.get(a.status, 0) + 1

    app_rows = [
        {
            "id":           a.id,
            "company":      a.company,
            "job_title":    a.job_title,
            "url":          a.url,
            "score_display": f"{a.match_score:.0%}" if a.match_score else "—",
            "score_class":  score_class(a.match_score),
            "resume_used":  a.resume_used,
            "status":       a.status,
            "applied_date": str(a.applied_date) if a.applied_date else "—",
            "created_date": str(a.created_at)[:10] if a.created_at else "—",
        }
        for a in apps
    ]

    return templates.TemplateResponse("dashboard.html", {
        "request":       request,
        "apps":          app_rows,
        "total":         len(apps),
        "stats":         stats,
        "status_colors": STATUS_COLORS,
        "statuses":      list(STATUS_COLORS.keys()),
    })


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "threshold": settings.match_score_threshold}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _serialize_application(a: Application) -> dict:
    return {
        "id": a.id,
        "job_title": a.job_title,
        "company": a.company,
        "url": a.url,
        "location": a.location,
        "salary": a.salary,
        "job_type": a.job_type,
        "match_score": a.match_score,
        "resume_used": a.resume_used,
        "status": a.status,
        "applied_date": str(a.applied_date) if a.applied_date else None,
        "follow_up_due_1": str(a.follow_up_due_1) if a.follow_up_due_1 else None,
        "follow_up_due_2": str(a.follow_up_due_2) if a.follow_up_due_2 else None,
        "created_at": str(a.created_at),
    }

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
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from backend.agents.followup_scheduler import start_scheduler, stop_scheduler
from backend.agents.job_parser import parse_job
from backend.agents.outreach_generator import generate_followup, generate_outreach
from backend.agents.recruiter_finder import find_contacts
from backend.agents.resume_matcher import match_resume
from backend.config import settings
from backend.models.job_model import JobInput, ProcessJobResponse
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Auth ─────────────────────────────────────────────────────────────────────

async def _require_api_key(x_api_key: str = Header(default="")) -> None:
    """If API_KEY is configured, all write endpoints must supply it via X-Api-Key header."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


_AUTH = [Depends(_require_api_key)]

# ─── POST /api/jobs/process ───────────────────────────────────────────────────

@app.post("/api/jobs/process", response_model=ProcessJobResponse, tags=["Pipeline"],
          dependencies=_AUTH)
async def process_job(job_input: JobInput, db: Session = Depends(get_db)):
    """
    Full pipeline triggered by the Chrome extension:
    1. Parse job (Groq / OpenAI)
    2. Match resume (embeddings + keyword overlap)
    3. Confidence gate → outreach generation
    4. Contact discovery via Hunter.io (optional)
    5. Store application, contacts, and outreach message
    """
    # Normalise URL before dedup check (case + trailing slash)
    url = job_input.url.strip().rstrip("/")

    logger.info(f"Processing job from: {url}")

    existing = get_application_by_url(db, url)
    if existing:
        raise HTTPException(status_code=409, detail=f"duplicate:{existing.id}")

    # Step 1 — Parse
    job = await parse_job(job_input)

    # Step 2 — Match resume
    resume_match = match_resume(job, db=db)
    if not resume_match:
        raise HTTPException(
            status_code=422,
            detail="No resumes found. Upload a PDF via /api/resumes/upload.",
        )

    # Step 3 — Confidence gate + outreach generation
    score = resume_match.score
    try:
        outreach_msg, skip_reason = generate_outreach(job, resume_match)
    except Exception as e:
        logger.error(f"Outreach generation failed: {e}")
        outreach_msg, skip_reason = None, f"Outreach error: {e}"

    # Step 4 — Contact discovery (Hunter.io: LinkedIn name → HR → management)
    contacts: list[dict] = []
    if job.company_domain:
        try:
            contacts = await find_contacts(
                company_domain=job.company_domain,
                linkedin_name=job_input.linkedin_recruiter_name,
            )
        except Exception as e:
            logger.warning(f"Contact discovery failed for {job.company_domain}: {e}")

    # Step 5 — Store application
    app_record = create_application(
        db=db,
        job_title=job.title,
        company=job.company,
        url=url,
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

    for c in contacts:
        create_contact(
            db=db,
            application_id=app_record.id,
            name=c.get("name"),
            email=c.get("email"),
            title=c.get("title"),
            linkedin_url=c.get("linkedin_url"),
        )

    best_contact = contacts[0] if contacts else None
    if outreach_msg:
        create_outreach(
            db=db,
            application_id=app_record.id,
            message_subject=outreach_msg.subject,
            message_body=outreach_msg.body,
            contact_name=best_contact.get("name")  if best_contact else None,
            contact_email=best_contact.get("email") if best_contact else None,
        )

    logger.info(
        f"Captured: {job.title} @ {job.company} | "
        f"score={score:.0%} | outreach={'yes' if outreach_msg else 'skipped'} | "
        f"contacts={len(contacts)}"
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
            {
                "name": c.get("name"), "email": c.get("email"),
                "title": c.get("title"), "verified": c.get("verified", False),
                "source": c.get("source"), "linkedin_url": c.get("linkedin_url"),
            }
            for c in contacts
        ],
        outreach_generated=outreach_msg is not None,
        outreach_skipped_reason=skip_reason,
        outreach_subject=outreach_msg.subject if outreach_msg else None,
        outreach_body=outreach_msg.body    if outreach_msg else None,
        message=(
            f"Captured. Match: {score:.0%}. "
            + ("Outreach ready." if outreach_msg else f"Outreach skipped: {skip_reason}")
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
            "contact_name": o.contact_name,
            "contact_email": o.contact_email,
            "followups": [
                {
                    "id": f.id,
                    "followup_number": f.followup_number,
                    "body": f.message_body,
                    "status": f.status,
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

@app.patch("/api/applications/{application_id}/status", tags=["Applications"],
           dependencies=_AUTH)
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

@app.post("/api/applications/{application_id}/apply", tags=["Applications"],
          dependencies=_AUTH)
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

@app.post("/api/followups/{application_id}/process", tags=["Follow-ups"],
          dependencies=_AUTH)
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

    if outreach_id:
        create_followup(
            db=db,
            outreach_id=outreach_id,
            application_id=application_id,
            message_body=followup_msg.body,
            followup_number=followup_number,
        )

    if followup_number == 2:
        update_application_status(db, application_id, "no_response")

    return {
        "application_id": application_id,
        "followup_number": followup_number,
        "subject": followup_msg.subject,
        "body": followup_msg.body,
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

@app.post("/api/resumes/upload", tags=["Resumes"], dependencies=_AUTH)
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


# ─── Dashboard HTML (self-contained, no Jinja2 dependency) ───────────────────

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>AI Job Agent — Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root{--accent:#6366f1;--accent-lt:#818cf8;--green:#10b981;--amber:#f59e0b;--red:#ef4444;--text-1:#f1f5f9;--text-2:#94a3b8;--text-3:#475569;--s1:rgba(255,255,255,0.07);--s2:rgba(255,255,255,0.04);--bdr:rgba(255,255,255,0.09);--bdr-h:rgba(255,255,255,0.16);--ease:cubic-bezier(0.4,0,0.2,1)}
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:linear-gradient(160deg,#0e0e20 0%,#080812 100%);color:var(--text-1);min-height:100vh;padding:32px 24px 48px;-webkit-font-smoothing:antialiased}
    .page{max-width:1060px;margin:0 auto}
    .header{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;flex-wrap:wrap;gap:14px}
    .header-left{display:flex;align-items:center;gap:12px}
    .header-icon{width:40px;height:40px;border-radius:11px;background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);display:flex;align-items:center;justify-content:center;box-shadow:0 4px 18px rgba(99,102,241,0.5),inset 0 1px 0 rgba(255,255,255,0.2);flex-shrink:0}
    .header-icon svg{width:20px;height:20px}
    .header-title{font-size:20px;font-weight:800;letter-spacing:-0.03em}
    .header-sub{font-size:12px;color:var(--text-3);margin-top:2px}
    .actions{display:flex;gap:8px;flex-wrap:wrap}
    .btn{display:inline-flex;align-items:center;gap:6px;background:var(--s1);border:1px solid var(--bdr);color:var(--text-2);padding:7px 14px;border-radius:8px;font-size:12px;font-weight:500;font-family:inherit;cursor:pointer;text-decoration:none;transition:all 0.15s var(--ease)}
    .btn:hover{background:rgba(255,255,255,0.1);border-color:var(--bdr-h);color:var(--text-1)}
    .btn-primary{background:linear-gradient(135deg,#4f46e5,#6366f1);border-color:transparent;color:#fff;font-weight:600;box-shadow:0 2px 12px rgba(99,102,241,0.4)}
    .btn-primary:hover{box-shadow:0 4px 18px rgba(99,102,241,0.55);color:#fff}
    .stats-strip{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
    .stat-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:11.5px;font-weight:600;border:1px solid transparent;cursor:pointer;transition:all 0.15s var(--ease);background:none;font-family:inherit}
    .stat-chip:hover{filter:brightness(1.15)}
    .stat-chip.active{box-shadow:0 0 0 2px currentColor}
    .chip-all{background:var(--s1);color:var(--text-2);border-color:var(--bdr)}
    .chip-captured{background:rgba(99,102,241,0.14);color:#818cf8;border-color:rgba(99,102,241,0.28)}
    .chip-applied{background:rgba(99,102,241,0.2);color:#a5b4fc;border-color:rgba(99,102,241,0.36)}
    .chip-interviewing{background:rgba(245,158,11,0.15);color:#fcd34d;border-color:rgba(245,158,11,0.3)}
    .chip-offer{background:rgba(16,185,129,0.15);color:#34d399;border-color:rgba(16,185,129,0.3)}
    .chip-rejected{background:rgba(239,68,68,0.13);color:#fca5a5;border-color:rgba(239,68,68,0.28)}
    .chip-no_response{background:rgba(71,85,105,0.25);color:#64748b;border-color:rgba(71,85,105,0.4)}
    .stat-dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0}
    .table-card{background:var(--s1);border:1px solid var(--bdr);border-radius:14px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.4),inset 0 1px 0 rgba(255,255,255,0.04)}
    table{width:100%;border-collapse:collapse}
    thead th{background:rgba(0,0,0,0.25);color:var(--text-3);font-size:10px;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;padding:11px 16px;text-align:left;border-bottom:1px solid var(--bdr);white-space:nowrap}
    tbody tr{border-bottom:1px solid rgba(255,255,255,0.04);transition:background 0.12s var(--ease)}
    tbody tr:last-child{border-bottom:none}
    tbody tr:hover{background:rgba(255,255,255,0.04)}
    td{padding:11px 16px;vertical-align:middle;font-size:12.5px}
    .td-id{color:var(--text-3);font-size:11px;width:40px}
    .td-co{color:var(--text-1);font-weight:600;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .td-role{color:var(--text-2);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}
    .td-date{color:var(--text-3);font-size:11.5px;white-space:nowrap}
    .td-resume{color:var(--text-3);font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .score-badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;border:1px solid transparent}
    .score-high{background:rgba(16,185,129,0.14);color:#34d399;border-color:rgba(16,185,129,0.28)}
    .score-mid{background:rgba(245,158,11,0.13);color:#fcd34d;border-color:rgba(245,158,11,0.28)}
    .score-low{background:rgba(239,68,68,0.12);color:#fca5a5;border-color:rgba(239,68,68,0.25)}
    .score-none{background:var(--s2);color:var(--text-3);border-color:var(--bdr)}
    .status-select{appearance:none;-webkit-appearance:none;background:var(--s2);border:1px solid var(--bdr);color:var(--text-2);padding:4px 22px 4px 9px;border-radius:7px;font-size:11px;font-weight:500;font-family:inherit;cursor:pointer;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' fill='none'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23475569' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 7px center;transition:border-color 0.15s;outline:none}
    .status-select:hover{border-color:var(--bdr-h);color:var(--text-1)}
    .status-select:focus{border-color:var(--accent)}
    .job-link{color:rgba(129,140,248,0.7);text-decoration:none;font-size:12px;margin-left:4px;transition:color 0.12s}
    .job-link:hover{color:var(--accent-lt)}
    .empty-state{padding:64px 24px;text-align:center}
    .empty-icon{width:48px;height:48px;border-radius:14px;margin:0 auto 16px;background:linear-gradient(135deg,#4f46e5,#7c3aed);display:flex;align-items:center;justify-content:center;box-shadow:0 4px 18px rgba(99,102,241,0.4)}
    .empty-icon svg{width:24px;height:24px}
    .empty-title{font-size:15px;font-weight:700;margin-bottom:6px}
    .empty-sub{font-size:12.5px;color:var(--text-3)}
    .loading{padding:48px;text-align:center;color:var(--text-3);font-size:13px}
    .toast{position:fixed;bottom:24px;right:24px;padding:9px 16px;border-radius:9px;font-size:12px;font-weight:600;opacity:0;pointer-events:none;transition:opacity 0.25s var(--ease),transform 0.25s var(--ease);transform:translateY(6px)}
    .toast.show{opacity:1;transform:translateY(0)}
    .toast-ok{background:rgba(16,185,129,0.92);color:#fff}
    .toast-err{background:rgba(239,68,68,0.92);color:#fff}
    .hidden-row{display:none}
  </style>
</head>
<body>
<div class="page">
  <div class="header">
    <div class="header-left">
      <div class="header-icon">
        <svg viewBox="0 0 20 20" fill="none"><path d="M10 2C10 6.6 6.6 10 2 10C6.6 10 10 13.4 10 18C10 13.4 13.4 10 18 10C13.4 10 10 6.6 10 2Z" fill="white" opacity="0.95"/><circle cx="16" cy="4" r="1.3" fill="white" opacity="0.55"/></svg>
      </div>
      <div>
        <div class="header-title">AI Job Agent</div>
        <div class="header-sub" id="headerSub">Loading…</div>
      </div>
    </div>
    <div class="actions">
      <a class="btn" href="/api/export/csv">&#8595; Export CSV</a>
      <a class="btn" href="/api/resumes/gaps" target="_blank">Skill gaps</a>
      <a class="btn btn-primary" href="/docs" target="_blank">API docs</a>
    </div>
  </div>

  <div class="stats-strip" id="statsStrip"></div>
  <div class="table-card" id="tableCard"><div class="loading">Loading applications…</div></div>
</div>

<div class="toast" id="toast"></div>

<script>
const STATUSES = ['captured','applied','interviewing','offer','rejected','no_response'];
const CHIP_LABELS = {captured:'Captured',applied:'Applied',interviewing:'Interviewing',offer:'Offer',rejected:'Rejected',no_response:'No Response'};
let allApps = [];
let activeFilter = 'all';

function scoreClass(s) {
  if (s == null) return 'score-none';
  if (s >= 0.70) return 'score-high';
  if (s >= 0.50) return 'score-mid';
  return 'score-low';
}
function scoreFmt(s) { return s != null ? Math.round(s * 100) + '%' : '—'; }
function esc(s) { if (!s) return ''; return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmtDate(s) { return s ? s.slice(0,10) : '—'; }

function buildStats(apps) {
  const counts = {all: apps.length};
  STATUSES.forEach(s => counts[s] = 0);
  apps.forEach(a => { if (counts[a.status] != null) counts[a.status]++; });
  return counts;
}

function renderStrip(counts) {
  const strip = document.getElementById('statsStrip');
  let html = `<button class="stat-chip chip-all ${activeFilter==='all'?'active':''}" onclick="filter('all')"><span class="stat-dot"></span>All <strong>${counts.all}</strong></button>`;
  STATUSES.forEach(s => {
    if (counts[s] > 0) {
      html += `<button class="stat-chip chip-${s} ${activeFilter===s?'active':''}" onclick="filter('${s}')"><span class="stat-dot"></span>${CHIP_LABELS[s]} <strong>${counts[s]}</strong></button>`;
    }
  });
  strip.innerHTML = html;
}

function renderTable(apps) {
  if (!apps.length) {
    document.getElementById('tableCard').innerHTML = `<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 20 20" fill="none"><path d="M10 2C10 6.6 6.6 10 2 10C6.6 10 10 13.4 10 18C10 13.4 13.4 10 18 10C13.4 10 10 6.6 10 2Z" fill="white" opacity="0.9"/></svg></div><div class="empty-title">No applications yet</div><div class="empty-sub">Open a job posting and click Capture &amp; Process in the extension.</div></div>`;
    return;
  }
  let rows = apps.map(a => {
    const sc = scoreClass(a.match_score);
    const opts = STATUSES.map(s => `<option value="${s}" ${a.status===s?'selected':''}>${CHIP_LABELS[s]}</option>`).join('');
    const link = a.url ? `<a href="${esc(a.url)}" target="_blank" class="job-link" title="${esc(a.url)}">&#8599;</a>` : '';
    return `<tr data-status="${esc(a.status)}">
      <td class="td-id">${a.id}</td>
      <td class="td-co">${esc(a.company||'—')}</td>
      <td><span class="td-role">${esc(a.job_title||'—')}</span>${link}</td>
      <td><span class="score-badge ${sc}">${scoreFmt(a.match_score)}</span></td>
      <td class="td-resume">${esc(a.resume_used||'—')}</td>
      <td><select class="status-select" onchange="updateStatus(${a.id},this.value)">${opts}</select></td>
      <td class="td-date">${fmtDate(a.applied_date)}</td>
      <td class="td-date">${fmtDate(a.created_at)}</td>
    </tr>`;
  }).join('');
  document.getElementById('tableCard').innerHTML = `<table><thead><tr><th>#</th><th>Company</th><th>Role</th><th>Score</th><th>Resume</th><th>Status</th><th>Applied</th><th>Captured</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function filter(status) {
  activeFilter = status;
  renderStrip(buildStats(allApps));
  document.querySelectorAll('#tableCard tbody tr').forEach(tr => {
    tr.classList.toggle('hidden-row', status !== 'all' && tr.dataset.status !== status);
  });
}

async function updateStatus(id, status) {
  try {
    const r = await fetch(`/api/applications/${id}/status?status=${encodeURIComponent(status)}`, {method:'PATCH'});
    if (!r.ok) throw new Error();
    const tr = document.querySelector(`#tableCard tbody tr:has([onchange*="updateStatus(${id},"])`) ||
               [...document.querySelectorAll('#tableCard tbody tr')].find(tr => tr.innerHTML.includes(`updateStatus(${id},`));
    if (tr) tr.dataset.status = status;
    const idx = allApps.findIndex(a => a.id === id);
    if (idx >= 0) allApps[idx].status = status;
    renderStrip(buildStats(allApps));
    showToast(`#${id} → ${CHIP_LABELS[status]||status}`, false);
  } catch { showToast('Update failed', true); }
}

function showToast(msg, err) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${err ? 'toast-err' : 'toast-ok'} show`;
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), 2200);
}

async function load() {
  try {
    const r = await fetch('/api/applications');
    if (!r.ok) throw new Error('API error');
    allApps = await r.json();
    document.getElementById('headerSub').textContent = `${allApps.length} application${allApps.length!==1?'s':''} tracked`;
    renderStrip(buildStats(allApps));
    renderTable(allApps);
  } catch(e) {
    document.getElementById('tableCard').innerHTML = `<div class="empty-state"><div class="empty-title">Failed to load</div><div class="empty-sub">${e.message}</div></div>`;
  }
}

load();
</script>
</body>
</html>"""


# ─── GET /dashboard ───────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard():
    """Client-side rendered application dashboard. Fetches data from /api/applications."""
    return HTMLResponse(content=_DASHBOARD_HTML)


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

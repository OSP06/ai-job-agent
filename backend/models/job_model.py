from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


# ─── Input from Chrome Extension ─────────────────────────────────────────────

class JobInput(BaseModel):
    url: str
    raw_text: str
    page_title: Optional[str] = None
    # Extracted by content.js from LinkedIn / job page
    linkedin_recruiter_name: Optional[str] = None
    linkedin_recruiter_url: Optional[str] = None


# ─── Parsed Job (from OpenAI) ─────────────────────────────────────────────────

class JobData(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None          # full-time, contract, etc.
    description: str
    requirements: list[str] = Field(default_factory=list)
    company_domain: Optional[str] = None   # used for Hunter.io lookup


# ─── Resume match result ──────────────────────────────────────────────────────

class ResumeMatch(BaseModel):
    resume_name: str
    resume_path: str
    score: float                            # 0.0–1.0 hybrid score
    resume_text_snippet: str               # first 500 chars for outreach prompt
    all_scores: dict[str, float] = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


# ─── Outreach message ─────────────────────────────────────────────────────────

class OutreachMessage(BaseModel):
    subject: str
    body: str


# ─── Contact ─────────────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    application_id: int
    name: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    title: Optional[str] = None


class ContactResponse(ContactCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Application ─────────────────────────────────────────────────────────────

class ApplicationCreate(BaseModel):
    job_title: str
    company: str
    url: str
    location: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None
    description: str
    requirements_json: str                  # JSON-serialised list
    resume_used: Optional[str] = None
    match_score: Optional[float] = None
    status: str = "captured"               # captured | applied | interviewing | rejected | offer | no_response


class ApplicationResponse(ApplicationCreate):
    id: int
    applied_date: Optional[date] = None
    follow_up_due_1: Optional[date] = None
    follow_up_due_2: Optional[date] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Outreach record ─────────────────────────────────────────────────────────

class OutreachCreate(BaseModel):
    application_id: int
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    message_subject: str
    message_body: str
    status: str = "draft"                   # draft | sent
    gmail_draft_id: Optional[str] = None


class OutreachResponse(OutreachCreate):
    id: int
    sent_at: Optional[datetime] = None
    followup_due: Optional[date] = None
    followup_sent: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Follow-up record ────────────────────────────────────────────────────────

class FollowupCreate(BaseModel):
    outreach_id: int
    application_id: int
    message_body: str
    followup_number: int                   # 1 = day-7, 2 = day-14
    gmail_draft_id: Optional[str] = None


class FollowupResponse(FollowupCreate):
    id: int
    status: str                            # pending | sent | skipped
    sent_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Pipeline response (returned to extension) ───────────────────────────────

class ProcessJobResponse(BaseModel):
    application_id: int
    job_title: str
    company: str
    match_score: float
    resume_used: str
    all_resume_scores: dict[str, float] = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    contacts_found: list[dict] = Field(default_factory=list)
    outreach_generated: bool
    outreach_skipped_reason: Optional[str] = None
    gmail_draft_id: Optional[str] = None
    message: str

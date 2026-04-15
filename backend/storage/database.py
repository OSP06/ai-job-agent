"""
SQLAlchemy models and CRUD helpers.

Tables
------
applications      — one row per job posting captured
contacts          — recruiter/hiring-manager contacts per application
outreach_messages — initial outreach email per application
followups         — day-7 and day-14 follow-up emails
"""

import json
import os
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from backend.config import settings


# ─── Engine & session ─────────────────────────────────────────────────────────

def _build_engine():
    url = os.environ.get("DATABASE_URL", f"sqlite:///{settings.db_path}")
    # Render supplies postgres:// but SQLAlchemy requires postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── ORM models ───────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    url = Column(String, nullable=False)
    location = Column(String)
    salary = Column(String)
    job_type = Column(String)
    description = Column(Text)
    requirements_json = Column(Text, default="[]")
    resume_used = Column(String)
    match_score = Column(Float)
    missing_skills_json = Column(Text, default="[]")

    # Status lifecycle: captured → applied → interviewing → rejected | offer | no_response
    status = Column(String, default="captured")

    applied_date = Column(Date)
    follow_up_due_1 = Column(Date)       # applied_date + 7 days
    follow_up_due_2 = Column(Date)       # applied_date + 14 days
    created_at = Column(DateTime, default=datetime.utcnow)

    contacts = relationship("Contact", back_populates="application", cascade="all, delete-orphan")
    outreach_messages = relationship("OutreachMessage", back_populates="application", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    name = Column(String)
    email = Column(String)
    linkedin_url = Column(String)
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="contacts")


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    contact_name = Column(String)
    contact_email = Column(String)
    message_subject = Column(String)
    message_body = Column(Text)
    status = Column(String, default="draft")     # draft | sent
    gmail_draft_id = Column(String)
    sent_at = Column(DateTime)
    followup_due = Column(Date)                  # set when status → sent
    followup_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    application = relationship("Application", back_populates="outreach_messages")
    followups = relationship("Followup", back_populates="outreach", cascade="all, delete-orphan")


class Followup(Base):
    __tablename__ = "followups"

    id = Column(Integer, primary_key=True, index=True)
    outreach_id = Column(Integer, ForeignKey("outreach_messages.id"), nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    followup_number = Column(Integer)            # 1 = day-7, 2 = day-14
    message_body = Column(Text)
    gmail_draft_id = Column(String)
    status = Column(String, default="pending")   # pending | sent | skipped
    sent_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    outreach = relationship("OutreachMessage", back_populates="followups")


class Resume(Base):
    """Stores resume text + embedding so data persists without a filesystem volume."""
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)   # filename stem, e.g. "john_doe_resume"
    text = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=False)        # JSON array of floats
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Init ─────────────────────────────────────────────────────────────────────

def init_db() -> None:
    Base.metadata.create_all(bind=engine)


# ─── CRUD: Applications ───────────────────────────────────────────────────────

def get_application_by_url(db: Session, url: str) -> Optional[Application]:
    return db.query(Application).filter(Application.url == url).first()


def create_application(
    db: Session,
    job_title: str,
    company: str,
    url: str,
    description: str,
    requirements: list[str],
    resume_used: Optional[str] = None,
    match_score: Optional[float] = None,
    location: Optional[str] = None,
    salary: Optional[str] = None,
    job_type: Optional[str] = None,
    status: str = "captured",
    missing_skills: list[str] | None = None,
) -> Application:
    app = Application(
        job_title=job_title,
        company=company,
        url=url,
        description=description,
        requirements_json=json.dumps(requirements),
        resume_used=resume_used,
        match_score=match_score,
        location=location,
        salary=salary,
        job_type=job_type,
        status=status,
        missing_skills_json=json.dumps(missing_skills or []),
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def mark_applied(db: Session, application_id: int) -> Optional[Application]:
    app = db.get(Application, application_id)
    if not app:
        return None
    today = date.today()
    app.status = "applied"
    app.applied_date = today
    app.follow_up_due_1 = today + timedelta(days=settings.followup_day_1)
    app.follow_up_due_2 = today + timedelta(days=settings.followup_day_2)
    db.commit()
    db.refresh(app)
    return app


def update_application_status(db: Session, application_id: int, status: str) -> Optional[Application]:
    app = db.get(Application, application_id)
    if not app:
        return None
    app.status = status
    db.commit()
    db.refresh(app)
    return app


def get_applications(db: Session, status: Optional[str] = None) -> list[Application]:
    q = db.query(Application)
    if status:
        q = q.filter(Application.status == status)
    return q.order_by(Application.created_at.desc()).all()


def get_application(db: Session, application_id: int) -> Optional[Application]:
    return db.get(Application, application_id)


# ─── CRUD: Contacts ───────────────────────────────────────────────────────────

def create_contact(
    db: Session,
    application_id: int,
    name: Optional[str] = None,
    email: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    title: Optional[str] = None,
) -> Contact:
    contact = Contact(
        application_id=application_id,
        name=name,
        email=email,
        linkedin_url=linkedin_url,
        title=title,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ─── CRUD: Outreach messages ──────────────────────────────────────────────────

def create_outreach(
    db: Session,
    application_id: int,
    message_subject: str,
    message_body: str,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    gmail_draft_id: Optional[str] = None,
) -> OutreachMessage:
    outreach = OutreachMessage(
        application_id=application_id,
        contact_name=contact_name,
        contact_email=contact_email,
        message_subject=message_subject,
        message_body=message_body,
        gmail_draft_id=gmail_draft_id,
        status="draft",
    )
    db.add(outreach)
    db.commit()
    db.refresh(outreach)
    return outreach


def get_pending_followups(db: Session) -> list[OutreachMessage]:
    """Return outreach records where followup is due and not yet sent."""
    today = date.today()
    return (
        db.query(OutreachMessage)
        .filter(
            OutreachMessage.followup_due <= today,
            OutreachMessage.followup_sent == False,  # noqa: E712
            OutreachMessage.status == "sent",
        )
        .all()
    )


def get_applications_due_followup(db: Session, followup_number: int) -> list[Application]:
    """Return applied applications whose follow_up_due_N date has arrived."""
    today = date.today()
    if followup_number == 1:
        return (
            db.query(Application)
            .filter(
                Application.status == "applied",
                Application.follow_up_due_1 <= today,
            )
            .all()
        )
    return (
        db.query(Application)
        .filter(
            Application.status == "applied",
            Application.follow_up_due_2 <= today,
        )
        .all()
    )


# ─── CRUD: Follow-ups ────────────────────────────────────────────────────────

def create_followup(
    db: Session,
    outreach_id: int,
    application_id: int,
    message_body: str,
    followup_number: int,
    gmail_draft_id: Optional[str] = None,
) -> Followup:
    followup = Followup(
        outreach_id=outreach_id,
        application_id=application_id,
        message_body=message_body,
        followup_number=followup_number,
        gmail_draft_id=gmail_draft_id,
        status="pending",
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


def mark_followup_sent(db: Session, followup_id: int) -> Optional[Followup]:
    followup = db.get(Followup, followup_id)
    if not followup:
        return None
    followup.status = "sent"
    followup.sent_at = datetime.utcnow()
    db.commit()
    db.refresh(followup)
    return followup


# ─── CRUD: Resumes ────────────────────────────────────────────────────────────

def upsert_resume(db: Session, name: str, text: str, embedding: list) -> Resume:
    """Insert or replace a resume record."""
    existing = db.query(Resume).filter(Resume.name == name).first()
    if existing:
        existing.text = text
        existing.embedding_json = json.dumps(embedding)
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    resume = Resume(name=name, text=text, embedding_json=json.dumps(embedding))
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def get_all_resumes(db: Session) -> list[Resume]:
    return db.query(Resume).all()


def delete_resume(db: Session, name: str) -> bool:
    existing = db.query(Resume).filter(Resume.name == name).first()
    if not existing:
        return False
    db.delete(existing)
    db.commit()
    return True

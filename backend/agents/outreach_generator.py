"""
outreach_generator.py
─────────────────────
Uses OpenAI GPT-4o-mini to generate:
  1. Initial outreach email (cold email / LinkedIn note)
  2. Follow-up email variants (day-7 and day-14)

Outreach is ONLY generated when match_score >= settings.match_score_threshold.
"""

import json
from openai import OpenAI
from backend.config import settings
from backend.models.job_model import JobData, OutreachMessage, ResumeMatch
from backend.utils.logger import logger

_client: OpenAI | None = None


def _get_client() -> OpenAI | None:
    global _client
    if _client is None:
        key = settings.openai_api_key
        if not key:
            logger.warning("OPENAI_API_KEY is not set — outreach generation disabled")
            return None
        _client = OpenAI(api_key=key)
    return _client


OUTREACH_SYSTEM = """You are an expert job-application copywriter.
Write a short, personalized cold email for a job application.
Rules:
- Subject line: concise, specific to the role (max 10 words)
- Body: 3–4 sentences max. Mention the specific role, 1–2 matching skills, clear CTA.
- Tone: professional but human — not robotic, not sycophantic.
- Sign off with "Best,\\nOm"
Return ONLY valid JSON with no markdown: {"subject": "...", "body": "..."}
"""

FOLLOWUP_SYSTEM = """You are writing a brief follow-up email for a job application.
Rules:
- Reference the original outreach naturally.
- Express continued interest in 1–2 sentences.
- Keep it under 5 sentences total.
- Tone: friendly, not pushy.
- Sign off with "Best,\\nOm"
Return ONLY valid JSON with no markdown: {"subject": "...", "body": "..."}
"""


def _should_generate(score: float) -> tuple[bool, str | None]:
    """Returns (should_generate, skip_reason)."""
    if score < settings.match_score_threshold:
        reason = (
            f"Match score {score:.0%} is below threshold "
            f"{settings.match_score_threshold:.0%}. Outreach skipped."
        )
        return False, reason
    return True, None


def _parse_json(raw: str) -> dict:
    """Parse JSON, stripping optional markdown code fences."""
    import re
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def generate_outreach(
    job: JobData,
    resume_match: ResumeMatch,
) -> tuple[OutreachMessage | None, str | None]:
    """
    Generate initial outreach email.

    Returns:
        (OutreachMessage, None) on success
        (None, skip_reason) when score is below threshold or client unavailable
    """
    should_go, skip_reason = _should_generate(resume_match.score)
    if not should_go:
        logger.info(skip_reason)
        return None, skip_reason

    client = _get_client()
    if not client:
        return None, "OPENAI_API_KEY not configured"

    logger.info(f"Generating outreach for {job.title} @ {job.company}")

    user_prompt = f"""Job: {job.title} at {job.company}
Location: {job.location or "Not specified"}
Requirements: {", ".join(job.requirements[:6])}
Job summary: {job.description[:300]}

My resume highlights (matched resume: {resume_match.resume_name}):
{resume_match.resume_text_snippet}

Write the cold email."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": OUTREACH_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=512,
        temperature=0.7,
    )

    data = _parse_json(response.choices[0].message.content)
    msg = OutreachMessage(subject=data["subject"], body=data["body"])
    logger.info(f"Outreach generated. Subject: '{msg.subject}'")
    return msg, None


def generate_followup(
    job: JobData,
    original_subject: str,
    followup_number: int,
    contact_name: str | None = None,
) -> OutreachMessage:
    """
    Generate a follow-up email.

    followup_number:
        1 = day-7 follow-up
        2 = day-14 final follow-up (after this → mark no_response)
    """
    client = _get_client()
    if not client:
        raise RuntimeError("OPENAI_API_KEY not configured — cannot generate follow-up")

    label = "first follow-up (Day 7)" if followup_number == 1 else "final follow-up (Day 14)"
    logger.info(f"Generating {label} for {job.title} @ {job.company}")

    greeting = f"Hi {contact_name}" if contact_name else "Hi"
    day_context = (
        "I sent an initial message about a week ago"
        if followup_number == 1
        else "I've reached out twice before about this role"
    )

    user_prompt = f"""Context: {day_context}.
Role: {job.title} at {job.company}
Original subject: "{original_subject}"
Greeting to use: "{greeting}"
Follow-up number: {followup_number} of 2

Write the follow-up email.
After this (follow-up 2), I will stop reaching out and mark the application as no response."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": FOLLOWUP_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=512,
        temperature=0.7,
    )

    data = _parse_json(response.choices[0].message.content)
    msg = OutreachMessage(subject=data["subject"], body=data["body"])
    logger.info(f"Follow-up {followup_number} generated. Subject: '{msg.subject}'")
    return msg

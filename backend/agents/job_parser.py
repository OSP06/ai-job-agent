"""
job_parser.py
─────────────
Uses OpenAI GPT-4o (JSON mode) to extract structured job data from raw page text.
"""

import json
from openai import OpenAI
from backend.config import settings
from backend.models.job_model import JobData, JobInput
from backend.utils.logger import logger

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


SYSTEM_PROMPT = """You are a precise job-data extractor.
Given raw text scraped from a job posting, return a JSON object with these fields:
- title: string (job title)
- company: string (company name)
- location: string or null
- salary: string or null (e.g. "$120k–$160k")
- job_type: string or null (full-time, contract, part-time, etc.)
- description: string (2–4 sentence summary of the role)
- requirements: array of strings (key required skills/qualifications, max 10)
- company_domain: string or null (e.g. "stripe.com" inferred from company name or URL)

Return ONLY valid JSON. No explanation, no markdown.
"""


async def parse_job(job_input: JobInput) -> JobData:
    """Call GPT-4o to extract structured job data from raw scraped text."""
    client = _get_client()

    user_content = f"URL: {job_input.url}\n\nPAGE TITLE: {job_input.page_title or 'N/A'}\n\nCONTENT:\n{job_input.raw_text[:6000]}"

    logger.info(f"Parsing job from {job_input.url}")

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)

    job = JobData(
        title=data.get("title", "Unknown Role"),
        company=data.get("company", "Unknown Company"),
        location=data.get("location"),
        salary=data.get("salary"),
        job_type=data.get("job_type"),
        description=data.get("description", ""),
        requirements=data.get("requirements", []),
        company_domain=data.get("company_domain"),
    )

    logger.info(f"Parsed: {job.title} @ {job.company} (match threshold check next)")
    return job

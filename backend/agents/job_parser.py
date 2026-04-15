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

_client: tuple | None = None   # (OpenAI instance, model name)


def _get_client() -> tuple:
    global _client
    if _client is None:
        if settings.groq_api_key:
            _client = (
                OpenAI(api_key=settings.groq_api_key,
                       base_url="https://api.groq.com/openai/v1"),
                "llama-3.3-70b-versatile",
            )
            logger.info("job_parser: using Groq (llama-3.3-70b-versatile)")
        else:
            _client = (OpenAI(api_key=settings.openai_api_key), "gpt-4o")
            logger.info("job_parser: using OpenAI (gpt-4o)")
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
- company_domain: string or null — the HIRING COMPANY's own website domain, inferred from
  the company name only (e.g. "sofi.com" for "SoFi", "stripe.com" for "Stripe").
  NEVER use job board / ATS platform domains such as linkedin.com, indeed.com, greenhouse.io,
  lever.co, tokyodev.com, wellfound.com, workday.com, ashbyhq.com, smartrecruiters.com, etc.
  If you cannot confidently infer the company's own domain, return null.

Return ONLY valid JSON. No explanation, no markdown.
"""


async def parse_job(job_input: JobInput) -> JobData:
    """Extract structured job data from raw scraped text via Groq or OpenAI."""
    client, model = _get_client()

    user_content = f"URL: {job_input.url}\n\nPAGE TITLE: {job_input.page_title or 'N/A'}\n\nCONTENT:\n{job_input.raw_text[:6000]}"

    logger.info(f"Parsing job from {job_input.url}")

    response = client.chat.completions.create(
        model=model,
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

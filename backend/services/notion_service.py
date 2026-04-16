"""
notion_service.py
─────────────────
Optional Notion integration — syncs captured jobs to a Notion database.
Skipped silently when NOTION_TOKEN / NOTION_DATABASE_ID are not set.

Notion database columns expected:
  Job Title    → Title
  Company      → Text
  URL          → URL
  Status       → Select  (captured | applied | interviewing | offer | rejected)
  Match Score  → Number  (percentage, e.g. 78.5)
  Resume Used  → Text
  Location     → Text
  Email Subject→ Text

The outreach email body is written as a paragraph block inside the page.
"""

from typing import Optional

import httpx

from backend.config import settings
from backend.utils.logger import logger

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


async def sync_to_notion(
    job_title: str,
    company: str,
    url: str,
    status: str,
    match_score: Optional[float] = None,
    resume_used: Optional[str] = None,
    location: Optional[str] = None,
    outreach_subject: Optional[str] = None,
    outreach_body: Optional[str] = None,
) -> Optional[str]:
    """
    Create a new page in the configured Notion database.
    Returns the Notion page ID, or None if not configured / on failure.
    """
    if not settings.notion_token or not settings.notion_database_id:
        logger.debug("Notion not configured — skipping sync")
        return None

    headers = {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    properties: dict = {
        "Job Title": {"title":     [{"text": {"content": job_title}}]},
        "Company":   {"rich_text": [{"text": {"content": company}}]},
        "URL":       {"url": url},
        "Status":    {"select":    {"name": status}},
    }

    if location:
        properties["Location"]      = {"rich_text": [{"text": {"content": location}}]}
    if match_score is not None:
        properties["Match Score"]   = {"number": round(match_score * 100, 1)}
    if resume_used:
        properties["Resume Used"]   = {"rich_text": [{"text": {"content": resume_used}}]}
    if outreach_subject:
        properties["Email Subject"] = {"rich_text": [{"text": {"content": outreach_subject}}]}

    # Outreach body goes in the page body (too long for a property)
    children = []
    if outreach_body:
        children = [
            {
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": "Outreach Email"}}]},
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": outreach_body[:2000]}}]},
            },
        ]

    payload = {
        "parent": {"database_id": settings.notion_database_id},
        "properties": properties,
        **({"children": children} if children else {}),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(NOTION_API_URL, headers=headers, json=payload)
            r.raise_for_status()
            page_id = r.json().get("id")
            logger.info(f"Notion page created: {page_id} — {job_title} @ {company}")
            return page_id
    except Exception as e:
        logger.warning(f"Notion sync failed: {e}")
        return None

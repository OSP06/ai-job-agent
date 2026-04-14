"""
notion_service.py
─────────────────
Optional Notion integration — syncs application records to a Notion database.
Skipped silently when NOTION_TOKEN is not set.
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
) -> Optional[str]:
    """
    Create a new page in the configured Notion database.

    Returns the Notion page ID, or None if not configured / failed.
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
        "Job Title": {"title": [{"text": {"content": job_title}}]},
        "Company": {"rich_text": [{"text": {"content": company}}]},
        "URL": {"url": url},
        "Status": {"select": {"name": status}},
    }

    if location:
        properties["Location"] = {"rich_text": [{"text": {"content": location}}]}
    if match_score is not None:
        properties["Match Score"] = {"number": round(match_score * 100, 1)}
    if resume_used:
        properties["Resume Used"] = {"rich_text": [{"text": {"content": resume_used}}]}

    payload = {
        "parent": {"database_id": settings.notion_database_id},
        "properties": properties,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(NOTION_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            page_id = response.json().get("id")
            logger.info(f"Notion page created: {page_id} for {job_title} @ {company}")
            return page_id
    except Exception as e:
        logger.warning(f"Notion sync failed: {e}")
        return None

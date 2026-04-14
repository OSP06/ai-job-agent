"""
recruiter_finder.py
───────────────────
Uses Hunter.io to find recruiter / hiring-manager emails for a company domain.
Returns None gracefully if HUNTER_API_KEY is not configured.
"""

import httpx
from backend.config import settings
from backend.utils.logger import logger

HUNTER_API_URL = "https://api.hunter.io/v2/domain-search"


async def find_recruiter(company_domain: str) -> dict | None:
    """
    Search Hunter.io for the most relevant recruiter contact at a domain.

    Returns:
        {"name": str, "email": str, "title": str} or None
    """
    if not settings.hunter_api_key:
        logger.debug("HUNTER_API_KEY not set — skipping recruiter lookup")
        return None

    if not company_domain:
        return None

    params = {
        "domain": company_domain,
        "api_key": settings.hunter_api_key,
        "limit": 5,
        "type": "personal",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(HUNTER_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

        emails = data.get("data", {}).get("emails", [])
        if not emails:
            logger.info(f"No contacts found for domain: {company_domain}")
            return None

        # Prefer HR / recruiting titles
        priority_keywords = ["recruit", "talent", "hr", "people", "hiring"]
        for email_data in emails:
            title = (email_data.get("position") or "").lower()
            if any(kw in title for kw in priority_keywords):
                return _format_contact(email_data)

        # Fall back to first result
        return _format_contact(emails[0])

    except Exception as e:
        logger.warning(f"Hunter.io lookup failed for {company_domain}: {e}")
        return None


def _format_contact(email_data: dict) -> dict:
    first = email_data.get("first_name", "")
    last = email_data.get("last_name", "")
    name = f"{first} {last}".strip() or None
    return {
        "name": name,
        "email": email_data.get("value"),
        "title": email_data.get("position"),
    }

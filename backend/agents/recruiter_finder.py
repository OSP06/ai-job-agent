"""
recruiter_finder.py
───────────────────
Finds and verifies contacts at a company using Hunter.io.

Priority order:
  1. LinkedIn-named recruiter  →  Hunter email-finder by name
  2. HR / recruiting dept      →  Hunter domain-search (department=hr)
  3. Management / engineering  →  Hunter domain-search (department=management)

Each email is verified before being returned.
Returns up to 3 ranked contacts, verified first.
"""

import httpx
from backend.config import settings
from backend.utils.logger import logger

HUNTER_BASE = "https://api.hunter.io/v2"


# ─── Public entry point ───────────────────────────────────────────────────────

async def find_contacts(
    company_domain: str,
    linkedin_name: str | None = None,
) -> list[dict]:
    """
    Returns up to 3 ranked, verified contacts for the company.
    Each contact: {name, email, title, linkedin_url, source, verified, confidence}
    """
    if not settings.hunter_api_key or not company_domain:
        return []

    seen: set[str] = set()
    candidates: list[dict] = []

    # 1. LinkedIn-named person → email-finder (highest priority)
    if linkedin_name:
        found = await _find_email_by_name(linkedin_name, company_domain)
        if found and found.get("email"):
            _add_unique(candidates, seen, {**found, "source": "linkedin"})

    # 2. HR / recruiting dept
    hr = await _domain_search(company_domain, department="hr", limit=5)
    for c in hr:
        _add_unique(candidates, seen, {**c, "source": "hunter_hr"})

    # 3. Management
    mgmt = await _domain_search(company_domain, department="management", limit=3)
    for c in mgmt:
        _add_unique(candidates, seen, {**c, "source": "hunter_mgmt"})

    # 4. Fallback: any (if nothing found yet)
    if not candidates:
        any_contacts = await _domain_search(company_domain, department=None, limit=5)
        for c in any_contacts:
            _add_unique(candidates, seen, {**c, "source": "hunter_any"})

    # 5. Verify emails (cap at 5 to stay within Hunter free tier)
    for contact in candidates[:5]:
        ver = await _verify_email(contact["email"])
        contact["verified"] = ver.get("result") == "deliverable"
        contact["confidence"] = ver.get("score", 0)

    # 6. Rank: verified first, then by confidence
    candidates.sort(key=lambda c: (-int(c.get("verified", False)), -c.get("confidence", 0)))

    logger.info(
        f"Hunter contacts for {company_domain}: "
        + ", ".join(f"{c['name']} <{c['email']}> verified={c.get('verified')}" for c in candidates[:3])
    )
    return candidates[:3]


# ─── Hunter API calls ─────────────────────────────────────────────────────────

async def _domain_search(
    domain: str,
    department: str | None,
    limit: int = 5,
) -> list[dict]:
    params = {
        "domain": domain,
        "api_key": settings.hunter_api_key,
        "limit": limit,
        "type": "personal",
    }
    if department:
        params["department"] = department

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{HUNTER_BASE}/domain-search", params=params)
            r.raise_for_status()
        emails = r.json().get("data", {}).get("emails", [])
        return [_fmt(e) for e in emails if e.get("value")]
    except Exception as e:
        logger.warning(f"Hunter domain-search failed ({domain}, {department}): {e}")
        return []


async def _find_email_by_name(full_name: str, domain: str) -> dict | None:
    """Use Hunter email-finder to get the email for a specific person."""
    params = {
        "domain": domain,
        "full_name": full_name,
        "api_key": settings.hunter_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{HUNTER_BASE}/email-finder", params=params)
            r.raise_for_status()
        data = r.json().get("data", {})
        email = data.get("email")
        if not email:
            return None
        return {
            "name": full_name,
            "email": email,
            "title": data.get("position"),
            "linkedin_url": None,
            "confidence": data.get("score", 0),
        }
    except Exception as e:
        logger.warning(f"Hunter email-finder failed ({full_name} @ {domain}): {e}")
        return None


async def _verify_email(email: str) -> dict:
    """Verify a single email address. Returns {result, score}."""
    if not email:
        return {}
    params = {"email": email, "api_key": settings.hunter_api_key}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f"{HUNTER_BASE}/email-verifier", params=params)
            r.raise_for_status()
        data = r.json().get("data", {})
        return {"result": data.get("result"), "score": data.get("score", 0)}
    except Exception as e:
        logger.warning(f"Hunter email-verify failed ({email}): {e}")
        return {}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fmt(e: dict) -> dict:
    first = e.get("first_name", "")
    last  = e.get("last_name", "")
    return {
        "name":         f"{first} {last}".strip() or None,
        "email":        e.get("value"),
        "title":        e.get("position"),
        "linkedin_url": e.get("linkedin"),
        "verified":     False,
        "confidence":   e.get("confidence", 0),
    }


def _add_unique(lst: list, seen: set, contact: dict) -> None:
    email = contact.get("email")
    if email and email not in seen:
        seen.add(email)
        lst.append(contact)


# ─── Backward-compat shim (used by followup_scheduler) ───────────────────────
async def find_recruiter(company_domain: str) -> dict | None:
    contacts = await find_contacts(company_domain)
    return contacts[0] if contacts else None

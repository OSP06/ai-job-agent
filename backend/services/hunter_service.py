"""
hunter_service.py
─────────────────
Thin wrapper re-exported for convenience.
The actual logic lives in agents/recruiter_finder.py to keep it co-located
with other agent code. Import from here for service-layer usage.
"""

from backend.agents.recruiter_finder import find_recruiter

__all__ = ["find_recruiter"]

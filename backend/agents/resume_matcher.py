"""
resume_matcher.py
─────────────────
Loads resumes from the database (text + pre-computed embeddings).
Resumes are stored in the DB so they survive across Render restarts
without needing a persistent filesystem volume.

Upload flow:  POST /api/resumes/upload  →  extract text  →  embed  →  upsert DB  →  refresh cache
Match flow:   match_resume(job)  →  cosine similarity vs cached embeddings  →  ResumeMatch
"""

import json
import re
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.job_model import JobData, ResumeMatch
from backend.utils.embeddings import cosine_similarity, encode
from backend.utils.logger import logger

# In-memory cache: {name: (text, embedding)}
_resume_cache: dict[str, tuple[str, list]] = {}


def load_resumes_from_db(db) -> int:
    """Populate in-memory cache from the resumes table. Returns count loaded."""
    from backend.storage.database import get_all_resumes
    _resume_cache.clear()
    rows = get_all_resumes(db)
    for row in rows:
        try:
            embedding = json.loads(row.embedding_json)
            _resume_cache[row.name] = (row.text, embedding)
        except Exception as e:
            logger.error(f"Failed to load resume '{row.name}' from DB: {e}")
    logger.info(f"Loaded {len(_resume_cache)} resume(s) from database.")
    return len(_resume_cache)


def ingest_pdf(pdf_bytes: bytes, filename: str, db) -> "ResumeRecord":
    """
    Extract text from PDF bytes, compute embedding, persist to DB, update cache.
    Returns the DB record.
    """
    from backend.storage.database import upsert_resume
    name = Path(filename).stem
    text = _extract_text_from_bytes(pdf_bytes)
    if not text:
        raise ValueError(f"Could not extract any text from {filename}")
    embedding = encode(text[:8000])
    record = upsert_resume(db, name=name, text=text, embedding=embedding)
    _resume_cache[name] = (text, embedding)
    logger.info(f"Resume ingested: '{name}' ({len(text)} chars)")
    return record


def _extract_text_from_bytes(pdf_bytes: bytes) -> str:
    import io
    import pdfplumber  # lazy import
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    raw = "\n".join(text_parts)
    return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _build_job_query(job: JobData) -> str:
    parts = [job.title, job.company, job.description]
    if job.requirements:
        parts.append("Requirements: " + ", ".join(job.requirements))
    return " ".join(filter(None, parts))


def match_resume(job: JobData, db=None) -> Optional[ResumeMatch]:
    """
    Returns the best-matching resume or None if no resumes are loaded.
    Always reloads from DB when db is provided to stay in sync with uploads.
    """
    if db is not None:
        load_resumes_from_db(db)

    if not _resume_cache:
        logger.warning("No resumes in cache — skipping resume matching")
        return None

    query = _build_job_query(job)
    query_embedding = encode(query)

    best_name: Optional[str] = None
    best_score = -1.0
    best_text = ""
    all_scores: dict[str, float] = {}

    for name, (text, embedding) in _resume_cache.items():
        score = cosine_similarity(query_embedding, embedding)
        all_scores[name] = round(score, 4)
        if score > best_score:
            best_score = score
            best_name = name
            best_text = text

    if best_name is None:
        return None

    logger.info(
        f"Resume scores: {all_scores} → best='{best_name}' ({best_score:.0%}) "
        f"threshold={settings.match_score_threshold:.0%}"
    )

    return ResumeMatch(
        resume_name=best_name,
        resume_path=f"db:{best_name}",
        score=round(best_score, 4),
        resume_text_snippet=best_text[:500],
        all_scores=all_scores,
    )


def reload_resumes(db) -> int:
    """Clear cache and reload from DB."""
    return load_resumes_from_db(db)

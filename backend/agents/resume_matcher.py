"""
resume_matcher.py
─────────────────
Loads all PDFs from the resumes/ directory, computes sentence-transformer
embeddings, and returns the best-matching resume for a given job description.

Match score is a cosine similarity (0.0–1.0).
If score < settings.match_score_threshold, outreach generation is skipped.
"""

import re
from pathlib import Path

from backend.config import settings
from backend.models.job_model import JobData, ResumeMatch
from backend.utils.embeddings import cosine_similarity, encode
from backend.utils.logger import logger

# In-memory cache: {resume_name: (text, embedding)}
_resume_cache: dict[str, tuple[str, object]] = {}  # {name: (text, embedding)}


def _load_resumes() -> None:
    """Load and embed all PDFs from the resumes directory."""
    resumes_dir = Path(settings.resumes_dir)
    if not resumes_dir.exists():
        logger.warning(f"Resumes directory not found: {resumes_dir}")
        return

    pdf_files = list(resumes_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDF resumes found. Add PDFs to backend/resumes/")
        return

    for pdf_path in pdf_files:
        name = pdf_path.stem
        if name in _resume_cache:
            continue
        try:
            text = _extract_pdf_text(pdf_path)
            embedding = encode(text[:3000])  # use first ~3000 chars for embedding
            _resume_cache[name] = (text, embedding)
            logger.info(f"Loaded resume: {name} ({len(text)} chars)")
        except Exception as e:
            logger.error(f"Failed to load {pdf_path.name}: {e}")


def _extract_pdf_text(path: Path) -> str:
    import pdfplumber  # lazy import — avoids slow startup
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    raw = "\n".join(text_parts)
    # Collapse excessive whitespace
    return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _build_job_query(job: JobData) -> str:
    """Combine job fields into a single string for embedding."""
    parts = [job.title, job.company, job.description]
    if job.requirements:
        parts.append("Requirements: " + ", ".join(job.requirements))
    return " ".join(filter(None, parts))


def match_resume(job: JobData) -> ResumeMatch | None:
    """
    Returns the best-matching resume or None if no resumes are loaded.
    The caller is responsible for checking score vs threshold.
    """
    if not _resume_cache:
        _load_resumes()

    if not _resume_cache:
        logger.warning("No resumes available — skipping resume matching")
        return None

    query = _build_job_query(job)
    query_embedding = encode(query)

    best_name: str | None = None
    best_score = -1.0
    best_text = ""

    for name, (text, embedding) in _resume_cache.items():
        score = cosine_similarity(query_embedding, embedding)
        logger.debug(f"Resume '{name}' score: {score:.3f}")
        if score > best_score:
            best_score = score
            best_name = name
            best_text = text

    if best_name is None:
        return None

    resume_path = str(Path(settings.resumes_dir) / f"{best_name}.pdf")

    logger.info(
        f"Best resume: '{best_name}' score={best_score:.3f} "
        f"(threshold={settings.match_score_threshold})"
    )

    return ResumeMatch(
        resume_name=best_name,
        resume_path=resume_path,
        score=round(best_score, 4),
        resume_text_snippet=best_text[:500],
    )


def reload_resumes() -> int:
    """Clear cache and reload all resumes. Returns count loaded."""
    _resume_cache.clear()
    _load_resumes()
    return len(_resume_cache)

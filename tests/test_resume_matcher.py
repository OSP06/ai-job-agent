"""
Unit tests for the three pure scoring helpers in resume_matcher.py.

No DB, no network, no OpenAI calls — these are deterministic math functions.
"""
import pytest
from backend.agents.resume_matcher import _normalize_embedding, _keyword_score, _hybrid


# ─── _normalize_embedding ─────────────────────────────────────────────────────

def test_normalize_below_floor():
    """Cosine below 0.20 → clamped to 0.0."""
    assert _normalize_embedding(0.10) == 0.0


def test_normalize_above_ceiling():
    """Cosine above 0.70 → clamped to 1.0."""
    assert _normalize_embedding(0.75) == 1.0


def test_normalize_midpoint():
    """Midpoint cosine 0.45 → (0.45-0.20)/0.50 = 0.50."""
    assert _normalize_embedding(0.45) == pytest.approx(0.50, abs=1e-6)


# ─── _keyword_score ───────────────────────────────────────────────────────────

def test_keyword_score_no_known_skills():
    """JD with no recognised TECH_SKILLS terms returns neutral score (0.5, [], [])."""
    score, matched, missing = _keyword_score(
        "python developer",
        "looking for a motivated person with great communication skills",
    )
    assert score == 0.5
    assert matched == []
    assert missing == []


def test_keyword_score_perfect_match():
    """Resume and JD both contain 'python' → score 1.0, python in matched, nothing missing."""
    score, matched, missing = _keyword_score(
        "I know python and have used it for years",
        "requires python experience",
    )
    assert score == pytest.approx(1.0)
    assert "python" in matched
    assert missing == []


def test_keyword_score_zero_match():
    """JD requires python, resume only mentions java → score 0.0, python in missing."""
    score, matched, missing = _keyword_score(
        "expert java developer with spring boot experience",
        "requires python experience",
    )
    assert score == pytest.approx(0.0)
    assert matched == []
    assert "python" in missing


# ─── _hybrid ─────────────────────────────────────────────────────────────────

def test_hybrid_strong_match():
    """cosine=0.55, kw=0.90 → norm_emb=0.70 → 0.4*0.70 + 0.6*0.90 = 0.82."""
    assert _hybrid(0.55, 0.90) == pytest.approx(0.82, abs=1e-3)


def test_hybrid_weak_match():
    """cosine=0.25, kw=0.25 → norm_emb=0.10 → 0.4*0.10 + 0.6*0.25 = 0.19."""
    assert _hybrid(0.25, 0.25) == pytest.approx(0.19, abs=1e-3)


def test_hybrid_neutral_kw():
    """cosine=0.35, kw=0.50 (neutral JD) → norm_emb=0.30 → 0.4*0.30 + 0.6*0.50 = 0.42."""
    assert _hybrid(0.35, 0.50) == pytest.approx(0.42, abs=1e-3)

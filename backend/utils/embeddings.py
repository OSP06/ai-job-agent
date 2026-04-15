"""
embeddings.py
─────────────
Uses OpenAI text-embedding-3-small for resume matching.
Always OpenAI — Groq has no embedding models.
Avoids local PyTorch/sentence-transformers (~1GB) so the app runs on free hosting tiers.
Cost: ~$0.013/month at 900 jobs/month (text-embedding-3-small at $0.02/1M tokens).
"""

import math
from typing import List

from backend.config import settings


def encode(text: str) -> List[float]:
    """Return a unit-normalised embedding vector via OpenAI API."""
    from openai import OpenAI  # lazy: avoids import cost at startup
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],  # model max input
    )
    return response.data[0].embedding


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)

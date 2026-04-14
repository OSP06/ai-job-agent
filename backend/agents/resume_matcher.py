"""
resume_matcher.py
─────────────────
Hybrid scoring: embedding cosine similarity (resume selection) +
keyword overlap (ATS-style skill matching).

Formula:
  hybrid = 0.4 × norm_embedding + 0.6 × keyword_overlap
  norm_embedding = clamp((cosine − 0.20) / 0.50, 0, 1)

Calibration:
  Strong match  (cosine 0.55, 18/20 skills) → ~82%
  Moderate      (cosine 0.48, 12/20 skills) → ~65%
  Weak          (cosine 0.35,  5/20 skills) → ~33%
"""

import json
import re
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.models.job_model import JobData, ResumeMatch
from backend.utils.embeddings import cosine_similarity, encode
from backend.utils.logger import logger

# ─── Tech skills vocabulary (~400 terms) ─────────────────────────────────────
TECH_SKILLS: set[str] = {
    # Languages
    "python", "java", "javascript", "typescript", "go", "golang", "rust",
    "c++", "c#", "ruby", "php", "swift", "kotlin", "scala", "r", "bash",
    "shell", "sql", "html", "css", "elixir", "haskell", "lua", "perl",
    "objective-c", "dart", "groovy", "matlab",
    # Backend frameworks
    "fastapi", "django", "flask", "spring", "spring boot", "express",
    "rails", "node.js", "nodejs", "nestjs", "gin", "fiber", "actix",
    "laravel", "symfony", "asp.net", "grpc", "graphql", "rest", "websocket",
    "microservices", "serverless",
    # Frontend
    "react", "angular", "vue", "next.js", "nextjs", "svelte", "nuxt",
    "tailwind", "bootstrap", "redux", "zustand", "webpack", "vite",
    "react native", "flutter", "ionic",
    # AI / ML
    "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn",
    "langchain", "openai", "hugging face", "huggingface", "transformers",
    "bert", "gpt", "llm", "rag", "nlp", "computer vision", "mlflow",
    "weights & biases", "wandb", "xgboost", "lightgbm", "catboost",
    "spacy", "nltk", "stable diffusion", "diffusers", "llamaindex",
    "llama", "mistral", "anthropic", "claude", "embeddings",
    "fine-tuning", "rlhf", "vector database", "pinecone", "weaviate",
    "chroma", "faiss", "qdrant", "semantic search",
    # Data engineering
    "postgresql", "postgres", "mysql", "mongodb", "redis", "kafka",
    "elasticsearch", "dynamodb", "bigquery", "snowflake", "spark",
    "airflow", "dbt", "pandas", "numpy", "polars", "neo4j", "cassandra",
    "sqlite", "oracle", "mssql", "clickhouse", "databricks", "flink",
    "rabbitmq", "celery", "sqs", "sns", "kinesis", "pubsub",
    # Cloud
    "aws", "gcp", "azure", "lambda", "ec2", "s3", "ecs", "eks",
    "cloud run", "cloud functions", "fargate", "rds", "aurora",
    "cloudformation", "cdk", "terraform", "pulumi", "kubernetes",
    "docker", "helm", "istio", "service mesh",
    # DevOps / observability
    "github actions", "jenkins", "circleci", "gitlab", "gitlab ci",
    "ci/cd", "prometheus", "grafana", "datadog", "splunk", "new relic",
    "cloudwatch", "x-ray", "opentelemetry", "jaeger", "elk",
    "ansible", "chef", "puppet", "argocd", "flux",
    # Security
    "oauth", "oauth2", "jwt", "rbac", "saml", "sso", "ldap",
    "soc 2", "pci", "gdpr", "zero trust", "iam", "vault",
    # Testing
    "pytest", "jest", "cypress", "selenium", "playwright", "junit",
    "testng", "mocha", "chai", "vitest", "k6", "locust",
    # Architecture / patterns
    "event-driven", "cqrs", "saga", "domain-driven", "ddd",
    "api gateway", "load balancer", "cdn", "websockets", "grpc",
    "message queue", "pub/sub", "etl", "data pipeline",
    # Mobile
    "ios", "android", "swiftui", "jetpack compose",
    # Misc tools
    "git", "linux", "nginx", "apache", "kafka", "redis",
    "storybook", "figma", "postman", "swagger", "openapi",
    # Soft / process
    "agile", "scrum", "kanban", "jira", "confluence",
}

# Pre-compiled pattern for whole-word matching (built once at import time)
_SKILL_PATTERNS: dict[str, re.Pattern] = {
    skill: re.compile(r"(?<![a-z0-9\-])" + re.escape(skill) + r"(?![a-z0-9\-])", re.IGNORECASE)
    for skill in TECH_SKILLS
}

# In-memory cache: {name: (text, embedding)}
_resume_cache: dict[str, tuple[str, list]] = {}


# ─── Scoring helpers ──────────────────────────────────────────────────────────

def _normalize_embedding(cosine: float) -> float:
    """Map raw cosine (0.20–0.70) → 0–1. Values outside range are clamped."""
    return max(0.0, min(1.0, (cosine - 0.20) / 0.50))


def _keyword_score(
    resume_text: str,
    jd_text: str,
) -> tuple[float, list[str], list[str]]:
    """
    Returns (score 0–1, matched_skills, missing_skills).
    Skills are those from TECH_SKILLS that appear in the JD.
    Score = matched / total_in_jd  (0 if JD has no recognised skills).
    """
    jd_lower = jd_text.lower()
    resume_lower = resume_text.lower()

    required: list[str] = []
    for skill, pat in _SKILL_PATTERNS.items():
        if pat.search(jd_lower):
            required.append(skill)

    if not required:
        return 0.5, [], []   # neutral if JD has no recognised skills

    matched = [s for s in required if _SKILL_PATTERNS[s].search(resume_lower)]
    missing = [s for s in required if s not in matched]

    score = len(matched) / len(required)
    # Sort for display: matched descending by length (more specific first)
    matched.sort(key=len, reverse=True)
    missing.sort(key=len, reverse=True)
    return score, matched, missing


def _hybrid(cosine: float, kw: float) -> float:
    return round(0.4 * _normalize_embedding(cosine) + 0.6 * kw, 4)


# ─── DB + cache helpers ───────────────────────────────────────────────────────

def load_resumes_from_db(db) -> int:
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
    import pdfplumber
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


# ─── Main entry point ─────────────────────────────────────────────────────────

def match_resume(job: JobData, db=None) -> Optional[ResumeMatch]:
    """
    1. Reload all resumes from DB.
    2. Pick best resume by embedding cosine similarity.
    3. Compute hybrid score (embedding + keyword overlap) for every resume.
    4. Return ResumeMatch with hybrid score, matched skills, missing skills.
    """
    if db is not None:
        load_resumes_from_db(db)

    if not _resume_cache:
        logger.warning("No resumes in cache — skipping resume matching")
        return None

    job_text = _build_job_query(job)
    job_embedding = encode(job_text)

    # Step 1: pick best resume by raw cosine (embedding is best for selection)
    best_name: Optional[str] = None
    best_cosine = -1.0
    best_text = ""
    cosines: dict[str, float] = {}

    for name, (text, embedding) in _resume_cache.items():
        cosine = cosine_similarity(job_embedding, embedding)
        cosines[name] = cosine
        if cosine > best_cosine:
            best_cosine = cosine
            best_name = name
            best_text = text

    if best_name is None:
        return None

    # Step 2: keyword score for best resume (gives matched/missing lists)
    kw_score, matched, missing = _keyword_score(best_text, job_text)

    # Step 3: hybrid scores for ALL resumes (for display in extension)
    all_scores: dict[str, float] = {}
    for name, cosine in cosines.items():
        if name == best_name:
            all_scores[name] = _hybrid(cosine, kw_score)
        else:
            # Cheap keyword score for other resumes too
            other_text = _resume_cache[name][0]
            other_kw, _, _ = _keyword_score(other_text, job_text)
            all_scores[name] = _hybrid(cosine, other_kw)

    final_score = all_scores[best_name]

    logger.info(
        f"Hybrid scores: {all_scores} → best='{best_name}' ({final_score:.0%}) "
        f"[cosine={best_cosine:.3f}, kw={kw_score:.2f}] "
        f"threshold={settings.match_score_threshold:.0%}"
    )

    return ResumeMatch(
        resume_name=best_name,
        resume_path=f"db:{best_name}",
        score=final_score,
        resume_text_snippet=best_text[:500],
        all_scores=all_scores,
        matched_skills=matched[:20],   # cap for response size
        missing_skills=missing[:15],
    )


def reload_resumes(db) -> int:
    return load_resumes_from_db(db)

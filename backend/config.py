from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── AI providers ──────────────────────────────────────────────────────────
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    groq_api_key:   str = Field(default="", alias="GROQ_API_KEY")

    # ── Contact discovery ─────────────────────────────────────────────────────
    hunter_api_key: str = Field(default="", alias="HUNTER_API_KEY")

    # ── Security ──────────────────────────────────────────────────────────────
    api_key: str = Field(default="", alias="API_KEY")   # if set, all write endpoints require X-Api-Key header

    # ── Storage ───────────────────────────────────────────────────────────────
    db_path:     str = Field(default="backend/storage/jobs.db", alias="DB_PATH")
    resumes_dir: str = Field(default="backend/resumes",         alias="RESUMES_DIR")

    # ── Agent settings ────────────────────────────────────────────────────────
    match_score_threshold: float = Field(default=0.50, alias="MATCH_SCORE_THRESHOLD")
    followup_day_1:        int   = Field(default=7,    alias="FOLLOWUP_DAY_1")
    followup_day_2:        int   = Field(default=14,   alias="FOLLOWUP_DAY_2")
    scheduler_timezone:    str   = Field(default="America/New_York", alias="SCHEDULER_TIMEZONE")

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()

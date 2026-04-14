from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AI providers
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    # Gmail
    gmail_credentials_path: str = Field(default="backend/credentials.json", alias="GMAIL_CREDENTIALS_PATH")
    gmail_token_path: str = Field(default="backend/token.json", alias="GMAIL_TOKEN_PATH")
    gmail_sender_email: str = Field(default="", alias="GMAIL_SENDER_EMAIL")

    # Optional integrations
    hunter_api_key: str = Field(default="", alias="HUNTER_API_KEY")
    notion_token: str = Field(default="", alias="NOTION_TOKEN")
    notion_database_id: str = Field(default="", alias="NOTION_DATABASE_ID")

    # Storage
    db_path: str = Field(default="backend/storage/jobs.db", alias="DB_PATH")
    resumes_dir: str = Field(default="backend/resumes", alias="RESUMES_DIR")

    # Agent thresholds
    match_score_threshold: float = Field(default=0.70, alias="MATCH_SCORE_THRESHOLD")
    followup_day_1: int = Field(default=7, alias="FOLLOWUP_DAY_1")
    followup_day_2: int = Field(default=14, alias="FOLLOWUP_DAY_2")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./dev.db"

    # GitHub OAuth
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_WEBHOOK_SECRET: str = "dev_webhook_secret"

    # Session
    SECRET_KEY: str = "dev_secret_key_change_in_production"

    # AI
    AI_PROVIDER: str = "anthropic"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # App
    APP_URL: str = "http://localhost:8000"
    AUTO_COMMIT_DOCS: bool = False
    DOCS_BRANCH: str = "ai-docs"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (SQLite)
    DATABASE_URL: str = "sqlite+aiosqlite:///./collab_editor.db"

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # AI - default provider when user doesn't specify
    AI_DEFAULT_PROVIDER: str = "ollama"  # openai | claude | ollama

    # OpenAI (user can override via request)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Anthropic / Claude (user can override via request)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"

    # Ollama (local, free)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:8b"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

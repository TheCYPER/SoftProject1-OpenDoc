from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database (SQLite)
    DATABASE_URL: str = "sqlite+aiosqlite:///./collab_editor.db"

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # WebSocket — lifecycle tuning
    WS_IDLE_TIMEOUT_SECONDS: int = 60  # close a silent client after this many seconds
    WS_PERSIST_INTERVAL_UPDATES: int = 50  # flush yjs_state to DB every N applied updates

    # AI - default provider when user doesn't specify
    AI_DEFAULT_PROVIDER: str = "ollama"  # openai | groq | claude | ollama

    # OpenAI (user can override via request)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Groq (OpenAI-compatible API)
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Anthropic / Claude (user can override via request)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"

    # Ollama (local, free)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:8b"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "false"}:
        return normalized == "true"
    return default


@dataclass
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://permaneco@localhost:5432/permaneco",
    )
    demo_mode: bool = _env_bool("DEMO_MODE", False)
    cookie_secure: bool = _env_bool("COOKIE_SECURE", True)
    session_ttl_hours: int = int(os.getenv("SESSION_TTL_HOURS", "12"))
    login_lock_minutes: int = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
    demo_password: str = os.getenv("DEMO_PASSWORD", "")
    retention_days: int = int(os.getenv("RETENTION_DAYS", "90"))
    max_daily_tokens_per_student: int = int(os.getenv("MAX_DAILY_TOKENS_PER_STUDENT", "25000"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model_main: str = os.getenv("LLM_MODEL_MAIN", "gemini-3.6-flash")
    llm_model_fast: str = os.getenv("LLM_MODEL_FAST", "gemini-3.5-flash-lite")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    allowed_link_domains: tuple[str, ...] = tuple(
        domain.strip().lower()
        for domain in os.getenv("ALLOWED_LINK_DOMAINS", "cvv.org.br,gov.br,example.com").split(",")
        if domain.strip()
    )


settings = Settings()

"""
Application configuration loaded exclusively from environment variables.
DATABASE_URL and GROQ_API_KEY are mandatory — the app raises a clear
startup error if either is absent.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, ValidationError
import sys


class Settings(BaseSettings):
    # --- Required (no default — absence causes explicit startup failure) ---
    DATABASE_URL: str
    GROQ_API_KEY: str

    # --- Optional with sensible defaults ---
    LOG_LEVEL: str = "INFO"
    MAX_UPLOAD_PAGES: int = 3
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def database_url_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "DATABASE_URL must not be empty. "
                "Set it to a valid postgresql:// connection string."
            )
        return v

    @field_validator("GROQ_API_KEY")
    @classmethod
    def groq_api_key_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "GROQ_API_KEY must not be empty. "
                "Obtain a key from https://console.groq.com and set it in .env."
            )
        return v


def _load_settings() -> Settings:
    """Load and validate settings, exiting with a readable message on failure."""
    try:
        return Settings()
    except ValidationError as exc:
        missing = []
        for err in exc.errors():
            field = " -> ".join(str(loc) for loc in err["loc"])
            msg = err["msg"]
            missing.append(f"  • {field}: {msg}")
        print(
            "\n[STARTUP ERROR] Required environment variables are missing or invalid:\n"
            + "\n".join(missing)
            + "\n\nCopy .env.example to .env and fill in the required values.\n",
            file=sys.stderr,
        )
        sys.exit(1)


settings = _load_settings()

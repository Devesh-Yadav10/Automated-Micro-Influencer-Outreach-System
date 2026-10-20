"""Application configuration management with environment variable loading."""

import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    # Load environment variables from .env if present
    load_dotenv(override=False)
except ImportError:
    pass


class Settings:
    """Centralized application settings with safe defaults and secret protection."""

    def __init__(self) -> None:
        self.BASE_DIR: Path = Path(__file__).resolve().parent.parent
        self.APP_ENV: str = os.getenv("APP_ENV", "development").lower()
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

        default_db = str(self.BASE_DIR / "data" / "micro_influencer.db")
        self.DATABASE_PATH: str = os.getenv("DATABASE_PATH", default_db)

        # Outreach defaults strictly to simulation to prevent unintended dispatches
        self.OUTREACH_MODE: str = os.getenv("OUTREACH_MODE", "simulation").lower()

        self.YOUTUBE_API_KEY: Optional[str] = os.getenv("YOUTUBE_API_KEY") or None

        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "fallback").lower()
        self.GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY") or None
        self.OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY") or None

        self.SMTP_HOST: str = os.getenv("SMTP_HOST", "")
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
        self.SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
        self.SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "outreach-simulation@example.com")

    @property
    def is_simulation_mode(self) -> bool:
        """Return True if outreach mode is configured for simulation."""
        return self.OUTREACH_MODE != "live_smtp"

    @property
    def is_development(self) -> bool:
        """Return True if running in development mode."""
        return self.APP_ENV in {"development", "dev", "local"}

    def get_db_path(self) -> Path:
        """Get resolved Path object for SQLite database."""
        path = Path(self.DATABASE_PATH)
        if not path.is_absolute():
            path = self.BASE_DIR / path
        return path

    @staticmethod
    def _mask_secret(value: Optional[str]) -> str:
        """Mask secrets so they are never exposed in logs or console output."""
        if not value:
            return "<not set>"
        if len(value) <= 6:
            return "***"
        return f"{value[:3]}...{value[-3:]}"

    def safe_dict(self) -> dict:
        """Return configuration dictionary with all sensitive credentials masked."""
        return {
            "APP_ENV": self.APP_ENV,
            "LOG_LEVEL": self.LOG_LEVEL,
            "DATABASE_PATH": str(self.get_db_path()),
            "OUTREACH_MODE": self.OUTREACH_MODE,
            "IS_SIMULATION": self.is_simulation_mode,
            "YOUTUBE_API_KEY": self._mask_secret(self.YOUTUBE_API_KEY),
            "LLM_PROVIDER": self.LLM_PROVIDER,
            "GEMINI_API_KEY": self._mask_secret(self.GEMINI_API_KEY),
            "OPENAI_API_KEY": self._mask_secret(self.OPENAI_API_KEY),
            "SMTP_HOST": self.SMTP_HOST or "<not set>",
            "SMTP_PORT": self.SMTP_PORT,
            "SMTP_USERNAME": self._mask_secret(self.SMTP_USERNAME) if self.SMTP_USERNAME else "<not set>",
            "SMTP_PASSWORD": "***" if self.SMTP_PASSWORD else "<not set>",
            "SENDER_EMAIL": self.SENDER_EMAIL,
        }

    def __repr__(self) -> str:
        return f"Settings({self.safe_dict()})"


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


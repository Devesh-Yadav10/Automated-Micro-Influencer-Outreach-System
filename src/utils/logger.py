"""Application-wide structured logging utility."""

import logging
import re
import sys
from typing import Optional

# Sensitive patterns that should never be logged in plain text
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{6,})['\"]?"),
]


class SecretMaskingFormatter(logging.Formatter):
    """Custom formatter that automatically masks API keys and credentials."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        masked = original
        for pattern in SENSITIVE_PATTERNS:
            masked = pattern.sub(r"\1=***", masked)
        return masked


def setup_logger(
    name: str = "influencer_outreach",
    level: Optional[str] = None,
) -> logging.Logger:
    """Configure and return a structured logger with secret masking."""
    logger = logging.getLogger(name)

    if level is None:
        from config.settings import get_settings
        level = get_settings().LOG_LEVEL

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)

        formatter = SecretMaskingFormatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def get_logger(name: str = "influencer_outreach") -> logging.Logger:
    """Get an existing logger or create one with default settings."""
    return setup_logger(name)


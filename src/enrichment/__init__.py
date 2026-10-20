"""Profile enrichment package."""

from src.enrichment.extractor import (
    extract_email_from_text,
    extract_themes_from_text,
)

__all__ = ["extract_email_from_text", "extract_themes_from_text"]


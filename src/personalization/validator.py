"""Validation utilities and strict word count checkers for outreach messages."""

import re
from typing import Optional, Tuple

from src.validation.models import InfluencerProfile

# Constraints per assignment specification
MIN_EMAIL_WORDS = 60
MAX_EMAIL_WORDS = 90

MIN_DM_WORDS = 15
MAX_DM_WORDS = 30


def count_words(text: Optional[str]) -> int:
    """
    Count words accurately by splitting on whitespace and ignoring pure punctuation tokens.
    """
    if not text or not isinstance(text, str):
        return 0

    clean = text.strip()
    if not clean:
        return 0

    # Split on whitespace
    tokens = clean.split()
    # Filter out empty tokens or tokens that are just symbols (like '---' or '***')
    words = [t for t in tokens if re.search(r"\w", t)]
    return len(words)


def validate_email_pitch(text: Optional[str]) -> Tuple[bool, str, int]:
    """
    Validate that an email pitch meets the 60–90 word count requirement.
    Returns: (is_valid: bool, reason: str, word_count: int)
    """
    wc = count_words(text)
    if wc == 0:
        return False, "Email pitch message is empty.", 0
    if wc < MIN_EMAIL_WORDS:
        return (
            False,
            f"Email pitch has {wc} words, which is below the minimum required of {MIN_EMAIL_WORDS} words.",
            wc,
        )
    if wc > MAX_EMAIL_WORDS:
        return (
            False,
            f"Email pitch has {wc} words, which exceeds the maximum allowed of {MAX_EMAIL_WORDS} words.",
            wc,
        )
    return True, f"Email pitch meets length requirements ({wc} words).", wc


def validate_instagram_dm(text: Optional[str]) -> Tuple[bool, str, int]:
    """
    Validate that an Instagram DM meets the 15–30 word count requirement.
    Returns: (is_valid: bool, reason: str, word_count: int)
    """
    wc = count_words(text)
    if wc == 0:
        return False, "Instagram DM message is empty.", 0
    if wc < MIN_DM_WORDS:
        return (
            False,
            f"Instagram DM has {wc} words, which is below the minimum required of {MIN_DM_WORDS} words.",
            wc,
        )
    if wc > MAX_DM_WORDS:
        return (
            False,
            f"Instagram DM has {wc} words, which exceeds the maximum allowed of {MAX_DM_WORDS} words.",
            wc,
        )
    return True, f"Instagram DM meets length requirements ({wc} words).", wc


def check_personalization_evidence(text: str, profile: InfluencerProfile) -> Tuple[bool, str]:
    """
    Verify that the message references real profile data (creator name, handle, themes, or niche).
    """
    if not text:
        return False, "Empty message body."

    text_lower = text.lower()
    first_name = profile.name.split()[0].lower() if profile.name else ""

    # Check for creator name/handle
    has_name = (
        (first_name and first_name in text_lower)
        or (profile.handle and profile.handle.lower().lstrip("@") in text_lower)
        or profile.name.lower() in text_lower
    )

    # Check for themes or niche keywords
    theme_matches = [t for t in profile.content_themes if t.lower() in text_lower]
    has_theme_or_niche = bool(theme_matches) or any(
        kw in text_lower for kw in ["ai", "python", "machine learning", "data", "engineering", "tech"]
    )

    if not has_name and not has_theme_or_niche:
        return False, "Message does not reference creator name or relevant niche themes."

    return True, "Message contains verified creator references."


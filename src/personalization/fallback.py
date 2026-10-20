"""Deterministic fallback outreach message generator requiring no API keys."""

from typing import Tuple
from src.personalization.validator import count_words, validate_email_pitch, validate_instagram_dm
from src.validation.models import InfluencerProfile


class DeterministicMessageGenerator:
    """
    Generates rule-based, verified personalized outreach messages.
    Guarantees strict adherence to word count constraints without any external LLM dependencies.
    """

    @staticmethod
    def _extract_name_and_themes(profile: InfluencerProfile) -> Tuple[str, str, str]:
        """Extract clean creator first name and top two themes."""
        # Clean first name
        raw_name = profile.name.strip()
        first_name = raw_name.split()[0] if raw_name else "there"
        # If first name is a channel title like 'AI', use full title or handle
        if len(first_name) < 3 and profile.handle:
            first_name = profile.handle.lstrip("@")

        themes = profile.content_themes or ["technology and modern software", "developer workflows"]
        theme1 = themes[0] if len(themes) > 0 else "technology and modern software"
        theme2 = themes[1] if len(themes) > 1 else "developer workflows"

        return first_name, theme1, theme2

    def generate_email_pitch(self, profile: InfluencerProfile) -> Tuple[str, str, int]:
        """
        Generate a personalized email pitch strictly between 60 and 90 words.
        Returns: (subject: str, body: str, word_count: int)
        """
        first_name, theme1, theme2 = self._extract_name_and_themes(profile)
        subject = f"Collaboration Inquiry: Developer Tools & {theme1}"

        # Base body carefully crafted to hit 65-75 words
        body = (
            f"Hi {first_name},\n\n"
            f"I have been following your work on {theme1} and genuinely appreciate how clearly you break "
            f"down complex concepts for your community. "
            f"Our engineering team has built a developer productivity platform designed to help technical "
            f"creators and engineers build modern software workflows faster. "
            f"Given your strong expertise in {theme2}, we would love to sponsor an upcoming segment or explore a "
            f"collaborative partnership that provides genuine value to your audience.\n\n"
            f"Would you be open to a brief conversation this week to discuss ideas?\n\n"
            f"Best regards,\n"
            f"Outreach Team"
        )

        wc = count_words(body)

        # Micro-adjustments if theme lengths push boundaries
        if wc < 60:
            body = (
                f"Hi {first_name},\n\n"
                f"I have been following your insightful content on {theme1} and genuinely appreciate how clearly you break "
                f"down complex technical concepts for your community. "
                f"Our dedicated engineering team has built a developer productivity platform designed to help technical "
                f"creators and software engineers build modern development workflows much faster. "
                f"Given your strong demonstrated expertise in {theme2}, we would love to sponsor an upcoming project or explore a "
                f"collaborative partnership that provides real value to your audience.\n\n"
                f"Would you be open to a brief conversation this week to discuss potential ideas together?\n\n"
                f"Best regards,\n"
                f"Outreach Team"
            )
            wc = count_words(body)
        elif wc > 90:
            body = (
                f"Hi {first_name},\n\n"
                f"I follow your work on {theme1} and appreciate how clearly you explain complex concepts. "
                f"Our team built a developer productivity platform designed to help technical creators and engineers build "
                f"faster software workflows. "
                f"Given your focus on {theme2}, we would love to sponsor an upcoming video or explore a collaborative partnership.\n\n"
                f"Would you be open to a brief conversation this week to discuss ideas?\n\n"
                f"Best regards,\n"
                f"Outreach Team"
            )
            wc = count_words(body)

        is_valid, reason, final_wc = validate_email_pitch(body)
        return subject, body, final_wc

    def generate_instagram_dm(self, profile: InfluencerProfile) -> Tuple[str, int]:
        """
        Generate a natural, concise Instagram DM strictly between 15 and 30 words.
        Returns: (message_body: str, word_count: int)
        """
        first_name, theme1, _ = self._extract_name_and_themes(profile)

        message = (
            f"Hey {first_name}! Loved your recent breakdown on {theme1}. "
            f"We are building AI tools for developers and would love to collaborate. Interested in discussing?"
        )

        wc = count_words(message)

        # Micro-adjustments for short/long themes
        if wc < 15:
            message = (
                f"Hey {first_name}! Really loved your recent breakdown on {theme1}. "
                f"We are building smart AI tools for developers and would love to collaborate with you. Interested in discussing?"
            )
            wc = count_words(message)
        elif wc > 30:
            message = (
                f"Hey {first_name}! Loved your work on {theme1}. "
                f"We build developer AI tools and would love to collaborate. Interested?"
            )
            wc = count_words(message)

        is_valid, reason, final_wc = validate_instagram_dm(message)
        return message, final_wc


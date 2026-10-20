"""LLM client integration with seamless deterministic fallback for outreach generation."""

from typing import Any, Dict, Optional

from config.settings import get_settings
from src.personalization.fallback import DeterministicMessageGenerator
from src.personalization.prompts import SYSTEM_PROMPT, build_dm_prompt, build_email_prompt
from src.personalization.validator import (
    validate_email_pitch,
    validate_instagram_dm,
)
from src.storage.database import DatabaseManager
from src.utils.logger import get_logger
from src.validation.models import InfluencerProfile

logger = get_logger("personalization.engine")


class PersonalizationEngine:
    """
    Orchestrates outreach message generation.
    Supports optional LLM providers (Gemini / OpenAI) with automatic, guaranteed fallback
    to the deterministic generator when credentials are not configured or responses fail validation.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.db = db
        settings = get_settings()
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        self.api_key = api_key or (
            settings.GEMINI_API_KEY if self.provider == "gemini" else settings.OPENAI_API_KEY
        )
        self.fallback_generator = DeterministicMessageGenerator()

    def generate_messages(
        self,
        profile: InfluencerProfile,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate both an Email Pitch (60–90 words) and an Instagram DM (15–30 words)
        for a qualified influencer profile.
        """
        # Try generating via LLM if provider and credentials are configured
        email_data = None
        dm_data = None

        if self.provider != "fallback" and self.api_key:
            try:
                email_data = self._generate_email_llm(profile)
            except Exception as e:
                logger.warning(f"LLM email generation failed for {profile.name}: {e}. Using fallback.")

            try:
                dm_data = self._generate_dm_llm(profile)
            except Exception as e:
                logger.warning(f"LLM DM generation failed for {profile.name}: {e}. Using fallback.")

        # If LLM generation didn't succeed or wasn't configured, use deterministic fallback
        if not email_data:
            subj, body, wc = self.fallback_generator.generate_email_pitch(profile)
            email_data = {
                "subject": subj,
                "body": body,
                "word_count": wc,
                "is_valid": True,
                "generation_method": "deterministic_fallback",
            }

        if not dm_data:
            body, wc = self.fallback_generator.generate_instagram_dm(profile)
            dm_data = {
                "body": body,
                "word_count": wc,
                "is_valid": True,
                "generation_method": "deterministic_fallback",
            }

        # Persist to database if requested
        if persist and self.db:
            self.db.save_generated_message(
                influencer_id=profile.id,
                channel="email",
                subject=email_data["subject"],
                message_body=email_data["body"],
                word_count=email_data["word_count"],
                generation_method=email_data["generation_method"],
                status="DRAFT",
            )
            self.db.save_generated_message(
                influencer_id=profile.id,
                channel="instagram_dm",
                subject="Instagram DM",
                message_body=dm_data["body"],
                word_count=dm_data["word_count"],
                generation_method=dm_data["generation_method"],
                status="DRAFT",
            )

        return {
            "influencer_id": profile.id,
            "creator_name": profile.name,
            "email": email_data,
            "instagram_dm": dm_data,
        }

    def _generate_email_llm(self, profile: InfluencerProfile) -> Optional[Dict[str, Any]]:
        """Call configured LLM to generate email pitch with retry and validation."""
        prompt = build_email_prompt(profile)
        raw_output = self._call_llm_api(prompt)
        if not raw_output:
            return None

        # Parse subject and body
        subject = f"Collaboration with {profile.name}: Developer Intelligence Platform"
        body = raw_output.strip()

        lines = raw_output.strip().splitlines()
        for i, line in enumerate(lines):
            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                body = "\n".join(lines[i + 1 :]).strip()
                break

        is_valid, reason, wc = validate_email_pitch(body)
        if not is_valid:
            logger.warning(f"LLM email failed word count validation ({wc} words): {reason}")
            return None

        return {
            "subject": subject,
            "body": body,
            "word_count": wc,
            "is_valid": True,
            "generation_method": f"llm_{self.provider}",
        }

    def _generate_dm_llm(self, profile: InfluencerProfile) -> Optional[Dict[str, Any]]:
        """Call configured LLM to generate Instagram DM with validation."""
        prompt = build_dm_prompt(profile)
        raw_output = self._call_llm_api(prompt)
        if not raw_output:
            return None

        body = raw_output.strip().strip('"').strip("'")
        is_valid, reason, wc = validate_instagram_dm(body)
        if not is_valid:
            logger.warning(f"LLM DM failed word count validation ({wc} words): {reason}")
            return None

        return {
            "body": body,
            "word_count": wc,
            "is_valid": True,
            "generation_method": f"llm_{self.provider}",
        }

    def _call_llm_api(self, prompt: str) -> Optional[str]:
        """Call external LLM API (Google GenAI or OpenAI) based on provider setting."""
        if self.provider == "gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                return None
        elif self.provider == "openai":
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                )
                return resp.choices[0].message.content
            except Exception as e:
                logger.error(f"OpenAI API call failed: {e}")
                return None
        return None


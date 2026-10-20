"""Prompt templates and system guidelines for outreach message generation."""

from src.validation.models import InfluencerProfile

SYSTEM_PROMPT = """You are an AI Outreach Specialist for an innovative developer tooling and AI productivity platform.
Your task is to write highly personalized, authentic outreach messages to creators based strictly on their verified public profile data.

Strict Constraints:
1. NEVER invent or fabricate videos, blog posts, personal interests, audience statistics, demographic details, or prior relationships.
2. Only reference their verified name, niche, listed content themes, and public bio.
3. For Email Collaboration Pitches:
   - Must be STRICTLY between 60 and 90 words (excluding the subject line).
   - Must include a concise, compelling subject line (e.g. Subject: Partnership inquiry with [Name]).
   - Must clearly propose a mutual collaboration or sponsorship value proposition.
   - Tone: Professional, appreciative, and concise.
4. For Instagram DMs:
   - Must be STRICTLY between 15 and 30 words.
   - Tone: Natural, friendly, direct, and tailored to their niche.
5. Do not include placeholders like '[Insert Video Name]' or '[Company Name]'. Use 'our developer intelligence platform'.
"""


def build_email_prompt(profile: InfluencerProfile) -> str:
    """Build user prompt for email collaboration pitch (60–90 words)."""
    themes_str = ", ".join(profile.content_themes) if profile.content_themes else "Technology & AI"
    bio_snippet = f"Bio: {profile.bio[:200]}" if profile.bio else "Bio: Not provided"

    return f"""Please draft a personalized email collaboration pitch to the following creator:
- Creator Name: {profile.name}
- Platform: {profile.platform.capitalize()}
- Handle: {profile.handle or 'N/A'}
- Niche: {profile.niche}
- Verified Content Themes: {themes_str}
- {bio_snippet}

Output Format:
Subject: <Compelling Subject Line>

<Email Body strictly 60 to 90 words>

Ensure the body word count is exactly between 60 and 90 words. Count words carefully.
"""


def build_dm_prompt(profile: InfluencerProfile) -> str:
    """Build user prompt for Instagram DM (15–30 words)."""
    themes_str = ", ".join(profile.content_themes[:2]) if profile.content_themes else "tech projects"

    return f"""Please draft a natural, concise Instagram DM to the following creator:
- Creator Name: {profile.name}
- Handle: {profile.handle or 'N/A'}
- Primary Focus: {themes_str}

Output Format:
<DM message strictly 15 to 30 words>

Ensure the word count is strictly between 15 and 30 words.
"""


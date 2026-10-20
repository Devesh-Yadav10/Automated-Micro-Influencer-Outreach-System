"""Configurable filtering rules for micro-influencer qualification and audit trails."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from src.validation.models import InfluencerProfile


class RuleDecision(str, Enum):
    """Evaluation status for an individual rule check."""
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class RuleResult:
    """Individual rule evaluation output containing reason and metric snapshot."""
    rule_name: str
    decision: RuleDecision
    reason: str
    metrics: Dict[str, Any]


class MicroInfluencerTierRule:
    """
    Evaluates whether the influencer's audience size conforms to the micro-influencer tier.
    Default range: 5,000 to 100,000 subscribers/followers inclusive.
    """

    def __init__(self, min_followers: int = 5000, max_followers: int = 100000) -> None:
        self.min_followers = min_followers
        self.max_followers = max_followers

    def evaluate(self, profile: InfluencerProfile) -> RuleResult:
        follower_count = profile.follower_count

        # Check for unknown / hidden audience flags
        if (
            follower_count == 0
            and profile.verification_status in {"hidden_subscribers", "unknown_audience"}
        ):
            return RuleResult(
                rule_name="MicroInfluencerTier",
                decision=RuleDecision.NEEDS_REVIEW,
                reason="Audience size is hidden or unknown; cannot verify micro-tier qualification.",
                metrics={"follower_count": None, "verification_status": profile.verification_status},
            )

        if follower_count < self.min_followers:
            return RuleResult(
                rule_name="MicroInfluencerTier",
                decision=RuleDecision.FAIL,
                reason=(
                    f"Follower count {follower_count:,} is below the micro-tier threshold "
                    f"of {self.min_followers:,}."
                ),
                metrics={
                    "follower_count": follower_count,
                    "min_followers": self.min_followers,
                    "max_followers": self.max_followers,
                },
            )

        if follower_count > self.max_followers:
            return RuleResult(
                rule_name="MicroInfluencerTier",
                decision=RuleDecision.FAIL,
                reason=(
                    f"Follower count {follower_count:,} exceeds the micro-tier threshold "
                    f"of {self.max_followers:,} (macro/mega influencer tier)."
                ),
                metrics={
                    "follower_count": follower_count,
                    "min_followers": self.min_followers,
                    "max_followers": self.max_followers,
                },
            )

        return RuleResult(
            rule_name="MicroInfluencerTier",
            decision=RuleDecision.PASS,
            reason=(
                f"Follower count {follower_count:,} is within the micro-tier range "
                f"({self.min_followers:,}–{self.max_followers:,})."
            ),
            metrics={
                "follower_count": follower_count,
                "min_followers": self.min_followers,
                "max_followers": self.max_followers,
            },
        )


class NicheRelevanceRule:
    """
    Evaluates whether the creator's profile description and content themes support
    the designated target category (e.g. Technology / AI / Machine Learning).
    Transparent keyword and theme matching; never relies solely on handles.
    """

    TECH_AI_KEYWORDS = [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "python", "data science", "neural network", "llm", "large language model",
        "agents", "nlp", "computer vision", "robotics", "mlops", "transformers",
        "pytorch", "tensorflow", "opencv", "scikit-learn", "coding", "software engineering",
        "data analysis", "prompt engineering", "langchain", "vector database",
    ]

    def __init__(
        self,
        target_niche: str = "Technology / AI / Machine Learning",
        custom_keywords: Optional[List[str]] = None,
    ) -> None:
        self.target_niche = target_niche
        self.keywords = custom_keywords or self.TECH_AI_KEYWORDS

    def evaluate(self, profile: InfluencerProfile) -> RuleResult:
        # Check if the creator's declared niche aligns with target niche
        target_tokens = [t.strip().lower() for t in self.target_niche.split("/") if t.strip()]
        profile_niche_lower = profile.niche.lower()

        niche_matches = (
            self.target_niche.lower() in profile_niche_lower
            or profile_niche_lower in self.target_niche.lower()
            or any(t in profile_niche_lower for t in target_tokens)
            or any(t in profile_niche_lower for t in ["technology", "ai", "machine learning", "tech"])
        )

        if not niche_matches:
            return RuleResult(
                rule_name="NicheRelevance",
                decision=RuleDecision.FAIL,
                reason=(
                    f"Profile declared niche '{profile.niche}' does not match "
                    f"target category '{self.target_niche}'."
                ),
                metrics={
                    "target_niche": self.target_niche,
                    "profile_niche": profile.niche,
                    "matched_keywords": [],
                    "content_themes": profile.content_themes,
                },
            )

        # Match content themes and bio as supporting evidence
        combined_text = f"{' '.join(profile.content_themes)} {profile.bio or ''}".lower()
        matched_keywords = []
        for kw in self.keywords:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, combined_text):
                matched_keywords.append(kw)

        if not matched_keywords and not profile.content_themes and not profile.bio:
            return RuleResult(
                rule_name="NicheRelevance",
                decision=RuleDecision.NEEDS_REVIEW,
                reason=(
                    f"Stated niche mentions '{profile.niche}', but insufficient content description "
                    f"or themes are available to substantiate relevance."
                ),
                metrics={
                    "target_niche": self.target_niche,
                    "profile_niche": profile.niche,
                    "matched_keywords": [],
                },
            )

        return RuleResult(
            rule_name="NicheRelevance",
            decision=RuleDecision.PASS,
            reason=(
                f"Content aligns with '{self.target_niche}' supported by keywords/themes: "
                f"{', '.join(matched_keywords[:5]) or 'Stated niche alignment'}."
            ),
            metrics={
                "target_niche": self.target_niche,
                "profile_niche": profile.niche,
                "matched_keywords": matched_keywords[:8],
                "content_themes": profile.content_themes,
            },
        )


class EngagementRateRule:
    """
    Evaluates recent video engagement rate proxy against a configurable minimum threshold.

    Integrity Safeguards:
    - If minimum threshold is not configured (None), passes without imposing restrictions.
    - If minimum threshold is set and engagement is known: evaluates against threshold.
    - If minimum threshold is set but engagement is unknown (None): returns NEEDS_REVIEW
      (missing evidence) rather than failing as zero.
    """

    def __init__(self, min_engagement_rate: Optional[float] = None) -> None:
        self.min_engagement_rate = min_engagement_rate

    def evaluate(self, profile: InfluencerProfile) -> RuleResult:
        if self.min_engagement_rate is None:
            return RuleResult(
                rule_name="EngagementRate",
                decision=RuleDecision.PASS,
                reason="No minimum engagement rate threshold enforced (unconstrained).",
                metrics={
                    "engagement_rate": profile.engagement_rate,
                    "min_engagement_rate": None,
                    "measurement_method": "YouTube recent-video proxy (likes+comments)/views",
                },
            )

        if profile.engagement_rate is None:
            return RuleResult(
                rule_name="EngagementRate",
                decision=RuleDecision.NEEDS_REVIEW,
                reason=(
                    f"Engagement rate is unknown; requires verification against the "
                    f"minimum threshold of {self.min_engagement_rate}%."
                ),
                metrics={
                    "engagement_rate": None,
                    "min_engagement_rate": self.min_engagement_rate,
                    "measurement_method": "Unknown / Insufficient public data",
                },
            )

        if profile.engagement_rate < self.min_engagement_rate:
            return RuleResult(
                rule_name="EngagementRate",
                decision=RuleDecision.FAIL,
                reason=(
                    f"Recent video engagement proxy of {profile.engagement_rate}% is below "
                    f"the minimum threshold of {self.min_engagement_rate}%."
                ),
                metrics={
                    "engagement_rate": profile.engagement_rate,
                    "min_engagement_rate": self.min_engagement_rate,
                    "measurement_method": "YouTube recent-video proxy (likes+comments)/views",
                },
            )

        return RuleResult(
            rule_name="EngagementRate",
            decision=RuleDecision.PASS,
            reason=(
                f"Recent video engagement proxy of {profile.engagement_rate}% meets or "
                f"exceeds the minimum threshold of {self.min_engagement_rate}%."
            ),
            metrics={
                "engagement_rate": profile.engagement_rate,
                "min_engagement_rate": self.min_engagement_rate,
                "measurement_method": "YouTube recent-video proxy (likes+comments)/views",
            },
        )


class DataQualityRule:
    """
    Validates data integrity, URL correctness, and source provenance.
    Notes contact email availability without automatically disqualifying missing emails.
    """

    def evaluate(self, profile: InfluencerProfile) -> RuleResult:
        # Validate profile URL
        parsed_profile = urlparse(profile.profile_url)
        if not (parsed_profile.scheme in {"http", "https"} and parsed_profile.netloc):
            return RuleResult(
                rule_name="DataQuality",
                decision=RuleDecision.FAIL,
                reason=f"Profile URL '{profile.profile_url}' is missing or malformed.",
                metrics={"profile_url": profile.profile_url, "source_url": profile.source_url},
            )

        # Validate source URL provenance
        if not profile.source_url or profile.source_url.strip() in {"", "unknown"}:
            return RuleResult(
                rule_name="DataQuality",
                decision=RuleDecision.NEEDS_REVIEW,
                reason="Insufficient data provenance: collection source URL is missing.",
                metrics={"source_url": profile.source_url},
            )

        email_available = profile.contact_email != "Not Found"
        email_note = (
            f"Public business email verified: {profile.contact_email}"
            if email_available
            else "Contact email unavailable ('Not Found'); shortlisted for discovery, alternative outreach (DM) required."
        )

        return RuleResult(
            rule_name="DataQuality",
            decision=RuleDecision.PASS,
            reason=f"Profile URL and source provenance verified. {email_note}",
            metrics={
                "profile_url": profile.profile_url,
                "source_url": profile.source_url,
                "contact_email": profile.contact_email,
                "email_outreach_ready": email_available,
            },
        )

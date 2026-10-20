"""Pydantic data models for influencers, filtering audit logs, and outreach messages."""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


def _current_utc_timestamp() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class InfluencerProfile(BaseModel):
    """Normalized profile schema representing a real discovered micro-influencer."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique internal identifier (UUID4 string)",
    )
    name: str = Field(..., min_length=1, description="Influencer display name or channel title")
    platform: str = Field(..., min_length=1, description="Social platform name, e.g. 'youtube', 'instagram'")
    profile_url: str = Field(..., min_length=1, description="Direct URL to creator profile")
    handle: Optional[str] = Field(default=None, description="Platform username, handle, or channel ID")
    follower_count: int = Field(..., ge=0, description="Follower or subscriber count; must be non-negative")
    engagement_rate: Optional[float] = Field(
        default=None,
        description="Engagement rate as a percentage, e.g. 3.5 represents 3.5%. Must remain None if unknown.",
    )
    niche: str = Field(..., min_length=1, description="Primary niche category, e.g. 'Tech & AI', 'Fitness'")
    content_themes: List[str] = Field(
        default_factory=list,
        description="Identified content topics, tags, or recurring themes",
    )
    contact_email: str = Field(
        default="Not Found",
        description="Contact email address, or 'Not Found' if unavailable",
    )
    bio: Optional[str] = Field(
        default=None,
        description="Public biography, channel description, or profile summary",
    )
    source_url: Optional[str] = Field(
        default=None,
        description="URL or source from which data was collected",
    )
    collected_at: datetime = Field(
        default_factory=_current_utc_timestamp,
        description="Timestamp of data collection (UTC)",
    )
    verification_status: str = Field(
        default="unverified",
        description="Status of profile verification ('verified', 'unverified', 'api_ingested', 'seed')",
    )

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, v: Any) -> str:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if not v_clean:
                raise ValueError("Platform cannot be empty")
            return v_clean
        raise ValueError("Platform must be a string")

    @field_validator("engagement_rate")
    @classmethod
    def validate_engagement_rate(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v < 0.0 or v > 100.0:
            raise ValueError(f"Engagement rate must be between 0.0% and 100.0%, received: {v}")
        return round(float(v), 2)

    @field_validator("contact_email", mode="before")
    @classmethod
    def normalize_contact_email(cls, v: Any) -> str:
        if v is None:
            return "Not Found"
        val = str(v).strip()
        if not val or val.lower() in {"not found", "none", "n/a", "null", "unknown", ""}:
            return "Not Found"
        # Validate format if an actual email is provided
        if not EMAIL_REGEX.match(val):
            raise ValueError(
                f"Contact email '{val}' is not a valid email address. Use 'Not Found' if unavailable."
            )
        return val.lower()

    @property
    def dedup_key(self) -> str:
        """Generate normalized platform-scoped deduplication key."""
        # Use handle if available, otherwise normalized URL path
        identifier = self.handle.strip().lower() if self.handle else ""
        if not identifier:
            parsed = urlparse(self.profile_url)
            identifier = (parsed.netloc + parsed.path).rstrip("/").lower()
        return f"{self.platform}:{identifier}"


class FilteringResult(BaseModel):
    """Audit log record for an influencer evaluation against filtering rules."""

    influencer_id: str = Field(..., description="Foreign key referencing InfluencerProfile.id")
    passed: bool = Field(..., description="Whether the influencer qualified for outreach")
    classification: str = Field(
        default="DISQUALIFIED",
        description="Classification decision: 'QUALIFIED', 'DISQUALIFIED', or 'NEEDS_REVIEW'",
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Detailed human-readable justifications explaining pass or failure",
    )
    filter_criteria_version: str = Field(
        default="v1.0",
        description="Version tag of the filtering rule set applied",
    )
    metrics_evaluated: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of evaluated metrics (e.g. follower_count, engagement_rate, niche)",
    )
    evaluated_at: datetime = Field(
        default_factory=_current_utc_timestamp,
        description="Evaluation timestamp (UTC)",
    )

    def model_post_init(self, __context: Any) -> None:
        """Keep passed and classification synchronized."""
        if self.passed and self.classification == "DISQUALIFIED":
            self.classification = "QUALIFIED"
        elif self.classification == "QUALIFIED":
            self.passed = True
        elif self.classification in {"DISQUALIFIED", "NEEDS_REVIEW"}:
            self.passed = False


class OutreachMessage(BaseModel):
    """Record of an outreach dispatch (email pitch or Instagram DM)."""

    influencer_id: str = Field(..., description="Foreign key referencing InfluencerProfile.id")
    channel: str = Field(..., description="Outreach channel ('email', 'instagram_dm')")
    recipient_contact: str = Field(..., description="Recipient email address or social handle")
    subject: Optional[str] = Field(default=None, description="Email subject line or DM topic")
    message_body: str = Field(..., min_length=1, description="Generated pitch message body")
    status: str = Field(
        default="PENDING",
        description="Dispatch status ('PENDING', 'SIMULATED_SENT', 'SENT', 'FAILED', 'ALREADY_CONTACTED')",
    )
    timestamp: datetime = Field(
        default_factory=_current_utc_timestamp,
        description="Timestamp of outreach attempt (UTC)",
    )
    deduplication_key: Optional[str] = Field(
        default=None,
        description="Key used to prevent re-contacting the same influencer on this channel",
    )

    def model_post_init(self, __context: Any) -> None:
        """Automatically construct deduplication key if not supplied."""
        if not self.deduplication_key:
            channel_norm = self.channel.strip().lower()
            self.deduplication_key = f"{self.influencer_id}:{channel_norm}"

    @field_validator("channel", mode="before")
    @classmethod
    def normalize_channel(cls, v: Any) -> str:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if not v_clean:
                raise ValueError("Channel cannot be empty")
            return v_clean
        raise ValueError("Channel must be a string")


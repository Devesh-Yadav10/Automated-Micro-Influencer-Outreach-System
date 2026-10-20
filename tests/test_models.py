"""Unit tests for Pydantic data models (InfluencerProfile, FilteringResult, OutreachMessage)."""

import pytest
from pydantic import ValidationError
from src.validation.models import (
    FilteringResult,
    InfluencerProfile,
    OutreachMessage,
)


def test_valid_influencer_profile():
    """Verify standard valid influencer profile creation with all fields."""
    profile = InfluencerProfile(
        name="Alex Rivera",
        platform="YouTube",
        profile_url="https://youtube.com/@alexriveratech",
        handle="@alexriveratech",
        follower_count=35000,
        engagement_rate=4.25,
        niche="Tech & AI",
        content_themes=["Python Tutorials", "AI Agents", "Tech Reviews"],
        contact_email="alex@riveramedia.com",
        bio="Software engineer covering emerging AI technologies and workflows.",
        source_url="https://youtube.com/@alexriveratech/about",
    )

    assert profile.name == "Alex Rivera"
    assert profile.platform == "youtube"  # Normalized lowercase
    assert profile.follower_count == 35000
    assert profile.engagement_rate == 4.25
    assert profile.contact_email == "alex@riveramedia.com"
    assert len(profile.content_themes) == 3
    assert profile.dedup_key == "youtube:@alexriveratech"


def test_missing_email_represented_as_not_found():
    """Missing, None, or empty email strings must strictly normalize to 'Not Found'."""
    # When email is omitted / None
    p1 = InfluencerProfile(
        name="Dev Creator",
        platform="instagram",
        profile_url="https://instagram.com/devcreator",
        follower_count=12000,
        niche="Fitness",
        source_url="https://instagram.com/devcreator",
        contact_email=None,
    )
    assert p1.contact_email == "Not Found"

    # When email is whitespace
    p2 = InfluencerProfile(
        name="Dev Creator",
        platform="instagram",
        profile_url="https://instagram.com/devcreator",
        follower_count=12000,
        niche="Fitness",
        source_url="https://instagram.com/devcreator",
        contact_email="   ",
    )
    assert p2.contact_email == "Not Found"

    # When email is literally 'not found' or 'N/A'
    p3 = InfluencerProfile(
        name="Dev Creator",
        platform="instagram",
        profile_url="https://instagram.com/devcreator",
        follower_count=12000,
        niche="Fitness",
        source_url="https://instagram.com/devcreator",
        contact_email="Not Found",
    )
    assert p3.contact_email == "Not Found"


def test_invalid_email_format_rejected():
    """Malformed email strings that are not 'Not Found' should fail validation."""
    with pytest.raises(ValidationError):
        InfluencerProfile(
            name="Dev Creator",
            platform="youtube",
            profile_url="https://youtube.com/@dev",
            follower_count=15000,
            niche="Tech",
            source_url="https://youtube.com/@dev",
            contact_email="invalid-not-an-email",
        )


def test_negative_follower_count_rejected():
    """Follower count must be strictly non-negative."""
    with pytest.raises(ValidationError):
        InfluencerProfile(
            name="Dev Creator",
            platform="youtube",
            profile_url="https://youtube.com/@dev",
            follower_count=-500,
            niche="Tech",
            source_url="https://youtube.com/@dev",
        )


def test_unknown_engagement_rate_preserved_as_none():
    """Missing engagement rate must remain None and never be fabricated or set to 0.0."""
    profile = InfluencerProfile(
        name="Dev Creator",
        platform="youtube",
        profile_url="https://youtube.com/@dev",
        follower_count=15000,
        niche="Tech",
        source_url="https://youtube.com/@dev",
        engagement_rate=None,
    )
    assert profile.engagement_rate is None


def test_invalid_engagement_rate_boundaries():
    """Engagement rate percentage must be within 0.0% and 100.0%."""
    # Negative engagement rate
    with pytest.raises(ValidationError):
        InfluencerProfile(
            name="Dev Creator",
            platform="youtube",
            profile_url="https://youtube.com/@dev",
            follower_count=15000,
            niche="Tech",
            source_url="https://youtube.com/@dev",
            engagement_rate=-1.5,
        )

    # Exceeding 100%
    with pytest.raises(ValidationError):
        InfluencerProfile(
            name="Dev Creator",
            platform="youtube",
            profile_url="https://youtube.com/@dev",
            follower_count=15000,
            niche="Tech",
            source_url="https://youtube.com/@dev",
            engagement_rate=105.0,
        )


def test_filtering_result_model():
    """Verify FilteringResult creation and audit payload."""
    audit = FilteringResult(
        influencer_id="test-id-123",
        passed=False,
        reasons=[
            "Follower count 4500 is below the micro-tier threshold of 10,000",
            "Engagement rate 0.8% is below the required 2.0% minimum",
        ],
        filter_criteria_version="v1.0",
        metrics_evaluated={"follower_count": 4500, "engagement_rate": 0.8},
    )

    assert audit.influencer_id == "test-id-123"
    assert audit.passed is False
    assert len(audit.reasons) == 2
    assert audit.metrics_evaluated["follower_count"] == 4500


def test_outreach_message_model():
    """Verify OutreachMessage creation and automatic deduplication key construction."""
    msg = OutreachMessage(
        influencer_id="test-id-456",
        channel="email",
        recipient_contact="alex@riveramedia.com",
        subject="Partnership Collaboration",
        message_body="Hi Alex, loved your recent video on Python AI agents.",
        status="SIMULATED_SENT",
    )

    assert msg.channel == "email"
    assert msg.deduplication_key == "test-id-456:email"
    assert msg.status == "SIMULATED_SENT"


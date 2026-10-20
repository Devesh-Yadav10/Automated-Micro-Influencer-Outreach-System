"""Unit tests for SQLite storage, transactions, foreign keys, and deduplication."""

import pytest
from src.storage.database import DatabaseManager
from src.validation.models import (
    FilteringResult,
    InfluencerProfile,
    OutreachMessage,
)


@pytest.fixture
def temp_db(tmp_path):
    """Fixture to create an isolated temporary SQLite database for each test."""
    db_file = tmp_path / "test_micro_influencer.db"
    db = DatabaseManager(db_file)
    return db


def test_database_initialization(temp_db):
    """Verify database schema creates all three primary tables and returns zero counts."""
    counts = temp_db.get_counts()
    assert counts["influencers"] == 0
    assert counts["filtering_audits"] == 0
    assert counts["outreach_logs"] == 0


def test_insert_and_retrieve_influencer(temp_db):
    """Verify storing and fetching a complete influencer profile."""
    profile = InfluencerProfile(
        name="Jordan Lee",
        platform="youtube",
        profile_url="https://youtube.com/@jordanlee_fit",
        handle="@jordanlee_fit",
        follower_count=42000,
        engagement_rate=3.8,
        niche="Fitness & Wellness",
        content_themes=["HIIT Workouts", "Nutrition"],
        contact_email="jordan@fitpulse.co",
        bio="Certified fitness coach sharing daily home workouts.",
        source_url="https://youtube.com/@jordanlee_fit/about",
    )

    # Insert into database
    success = temp_db.insert_influencer(profile)
    assert success is True

    # Retrieve by ID
    retrieved = temp_db.get_influencer_by_id(profile.id)
    assert retrieved is not None
    assert retrieved.name == "Jordan Lee"
    assert retrieved.follower_count == 42000
    assert retrieved.engagement_rate == 3.8
    assert retrieved.contact_email == "jordan@fitpulse.co"
    assert retrieved.content_themes == ["HIIT Workouts", "Nutrition"]

    # Retrieve by Dedup Key
    by_key = temp_db.get_influencer_by_dedup_key(profile.dedup_key)
    assert by_key is not None
    assert by_key.id == profile.id


def test_duplicate_influencer_prevention(temp_db):
    """Profiles sharing the same platform + handle/URL must be rejected as duplicates."""
    profile1 = InfluencerProfile(
        name="Jordan Lee",
        platform="youtube",
        profile_url="https://youtube.com/@jordanlee_fit",
        handle="@jordanlee_fit",
        follower_count=42000,
        niche="Fitness",
        source_url="https://youtube.com/@jordanlee_fit",
    )
    # Profile 2 has a different ID but identical dedup key (youtube:@jordanlee_fit)
    profile2 = InfluencerProfile(
        name="Jordan Lee Clone",
        platform="youtube",
        profile_url="https://youtube.com/@jordanlee_fit",
        handle="@jordanlee_fit",
        follower_count=43000,
        niche="Fitness",
        source_url="https://youtube.com/@jordanlee_fit",
    )

    res1 = temp_db.insert_influencer(profile1)
    res2 = temp_db.insert_influencer(profile2)

    assert res1 is True
    assert res2 is False  # Rejected due to duplicate dedup_key

    # Total count in DB should remain 1
    assert temp_db.get_counts()["influencers"] == 1


def test_missing_email_and_unknown_metrics_persistence(temp_db):
    """Ensure missing email persists as 'Not Found' and unknown engagement rate persists as None."""
    profile = InfluencerProfile(
        name="Mystery Creator",
        platform="youtube",
        profile_url="https://youtube.com/@mystery",
        follower_count=20000,
        niche="General",
        source_url="https://youtube.com/@mystery",
        engagement_rate=None,  # Unknown
        contact_email=None,     # Missing
    )

    temp_db.insert_influencer(profile)
    retrieved = temp_db.get_influencer_by_id(profile.id)

    assert retrieved is not None
    assert retrieved.contact_email == "Not Found"
    assert retrieved.engagement_rate is None


def test_filtering_audit_persistence(temp_db):
    """Verify filtering audits are correctly linked to influencers and store reasons."""
    profile = InfluencerProfile(
        name="Sam Tech",
        platform="youtube",
        profile_url="https://youtube.com/@samtech",
        follower_count=8500,
        niche="Tech",
        source_url="https://youtube.com/@samtech",
    )
    temp_db.insert_influencer(profile)

    audit = FilteringResult(
        influencer_id=profile.id,
        passed=False,
        reasons=["Follower count 8,500 is below minimum threshold of 10,000"],
        filter_criteria_version="v1.0",
        metrics_evaluated={"follower_count": 8500},
    )

    audit_id = temp_db.record_filtering_audit(audit)
    assert audit_id > 0

    audits = temp_db.get_filtering_audits_for_influencer(profile.id)
    assert len(audits) == 1
    assert audits[0].passed is False
    assert "below minimum threshold" in audits[0].reasons[0]


def test_outreach_logging_and_deduplication(temp_db):
    """Verify outreach logging and strict prevention of duplicate outreach on the same channel."""
    profile = InfluencerProfile(
        name="Target Influencer",
        platform="youtube",
        profile_url="https://youtube.com/@target",
        follower_count=50000,
        niche="Tech",
        contact_email="target@example.com",
        source_url="https://youtube.com/@target",
    )
    temp_db.insert_influencer(profile)

    # Initial check: can send outreach
    assert temp_db.can_send_outreach(profile.id, "email") is True

    # Record first outreach (simulated)
    msg1 = OutreachMessage(
        influencer_id=profile.id,
        channel="email",
        recipient_contact="target@example.com",
        subject="Collaboration Inquiry",
        message_body="Hi Target, would love to partner with you.",
        status="SIMULATED_SENT",
    )
    success1, reason1 = temp_db.record_outreach(msg1)
    assert success1 is True
    assert "recorded successfully" in reason1

    # Immediate check: cannot send duplicate outreach on the same channel
    assert temp_db.can_send_outreach(profile.id, "email") is False

    # Second attempt to send outreach on the same channel should be rejected
    msg2 = OutreachMessage(
        influencer_id=profile.id,
        channel="email",
        recipient_contact="target@example.com",
        subject="Second Attempt",
        message_body="Following up on my previous message.",
        status="SIMULATED_SENT",
    )
    success2, reason2 = temp_db.record_outreach(msg2)
    assert success2 is False
    assert "Duplicate outreach prevented" in reason2

    # Verification: Only 1 outreach record exists in database
    logs = temp_db.get_outreach_logs_for_influencer(profile.id)
    assert len(logs) == 1
    assert logs[0].subject == "Collaboration Inquiry"


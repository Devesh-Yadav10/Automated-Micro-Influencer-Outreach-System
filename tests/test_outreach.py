"""Unit tests for outreach simulation, email service, duplicate prevention, and DM logging."""

import pytest

from src.outreach.dispatcher import OutreachDispatcher
from src.outreach.email_service import EmailService
from src.storage.database import DatabaseManager
from src.validation.models import InfluencerProfile


@pytest.fixture
def temp_db(tmp_path):
    """Temporary SQLite database fixture."""
    return DatabaseManager(tmp_path / "test_outreach.db")


def create_profile(
    name: str = "Elena Rostova",
    email: str = "elena@neuralcode.org",
    handle: str = "@elenacode",
) -> InfluencerProfile:
    clean_handle = handle.lstrip("@")
    profile_url = f"https://youtube.com/@{clean_handle}"
    return InfluencerProfile(
        name=name,
        platform="youtube",
        profile_url=profile_url,
        handle=handle,
        follower_count=32000,
        engagement_rate=4.1,
        niche="Technology / AI / Machine Learning",
        content_themes=["Machine Learning", "PyTorch"],
        contact_email=email,
        source_url=f"{profile_url}/about",
    )


def test_email_service_simulation_mode_safe():
    """Simulation mode must succeed without attempting network/SMTP connections."""
    service = EmailService(mode="simulation")
    assert service.is_simulation is True

    success, status, msg = service.send_email(
        recipient="test@example.org",
        subject="Collaboration Inquiry",
        body="Hi Elena, would love to collaborate on a developer tooling project with you.",
    )

    assert success is True
    assert status == "SIMULATED_SENT"
    assert "No network request made" in msg


def test_email_service_rejects_not_found_email():
    """Email service must skip recipients with email 'Not Found' or empty."""
    service = EmailService(mode="simulation")

    success1, status1, _ = service.send_email("Not Found", "Subject", "Body")
    assert success1 is False
    assert status1 == "SKIPPED"

    success2, status2, _ = service.send_email("", "Subject", "Body")
    assert success2 is False
    assert status2 == "SKIPPED"


def test_live_smtp_mode_requires_explicit_confirmation():
    """Live SMTP mode must not send unless confirmed_by_user=True."""
    service = EmailService(mode="live_smtp")
    assert service.is_simulation is False

    success, status, msg = service.send_email(
        recipient="creator@example.com",
        subject="Collab",
        body="Pitch text",
        confirmed_by_user=False,
    )

    assert success is False
    assert status == "SKIPPED"
    assert "missing explicit user confirmation" in msg


def test_outreach_dispatcher_simulated_email_and_deduplication(temp_db):
    """Dispatcher must send simulated email, log it, and block duplicate sends on same channel."""
    profile = create_profile()
    temp_db.insert_influencer(profile)

    dispatcher = OutreachDispatcher(db=temp_db)

    # Initial state: can send
    assert temp_db.can_send_outreach(profile.id, "email") is True

    # 1. Send first simulated email
    success, msg, out_record = dispatcher.dispatch_email_to_influencer(profile)
    assert success is True
    assert out_record.status == "SIMULATED_SENT"

    # Verify log in database
    logs = temp_db.get_outreach_logs_for_influencer(profile.id)
    assert len(logs) == 1
    assert logs[0].channel == "email"
    assert logs[0].status == "SIMULATED_SENT"

    # Cannot send again
    assert temp_db.can_send_outreach(profile.id, "email") is False

    # 2. Second attempt must be rejected as duplicate
    dup_success, dup_msg, dup_record = dispatcher.dispatch_email_to_influencer(profile)
    assert dup_success is False
    assert "already been contacted" in dup_msg
    assert dup_record is None

    # Database still has only 1 record
    assert len(temp_db.get_outreach_logs_for_influencer(profile.id)) == 1


def test_outreach_dispatcher_skips_influencer_without_email(temp_db):
    """Influencers with 'Not Found' emails must never be contacted via email."""
    profile_no_email = create_profile(email=None)  # Normalized to "Not Found"
    temp_db.insert_influencer(profile_no_email)

    dispatcher = OutreachDispatcher(db=temp_db)
    success, reason, _ = dispatcher.dispatch_email_to_influencer(profile_no_email)

    assert success is False
    assert "has no public email" in reason


def test_instagram_dm_manual_workflow_and_deduplication(temp_db):
    """Verify Instagram DM manual recording and duplicate prevention."""
    profile = create_profile()
    temp_db.insert_influencer(profile)

    dispatcher = OutreachDispatcher(db=temp_db)

    # 1. Record manual DM
    dm_text = "Hey Elena! Loved your recent PyTorch tutorial. Interested in collaborating with our dev team?"
    success, msg, record = dispatcher.record_manual_instagram_dm(profile, dm_text, simulated=False)

    assert success is True
    assert record.status == "MANUAL_SENT"
    assert "MANUAL_SENT" in msg

    # Verify log
    logs = temp_db.get_outreach_logs_for_influencer(profile.id)
    assert len(logs) == 1
    assert logs[0].channel == "instagram_dm"
    assert logs[0].status == "MANUAL_SENT"

    # 2. Duplicate manual DM attempt must be rejected
    dup_success, dup_msg, _ = dispatcher.record_manual_instagram_dm(profile, dm_text)
    assert dup_success is False
    assert "already has logged Instagram DM outreach" in dup_msg


def test_batch_simulated_outreach(temp_db):
    """Verify batch simulated dispatch metrics (dispatched, skipped no email, skipped duplicate)."""
    p1 = create_profile("P1", email="p1@example.org", handle="@p1")
    p2 = create_profile("P2", email=None, handle="@p2")
    p3 = create_profile("P3", email="p3@example.org", handle="@p3")

    for p in [p1, p2, p3]:
        temp_db.insert_influencer(p)

    dispatcher = OutreachDispatcher(db=temp_db)

    # First batch run: P1 and P3 should be dispatched, P2 skipped for no email
    res1 = dispatcher.dispatch_batch_simulated_emails([p1, p2, p3])
    assert res1["simulated_dispatched"] == 2
    assert res1["skipped_no_email"] == 1
    assert res1["skipped_duplicate"] == 0

    # Second batch run immediately: P1 and P3 skipped as duplicate, P2 skipped for no email
    res2 = dispatcher.dispatch_batch_simulated_emails([p1, p2, p3])
    assert res2["simulated_dispatched"] == 0
    assert res2["skipped_duplicate"] == 2
    assert res2["skipped_no_email"] == 1

"""Unit tests for dashboard data-access logic and summary reporting."""

import pandas as pd
import pytest

from src.storage.database import DatabaseManager
from src.validation.models import InfluencerProfile, OutreachMessage


@pytest.fixture
def temp_db(tmp_path):
    """Temporary SQLite database fixture."""
    return DatabaseManager(tmp_path / "test_dashboard.db")


def test_empty_database_dashboard_resilience(temp_db):
    """Verify that dashboard queries handle an empty database without throwing errors."""
    influencers = temp_db.list_influencers()
    audits = temp_db.get_latest_filtering_audits()
    counts = temp_db.get_counts()

    assert len(influencers) == 0
    assert len(audits) == 0
    assert counts["influencers"] == 0
    assert counts["filtering_audits"] == 0
    assert counts["outreach_logs"] == 0
    assert counts["generated_messages"] == 0


def test_dashboard_dataframe_generation(temp_db):
    """Verify that profiles and outreach logs can be transformed into DataFrames for display."""
    profile = InfluencerProfile(
        name="Sarah Chen",
        platform="youtube",
        profile_url="https://youtube.com/@sarahchen",
        follower_count=28000,
        engagement_rate=4.5,
        niche="Technology / AI / Machine Learning",
        content_themes=["Machine Learning", "Python Programming"],
        contact_email="sarah@chen.ai",
        source_url="https://youtube.com/@sarahchen/about",
    )
    temp_db.insert_influencer(profile)

    msg = OutreachMessage(
        influencer_id=profile.id,
        channel="email",
        recipient_contact=profile.contact_email,
        subject="Partnership",
        message_body="Hi Sarah, would love to collaborate.",
        status="SIMULATED_SENT",
    )
    temp_db.record_outreach(msg)

    # Convert to DataFrames
    profiles = temp_db.list_influencers()
    df_profiles = pd.DataFrame([p.model_dump() for p in profiles])
    assert len(df_profiles) == 1
    assert df_profiles.iloc[0]["name"] == "Sarah Chen"
    assert df_profiles.iloc[0]["follower_count"] == 28000

    logs = temp_db.get_outreach_logs_for_influencer(profile.id)
    df_logs = pd.DataFrame([m.model_dump() for m in logs])
    assert len(df_logs) == 1
    assert df_logs.iloc[0]["status"] == "SIMULATED_SENT"


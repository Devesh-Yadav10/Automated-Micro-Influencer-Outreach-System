"""Unit tests for filtering rules, classification logic, auditing, and CSV export."""

import pytest

from src.filtering.pipeline import FilteringPipeline
from src.filtering.rules import (
    DataQualityRule,
    EngagementRateRule,
    MicroInfluencerTierRule,
    NicheRelevanceRule,
    RuleDecision,
)
from src.storage.database import DatabaseManager
from src.validation.models import InfluencerProfile


@pytest.fixture
def temp_db(tmp_path):
    """Temporary SQLite database fixture."""
    return DatabaseManager(tmp_path / "test_filtering.db")


def create_sample_profile(
    name: str = "Test Creator",
    follower_count: int = 50000,
    engagement_rate: float = 3.5,
    niche: str = "Technology / AI / Machine Learning",
    content_themes: list = None,
    contact_email: str = "collab@creator.com",
    profile_url: str = "https://youtube.com/@testcreator",
    source_url: str = "https://youtube.com/@testcreator/about",
    verification_status: str = "verified_public_data",
) -> InfluencerProfile:
    """Helper factory for test profiles."""
    return InfluencerProfile(
        name=name,
        platform="youtube",
        profile_url=profile_url,
        handle=f"@{name.lower().replace(' ', '')}",
        follower_count=follower_count,
        engagement_rate=engagement_rate,
        niche=niche,
        content_themes=content_themes or ["Python Programming", "Machine Learning"],
        contact_email=contact_email,
        bio="Creating weekly tutorials on AI and Python programming.",
        source_url=source_url,
        verification_status=verification_status,
    )


def test_follower_count_boundary_conditions():
    """Test boundary follower counts: 4999 (Fail), 5000 (Pass), 100000 (Pass), 100001 (Fail)."""
    rule = MicroInfluencerTierRule(min_followers=5000, max_followers=100000)

    # 4,999 -> Below threshold
    p_4999 = create_sample_profile(follower_count=4999)
    res_4999 = rule.evaluate(p_4999)
    assert res_4999.decision == RuleDecision.FAIL
    assert "below the micro-tier threshold" in res_4999.reason

    # 5,000 -> Exactly minimum
    p_5000 = create_sample_profile(follower_count=5000)
    res_5000 = rule.evaluate(p_5000)
    assert res_5000.decision == RuleDecision.PASS

    # 100,000 -> Exactly maximum
    p_100k = create_sample_profile(follower_count=100000)
    res_100k = rule.evaluate(p_100k)
    assert res_100k.decision == RuleDecision.PASS

    # 100,001 -> Exceeds maximum (macro tier)
    p_100001 = create_sample_profile(follower_count=100001)
    res_100001 = rule.evaluate(p_100001)
    assert res_100001.decision == RuleDecision.FAIL
    assert "exceeds the micro-tier threshold" in res_100001.reason


def test_unknown_follower_count_needs_review():
    """When follower count is hidden/unknown, evaluation must yield NEEDS_REVIEW."""
    rule = MicroInfluencerTierRule(min_followers=5000, max_followers=100000)
    profile = create_sample_profile(follower_count=0, verification_status="hidden_subscribers")
    res = rule.evaluate(profile)

    assert res.decision == RuleDecision.NEEDS_REVIEW
    assert "hidden or unknown" in res.reason


def test_niche_relevance_classification():
    """Verify relevant tech niche passes while unrelated niche fails."""
    rule = NicheRelevanceRule(target_niche="Technology / AI / Machine Learning")

    # Relevant niche
    tech_prof = create_sample_profile(
        niche="Technology / AI / Machine Learning",
        content_themes=["Deep Learning", "PyTorch"],
    )
    assert rule.evaluate(tech_prof).decision == RuleDecision.PASS

    # Irrelevant niche
    cooking_prof = create_sample_profile(
        niche="Cooking & Culinary Arts",
        content_themes=["Italian Recipes", "Baking Pastries"],
    )
    cooking_res = rule.evaluate(cooking_prof)
    assert cooking_res.decision == RuleDecision.FAIL
    assert "does not match" in cooking_res.reason


def test_engagement_rate_threshold_and_unknown_handling():
    """Verify known engagement rate comparisons and unknown metric handling."""
    # Enforce 2.0% minimum
    rule_with_threshold = EngagementRateRule(min_engagement_rate=2.0)

    # Above threshold
    p_above = create_sample_profile(engagement_rate=3.5)
    assert rule_with_threshold.evaluate(p_above).decision == RuleDecision.PASS

    # Below threshold
    p_below = create_sample_profile(engagement_rate=1.2)
    res_below = rule_with_threshold.evaluate(p_below)
    assert res_below.decision == RuleDecision.FAIL
    assert "below the minimum threshold of 2.0%" in res_below.reason

    # Unknown engagement rate -> NEEDS_REVIEW (never fails as 0.0%)
    p_unknown = create_sample_profile(engagement_rate=None)
    res_unknown = rule_with_threshold.evaluate(p_unknown)
    assert res_unknown.decision == RuleDecision.NEEDS_REVIEW
    assert "requires verification against the minimum threshold" in res_unknown.reason


def test_missing_email_does_not_disqualify():
    """Missing contact email should qualify for shortlist, but flag email_outreach_ready as False."""
    pipeline = FilteringPipeline()
    p_no_email = create_sample_profile(contact_email=None)  # Normalized to "Not Found"

    result = pipeline.evaluate_profile(p_no_email)
    assert result.classification == "QUALIFIED"
    assert result.passed is True
    assert result.metrics_evaluated["email_outreach_ready"] is False
    assert any("alternative outreach (DM) required" in r for r in result.reasons)


def test_data_quality_missing_provenance_needs_review():
    """Missing source URL triggers NEEDS_REVIEW due to incomplete provenance."""
    quality_rule = DataQualityRule()
    profile = create_sample_profile(source_url="")
    res = quality_rule.evaluate(profile)

    assert res.decision == RuleDecision.NEEDS_REVIEW
    assert "missing" in res.reason


def test_pipeline_decision_synthesis():
    """Test full pipeline decision logic: QUALIFIED, DISQUALIFIED, NEEDS_REVIEW."""
    pipeline = FilteringPipeline(min_followers=5000, max_followers=100000, min_engagement_rate=2.0)

    # Fully qualified profile
    qualified = pipeline.evaluate_profile(create_sample_profile(follower_count=30000, engagement_rate=3.5))
    assert qualified.classification == "QUALIFIED"
    assert qualified.passed is True

    # Disqualified profile (Followers = 150,000)
    disqualified = pipeline.evaluate_profile(create_sample_profile(follower_count=150000, engagement_rate=3.5))
    assert disqualified.classification == "DISQUALIFIED"
    assert disqualified.passed is False

    # Needs review profile (Engagement = None when threshold is required)
    needs_review = pipeline.evaluate_profile(create_sample_profile(follower_count=30000, engagement_rate=None))
    assert needs_review.classification == "NEEDS_REVIEW"
    assert needs_review.passed is False


def test_audit_persistence_and_history(temp_db):
    """Verify saving audits to SQLite preserves evaluation history."""
    profile = create_sample_profile()
    temp_db.insert_influencer(profile)

    pipeline = FilteringPipeline(db=temp_db)

    # First evaluation
    pipeline.evaluate_all(profiles=[profile], persist=True)
    audits_run1 = temp_db.get_filtering_audits_for_influencer(profile.id)
    assert len(audits_run1) == 1
    assert audits_run1[0].classification == "QUALIFIED"

    # Second evaluation with stricter criteria (e.g. min_followers=60,000)
    strict_pipeline = FilteringPipeline(db=temp_db, min_followers=60000)
    strict_pipeline.evaluate_all(profiles=[profile], persist=True)

    # Both audit entries must be preserved in history
    audits_run2 = temp_db.get_filtering_audits_for_influencer(profile.id)
    assert len(audits_run2) == 2
    assert audits_run2[0].classification == "DISQUALIFIED"  # Most recent first
    assert audits_run2[1].classification == "QUALIFIED"     # Historical run preserved


def test_export_audit_to_csv(tmp_path):
    """Verify exporting audit results and reasons to CSV."""
    pipeline = FilteringPipeline()
    p1 = create_sample_profile(name="Creator A", follower_count=20000)
    p2 = create_sample_profile(name="Creator B", follower_count=120000)

    audits = pipeline.evaluate_all(profiles=[p1, p2], persist=False)
    csv_file = tmp_path / "audit_report.csv"

    exported_path = pipeline.export_audit_to_csv(audits, [p1, p2], csv_file)
    assert exported_path.exists()

    content = exported_path.read_text(encoding="utf-8")
    assert "Creator A" in content
    assert "Creator B" in content
    assert "QUALIFIED" in content
    assert "DISQUALIFIED" in content

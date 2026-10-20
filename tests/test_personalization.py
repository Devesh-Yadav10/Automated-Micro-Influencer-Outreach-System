"""Unit tests for outreach message personalization, word count boundaries, fallback, and validation."""

from unittest.mock import patch
import pytest

from src.personalization.fallback import DeterministicMessageGenerator
from src.personalization.llm_client import PersonalizationEngine
from src.personalization.validator import (
    count_words,
    validate_email_pitch,
    validate_instagram_dm,
)
from src.storage.database import DatabaseManager
from src.validation.models import InfluencerProfile


@pytest.fixture
def temp_db(tmp_path):
    """Temporary SQLite database fixture."""
    return DatabaseManager(tmp_path / "test_personalization.db")


def make_profile(
    name: str = "Alex Rivera",
    themes: list = None,
    bio: str = "Machine learning engineer sharing open-source AI projects.",
) -> InfluencerProfile:
    return InfluencerProfile(
        name=name,
        platform="youtube",
        profile_url="https://youtube.com/@alexrivera",
        handle="@alexrivera",
        follower_count=45000,
        engagement_rate=3.8,
        niche="Technology / AI / Machine Learning",
        content_themes=themes or ["Python Programming", "Autonomous AI Agents"],
        contact_email="alex@riveramedia.com",
        bio=bio,
        source_url="https://youtube.com/@alexrivera/about",
    )


def test_word_count_utility():
    """Verify accurate word counting splitting on whitespace and ignoring symbols."""
    assert count_words("") == 0
    assert count_words(None) == 0
    assert count_words("Hello world") == 2
    assert count_words("One, two, three! Four... five?") == 5
    assert count_words("Word with   extra   spaces\nand\nnewlines.") == 6


def test_email_pitch_boundary_validation():
    """Verify 59 (fail), 60 (pass), 90 (pass), 91 (fail) for email pitch."""
    # 59 words -> Fail
    text_59 = " ".join(["word"] * 59)
    valid_59, msg_59, wc_59 = validate_email_pitch(text_59)
    assert valid_59 is False
    assert wc_59 == 59
    assert "below the minimum required of 60 words" in msg_59

    # 60 words -> Pass
    text_60 = " ".join(["word"] * 60)
    valid_60, msg_60, wc_60 = validate_email_pitch(text_60)
    assert valid_60 is True
    assert wc_60 == 60

    # 90 words -> Pass
    text_90 = " ".join(["word"] * 90)
    valid_90, msg_90, wc_90 = validate_email_pitch(text_90)
    assert valid_90 is True
    assert wc_90 == 90

    # 91 words -> Fail
    text_91 = " ".join(["word"] * 91)
    valid_91, msg_91, wc_91 = validate_email_pitch(text_91)
    assert valid_91 is False
    assert wc_91 == 91
    assert "exceeds the maximum allowed of 90 words" in msg_91


def test_instagram_dm_boundary_validation():
    """Verify 14 (fail), 15 (pass), 30 (pass), 31 (fail) for Instagram DM."""
    # 14 words -> Fail
    text_14 = " ".join(["word"] * 14)
    valid_14, msg_14, wc_14 = validate_instagram_dm(text_14)
    assert valid_14 is False
    assert wc_14 == 14
    assert "below the minimum required of 15 words" in msg_14

    # 15 words -> Pass
    text_15 = " ".join(["word"] * 15)
    valid_15, msg_15, wc_15 = validate_instagram_dm(text_15)
    assert valid_15 is True
    assert wc_15 == 15

    # 30 words -> Pass
    text_30 = " ".join(["word"] * 30)
    valid_30, msg_30, wc_30 = validate_instagram_dm(text_30)
    assert valid_30 is True
    assert wc_30 == 30

    # 31 words -> Fail
    text_31 = " ".join(["word"] * 31)
    valid_31, msg_31, wc_31 = validate_instagram_dm(text_31)
    assert valid_31 is False
    assert wc_31 == 31
    assert "exceeds the maximum allowed of 30 words" in msg_31


def test_deterministic_fallback_guarantees_length_and_personalization():
    """Deterministic fallback generator must produce valid messages across varied profiles."""
    gen = DeterministicMessageGenerator()

    profiles_to_test = [
        make_profile("Jordan Lee", ["PyTorch", "Computer Vision"]),
        make_profile("AI Jason", ["Autonomous Agents"]),
        make_profile("Short", ["Tech"], bio=None),
        make_profile("Complex Long Channel Name With Multiple Words", ["Deep Learning", "Transformers", "NLP"]),
    ]

    for p in profiles_to_test:
        subject, email_body, email_wc = gen.generate_email_pitch(p)
        assert 60 <= email_wc <= 90
        assert p.name.split()[0].lower() in email_body.lower() or (p.handle and p.handle.lstrip("@").lower() in email_body.lower())
        assert subject.startswith("Collaboration")

        dm_body, dm_wc = gen.generate_instagram_dm(p)
        assert 15 <= dm_wc <= 30
        assert p.name.split()[0].lower() in dm_body.lower() or (p.handle and p.handle.lstrip("@").lower() in dm_body.lower())


def test_llm_engine_fallback_on_missing_keys():
    """Engine must cleanly fall back to deterministic generator when no API key is provided."""
    engine = PersonalizationEngine(provider="fallback", api_key=None)
    profile = make_profile()

    result = engine.generate_messages(profile, persist=False)

    assert result["email"]["generation_method"] == "deterministic_fallback"
    assert result["email"]["is_valid"] is True
    assert 60 <= result["email"]["word_count"] <= 90

    assert result["instagram_dm"]["generation_method"] == "deterministic_fallback"
    assert result["instagram_dm"]["is_valid"] is True
    assert 15 <= result["instagram_dm"]["word_count"] <= 30


def test_llm_engine_fallback_on_api_exception():
    """If external LLM raises an error, engine falls back gracefully without crashing."""
    engine = PersonalizationEngine(provider="openai", api_key="test_key")

    with patch.object(engine, "_call_llm_api", side_effect=Exception("API connection timeout")):
        result = engine.generate_messages(make_profile(), persist=False)
        assert result["email"]["generation_method"] == "deterministic_fallback"
        assert result["email"]["is_valid"] is True
        assert 60 <= result["email"]["word_count"] <= 90


def test_llm_engine_mock_success():
    """When LLM returns a valid message, it is parsed and recorded."""
    engine = PersonalizationEngine(provider="openai", api_key="test_key")

    mock_email_words = ["word"] * 70
    mock_email_response = f"Subject: AI Tooling Partnership\n\nHi Alex,\n" + " ".join(mock_email_words)
    mock_dm_response = "Hey Alex! Loved your content on AI agents. We built a fast tool and would love to collaborate. Interested?"

    with patch.object(engine, "_call_llm_api", side_effect=[mock_email_response, mock_dm_response]):
        result = engine.generate_messages(make_profile(), persist=False)
        assert result["email"]["generation_method"] == "llm_openai"
        assert result["email"]["subject"] == "AI Tooling Partnership"
        assert result["instagram_dm"]["generation_method"] == "llm_openai"


def test_generated_message_persistence(temp_db):
    """Generated messages must persist to SQLite and be retrievable."""
    profile = make_profile()
    temp_db.insert_influencer(profile)

    engine = PersonalizationEngine(db=temp_db, provider="fallback")
    engine.generate_messages(profile, persist=True)

    saved_email = temp_db.get_latest_generated_message(profile.id, "email")
    assert saved_email is not None
    assert saved_email["channel"] == "email"
    assert 60 <= saved_email["word_count"] <= 90

    saved_dm = temp_db.get_latest_generated_message(profile.id, "instagram_dm")
    assert saved_dm is not None
    assert saved_dm["channel"] == "instagram_dm"
    assert 15 <= saved_dm["word_count"] <= 30


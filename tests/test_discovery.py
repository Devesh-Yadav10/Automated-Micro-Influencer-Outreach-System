"""Unit tests for discovery sources (SeedFileDiscoverySource, YouTubeDiscoverySource)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.discovery.base import (
    DiscoveryError,
    InvalidResponseError,
    QuotaExhaustedError,
    SourceUnavailableError,
)
from src.discovery.seed_source import SeedFileDiscoverySource
from src.discovery.youtube_source import YouTubeDiscoverySource


def test_discovery_exception_hierarchy():
    """Verify custom exception inheritance."""
    err = QuotaExhaustedError("Daily limit reached", source="youtube")
    assert isinstance(err, DiscoveryError)
    assert "[youtube]" in str(err)


def test_seed_source_loads_verified_50_profiles():
    """Load the verified Technology / AI dataset and confirm >= 50 valid profiles."""
    verified_file = Path("data/verified_tech_influencers.json")
    assert verified_file.exists(), "Verified tech influencers file must exist"

    source = SeedFileDiscoverySource()
    profiles = source.discover(file_path=verified_file, allow_fictional=False)

    # Deliverable 1: At least 50 real influencer profiles
    assert len(profiles) >= 50

    # Validate profile fields
    for p in profiles:
        assert p.name
        assert p.platform == "youtube"
        assert p.profile_url.startswith("https://")
        assert p.follower_count >= 0
        assert p.niche == "Technology / AI / Machine Learning"
        assert isinstance(p.content_themes, list)
        assert len(p.content_themes) > 0
        assert p.contact_email == "Not Found" or "@" in p.contact_email
        if p.engagement_rate is not None:
            assert 0.0 <= p.engagement_rate <= 100.0


def test_seed_source_safeguard_blocks_fictional():
    """By default, seed importer must reject datasets containing fictional test records."""
    fictional_file = Path("data/seed_example_fictional.csv")
    assert fictional_file.exists()

    source = SeedFileDiscoverySource()

    # With allow_fictional=False (default), fictional records are skipped
    imported_safe = source.discover(file_path=fictional_file, allow_fictional=False)
    assert len(imported_safe) == 0

    # With allow_fictional=True, fictional records can be imported for explicit tests
    imported_test = source.discover(file_path=fictional_file, allow_fictional=True)
    assert len(imported_test) == 2
    assert "[FICTIONAL TEST ONLY]" in imported_test[0].name


def test_seed_source_missing_file_raises():
    """Non-existent file must raise SourceUnavailableError."""
    source = SeedFileDiscoverySource()
    with pytest.raises(SourceUnavailableError):
        source.discover(file_path="data/non_existent_file.json")


def test_seed_source_unsupported_format_raises(tmp_path):
    """Unsupported extension must raise InvalidResponseError."""
    bad_file = tmp_path / "test.txt"
    bad_file.write_text("Hello World", encoding="utf-8")

    source = SeedFileDiscoverySource()
    with pytest.raises(InvalidResponseError):
        source.discover(file_path=bad_file)


def test_youtube_source_missing_api_key_raises():
    """YouTube discovery without API key must raise SourceUnavailableError."""
    source = YouTubeDiscoverySource(api_key=None)
    with pytest.raises(SourceUnavailableError):
        source.discover(queries=["AI tutorial"])


def test_youtube_engagement_calculation_mock():
    """Verify calculation of engagement proxy from video statistics."""
    source = YouTubeDiscoverySource(api_key="mock_key")

    mock_service = MagicMock()
    # Mock playlistItems response
    mock_service.playlistItems().list().execute.return_value = {
        "items": [
            {"contentDetails": {"videoId": "vid1"}},
            {"contentDetails": {"videoId": "vid2"}},
        ]
    }
    # Mock videos statistics response: 1000 views, 50 likes, 10 comments = 60 / 1000 = 6.0%
    mock_service.videos().list().execute.return_value = {
        "items": [
            {"statistics": {"viewCount": "600", "likeCount": "30", "commentCount": "5"}},
            {"statistics": {"viewCount": "400", "likeCount": "20", "commentCount": "5"}},
        ]
    }

    content_details = {"relatedPlaylists": {"uploads": "UU_test_playlist"}}
    rate = source._calculate_recent_video_engagement(mock_service, content_details)

    assert rate == 6.0  # (35 + 25) / 1000 * 100 = 6.0%


def test_youtube_quota_exceeded_handling():
    """Verify QuotaExhaustedError is raised on 403 quotaExceeded."""
    source = YouTubeDiscoverySource(api_key="mock_key")
    with pytest.raises(QuotaExhaustedError):
        source._handle_api_exception(Exception("HttpError 403: quotaExceeded limit reached"))


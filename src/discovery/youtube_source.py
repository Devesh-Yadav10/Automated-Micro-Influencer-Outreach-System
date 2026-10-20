"""Official YouTube Data API v3 discovery client for micro-influencer acquisition."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from src.discovery.base import (
    BaseDiscoverySource,
    DiscoveryError,
    InvalidResponseError,
    QuotaExhaustedError,
    SourceUnavailableError,
)
from src.enrichment.extractor import (
    extract_email_from_text,
    extract_themes_from_text,
)
from src.utils.logger import get_logger
from src.validation.models import InfluencerProfile

logger = get_logger("discovery.youtube")

# Default search topics for the initial Technology / AI niche
DEFAULT_TECH_QUERIES = [
    "AI tutorial",
    "machine learning engineering",
    "python data science",
    "deep learning projects",
    "LLM engineering",
]


class YouTubeDiscoverySource(BaseDiscoverySource):
    """
    Legitimate discovery client utilizing the official YouTube Data API v3.

    Engagement Rate Proxy Documentation:
    - Observation Window: Most recent public uploaded videos (up to 5 videos).
    - Formula: (Sum of likes + Sum of comments across window) / (Sum of views across window) * 100
    - Limitations: Represents an engagement proxy on recent public video content only,
      not overall channel lifetime engagement or cross-platform engagement.
    - If total views across the window is zero, or statistics are private/disabled,
      the engagement rate remains unknown (None).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        super().__init__(source_name="youtube_api_v3")
        self.api_key = api_key or get_settings().YOUTUBE_API_KEY
        self._service = None

    def _get_service(self) -> Any:
        """Lazily initialize Google API client service."""
        if self._service is not None:
            return self._service

        if not self.api_key:
            raise SourceUnavailableError(
                "YouTube API key is missing. Configure YOUTUBE_API_KEY in .env or provide it directly.",
                source=self.source_name,
            )

        try:
            from googleapiclient.discovery import build
            self._service = build("youtube", "v3", developerKey=self.api_key)
            return self._service
        except ImportError as e:
            raise SourceUnavailableError(
                "google-api-python-client is not installed. Install with: pip install google-api-python-client",
                source=self.source_name,
            ) from e
        except Exception as e:
            raise DiscoveryError(f"Failed to initialize YouTube service: {e}", source=self.source_name) from e

    def discover(
        self,
        queries: Optional[List[str]] = None,
        max_results_per_query: int = 15,
        target_niche: str = "Technology / AI / Machine Learning",
        compute_engagement: bool = True,
        **kwargs: Any,
    ) -> List[InfluencerProfile]:
        """
        Discover channels matching search queries and extract normalized profiles.

        Args:
            queries: List of search keywords (defaults to DEFAULT_TECH_QUERIES).
            max_results_per_query: Max channel search results per query (1-50).
            target_niche: Assigned niche label.
            compute_engagement: Whether to fetch recent video stats to calculate engagement proxy.

        Returns:
            List[InfluencerProfile]: Validated, deduplicated influencer profiles.
        """
        service = self._get_service()
        search_terms = queries or DEFAULT_TECH_QUERIES
        channel_ids_set = set()

        # Step 1: Search for channel IDs
        for term in search_terms:
            try:
                logger.info(f"Querying YouTube Data API for: '{term}'")
                request = service.search().list(
                    part="snippet",
                    q=term,
                    type="channel",
                    maxResults=min(max_results_per_query, 50),
                )
                response = request.execute()
                items = response.get("items", [])
                for item in items:
                    ch_id = item.get("id", {}).get("channelId")
                    if ch_id:
                        channel_ids_set.add(ch_id)
            except Exception as e:
                self._handle_api_exception(e)

        if not channel_ids_set:
            logger.warning("No channels discovered from YouTube search.")
            return []

        # Step 2: Fetch full channel details in batches (max 50 per batch)
        channel_ids_list = list(channel_ids_set)
        profiles: List[InfluencerProfile] = []

        for i in range(0, len(channel_ids_list), 50):
            batch_ids = channel_ids_list[i : i + 50]
            try:
                ch_request = service.channels().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(batch_ids),
                )
                ch_response = ch_request.execute()
                channel_items = ch_response.get("items", [])

                for ch in channel_items:
                    profile = self._parse_channel_item(
                        ch,
                        service=service if compute_engagement else None,
                        target_niche=target_niche,
                    )
                    if profile:
                        profiles.append(profile)
            except Exception as e:
                self._handle_api_exception(e)

        logger.info(f"Successfully discovered {len(profiles)} YouTube influencer profiles.")
        return profiles

    def _parse_channel_item(
        self,
        item: Dict[str, Any],
        service: Optional[Any],
        target_niche: str,
    ) -> Optional[InfluencerProfile]:
        """Parse raw YouTube channel JSON item into an InfluencerProfile."""
        ch_id = item.get("id")
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})

        if not ch_id or not snippet:
            return None

        title = snippet.get("title", "").strip() or f"Channel {ch_id}"
        description = snippet.get("description", "")
        custom_url = snippet.get("customUrl")  # e.g. '@sentdex'
        handle = custom_url if custom_url else f"@{ch_id}"
        profile_url = f"https://www.youtube.com/{custom_url}" if custom_url else f"https://www.youtube.com/channel/{ch_id}"

        is_hidden = statistics.get("hiddenSubscriberCount", False)
        sub_count_raw = statistics.get("subscriberCount")

        if is_hidden or sub_count_raw is None:
            follower_count = 0
            verification_status = "hidden_subscribers"
        else:
            try:
                follower_count = int(sub_count_raw)
                verification_status = "api_verified"
            except (ValueError, TypeError):
                follower_count = 0
                verification_status = "invalid_sub_count"

        engagement_rate: Optional[float] = None
        if service and not is_hidden:
            engagement_rate = self._calculate_recent_video_engagement(service, content_details)

        contact_email = extract_email_from_text(description)
        content_themes = extract_themes_from_text(description, default_themes=["Technology", "AI"])

        try:
            return InfluencerProfile(
                name=title,
                platform="youtube",
                profile_url=profile_url,
                handle=handle,
                follower_count=follower_count,
                engagement_rate=engagement_rate,
                niche=target_niche,
                content_themes=content_themes,
                contact_email=contact_email,
                bio=description[:1000] if description else None,
                source_url=f"https://www.googleapis.com/youtube/v3/channels?id={ch_id}",
                collected_at=datetime.now(timezone.utc),
                verification_status=verification_status,
            )
        except Exception as e:
            logger.warning(f"Failed to create InfluencerProfile for channel {ch_id}: {e}")
            return None

    def _calculate_recent_video_engagement(
        self,
        service: Any,
        content_details: Dict[str, Any],
        recent_video_limit: int = 5,
    ) -> Optional[float]:
        """
        Calculate engagement rate proxy from the most recent public videos.

        Formula:
            (sum(likes) + sum(comments)) / sum(views) * 100
        """
        try:
            uploads_playlist = (
                content_details.get("relatedPlaylists", {}).get("uploads")
            )
            if not uploads_playlist:
                return None

            # Fetch recent upload playlist items
            playlist_resp = (
                service.playlistItems()
                .list(
                    part="contentDetails",
                    playlistId=uploads_playlist,
                    maxResults=recent_video_limit,
                )
                .execute()
            )

            video_ids = [
                it["contentDetails"]["videoId"]
                for it in playlist_resp.get("items", [])
                if "contentDetails" in it and "videoId" in it["contentDetails"]
            ]

            if not video_ids:
                return None

            # Fetch statistics for these videos
            videos_resp = (
                service.videos()
                .list(part="statistics", id=",".join(video_ids))
                .execute()
            )

            total_views = 0
            total_interactions = 0

            for v in videos_resp.get("items", []):
                stats = v.get("statistics", {})
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))

                total_views += views
                total_interactions += likes + comments

            if total_views <= 0:
                return None

            rate = (total_interactions / total_views) * 100.0
            return round(rate, 2)

        except Exception as e:
            logger.debug(f"Could not compute video engagement rate: {e}")
            return None

    def _handle_api_exception(self, e: Exception) -> None:
        """Categorize Google API exceptions into standard discovery errors."""
        err_str = str(e).lower()
        if "quotaexceeded" in err_str or "rateLimitExceeded" in err_str or "403" in err_str:
            raise QuotaExhaustedError(
                f"YouTube API quota exceeded or forbidden: {e}",
                source=self.source_name,
            ) from e
        raise DiscoveryError(f"YouTube API error: {e}", source=self.source_name) from e


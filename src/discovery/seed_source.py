"""Seed file import discovery source supporting CSV and JSON datasets."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.discovery.base import (
    BaseDiscoverySource,
    DiscoveryError,
    InvalidResponseError,
    SourceUnavailableError,
)
from src.enrichment.extractor import extract_email_from_text, extract_themes_from_text
from src.utils.logger import get_logger
from src.validation.models import InfluencerProfile

logger = get_logger("discovery.seed")

# Marker values that signal fictional / test-only datasets
FICTIONAL_MARKERS = ["fictional", "synthetic", "test_only", "dummy", "fake", "sample_record"]


class SeedFileDiscoverySource(BaseDiscoverySource):
    """
    Imports and validates influencer profiles from genuine user-supplied CSV or JSON files.

    Guarantees:
    - Preserves all core fields and data provenance.
    - Missing emails normalize to 'Not Found'.
    - Unknown metrics remain None rather than invented numbers.
    - Safeguards against accidentally importing fictional test files into production discovery.
    """

    def __init__(self, file_path: Optional[Union[str, Path]] = None) -> None:
        super().__init__(source_name="seed_file")
        self.file_path = Path(file_path) if file_path else None

    def discover(
        self,
        file_path: Optional[Union[str, Path]] = None,
        allow_fictional: bool = False,
        default_niche: str = "Technology / AI / Machine Learning",
        **kwargs: Any,
    ) -> List[InfluencerProfile]:
        """
        Read, validate, and return influencer profiles from a CSV or JSON seed file.

        Args:
            file_path: Path to CSV or JSON file.
            allow_fictional: If False (default), blocks datasets labeled as fictional/synthetic.
            default_niche: Fallback niche if not specified in record.

        Returns:
            List[InfluencerProfile]: Validated influencer profile instances.
        """
        target_path = Path(file_path) if file_path else self.file_path
        if not target_path:
            raise SourceUnavailableError(
                "No seed file path provided.", source=self.source_name
            )

        if not target_path.exists():
            raise SourceUnavailableError(
                f"Seed file not found at: {target_path}", source=self.source_name
            )

        suffix = target_path.suffix.lower()
        if suffix == ".json":
            raw_records = self._load_json(target_path)
        elif suffix == ".csv":
            raw_records = self._load_csv(target_path)
        else:
            raise InvalidResponseError(
                f"Unsupported file format '{suffix}'. Expected .csv or .json.",
                source=self.source_name,
            )

        validated_profiles: List[InfluencerProfile] = []
        for index, raw in enumerate(raw_records, start=1):
            # Safeguard: Check for fictional indicators
            verification_status = str(raw.get("verification_status", "unverified")).strip()
            name = str(raw.get("name", "")).strip()

            is_fictional = (
                any(m in verification_status.lower() for m in FICTIONAL_MARKERS)
                or any(m in name.lower() for m in FICTIONAL_MARKERS)
                or "[fictional" in name.lower()
            )

            if is_fictional and not allow_fictional:
                logger.warning(
                    f"Skipping record #{index} ('{name}'): labeled as fictional/test data "
                    f"and allow_fictional=False."
                )
                continue

            try:
                profile = self._normalize_record(raw, target_path, default_niche)
                validated_profiles.append(profile)
            except Exception as e:
                logger.warning(f"Validation error in record #{index} ({name}): {e}")

        logger.info(
            f"Successfully imported and validated {len(validated_profiles)} profiles "
            f"from {target_path.name}"
        )
        return validated_profiles

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        """Load records from JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "influencers" in data:
                    return data["influencers"]
                else:
                    raise InvalidResponseError(
                        f"JSON file must contain a list of records or an 'influencers' array.",
                        source=self.source_name,
                    )
        except json.JSONDecodeError as e:
            raise InvalidResponseError(
                f"Malformed JSON in {path}: {e}", source=self.source_name
            ) from e

    def _load_csv(self, path: Path) -> List[Dict[str, Any]]:
        """Load records from CSV file."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                return [dict(row) for row in reader]
        except Exception as e:
            raise InvalidResponseError(
                f"Could not read CSV file {path}: {e}", source=self.source_name
            ) from e

    def _normalize_record(
        self,
        raw: Dict[str, Any],
        source_path: Path,
        default_niche: str,
    ) -> InfluencerProfile:
        """Convert a raw dictionary into a validated InfluencerProfile."""
        name = str(raw.get("name", "")).strip()
        platform = str(raw.get("platform", "youtube")).strip().lower()
        profile_url = str(raw.get("profile_url", "")).strip()
        handle = raw.get("handle")
        if handle is not None:
            handle = str(handle).strip() or None

        # Parse follower / subscriber count
        raw_followers = raw.get("follower_count") or raw.get("subscribers") or raw.get("followers")
        if raw_followers is None or str(raw_followers).strip() in {"", "None", "null", "unknown"}:
            follower_count = 0
        else:
            try:
                # Support strings with commas or decimals (e.g. "45,000")
                cleaned = str(raw_followers).replace(",", "").strip()
                follower_count = int(float(cleaned))
            except (ValueError, TypeError):
                follower_count = 0

        # Parse engagement rate (strictly None if missing/unknown)
        raw_engagement = raw.get("engagement_rate")
        engagement_rate: Optional[float] = None
        if raw_engagement is not None and str(raw_engagement).strip() not in {"", "None", "null", "unknown", "N/A"}:
            try:
                cleaned_eng = str(raw_engagement).replace("%", "").strip()
                val = float(cleaned_eng)
                if 0.0 <= val <= 100.0:
                    engagement_rate = round(val, 2)
            except (ValueError, TypeError):
                engagement_rate = None

        niche = str(raw.get("niche", "")).strip() or default_niche

        # Parse content themes
        themes_raw = raw.get("content_themes") or raw.get("themes")
        content_themes: List[str] = []
        if isinstance(themes_raw, list):
            content_themes = [str(t).strip() for t in themes_raw if str(t).strip()]
        elif isinstance(themes_raw, str) and themes_raw.strip():
            # Support comma-separated strings or JSON arrays in CSV
            themes_str = themes_raw.strip()
            if themes_str.startswith("[") and themes_str.endswith("]"):
                try:
                    content_themes = json.loads(themes_str)
                except Exception:
                    content_themes = [t.strip() for t in themes_str.strip("[]").split(",") if t.strip()]
            else:
                content_themes = [t.strip() for t in themes_str.split(",") if t.strip()]

        bio = str(raw.get("bio", "")).strip() or None

        # If themes still empty, attempt to infer from bio or default
        if not content_themes:
            content_themes = extract_themes_from_text(bio, default_themes=["Technology", "AI"])

        # Parse contact email
        raw_email = raw.get("contact_email") or raw.get("email")
        if raw_email and str(raw_email).strip().lower() not in {"not found", "none", "null", "n/a", ""}:
            contact_email = str(raw_email).strip()
        else:
            # Check bio text if not explicitly in email column
            contact_email = extract_email_from_text(bio)

        # Provenance metadata
        source_url = str(raw.get("source_url", "")).strip() or f"file://{source_path.resolve()}"

        raw_collected = raw.get("collected_at") or raw.get("collection_date")
        if raw_collected:
            try:
                collected_at = datetime.fromisoformat(str(raw_collected).replace("Z", "+00:00"))
            except Exception:
                collected_at = datetime.now(timezone.utc)
        else:
            collected_at = datetime.now(timezone.utc)

        verification_status = str(raw.get("verification_status", "seed_imported")).strip()

        return InfluencerProfile(
            name=name,
            platform=platform,
            profile_url=profile_url,
            handle=handle,
            follower_count=follower_count,
            engagement_rate=engagement_rate,
            niche=niche,
            content_themes=content_themes,
            contact_email=contact_email,
            bio=bio,
            source_url=source_url,
            collected_at=collected_at,
            verification_status=verification_status,
        )


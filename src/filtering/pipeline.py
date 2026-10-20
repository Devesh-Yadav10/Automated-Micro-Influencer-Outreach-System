"""Filtering and classification pipeline with transparent auditing and CSV export."""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.filtering.rules import (
    DataQualityRule,
    EngagementRateRule,
    MicroInfluencerTierRule,
    NicheRelevanceRule,
    RuleDecision,
)
from src.storage.database import DatabaseManager
from src.utils.logger import get_logger
from src.validation.models import FilteringResult, InfluencerProfile

logger = get_logger("filtering.pipeline")


class FilteringPipeline:
    """
    Configurable filtering and classification engine for candidate micro-influencers.

    Evaluates profiles against:
    1. Micro-influencer tier (default: 5,000–100,000 followers)
    2. Niche relevance (Technology / AI / Machine Learning)
    3. Recent-video engagement rate proxy (optional minimum threshold)
    4. Data quality and provenance (valid URLs, provenance metadata, email availability)

    Classification categories:
    - QUALIFIED: Satisfies all criteria.
    - DISQUALIFIED: Hard failure on audience size, niche, or engagement.
    - NEEDS_REVIEW: Incomplete evidence, missing provenance, or unknown required metrics.
    """

    RULESET_VERSION = "v1.1"

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        min_followers: int = 5000,
        max_followers: int = 100000,
        target_niche: str = "Technology / AI / Machine Learning",
        min_engagement_rate: Optional[float] = None,
        ruleset_version: str = RULESET_VERSION,
    ) -> None:
        self.db = db
        self.ruleset_version = ruleset_version
        self.min_followers = min_followers
        self.max_followers = max_followers
        self.target_niche = target_niche
        self.min_engagement_rate = min_engagement_rate

        # Initialize modular rules
        self.tier_rule = MicroInfluencerTierRule(
            min_followers=min_followers,
            max_followers=max_followers,
        )
        self.niche_rule = NicheRelevanceRule(target_niche=target_niche)
        self.engagement_rule = EngagementRateRule(min_engagement_rate=min_engagement_rate)
        self.quality_rule = DataQualityRule()

    def evaluate_profile(self, profile: InfluencerProfile) -> FilteringResult:
        """Evaluate a single influencer profile against all active rules."""
        results = [
            self.tier_rule.evaluate(profile),
            self.niche_rule.evaluate(profile),
            self.engagement_rule.evaluate(profile),
            self.quality_rule.evaluate(profile),
        ]

        decisions = [r.decision for r in results]
        reasons: List[str] = []
        metrics_snapshot: Dict[str, Any] = {
            "follower_count": profile.follower_count,
            "engagement_rate": profile.engagement_rate,
            "niche": profile.niche,
            "contact_email": profile.contact_email,
            "email_outreach_ready": profile.contact_email != "Not Found",
        }

        for r in results:
            reasons.append(f"[{r.rule_name} - {r.decision.value}] {r.reason}")
            metrics_snapshot.update(r.metrics)

        # Classification synthesis
        if RuleDecision.FAIL in decisions:
            classification = "DISQUALIFIED"
            passed = False
        elif RuleDecision.NEEDS_REVIEW in decisions:
            classification = "NEEDS_REVIEW"
            passed = False
        else:
            classification = "QUALIFIED"
            passed = True

        metrics_snapshot["classification"] = classification

        return FilteringResult(
            influencer_id=profile.id,
            passed=passed,
            classification=classification,
            reasons=reasons,
            filter_criteria_version=self.ruleset_version,
            metrics_evaluated=metrics_snapshot,
            evaluated_at=datetime.now(timezone.utc),
        )

    def evaluate_all(
        self,
        profiles: Optional[List[InfluencerProfile]] = None,
        persist: bool = True,
    ) -> List[FilteringResult]:
        """
        Evaluate candidate profiles and optionally persist the audit results in SQLite.

        Args:
            profiles: List of profiles to evaluate. If None, loads all profiles from DB.
            persist: If True and database is available, records audits in filtering_audits table.

        Returns:
            List[FilteringResult]: Evaluation results for each profile.
        """
        if profiles is None:
            if not self.db:
                raise ValueError("DatabaseManager required when profiles list is not supplied.")
            profiles = self.db.list_influencers()

        audits: List[FilteringResult] = []
        for profile in profiles:
            audit = self.evaluate_profile(profile)
            audits.append(audit)
            if persist and self.db:
                self.db.record_filtering_audit(audit)

        logger.info(
            f"Evaluated {len(audits)} profiles against ruleset {self.ruleset_version}."
        )
        return audits

    def get_summary(self, audits: List[FilteringResult]) -> Dict[str, Any]:
        """Generate high-level counts and qualification statistics from audit records."""
        total = len(audits)
        qualified = sum(1 for a in audits if a.classification == "QUALIFIED")
        disqualified = sum(1 for a in audits if a.classification == "DISQUALIFIED")
        needs_review = sum(1 for a in audits if a.classification == "NEEDS_REVIEW")

        pass_rate = round((qualified / total * 100.0), 2) if total > 0 else 0.0

        return {
            "total_evaluated": total,
            "qualified": qualified,
            "disqualified": disqualified,
            "needs_review": needs_review,
            "qualification_rate_percent": pass_rate,
            "filter_ruleset_version": self.ruleset_version,
            "thresholds": {
                "min_followers": self.min_followers,
                "max_followers": self.max_followers,
                "target_niche": self.target_niche,
                "min_engagement_rate": self.min_engagement_rate,
            },
        }

    def export_audit_to_csv(
        self,
        audits: List[FilteringResult],
        profiles: List[InfluencerProfile],
        output_path: Union[str, Path],
    ) -> Path:
        """
        Export classification results, reasons, and evaluated metrics to a CSV file.

        Args:
            audits: List of FilteringResult records.
            profiles: List of matching InfluencerProfile records.
            output_path: Destination CSV file path.

        Returns:
            Path: Absolute resolved path to generated CSV.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        profiles_by_id = {p.id: p for p in profiles}

        headers = [
            "influencer_id",
            "name",
            "platform",
            "profile_url",
            "follower_count",
            "engagement_rate",
            "contact_email",
            "classification",
            "passed",
            "reasons",
            "ruleset_version",
            "evaluated_at",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for audit in audits:
                prof = profiles_by_id.get(audit.influencer_id)
                writer.writerow(
                    {
                        "influencer_id": audit.influencer_id,
                        "name": prof.name if prof else "Unknown",
                        "platform": prof.platform if prof else "Unknown",
                        "profile_url": prof.profile_url if prof else "Unknown",
                        "follower_count": prof.follower_count if prof else 0,
                        "engagement_rate": prof.engagement_rate if prof else "Unknown",
                        "contact_email": prof.contact_email if prof else "Not Found",
                        "classification": audit.classification,
                        "passed": "YES" if audit.passed else "NO",
                        "reasons": " | ".join(audit.reasons),
                        "ruleset_version": audit.filter_criteria_version,
                        "evaluated_at": audit.evaluated_at.isoformat(),
                    }
                )

        logger.info(f"Exported {len(audits)} audit records to {path}")
        return path


"""Outreach dispatcher orchestrating email simulation and Instagram DM logging with deduplication."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.outreach.email_service import EmailService
from src.personalization.fallback import DeterministicMessageGenerator
from src.storage.database import DatabaseManager
from src.utils.logger import get_logger
from src.validation.models import InfluencerProfile, OutreachMessage

logger = get_logger("outreach.dispatcher")


class OutreachDispatcher:
    """
    Manages end-to-end outreach execution.
    Enforces email eligibility, deduplication safeguards, and simulation defaults.
    """

    def __init__(
        self,
        db: DatabaseManager,
        email_service: Optional[EmailService] = None,
    ) -> None:
        self.db = db
        self.email_service = email_service or EmailService()
        self.fallback_generator = DeterministicMessageGenerator()

    def dispatch_email_to_influencer(
        self,
        profile: InfluencerProfile,
        confirmed_by_user: bool = False,
        custom_subject: Optional[str] = None,
        custom_body: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[OutreachMessage]]:
        """
        Dispatch an outreach email to an influencer with deduplication protection.
        """
        # Check eligibility: missing or unverified email cannot proceed
        if not profile.contact_email or profile.contact_email.strip().lower() in {"not found", "none", ""}:
            reason = f"Creator '{profile.name}' has no public email ('Not Found'). Skipped."
            logger.warning(reason)
            return False, reason, None

        # Check deduplication policy (only 1 contact per channel)
        if not self.db.can_send_outreach(profile.id, "email"):
            reason = f"Duplicate outreach prevented: '{profile.name}' has already been contacted via email."
            logger.warning(reason)
            return False, reason, None

        # Retrieve message content from arguments, saved drafts, or fallback generator
        if custom_body and custom_subject:
            subject = custom_subject
            body = custom_body
        else:
            saved = self.db.get_latest_generated_message(profile.id, "email")
            if saved:
                subject = saved.get("subject") or f"Partnership Inquiry: {profile.name}"
                body = saved["message_body"]
            else:
                subj, b, _ = self.fallback_generator.generate_email_pitch(profile)
                subject = subj
                body = b

        # Dispatch via email service
        success, status, log_msg = self.email_service.send_email(
            recipient=profile.contact_email,
            subject=subject,
            body=body,
            confirmed_by_user=confirmed_by_user,
        )

        # Record in outreach log
        outreach_msg = OutreachMessage(
            influencer_id=profile.id,
            channel="email",
            recipient_contact=profile.contact_email,
            subject=subject,
            message_body=body,
            status=status,
            timestamp=datetime.now(timezone.utc),
            deduplication_key=f"{profile.id}:email",
        )

        db_success, db_msg = self.db.record_outreach(outreach_msg, enforce_dedup=True)
        return success and db_success, log_msg, outreach_msg

    def record_manual_instagram_dm(
        self,
        profile: InfluencerProfile,
        dm_body: str,
        simulated: bool = False,
    ) -> Tuple[bool, str, Optional[OutreachMessage]]:
        """
        Record an Instagram DM outreach action (manual or simulated).
        Never performs automated platform scraping or automated DM sending.
        """
        channel = "instagram_dm"
        recipient = profile.handle or profile.name

        # Check deduplication
        if not self.db.can_send_outreach(profile.id, channel):
            reason = f"Duplicate outreach prevented: '{profile.name}' already has logged Instagram DM outreach."
            logger.warning(reason)
            return False, reason, None

        status = "SIMULATED_SENT" if simulated else "MANUAL_SENT"
        outreach_msg = OutreachMessage(
            influencer_id=profile.id,
            channel=channel,
            recipient_contact=recipient,
            subject="Instagram Direct Message",
            message_body=dm_body,
            status=status,
            timestamp=datetime.now(timezone.utc),
            deduplication_key=f"{profile.id}:{channel}",
        )

        success, msg = self.db.record_outreach(outreach_msg, enforce_dedup=True)
        if not success:
            return False, msg, None
        return True, f"Instagram DM recorded as {status}", outreach_msg

    def dispatch_batch_simulated_emails(
        self,
        qualified_profiles: Optional[List[InfluencerProfile]] = None,
    ) -> Dict[str, Any]:
        """
        Execute simulated email outreach for all eligible qualified influencers.
        """
        if qualified_profiles is None:
            # Query qualified profiles
            all_profiles = self.db.list_influencers()
            latest_audits = self.db.get_latest_filtering_audits()
            qualified_profiles = [
                p for p in all_profiles
                if latest_audits.get(p.id) and latest_audits[p.id].classification == "QUALIFIED"
            ]

        dispatched = 0
        skipped_no_email = 0
        skipped_duplicate = 0
        failed = 0

        for profile in qualified_profiles:
            if not profile.contact_email or profile.contact_email == "Not Found":
                skipped_no_email += 1
                continue

            if not self.db.can_send_outreach(profile.id, "email"):
                skipped_duplicate += 1
                continue

            success, reason, _ = self.dispatch_email_to_influencer(profile, confirmed_by_user=False)
            if success:
                dispatched += 1
            else:
                failed += 1

        summary = {
            "total_qualified": len(qualified_profiles),
            "simulated_dispatched": dispatched,
            "skipped_no_email": skipped_no_email,
            "skipped_duplicate": skipped_duplicate,
            "failed": failed,
        }
        logger.info(f"Batch simulated outreach complete: {summary}")
        return summary

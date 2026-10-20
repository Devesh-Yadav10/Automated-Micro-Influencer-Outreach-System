"""Email service with default safe simulation and optional guarded SMTP transport."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Tuple

from config.settings import get_settings
from src.utils.logger import get_logger
from src.validation.models import EMAIL_REGEX

logger = get_logger("outreach.email_service")


class EmailService:
    """
    Manages email delivery. Strictly defaults to simulation mode.
    Simulated dispatch generates zero network traffic and records logs safely.
    """

    def __init__(self, mode: Optional[str] = None) -> None:
        settings = get_settings()
        self.mode = (mode or settings.OUTREACH_MODE).lower()
        self.sender_email = settings.SENDER_EMAIL
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD

    @property
    def is_simulation(self) -> bool:
        """Return True if running in simulation mode."""
        return self.mode != "live_smtp"

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        confirmed_by_user: bool = False,
    ) -> Tuple[bool, str, str]:
        """
        Send an email via simulation or live SMTP.

        Returns:
            Tuple[bool, str, str]: (success: bool, status: str, log_message: str)
        """
        # Baseline validation
        if not recipient or recipient.strip().lower() in {"not found", "none", "n/a", ""}:
            return (
                False,
                "SKIPPED",
                "Recipient email is marked as 'Not Found'. Email outreach cannot proceed.",
            )

        clean_recipient = recipient.strip().lower()
        if not EMAIL_REGEX.match(clean_recipient):
            return (
                False,
                "FAILED",
                f"Invalid recipient email format: '{recipient}'.",
            )

        if not body or not body.strip():
            return False, "FAILED", "Email body cannot be empty."

        # Case 1: Simulation Mode (Default & Safe)
        if self.is_simulation:
            logger.info(
                f"[SIMULATION] Simulated email dispatched to: {clean_recipient} | Subject: '{subject}'"
            )
            return (
                True,
                "SIMULATED_SENT",
                "Simulated dispatch successful. No network request made.",
            )

        # Case 2: Live SMTP Mode (Requires explicit user confirmation)
        if not confirmed_by_user:
            return (
                False,
                "SKIPPED",
                "Live SMTP dispatch requested but missing explicit user confirmation.",
            )

        if not self.smtp_host or not self.smtp_username or not self.smtp_password:
            return (
                False,
                "FAILED",
                "Live SMTP configuration is incomplete. Missing host, username, or password.",
            )

        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = clean_recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"[LIVE SMTP] Successfully dispatched email to: {clean_recipient}")
            return True, "SENT", "Email successfully dispatched via SMTP."

        except Exception as e:
            logger.error(f"[LIVE SMTP ERROR] Failed to send email to {clean_recipient}: {e}")
            return False, "FAILED", f"SMTP error: {str(e)}"


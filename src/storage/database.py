"""SQLite database operations, transactions, and schema management."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from src.utils.logger import get_logger
from src.validation.models import (
    FilteringResult,
    InfluencerProfile,
    OutreachMessage,
)

logger = get_logger("database")


class DatabaseManager:
    """Manages SQLite storage, table creation, parameterized queries, and deduplication."""

    SCHEMA_SQL = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS influencers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        platform TEXT NOT NULL,
        profile_url TEXT NOT NULL,
        handle TEXT,
        follower_count INTEGER NOT NULL CHECK(follower_count >= 0),
        engagement_rate REAL CHECK(engagement_rate IS NULL OR (engagement_rate >= 0.0 AND engagement_rate <= 100.0)),
        niche TEXT NOT NULL,
        content_themes TEXT NOT NULL,
        contact_email TEXT NOT NULL DEFAULT 'Not Found',
        bio TEXT,
        source_url TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        verification_status TEXT NOT NULL,
        dedup_key TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_influencers_platform ON influencers(platform);
    CREATE INDEX IF NOT EXISTS idx_influencers_niche ON influencers(niche);
    CREATE INDEX IF NOT EXISTS idx_influencers_dedup ON influencers(dedup_key);

    CREATE TABLE IF NOT EXISTS filtering_audits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        influencer_id TEXT NOT NULL,
        passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
        classification TEXT NOT NULL DEFAULT 'DISQUALIFIED',
        reasons TEXT NOT NULL,
        filter_criteria_version TEXT NOT NULL,
        metrics_evaluated TEXT NOT NULL,
        evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_audits_influencer ON filtering_audits(influencer_id);

    CREATE TABLE IF NOT EXISTS outreach_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        influencer_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        recipient_contact TEXT NOT NULL,
        subject TEXT,
        message_body TEXT NOT NULL,
        status TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deduplication_key TEXT UNIQUE NOT NULL,
        FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_outreach_influencer ON outreach_logs(influencer_id);
    CREATE INDEX IF NOT EXISTS idx_outreach_dedup ON outreach_logs(deduplication_key);

    CREATE TABLE IF NOT EXISTS generated_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        influencer_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        subject TEXT,
        message_body TEXT NOT NULL,
        word_count INTEGER NOT NULL,
        generation_method TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (influencer_id) REFERENCES influencers(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_gen_msg_influencer ON generated_messages(influencer_id);
    CREATE INDEX IF NOT EXISTS idx_gen_msg_channel ON generated_messages(channel);
    """

    def __init__(self, db_path: Union[str, Path] = "data/micro_influencer.db") -> None:
        self.db_path = Path(db_path)
        # Ensure parent directory exists for file-based paths
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a transactional SQLite connection with foreign keys and row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction rolled back due to error: {e}")
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Create tables and indexes if they do not already exist, with safe migrations."""
        with self.get_connection() as conn:
            conn.executescript(self.SCHEMA_SQL)
            # Safe migration: ensure classification column exists in filtering_audits
            cursor = conn.execute("PRAGMA table_info(filtering_audits);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "classification" not in columns:
                try:
                    conn.execute(
                        "ALTER TABLE filtering_audits ADD COLUMN classification TEXT DEFAULT 'DISQUALIFIED';"
                    )
                    logger.debug("Migrated filtering_audits: added classification column")
                except sqlite3.OperationalError:
                    pass
        logger.debug(f"Database schema initialized at {self.db_path}")

    def insert_influencer(self, profile: InfluencerProfile) -> bool:
        """
        Insert a new influencer profile.
        Returns True if inserted, or False if a profile with the same dedup_key already exists.
        """
        sql = """
        INSERT INTO influencers (
            id, name, platform, profile_url, handle, follower_count,
            engagement_rate, niche, content_themes, contact_email,
            bio, source_url, collected_at, verification_status, dedup_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            profile.id,
            profile.name,
            profile.platform,
            profile.profile_url,
            profile.handle,
            profile.follower_count,
            profile.engagement_rate,  # Stored as NULL if None
            profile.niche,
            json.dumps(profile.content_themes),
            profile.contact_email,
            profile.bio,
            profile.source_url,
            profile.collected_at.isoformat(),
            profile.verification_status,
            profile.dedup_key,
        )
        try:
            with self.get_connection() as conn:
                conn.execute(sql, params)
            logger.debug(f"Inserted influencer '{profile.name}' ({profile.id})")
            return True
        except sqlite3.IntegrityError as e:
            logger.warning(f"Duplicate influencer ignored: {profile.dedup_key} ({e})")
            return False

    def get_influencer_by_id(self, influencer_id: str) -> Optional[InfluencerProfile]:
        """Retrieve an influencer profile by its primary ID."""
        sql = "SELECT * FROM influencers WHERE id = ?"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (influencer_id,))
            row = cursor.fetchone()
        return self._row_to_influencer(row) if row else None

    def get_influencer_by_dedup_key(self, dedup_key: str) -> Optional[InfluencerProfile]:
        """Retrieve an influencer profile by its normalized deduplication key."""
        sql = "SELECT * FROM influencers WHERE dedup_key = ?"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (dedup_key,))
            row = cursor.fetchone()
        return self._row_to_influencer(row) if row else None

    def list_influencers(
        self,
        platform: Optional[str] = None,
        niche: Optional[str] = None,
    ) -> List[InfluencerProfile]:
        """List influencer profiles with optional platform or niche filtering."""
        conditions = []
        params: List[Any] = []

        if platform:
            conditions.append("platform = ?")
            params.append(platform.strip().lower())
        if niche:
            conditions.append("niche = ?")
            params.append(niche.strip())

        sql = "SELECT * FROM influencers"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY follower_count DESC"

        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        return [self._row_to_influencer(row) for row in rows]

    def record_filtering_audit(self, audit: FilteringResult) -> int:
        """Store evaluation result and reasons for an influencer."""
        sql = """
        INSERT INTO filtering_audits (
            influencer_id, passed, classification, reasons, filter_criteria_version,
            metrics_evaluated, evaluated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            audit.influencer_id,
            1 if audit.passed else 0,
            audit.classification,
            json.dumps(audit.reasons),
            audit.filter_criteria_version,
            json.dumps(audit.metrics_evaluated),
            audit.evaluated_at.isoformat(),
        )
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            audit_id = cursor.lastrowid
        logger.debug(
            f"Recorded audit for influencer {audit.influencer_id}: passed={audit.passed}, "
            f"classification={audit.classification}"
        )
        return audit_id

    def get_filtering_audits_for_influencer(self, influencer_id: str) -> List[FilteringResult]:
        """Retrieve historical filtering audit logs for an influencer."""
        sql = """
        SELECT * FROM filtering_audits
        WHERE influencer_id = ?
        ORDER BY evaluated_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (influencer_id,))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            classification = (
                r["classification"]
                if "classification" in r.keys() and r["classification"]
                else ("QUALIFIED" if r["passed"] else "DISQUALIFIED")
            )
            results.append(
                FilteringResult(
                    influencer_id=r["influencer_id"],
                    passed=bool(r["passed"]),
                    classification=classification,
                    reasons=json.loads(r["reasons"]),
                    filter_criteria_version=r["filter_criteria_version"],
                    metrics_evaluated=json.loads(r["metrics_evaluated"]),
                    evaluated_at=datetime.fromisoformat(r["evaluated_at"]),
                )
            )
        return results

    def get_latest_filtering_audits(self) -> Dict[str, FilteringResult]:
        """
        Retrieve the most recent audit record for each influencer.
        Returns a dictionary mapping influencer_id -> latest FilteringResult.
        """
        sql = """
        SELECT fa.* FROM filtering_audits fa
        INNER JOIN (
            SELECT influencer_id, MAX(id) as max_id
            FROM filtering_audits
            GROUP BY influencer_id
        ) latest ON fa.id = latest.max_id
        ORDER BY fa.evaluated_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()

        audits_by_id = {}
        for r in rows:
            classification = (
                r["classification"]
                if "classification" in r.keys() and r["classification"]
                else ("QUALIFIED" if r["passed"] else "DISQUALIFIED")
            )
            audits_by_id[r["influencer_id"]] = FilteringResult(
                influencer_id=r["influencer_id"],
                passed=bool(r["passed"]),
                classification=classification,
                reasons=json.loads(r["reasons"]),
                filter_criteria_version=r["filter_criteria_version"],
                metrics_evaluated=json.loads(r["metrics_evaluated"]),
                evaluated_at=datetime.fromisoformat(r["evaluated_at"]),
            )
        return audits_by_id

    def can_send_outreach(self, influencer_id: str, channel: str) -> bool:
        """
        Check if outreach can be dispatched to an influencer through the specified channel.
        Policy: An influencer can only be successfully contacted once per channel.
        """
        dedup_key = f"{influencer_id}:{channel.strip().lower()}"
        sql = """
        SELECT COUNT(*) FROM outreach_logs
        WHERE deduplication_key = ?
          AND status IN ('SENT', 'SIMULATED_SENT', 'MANUAL_SENT')
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (dedup_key,))
            count = cursor.fetchone()[0]
        return count == 0

    def record_outreach(
        self,
        message: OutreachMessage,
        enforce_dedup: bool = True,
    ) -> Tuple[bool, str]:
        """
        Record outreach message dispatch in the database.
        If enforce_dedup is True, duplicate contact on the same channel is rejected.
        Returns: (success: bool, status_message: str)
        """
        if enforce_dedup and not self.can_send_outreach(message.influencer_id, message.channel):
            reason = (
                f"Duplicate outreach prevented: influencer '{message.influencer_id}' "
                f"already contacted via '{message.channel}'"
            )
            logger.warning(reason)
            return False, reason

        sql = """
        INSERT INTO outreach_logs (
            influencer_id, channel, recipient_contact, subject,
            message_body, status, timestamp, deduplication_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            message.influencer_id,
            message.channel,
            message.recipient_contact,
            message.subject,
            message.message_body,
            message.status,
            message.timestamp.isoformat(),
            message.deduplication_key,
        )
        try:
            with self.get_connection() as conn:
                conn.execute(sql, params)
            logger.info(
                f"Recorded outreach [{message.status}] to {message.recipient_contact} "
                f"via {message.channel}"
            )
            return True, "Outreach recorded successfully"
        except sqlite3.IntegrityError as e:
            msg = f"Duplicate key constraint violation: {message.deduplication_key} ({e})"
            logger.warning(msg)
            return False, msg

    def get_outreach_logs_for_influencer(self, influencer_id: str) -> List[OutreachMessage]:
        """Retrieve outreach history for a specific influencer."""
        sql = """
        SELECT * FROM outreach_logs
        WHERE influencer_id = ?
        ORDER BY timestamp DESC
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (influencer_id,))
            rows = cursor.fetchall()

        logs = []
        for r in rows:
            logs.append(
                OutreachMessage(
                    influencer_id=r["influencer_id"],
                    channel=r["channel"],
                    recipient_contact=r["recipient_contact"],
                    subject=r["subject"],
                    message_body=r["message_body"],
                    status=r["status"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    deduplication_key=r["deduplication_key"],
                )
            )
        return logs

    def save_generated_message(
        self,
        influencer_id: str,
        channel: str,
        message_body: str,
        word_count: int,
        generation_method: str,
        subject: Optional[str] = None,
        status: str = "DRAFT",
    ) -> int:
        """Store a generated email pitch or Instagram DM."""
        sql = """
        INSERT INTO generated_messages (
            influencer_id, channel, subject, message_body,
            word_count, generation_method, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            influencer_id,
            channel.strip().lower(),
            subject,
            message_body,
            word_count,
            generation_method,
            status,
        )
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params)
            msg_id = cursor.lastrowid
        logger.debug(f"Saved generated {channel} message #{msg_id} for influencer {influencer_id}")
        return msg_id

    def get_latest_generated_message(
        self,
        influencer_id: str,
        channel: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent generated message for an influencer and channel."""
        sql = """
        SELECT * FROM generated_messages
        WHERE influencer_id = ? AND channel = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (influencer_id, channel.strip().lower()))
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_generated_messages_for_influencer(
        self,
        influencer_id: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve all generated messages for a given influencer."""
        sql = """
        SELECT * FROM generated_messages
        WHERE influencer_id = ?
        ORDER BY created_at DESC, id DESC
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (influencer_id,))
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def list_all_generated_messages(self) -> List[Dict[str, Any]]:
        """Retrieve all generated messages across the database."""
        sql = "SELECT * FROM generated_messages ORDER BY created_at DESC, id DESC"
        with self.get_connection() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_counts(self) -> Dict[str, int]:
        """Return counts of records in all primary tables."""
        with self.get_connection() as conn:
            influencer_count = conn.execute("SELECT COUNT(*) FROM influencers").fetchone()[0]
            audit_count = conn.execute("SELECT COUNT(*) FROM filtering_audits").fetchone()[0]
            outreach_count = conn.execute("SELECT COUNT(*) FROM outreach_logs").fetchone()[0]
            try:
                gen_msg_count = conn.execute("SELECT COUNT(*) FROM generated_messages").fetchone()[0]
            except sqlite3.OperationalError:
                gen_msg_count = 0
        return {
            "influencers": influencer_count,
            "filtering_audits": audit_count,
            "outreach_logs": outreach_count,
            "generated_messages": gen_msg_count,
        }

    @staticmethod
    def _row_to_influencer(row: sqlite3.Row) -> InfluencerProfile:
        """Convert a SQLite Row into a validated InfluencerProfile instance."""
        return InfluencerProfile(
            id=row["id"],
            name=row["name"],
            platform=row["platform"],
            profile_url=row["profile_url"],
            handle=row["handle"],
            follower_count=row["follower_count"],
            engagement_rate=row["engagement_rate"],  # None if NULL
            niche=row["niche"],
            content_themes=json.loads(row["content_themes"]),
            contact_email=row["contact_email"],
            bio=row["bio"],
            source_url=row["source_url"],
            collected_at=datetime.fromisoformat(row["collected_at"]),
            verification_status=row["verification_status"],
        )


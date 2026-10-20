"""Outreach logs integrity audit script."""

import sqlite3
from pathlib import Path
from src.validation.models import EMAIL_REGEX

db_path = Path("data/micro_influencer.db")
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT o.*, i.name, i.contact_email as profile_email
    FROM outreach_logs o
    JOIN influencers i ON o.influencer_id = i.id
""")
logs = cursor.fetchall()
conn.close()

print(f"Total outreach logs: {len(logs)}")
bad_emails = [r["recipient_contact"] for r in logs if not EMAIL_REGEX.match(r["recipient_contact"])]
not_found_recipients = [r["recipient_contact"] for r in logs if r["recipient_contact"] == "Not Found"]
duplicate_keys = set()
duplicates = []
for r in logs:
    key = r["deduplication_key"]
    if key in duplicate_keys:
        duplicates.append(key)
    duplicate_keys.add(key)

print(f"Recipients with invalid email syntax: {len(bad_emails)}")
print(f"Recipients with 'Not Found' email: {len(not_found_recipients)}")
print(f"Duplicate outreach records: {len(duplicates)}")
print(f"Unique deduplication keys in logs: {len(duplicate_keys)}")


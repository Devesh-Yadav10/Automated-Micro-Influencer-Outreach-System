"""Audit generated messages in SQLite database."""

import sqlite3
from pathlib import Path
from src.personalization.validator import count_words, validate_email_pitch, validate_instagram_dm

db_path = Path("data/micro_influencer.db")
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT gm.*, i.name as creator_name, i.niche, i.content_themes, i.contact_email
    FROM generated_messages gm
    JOIN influencers i ON gm.influencer_id = i.id
    ORDER BY gm.id ASC
""")
rows = cursor.fetchall()
conn.close()

print(f"Total stored messages audited: {len(rows)}")

email_count = 0
dm_count = 0
invalid_emails = []
invalid_dms = []

for r in rows:
    chan = r["channel"]
    body = r["message_body"]
    wc = count_words(body)
    creator = r["creator_name"]

    if chan == "email":
        email_count += 1
        is_val, reason, _ = validate_email_pitch(body)
        if not is_val:
            invalid_emails.append((creator, wc, reason))
    elif chan == "instagram_dm":
        dm_count += 1
        is_val, reason, _ = validate_instagram_dm(body)
        if not is_val:
            invalid_dms.append((creator, wc, reason))

print(f"Emails audited: {email_count} | Invalid: {len(invalid_emails)}")
if invalid_emails:
    for inv in invalid_emails[:3]:
        print(f"  Invalid Email: {inv}")

print(f"Instagram DMs audited: {dm_count} | Invalid: {len(invalid_dms)}")
if invalid_dms:
    for inv in invalid_dms[:3]:
        print(f"  Invalid DM: {inv}")


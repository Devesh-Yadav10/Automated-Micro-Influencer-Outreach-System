"""Dataset and database audit script."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

json_path = Path("data/verified_tech_influencers.json")
with open(json_path, "r", encoding="utf-8") as f:
    json_records = json.load(f)

print(f"Total records in JSON: {len(json_records)}")

# 1. Unique identities & URLs
names = [r["name"] for r in json_records]
unique_names = set(names)
handles = [r["handle"] for r in json_records]
unique_handles = set(handles)
urls = [r["profile_url"] for r in json_records]
unique_urls = set(urls)

print(f"Unique names: {len(unique_names)}/{len(names)}")
print(f"Unique handles: {len(unique_handles)}/{len(handles)}")
print(f"Unique profile URLs: {len(unique_urls)}/{len(urls)}")

# 2. Check profile URLs match handles and platforms
invalid_urls = []
for r in json_records:
    parsed = urlparse(r["profile_url"])
    if parsed.netloc not in {"www.youtube.com", "youtube.com"} or not r["profile_url"].startswith("https://"):
        invalid_urls.append(r["profile_url"])
print(f"Invalid profile URLs: {len(invalid_urls)}")

# 3. Source provenance & timestamps
missing_sources = [r["name"] for r in json_records if not r.get("source_url") or not r.get("collection_date")]
print(f"Records missing source URL or collection date: {len(missing_sources)}")

# 4. Subscriber count ranges
followers = [r["follower_count"] for r in json_records]
below_5k = [r for r in json_records if r["follower_count"] < 5000]
in_range_5k_100k = [r for r in json_records if 5000 <= r["follower_count"] <= 100000]
above_100k = [r for r in json_records if r["follower_count"] > 100000]

print(f"Subscribers < 5,000: {len(below_5k)}")
print(f"Subscribers 5,000–100,000 (Micro): {len(in_range_5k_100k)}")
print(f"Subscribers > 100,000 (Macro): {len(above_100k)}")

# 5. Email analysis: explicitly in text vs Not Found
emails = [r["contact_email"] for r in json_records]
has_email = [r for r in json_records if r["contact_email"] != "Not Found"]
not_found_email = [r for r in json_records if r["contact_email"] == "Not Found"]
print(f"Public business email present: {len(has_email)}")
print(f"Contact email 'Not Found': {len(not_found_email)}")

# 6. Database record comparison
db_path = Path("data/micro_influencer.db")
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM influencers")
    db_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT dedup_key) FROM influencers")
    db_unique = cursor.fetchone()[0]
    print(f"DB total influencers: {db_count}, unique: {db_unique}")

    # Check generated messages
    cursor.execute("SELECT COUNT(*) FROM generated_messages")
    gen_count = cursor.fetchone()[0]
    cursor.execute("SELECT channel, COUNT(*) FROM generated_messages GROUP BY channel")
    gen_by_chan = cursor.fetchall()
    print(f"DB generated messages: {gen_count} ({gen_by_chan})")

    # Check outreach logs
    cursor.execute("SELECT COUNT(*) FROM outreach_logs")
    out_count = cursor.fetchone()[0]
    cursor.execute("SELECT channel, status, COUNT(*) FROM outreach_logs GROUP BY channel, status")
    out_breakdown = cursor.fetchall()
    print(f"DB outreach logs: {out_count} ({out_breakdown})")
    conn.close()


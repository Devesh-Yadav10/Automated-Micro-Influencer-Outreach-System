"""Command-line interface for the Micro-Influencer Outreach System."""

import argparse
from pathlib import Path

from config.settings import get_settings
from src.discovery.seed_source import SeedFileDiscoverySource
from src.discovery.youtube_source import YouTubeDiscoverySource
from src.filtering.pipeline import FilteringPipeline
from src.outreach.dispatcher import OutreachDispatcher
from src.personalization.llm_client import PersonalizationEngine
from src.storage.database import DatabaseManager
from src.utils.logger import get_logger

logger = get_logger("cli")


def main() -> None:
    """Execute CLI actions."""
    parser = argparse.ArgumentParser(
        description="Automated Micro-Influencer Outreach System"
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize or verify the SQLite database schema.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display application configuration and database statistics.",
    )
    parser.add_argument(
        "--import-seed",
        nargs="?",
        const="data/verified_tech_influencers.json",
        help="Import verified micro-influencer profiles from a CSV or JSON file into the database.",
    )
    parser.add_argument(
        "--discover-youtube",
        action="store_true",
        help="Run live discovery using the official YouTube Data API v3 (requires YOUTUBE_API_KEY).",
    )
    parser.add_argument(
        "--filter",
        action="store_true",
        help="Run the filtering and classification pipeline on all stored influencer profiles.",
    )
    parser.add_argument(
        "--min-followers",
        type=int,
        default=5000,
        help="Minimum follower/subscriber threshold for micro-influencer tier (default: 5,000).",
    )
    parser.add_argument(
        "--max-followers",
        type=int,
        default=100000,
        help="Maximum follower/subscriber threshold for micro-influencer tier (default: 100,000).",
    )
    parser.add_argument(
        "--target-niche",
        type=str,
        default="Technology / AI / Machine Learning",
        help="Target niche category (default: 'Technology / AI / Machine Learning').",
    )
    parser.add_argument(
        "--min-engagement",
        type=float,
        default=None,
        help="Optional minimum engagement rate threshold percentage (e.g. 2.0).",
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="Export filtering audit results to the specified CSV file path.",
    )
    parser.add_argument(
        "--generate-messages",
        action="store_true",
        help="Generate personalized outreach emails and DMs for all qualified influencers.",
    )
    parser.add_argument(
        "--simulate-outreach",
        action="store_true",
        help="Dispatch simulated email outreach to all qualified influencers with verified public emails.",
    )

    args = parser.parse_args()
    settings = get_settings()

    logger.info("Starting Automated Micro-Influencer Outreach System")
    db = DatabaseManager(settings.get_db_path())

    if args.import_seed:
        file_path = Path(args.import_seed)
        logger.info(f"Importing verified profiles from {file_path}...")
        source = SeedFileDiscoverySource()
        profiles = source.discover(file_path=file_path, allow_fictional=False)
        inserted_count = 0
        duplicate_count = 0

        for p in profiles:
            if db.insert_influencer(p):
                inserted_count += 1
            else:
                duplicate_count += 1

        logger.info(
            f"Import complete: {inserted_count} newly inserted, {duplicate_count} duplicates skipped."
        )

    if args.discover_youtube:
        logger.info("Running live YouTube Data API v3 discovery...")
        yt_source = YouTubeDiscoverySource()
        try:
            yt_profiles = yt_source.discover()
            inserted_count = 0
            for p in yt_profiles:
                if db.insert_influencer(p):
                    inserted_count += 1
            logger.info(f"YouTube discovery complete: {inserted_count} profiles inserted.")
        except Exception as e:
            logger.error(f"YouTube discovery could not be completed: {e}")

    if args.filter:
        logger.info("Executing filtering and classification pipeline on stored profiles...")
        profiles = db.list_influencers()
        if not profiles:
            logger.warning("No profiles found in database. Run --import-seed first.")
        else:
            pipeline = FilteringPipeline(
                db=db,
                min_followers=args.min_followers,
                max_followers=args.max_followers,
                target_niche=args.target_niche,
                min_engagement_rate=args.min_engagement,
            )
            audits = pipeline.evaluate_all(profiles=profiles, persist=True)
            summary = pipeline.get_summary(audits)

            print("\n" + "=" * 68)
            print("  FILTERING & CLASSIFICATION SUMMARY")
            print("=" * 68)
            print(f"  Target Niche            : {args.target_niche}")
            print(f"  Follower Range          : {args.min_followers:,} – {args.max_followers:,}")
            print(f"  Min Engagement Rate     : {args.min_engagement if args.min_engagement is not None else 'Unconstrained'}%")
            print(f"  Total Profiles Evaluated: {summary['total_evaluated']}")
            print(f"  - QUALIFIED             : {summary['qualified']} ({summary['qualification_rate_percent']}%)")
            print(f"  - DISQUALIFIED          : {summary['disqualified']}")
            print(f"  - NEEDS_REVIEW          : {summary['needs_review']}")
            print("=" * 68)

            # Sample breakdown
            print("\nClassification Highlights:")
            for a in audits[:8]:
                prof = next((p for p in profiles if p.id == a.influencer_id), None)
                p_name = prof.name if prof else a.influencer_id
                print(f"  [{a.classification:<12}] {p_name:<30} | {a.reasons[0]}")
            if len(audits) > 8:
                print(f"  ... and {len(audits) - 8} more profiles recorded in SQLite audit log.")

            if args.export_csv:
                export_path = pipeline.export_audit_to_csv(audits, profiles, args.export_csv)
                print(f"\n  Audit results successfully exported to: {export_path}")

    if args.generate_messages:
        logger.info("Generating personalized outreach pitches for qualified creators...")
        all_profiles = db.list_influencers()
        audits_by_id = db.get_latest_filtering_audits()
        qualified_profiles = [
            p for p in all_profiles
            if audits_by_id.get(p.id) and audits_by_id[p.id].classification == "QUALIFIED"
        ]

        if not qualified_profiles:
            logger.warning("No qualified profiles found. Please run --filter first.")
        else:
            engine = PersonalizationEngine(db=db)
            generated_count = 0
            for p in qualified_profiles:
                res = engine.generate_messages(p, persist=True)
                generated_count += 1
            print(f"\n  Successfully generated pitches for {generated_count} qualified creators.")
            print(f"  All emails strictly meet 60–90 words; all Instagram DMs meet 15–30 words.")

    if args.simulate_outreach:
        logger.info("Executing simulated outreach batch for qualified creators with valid emails...")
        dispatcher = OutreachDispatcher(db=db)
        batch_summary = dispatcher.dispatch_batch_simulated_emails()
        print("\n" + "=" * 68)
        print("  SIMULATED OUTREACH DISPATCH SUMMARY")
        print("=" * 68)
        print(f"  Total Qualified Candidates: {batch_summary['total_qualified']}")
        print(f"  Simulated Dispatches      : {batch_summary['simulated_dispatched']}")
        print(f"  Skipped (No Public Email) : {batch_summary['skipped_no_email']}")
        print(f"  Skipped (Duplicate Send)  : {batch_summary['skipped_duplicate']}")
        print(f"  Failed Dispatches         : {batch_summary['failed']}")
        print("=" * 68)

    # Display status summary
    counts = db.get_counts()
    print("\n" + "=" * 68)
    print("  MICRO-INFLUENCER OUTREACH SYSTEM - STATUS")
    print("=" * 68)
    print(f"  App Environment  : {settings.APP_ENV}")
    print(f"  Outreach Mode    : {settings.OUTREACH_MODE} (Default: safe simulation)")
    print(f"  Database Path    : {settings.get_db_path()}")
    print(f"  LLM Provider     : {settings.LLM_PROVIDER}")
    print(f"  YouTube API Key  : {'Configured' if settings.YOUTUBE_API_KEY else 'Not Set (using Seed Import)'}")
    print("  Database Counts  :")
    print(f"    - Influencers     : {counts['influencers']}")
    print(f"    - Filtering Audits: {counts['filtering_audits']}")
    print(f"    - Outreach Logs   : {counts['outreach_logs']}")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()

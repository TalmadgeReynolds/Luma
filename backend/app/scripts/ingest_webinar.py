"""
CLI script for ingesting webinars into the database.

Usage:
    # Use fixture data
    python -m app.scripts.ingest_webinar --fixture

    # Use custom data
    python -m app.scripts.ingest_webinar \
        --title "My Webinar" \
        --description "Description here" \
        --date "2026-04-12" \
        --speakers "Alice,Bob" \
        --video-url "/videos/my-webinar.mp4" \
        --transcript "/transcripts/my-webinar.json"
"""
import argparse
import asyncio
from pathlib import Path

from app.db.database import AsyncSessionLocal
from app.services.ingestion_service import ingest_webinar


async def main():
    """Main entry point for the ingestion script."""
    parser = argparse.ArgumentParser(
        description="Ingest a webinar into the database"
    )

    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use fixture data (sample_transcript.json)"
    )

    parser.add_argument("--title", type=str, help="Video title")
    parser.add_argument("--description", type=str, help="Video description")
    parser.add_argument("--date", type=str, help="Webinar date (ISO format: YYYY-MM-DD)")
    parser.add_argument(
        "--speakers",
        type=str,
        help="Comma-separated list of speaker names"
    )
    parser.add_argument("--video-url", type=str, help="URL to video file")
    parser.add_argument("--transcript", type=str, help="Path to transcript JSON file")

    args = parser.parse_args()

    # Use fixture data or custom data
    if args.fixture:
        print("Using fixture data...")
        fixture_dir = Path(__file__).parent.parent.parent / "fixtures"
        title = "Character Consistency Deep Dive"
        description = "Internal webinar on maintaining character identity across AI-generated shots"
        webinar_date = "2026-04-12"
        speakers = ["Alice Chen", "Bob Martinez"]
        video_url = "/videos/char-consistency.mp4"
        transcript_path = str(fixture_dir / "sample_transcript.json")
    else:
        # Validate required arguments
        required = ["title", "speakers", "transcript"]
        missing = [arg for arg in required if not getattr(args, arg)]
        if missing:
            parser.error(f"The following arguments are required when not using --fixture: {', '.join(missing)}")

        title = args.title
        description = args.description
        webinar_date = args.date
        speakers = [s.strip() for s in args.speakers.split(",")]
        video_url = args.video_url
        transcript_path = args.transcript

    # Run ingestion
    try:
        async with AsyncSessionLocal() as session:
            video_id, chunk_count = await ingest_webinar(
                title=title,
                description=description,
                webinar_date=webinar_date,
                speakers=speakers,
                video_url=video_url,
                transcript_path=transcript_path,
                db_session=session,
            )

            print(f"\n{'='*60}")
            print(f"✓ SUCCESS")
            print(f"{'='*60}")
            print(f"Video ID: {video_id}")
            print(f"Chunks created: {chunk_count}")
            print(f"{'='*60}\n")

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"✗ FAILED")
        print(f"{'='*60}")
        print(f"Error: {e}")
        print(f"{'='*60}\n")
        raise


if __name__ == "__main__":
    asyncio.run(main())

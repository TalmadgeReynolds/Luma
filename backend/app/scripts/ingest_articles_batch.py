"""
CLI script for batch ingesting all articles from the manifest.

Usage:
    python -m app.scripts.ingest_articles_batch \
        --manifest /path/to/manifest.csv \
        --continue-on-error \
        --log-file ingestion.log
"""
import argparse
import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from app.db.database import AsyncSessionLocal
from app.db.models import Video
from app.services.article_ingestion_service import ingest_article


async def main():
    """Main entry point for batch article ingestion."""
    parser = argparse.ArgumentParser(
        description="Batch ingest all articles from manifest.csv"
    )

    parser.add_argument(
        "--manifest",
        type=str,
        required=True,
        help="Path to manifest.csv file"
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing even if an article fails"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Path to log file (optional)"
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip articles that are already ingested (default: True)"
    )

    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"✗ ERROR: Manifest not found at: {manifest_path}")
        sys.exit(1)

    # Setup logging
    log_file = None
    if args.log_file:
        log_file = open(args.log_file, 'a')
        log_file.write(f"\n{'='*80}\n")
        log_file.write(f"Batch ingestion started: {datetime.now()}\n")
        log_file.write(f"{'='*80}\n\n")

    def log(message):
        """Log to both console and file."""
        print(message)
        if log_file:
            log_file.write(message + '\n')
            log_file.flush()

    # Read manifest
    articles = []
    with open(manifest_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('status', 'ok') != 'ok':
                continue
            articles.append(row)

    log(f"Found {len(articles)} articles in manifest")
    log("")

    # Get already-ingested articles if skip_existing is enabled
    existing_urls = set()
    if args.skip_existing:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Video.source_url).where(Video.content_type == 'article')
            )
            existing_urls = {url for (url,) in result.fetchall() if url}
            if existing_urls:
                log(f"Found {len(existing_urls)} already-ingested articles (will skip)")
                log("")

    # Track stats
    stats = {
        'total': len(articles),
        'success': 0,
        'skipped': 0,
        'failed': 0,
        'chunks_created': 0
    }
    failed_articles = []

    # Process each article
    for i, article_row in enumerate(articles, 1):
        article_id = article_row['index']
        title = article_row['title']
        url = article_row['url']
        filename = article_row['filename']
        date = "2026-03-09"  # All articles have same publication date

        log(f"[{i}/{len(articles)}] Processing: {title}")

        # Check if already ingested
        if args.skip_existing and url in existing_urls:
            log(f"  ⊙ Skipped (already ingested)")
            log("")
            stats['skipped'] += 1
            continue

        # Find article file
        article_path = manifest_path.parent / filename
        if not article_path.exists():
            log(f"  ✗ ERROR: Article file not found: {filename}")
            log("")
            stats['failed'] += 1
            failed_articles.append((title, f"File not found: {filename}"))
            if not args.continue_on_error:
                break
            continue

        # Read article text
        try:
            article_text = article_path.read_text(encoding='utf-8')
        except Exception as e:
            log(f"  ✗ ERROR: Could not read file: {e}")
            log("")
            stats['failed'] += 1
            failed_articles.append((title, f"Read error: {e}"))
            if not args.continue_on_error:
                break
            continue

        # Ingest article
        try:
            async with AsyncSessionLocal() as session:
                article_db_id, chunk_count = await ingest_article(
                    title=title,
                    source_url=url,
                    publication_date=date,
                    article_text=article_text,
                    db_session=session,
                )

                log(f"  ✓ Success: {chunk_count} chunks created")
                log("")
                stats['success'] += 1
                stats['chunks_created'] += chunk_count

        except Exception as e:
            log(f"  ✗ ERROR: {e}")
            log("")
            stats['failed'] += 1
            failed_articles.append((title, str(e)))

            if not args.continue_on_error:
                log("\nStopping due to error (use --continue-on-error to keep going)")
                break

    # Print summary
    log("")
    log("="*80)
    log("BATCH INGESTION SUMMARY")
    log("="*80)
    log(f"Total articles: {stats['total']}")
    log(f"  ✓ Successful: {stats['success']}")
    log(f"  ⊙ Skipped: {stats['skipped']}")
    log(f"  ✗ Failed: {stats['failed']}")
    log(f"Total chunks created: {stats['chunks_created']}")
    log("="*80)

    if failed_articles:
        log("")
        log("FAILED ARTICLES:")
        log("-" * 80)
        for title, error in failed_articles:
            log(f"  - {title}")
            log(f"    Error: {error}")
        log("="*80)

    # Close log file
    if log_file:
        log_file.write(f"\nBatch ingestion completed: {datetime.now()}\n")
        log_file.close()

    # Exit with appropriate code
    if stats['failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

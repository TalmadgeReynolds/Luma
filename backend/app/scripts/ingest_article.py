"""
CLI script for ingesting a single article into the database.

Usage:
    # Ingest specific article by ID (from exported articles)
    python -m app.scripts.ingest_article --article-id 1

    # Use custom data
    python -m app.scripts.ingest_article \
        --title "The Luma Agent" \
        --url "https://lumalabs.ai/learning-center/articles/about-the-luma-agent" \
        --date "2026-03-09" \
        --file "/path/to/article.txt"
"""
import argparse
import asyncio
import csv
from pathlib import Path

from app.db.database import AsyncSessionLocal
from app.services.article_ingestion_service import ingest_article


async def main():
    """Main entry point for the article ingestion script."""
    parser = argparse.ArgumentParser(
        description="Ingest a single article into the database"
    )

    parser.add_argument(
        "--article-id",
        type=int,
        help="Article ID (index) from the manifest.csv (1-28)"
    )

    parser.add_argument("--title", type=str, help="Article title")
    parser.add_argument("--url", type=str, help="Article source URL")
    parser.add_argument("--date", type=str, help="Publication date (ISO format: YYYY-MM-DD)")
    parser.add_argument("--file", type=str, help="Path to article text file")

    args = parser.parse_args()

    # Use article-id or custom data
    if args.article_id:
        print(f"Loading article {args.article_id} from manifest...")

        # Path to exported articles
        export_dir = Path(__file__).parent.parent.parent.parent / "scripts" / "luma_learning_center_plain_text_exporter" / "luma_learning_center_plain_text_articles"
        manifest_path = export_dir / "manifest.csv"

        if not manifest_path.exists():
            parser.error(f"Manifest not found at: {manifest_path}")

        # Read manifest to find article
        article_found = False
        with open(manifest_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if int(row['index']) == args.article_id:
                    title = row['title']
                    url = row['url']
                    date = "2026-03-09"  # All articles have same date
                    filename = row['filename']
                    article_path = export_dir / filename
                    article_found = True
                    break

        if not article_found:
            parser.error(f"Article {args.article_id} not found in manifest (valid range: 1-28)")

        if not article_path.exists():
            parser.error(f"Article file not found at: {article_path}")

        # Read article text
        article_text = article_path.read_text(encoding='utf-8')

    else:
        # Validate required arguments
        required = ["title", "url", "file"]
        missing = [arg for arg in required if not getattr(args, arg)]
        if missing:
            parser.error(f"The following arguments are required when not using --article-id: {', '.join(missing)}")

        title = args.title
        url = args.url
        date = args.date
        article_path = Path(args.file)

        if not article_path.exists():
            parser.error(f"Article file not found at: {article_path}")

        # Read article text
        article_text = article_path.read_text(encoding='utf-8')

    # Run ingestion
    try:
        async with AsyncSessionLocal() as session:
            article_id, chunk_count = await ingest_article(
                title=title,
                source_url=url,
                publication_date=date,
                article_text=article_text,
                db_session=session,
            )

            print(f"\n{'='*60}")
            print(f"✓ SUCCESS")
            print(f"{'='*60}")
            print(f"Article ID: {article_id}")
            print(f"Chunks created: {chunk_count}")
            print(f"Source URL: {url}")
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

"""
Run migration 009: backfill webinar_date and standardize titles.

Usage:
    python run_migration_009.py          # dry run — shows what will change
    python run_migration_009.py --apply  # applies the migration
"""
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.db.database import engine


PREVIEW_SQL = """
SELECT
    id,
    title,
    webinar_date,
    CASE
        WHEN title ~ '^\\d{2}-\\d{2}-\\d{4}$'
            THEN TO_DATE(title, 'MM-DD-YYYY')
        WHEN title ~ '^GMT\\d{8}[-_]'
            THEN TO_DATE(substring(title FROM 'GMT(\\d{8})'), 'YYYYMMDD')
        WHEN title ~ '^\\d{8}(\\s|$)'
            THEN TO_DATE(substring(title FROM '^(\\d{8})'), 'YYYYMMDD')
        ELSE NULL
    END AS parsed_date
FROM videos
WHERE content_type = 'webinar'
ORDER BY webinar_date NULLS FIRST, title;
"""


async def main(apply: bool):
    migration_file = Path(__file__).parent / "backend" / "app" / "db" / "migrations" / "009_fix_webinar_titles_and_dates.sql"

    async with engine.connect() as conn:
        # Preview current state
        result = await conn.execute(text(PREVIEW_SQL))
        rows = result.fetchall()

        print(f"\n{'─'*70}")
        print(f"{'TITLE':<45} {'CURRENT DATE':<14} {'PARSED DATE'}")
        print(f"{'─'*70}")
        for row in rows:
            current = str(row.webinar_date) if row.webinar_date else "(null)"
            parsed = str(row.parsed_date) if row.parsed_date else "(no match)"
            print(f"{row.title[:44]:<45} {current:<14} {parsed}")

        print(f"{'─'*70}")
        print(f"Total webinars: {len(rows)}")
        nulls = sum(1 for r in rows if r.webinar_date is None)
        matched = sum(1 for r in rows if r.webinar_date is None and r.parsed_date is not None)
        print(f"  webinar_date is NULL: {nulls}")
        print(f"  Will be backfilled:   {matched}")
        print(f"  No date match:        {nulls - matched}")

        if not apply:
            print("\nDry run — pass --apply to execute.\n")
            return

        # Apply migration
        sql = migration_file.read_text()
        statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]

        async with conn.begin():
            for stmt in statements:
                r = await conn.execute(text(stmt))
                print(f"  Executed ({r.rowcount} rows affected): {stmt[:60]}...")

        print("\nMigration 009 applied successfully.\n")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(main(apply))

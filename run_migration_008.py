"""Run migration 008 only."""
import asyncio
from pathlib import Path
from sqlalchemy import text
from app.db.database import engine


async def run_migration_008():
    """Execute migration 008."""
    migration_file = Path("backend/app/db/migrations/008_add_content_type_to_videos.sql")

    print(f"Running: {migration_file.name}")

    # Read SQL content
    sql_content = migration_file.read_text()

    # Split SQL into individual statements
    statements = [
        stmt.strip()
        for stmt in sql_content.split(';')
        if stmt.strip()
    ]

    async with engine.begin() as conn:
        try:
            for stmt in statements:
                print(f"Executing: {stmt[:100]}...")
                await conn.execute(text(stmt))
            print(f"✓ {migration_file.name} completed successfully")
        except Exception as e:
            print(f"✗ {migration_file.name} failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run_migration_008())

"""
Migration runner script.

Executes all SQL migration files in the db/migrations/ directory in lexicographic order.
Substitutes {{EMBEDDING_DIMENSION}} placeholder with the value from config.
"""
import asyncio
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.db.database import engine


async def run_migrations():
    """Execute all migration SQL files in order."""
    settings = get_settings()
    migrations_dir = Path(__file__).parent.parent / "db" / "migrations"

    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print("No migration files found.")
        return

    print(f"Found {len(migration_files)} migration files.")
    print(f"EMBEDDING_DIMENSION: {settings.EMBEDDING_DIMENSION}")

    async with engine.begin() as conn:
        for sql_file in migration_files:
            print(f"\nExecuting: {sql_file.name}")

            # Read SQL content
            sql_content = sql_file.read_text()

            # Substitute EMBEDDING_DIMENSION placeholder
            sql_content = sql_content.replace(
                "{{EMBEDDING_DIMENSION}}",
                str(settings.EMBEDDING_DIMENSION)
            )

            # Split SQL into individual statements and execute each
            # (asyncpg doesn't support multiple commands in a single execute)
            statements = [
                stmt.strip()
                for stmt in sql_content.split(';')
                if stmt.strip()
            ]

            try:
                for stmt in statements:
                    await conn.execute(text(stmt))
                print(f"✓ {sql_file.name} completed successfully")
            except Exception as e:
                print(f"✗ {sql_file.name} failed: {e}")
                raise

    print("\n✓ All migrations completed successfully!")


def main():
    """Entry point for the migration script."""
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()

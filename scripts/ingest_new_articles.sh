#!/usr/bin/env bash
# =============================================================================
# ingest_new_articles.sh
#
# End-to-end script that:
#   1. Installs scraper dependencies
#   2. Scrapes Learning Center articles to plain text + manifest.csv
#   3. Ingests only NEW articles (skips already-ingested ones)
#
# Usage:
#   ./scripts/ingest_new_articles.sh
#   ./scripts/ingest_new_articles.sh --browser    # use Playwright for discovery
#
# Prerequisites:
#   - Python 3.9+ in PATH
#   - Backend .env file configured at backend/.env
#   - PostgreSQL running and accessible
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

EXPORTER_DIR="$SCRIPT_DIR/luma_learning_center_plain_text_exporter"
ARTICLES_DIR="$EXPORTER_DIR/luma_learning_center_plain_text_articles"
MANIFEST="$ARTICLES_DIR/manifest.csv"

BACKEND_DIR="$REPO_ROOT/backend"

# ---------------------------------------------------------------------------
echo "=== Step 1: Install scraper dependencies ==="
pip install -r "$EXPORTER_DIR/requirements.txt" --quiet

# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: Scrape Learning Center articles ==="
(
  cd "$EXPORTER_DIR"
  python export_luma_learning_center_articles.py "$@"
)

if [[ ! -f "$MANIFEST" ]]; then
  echo "✗ ERROR: Manifest not found at $MANIFEST after scraping."
  exit 1
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: Ingest new articles ==="
(
  cd "$BACKEND_DIR"
  python -m app.scripts.ingest_articles_batch \
    --manifest "$MANIFEST" \
    --skip-existing \
    --continue-on-error
)

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRAPER_DIR="$REPO_ROOT/scripts/luma_learning_center_plain_text_exporter"
MANIFEST="$SCRAPER_DIR/luma_learning_center_plain_text_articles/manifest.csv"

echo "=== Step 1: Install scraper dependencies ==="
pip install -r "$SCRAPER_DIR/requirements.txt" -q
python -m playwright install chromium --quiet 2>/dev/null || true

echo ""
echo "=== Step 2: Scrape Learning Center articles ==="
(cd "$SCRAPER_DIR" && python export_luma_learning_center_articles.py --browser)

echo ""
echo "=== Step 3: Ingest new articles ==="
(cd "$REPO_ROOT/backend" && python -m app.scripts.ingest_articles_batch \
  --manifest "$MANIFEST" \
  --continue-on-error)

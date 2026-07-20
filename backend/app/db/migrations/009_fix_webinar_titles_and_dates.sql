-- Migration 009: Backfill webinar_date from title strings, then standardize webinar titles
--
-- Step 1 MUST run before Step 2 — the date info lives in the title and is lost after rename.

-- ── Step 1: Backfill webinar_date where NULL ─────────────────────────────────

-- Pattern: MM-DD-YYYY  (e.g. "03-25-2026")
UPDATE videos
SET webinar_date = TO_DATE(title, 'MM-DD-YYYY')
WHERE content_type = 'webinar'
  AND webinar_date IS NULL
  AND title ~ '^\d{2}-\d{2}-\d{4}$';

-- Pattern: GMT{YYYYMMDD}-...  (e.g. "GMT20260610-165948_Recording_1820x886")
UPDATE videos
SET webinar_date = TO_DATE(substring(title FROM 'GMT(\d{8})'), 'YYYYMMDD')
WHERE content_type = 'webinar'
  AND webinar_date IS NULL
  AND title ~ '^GMT\d{8}[-_]';

-- Pattern: {YYYYMMDD} at start, optionally followed by space + text
-- (e.g. "20260529 Luma Webinar" or bare "20260210")
UPDATE videos
SET webinar_date = TO_DATE(substring(title FROM '^(\d{8})'), 'YYYYMMDD')
WHERE content_type = 'webinar'
  AND webinar_date IS NULL
  AND title ~ '^\d{8}(\s|$)';

-- ── Step 2: Rename all webinar titles ────────────────────────────────────────

UPDATE videos
SET title = 'Luma Weekly Training Session'
WHERE content_type = 'webinar';

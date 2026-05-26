-- Migration 008: Add content_type and source_url to videos table
-- Add section_heading to chunks table for article section linking

-- Add new columns to videos table
ALTER TABLE videos ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'webinar';
ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Add section_heading to chunks table for article section linking
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_heading TEXT;

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_videos_content_type ON videos(content_type);
CREATE INDEX IF NOT EXISTS idx_videos_status_type ON videos(status, content_type);
CREATE INDEX IF NOT EXISTS idx_videos_source_url ON videos(source_url);

-- Mark existing records as webinars (already handled by DEFAULT, but being explicit)
UPDATE videos SET content_type = 'webinar' WHERE content_type IS NULL OR content_type = '';

-- Add comment to explain content_type usage
COMMENT ON COLUMN videos.content_type IS 'Type of content: webinar (video with transcript) or article (text document)';
COMMENT ON COLUMN videos.source_url IS 'Source URL for the content (e.g., Learning Center article URL)';
COMMENT ON COLUMN chunks.section_heading IS 'Section heading for articles, NULL for webinars';

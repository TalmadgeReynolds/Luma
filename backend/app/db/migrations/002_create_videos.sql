-- Create videos table
CREATE TABLE videos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title            TEXT NOT NULL,
    description      TEXT,
    webinar_date     DATE,
    speakers         TEXT[],
    video_url        TEXT,
    duration_seconds INTEGER,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TIMESTAMP DEFAULT NOW(),
    updated_at       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_videos_status ON videos(status);

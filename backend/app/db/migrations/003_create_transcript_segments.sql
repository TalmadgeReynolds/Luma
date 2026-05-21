-- Create transcript_segments table
CREATE TABLE transcript_segments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID REFERENCES videos(id) ON DELETE CASCADE,
    start_time_seconds  FLOAT NOT NULL,
    end_time_seconds    FLOAT NOT NULL,
    speaker             TEXT,
    text                TEXT NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_transcript_segments_video_id ON transcript_segments(video_id);
CREATE INDEX idx_transcript_segments_time ON transcript_segments(video_id, start_time_seconds, end_time_seconds);

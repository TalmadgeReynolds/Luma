-- Create chunks table
-- Note: EMBEDDING_DIMENSION will be substituted by run_migrations.py
CREATE TABLE chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID REFERENCES videos(id) ON DELETE CASCADE,
    start_time_seconds  FLOAT NOT NULL,
    end_time_seconds    FLOAT NOT NULL,
    raw_text            TEXT NOT NULL,
    contextual_text     TEXT NOT NULL,
    summary             TEXT,
    topic_tags          TEXT[],
    questions_answered  TEXT[],
    speaker_names       TEXT[],
    embedding           VECTOR({{EMBEDDING_DIMENSION}}),
    chunk_index         INTEGER,
    word_count          INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_video_id ON chunks(video_id);
CREATE INDEX idx_chunks_time ON chunks(video_id, start_time_seconds, end_time_seconds);
CREATE INDEX idx_chunks_topic_tags ON chunks USING GIN(topic_tags);
CREATE INDEX idx_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_raw_text_idx ON chunks USING gin(to_tsvector('english', raw_text));

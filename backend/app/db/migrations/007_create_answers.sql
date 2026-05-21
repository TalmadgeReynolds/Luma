-- Create answers table
CREATE TABLE answers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id            UUID REFERENCES queries(id) ON DELETE CASCADE,
    answer_text         TEXT NOT NULL,
    source_chunk_ids    UUID[],
    suggested_questions TEXT[],
    confidence          TEXT,
    not_enough_evidence BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_answers_query_id ON answers(query_id);

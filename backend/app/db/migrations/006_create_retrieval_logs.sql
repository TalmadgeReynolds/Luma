-- Create retrieval_logs table
CREATE TABLE retrieval_logs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id          UUID REFERENCES queries(id) ON DELETE CASCADE,
    chunk_id          UUID REFERENCES chunks(id) ON DELETE CASCADE,
    retrieval_method  TEXT,
    retrieval_score   FLOAT,
    rank              INTEGER,
    created_at        TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_retrieval_logs_query_id ON retrieval_logs(query_id);
CREATE INDEX idx_retrieval_logs_chunk_id ON retrieval_logs(chunk_id);

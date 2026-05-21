-- Create queries table
CREATE TABLE queries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_question       TEXT NOT NULL,
    rewritten_question  TEXT,
    search_terms        TEXT[],
    created_at          TIMESTAMP DEFAULT NOW()
);

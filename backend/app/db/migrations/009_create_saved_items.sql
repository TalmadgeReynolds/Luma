-- Create saved_items table for persisting user sidebar saves
CREATE TABLE saved_items (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT NOT NULL,
    type        TEXT NOT NULL,
    label       TEXT NOT NULL,
    detail      TEXT,
    saved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_saved_items_session ON saved_items(session_id);

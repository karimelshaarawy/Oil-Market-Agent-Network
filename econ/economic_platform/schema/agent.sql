CREATE TABLE IF NOT EXISTS agent (
    agent_id    INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    agent_type  TEXT    NOT NULL,  -- 'firm', 'consumer', 'bank', 'refiner', 'speculator'
    sector      TEXT    NOT NULL,
    region      TEXT,              -- geographic region (NULL = no restriction)
    balance     REAL    NOT NULL DEFAULT 0.0,
    produces    TEXT,              -- comma-separated list of allowed good names (NULL = unrestricted)
    created_at  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS good (
    good_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    producer_id INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    quantity    INTEGER NOT NULL DEFAULT 0,
    unit_cost   REAL    NOT NULL DEFAULT 0.0,
    created_at  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (producer_id) REFERENCES agent (agent_id)
);

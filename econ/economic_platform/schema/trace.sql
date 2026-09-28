CREATE TABLE IF NOT EXISTS trace (
    agent_id   INTEGER NOT NULL,
    timestamp  INTEGER NOT NULL,
    action     TEXT    NOT NULL,
    info       TEXT    NOT NULL DEFAULT '{}',
    PRIMARY KEY (agent_id, timestamp, action, info),
    FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
);

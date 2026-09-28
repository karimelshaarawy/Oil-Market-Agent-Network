-- LLM-authored per-step reflections.
-- These are private memory summaries written by each agent after it acts.
CREATE TABLE IF NOT EXISTS agent_reflection (
    reflection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      INTEGER NOT NULL,
    step          INTEGER NOT NULL,
    reflection    TEXT    NOT NULL,
    created_at    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
);


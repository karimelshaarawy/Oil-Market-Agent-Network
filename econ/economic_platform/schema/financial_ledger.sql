-- Per-step financial ledger: records every credit/debit event per agent.
-- amount > 0 = inflow (income), amount < 0 = outflow (expense).
CREATE TABLE IF NOT EXISTS financial_ledger (
    ledger_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    INTEGER NOT NULL,
    step        INTEGER NOT NULL,
    category    TEXT    NOT NULL,  -- 'sale','purchase','production','refinement',
                                   -- 'income_grant','loan_received','loan_repaid'
    amount      REAL    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (agent_id) REFERENCES agent (agent_id)
);

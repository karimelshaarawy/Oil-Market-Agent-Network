CREATE TABLE IF NOT EXISTS loan (
    loan_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    lender_id     INTEGER NOT NULL,
    borrower_id   INTEGER NOT NULL,
    amount        REAL    NOT NULL,
    interest_rate REAL    NOT NULL DEFAULT 0.05,
    borrowed_at   INTEGER NOT NULL DEFAULT 0,
    due_at        INTEGER NOT NULL DEFAULT 0,
    repaid        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (lender_id)   REFERENCES agent (agent_id),
    FOREIGN KEY (borrower_id) REFERENCES agent (agent_id)
);

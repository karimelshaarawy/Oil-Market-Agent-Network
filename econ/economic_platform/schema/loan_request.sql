-- Loan applications awaiting a bank's decision.
--
-- Credit is a deferred request → approve protocol: a borrower files a request
-- in step N (no escrow); the bank sees pending requests in its observation and
-- adjudicates in step N+1 via approve_loan / deny_loan. An approved request
-- disburses funds and creates the matching row in the `loan` table.
CREATE TABLE IF NOT EXISTS loan_request (
    request_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id     INTEGER NOT NULL,
    lender_id       INTEGER NOT NULL,
    amount          REAL    NOT NULL,
    proposed_rate   REAL,                              -- borrower's willingness-to-pay (nullable)
    status          TEXT    NOT NULL DEFAULT 'pending',-- pending | approved | denied | expired
    reason          TEXT,                              -- denial / expiry note
    approved_amount REAL,                              -- set on approval (may be < amount)
    approved_rate   REAL,                              -- set on approval
    loan_id         INTEGER,                           -- the loan created on approval
    requested_at    INTEGER NOT NULL DEFAULT 0,
    decided_at      INTEGER,
    FOREIGN KEY (borrower_id) REFERENCES agent (agent_id),
    FOREIGN KEY (lender_id)   REFERENCES agent (agent_id),
    FOREIGN KEY (loan_id)     REFERENCES loan (loan_id)
);

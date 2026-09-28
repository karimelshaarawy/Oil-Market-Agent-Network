CREATE TABLE IF NOT EXISTS market_transaction (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id       INTEGER NOT NULL,
    seller_id      INTEGER NOT NULL,
    good_name      TEXT    NOT NULL,
    price          REAL    NOT NULL,
    quantity       INTEGER NOT NULL,
    total_paid     REAL    NOT NULL,
    timestamp      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (buyer_id)  REFERENCES agent (agent_id),
    FOREIGN KEY (seller_id) REFERENCES agent (agent_id)
);

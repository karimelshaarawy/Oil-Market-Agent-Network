CREATE TABLE IF NOT EXISTS market_listing (
    listing_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id          INTEGER NOT NULL,
    good_id            INTEGER NOT NULL,
    good_name          TEXT    NOT NULL,
    ask_price          REAL    NOT NULL,
    quantity_available INTEGER NOT NULL DEFAULT 0,
    created_at         INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (seller_id) REFERENCES agent (agent_id),
    FOREIGN KEY (good_id)   REFERENCES good  (good_id)
);

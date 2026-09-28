CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    good_name  TEXT    NOT NULL,
    price      REAL    NOT NULL,
    quantity   INTEGER NOT NULL DEFAULT 1,
    timestamp  INTEGER NOT NULL DEFAULT 0
);

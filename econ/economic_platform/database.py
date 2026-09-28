from __future__ import annotations

import os
import os.path as osp
import sqlite3

_SCHEMA_DIR = osp.join(osp.dirname(__file__), "schema")

_SCHEMA_FILES = [
    "agent.sql",
    "good.sql",
    "market_listing.sql",
    "market_transaction.sql",
    "price_history.sql",
    "loan.sql",
    "loan_request.sql",
    "trace.sql",
    "financial_ledger.sql",
    "agent_reflection.sql",
]

_DB_PATH_ENV = "ECON_DB_PATH"


def get_db_path() -> str:
    env_path = os.environ.get(_DB_PATH_ENV)
    if env_path:
        return env_path
    data_dir = osp.join(osp.dirname(osp.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    return osp.join(data_dir, "economy.db")


def create_db(
    db_path: str,
) -> tuple[sqlite3.Connection, sqlite3.Cursor]:
    """Create (or open) the SQLite database and apply all schema files."""
    os.environ[_DB_PATH_ENV] = db_path
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    for schema_file in _SCHEMA_FILES:
        schema_path = osp.join(_SCHEMA_DIR, schema_file)
        with open(schema_path) as f:
            cursor.executescript(f.read())
    conn.commit()
    return conn, cursor


def fetch_table(
    conn: sqlite3.Connection,
    table_name: str,
) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

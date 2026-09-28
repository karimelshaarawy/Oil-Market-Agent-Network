"""Read-only queries over a completed simulation run's SQLite database.

Shared by the API's REST endpoints and the post-simulation report/interview
services, so knowledge of the run schema lives in one place. Everything here
is a plain SELECT — no simulation state is ever modified.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


class SimulationDBReader:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def exists(self) -> bool:
        return bool(self.db_path) and Path(self.db_path).exists()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Run-level overview ───────────────────────────────────────────────

    def max_step(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(timestamp), 0) AS step FROM trace"
            ).fetchone()
            return int(row["step"] or 0)

    def agents_overview(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT agent_id, name, agent_type, sector, balance FROM agent ORDER BY agent_id"
            ).fetchall()]

    def price_history(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT good_name, price, quantity, timestamp "
                "FROM price_history ORDER BY timestamp ASC, rowid ASC"
            ).fetchall()]

    def transactions(self) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT t.buyer_id, b.name AS buyer, t.seller_id, s.name AS seller, "
                "t.good_name, t.price, t.quantity, t.timestamp "
                "FROM market_transaction t "
                "JOIN agent b ON t.buyer_id = b.agent_id "
                "JOIN agent s ON t.seller_id = s.agent_id "
                "ORDER BY t.timestamp ASC"
            ).fetchall()]

    def balance_history(self) -> list[dict]:
        """Balance over time: cumulative sum per agent per step from ledger."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT a.name, fl.step, ROUND(SUM(fl.amount) OVER "
                "(PARTITION BY fl.agent_id ORDER BY fl.rowid), 2) AS running_balance "
                "FROM financial_ledger fl JOIN agent a ON fl.agent_id = a.agent_id "
                "ORDER BY fl.step ASC, a.name ASC"
            ).fetchall()]

    # ── Per-agent history ────────────────────────────────────────────────

    def agent_row(self, agent_name: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT agent_id, name, agent_type, sector, region FROM agent WHERE name = ?",
                (agent_name,),
            ).fetchone()

    def traces(self, agent_id: int) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT timestamp, action, info FROM trace "
                "WHERE agent_id = ? ORDER BY timestamp ASC, rowid ASC",
                (agent_id,),
            ).fetchall()]

    def ledger(self, agent_id: int) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT step, category, amount, description FROM financial_ledger "
                "WHERE agent_id = ? ORDER BY step ASC, rowid ASC",
                (agent_id,),
            ).fetchall()]

    def balance_steps(self, agent_id: int) -> list[dict]:
        """Balance snapshots per step (running ledger sum)."""
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT step, ROUND(SUM(amount) OVER (ORDER BY rowid), 2) AS balance "
                "FROM financial_ledger WHERE agent_id = ? ORDER BY rowid ASC",
                (agent_id,),
            ).fetchall()]

    def agent_inventory(self, agent_id: int) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT name, SUM(quantity) AS quantity, "
                "ROUND(AVG(unit_cost), 4) AS avg_unit_cost "
                "FROM good WHERE producer_id = ? AND quantity > 0 GROUP BY name",
                (agent_id,),
            ).fetchall()]

    def recent_reflection_rows(self, agent_id: int, limit: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT step, substr(reflection, 1, 600) AS reflection
                FROM agent_reflection
                WHERE agent_id = ?
                ORDER BY step DESC
                LIMIT ?
                """,
                (agent_id, int(limit)),
            ).fetchall()

    def recent_ledger_rows(self, agent_id: int, limit: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT step, category, ROUND(amount, 4) AS amount, substr(description, 1, 220) AS description
                FROM financial_ledger
                WHERE agent_id = ?
                ORDER BY step DESC, ledger_id DESC
                LIMIT ?
                """,
                (agent_id, int(limit)),
            ).fetchall()

    # ── Report summaries (rows only — text formatting stays in ReportAgent) ──

    def balances_after_debt_rows(self, limit: int = 20) -> list[sqlite3.Row]:
        sql = """
        SELECT a.name, a.agent_type, ROUND(a.balance, 2) AS balance,
               ROUND(COALESCE((SELECT SUM(amount) FROM loan
                               WHERE borrower_id = a.agent_id AND repaid = 0), 0), 2) AS debt,
               ROUND(a.balance - COALESCE((SELECT SUM(amount) FROM loan
                                           WHERE borrower_id = a.agent_id AND repaid = 0), 0), 2)
                    AS net_after_debt
        FROM agent a
        ORDER BY net_after_debt DESC
        """
        return self._fetch(sql, limit)

    def transaction_summary_rows(self, limit: int = 20) -> list[sqlite3.Row]:
        sql = """
        SELECT good_name, COUNT(*) AS tx_count, ROUND(AVG(price), 2) AS avg_price,
               ROUND(MIN(price), 2) AS min_price, ROUND(MAX(price), 2) AS max_price,
               SUM(quantity) AS total_qty
        FROM market_transaction
        GROUP BY good_name
        ORDER BY good_name
        """
        return self._fetch(sql, limit)

    def price_by_step_rows(self, limit: int = 30) -> list[sqlite3.Row]:
        sql = """
        SELECT timestamp AS step, good_name, ROUND(AVG(price), 2) AS avg_price,
               SUM(quantity) AS qty
        FROM market_transaction
        GROUP BY timestamp, good_name
        ORDER BY timestamp, good_name
        """
        return self._fetch(sql, limit)

    def loan_summary_rows(self, limit: int = 40) -> list[sqlite3.Row]:
        sql = """
        SELECT borrower.name AS borrower, lender.name AS lender,
               ROUND(loan.amount, 2) AS amount, loan.borrowed_at,
               loan.due_at, loan.repaid
        FROM loan
        JOIN agent borrower ON borrower.agent_id = loan.borrower_id
        JOIN agent lender ON lender.agent_id = loan.lender_id
        ORDER BY loan.borrowed_at, loan.loan_id
        """
        return self._fetch(sql, limit)

    def reflection_overview_rows(self, limit: int = 12) -> list[sqlite3.Row]:
        sql = """
        SELECT ar.step, a.name, substr(ar.reflection, 1, 180) AS reflection
        FROM agent_reflection ar
        JOIN agent a ON a.agent_id = ar.agent_id
        ORDER BY ar.step DESC, ar.agent_id ASC
        """
        return self._fetch(sql, limit)

    def _fetch(self, sql: str, limit: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(sql).fetchmany(limit)

"""Agent balances and the financial ledger (every credit/debit event)."""
from __future__ import annotations

import logging

from econ.economic_platform.context import PlatformContext

logger = logging.getLogger(__name__)


class LedgerService:
    def __init__(self, ctx: PlatformContext) -> None:
        self.ctx = ctx

    def record(
        self,
        agent_id: int,
        category: str,
        amount: float,
        description: str = "",
    ) -> None:
        """Write one financial event to the ledger.

        amount > 0 = inflow (income / revenue).
        amount < 0 = outflow (cost / expense).
        """
        step = self.ctx.clock.now()
        try:
            self.ctx.execute(
                "INSERT INTO financial_ledger "
                "(agent_id, step, category, amount, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (agent_id, step, category, round(amount, 4), description),
                commit=True,
            )
        except Exception as exc:
            logger.warning("ledger insert failed: %s", exc)

    def balance(self, agent_id: int) -> float:
        row = self.ctx.execute(
            "SELECT balance FROM agent WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return float(row["balance"]) if row else 0.0

    def credit(self, agent_id: int, amount: float) -> None:
        self.ctx.execute(
            "UPDATE agent SET balance = balance + ? WHERE agent_id = ?",
            (amount, agent_id),
            commit=True,
        )

    def debit(self, agent_id: int, amount: float) -> bool:
        balance = self.balance(agent_id)
        if balance < amount:
            return False
        self.ctx.execute(
            "UPDATE agent SET balance = balance - ? WHERE agent_id = ?",
            (amount, agent_id),
            commit=True,
        )
        return True

    def force_debit(self, agent_id: int, amount: float) -> None:
        """Decrement the balance even below zero (e.g. operating losses)."""
        self.ctx.execute(
            "UPDATE agent SET balance = balance - ? WHERE agent_id = ?",
            (amount, agent_id),
            commit=True,
        )

    def step_financials(self, agent_id: int, step: int) -> tuple[float, float]:
        """Return (income, expenses) recorded during one step."""
        rows = self.ctx.execute(
            "SELECT category, amount FROM financial_ledger "
            "WHERE agent_id = ? AND step = ?",
            (agent_id, step),
        ).fetchall()
        income = round(sum(r["amount"] for r in rows if r["amount"] > 0), 4)
        expenses = round(sum(-r["amount"] for r in rows if r["amount"] < 0), 4)
        return income, expenses

    def all_time_financials(self, agent_id: int) -> tuple[float, float]:
        """Return (total_income, total_expenses) across the whole run."""
        rows = self.ctx.execute(
            "SELECT amount FROM financial_ledger WHERE agent_id = ?",
            (agent_id,),
        ).fetchall()
        income = round(sum(r["amount"] for r in rows if r["amount"] > 0), 4)
        expenses = round(sum(-r["amount"] for r in rows if r["amount"] < 0), 4)
        return income, expenses

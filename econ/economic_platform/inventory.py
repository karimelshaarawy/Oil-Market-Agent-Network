"""Goods production, refinement, and FIFO inventory consumption."""
from __future__ import annotations

from econ.economic_platform.context import PlatformContext
from econ.economic_platform.ledger import LedgerService
from econ.economic_platform.typing import ActionType


class InventoryService:
    def __init__(self, ctx: PlatformContext, ledger: LedgerService) -> None:
        self.ctx = ctx
        self.ledger = ledger

    def consume_fifo(self, agent_id: int, good_name: str, quantity: int) -> tuple[int, float]:
        """Consume unlisted inventory FIFO and return (units_consumed, cost_basis)."""
        remaining = int(quantity)
        consumed = 0
        cost_basis = 0.0
        rows = self.ctx.execute(
            "SELECT good_id, quantity, unit_cost FROM good "
            "WHERE producer_id = ? AND name = ? AND quantity > 0 ORDER BY good_id ASC",
            (agent_id, good_name),
        ).fetchall()
        for row in rows:
            if remaining <= 0:
                break
            deduct = min(row["quantity"], remaining)
            self.ctx.execute(
                "UPDATE good SET quantity = quantity - ? WHERE good_id = ?",
                (deduct, row["good_id"]),
                commit=True,
            )
            consumed += deduct
            cost_basis += deduct * float(row["unit_cost"] or 0.0)
            remaining -= deduct
        return consumed, round(cost_basis, 4)

    def summary(self, agent_id: int) -> list[dict]:
        """Per-good inventory totals with average and latest unit cost."""
        rows = self.ctx.execute(
            """SELECT g.name,
                      SUM(g.quantity) AS total_quantity,
                      ROUND(
                          CASE WHEN SUM(g.quantity) > 0
                               THEN SUM(g.quantity * g.unit_cost) / SUM(g.quantity)
                               ELSE 0.0 END,
                      4) AS avg_unit_cost,
                      ROUND(
                          (SELECT unit_cost FROM good
                           WHERE producer_id = g.producer_id
                             AND name = g.name
                             AND quantity > 0
                           ORDER BY created_at DESC
                           LIMIT 1),
                      4) AS latest_unit_cost
               FROM good g
               WHERE g.producer_id = ? AND g.quantity > 0
               GROUP BY g.name""",
            (agent_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    async def produce(self, agent_id: int, message) -> dict:
        """Produce goods.  Deducts production cost (unit_cost * quantity) from balance.

        message: (good_name: str, quantity: int, unit_cost: float)
        """
        good_name, quantity, unit_cost = message
        quantity = int(quantity)
        unit_cost = float(unit_cost)

        if unit_cost <= 0:
            return {
                "success": False,
                "error": (
                    f"unit_cost must be greater than 0 (got {unit_cost}). "
                    "Check your PRODUCTION COSTS section for the correct value."
                ),
            }

        total_cost = round(quantity * unit_cost, 4)
        ts = self.ctx.clock.now()

        # Enforce per-agent production restrictions stored at registration.
        agent_row = self.ctx.execute(
            "SELECT produces FROM agent WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if agent_row and agent_row["produces"]:
            allowed = [g.strip() for g in agent_row["produces"].split(",")]
            if good_name not in allowed:
                return {
                    "success": False,
                    "error": (
                        f"You are not authorised to produce {good_name!r}. "
                        f"Your production is restricted to: {', '.join(allowed)}."
                    ),
                }

        if not self.ledger.debit(agent_id, total_cost):
            return {"success": False,
                    "error": f"Insufficient balance to produce {quantity} units "
                             f"of {good_name!r} (cost={total_cost:.2f})"}

        cursor = self.ctx.execute(
            "INSERT INTO good (producer_id, name, quantity, unit_cost, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (agent_id, good_name, quantity, unit_cost, ts),
            commit=True,
        )
        good_id = cursor.lastrowid
        self.ledger.record(
            agent_id, "production", -total_cost,
            f"Produced {quantity} × {good_name} @ {unit_cost:.2f}/unit",
        )
        self.ctx.record_trace(agent_id, ActionType.PRODUCE.value,
                              {"good_name": good_name, "quantity": quantity,
                               "unit_cost": unit_cost, "total_cost": total_cost,
                               "good_id": good_id})
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "produce",
            "good": good_name,
            "qty": quantity,
            "price": unit_cost,
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": f"Produced {quantity} {good_name} @ ${unit_cost:.2f}/unit",
        })
        return {"success": True, "good_id": good_id,
                "good_name": good_name, "quantity": quantity,
                "cost_incurred": total_cost}

    async def refine(self, agent_id: int, message) -> dict:
        """Convert input goods into refined output goods.

        Checks the agent owns enough unlisted input goods, consumes them
        (deducted from the good table FIFO), charges a conversion cost, and
        writes a new good row for the output.  The returned output_good_id can
        be passed directly to list_good().

        message: (input_good: str, input_qty: int, output_good: str,
                  output_qty: int, conversion_cost_per_unit: float)
        """
        input_good, input_qty, output_good, output_qty, conversion_cost = message
        input_qty = int(input_qty)
        output_qty = int(output_qty)
        conversion_cost = float(conversion_cost)
        total_cost = round(conversion_cost * output_qty, 4)
        ts = self.ctx.clock.now()

        # Enforce per-agent output restrictions for refiners.
        agent_row = self.ctx.execute(
            "SELECT produces FROM agent WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if agent_row and agent_row["produces"]:
            allowed = [g.strip() for g in agent_row["produces"].split(",")]
            if output_good not in allowed:
                return {
                    "success": False,
                    "error": (
                        f"You are not authorised to produce {output_good!r} via refine. "
                        f"Your output is restricted to: {', '.join(allowed)}."
                    ),
                }

        # list_good() already reduces good.quantity when goods are listed, so
        # good.quantity represents only unlisted (available) inventory.
        available = self.ctx.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM good "
            "WHERE producer_id = ? AND name = ?",
            (agent_id, input_good),
        ).fetchone()[0]

        if available < input_qty:
            return {
                "success": False,
                "error": (
                    f"Insufficient {input_good!r} in inventory: {available} units "
                    f"available, need {input_qty}. "
                    "Bid for more crude_oil (place_bid) — it settles next step — "
                    "or delist some existing listings."
                ),
            }

        if not self.ledger.debit(agent_id, total_cost):
            return {
                "success": False,
                "error": f"Insufficient balance for conversion cost {total_cost:.2f}",
            }

        # Consume input goods FIFO across good rows and carry their purchase
        # cost into the refined output's inventory cost basis.
        consumed_qty, input_cost_basis = self.consume_fifo(
            agent_id, input_good, input_qty
        )
        if consumed_qty < input_qty:
            return {
                "success": False,
                "error": (
                    f"Unexpected inventory shortfall while refining: consumed "
                    f"{consumed_qty}/{input_qty} units of {input_good}."
                ),
            }

        # Produce the refined output.
        total_output_cost = round(input_cost_basis + total_cost, 4)
        unit_cost = round(total_output_cost / output_qty, 4) if output_qty > 0 else 0.0
        cursor = self.ctx.execute(
            "INSERT INTO good (producer_id, name, quantity, unit_cost, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (agent_id, output_good, output_qty, unit_cost, ts),
            commit=True,
        )
        output_good_id = cursor.lastrowid

        self.ledger.record(
            agent_id, "refinement", -total_cost,
            f"Refined {input_qty} × {input_good} → {output_qty} × {output_good} "
            f"(input cost basis {input_cost_basis:.2f}, conversion cost {total_cost:.2f})",
        )
        self.ctx.record_trace(agent_id, ActionType.REFINE.value, {
            "input_good": input_good, "input_qty_consumed": input_qty,
            "output_good": output_good, "output_qty": output_qty,
            "input_cost_basis": input_cost_basis,
            "conversion_cost": total_cost,
            "total_output_cost": total_output_cost,
            "break_even_unit_cost": unit_cost,
            "output_good_id": output_good_id,
        })
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "refine",
            "good": output_good,
            "qty": output_qty,
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": f"Refined {input_qty} {input_good} → {output_qty} {output_good}",
        })
        return {
            "success": True,
            "input_good": input_good,
            "input_qty_consumed": input_qty,
            "output_good": output_good,
            "output_good_id": output_good_id,
            "output_qty": output_qty,
            "input_cost_basis": input_cost_basis,
            "conversion_cost": total_cost,
            "total_output_cost": total_output_cost,
            "break_even_unit_cost": unit_cost,
        }

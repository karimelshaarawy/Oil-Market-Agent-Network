"""Consumer operating needs: price-elastic consumption, revenue, and income grants."""
from __future__ import annotations

from econ.core.demand import target_from_need
from econ.economic_platform.context import PlatformContext
from econ.economic_platform.inventory import InventoryService
from econ.economic_platform.ledger import LedgerService
from econ.economic_platform.market import MarketService


class ConsumerOperationsService:
    def __init__(
        self,
        ctx: PlatformContext,
        ledger: LedgerService,
        inventory: InventoryService,
        market: MarketService,
    ) -> None:
        self.ctx = ctx
        self.ledger = ledger
        self.inventory = inventory
        self.market = market

    def apply(self, step: int) -> None:
        """Run every consumer's operating needs for one step.

        Consumes required inputs from inventory FIFO to earn operating
        revenue (with price pass-through), and applies shortage penalties
        when essential inputs are missing.
        """
        consumers = self.ctx.execute(
            "SELECT agent_id, name FROM agent WHERE agent_type = 'consumer'",
        ).fetchall()
        for row in consumers:
            agent_id = int(row["agent_id"])
            profile = self.ctx.agent_profile(agent_id)
            needs = profile.get("consumption_needs") or []
            for need in needs:
                good_name = str(need.get("good_name", "")).strip()
                base_required = int(need.get("quantity_per_step", 0) or 0)
                if not good_name or base_required <= 0:
                    continue

                # Demand is price-elastic: the operating target this step scales
                # with the good's clearing price, so a consumer that rationally
                # buys less when prices spike is not penalised for the units it
                # never needed. Falls back to recent average → base when the
                # good has not cleared yet.
                market_price = (
                    self.market.last_clearing_price(good_name)
                    or self.market.recent_average_price(good_name)
                )
                required = target_from_need(need, market_price)
                if required <= 0:
                    continue

                consumed, cost_basis = self.inventory.consume_fifo(agent_id, good_name, required)
                # Shortage is assessed only against the inelastic core, never
                # above the base need. At HIGH prices the elastic target is below
                # base, so the reduced target is the baseline (demand destruction
                # is not punished). At LOW prices the target rises above base to
                # let the consumer profitably run hotter, but failing to expand
                # consumption of a cheap input is not an essential shortage — so
                # the penalty baseline is capped at base. Revenue still scales
                # with everything actually consumed (up to the full target).
                essential = min(required, base_required)
                shortage = max(0, essential - consumed)

                reference_price = float(need.get("reference_price", 1.0) or 1.0)
                avg_consumed_unit_cost = (
                    round(cost_basis / consumed, 4)
                    if consumed > 0
                    else self.market.recent_average_price(good_name) or reference_price
                )
                pass_through = float(need.get("price_pass_through", 0.0) or 0.0)
                base_revenue = float(need.get("revenue_per_unit", 0.0) or 0.0)
                price_pressure = max(0.0, (avg_consumed_unit_cost / reference_price) - 1.0)
                revenue_per_unit = round(base_revenue * (1 + pass_through * price_pressure), 4)
                operating_revenue = round(consumed * revenue_per_unit, 4)
                if operating_revenue > 0:
                    self.ledger.credit(agent_id, operating_revenue)
                    self.ledger.record(
                        agent_id,
                        "operating_revenue",
                        operating_revenue,
                        (
                            f"Consumed {consumed}/{required} × {good_name} for operations "
                            f"@ revenue {revenue_per_unit:.2f}/unit "
                            f"(avg consumed input cost {avg_consumed_unit_cost:.2f}, "
                            f"total cost basis {cost_basis:.2f})"
                        ),
                    )

                penalty_per_unit = float(need.get("shortage_penalty_per_unit", 0.0) or 0.0)
                # Shortage penalties are postponed during the grace window so the
                # auction's demand side can ramp up before unmet needs cost credits.
                in_grace = step <= self.ctx.shortage_penalty_grace_steps
                shortage_penalty = 0.0 if in_grace else round(shortage * penalty_per_unit, 4)
                if shortage_penalty > 0:
                    # A shortage is an operating loss, so allow it to push balance lower.
                    self.ledger.force_debit(agent_id, shortage_penalty)
                    self.ledger.record(
                        agent_id,
                        "shortage_penalty",
                        -shortage_penalty,
                        f"Short {shortage}/{required} × {good_name}; lost operations at step {step}",
                    )

                self.ctx.record_trace(
                    agent_id,
                    "consume_need",
                    {
                        "good_name": good_name,
                        "base_required": base_required,
                        "market_price": market_price,
                        "required": required,
                        "consumed": consumed,
                        "shortage": shortage,
                        "avg_consumed_unit_cost": avg_consumed_unit_cost,
                        "revenue_per_unit": revenue_per_unit,
                        "operating_revenue": operating_revenue,
                        "shortage_penalty": shortage_penalty,
                    },
                )

    def grant_income(self, step: int, amount: float) -> None:
        """Credit every consumer a flat periodic income."""
        consumers = self.ctx.execute(
            "SELECT agent_id, name FROM agent WHERE agent_type = 'consumer'",
        ).fetchall()
        for row in consumers:
            aid = row["agent_id"]
            self.ledger.credit(aid, amount)
            self.ledger.record(
                aid,
                "income_grant",
                amount,
                f"Step {step} periodic income",
            )

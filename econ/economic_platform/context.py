"""Shared infrastructure for platform components.

``PlatformContext`` owns what every component needs: the SQLite connection,
the simulation clock, agent profiles, transport costs, the optional event
bus, and the economy tunables. Components receive it by reference, so the
platform stays the single place where all of this is wired together.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Awaitable, Callable

from econ.clock.clock import Clock
from econ.core.profile_store import ProfileStore
from econ.core.transport_costs import TransportCostProvider

logger = logging.getLogger(__name__)


class PlatformContext:
    def __init__(
        self,
        db: sqlite3.Connection,
        clock: Clock,
        profile_store: ProfileStore,
        transport_costs: TransportCostProvider,
        event_bus: Callable[[dict], Awaitable[None]] | None,
        *,
        interest_rate: float,
        loan_duration_steps: int,
        price_history_window: int,
        consumer_income_per_step: float,
        consumer_operations_enabled: bool,
        auto_cancel_steps: int,
        shortage_penalty_grace_steps: int,
        max_borrow_fraction: float,
        min_interest_rate: float,
        max_interest_rate: float,
        loan_request_expiry_steps: int,
    ) -> None:
        self.db = db
        self.clock = clock
        self.profile_store = profile_store
        self.transport_costs = transport_costs
        self.event_bus = event_bus
        self.interest_rate = interest_rate
        self.loan_duration_steps = loan_duration_steps
        self.price_history_window = price_history_window
        self.consumer_income_per_step = consumer_income_per_step
        self.consumer_operations_enabled = consumer_operations_enabled
        # Number of full steps an unsold ask may rest on the book before it is
        # automatically cancelled (its remaining stock returned to the seller's
        # inventory). The call auction performs price discovery, so there is no
        # automatic price decay; auto-cancel only keeps the book from filling
        # with permanently-overpriced asks and forces a fresh pricing decision.
        # 0 disables auto-cancel.
        self.auto_cancel_steps = auto_cancel_steps
        # Grace window: consumer shortage penalties are waived for steps with
        # step <= shortage_penalty_grace_steps, giving the auction's demand side
        # time to ramp up before unmet needs start costing credits. Consumption
        # and operating revenue still apply during the grace window; only the
        # penalty is postponed. 0 = no grace (penalise from the first step).
        self.shortage_penalty_grace_steps = shortage_penalty_grace_steps
        # Maximum fraction of the lender's current balance a single loan can be.
        # Under endogenous credit this is a SOFT signal surfaced to the bank in
        # its loan-desk view ("this loan is X% of your capital"), not a hard cap —
        # sizing risk is the bank's judgment. It is still shown for guidance.
        self.max_borrow_fraction = max_borrow_fraction
        # The bank chooses a per-loan rate when approving; it is clamped to this
        # band. ``interest_rate`` is the reference / fallback rate.
        self.min_interest_rate = min_interest_rate
        self.max_interest_rate = max_interest_rate
        # A pending loan request the bank neither approves nor denies within this
        # many steps is auto-expired in update_market_state(). 0 disables expiry.
        self.loan_request_expiry_steps = loan_request_expiry_steps

    def execute(self, sql: str, params: tuple = (), commit: bool = False) -> sqlite3.Cursor:
        cursor = self.db.cursor()
        cursor.execute(sql, params)
        if commit:
            self.db.commit()
        return cursor

    def record_trace(self, agent_id: int, action: str, info: dict) -> None:
        ts = self.clock.now()
        info_str = json.dumps(info)
        try:
            self.execute(
                "INSERT OR IGNORE INTO trace (agent_id, timestamp, action, info) "
                "VALUES (?, ?, ?, ?)",
                (agent_id, ts, action, info_str),
                commit=True,
            )
        except Exception as exc:
            logger.warning("trace insert failed: %s", exc)

    async def emit(self, event: dict) -> None:
        if self.event_bus is not None:
            await self.event_bus(event)

    def agent_name(self, agent_id: int) -> str:
        row = self.execute(
            "SELECT name FROM agent WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return row["name"] if row else str(agent_id)

    def agent_profile(self, agent_id: int) -> dict[str, Any]:
        return dict(self.profile_store.get_profile(int(agent_id)))

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from econ.clock.clock import Clock
from econ.core.config import (
    LOAN_REQUEST_EXPIRY_STEPS,
    MAX_INTEREST_RATE,
    MIN_INTEREST_RATE,
)
from econ.core.profile_store import ProfileStore
from econ.core.transport_costs import TransportCostProvider
from econ.economic_platform.channel import Channel
from econ.economic_platform.consumer_ops import ConsumerOperationsService
from econ.economic_platform.context import PlatformContext
from econ.economic_platform.database import create_db
from econ.economic_platform.inventory import InventoryService
from econ.economic_platform.ledger import LedgerService
from econ.economic_platform.loans import LoanService
from econ.economic_platform.market import MarketService
from econ.economic_platform.typing import ActionType

logger = logging.getLogger(__name__)


class EconomicPlatform:
    """The simulated economy backend.

    Runs as a perpetual asyncio task (``await platform.running()``).
    Reads action requests from the ``Channel``, processes them against the
    SQLite database, and writes results back through the ``Channel``.

    Action dispatch uses reflection: the
    ``ActionType`` enum value must match a method name on this class exactly.
    Methods may have signature ``(self, agent_id)`` or
    ``(self, agent_id, message)``.

    The economy rules themselves live in focused components, each sharing one
    :class:`PlatformContext` (DB connection, clock, profiles, tunables):

    - :class:`LedgerService` (``self.ledger``) — balances + financial ledger
    - :class:`InventoryService` (``self.inventory``) — produce / refine / FIFO
    - :class:`MarketService` (``self.market``) — listings, trades, prices
    - :class:`LoanService` (``self.loans``) — loan requests, bank adjudication,
      and repayment
    - :class:`ConsumerOperationsService` (``self.consumer_ops``) — consumer
      needs and income grants

    This class stays the single dispatch surface: every action method here is
    a thin delegate, so the Channel/ActionType contract is unchanged.
    """

    def __init__(
        self,
        db_path: str,
        profile_store: ProfileStore,
        transport_costs: TransportCostProvider,
        channel: Channel | None = None,
        clock: Clock | None = None,
        interest_rate: float = 0.05,
        loan_duration_steps: int = 10,
        price_history_window: int = 20,
        consumer_income_per_step: float = 0.0,
        consumer_operations_enabled: bool = True,
        auto_cancel_steps: int = 3,
        shortage_penalty_grace_steps: int = 0,
        max_borrow_fraction: float = 0.5,
        min_interest_rate: float = MIN_INTEREST_RATE,
        max_interest_rate: float = MAX_INTEREST_RATE,
        loan_request_expiry_steps: int = LOAN_REQUEST_EXPIRY_STEPS,
        event_bus: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self.db_path = db_path
        self.channel = channel or Channel()
        self.clock = clock or Clock()
        self.db, self.db_cursor = create_db(db_path)
        self.db.execute("PRAGMA synchronous = OFF")
        self.db.execute("PRAGMA journal_mode = WAL")

        self.ctx = PlatformContext(
            db=self.db,
            clock=self.clock,
            profile_store=profile_store,
            transport_costs=transport_costs,
            event_bus=event_bus,
            interest_rate=interest_rate,
            loan_duration_steps=loan_duration_steps,
            price_history_window=price_history_window,
            consumer_income_per_step=consumer_income_per_step,
            consumer_operations_enabled=consumer_operations_enabled,
            auto_cancel_steps=int(auto_cancel_steps),
            shortage_penalty_grace_steps=int(shortage_penalty_grace_steps),
            max_borrow_fraction=float(max_borrow_fraction),
            min_interest_rate=float(min_interest_rate),
            max_interest_rate=float(max_interest_rate),
            loan_request_expiry_steps=int(loan_request_expiry_steps),
        )
        self.ledger = LedgerService(self.ctx)
        self.inventory = InventoryService(self.ctx, self.ledger)
        self.market = MarketService(self.ctx, self.ledger)
        self.loans = LoanService(self.ctx, self.ledger)
        self.consumer_ops = ConsumerOperationsService(
            self.ctx, self.ledger, self.inventory, self.market
        )

    # ── Simulation loop ──────────────────────────────────────────────────

    async def running(self) -> None:
        """Perpetual event loop — read channel, dispatch action, return result."""
        try:
            while True:
                message_id, data = await self.channel.receive_from()
                agent_id, message, action = data
                action = ActionType(action)

                if action == ActionType.EXIT:
                    break

                action_function = getattr(self, action.value, None)
                if action_function is None:
                    raise ValueError(f"Action {action.value!r} has no handler on EconomicPlatform")

                func_code = action_function.__code__
                param_names = func_code.co_varnames[:func_code.co_argcount]
                n = len(param_names)
                if n > 3:
                    raise ValueError(f"Handler {action.value!r} has too many parameters ({n})")

                params: dict[str, Any] = {}
                if n >= 2:
                    params["agent_id"] = agent_id
                if n == 3:
                    params[param_names[2]] = message

                result = await action_function(**params)
                await self.channel.send_to((message_id, agent_id, result))
        finally:
            # Close DB cleanly on EXIT, exception, or cancellation.
            try:
                self.db_cursor.close()
                self.db.close()
            except Exception:
                pass

    # ── Reflection persistence ───────────────────────────────────────────

    def record_agent_reflection(
        self,
        agent_id: int,
        step: int,
        reflection: str,
    ) -> None:
        """Persist one LLM-authored agent reflection in SQLite."""
        if not reflection.strip():
            return
        try:
            self.ctx.execute(
                "INSERT INTO agent_reflection "
                "(agent_id, step, reflection, created_at) "
                "VALUES (?, ?, ?, ?)",
                (agent_id, step, reflection.strip(), self.clock.now()),
                commit=True,
            )
        except Exception as exc:
            logger.warning("agent reflection insert failed: %s", exc)

    # ── Pre-step hook ────────────────────────────────────────────────────

    async def update_market_state(self) -> None:
        """Called once before every ``EconomicEnv.step()``.

        1. Removes fully-exhausted market listings.
        2. Auto-cancels asks that have rested unfilled past ``auto_cancel_steps``
           (their stock returns to the seller's inventory). The call auction
           handles price discovery, so prices are never decayed automatically;
           this only keeps stale, never-clearing asks from accumulating.
        3. Resets any leftover sealed bids (defensive — bids are per-step).

        Consumer operating needs (inventory consumption + shortage penalty)
        are applied *after* agent actions via ``apply_consumer_needs()``,
        so agents have a chance to buy required inputs before being penalised.
        """
        step = self.clock.now()

        self.market.purge_exhausted()
        self.market.reset_pending_bids()

        if self.ctx.consumer_income_per_step > 0:
            self.consumer_ops.grant_income(step, self.ctx.consumer_income_per_step)

        if self.ctx.auto_cancel_steps > 0 and step > 0:
            self.market.auto_cancel_stale(step, self.ctx.auto_cancel_steps)

        if self.ctx.loan_request_expiry_steps > 0 and step > 0:
            self.loans.expire_stale_requests(step, self.ctx.loan_request_expiry_steps)

    async def clear_market(self) -> list[dict]:
        """Clear the call auction for the current step.

        Called by ``EconomicEnv.step()`` *after* all agent actions and *before*
        ``apply_consumer_needs()``, so a consumer's winning bid can feed the
        same step's consumption while refiners/speculators carry a 1-step lag.
        """
        return await self.market.clear(self.clock.now())

    async def apply_consumer_needs(self) -> None:
        """Called once *after* agent actions in every ``EconomicEnv.step()``.

        Consumes required inputs from each consumer's inventory (FIFO) to earn
        operating revenue, then assesses shortage penalties for any unmet needs.
        Running this post-actions means agents can buy/produce required goods
        during the step before the shortage check fires.
        """
        step = self.clock.now()
        if self.ctx.consumer_operations_enabled and step > 0:
            self.consumer_ops.apply(step)

    # ── Action handlers ──────────────────────────────────────────────────
    # Each method name must match ActionType.<NAME>.value exactly.
    # Signature: (self, agent_id) or (self, agent_id, message).

    async def register(self, agent_id: int, message) -> dict:
        """Register a new agent in the economy (called during env.reset())."""
        name, agent_type, sector, initial_balance, region, produces = message
        # produces is a list; store as comma-separated string (empty = unrestricted).
        produces_str = ",".join(produces) if produces else None
        ts = self.clock.now()
        self.ctx.execute(
            "INSERT OR REPLACE INTO agent "
            "(agent_id, name, agent_type, sector, region, balance, produces, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (agent_id, name, agent_type, sector, region,
             float(initial_balance), produces_str, ts),
            commit=True,
        )
        self.ctx.record_trace(agent_id, ActionType.REGISTER.value,
                              {"name": name, "agent_type": agent_type,
                               "sector": sector, "region": region,
                               "produces": produces,
                               "initial_balance": initial_balance})
        return {"success": True, "agent_id": agent_id}

    async def observe_market(self, agent_id: int) -> dict:
        """Return current market listings and recent transaction prices."""
        return await self.market.observe_market(agent_id)

    async def produce(self, agent_id: int, message) -> dict:
        """Produce goods; message: (good_name, quantity, unit_cost)."""
        return await self.inventory.produce(agent_id, message)

    async def refine(self, agent_id: int, message) -> dict:
        """Refine input goods into outputs; message: (input_good, input_qty,
        output_good, output_qty, conversion_cost_per_unit)."""
        return await self.inventory.refine(agent_id, message)

    async def list_good(self, agent_id: int, message) -> dict:
        """List goods on the market; message: (good_id, ask_price, quantity)."""
        return await self.market.list_good(agent_id, message)

    async def update_listing_price(self, agent_id: int, message) -> dict:
        """Reprice an own listing; message: (listing_id, new_price)."""
        return await self.market.update_listing_price(agent_id, message)

    async def place_bid(self, agent_id: int, message) -> dict:
        """Submit a sealed buy order; message: (good_name, limit_price, quantity)."""
        return await self.market.place_bid(agent_id, message)

    async def check_balance(self, agent_id: int) -> dict:
        """Return the agent's current balance, inventory, outstanding loans,
        and a financial P&L summary for the current step and all time."""
        agent = self.ctx.execute(
            "SELECT * FROM agent WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if agent is None:
            return {"success": False, "error": f"agent_id {agent_id} not found"}

        step = self.clock.now()
        inventory = self.inventory.summary(agent_id)
        own_listings = self.market.own_listings(agent_id, step)
        loans = self.loans.active_loans(agent_id, step)
        step_income, step_expenses = self.ledger.step_financials(agent_id, step)
        total_income, total_expenses = self.ledger.all_time_financials(agent_id)
        profile = self.ctx.agent_profile(agent_id)
        consumer_needs = profile.get("consumption_needs") or []

        self.ctx.record_trace(agent_id, ActionType.CHECK_BALANCE.value, {})
        result = {
            "success": True,
            "balance": round(float(agent["balance"]), 4),
            "agent_type": agent["agent_type"],
            "sector": agent["sector"],
            "inventory": inventory,
            "consumption_needs": consumer_needs,
            "own_active_listings": own_listings,
            "active_loans": loans,
            "this_step_financials": {
                "step": step,
                "income": step_income,
                "expenses": step_expenses,
                "net": round(step_income - step_expenses, 4),
            },
            "all_time_financials": {
                "total_income": total_income,
                "total_expenses": total_expenses,
                "net_profit": round(total_income - total_expenses, 4),
            },
        }
        # Banks also see their loan desk: pending applications + applicant
        # dossiers, so the LLM can approve/deny/set-rate from one observation.
        if agent["agent_type"] == "bank":
            result["pending_loan_requests"] = self.loans.pending_requests_for_lender(
                agent_id, step
            )
        return result

    async def check_price_history(self, agent_id: int, message) -> dict:
        """Recent transaction prices for a good; message: good_name (str)."""
        return await self.market.check_price_history(agent_id, message)

    async def request_loan(self, agent_id: int, message) -> dict:
        """File a loan application with a bank; message: (lender_id, amount,
        proposed_rate). Queued for the bank to adjudicate next step."""
        return await self.loans.request_loan(agent_id, message)

    async def approve_loan(self, agent_id: int, message) -> dict:
        """Bank approves a pending request; message: (request_id, rate,
        approved_amount). Disburses funds and creates the loan."""
        return await self.loans.approve_loan(agent_id, message)

    async def deny_loan(self, agent_id: int, message) -> dict:
        """Bank denies a pending request; message: (request_id, reason)."""
        return await self.loans.deny_loan(agent_id, message)

    async def repay(self, agent_id: int, message) -> dict:
        """Repay a loan; message: loan_id (int)."""
        return await self.loans.repay(agent_id, message)

    async def search_goods(self, agent_id: int, message) -> dict:
        """Search listings by good name keyword; message: query (str)."""
        return await self.market.search_goods(agent_id, message)

    async def search_agents(self, agent_id: int, message) -> dict:
        """Search agents by name or type; message: query (str)."""
        return await self.market.search_agents(agent_id, message)

    async def do_nothing(self, agent_id: int) -> dict:
        """Perform no action this step."""
        self.ctx.record_trace(agent_id, ActionType.DO_NOTHING.value, {})
        return {"success": True}

    async def interview(self, agent_id: int, message) -> dict:
        """Record an interview prompt/response pair.  Used by researchers
        to query agent beliefs without affecting the market.

        message: {"prompt": str, "response": str}
        """
        ts = self.clock.now()
        info = message if isinstance(message, dict) else {"prompt": str(message)}
        interview_id = f"{ts}_{agent_id}"
        self.ctx.record_trace(agent_id, ActionType.INTERVIEW.value, info)
        return {"success": True, "interview_id": interview_id}

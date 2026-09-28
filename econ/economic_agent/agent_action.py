from __future__ import annotations

from typing import Any

from camel.toolkits import FunctionTool

from econ.economic_platform.channel import Channel
from econ.economic_platform.typing import ActionType


class EconomicAction:
    """Thin channel-bridge layer — one async method per ``ActionType``.

    Every method:
    1. Shapes its arguments into a ``message`` payload.
    2. Writes ``(agent_id, message, action_type)`` to the channel queue.
    3. Awaits the platform's result and returns it.

    IMPORTANT: docstrings are converted to OpenAI function schemas by CAMEL's
    ``FunctionTool``.  Keep them accurate and complete — the LLM reads them
    when deciding which action to call.
    """

    def __init__(self, agent_id: int, channel: Channel) -> None:
        self.agent_id = agent_id
        self.channel = channel

    # ── Core dispatch ────────────────────────────────────────────────────

    async def perform_action(self, message: Any, action_type: str) -> Any:
        message_id = await self.channel.write_to_receive_queue(
            (self.agent_id, message, action_type)
        )
        response = await self.channel.read_from_send_queue(message_id)
        return response[2]

    # ── Tool list ────────────────────────────────────────────────────────

    def get_openai_function_list(self) -> list[FunctionTool]:
        return [
            FunctionTool(func)
            for func in [
                self.observe_market,
                self.produce,
                self.refine,
                self.list_good,
                self.update_listing_price,
                self.place_bid,
                self.check_balance,
                self.check_price_history,
                self.request_loan,
                self.approve_loan,
                self.deny_loan,
                self.repay,
                self.search_goods,
                self.search_agents,
                self.do_nothing,
            ]
        ]

    # ── Registration (not exposed as an LLM tool) ─────────────────────────

    async def register(
        self,
        name: str,
        agent_type: str,
        sector: str,
        initial_balance: float,
        region: str | None = None,
        produces: list[str] | None = None,
    ) -> dict:
        """Register this agent in the economy. Called once during env.reset()."""
        return await self.perform_action(
            (name, agent_type, sector, initial_balance, region, produces or []),
            ActionType.REGISTER.value,
        )

    # ── Market observation ───────────────────────────────────────────────

    async def observe_market(self) -> dict:
        """Observe the current economy: market listings, recent transaction prices,
        and the current simulation time step.

        Returns:
            dict: {
                "success": True,
                "time_step": 7,
                "listings": [
                    {"listing_id": 1, "seller_id": 2, "good_name": "wheat",
                     "ask_price": 45.0, "quantity_available": 50},
                    ...
                ],
                "recent_transactions": [
                    {"good_name": "wheat", "price": 43.0,
                     "quantity": 10, "timestamp": 6},
                    ...
                ]
            }
        """
        return await self.perform_action(None, ActionType.OBSERVE_MARKET.value)

    # ── Production ───────────────────────────────────────────────────────

    async def produce(self, good_name: str, quantity: int,
                      unit_cost: float) -> dict:
        """Produce goods by paying production cost (unit_cost * quantity).
        The produced goods enter your inventory and can be listed for sale.

        Args:
            good_name (str): The type of good to produce (e.g. "wheat", "steel").
            quantity (int): Number of units to produce.
            unit_cost (float): Cost in credits per unit produced.

        Returns:
            dict: {
                "success": True,
                "good_id": 7,
                "good_name": "wheat",
                "quantity": 100,
                "cost_incurred": 150.0
            }

        Note:
            Fails if your balance is below (unit_cost * quantity).
            Fails if you attempt to produce a good outside your registered
            production list — each agent type is restricted to specific goods.
        """
        return await self.perform_action(
            (good_name, quantity, unit_cost),
            ActionType.PRODUCE.value,
        )

    async def refine(
        self,
        input_good: str,
        input_qty: int,
        output_good: str,
        output_qty: int,
        conversion_cost_per_unit: float,
    ) -> dict:
        """Convert input goods (e.g. crude_oil) into refined output goods
        (e.g. refined_fuel or diesel).  The input goods must already be in
        your inventory — either self-produced or won in a PREVIOUS step's
        auction via place_bid (bids settle at end of step, so crude you bid for
        this step is only available to refine next step).
        The specified quantity of input goods is consumed and replaced by
        the output goods.

        Args:
            input_good (str): Good to consume as feedstock (e.g. "crude_oil").
            input_qty (int): Number of input units to consume.
            output_good (str): Good to create (e.g. "refined_fuel").
            output_qty (int): Number of output units to produce.
            conversion_cost_per_unit (float): Processing cost per output unit
                (covers energy, labour, etc.).

        Returns:
            dict: {
                "success": True,
                "input_good": "crude_oil",
                "input_qty_consumed": 50,
                "output_good": "refined_fuel",
                "output_good_id": 12,
                "output_qty": 40,
                "input_cost_basis": 1200.0,
                "conversion_cost": 200.0,
                "total_output_cost": 1400.0,
                "break_even_unit_cost": 35.0
            }

        Note:
            Fails if you have fewer unlisted input units than input_qty, or if
            your balance cannot cover (conversion_cost_per_unit * output_qty).
            After a successful refine, pass output_good_id to list_good() to
            sell the refined product. Set ask_price above break_even_unit_cost;
            it includes both crude input cost and conversion cost.
            Goods you have already listed on the market cannot be used as
            refinery inputs — delist them first if needed.
        """
        return await self.perform_action(
            (input_good, input_qty, output_good, output_qty, conversion_cost_per_unit),
            ActionType.REFINE.value,
        )

    # ── Market listing ───────────────────────────────────────────────────

    async def list_good(self, good_id: int, ask_price: float,
                        quantity: int) -> dict:
        """List goods you own on the market at a specified ask price.
        Buyers can then purchase these units.

        Args:
            good_id (int): The ID of the good to list (from produce()).
            ask_price (float): Price per unit you are asking for.
            quantity (int): Number of units to list.

        Returns:
            dict: {
                "success": True,
                "listing_id": 12,
                "good_name": "wheat",
                "ask_price": 55.0,
                "quantity_listed": 100
            }

        Note:
            Fails if good_id does not belong to you or has insufficient quantity.
        """
        return await self.perform_action(
            (good_id, ask_price, quantity),
            ActionType.LIST_GOOD.value,
        )

    async def update_listing_price(
        self, listing_id: int, new_price: float
    ) -> dict:
        """Lower (or raise) the ask price on one of your own active listings.

        Use this when your goods have been sitting unsold for one or more
        steps — reducing the price attracts buyers and clears inventory.
        Check own_active_listings in check_balance() to see which of your
        listings are stale (steps_listed > 0) and at what price they sit.

        Args:
            listing_id (int): The listing to reprice (from check_balance
                own_active_listings or your own list_good calls).
            new_price (float): New ask price per unit.  Must be positive.

        Returns:
            dict: {
                "success": True,
                "listing_id": 12,
                "good_name": "crude_oil",
                "old_price": 28.0,
                "new_price": 24.0,
                "quantity_available": 500
            }

        Note:
            Fails if the listing does not belong to you, is already sold out,
            or if new_price <= 0.
            The platform also applies a small automatic discount each step to
            stale listings, but voluntary repricing is faster and more precise.
        """
        return await self.perform_action(
            (listing_id, new_price),
            ActionType.UPDATE_LISTING_PRICE.value,
        )

    # ── Purchasing (sealed bids) ───────────────────────────────────────────

    async def place_bid(self, good_name: str, limit_price: float,
                        quantity: int) -> dict:
        """Submit a sealed buy order into this step's market call auction.

        The market does NOT execute trades immediately. Every step, all buy
        orders (bids) and sell orders (listings) for each good are collected and
        cleared together at a single uniform clearing price. You bid the MAXIMUM
        price per unit you are willing to pay; if the clearing price is at or
        below your limit you trade at the (possibly lower) clearing price.

        Args:
            good_name (str): The good you want to buy (e.g. "crude_oil").
            limit_price (float): Maximum price per unit you will pay (your
                reservation price). Bids at or above the clearing price win.
            quantity (int): Number of units you want to buy.

        Returns:
            dict: {
                "success": True,
                "good_name": "crude_oil",
                "limit_price": 12.0,
                "quantity_submitted": 45,
                "escrow": 540.0,
                "note": "Bid queued for end-of-step clearing; not yet filled."
            }

        Note:
            limit_price * quantity is ESCROWED from your balance when you bid.
            Any escrow not spent at clearing is refunded the same step. If your
            balance can't cover the full escrow, the quantity is reduced to what
            you can afford.
            SETTLEMENT TIMING: goods you win are added to your inventory at
            end-of-step clearing. As a consumer you can still consume them this
            same step. As a refiner or speculator you cannot refine/relist them
            until the NEXT step — bid one step ahead of when you need the goods.
            Bids are sealed: other agents never see them. Set limit_price using
            the recent clearing prices (check_price_history) and your own costs.
        """
        return await self.perform_action(
            (good_name, limit_price, quantity),
            ActionType.PLACE_BID.value,
        )

    # ── Balance & inventory ──────────────────────────────────────────────

    async def check_balance(self) -> dict:
        """Check your current credit balance, goods inventory, active loans,
        and a financial P&L summary so you can track income vs expenses.

        Returns:
            dict: {
                "success": True,
                "balance": 1234.56,
                "agent_type": "firm",
                "sector": "agriculture",
                "inventory": [{"name": "crude_oil", "total_quantity": 80,
                               "avg_unit_cost": 5.25, "latest_unit_cost": 6.10}],
                "consumption_needs": [
                    {"good_name": "refined_fuel", "quantity_per_step": 120,
                     "revenue_per_unit": 90.0, "shortage_penalty_per_unit": 120.0}
                ],
                "own_active_listings": [
                    {"listing_id": 5, "good_name": "crude_oil", "ask_price": 28.0,
                     "quantity_available": 300, "steps_listed": 2}
                ],
                "active_loans": [
                    {
                        "loan_id": 1, "lender_id": 5, "amount": 500.0,
                        "interest_rate": 0.05, "due_at": 20,
                        "steps_overdue": 0,
                        "current_repayment_due": 525.0
                    },
                    {
                        "loan_id": 2, "lender_id": 5, "amount": 300.0,
                        "interest_rate": 0.05, "due_at": 2,
                        "steps_overdue": 3,
                        "current_repayment_due": 319.5,
                        "WARNING": "OVERDUE by 3 step(s) — penalty growing by 1.50 cr/step. Call repay(loan_id=2) immediately. You cannot receive new credit until this is repaid."
                    }
                ],
                "this_step_financials": {
                    "step": 3,
                    "income": 800.0,
                    "expenses": 320.0,
                    "net": 480.0
                },
                "all_time_financials": {
                    "total_income": 2400.0,
                    "total_expenses": 1100.0,
                    "net_profit": 1300.0
                }
            }

        Note:
            inventory[].avg_unit_cost is your weighted-average cost basis across
            all batches you currently hold — use it as your price floor when
            calling list_good(). Never sell below avg_unit_cost unless you are
            deliberately liquidating at a loss.
            inventory[].latest_unit_cost is the unit_cost of your most recently
            acquired or produced batch. Compare it to avg_unit_cost: if
            latest_unit_cost > avg_unit_cost your newest stock is more expensive
            (input prices are rising); if it is lower, you secured a cheaper
            batch and can potentially undercut competitors while staying profitable.
            consumer consumption_needs show mandatory oil/fuel inputs consumed
            automatically each step. You earn operating revenue only from units
            consumed. Revenue flexes with the actual purchase cost of consumed
            inventory via price_pass_through, while unmet needs create shortage
            penalties. Maintain reserves and keep buying even when prices rise
            if operations depend on oil.
            own_active_listings shows your goods currently on the market.
            If steps_listed > 0 the good has been unsold for that many steps —
            consider calling update_listing_price() to lower the ask price.
            active_loans[].steps_overdue > 0 means the loan is past its due_at
            step. The WARNING field will be present and contains the exact
            repay() call you must make. Any loan with a WARNING must be repaid
            before you can receive new credit — the platform blocks new loan
            approvals while you have any overdue loan.
            (Banks only) pending_loan_requests lists applications awaiting your
            decision, each with an applicant dossier (balance, inventory_value,
            outstanding_debt, loans_repaid, overdue_loans) and what fraction of
            your capital the loan would be. Call approve_loan()/deny_loan() on each.
            active_loans[].current_repayment_due is the total amount (principal
            + interest + overdue penalty) you owe right now if you call repay().
            Use this_step_financials to decide whether you have already spent
            enough this step before taking further action.
            Use all_time_financials to judge your overall performance.
        """
        return await self.perform_action(None, ActionType.CHECK_BALANCE.value)

    # ── Price history ────────────────────────────────────────────────────

    async def check_price_history(self, good_name: str) -> dict:
        """Retrieve recent transaction prices for a specific good.
        Use this to estimate fair market value before producing or buying.

        Args:
            good_name (str): The name of the good (e.g. "wheat", "steel").

        Returns:
            dict: {
                "success": True,
                "good_name": "wheat",
                "average_price": 47.3,
                "prices": [
                    {"price": 45.0, "quantity": 10, "timestamp": 5},
                    {"price": 50.0, "quantity": 5,  "timestamp": 4},
                    ...
                ]
            }
        """
        return await self.perform_action(
            good_name,
            ActionType.CHECK_PRICE_HISTORY.value,
        )

    # ── Finance ──────────────────────────────────────────────────────────

    async def request_loan(
        self, lender_id: int, amount: float, proposed_rate: float | None = None
    ) -> dict:
        """Apply to borrow credits from a bank. This does NOT give you the money
        now — it files an application the bank reviews and decides on the NEXT
        step. Nothing is escrowed. Plan one step ahead of when you need the cash.

        Args:
            lender_id (int): The agent_id of the bank you are applying to. Loans
                are bank-only — use search_agents("bank") to find one.
            amount (float): Credits you want to borrow.
            proposed_rate (float, optional): The per-step interest rate you are
                willing to pay (e.g. 0.06 = 6%). A competitive offer can improve
                your odds; the bank sets the final rate and may override it.

        Returns:
            dict: {
                "success": True,
                "request_id": 4,
                "amount": 500.0,
                "lender_id": 5,
                "proposed_rate": 0.06,
                "note": "Application queued; the bank decides next step."
            }

        Note:
            Fails if the lender is not a bank, if you have any overdue loan, or
            if you already have a pending application with that bank. The bank
            may approve the full amount, approve a smaller amount, or deny you.
        """
        return await self.perform_action(
            (lender_id, amount, proposed_rate),
            ActionType.REQUEST_LOAN.value,
        )

    async def approve_loan(
        self,
        request_id: int,
        rate: float | None = None,
        approved_amount: float | None = None,
    ) -> dict:
        """(Banks only) Approve a pending loan application from your loan desk.
        This disburses the funds from your balance and creates the loan.

        Args:
            request_id (int): The application to approve (see pending_loan_requests
                in check_balance()).
            rate (float, optional): Per-step interest rate to charge (e.g. 0.08 =
                8%). Defaults to the applicant's proposed_rate, then the reference
                rate; always clamped to the allowed band. Charge more for riskier
                borrowers.
            approved_amount (float, optional): Approve less than requested to
                manage risk. Defaults to the full requested amount; cannot exceed it.

        Returns:
            dict: {
                "success": True,
                "request_id": 4,
                "loan_id": 9,
                "borrower_id": 7,
                "approved_amount": 400.0,
                "interest_rate": 0.08,
                "due_at": 14,
                "partial": True
            }

        Note:
            Auto-denied if the borrower has gone overdue since applying. Fails if
            you lack the balance to fund the approved amount — approve a smaller
            amount instead. Review the applicant dossier (balance, inventory value,
            outstanding debt, repayment history) before approving.
        """
        return await self.perform_action(
            (request_id, rate, approved_amount),
            ActionType.APPROVE_LOAN.value,
        )

    async def deny_loan(self, request_id: int, reason: str) -> dict:
        """(Banks only) Deny a pending loan application from your loan desk.

        Args:
            request_id (int): The application to deny.
            reason (str): A short explanation (e.g. "debt-to-asset too high",
                "sector distress", "insufficient collateral").

        Returns:
            dict: {
                "success": True,
                "request_id": 4,
                "status": "denied",
                "reason": "debt-to-asset too high"
            }
        """
        return await self.perform_action(
            (request_id, reason),
            ActionType.DENY_LOAN.value,
        )

    async def repay(self, loan_id: int) -> dict:
        """Repay an outstanding loan (principal + accrued interest).

        Args:
            loan_id (int): The loan to repay (from check_balance()).

        Returns:
            dict: {
                "success": True,
                "loan_id": 3,
                "amount_repaid": 525.0,
                "lender_id": 5
            }

        Note:
            Fails if your balance is below the repayment amount.
            Overdue loans incur additional penalty interest.
        """
        return await self.perform_action(loan_id, ActionType.REPAY.value)

    # ── Search ───────────────────────────────────────────────────────────

    async def search_goods(self, query: str) -> dict:
        """Search market listings by good name keyword.

        Args:
            query (str): Partial or full good name to search for.

        Returns:
            dict: {
                "success": True,
                "listings": [
                    {"listing_id": 1, "seller_id": 2, "good_name": "wheat",
                     "ask_price": 45.0, "quantity_available": 50},
                    ...
                ]
            }
        """
        return await self.perform_action(query, ActionType.SEARCH_GOODS.value)

    async def search_agents(self, query: str) -> dict:
        """Search registered agents by name, type, or sector.

        Args:
            query (str): Partial name, agent type, or sector to search for.

        Returns:
            dict: {
                "success": True,
                "agents": [
                    {"agent_id": 5, "name": "Bank Alpha",
                     "agent_type": "bank", "sector": "finance"},
                    ...
                ]
            }
        """
        return await self.perform_action(query, ActionType.SEARCH_AGENTS.value)

    # ── Inaction ─────────────────────────────────────────────────────────

    async def do_nothing(self) -> dict:
        """Take no economic action this step.

        Returns:
            dict: {"success": True}
        """
        return await self.perform_action(None, ActionType.DO_NOTHING.value)

    # ── Interview (not exposed as LLM tool) ──────────────────────────────

    async def interview(self, prompt: str, response: str) -> dict:
        return await self.perform_action(
            {"prompt": prompt, "response": response},
            ActionType.INTERVIEW.value,
        )

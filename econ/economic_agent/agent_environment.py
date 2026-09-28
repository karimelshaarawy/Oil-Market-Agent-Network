from __future__ import annotations

from abc import ABC, abstractmethod
from string import Template
from typing import TYPE_CHECKING

from econ.core.demand import target_from_need
from econ.economic_agent.agent_action import EconomicAction
from econ.economic_agent.market_snapshot import MarketSnapshot, MarketSnapshotFetcher

if TYPE_CHECKING:
    from econ.economic_agent.agent_graph import AgentGraph
    from econ.economic_agent.config.agent_info import AgentInfo
    from econ.rag import ChromaSimulationMemory


class Environment(ABC):

    @abstractmethod
    async def to_text_prompt(self) -> str:
        raise NotImplementedError


class EconomicEnvironment(Environment):
    """The agent's observable world — what it sees before making a decision.

    Calls the platform through the ``Channel`` (via ``EconomicAction``) to fetch
    live data, then assembles it into a natural-language string the LLM reads as
    its user message.

    The assembled prompt contains:
    - Current balance, inventory, and active loans.
    - Regional market listings (same-region sellers only, if geography is set).
    - Recent transaction prices (global, to gauge market trends).
    - Regional trade partners and their transport costs.
    - Current simulation time step.
    """

    balance_template = Template(
        "YOUR BALANCE SHEET:\n"
        "  Balance: $$$balance credits\n"
        "  Inventory: $inventory\n"
        "  Active loans: $loans"
    )

    market_template = Template(
        "CURRENT MARKET LISTINGS (goods available for purchase):\n$listings"
    )

    recent_tx_template = Template(
        "RECENT TRANSACTIONS (last $n deals, most recent first):\n$transactions"
    )

    neighbors_template = Template(
        "YOUR TRADE NETWORK:\n$neighbors"
    )

    env_template = Template(
        "Time step: $time_step\n\n"
        "$balance_section\n\n"
        "$demand_section\n\n"
        "$speculator_section\n\n"
        "$loan_desk_section\n\n"
        "$neighbors_section\n\n"
        "$rag_section\n\n"
        "$market_section\n\n"
        "$recent_tx_section\n\n"
        "${event_section}"
        "The market is a sealed call auction: it clears once at the end of this "
        "step at a single uniform price per good. To buy, place_bid(good_name, "
        "limit_price, quantity) — your limit is the MOST you'll pay; you trade at "
        "the (often lower) clearing price and unused escrow is refunded. To sell, "
        "list_good at an ask price. Goods you win settle at end of step: consumers "
        "can consume them this step; refiners/speculators can only refine/relist "
        "them next step, so bid one step ahead. "
        "Based on your profile and the above market state, choose your next "
        "economic action: producing goods, listing them for sale, bidding for "
        "inputs, checking clearing prices, applying for credit (request_loan), "
        "adjudicating loans (banks), or repaying loans."
    )

    def __init__(
        self,
        action: EconomicAction,
        agent_id: int | None = None,
        agent_graph: "AgentGraph | None" = None,
        max_listings_per_good: int = 5,
    ) -> None:
        self.action = action
        self.agent_id = agent_id
        self.agent_graph = agent_graph
        self.max_listings_per_good = max_listings_per_good
        self.current_event: str | None = None
        self.agent_info: "AgentInfo | None" = None
        self.rag_memory: "ChromaSimulationMemory | None" = None

    # ── Section builders ─────────────────────────────────────────────────

    def _balance_section(self, balance_result: dict | None) -> str:
        if balance_result is None:
            return "Balance information unavailable."
        inventory = balance_result.get("inventory", [])
        inv_str = (
            ", ".join(
                f"{r['name']}: {r['total_quantity']} units" for r in inventory
            )
            if inventory
            else "none"
        )
        loans = balance_result.get("active_loans", [])
        loan_str = (
            ", ".join(
                f"loan {r['loan_id']} ({r['amount']:.0f} cr, due step {r['due_at']})"
                for r in loans
            )
            if loans
            else "none"
        )
        return self.balance_template.substitute(
            balance=f"{balance_result['balance']:.2f}",
            inventory=inv_str,
            loans=loan_str,
        )

    def _latest_clearing_prices(self, snapshot: MarketSnapshot) -> dict[str, float]:
        """Most recent clearing price per good from the recent-transactions feed
        (newest first), used to drive the consumer demand target.
        """
        latest: dict[str, float] = {}
        for tx in snapshot.recent_transactions:
            good = tx.get("good_name")
            if good is not None and good not in latest:
                latest[good] = float(tx.get("price", 0.0) or 0.0)
        return latest

    def _demand_section(self, snapshot: MarketSnapshot) -> str:
        """Price-elastic operating target this step (consumers only).

        Demand is endogenous: the higher the recent clearing price, the lower the
        quantity the consumer needs to operate efficiently. This shows the target
        the accounting side will use, so the LLM's bids line up with the curve.
        """
        if self.agent_info is None:
            return ""
        needs = self.agent_info.profile.get("consumption_needs") or []
        if not needs:
            return ""
        prices = self._latest_clearing_prices(snapshot)
        lines = []
        for need in needs:
            good = str(need.get("good_name", "")).strip()
            base = int(need.get("quantity_per_step", 0) or 0)
            if not good or base <= 0:
                continue
            ref = float(need.get("reference_price", 0.0) or 0.0)
            price = prices.get(good)
            target = target_from_need(need, price)
            if price:
                price_str = f"recent price ~{price:.2f} (ref {ref:.2f})"
            else:
                price_str = f"no clearing price yet (using ref {ref:.2f})"
            lines.append(
                f"  - {good}: target ~{target} units this step "
                f"(base {base}; {price_str})"
            )
        if not lines:
            return ""
        return (
            "YOUR DEMAND THIS STEP (price-elastic — buy toward the target):\n"
            + "\n".join(lines)
            + "\n  When prices rise your efficient target falls (and so do your "
            "shortage penalties); when they fall it rises. Bid to reach the "
            "target, not a fixed quantity."
        )

    def _recent_prices_by_good(
        self, snapshot: MarketSnapshot
    ) -> dict[str, list[float]]:
        """All recent clearing prices per good, newest-first, used to derive a
        trailing-average fair value for speculators.
        """
        prices: dict[str, list[float]] = {}
        for tx in snapshot.recent_transactions:
            good = tx.get("good_name")
            if good is None:
                continue
            price = float(tx.get("price", 0.0) or 0.0)
            if price <= 0:
                continue
            prices.setdefault(good, []).append(price)
        return prices

    def _speculator_section(self, snapshot: MarketSnapshot) -> str:
        """Fair value vs market + mark-to-market positions (speculators only).

        Surfaces the two numbers the speculator's strategy depends on but that
        the generic balance/price sections drop: a trailing-average fair value
        per good (with the current deviation and a CHEAP/FAIR/RICH tag) and the
        unrealised P&L on every good held, marked to the latest clearing price.
        """
        if self.agent_info is None or self.agent_info.agent_type != "speculator":
            return ""

        band = 0.03  # ±3% dead-band around fair value before tagging cheap/rich
        prices_by_good = self._recent_prices_by_good(snapshot)
        latest = self._latest_clearing_prices(snapshot)

        signal_lines: list[str] = []
        for good in sorted(prices_by_good):
            history = prices_by_good[good]
            now = history[0]
            avg = sum(history) / len(history)
            if avg <= 0:
                continue
            dev = (now - avg) / avg
            if dev <= -band:
                tag = "CHEAP (lean buy)"
            elif dev >= band:
                tag = "RICH (lean sell)"
            else:
                tag = "FAIR"
            signal_lines.append(
                f"  {good}: latest {now:.2f} vs trailing avg {avg:.2f} "
                f"over {len(history)} print(s)  →  {dev*100:+.1f}%  {tag}"
            )
        if not signal_lines:
            signal_lines.append(
                "  No goods have cleared yet — no fair value to anchor to. Wait "
                "for prices, or probe with a small bid below recent asks."
            )

        position_lines: list[str] = []
        inventory = (
            snapshot.balance_result.get("inventory", [])
            if snapshot.balance_result
            else []
        )
        for row in inventory:
            good = row.get("name")
            qty = int(row.get("total_quantity", 0) or 0)
            if not good or qty <= 0:
                continue
            cost = float(row.get("avg_unit_cost", 0.0) or 0.0)
            mkt = latest.get(good)
            if mkt is None:
                position_lines.append(
                    f"  {good}: {qty} units @ avg cost {cost:.2f}  →  "
                    f"no clearing price yet (can't mark to market)"
                )
                continue
            pnl_unit = mkt - cost
            position_lines.append(
                f"  {good}: {qty} units @ avg cost {cost:.2f}  →  market {mkt:.2f}  "
                f"=  {pnl_unit:+.2f}/unit  ({pnl_unit*qty:+.2f} unrealized)"
            )
        if not position_lines:
            position_lines.append(
                "  You hold no inventory — deploy cash into a CHEAP good or wait "
                "for a better entry."
            )

        return (
            "SPECULATOR SIGNALS — fair value vs market (buy CHEAP, sell RICH):\n"
            + "\n".join(signal_lines)
            + "\n\nYOUR POSITIONS — marked to the latest clearing price "
            "(sell above your avg cost):\n"
            + "\n".join(position_lines)
        )

    def _loan_desk_section(self, snapshot: MarketSnapshot) -> str:
        """Pending loan applications + applicant dossiers (banks only)."""
        if snapshot.balance_result is None:
            return ""
        requests = snapshot.balance_result.get("pending_loan_requests")
        if requests is None:
            return ""
        if not requests:
            return (
                "LOAN DESK:\n  No pending applications. Lend by approving "
                "requests as they arrive; idle capital earns nothing."
            )
        lines = []
        for r in requests:
            a = r.get("applicant", {})
            frac = r.get("fraction_of_your_capital")
            frac_str = f"{frac*100:.0f}% of your capital" if frac is not None else "n/a"
            proposed = r.get("proposed_rate")
            proposed_str = (
                f"offers {proposed*100:.1f}%/step" if proposed is not None
                else "no rate offered"
            )
            lines.append(
                f"  - request #{r['request_id']} from {r.get('borrower')} "
                f"(id={r.get('borrower_id')}): wants {r.get('amount'):.2f} cr "
                f"[{frac_str}; {proposed_str}; waiting {r.get('steps_waiting')} step(s)]\n"
                f"      applicant: balance {a.get('balance')}, inventory value "
                f"{a.get('inventory_value')}, outstanding debt {a.get('outstanding_debt')}, "
                f"loans repaid {a.get('loans_repaid')}, overdue {a.get('overdue_loans')}, "
                f"sector {a.get('sector')}, region {a.get('region')}"
            )
        return (
            "LOAN DESK — pending applications (approve_loan / deny_loan each):\n"
            + "\n".join(lines)
            + "\n  Set the rate from risk (riskier → higher); approve a smaller "
            "amount to limit exposure. The capital % is a guide, not a hard cap."
        )

    def _neighbors_section(self, snapshot: MarketSnapshot) -> str:
        if not snapshot.neighbors:
            return ""
        lines = []
        for neighbor in snapshot.neighbors:
            cost_str = (
                "no surcharge"
                if neighbor.transport_cost == 0.0
                else f"+{neighbor.transport_cost*100:.0f}% transport cost"
            )
            lines.append(
                f"  agent_id={neighbor.agent_id}  {neighbor.name}  "
                f"({neighbor.agent_type}, {neighbor.region})  [{cost_str}]"
            )
        return self.neighbors_template.substitute(neighbors="\n".join(lines))

    def _market_section(self, snapshot: MarketSnapshot) -> str:
        listings = snapshot.listings
        scope_label = snapshot.scope_label
        if not listings:
            return (
                "RESTING SELL ORDERS (asks on the book):\n"
                "  No goods currently listed.\n"
                "  Place a bid anyway if you need a good — it clears against any "
                "asks submitted this step."
            )
        lines = []
        for r in listings:
            rate = r.get("transport_cost_rate", 0.0) or 0.0
            eff = r.get("effective_price", r["ask_price"])
            transport = (
                "same region" if rate == 0.0
                else f"+{rate*100:.0f}% transport → {eff:.2f} eff"
            )
            lines.append(
                f"  [{r['listing_id']}] {r['good_name']}  "
                f"ask {r['ask_price']:.2f} cr/unit  "
                f"({r['quantity_available']} available)  "
                f"seller={r['seller_id']}  ({transport})"
            )
        return (
            f"RESTING SELL ORDERS ({scope_label} — asks you can bid against):\n"
            + "\n".join(lines)
        )

    def _recent_transactions_section(self, snapshot: MarketSnapshot) -> str:
        txs = snapshot.recent_transactions
        if not txs:
            return "RECENT CLEARING PRICES:\n  No goods have cleared yet."
        lines = [
            f"  step {r['timestamp']}  {r['good_name']}  "
            f"{r['price']:.2f} cr/unit  x{r['quantity']} cleared"
            for r in txs[:10]
        ]
        return (
            "RECENT CLEARING PRICES (uniform price per good per step, newest first):\n"
            + "\n".join(lines)
        )

    async def to_text_prompt(self) -> str:
        """Return the full observation string for the LLM user message."""
        snapshot = await MarketSnapshotFetcher(
            action=self.action,
            agent_id=self.agent_id,
            agent_graph=self.agent_graph,
            max_listings_per_good=self.max_listings_per_good,
        ).fetch()

        balance_section = self._balance_section(snapshot.balance_result)
        demand_section = self._demand_section(snapshot)
        speculator_section = self._speculator_section(snapshot)
        loan_desk_section = self._loan_desk_section(snapshot)
        neighbors_section = self._neighbors_section(snapshot)
        rag_section = ""
        if self.rag_memory is not None and self.agent_info is not None:
            try:
                rag_section = self.rag_memory.retrieve_for_agent(
                    self.agent_info,
                    int(snapshot.time_step) if snapshot.time_step != "?" else 0,
                )
            except Exception:
                rag_section = ""

        market_section = self._market_section(snapshot)
        recent_tx_section = self._recent_transactions_section(snapshot)

        event_section = (
            f"⚠️  MARKET EVENT: {self.current_event}\n\n"
            if self.current_event
            else ""
        )

        return self.env_template.substitute(
            time_step=snapshot.time_step,
            balance_section=balance_section,
            demand_section=demand_section,
            speculator_section=speculator_section,
            loan_desk_section=loan_desk_section,
            neighbors_section=neighbors_section,
            rag_section=rag_section,
            market_section=market_section,
            recent_tx_section=recent_tx_section,
            event_section=event_section,
        )

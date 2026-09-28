from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentInfo:
    """Profile dataclass for one economic agent.

    The profile dict carries free-form persona text used to generate the LLM
    system prompt.

    Attributes:
        agent_id:        Unique integer identifier.
        name:            Display name (e.g. "GrainCorp", "Household_3").
        agent_type:      One of ``"firm"``, ``"consumer"``, ``"bank"``,
                         ``"refiner"``, or ``"speculator"``.
        sector:          Industry or category (e.g. "agriculture", "retail").
        initial_capital: Starting balance in the simulation's credit unit.
        risk_tolerance:  0.0 = maximally cautious, 1.0 = maximally aggressive.
        profile:         Free-form dict with at minimum a ``"persona"`` key.
    """

    agent_id: int
    name: str
    agent_type: str
    sector: str
    initial_capital: float
    risk_tolerance: float = 0.5
    region: str | None = None
    profile: dict[str, Any] = field(default_factory=dict)

    # ── System prompt ────────────────────────────────────────────────────

    def to_system_message(self) -> str:
        """Generate the LLM system prompt for this agent.

        The prompt tells the LLM:
        1. What role it plays (firm / consumer / bank).
        2. Its personality and strategic style.
        3. Its objective (profit maximisation, utility maximisation, etc.).
        4. That it must act via tool calling.
        """
        persona = self.profile.get("persona", "No additional persona provided.")
        risk_label = self._risk_label()
        objective = self._objective_text()
        produces = self.profile.get("produces", [])
        if produces:
            if self.agent_type == "refiner":
                # Refiners consume inputs and create outputs — make the chain explicit.
                inputs = self.profile.get("inputs", ["crude_oil"])
                produces_str = (
                    f"You convert {', '.join(inputs)} into {', '.join(produces)}. "
                    "Use refine() — NOT produce() — to create your output goods."
                )
            else:
                produces_str = f"You specialise in producing: {', '.join(produces)}."
        else:
            produces_str = ""
        region_str = (
            f"You are based in the {self.region} region. "
            "You primarily trade with other agents in your region "
            "(lower transport costs). Cross-region trade is possible "
            "but incurs an additional transport cost surcharge."
            if self.region
            else ""
        )

        unit_costs = self.profile.get("unit_costs", {})
        if unit_costs:
            cost_lines = ", ".join(
                f"{good} = {cost:.2f} cr/unit"
                for good, cost in unit_costs.items()
            )
            unit_costs_str = (
                f"Your standard production costs: {cost_lines}. "
                "Always use these values as unit_cost when calling produce() "
                "unless you have a specific operational reason to deviate "
                "(e.g. emergency run with premium inputs)."
            )
        else:
            unit_costs_str = ""

        consumption_needs = self.profile.get("consumption_needs", [])
        if consumption_needs:
            need_lines = []
            for need in consumption_needs:
                good = need.get("good_name", "unknown_good")
                qty = need.get("quantity_per_step", 0)
                revenue = need.get("revenue_per_unit", 0)
                penalty = need.get("shortage_penalty_per_unit", 0)
                reserve = need.get("reserve_target_steps", 1)
                elasticity = need.get("elasticity", 0.4)
                ref = need.get("reference_price", 0)
                need_lines.append(
                    f"- {good}: base {qty}/step at reference price {ref}; "
                    f"price-elasticity {elasticity} (higher = you cut volume more "
                    f"when prices rise). Earn about {revenue} cr/unit consumed; "
                    f"shortage penalty about {penalty} cr/unit; reserve {reserve} step(s)."
                )
            consumption_section = (
                "# OPERATING NEEDS (price-elastic demand)\n"
                + "\n".join(need_lines)
                + "\nYour demand is ENDOGENOUS: the quantity you actually need to "
                "operate efficiently moves with the market price. When the clearing "
                "price rises above your reference price your efficient target falls "
                "(and your shortage penalty is assessed against that lower target, "
                "so cutting volume is rational, not punished); when price falls your "
                "target rises. Each step your observation shows the concrete target "
                "for the current price — bid toward that target. You earn operating "
                "revenue only from consumed inputs, and revenue per unit flexes with "
                "your actual consumed inventory cost via price_pass_through. Use "
                "reserves or request_loan to ride out spikes; never collapse to zero "
                "on an essential input.\n"
            )
        else:
            consumption_section = "# OPERATING NEEDS\nNo mandatory operating consumption needs.\n"

        scenario_context = self.profile.get("scenario_context", "").strip()
        price_anchors = self.profile.get("price_anchors", "").strip()
        scenario_section = (
            "# WORLD CONTEXT\n"
            f"{scenario_context}\n\n"
            "Use this as broad market background only. Live market listings, "
            "your inventory costs, and price history are authoritative.\n"
            if scenario_context
            else "# WORLD CONTEXT\nNo external seed document context was provided.\n"
        )
        price_anchor_section = (
            "# PRICE ANCHORS\n"
            f"{price_anchors}\n"
            "These are non-binding reference ranges from the scenario pack. "
            "Do not blindly follow them if live prices or your costs disagree.\n"
            if price_anchors
            else "# PRICE ANCHORS\nNo external price anchors were provided.\n"
        )

        action_guidance = self._action_guidance(unit_costs)

        return f"""# OBJECTIVE
You are an economic agent participating in a simulated market economy.
After observing the current economic environment, choose actions that best
serve your economic interests and are consistent with your profile.

# SELF-DESCRIPTION
Your name is {self.name}.
You are a {self.agent_type} operating in the {self.sector} sector.
{produces_str}
{region_str}

# PERSONALITY & STRATEGY
{persona}
Your risk tolerance is {self.risk_tolerance:.1f} out of 1.0 ({risk_label}).

# OBJECTIVE
{objective}

# PRODUCTION COSTS
{unit_costs_str}

{consumption_section}

{scenario_section}

{price_anchor_section}

# RESPONSE METHOD
Please perform economic actions by tool calling.
{action_guidance}
"""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _risk_label(self) -> str:
        if self.risk_tolerance < 0.3:
            return "very risk-averse: prefer safe, certain outcomes"
        if self.risk_tolerance < 0.6:
            return "moderately risk-tolerant"
        return "risk-seeking: willing to take large bets for higher returns"

    def _objective_text(self) -> str:
        objectives = {
            "firm": (
                "Maximise profit by producing goods at low cost and selling them "
                "at a price above your production cost. Monitor market prices "
                "and adjust your output and pricing accordingly."
            ),
            "consumer": (
                "Maximise utility by bidding (place_bid) for the goods you need at a "
                "price you can justify. Your demand is price-elastic: each step your "
                "observation shows a concrete operating target for the current price "
                "— bid toward that target, not a fixed quantity. Your oil/fuel inputs "
                "are operational necessities: if you fail to hold enough inventory to "
                "meet the target, you lose operating revenue and may pay shortage "
                "penalties (assessed against the price-adjusted target). Because a "
                "missed unit costs you its shortage penalty AND its lost operating "
                "revenue, you can rationally bid up to roughly (revenue_per_unit + "
                "shortage_penalty_per_unit) when you are short. Goods you win settle "
                "in time to be consumed this same step. If a price spike makes your "
                "budget tight, apply for credit with request_loan (a bank reviews it "
                "and funds it next step). Keep enough reserves to continue operating."
            ),
            "bank": (
                "Maximise returns on capital by lending to creditworthy agents at "
                "a profitable interest rate. You are an ACTIVE lender: borrowers file "
                "loan applications that appear on your loan desk each step, and you "
                "decide each one. For every pending request call approve_loan "
                "(setting the per-step interest rate, and optionally a smaller amount "
                "to cap exposure) or deny_loan (with a reason). Price risk into the "
                "rate — charge more to highly indebted or distressed applicants, less "
                "to those with strong balances, real inventory, and a clean repayment "
                "history. Idle capital earns nothing, but a default loses principal, "
                "so size and price each loan to the applicant's risk. Tighten lending "
                "(higher rates, denials) when many applicants show distress or prices "
                "are falling; loosen when reserves are ample and borrowers are sound."
            ),
            "refiner": (
                "Maximise profit by bidding for crude inputs (crude_oil) via "
                "place_bid, then converting owned crude into refined products using "
                "the refine() tool, and listing those output goods at a margin above "
                "your total input cost. Rising crude prices usually justify higher "
                "refined fuel ask prices because fuel buyers still need oil to operate. "
                "Crude you win in the auction settles at END OF STEP, so you can only "
                "refine it NEXT step — keep a crude buffer and bid one step ahead of "
                "your throughput. refine() consumes owned crude and returns an "
                "output_good_id that you pass to list_good(). "
                "Monitor the crack spread — the gap between crude input prices and "
                "refined output prices. Cut throughput when margins are negative; "
                "ramp up when the spread is wide. Borrow short-term to secure cheap "
                "crude during supply gluts."
            ),
            "speculator": (
                "Maximise profit by bidding (place_bid) for commodities when the "
                "clearing price is below fair value — its recent trailing average — and "
                "reselling them (via list_good) when prices recover above your cost or "
                "spike above that average. Goods you win settle at END OF STEP, so you "
                "can only relist them the NEXT step — buy in anticipation of a move, "
                "not after it. The SPECULATOR SIGNALS section gives you fair value and "
                "the current deviation per good; YOUR POSITIONS gives mark-to-market "
                "profit on what you hold. Market events — supply disruptions, policy "
                "changes, geopolitical shocks — are trading signals. Manage risk: do "
                "not over-leverage, and be prepared to cut losses if the market moves "
                "against you."
            ),
        }
        return objectives.get(
            self.agent_type,
            "Maximise your economic wellbeing through sound market decisions.",
        )

    def _action_guidance(self, unit_costs: dict | None = None) -> str:
        """A short action hint consistent with each agent's tool set."""
        unit_costs = unit_costs or {}
        if unit_costs:
            cost_reminder = (
                "When calling produce(), use your standard production costs "
                "from the PRODUCTION COSTS section above as the unit_cost argument. "
            )
        else:
            cost_reminder = ""
        guidance = {
            "firm": (
                "Each step: call check_balance() first. "
                "Your inventory shows avg_unit_cost — the weighted-average cost of each good "
                "you hold. NEVER list below avg_unit_cost; use it as your price floor. "
                "If any own_active_listing has steps_listed > 0 with unsold stock, call "
                "update_listing_price() to lower the ask — but keep the new price above avg_unit_cost. "
                f"{cost_reminder}"
                "Then decide whether to produce() more and list_good() at a competitive price. "
                "Use check_price_history() to set prices close to recent transaction prices."
            ),
            "refiner": (
                "Each step: call check_balance() first to see inventory and own_active_listings. "
                "Your inventory shows avg_unit_cost for crude_oil — this is your input cost basis. "
                "After refine(), the returned break_even_unit_cost includes crude input cost "
                "plus conversion cost; list refined output above that break-even. "
                "When crude prices rise, raise refined_fuel/diesel asks enough to protect "
                "your crack spread, because consumers need fuel to earn operating revenue. "
                "If refined goods sit unsold (steps_listed > 0), call update_listing_price() "
                "to lower the ask toward the recent clearing price — but keep it above your "
                "total input cost. "
                "Workflow: refine() the crude you ALREADY own → list_good() the output at a "
                "margin; separately place_bid() for more crude to refine NEXT step (auction "
                "buys settle at end of step). Keep a crude buffer so you never run dry. "
                "Pause refining if your crack spread (refined price minus crude cost) is negative."
            ),
            "consumer": (
                "Each step: read YOUR DEMAND THIS STEP for the price-adjusted target, then "
                "call check_balance() to see inventory and budget. place_bid() toward the "
                "target (plus any reserve), not a fixed quantity; goods you win clear in time "
                "to be consumed this step. Set your limit price from the recent clearing "
                "prices, and raise it toward (revenue_per_unit + shortage_penalty_per_unit) "
                "when you are short, since a missed unit costs you both. If prices spike the "
                "target itself drops — buying less is correct and is not penalised. If your "
                "budget is tight, request_loan() from a bank, or draw down reserves; just "
                "avoid leaving the target badly unmet on an essential input."
            ),
            "speculator": (
                "Each step: call check_balance() first to see your cash and the avg "
                "cost of every good you hold, then read SPECULATOR SIGNALS (fair value "
                "vs market per good) and YOUR POSITIONS (mark-to-market profit/loss). "
                "Trade with discipline: place_bid for a good only when its latest "
                "clearing price is clearly BELOW its trailing average (a CHEAP signal) — "
                "buy in anticipation of a rebound, never chase a good already flagged "
                "RICH. list_good to sell a position you hold when the market is at or "
                "above your avg cost plus a target margin, or when the good reads RICH "
                "versus its trailing average. Goods you win settle at END OF STEP, so "
                "you can only relist them NEXT step — position one step ahead of the "
                "move, not after it. Market events (supply shocks, policy, geopolitics) "
                "are early signals to buy before the rest of the book reprices. Manage "
                "risk: size each position to what you can fund, cut a losing position "
                "rather than averaging down, and use request_loan only to amplify a "
                "high-conviction CHEAP setup."
            ),
            "bank": (
                "Each step: call check_balance() to see your capital and your loan desk "
                "(pending_loan_requests, each with an applicant dossier). For every pending "
                "request, decide: approve_loan(request_id, rate, approved_amount) — price the "
                "rate to the applicant's risk and optionally lend less than asked — or "
                "deny_loan(request_id, reason). Favour applicants with strong balances, real "
                "inventory value, low outstanding debt, and a clean repayment record; charge "
                "more or deny when debt is high, the sector looks distressed, or prices are "
                "sliding. Do not leave sound requests undecided — they expire, and idle "
                "capital earns nothing."
            ),
        }
        return guidance.get(
            self.agent_type,
            "Do not limit yourself to a single action type — consider checking the market and your balance before acting.",
        )

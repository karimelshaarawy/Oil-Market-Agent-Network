"""Oil-market scenario configuration.

Single source of truth for the oil simulation's agent roster, economy
parameters, seed inventory, and baseline event schedule. Consumed by both
the orchestration runner (API-driven runs) and the quick-start example.
"""
from __future__ import annotations

import json
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
PROFILE_PATH = Path(__file__).parent.parent / "data" / "agents" / "oil_agents.json"

# ── Agent category toggles ───────────────────────────────────────────────────
# Set any category to False to exclude those agents entirely.
INCLUDE: dict[str, bool] = {
    "upstream":   True,   # crude oil producers (firm)
    "downstream": True,   # refiners (refiner) — buy crude, sell refined products
    "financial":  True,   # commodity traders (speculator) + bank
    "consumer":   True,   # end users: airlines, chemical plants, retail fuel
}

# ── Market events ────────────────────────────────────────────────────────────
# Keys are step numbers at which the event fires.
# Set a step's value to None to clear a previously active event.
# Set EVENTS = {} to run a baseline with no shocks.
EVENTS: dict[int, str | None] = {
    2: (
        "⚡ OPEC EMERGENCY CUT: OPEC+ has announced a coordinated production cut "
        "of 2 million barrels per day, effective immediately. Global crude supply "
        "is now significantly tighter. Upstream producers should consider raising "
        "ask prices; refiners and consumers should expect higher input costs."
    ),
    4: (
        "🔥 PIPELINE DISRUPTION: A major crude oil pipeline in Texas has been shut "
        "down due to a cyberattack. Refinery throughput in the Texas region is "
        "disrupted. Refined fuel supply may fall sharply in the short term. Buyers "
        "should consider building emergency reserves now."
    ),
    6: (
        "🛢️  SPR RELEASE: The US government has released 50 million barrels from "
        "the Strategic Petroleum Reserve to cool prices. Additional crude supply "
        "is now entering the market. Prices may soften; buyers can afford to wait "
        "for a better entry point before purchasing."
    ),
    7: None,   # clear all events — market returns to neutral signals
}

# ── Economy parameters ────────────────────────────────────────────────────────
INTEREST_RATE        = 0.06   # reference/fallback per-step rate (bank sets actual)
LOAN_DURATION_STEPS  = 4
CROSS_REGION_COST    = 0.12   # 12% transport surcharge for cross-region trades
# Endogenous credit: the bank chooses each loan's rate when approving a request,
# clamped to this band. INTEREST_RATE is the reference used if the bank gives no
# rate and the borrower proposed none.
MIN_INTEREST_RATE    = 0.02
MAX_INTEREST_RATE    = 0.40
# A pending loan application the bank neither approves nor denies within this many
# steps is auto-expired (the borrower's situation may have changed by then).
LOAN_REQUEST_EXPIRY_STEPS = 3
# Legacy flat consumer income is disabled. Consumers now earn operating revenue
# only when they consume their required oil/fuel inputs; shortages create losses.
CONSUMER_INCOME_PER_STEP = 0.0
CONSUMER_OPERATIONS_ENABLED = True
# Waive consumer shortage penalties for the first N steps. Consumers still
# consume inventory and earn operating revenue during this window; only the
# penalty for unmet needs is postponed, giving the call auction's demand side
# time to ramp up before shortages start costing credits. 0 = penalise from step 1.
SHORTAGE_PENALTY_GRACE_STEPS = 4
# Number of full steps an unsold ask may rest on the call-auction book before
# it is auto-cancelled (remaining stock returned to the seller to re-list).
# The auction itself discovers prices, so there is no automatic price decay;
# this just keeps permanently-overpriced asks from piling up. 0 disables it.
AUTO_CANCEL_STEPS = 3

# ── RAG memory ────────────────────────────────────────────────────────────────
# Stores events, transactions, and deterministic agent reflections in a local
# Chroma DB, then injects hybrid semantic + keyword retrieval into prompts.
RAG_ENABLED = True
RAG_PERSIST_DIRECTORY = "chroma_oil_market"
RAG_TOP_K = 5
RAG_RESET_ON_START = True

# ── Multi-turn reasoning loop ─────────────────────────────────────────────────
# Max sequential LLM calls per agent per simulation step.
# 1 = original single-call behaviour (cheapest, fastest).
# 3 = lets an agent observe results and chain within-step actions, e.g.
#     refine() owned crude → list_good the output, or place_bid then list_good.
# Note: market buys settle at end-of-step clearing, so crude bid this step is
# only refinable next step — chaining is for internal ops on owned inventory.
MAX_ITERATION = 3

# ── Initial seed inventory ────────────────────────────────────────────────────
# Maps agent name → (good_name, quantity, unit_cost).
# Only agents present after INCLUDE filtering will be seeded.
# Refiners are seeded with crude_oil so they can call refine() from step 1
# without waiting for the auction to clear crude to them first.
SEED: dict[str, tuple[str, int, float]] = {
    "ArabianPetroleum": ("crude_oil", 200, 2.0),
    "ShaleProducer":    ("crude_oil", 100, 3.8),
    "MegaRefinery":     ("crude_oil", 150, 5.5),  # input feedstock, not output
    "EuroRefinery":     ("crude_oil", 100, 5.5),  # input feedstock, not output
}


def load_profiles(include: dict[str, bool] | None = None, *, verbose: bool = True) -> list[dict]:
    """Load agent profiles, filtered by category toggles (default: INCLUDE)."""
    if include is None:
        include = INCLUDE
    with open(PROFILE_PATH) as f:
        all_profiles = json.load(f)

    active = [p for p in all_profiles if include.get(p.get("category", ""), True)]

    excluded = [p["name"] for p in all_profiles if p not in active]
    if excluded and verbose:
        print(f"  Excluded agents: {', '.join(excluded)}")

    return active


def known_goods(profiles: list[dict]) -> list[str]:
    """All good names that can appear in this scenario (seeded + produced + inputs)."""
    goods: set[str] = set(SEED[name][0] for name in SEED)
    for profile in profiles:
        goods.update(profile.get("produces", []) or [])
        goods.update(profile.get("inputs", []) or [])
    return sorted(goods)

"""Oil-market simulation — upstream producers, refiners, speculators, end users.

The simulation models four layers of the global oil economy:

  upstream   — crude oil producers (firm)
  downstream — refiners who buy crude and sell refined products (refiner)
  financial  — commodity traders and a bank (speculator + bank)
  consumer   — airlines, chemical plants, and retail fuel buyers (consumer)

Configuration
-------------
Edit the ``INCLUDE`` and ``EVENTS`` dicts below to control which agent
categories participate and which market events fire at which step.

Run
---
    cd "Agent Network"
    python -m econ.examples.oil_market_quick_start
"""
from __future__ import annotations

import asyncio

from dotenv import load_dotenv

import econ
from econ.core.config import env_int as _env_int
from econ.core.model_factory import build_chat_model
from econ.economic_agent.agents_generator import generate_agent_graph_from_profiles
from econ.economic_platform.typing import ActionType, DefaultEconomyType
from econ.environment.env_action import LLMAction, ManualAction
from econ.news import build_live_news_events

# Scenario configuration (roster, events, economy parameters, seed inventory)
# lives in econ/orchestration/oil_market_config.py — re-exported here so this
# example stays the place to read and tweak a run.
from econ.orchestration.oil_market_config import (
    CONSUMER_INCOME_PER_STEP,
    CONSUMER_OPERATIONS_ENABLED,
    CROSS_REGION_COST,
    EVENTS,
    AUTO_CANCEL_STEPS,
    INCLUDE,
    INTEREST_RATE,
    LOAN_DURATION_STEPS,
    LOAN_REQUEST_EXPIRY_STEPS,
    MAX_INTEREST_RATE,
    MAX_ITERATION,
    MIN_INTEREST_RATE,
    PROFILE_PATH,
    RAG_ENABLED,
    RAG_PERSIST_DIRECTORY,
    RAG_RESET_ON_START,
    RAG_TOP_K,
    SEED,
    SHORTAGE_PENALTY_GRACE_STEPS,
    known_goods,
    load_profiles,
)

load_dotenv(override=True)

# ── Run settings ─────────────────────────────────────────────────────────────
DB_PATH = "oil_market_run.db"
N_STEPS = 8

# ── Live news ──────────────────────────────────────────────────────────────────
# When True, fetch recent real oil news (RSS), score each article for price
# impact with the LLM, and lay the most significant article across the steps in
# chronological order. This REPLACES the hardcoded EVENTS above. On any failure
# (feeds down, no recent articles, scoring error) the run falls back to EVENTS.
# Tune via ECON_NEWS_LOOKBACK_DAYS and ECON_NEWS_FEEDS (see econ/news/feeds.py).
USE_LIVE_NEWS = False

# ── LLM: completion cap vs CAMEL context memory (see .env) ───────────────────
# ECON_MAX_COMPLETION_TOKENS — ChatGPTConfig max_tokens (new tokens per reply).
# ECON_CAMEL_TOKEN_LIMIT — passed to EconomicAgent as token_limit (memory budget).
MAX_COMPLETION_TOKENS = _env_int("ECON_MAX_COMPLETION_TOKENS", 8192)
CAMEL_TOKEN_LIMIT = _env_int("ECON_CAMEL_TOKEN_LIMIT", 32768)


# ── Model factory ─────────────────────────────────────────────────────────────

def build_model():
    return build_chat_model(temperature=0.4, max_tokens=MAX_COMPLETION_TOKENS)


def print_config() -> None:
    active_cats = [c for c, v in INCLUDE.items() if v]
    inactive_cats = [c for c, v in INCLUDE.items() if not v]
    print("── Configuration ────────────────────────────────────────")
    print(f"  Active categories : {', '.join(active_cats) or 'none'}")
    if inactive_cats:
        print(f"  Excluded categories: {', '.join(inactive_cats)}")
    if EVENTS:
        print(f"  Scheduled events  : steps {sorted(s for s, e in EVENTS.items() if e)}")
    else:
        print("  Scheduled events  : none (baseline run)")
    print(f"  Steps             : {N_STEPS}")
    print(f"  Database          : {DB_PATH}")
    print("─────────────────────────────────────────────────────────")


# ── Main simulation ───────────────────────────────────────────────────────────

async def main() -> None:
    print_config()

    model = build_model()

    # ── Load profiles and build agent graph ───────────────────────────────
    print("\nLoading oil market profiles …")
    profiles = load_profiles()
    agent_graph = await generate_agent_graph_from_profiles(
        profiles=profiles,
        model=model,
        cross_region_transport_cost=CROSS_REGION_COST,
        token_limit=CAMEL_TOKEN_LIMIT,
        max_iteration=MAX_ITERATION,
    )
    print(f"  {agent_graph.get_num_nodes()} agents loaded.")

    # ── Create environment ─────────────────────────────────────────────────
    env = econ.make(
        agent_graph=agent_graph,
        economy_type=DefaultEconomyType.SIMPLE_GOODS,
        database_path=DB_PATH,
        interest_rate=INTEREST_RATE,
        loan_duration_steps=LOAN_DURATION_STEPS,
        min_interest_rate=MIN_INTEREST_RATE,
        max_interest_rate=MAX_INTEREST_RATE,
        loan_request_expiry_steps=LOAN_REQUEST_EXPIRY_STEPS,
        consumer_income_per_step=CONSUMER_INCOME_PER_STEP,
        consumer_operations_enabled=CONSUMER_OPERATIONS_ENABLED,
        auto_cancel_steps=AUTO_CANCEL_STEPS,
        shortage_penalty_grace_steps=SHORTAGE_PENALTY_GRACE_STEPS,
        rag_enabled=RAG_ENABLED,
        rag_persist_directory=RAG_PERSIST_DIRECTORY,
        rag_top_k=RAG_TOP_K,
        rag_reset_on_start=RAG_RESET_ON_START,
    )

    await env.reset()
    print("  All agents registered.\n")

    # ── Step 0: seed initial inventory via ManualAction ───────────────────
    print("[Step 0] Seeding initial inventory …")
    agents_by_name = {
        agent.agent_info.name: agent
        for _, agent in agent_graph.get_agents()
    }
    seed_actions = {
        agents_by_name[name]: ManualAction(
            action_type=ActionType.PRODUCE,
            action_args={"good_name": good, "quantity": qty, "unit_cost": cost},
        )
        for name, (good, qty, cost) in SEED.items()
        if name in agents_by_name
    }
    if seed_actions:
        await env.step(seed_actions)
        seeded = [a.agent_info.name for a in seed_actions]
        print(f"  Seeded: {', '.join(seeded)}")
    print("  (Firms and refiners will list goods autonomously from step 1.)\n")

    # ── Steps 1-N: LLM-driven with scheduled events ───────────────────────
    all_agents = [agent for _, agent in agent_graph.get_agents()]

    # Resolve the event schedule: live news (if enabled) overrides EVENTS.
    events_schedule: dict[int, str | None] = dict(EVENTS)
    if USE_LIVE_NEWS:
        print("\nFetching live oil news to build event schedule …")
        live = await build_live_news_events(n_steps=N_STEPS, goods=known_goods(profiles))
        if live is not None:
            live_events, _snapshot = live
            events_schedule = {e.step: e.event_text for e in live_events}
            fired = sum(1 for e in live_events if e.event_text)
            print(f"  Live news schedule ready: {fired}/{N_STEPS} steps have events.\n")
        else:
            print("  Live news unavailable — falling back to hardcoded EVENTS.\n")

    for step in range(1, N_STEPS + 1):
        if step in events_schedule:
            event_text = events_schedule[step]
            env.broadcast_event(event_text)
            if event_text:
                print(f"[Step {step}] EVENT FIRED:\n  {event_text[:120]} …")
            else:
                print(f"[Step {step}] Event cleared — market returns to normal signals.")
        else:
            print(f"[Step {step}] All agents deliberating …")

        actions = {agent: LLMAction() for agent in all_agents}
        await env.step(actions)
        print(f"  Step {step} complete.")

    # ── Post-simulation interview ─────────────────────────────────────────
    print("\n── Agent Market Assessments ─────────────────────────────────────")
    results = await env.interview_agents(
        agents=all_agents,
        prompt=(
            "In 2-3 sentences: how did the supply disruptions and any government "
            "interventions affect your decisions this simulation, and what is your "
            "current outlook for crude oil and refined fuel prices?"
        ),
    )
    for r in results:
        agent = agents_by_name.get(
            next(
                (a.agent_info.name for _, a in agent_graph.get_agents()
                 if a.economic_agent_id == r["agent_id"]),
                str(r["agent_id"]),
            )
        )
        name = agent.agent_info.name if agent else str(r["agent_id"])
        atype = agent.agent_info.agent_type if agent else ""
        print(f"\n  [{atype}] {name}:")
        print(f"  {r['content'][:240]}")

    # ── Shutdown ──────────────────────────────────────────────────────────
    await env.close()
    print(f"\nSimulation complete. Results written to: {DB_PATH}")
    print("Query the 'trace' table for the full per-step action log.")


if __name__ == "__main__":
    asyncio.run(main())

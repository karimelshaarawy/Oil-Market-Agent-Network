from __future__ import annotations

import asyncio
import json
from typing import List, Optional, Union

from camel.models import BaseModelBackend, ModelManager

from econ.economic_agent.agent import EconomicAgent
from econ.economic_agent.agent_graph import AgentGraph
from econ.economic_agent.config.agent_info import AgentInfo
from econ.economic_platform.channel import Channel
from econ.economic_platform.typing import ActionType


def _connect_channel(channel: Channel, agent_graph: AgentGraph) -> AgentGraph:
    """Inject the shared channel and graph reference into every agent."""
    for _, agent in agent_graph.get_agents():
        agent.channel = channel
        agent.env.action.channel = channel
        # Ensure the environment has the final graph reference (important when
        # agents were constructed before edges were added).
        agent.agent_graph = agent_graph
        agent.env.agent_graph = agent_graph
    return agent_graph


async def generate_custom_agents(
    channel: Channel,
    agent_graph: AgentGraph,
) -> AgentGraph:
    """Connect agents to the channel and register them with the platform.

    Called once during ``EconomicEnv.reset()``.

    Args:
        channel:     The shared ``Channel`` linked to ``EconomicPlatform``.
        agent_graph: Pre-populated ``AgentGraph``.

    Returns:
        The same ``AgentGraph`` with channels connected and all agents
        registered in the database.
    """
    agent_graph = _connect_channel(channel, agent_graph)

    register_tasks = [
        agent.env.action.register(
            name=agent.agent_info.name,
            agent_type=agent.agent_info.agent_type,
            sector=agent.agent_info.sector,
            initial_balance=agent.agent_info.initial_capital,
            region=agent.agent_info.region,
            produces=agent.agent_info.profile.get("produces") or [],
        )
        for _, agent in agent_graph.get_agents()
    ]
    results = await asyncio.gather(*register_tasks)
    for result in results:
        if not result.get("success"):
            raise RuntimeError(f"Agent registration failed: {result}")

    return agent_graph


_TYPE_ACTION_MAP = {
    "firm":       ActionType.get_firm_actions,
    "consumer":   ActionType.get_consumer_actions,
    "bank":       ActionType.get_bank_actions,
    "refiner":    ActionType.get_refiner_actions,
    "speculator": ActionType.get_speculator_actions,
}


async def generate_agent_graph_from_profiles(
    profiles: list[dict],
    model: Union[BaseModelBackend, List[BaseModelBackend], ModelManager],
    available_actions: list[ActionType] | None = None,
    cross_region_transport_cost: float = 0.10,
    max_listings_per_good: int = 5,
    token_limit: int | None = None,
    max_iteration: int = 1,
) -> AgentGraph:
    """Build an ``AgentGraph`` from an in-memory list of profile dicts.

    Each dict must contain: ``name``, ``agent_type``, ``sector``,
    ``initial_capital``.  Optional fields: ``risk_tolerance``, ``persona``,
    ``produces``, ``region``.  Any extra fields (e.g. ``category``) are
    silently ignored, which makes it easy to tag profiles for upstream
    filtering without changing the schema.

    Supported agent types and their default tool sets:

    - ``"firm"``       — produce, list, observe, balance, price history, request_loan/repay
    - ``"consumer"``   — bid, search goods, observe, balance, price history, request_loan/repay
    - ``"bank"``       — observe, balance, price history, search agents, approve_loan/deny_loan
    - ``"refiner"``    — bid + search goods + refine + list (buy inputs, sell outputs)
    - ``"speculator"`` — bid + list + search goods/agents (arbitrage/resale)

    When a ``region`` field is present on any profile, geographic edges are
    auto-created:

    - Same-region pairs → ``transport_cost=0.0``
    - Cross-region pairs → ``transport_cost=cross_region_transport_cost``

    Args:
        profiles:                   List of profile dicts (already loaded).
        model:                      CAMEL model backend(s) for all agents.
        available_actions:          Override the per-type tool set for all agents.
        cross_region_transport_cost: Fractional surcharge for cross-region
                                    purchases (default 10%).
        max_listings_per_good:      Max listings shown per good in each agent's
                                    market observation (default 5, 0 = no cap).
        token_limit:                Optional CAMEL ``ChatAgent`` context budget
                                    (``EconomicAgent``); ``None`` uses the agent default.
        max_iteration:              Max sequential LLM calls per simulation step
                                    (default 1 = original single-call behaviour).
                                    Set to 3–4 for supply-chain agents that need
                                    buy → refine → list within one step.

    Returns:
        A populated ``AgentGraph`` ready to pass to ``make()``.
    """
    agent_graph = AgentGraph()

    async def _make_agent(i: int, profile: dict) -> None:
        region = profile.get("region") or None
        agent_info = AgentInfo(
            agent_id=i,
            name=profile["name"],
            agent_type=profile["agent_type"],
            sector=profile["sector"],
            initial_capital=float(profile["initial_capital"]),
            risk_tolerance=float(profile.get("risk_tolerance", 0.5)),
            region=region,
            profile={
                "persona": profile.get("persona", ""),
                "produces": profile.get("produces", []),
                "inputs": profile.get("inputs", []),
                "unit_costs": profile.get("unit_costs", {}),
                "consumption_needs": profile.get("consumption_needs", []),
                "scenario_context": profile.get("scenario_context", ""),
                "price_anchors": profile.get("price_anchors", ""),
            },
        )

        if available_actions is None:
            factory = _TYPE_ACTION_MAP.get(agent_info.agent_type)
            type_actions = factory() if factory is not None else None
        else:
            type_actions = available_actions

        agent = EconomicAgent(
            agent_id=i,
            agent_info=agent_info,
            model=model,
            available_actions=type_actions,
            max_listings_per_good=max_listings_per_good,
            token_limit=token_limit,
            max_iteration=max_iteration,
        )
        agent_graph.add_agent(agent)

    await asyncio.gather(*[_make_agent(i, p) for i, p in enumerate(profiles)])

    # ── Build geographic edges ────────────────────────────────────────────
    agents = agent_graph.get_agents()
    has_regions = any(a.agent_info.region for _, a in agents)
    if has_regions:
        for id_a, agent_a in agents:
            region_a = agent_a.agent_info.region
            for id_b, agent_b in agents:
                if id_a == id_b:
                    continue
                region_b = agent_b.agent_info.region
                same = (
                    region_a is not None
                    and region_b is not None
                    and region_a == region_b
                )
                cost = 0.0 if same else cross_region_transport_cost
                agent_graph.add_edge(id_a, id_b, transport_cost=cost)

    return agent_graph


async def generate_agent_graph_from_file(
    profile_path: str,
    model: Union[BaseModelBackend, List[BaseModelBackend], ModelManager],
    available_actions: list[ActionType] | None = None,
    cross_region_transport_cost: float = 0.10,
    max_listings_per_good: int = 5,
    token_limit: int | None = None,
    max_iteration: int = 1,
) -> AgentGraph:
    """Load agent profiles from a JSON file and build an ``AgentGraph``.

    Convenience wrapper around ``generate_agent_graph_from_profiles`` that
    reads profiles from disk first.  See that function for full documentation
    of the profile schema and available agent types.

    Args:
        profile_path:               Path to the JSON file.
        model:                      CAMEL model backend(s) for all agents.
        available_actions:          Override the per-type tool set for all agents.
        cross_region_transport_cost: Fractional surcharge for cross-region
                                    purchases (default 10%).
        max_listings_per_good:      Max listings shown per good in each agent's
                                    market observation (default 5, 0 = no cap).
        token_limit:                Optional CAMEL ``ChatAgent`` context budget.
        max_iteration:              Max sequential LLM calls per step (default 1).

    Returns:
        A populated ``AgentGraph`` ready to pass to ``make()``.
    """
    with open(profile_path) as f:
        profiles = json.load(f)
    return await generate_agent_graph_from_profiles(
        profiles=profiles,
        model=model,
        available_actions=available_actions,
        cross_region_transport_cost=cross_region_transport_cost,
        max_listings_per_good=max_listings_per_good,
        token_limit=token_limit,
        max_iteration=max_iteration,
    )

"""econ — An LLM-powered economic world simulator.

Public API::

    import econ

    env = econ.make(agent_graph, econ.DefaultEconomyType.SIMPLE_GOODS, "run.db")
    await env.reset()
    await env.step({agent: econ.LLMAction() for _, agent in agent_graph.get_agents()})
    await env.close()
"""
from econ.economic_agent.agent import DEFAULT_TOKEN_LIMIT, EconomicAgent
from econ.economic_agent.agent_graph import AgentGraph
from econ.economic_agent.agents_generator import (
    generate_agent_graph_from_file,
    generate_agent_graph_from_profiles,
    generate_custom_agents,
)
from econ.economic_agent.config.agent_info import AgentInfo
from econ.economic_platform.platform import EconomicPlatform
from econ.economic_platform.typing import ActionType, DefaultEconomyType, MarketType
from econ.environment.env import EconomicEnv
from econ.environment.env_action import LLMAction, ManualAction
from econ.environment.make import make

__version__ = "0.1.0"

__all__ = [
    "make",
    "EconomicEnv",
    "EconomicPlatform",
    "EconomicAgent",
    "DEFAULT_TOKEN_LIMIT",
    "AgentGraph",
    "AgentInfo",
    "ActionType",
    "DefaultEconomyType",
    "MarketType",
    "ManualAction",
    "LLMAction",
    "generate_agent_graph_from_file",
    "generate_agent_graph_from_profiles",
    "generate_custom_agents",
]

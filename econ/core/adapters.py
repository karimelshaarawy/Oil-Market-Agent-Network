from __future__ import annotations

from typing import Any

from econ.core.profile_store import AgentProfile, ProfileStore
from econ.core.transport_costs import TransportCostProvider
from econ.economic_agent.agent_graph import AgentGraph


class AgentGraphProfileStore(ProfileStore):
    def __init__(self, agent_graph: AgentGraph) -> None:
        self._profiles: dict[int, AgentProfile] = {}
        for agent_id, agent in agent_graph.get_agents():
            profile = agent.agent_info.profile or {}
            produces = profile.get("produces")
            consumption_needs = profile.get("consumption_needs")
            if produces is None or consumption_needs is None:
                raise ValueError(
                    f"agent_id {agent_id} missing profile fields: produces/consumption_needs"
                )
            agent_profile: AgentProfile = {
                "name": agent.agent_info.name,
                "agent_type": agent.agent_info.agent_type,
                "region": agent.agent_info.region,
                "produces": list(produces),
                "consumption_needs": list(consumption_needs),
            }
            self._profiles[int(agent_id)] = agent_profile

    def get_profile(self, agent_id: int) -> AgentProfile:
        if int(agent_id) not in self._profiles:
            raise KeyError(f"agent_id {agent_id} missing from ProfileStore")
        return self._profiles[int(agent_id)]


class AgentGraphTransportCosts(TransportCostProvider):
    def __init__(self, agent_graph: AgentGraph) -> None:
        self._agent_graph = agent_graph

    def get_cost(self, from_agent_id: int, to_agent_id: int) -> float:
        return self._agent_graph.get_transport_cost(from_agent_id, to_agent_id)

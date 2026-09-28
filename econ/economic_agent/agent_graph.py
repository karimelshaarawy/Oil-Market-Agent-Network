from __future__ import annotations

from typing import TYPE_CHECKING

import igraph as ig

if TYPE_CHECKING:
    from econ.economic_agent.agent import EconomicAgent


class AgentGraph:
    """Directed graph of economic agents backed by igraph.

    Nodes are agents; directed edges represent trade relationships or supply
    chains (e.g. agent A is a regular supplier to agent B).
    """

    def __init__(self) -> None:
        self.graph: ig.Graph = ig.Graph(directed=True)
        self.agent_mappings: dict[int, "EconomicAgent"] = {}

    def reset(self) -> None:
        self.graph = ig.Graph(directed=True)
        self.agent_mappings = {}

    # ── Node management ──────────────────────────────────────────────────

    def add_agent(self, agent: "EconomicAgent") -> None:
        self.graph.add_vertex(agent.economic_agent_id)
        self.agent_mappings[agent.economic_agent_id] = agent

    def remove_agent(self, agent: "EconomicAgent") -> None:
        self.graph.delete_vertices(agent.economic_agent_id)
        del self.agent_mappings[agent.economic_agent_id]

    # ── Edge management (trade links) ────────────────────────────────────

    def add_edge(
        self,
        agent_id_0: int,
        agent_id_1: int,
        transport_cost: float = 0.0,
    ) -> None:
        """Add a directed trade edge: agent_id_0 → agent_id_1.

        Args:
            agent_id_0:     Source agent (seller / supplier).
            agent_id_1:     Target agent (buyer / consumer).
            transport_cost: Fractional surcharge applied on top of the ask
                            price when agent_id_1 buys from agent_id_0
                            (0.0 = same region, no surcharge; 0.1 = 10%).
        """
        try:
            self.graph.add_edge(
                agent_id_0, agent_id_1, transport_cost=transport_cost
            )
        except Exception:
            pass

    def get_transport_cost(self, seller_id: int, buyer_id: int) -> float:
        """Return the transport cost fraction on the edge seller → buyer.

        Returns 0.0 if the edge does not exist (same-region shortcut or
        no graph restriction in effect).
        """
        try:
            eid = self.graph.get_eid(seller_id, buyer_id)
            return float(self.graph.es[eid]["transport_cost"] or 0.0)
        except Exception:
            return 0.0

    def remove_edge(self, agent_id_0: int, agent_id_1: int) -> None:
        if self.graph.are_connected(agent_id_0, agent_id_1):
            self.graph.delete_edges([(agent_id_0, agent_id_1)])

    # ── Queries ──────────────────────────────────────────────────────────

    def get_agent(self, agent_id: int) -> "EconomicAgent":
        return self.agent_mappings[agent_id]

    def get_agents(
        self, agent_ids: list[int] | None = None
    ) -> list[tuple[int, "EconomicAgent"]]:
        if agent_ids:
            return [(aid, self.get_agent(aid)) for aid in agent_ids]
        return [
            (node.index, self.agent_mappings[node.index])
            for node in self.graph.vs
        ]

    def get_edges(self) -> list[tuple[int, int]]:
        return [(e.source, e.target) for e in self.graph.es]

    def get_num_nodes(self) -> int:
        return self.graph.vcount()

    def get_num_edges(self) -> int:
        return self.graph.ecount()

    # ── Visualisation ────────────────────────────────────────────────────

    def visualize(
        self,
        path: str,
        vertex_size: int = 20,
        edge_arrow_size: float = 0.5,
        with_labels: bool = True,
        vertex_color: str = "#1b8ff7",
        width: int = 1000,
        height: int = 1000,
    ) -> None:
        layout = self.graph.layout("auto")
        labels = [node_id for node_id, _ in self.get_agents()] if with_labels else None
        ig.plot(
            self.graph,
            target=path,
            layout=layout,
            vertex_label=labels,
            vertex_size=vertex_size,
            vertex_color=vertex_color,
            edge_arrow_size=edge_arrow_size,
            bbox=(width, height),
        )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from collections import defaultdict

from econ.economic_agent.agent_action import EconomicAction

if TYPE_CHECKING:
    from econ.economic_agent.agent_graph import AgentGraph


@dataclass(frozen=True)
class NeighborInfo:
    agent_id: int
    name: str
    agent_type: str
    region: str
    transport_cost: float


@dataclass(frozen=True)
class MarketSnapshot:
    time_step: str
    balance_result: dict[str, Any] | None
    neighbors: list[NeighborInfo]
    listings: list[dict[str, Any]]
    recent_transactions: list[dict[str, Any]]
    scope_label: str


class MarketSnapshotFetcher:
    def __init__(
        self,
        action: EconomicAction,
        agent_id: int | None,
        agent_graph: "AgentGraph | None",
        max_listings_per_good: int = 5,
    ) -> None:
        self.action = action
        self.agent_id = agent_id
        self.agent_graph = agent_graph
        self.max_listings_per_good = max_listings_per_good

    def _neighbor_ids(self) -> set[int] | None:
        if self.agent_graph is None or self.agent_id is None:
            return None
        try:
            ids = self.agent_graph.graph.neighbors(self.agent_id, mode="out")
            return set(ids)
        except Exception:
            return None

    def _neighbors(self) -> list[NeighborInfo]:
        if self.agent_graph is None or self.agent_id is None:
            return []
        neighbor_ids = self._neighbor_ids()
        if not neighbor_ids:
            return []
        neighbors: list[NeighborInfo] = []
        for nid in sorted(neighbor_ids):
            try:
                neighbor = self.agent_graph.get_agent(nid)
                cost = self.agent_graph.get_transport_cost(nid, self.agent_id)
                region = neighbor.agent_info.region or "unknown region"
                neighbors.append(
                    NeighborInfo(
                        agent_id=nid,
                        name=neighbor.agent_info.name,
                        agent_type=neighbor.agent_info.agent_type,
                        region=region,
                        transport_cost=cost,
                    )
                )
            except Exception:
                neighbors.append(
                    NeighborInfo(
                        agent_id=nid,
                        name="unknown",
                        agent_type="unknown",
                        region="unknown region",
                        transport_cost=0.0,
                    )
                )
        return neighbors

    def _annotate_listings(
        self,
        listings: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        """One global auction: show all resting asks, annotated with the
        transport cost from each seller to this agent (no region filtering).
        """
        annotated: list[dict[str, Any]] = []
        for r in listings:
            row = dict(r)
            rate = 0.0
            if self.agent_graph is not None and self.agent_id is not None:
                try:
                    rate = self.agent_graph.get_transport_cost(
                        int(r.get("seller_id")), self.agent_id
                    )
                except Exception:
                    rate = 0.0
            row["transport_cost_rate"] = rate
            row["effective_price"] = round(float(r.get("ask_price", 0.0)) * (1 + rate), 4)
            annotated.append(row)

        # Show the cheapest few (by effective price) per good to keep the prompt small.
        annotated.sort(key=lambda r: (str(r.get("good_name")), r["effective_price"]))
        if self.max_listings_per_good > 0:
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in annotated:
                grouped[str(r.get("good_name"))].append(r)
            limited: list[dict[str, Any]] = []
            for good_name in sorted(grouped):
                limited.extend(grouped[good_name][: self.max_listings_per_good])
            annotated = limited

        return annotated, "all regions, global auction"

    async def fetch(self) -> MarketSnapshot:
        market_result = await self.action.observe_market()
        time_step = (
            market_result.get("time_step", "?")
            if market_result.get("success")
            else "?"
        )

        balance_result = await self.action.check_balance()
        if not balance_result.get("success"):
            balance_result = None

        all_listings = (
            market_result.get("listings", [])
            if market_result.get("success")
            else []
        )
        listings, scope_label = self._annotate_listings(all_listings)

        txs = (
            market_result.get("recent_transactions", [])
            if market_result.get("success")
            else []
        )

        return MarketSnapshot(
            time_step=str(time_step),
            balance_result=balance_result,
            neighbors=self._neighbors(),
            listings=list(listings),
            recent_transactions=list(txs),
            scope_label=scope_label,
        )

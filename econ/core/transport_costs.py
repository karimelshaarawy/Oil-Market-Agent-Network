from __future__ import annotations

from typing import Protocol


class TransportCostProvider(Protocol):
    def get_cost(self, from_agent_id: int, to_agent_id: int) -> float:
        ...

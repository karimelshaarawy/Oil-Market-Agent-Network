from __future__ import annotations

from typing import Any, Protocol, TypedDict


class AgentProfile(TypedDict):
    name: str
    agent_type: str
    region: str | None
    produces: list[str]
    consumption_needs: list[dict[str, Any]]


class ProfileStore(Protocol):
    def get_profile(self, agent_id: int) -> AgentProfile:
        ...

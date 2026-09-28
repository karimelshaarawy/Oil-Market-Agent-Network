"""Shared fixtures and factories for platform component tests.

All tests run against an in-memory SQLite database with no LLM involved.
"""
from __future__ import annotations

from typing import Any

from econ.clock.clock import Clock
from econ.economic_platform.platform import EconomicPlatform


class DictProfileStore:
    """ProfileStore backed by a plain dict; unknown agents get an empty profile."""

    def __init__(self, profiles: dict[int, dict] | None = None) -> None:
        self.profiles = profiles or {}

    def get_profile(self, agent_id: int) -> dict:
        return self.profiles.get(int(agent_id), {})


class FlatTransportCosts:
    """TransportCostProvider returning the same rate for every pair."""

    def __init__(self, rate: float = 0.0) -> None:
        self.rate = rate

    def get_cost(self, from_agent_id: int, to_agent_id: int) -> float:
        return self.rate


def make_platform(**overrides: Any) -> tuple[EconomicPlatform, list[dict]]:
    """Build an in-memory platform plus a list collecting emitted events."""
    events: list[dict] = []

    async def collector(event: dict) -> None:
        events.append(event)

    kwargs: dict[str, Any] = dict(
        db_path=":memory:",
        profile_store=DictProfileStore(),
        transport_costs=FlatTransportCosts(0.0),
        clock=Clock(),
        event_bus=collector,
    )
    kwargs.update(overrides)
    return EconomicPlatform(**kwargs), events


async def register_agent(
    platform: EconomicPlatform,
    agent_id: int,
    *,
    name: str | None = None,
    agent_type: str = "firm",
    sector: str = "energy",
    balance: float = 1000.0,
    region: str = "NA",
    produces: tuple[str, ...] = (),
) -> dict:
    result = await platform.register(
        agent_id,
        (name or f"agent_{agent_id}", agent_type, sector, balance, region, list(produces)),
    )
    assert result["success"]
    return result


def balance_of(platform: EconomicPlatform, agent_id: int) -> float:
    row = platform.db.execute(
        "SELECT balance FROM agent WHERE agent_id = ?", (agent_id,)
    ).fetchone()
    return float(row["balance"])


def ledger_rows(platform: EconomicPlatform, agent_id: int) -> list[dict]:
    rows = platform.db.execute(
        "SELECT step, category, amount, description FROM financial_ledger "
        "WHERE agent_id = ? ORDER BY ledger_id",
        (agent_id,),
    ).fetchall()
    return [dict(r) for r in rows]

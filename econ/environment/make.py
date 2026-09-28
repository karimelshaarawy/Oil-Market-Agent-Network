from __future__ import annotations

from typing import Awaitable, Callable, TYPE_CHECKING, Union

from econ.core.adapters import AgentGraphProfileStore, AgentGraphTransportCosts
from econ.core.config import (
    DEFAULT_LLM_SEMAPHORE,
    LOAN_REQUEST_EXPIRY_STEPS,
    MAX_INTEREST_RATE,
    MIN_INTEREST_RATE,
)
from econ.economic_platform.channel import Channel
from econ.economic_platform.platform import EconomicPlatform
from econ.economic_platform.typing import DefaultEconomyType
from econ.environment.env import EconomicEnv
from econ.rag import ChromaSimulationMemory

if TYPE_CHECKING:
    from econ.economic_agent.agent_graph import AgentGraph


def make(
    agent_graph: "AgentGraph",
    economy_type: Union[DefaultEconomyType, EconomicPlatform],
    database_path: str = "economy.db",
    semaphore: int = DEFAULT_LLM_SEMAPHORE,
    interest_rate: float = 0.05,
    loan_duration_steps: int = 10,
    consumer_income_per_step: float = 0.0,
    consumer_operations_enabled: bool = True,
    auto_cancel_steps: int = 3,
    shortage_penalty_grace_steps: int = 0,
    max_borrow_fraction: float = 0.5,
    min_interest_rate: float = MIN_INTEREST_RATE,
    max_interest_rate: float = MAX_INTEREST_RATE,
    loan_request_expiry_steps: int = LOAN_REQUEST_EXPIRY_STEPS,
    rag_enabled: bool = False,
    rag_persist_directory: str = "chroma_econ",
    rag_collection_name: str = "econ_memory",
    rag_top_k: int = 8,
    rag_reset_on_start: bool = True,
    event_bus: Callable[[dict], Awaitable[None]] | None = None,
) -> EconomicEnv:
    """Factory function — the main public entry point.

    Creates an ``EconomicEnv`` wired with a fresh ``Channel`` and
    ``EconomicPlatform``.

    Args:
        agent_graph:             Populated ``AgentGraph`` of all agents.
        economy_type:            ``DefaultEconomyType`` preset or a custom
                                 ``EconomicPlatform`` instance.
        database_path:           Path to the SQLite ``.db`` file.
        semaphore:               Max concurrent LLM requests.  Keep this low
                                 (2–4) to avoid 429 rate-limit errors on
                                 shared inference servers.
        interest_rate:           Default per-step interest rate for loans.
        loan_duration_steps:     Steps before a loan is considered overdue.
        consumer_income_per_step: Optional legacy flat credits granted to every
                                 consumer. Prefer consumer_operations_enabled.
        consumer_operations_enabled: If True, consumers earn operating revenue
                                     only by consuming required oil/fuel inputs.

    Returns:
        A configured ``EconomicEnv`` ready for ``reset()`` → ``step()`` → ``close()``.

    Example::

        env = make(agent_graph, DefaultEconomyType.SIMPLE_GOODS, "run1.db",
                   consumer_income_per_step=500.0)
        await env.reset()
    """
    if isinstance(economy_type, DefaultEconomyType):
        channel = Channel()
        profile_store = AgentGraphProfileStore(agent_graph)
        transport_costs = AgentGraphTransportCosts(agent_graph)
        platform = EconomicPlatform(
            db_path=database_path,
            profile_store=profile_store,
            transport_costs=transport_costs,
            channel=channel,
            interest_rate=interest_rate,
            loan_duration_steps=loan_duration_steps,
            consumer_income_per_step=consumer_income_per_step,
            consumer_operations_enabled=consumer_operations_enabled,
            auto_cancel_steps=auto_cancel_steps,
            shortage_penalty_grace_steps=shortage_penalty_grace_steps,
            max_borrow_fraction=max_borrow_fraction,
            min_interest_rate=min_interest_rate,
            max_interest_rate=max_interest_rate,
            loan_request_expiry_steps=loan_request_expiry_steps,
            event_bus=event_bus,
        )
    elif isinstance(economy_type, EconomicPlatform):
        platform = economy_type
    else:
        raise ValueError(
            f"economy_type must be a DefaultEconomyType or EconomicPlatform, "
            f"got {type(economy_type)}"
        )

    rag_memory = (
        ChromaSimulationMemory(
            persist_directory=rag_persist_directory,
            collection_name=rag_collection_name,
            top_k=rag_top_k,
            enabled=True,
            reset_collection=rag_reset_on_start,
        )
        if rag_enabled
        else None
    )

    return EconomicEnv(
        agent_graph=agent_graph,
        platform=platform,
        semaphore=semaphore,
        rag_memory=rag_memory,
        event_bus=event_bus,
    )

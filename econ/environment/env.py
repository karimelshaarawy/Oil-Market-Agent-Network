from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TYPE_CHECKING, Union

from econ.core.config import DEFAULT_LLM_SEMAPHORE
from econ.economic_agent.agents_generator import generate_custom_agents
from econ.economic_platform.channel import Channel
from econ.economic_platform.platform import EconomicPlatform
from econ.economic_platform.typing import ActionType, DefaultEconomyType
from econ.environment.env_action import LLMAction, ManualAction

if TYPE_CHECKING:
    from econ.economic_agent.agent import EconomicAgent
    from econ.economic_agent.agent_graph import AgentGraph
    from econ.rag import ChromaSimulationMemory

logger = logging.getLogger("econ.env")


class EconomicEnv:
    """Top-level simulation orchestrator:

    - Holds the ``AgentGraph`` (who participates).
    - Spawns ``EconomicPlatform`` as a background asyncio task.
    - Drives the step loop: update market state → dispatch agent actions.

    Typical usage::

        env = make(agent_graph, DefaultEconomyType.SIMPLE_GOODS, "economy.db")
        await env.reset()
        for _ in range(N_STEPS):
            actions = {agent: LLMAction() for _, agent in env.agent_graph.get_agents()}
            await env.step(actions)
        await env.close()
    """

    def __init__(
        self,
        agent_graph: "AgentGraph",
        platform: EconomicPlatform,
        semaphore: int = DEFAULT_LLM_SEMAPHORE,
        rag_memory: "ChromaSimulationMemory | None" = None,
        pre_step_hook: Callable[["EconomicEnv", dict], Awaitable[None]] | None = None,
        post_step_hook: Callable[["EconomicEnv", dict, list], Awaitable[None]] | None = None,
        event_bus: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        self.agent_graph = agent_graph
        self.platform = platform
        self.channel = platform.channel
        self.llm_semaphore = asyncio.Semaphore(semaphore)
        self._chroma_lock = asyncio.Lock()
        self.rag_memory = rag_memory
        self.pre_step_hook = pre_step_hook
        self.post_step_hook = post_step_hook
        self.event_bus = event_bus
        if self.rag_memory is not None and self.post_step_hook is None:
            self.post_step_hook = self._rag_post_step

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def reset(self) -> None:
        """Start the platform background task and register all agents."""
        self.platform_task = asyncio.create_task(self.platform.running())
        self.agent_graph = await generate_custom_agents(
            channel=self.channel,
            agent_graph=self.agent_graph,
        )
        for _, agent in self.agent_graph.get_agents():
            agent.env.rag_memory = self.rag_memory
            agent.env.agent_info = agent.agent_info
        logger.info("All agents registered. Economy ready.")

    async def close(self) -> None:
        """Shut down the platform and flush the database."""
        await self.channel.write_to_receive_queue((None, None, ActionType.EXIT))
        await self.platform_task
        logger.info("Simulation finished. Database: %s", self.platform.db_path)

    # ── Step ─────────────────────────────────────────────────────────────

    async def step(
        self,
        actions: dict["EconomicAgent", Union[ManualAction, LLMAction]],
    ) -> None:
        """Run one simulation step.

        1. Update market state (purge exhausted listings, grant income, auto-cancel stale asks).
        2. Dispatch every agent's action concurrently (agents submit asks/bids).
        3. Clear the call auction at a uniform price per good.
        4. Apply consumer operating needs: consume inventory + shortage penalty
           (after clearing so a consumer's winning bid feeds this step's consumption).
        5. Advance the clock.

        Args:
            actions: Mapping of agent → action.  Pass ``ManualAction`` to
                script the agent's behaviour or ``LLMAction`` for autonomous
                LLM-driven decision.
        """
        if self.pre_step_hook is not None:
            await self.pre_step_hook(self, actions)
        await self.platform.update_market_state()

        tasks = []
        llm_agents: list["EconomicAgent"] = []
        for agent, action in actions.items():
            if isinstance(action, ManualAction):
                tasks.append(
                    agent.perform_action_by_data(
                        action.action_type, **action.action_args
                    )
                )
            elif isinstance(action, LLMAction):
                llm_agents.append(agent)
                tasks.append(self._perform_llm_action(agent))

        await asyncio.gather(*tasks)
        await self.platform.clear_market()
        await self.platform.apply_consumer_needs()
        if self.event_bus is not None:
            await self._emit_step_complete(self.platform.clock.now())
        if self.post_step_hook is not None:
            await self.post_step_hook(self, actions, llm_agents)
        self.platform.clock.tick()
        logger.info("Step %d complete.", self.platform.clock.now())

    async def _emit_step_complete(self, step: int) -> None:
        rows = self.platform.db.execute(
            "SELECT name, balance FROM agent ORDER BY agent_id"
        ).fetchall()
        balances: dict[str, float] = {
            row["name"]: round(float(row["balance"]), 2) for row in rows
        }
        prices: dict[str, float] = {}
        for good_row in self.platform.db.execute(
            "SELECT DISTINCT good_name FROM price_history"
        ).fetchall():
            latest = self.platform.db.execute(
                "SELECT price FROM price_history WHERE good_name = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (good_row["good_name"],),
            ).fetchone()
            if latest:
                prices[good_row["good_name"]] = round(float(latest["price"]), 2)
        await self.event_bus({
            "type": "step_complete",
            "step": step,
            "balances": balances,
            "prices": prices,
        })

    async def _perform_llm_action(self, agent: "EconomicAgent"):
        async with self.llm_semaphore:
            return await agent.perform_action_by_llm()

    async def _reflect_and_index(self, agent: "EconomicAgent", step: int) -> None:
        """Ask one agent to reflect on its step and index that reflection."""
        if self.rag_memory is None:
            return
        async with self.llm_semaphore:
            reflection = await agent.perform_step_reflection(step)
        if reflection:
            self.platform.record_agent_reflection(
                agent_id=agent.economic_agent_id,
                step=step,
                reflection=reflection,
            )
            async with self._chroma_lock:
                self.rag_memory.index_agent_reflection(step, agent, reflection)

    async def _rag_post_step(
        self,
        _env: "EconomicEnv",
        _actions: dict,
        llm_agents: list["EconomicAgent"],
    ) -> None:
        if self.rag_memory is None:
            return
        step = self.platform.clock.now()
        async with self._chroma_lock:
            self.rag_memory.index_step(
                db=self.platform.db,
                agent_graph=self.agent_graph,
                step=step,
            )
        reflection_tasks = [
            self._reflect_and_index(agent, step)
            for agent in llm_agents
        ]
        await asyncio.gather(*reflection_tasks)

    def broadcast_event(self, event_text: str | None) -> None:
        """Inject (or clear) a market-event message into every agent's observation.

        Call this before ``step()`` to have all agents see the event in their
        prompt that step.  Pass ``None`` to clear the event afterwards.

        Args:
            event_text: A short description of the event, e.g.
                ``"A trade war has doubled steel tariffs."``
                Pass ``None`` to remove the event banner.
        """
        if self.rag_memory is not None:
            self.rag_memory.index_event(
                step=self.platform.clock.now(),
                event_text=event_text,
            )
        for _, agent in self.agent_graph.get_agents():
            agent.env.current_event = event_text

    async def interview_agents(
        self,
        agents: list["EconomicAgent"],
        prompt: str,
    ) -> list[dict]:
        """Ask all given agents the same interview question concurrently."""
        tasks = [agent.perform_interview(prompt) for agent in agents]
        return await asyncio.gather(*tasks)

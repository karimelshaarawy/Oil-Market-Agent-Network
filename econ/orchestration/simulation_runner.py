from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from dataclasses import dataclass, replace
from typing import Awaitable, Callable

from dotenv import load_dotenv

import econ
from econ.core.config import env_int
from econ.core.model_factory import build_chat_model
from econ.economic_agent.agent import EconomicAgent
from econ.economic_agent.agent_graph import AgentGraph
from econ.economic_agent.agents_generator import generate_agent_graph_from_profiles
from econ.economic_platform.typing import ActionType, DefaultEconomyType
from econ.environment.env import EconomicEnv
from econ.environment.env_action import LLMAction, ManualAction
from econ.orchestration.oil_market_config import (
    CONSUMER_INCOME_PER_STEP,
    CONSUMER_OPERATIONS_ENABLED,
    AUTO_CANCEL_STEPS,
    CROSS_REGION_COST,
    EVENTS,
    INTEREST_RATE,
    LOAN_DURATION_STEPS,
    PROFILE_PATH,
    RAG_TOP_K,
    SEED,
    SHORTAGE_PENALTY_GRACE_STEPS,
    known_goods,
    load_profiles,
)
from econ.news import build_live_news_events
from econ.scenario import build_scenario_pack, fallback_scenario_pack
from econ.scenario.scenario_pack import ScenarioPack
from econ.orchestration.run_storage import SimulationRunPaths, create_run_paths, write_manifest

load_dotenv(override=True)


class SimulationCancelled(Exception):
    """Raised internally when the caller requests a stop.

    This is a *control-flow* signal, not an error: the WebSocket layer
    catches it and reports ``{"type": "stopped"}`` rather than an error.
    """


def _check_cancelled(cancel_event: "asyncio.Event | None") -> None:
    """Cheap synchronous checkpoint between phases / before each step."""
    if cancel_event is not None and cancel_event.is_set():
        raise SimulationCancelled()


_REQUIRED_PROFILE_FIELDS = ("name", "agent_type", "sector", "initial_capital")


def _validate_custom_profiles(profiles: list[dict]) -> list[dict]:
    """Validate a user-supplied agent roster from the frontend builder.

    ``generate_agent_graph_from_profiles`` reads the four required fields and
    defaults the rest, so we only enforce what would otherwise fail loudly or —
    worse — silently. The ``ValueError``s raised here surface to the client as an
    ``{"type": "error"}`` event via the WS layer.
    """
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("custom_agents must be a non-empty list of agent profiles.")

    seen_names: set[str] = set()
    normalized: list[dict] = []
    for i, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            raise ValueError(f"Agent #{i + 1} is not a valid object.")
        for field in _REQUIRED_PROFILE_FIELDS:
            if profile.get(field) in (None, ""):
                raise ValueError(f"Agent #{i + 1} is missing '{field}'.")

        name = str(profile["name"]).strip()
        if name in seen_names:
            # Duplicate names silently clobber the agents_by_name lookup, leaving
            # one agent unreachable — reject up front instead.
            raise ValueError(f"Duplicate agent name '{name}' — names must be unique.")
        seen_names.add(name)

        copied = dict(profile)
        copied["name"] = name
        try:
            copied["initial_capital"] = float(profile["initial_capital"])
            copied["risk_tolerance"] = float(profile.get("risk_tolerance", 0.5))
        except (TypeError, ValueError):
            raise ValueError(f"Agent '{name}' has non-numeric capital or risk tolerance.")
        normalized.append(copied)

    return normalized


async def _guard(awaitable, cancel_event: "asyncio.Event | None"):
    """Await ``awaitable``, but abort it immediately if ``cancel_event`` fires.

    The awaitable is run as a task; if the stop event wins the race we cancel
    that task, which propagates ``CancelledError`` down through ``env.step``'s
    ``asyncio.gather`` into each agent's in-flight ``AsyncOpenAI`` request so
    the network call is actually torn down. Then we raise
    :class:`SimulationCancelled` so the run unwinds.
    """
    if cancel_event is None:
        return await awaitable

    task = asyncio.ensure_future(awaitable)
    waiter = asyncio.ensure_future(cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {task, waiter}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await waiter

    if task in done:
        return task.result()

    # Stop requested mid-flight: tear down the in-flight work and bail.
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
    raise SimulationCancelled()


# Module-level strong references for cancelled platform tasks. asyncio
# emits "Task was destroyed but it is pending!" if a pending task is GC'd
# before its cancellation is processed; keeping a strong reference here
# until the done_callback fires prevents that.
_PENDING_PLATFORM_CLEANUPS: "set[asyncio.Task]" = set()


def _track_until_done(task: asyncio.Task) -> None:
    _PENDING_PLATFORM_CLEANUPS.add(task)
    task.add_done_callback(_PENDING_PLATFORM_CLEANUPS.discard)


@dataclass
class SimulationSession:
    simulation_id: str
    run_dir: str
    chroma_dir: str
    scenario_dir: str
    env: EconomicEnv
    agent_graph: AgentGraph
    agents_by_name: dict[str, EconomicAgent]
    db_path: str
    rag_enabled: bool
    scenario_pack: ScenarioPack

    @property
    def agent_names(self) -> list[str]:
        return sorted(self.agents_by_name)


def build_model():
    return build_chat_model(temperature=0.4)


def _inject_scenario_into_profiles(
    profiles: list[dict],
    scenario_pack: ScenarioPack,
) -> list[dict]:
    world_context = scenario_pack.world_context_prompt()
    price_anchors = scenario_pack.price_anchor_prompt()
    if not world_context and not price_anchors:
        return profiles
    enriched: list[dict] = []
    for profile in profiles:
        copied = dict(profile)
        copied["scenario_context"] = world_context
        copied["price_anchors"] = price_anchors
        enriched.append(copied)
    return enriched


async def run_oil_simulation(
    n_steps: int,
    db_path: str | None,
    semaphore: int,
    max_iteration: int,
    rag_enabled: bool,
    rag_reset_on_start: bool,
    include_upstream: bool = True,
    include_downstream: bool = True,
    include_financial: bool = True,
    include_consumer: bool = True,
    custom_profiles: list[dict] | None = None,
    seed_context_text: str | None = None,
    use_generated_events: bool = False,
    use_live_news: bool = False,
    news_lookback_days: int | None = None,
    progress: Callable[[str], None] | None = None,
    event_bus: Callable[[dict], Awaitable[None]] | None = None,
    cancel_event: "asyncio.Event | None" = None,
) -> SimulationSession:
    """Run the oil simulation and return objects plus a persistent run id.

    This mirrors MiroFish's approach: a run is addressable after completion via
    a ``simulation_id`` and a persistent folder that contains:
    - SQLite database
    - Chroma persistence directory
    - manifest.json snapshot of parameters
    """
    def emit(message: str) -> None:
        if progress is not None:
            progress(message)

    # Allocate a new persistent run folder.
    db_filename = Path(db_path).name if db_path else "simulation.db"
    run_paths: SimulationRunPaths = create_run_paths(db_filename=db_filename)
    resolved_db_path = str(run_paths.db_path.resolve())
    resolved_chroma_dir = str(run_paths.chroma_dir)
    resolved_scenario_dir = str(run_paths.scenario_dir)

    # Write manifest early so live queries during the run can resolve db_path.
    write_manifest(run_paths, {"status": "running"})

    if event_bus is not None:
        await event_bus({
            "type": "simulation_start",
            "simulation_id": run_paths.simulation_id,
        })

    # ``env`` is created partway through setup; initialise it here so the
    # teardown ``finally`` is safe even if a stop is requested before then.
    env = None
    try:
        include = {
            "upstream": include_upstream,
            "downstream": include_downstream,
            "financial": include_financial,
            "consumer": include_consumer,
        }

        # A user-supplied roster (from the frontend agent builder) fully replaces
        # the file-loaded agents; the category switches only apply to the default
        # file roster.
        if custom_profiles:
            profiles = _validate_custom_profiles(custom_profiles)
            emit(f"Using {len(profiles)} custom agent profiles.")
        else:
            # Reuse the example loader, then apply UI category switches.
            all_profiles = load_profiles()
            profiles = [p for p in all_profiles if include.get(p.get("category", ""), True)]
            emit(f"Loaded {len(profiles)} profiles from {Path(PROFILE_PATH).name}.")

        _check_cancelled(cancel_event)
        # build_scenario_pack is async (AsyncOpenAI under the hood); guarding the
        # await lets a stop cancel the in-flight LLM call directly — no thread.
        scenario_pack = await _guard(
            build_scenario_pack(
                seed_text=seed_context_text,
                n_steps=int(n_steps),
                goods=known_goods(profiles),
                fallback_events=EVENTS,
            ),
            cancel_event,
        )
        if not use_generated_events:
            fallback_pack = fallback_scenario_pack(EVENTS)
            scenario_pack = ScenarioPack(
                summary=scenario_pack.summary,
                macro_facts=scenario_pack.macro_facts,
                uncertainties=scenario_pack.uncertainties,
                price_anchors=scenario_pack.price_anchors,
                events=fallback_pack.events,
                raw_seed_text=scenario_pack.raw_seed_text,
                generated=scenario_pack.generated,
                source=(
                    "seed_documents_with_hardcoded_events"
                    if scenario_pack.generated
                    else fallback_pack.source
                ),
            )
        # Live-news override: replace the event schedule with one derived from
        # recent real oil news. On any failure we keep the schedule built above
        # (generated or hardcoded), so a "live news" run never breaks.
        news_snapshot: dict | None = None
        if use_live_news:
            emit("Fetching live oil news to build event schedule...")
            try:
                live = await _guard(
                    build_live_news_events(
                        int(n_steps),
                        known_goods(profiles),
                        lookback_days=news_lookback_days,
                    ),
                    cancel_event,
                )
            except SimulationCancelled:
                raise
            except Exception as exc:  # defensive — service already guards internally
                live = None
                emit(f"Live news failed ({exc}) — falling back to existing event schedule.")
            if live is not None:
                live_events, news_snapshot = live
                scenario_pack = replace(scenario_pack, events=live_events, source="live_news")
                fired = sum(1 for e in live_events if e.event_text)
                emit(f"Using live oil-news schedule ({fired}/{n_steps} steps have events).")
            else:
                emit("Live news unavailable — falling back to existing event schedule.")

        scenario_artifacts = scenario_pack.persist(run_paths.scenario_dir)
        if news_snapshot is not None:
            live_news_path = Path(run_paths.scenario_dir) / "live_news.json"
            live_news_path.write_text(json.dumps(news_snapshot, indent=2), encoding="utf-8")
            scenario_artifacts["live_news_path"] = str(live_news_path)
        if scenario_pack.source == "live_news":
            pass  # already emitted above
        elif scenario_pack.generated:
            emit("Built generated scenario pack from seed context.")
        else:
            emit("Using fallback hardcoded scenario events.")

        profiles = _inject_scenario_into_profiles(profiles, scenario_pack)

        _check_cancelled(cancel_event)
        agent_graph = await _guard(
            generate_agent_graph_from_profiles(
                profiles=profiles,
                model=build_model(),
                cross_region_transport_cost=CROSS_REGION_COST,
                token_limit=env_int("ECON_CAMEL_TOKEN_LIMIT", 32768),
                max_iteration=max_iteration,
            ),
            cancel_event,
        )
        emit(f"Built graph with {agent_graph.get_num_nodes()} agents.")

        env = econ.make(
            agent_graph=agent_graph,
            economy_type=DefaultEconomyType.SIMPLE_GOODS,
            database_path=resolved_db_path,
            semaphore=semaphore,
            interest_rate=INTEREST_RATE,
            loan_duration_steps=LOAN_DURATION_STEPS,
            consumer_income_per_step=CONSUMER_INCOME_PER_STEP,
            consumer_operations_enabled=CONSUMER_OPERATIONS_ENABLED,
            auto_cancel_steps=AUTO_CANCEL_STEPS,
            shortage_penalty_grace_steps=SHORTAGE_PENALTY_GRACE_STEPS,
            rag_enabled=rag_enabled,
            rag_persist_directory=resolved_chroma_dir,
            rag_top_k=RAG_TOP_K,
            rag_reset_on_start=rag_reset_on_start,
            event_bus=event_bus,
        )
        await _guard(env.reset(), cancel_event)
        emit("Registered all agents.")

        agents_by_name = {
            agent.agent_info.name: agent
            for _, agent in agent_graph.get_agents()
        }

        seed_actions = {
            agents_by_name[name]: ManualAction(
                action_type=ActionType.PRODUCE,
                action_args={"good_name": good, "quantity": qty, "unit_cost": cost},
            )
            for name, (good, qty, cost) in SEED.items()
            if name in agents_by_name
        }
        if seed_actions:
            await _guard(env.step(seed_actions), cancel_event)
            emit("Seeded initial inventories.")

        all_agents = [agent for _, agent in agent_graph.get_agents()]
        event_schedule = scenario_pack.events_by_step
        for step in range(1, n_steps + 1):
            # Honour a stop request before starting any new step so we never
            # kick off another round of LLM calls once cancellation is asked.
            _check_cancelled(cancel_event)
            event_text: str | None = None
            if step in event_schedule:
                event_text = event_schedule[step]
                env.broadcast_event(event_text)
                if event_text:
                    emit(f"Step {step}: event fired: {event_text[:120]}...")
                else:
                    emit(f"Step {step}: event cleared.")
            else:
                emit(f"Step {step}: agents deliberating.")

            if event_bus is not None:
                await event_bus({
                    "type": "step_start",
                    "step": step,
                    "event_text": event_text,
                })

            await _guard(
                env.step({agent: LLMAction() for agent in all_agents}),
                cancel_event,
            )
            emit(f"Step {step}: complete.")

        write_manifest(
            run_paths,
            {
                "status": "complete",
                "params": {
                    "n_steps": int(n_steps),
                    "semaphore": int(semaphore),
                    "max_iteration": int(max_iteration),
                    "rag_enabled": bool(rag_enabled),
                    "rag_reset_on_start": bool(rag_reset_on_start),
                    "include_upstream": bool(include_upstream),
                    "include_downstream": bool(include_downstream),
                    "include_financial": bool(include_financial),
                    "include_consumer": bool(include_consumer),
                    "use_generated_events": bool(use_generated_events),
                    "use_live_news": bool(use_live_news),
                    "news_lookback_days": (
                        int(news_lookback_days) if news_lookback_days is not None else None
                    ),
                    "custom_agents": (
                        [p["name"] for p in profiles] if custom_profiles else None
                    ),
                },
                "profile_path": str(Path(PROFILE_PATH).name),
                "scenario": {
                    "generated": scenario_pack.generated,
                    "source": scenario_pack.source,
                    **scenario_artifacts,
                },
            },
        )

        emit(
            "Simulation complete. You can now use ReportAgent or chat with agents. "
            f"simulation_id={run_paths.simulation_id}"
        )
        if event_bus is not None:
            await event_bus({
                "type": "simulation_complete",
                "simulation_id": run_paths.simulation_id,
                "agent_names": sorted(agents_by_name.keys()),
            })
        return SimulationSession(
            simulation_id=run_paths.simulation_id,
            run_dir=str(run_paths.run_dir),
            chroma_dir=resolved_chroma_dir,
            scenario_dir=resolved_scenario_dir,
            env=env,
            agent_graph=agent_graph,
            agents_by_name=agents_by_name,
            db_path=resolved_db_path,
            rag_enabled=rag_enabled,
            scenario_pack=scenario_pack,
        )
    except SimulationCancelled:
        # Hard-abort requested: discard the partial run and mark it aborted.
        emit("Simulation stopped by user.")
        with contextlib.suppress(Exception):
            write_manifest(run_paths, {"status": "aborted"})
        raise
    finally:
        # Tear down the perpetual platform task without blocking. Awaiting
        # the task here can hang or re-raise when we're already in a
        # cancellation-propagation path; instead we cancel and hold a
        # strong reference until the cancellation actually completes, so
        # the task doesn't get GC'd while still pending.
        task = getattr(env, "platform_task", None)
        if task is not None and not task.done():
            task.cancel()
            _track_until_done(task)

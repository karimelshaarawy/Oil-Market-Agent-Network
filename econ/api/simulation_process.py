"""Process-isolated simulation execution for the API.

A run is executed in a *spawned child process* so a stop request can always
halt the backend: the parent first asks the child to exit cleanly (aborting
in-flight async calls), then SIGKILLs it if it overruns the grace window.

Accepted ``params`` keys (all optional, defaults in ``_run_oil_inproc``):
``n_steps``, ``db_path``, ``semaphore``, ``max_iteration``, ``rag_enabled``,
``rag_reset_on_start``, ``include_upstream``, ``include_downstream``,
``include_financial``, ``include_consumer``, ``custom_agents``,
``use_generated_events``, ``use_live_news``, ``news_lookback_days``,
``seed_context_text``.
"""
from __future__ import annotations

import asyncio
import contextlib
import multiprocessing as mp
import queue as queue_mod

from econ.core.config import STOP_GRACE_SECONDS as _STOP_GRACE_SECONDS
from econ.orchestration.simulation_runner import run_oil_simulation, SimulationCancelled


async def _run_oil_inproc(
    params: dict,
    event_bus,
    cancel_event: asyncio.Event | None = None,
) -> None:
    """Run one simulation in the current process, emitting events via ``event_bus``.

    This is the body that actually executes the simulation. In production it runs
    inside a *child process* (see ``_sim_child_main``) so a stop can hard-kill it;
    a stop sets ``cancel_event`` first for a clean async unwind.
    """
    try:
        await run_oil_simulation(
            n_steps=int(params.get("n_steps", 8)),
            db_path=params.get("db_path"),
            semaphore=int(params.get("semaphore", 3)),
            max_iteration=int(params.get("max_iteration", 3)),
            rag_enabled=bool(params.get("rag_enabled", True)),
            rag_reset_on_start=bool(params.get("rag_reset_on_start", True)),
            include_upstream=bool(params.get("include_upstream", True)),
            include_downstream=bool(params.get("include_downstream", True)),
            include_financial=bool(params.get("include_financial", True)),
            include_consumer=bool(params.get("include_consumer", True)),
            custom_profiles=params.get("custom_agents") or None,
            use_generated_events=bool(params.get("use_generated_events", False)),
            use_live_news=bool(params.get("use_live_news", False)),
            news_lookback_days=(
                int(params["news_lookback_days"])
                if params.get("news_lookback_days") is not None
                else None
            ),
            seed_context_text=params.get("seed_context_text") or None,
            event_bus=event_bus,
            cancel_event=cancel_event,
        )
    except SimulationCancelled:
        # Expected on a stop request — the WS layer reports {"type":"stopped"}.
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await event_bus({"type": "error", "message": str(exc)})


# Sentinel pushed by the child onto the event queue when the run is fully done.
_DONE = {"__sim_done__": True}


def _sim_child_main(params: dict, event_q, stop_evt) -> None:
    """Child-process entry point (spawned). Runs the sim, streams events to a queue.

    A stop is delivered via ``stop_evt`` (a multiprocessing.Event); a watcher
    bridges it to the asyncio ``cancel_event`` so in-flight async calls abort
    cleanly. The parent SIGKILLs this process if it overruns the grace window.
    """
    async def _amain() -> None:
        cancel_event = asyncio.Event()

        async def bus(event: dict) -> None:
            event_q.put(event)

        async def _watch_stop() -> None:
            # Poll the cross-process stop flag. Polling (not run_in_executor on
            # stop_evt.wait) keeps this fully cancellable — otherwise a blocked
            # non-daemon executor thread would stall asyncio.run() shutdown and
            # the child would never exit after a clean finish.
            while not stop_evt.is_set():
                await asyncio.sleep(0.1)
            cancel_event.set()

        watcher = asyncio.create_task(_watch_stop())
        try:
            await _run_oil_inproc(params, bus, cancel_event)
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    try:
        asyncio.run(_amain())
    finally:
        # Signal completion and flush the queue's feeder thread before exit so
        # the final event (simulation_complete / error) reaches the parent.
        with contextlib.suppress(Exception):
            event_q.put(_DONE)
            event_q.close()
            event_q.join_thread()


async def _run_simulation(
    params: dict,
    event_bus,
    cancel_event: asyncio.Event,
    child_target=_sim_child_main,
) -> None:
    """Process-isolated runner: spawn the sim in a child, bridge its events.

    Guarantees a stop halts ALL backend work — including any blocking code that
    asyncio cancellation can't reach — by SIGKILLing the child after a short
    graceful window. On a clean run it just forwards events and returns.

    ``child_target`` is injectable for testing; production uses ``_sim_child_main``.
    """
    ctx = mp.get_context("spawn")
    event_q = ctx.Queue()
    stop_evt = ctx.Event()
    proc = ctx.Process(
        target=child_target, args=(params, event_q, stop_evt), daemon=True
    )
    proc.start()
    loop = asyncio.get_running_loop()

    async def _pump() -> None:
        """Forward child events to the WS bus until the child signals it is done."""
        while True:
            try:
                item = await loop.run_in_executor(None, event_q.get, True, 0.2)
            except queue_mod.Empty:
                continue
            if item == _DONE:
                return
            await event_bus(item)

    async def _supervise() -> None:
        """On stop: ask the child to exit, then SIGKILL it if it overruns grace."""
        await cancel_event.wait()
        stop_evt.set()
        deadline = loop.time() + _STOP_GRACE_SECONDS
        while proc.is_alive() and loop.time() < deadline:
            await asyncio.sleep(0.05)
        if proc.is_alive():
            proc.kill()

    pump = asyncio.create_task(_pump())
    supervise = asyncio.create_task(_supervise())
    try:
        await loop.run_in_executor(None, proc.join)
    finally:
        # However we got here (clean finish, stop, or task cancellation), make
        # sure the child is dead and the helper tasks are torn down.
        stop_evt.set()
        if proc.is_alive():
            proc.kill()
            await loop.run_in_executor(None, proc.join)
        for t in (pump, supervise):
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

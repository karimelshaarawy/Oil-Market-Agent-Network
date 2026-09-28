"""Simulation endpoints: the WebSocket run stream and read-only run queries.

GET endpoints intentionally return HTTP 200 with an ``{"error": ...}`` body on
failure — the frontend (frontend/lib/api.ts) relies on that shape.
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket

from econ.api.simulation_process import _STOP_GRACE_SECONDS, _run_simulation
from econ.economic_platform.read_queries import SimulationDBReader
from econ.orchestration.run_storage import list_simulation_ids, read_manifest

router = APIRouter()


# ── WebSocket simulation stream ───────────────────────────────────────────

@router.websocket("/ws/simulate")
async def simulate_ws(websocket: WebSocket) -> None:
    """Accept params as first JSON message, stream structured events back."""
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        params = json.loads(raw)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    queue: asyncio.Queue[dict] = asyncio.Queue()
    cancelled = asyncio.Event()

    async def event_bus(event: dict) -> None:
        await queue.put(event)

    async def _watch_client() -> None:
        """Detect a stop message or disconnect and signal the main loop."""
        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    if json.loads(msg).get("type") == "stop":
                        cancelled.set()
                        return
                except Exception:
                    pass
        except Exception:
            cancelled.set()

    # The same event drives both the WS loop and cooperative cancellation
    # inside the simulation runner, so a stop message / disconnect actually
    # tears down the in-flight work rather than just closing the socket.
    sim_task = asyncio.create_task(_run_simulation(params, event_bus, cancelled))
    watch_task = asyncio.create_task(_watch_client())
    # ``completed`` is True only when the run ended on its own (complete/error).
    # Every other exit (stop message, disconnect, send failure) is a stop, and
    # must be reported + closed deterministically — never left to a flag race.
    completed = False

    try:
        while not cancelled.is_set():
            get_task = asyncio.create_task(queue.get())
            cancel_task = asyncio.create_task(cancelled.wait())
            done, pending = await asyncio.wait(
                {get_task, cancel_task},
                timeout=120.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

            if not done:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break
                continue

            if cancelled.is_set():
                break

            event = get_task.result()
            try:
                await websocket.send_json(event)
            except Exception:
                break

            if event.get("type") in ("simulation_complete", "error"):
                completed = True
                await asyncio.sleep(1.0)
                break
    finally:
        # Setting ``cancelled`` tells the process-isolated runner to stop the
        # child gracefully, then SIGKILL it after the grace window — so teardown
        # is guaranteed regardless of what the child is doing.
        cancelled.set()
        watch_task.cancel()
        # Any non-natural exit is a stop/disconnect: tell the client outright so
        # it never waits on an echo that might not come. (Send may fail if the
        # client already went away — that's fine.)
        if not completed:
            try:
                await websocket.send_json({"type": "stopped"})
            except Exception:
                pass
        # Let the runner finish its graceful-then-kill (it self-terminates once
        # the child dies); cancel it only as a last resort if it badly overruns.
        try:
            await asyncio.wait_for(sim_task, timeout=_STOP_GRACE_SECONDS + 10.0)
        except Exception:
            sim_task.cancel()
            with contextlib.suppress(Exception):
                await sim_task
        with contextlib.suppress(Exception):
            await watch_task
        # Close from the server side regardless of how the loop exited, so the
        # socket is never left lingering open.
        try:
            await websocket.close()
        except Exception:
            pass


# ── Simulation REST endpoints ─────────────────────────────────────────────

def _get_manifest(simulation_id: str) -> dict | None:
    try:
        return read_manifest(simulation_id)
    except Exception:
        return None


def _reader(manifest: dict) -> SimulationDBReader | None:
    reader = SimulationDBReader(str(manifest.get("db_path", "")))
    return reader if reader.exists() else None


@router.get("/simulate/list")
def list_simulations():
    return {"simulations": list_simulation_ids()}


@router.get("/simulate/{simulation_id}/snapshot")
def simulation_snapshot(simulation_id: str):
    manifest = _get_manifest(simulation_id)
    if not manifest:
        return {"error": "Simulation not found"}
    reader = _reader(manifest)
    if reader is None:
        return {"error": "Database not found"}

    return {
        "agents": reader.agents_overview(),
        "price_history": reader.price_history(),
        "transactions": reader.transactions(),
        "balance_history": reader.balance_history(),
    }


@router.get("/simulate/{simulation_id}/agents")
def list_agents(simulation_id: str):
    manifest = _get_manifest(simulation_id)
    if not manifest:
        return {"agents": []}
    reader = _reader(manifest)
    if reader is None:
        return {"agents": []}
    return {"agents": reader.agents_overview()}


@router.get("/simulate/{simulation_id}/agent/{agent_name}/history")
def agent_history(simulation_id: str, agent_name: str):
    manifest = _get_manifest(simulation_id)
    if not manifest:
        return {"error": "Simulation not found"}
    reader = _reader(manifest)
    if reader is None:
        return {"error": "Database not found"}

    agent_row = reader.agent_row(agent_name)
    if not agent_row:
        return {"error": f"Agent {agent_name!r} not found"}

    agent_id = agent_row["agent_id"]
    return {
        "agent_name": agent_name,
        "traces": reader.traces(agent_id),
        "ledger": reader.ledger(agent_id),
        "balance_steps": reader.balance_steps(agent_id),
        "inventory": reader.agent_inventory(agent_id),
    }

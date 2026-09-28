"""Stop-path tests for the /ws/simulate WebSocket.

Drives the real route → ``_run_simulation`` → spawned child chain with an
LLM-free child that emits events until told to stop. Pins the contract that a
stop message (or an abrupt disconnect) tears down the child process and, for
an explicit stop, that the client receives ``{"type": "stopped"}``.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import time

from fastapi.testclient import TestClient

from econ.api.main import app
from econ.api.routers import simulation as sim_routes
from econ.api.simulation_process import _run_simulation


def _endless_child(params: dict, event_q, stop_evt) -> None:
    """Child-process stand-in for a simulation: ticks until stopped."""
    step = 0
    try:
        while not stop_evt.is_set():
            event_q.put({
                "type": "agent_action",
                "step": step,
                "agent": "FakeAgent",
                "agent_id": 1,
                "action": "produce",
                "summary": f"tick {step}",
            })
            step += 1
            time.sleep(0.05)
    finally:
        event_q.put({"__sim_done__": True})
        event_q.close()
        event_q.join_thread()


def _patch_fake_child(monkeypatch) -> None:
    async def fake_run(params, event_bus, cancel_event):
        await _run_simulation(params, event_bus, cancel_event, child_target=_endless_child)

    monkeypatch.setattr(sim_routes, "_run_simulation", fake_run)


def _wait_children_gone(baseline: set, timeout: float = 15.0) -> bool:
    """True once every child process spawned during the test has exited."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        extra = {p for p in mp.active_children() if p not in baseline and p.is_alive()}
        if not extra:
            return True
        time.sleep(0.1)
    return False


def test_stop_message_halts_run_and_reports_stopped(monkeypatch):
    _patch_fake_child(monkeypatch)
    baseline = set(mp.active_children())
    client = TestClient(app)

    with client.websocket_connect("/ws/simulate") as ws:
        ws.send_text(json.dumps({"n_steps": 9999}))

        # Run is demonstrably live: events are flowing.
        for _ in range(3):
            msg = ws.receive_json()
            assert msg["type"] == "agent_action"

        ws.send_text(json.dumps({"type": "stop"}))

        # In-flight events may still arrive; "stopped" must follow, and the
        # run must never claim natural completion.
        saw_stopped = False
        for _ in range(500):
            msg = ws.receive_json()
            assert msg["type"] != "simulation_complete"
            if msg["type"] == "stopped":
                saw_stopped = True
                break
        assert saw_stopped, "never received {'type': 'stopped'} after stop message"

    assert _wait_children_gone(baseline), "child process still alive after stop"


def test_client_disconnect_halts_run(monkeypatch):
    _patch_fake_child(monkeypatch)
    baseline = set(mp.active_children())
    client = TestClient(app)

    with client.websocket_connect("/ws/simulate") as ws:
        ws.send_text(json.dumps({"n_steps": 9999}))
        msg = ws.receive_json()
        assert msg["type"] == "agent_action"
        # Abrupt close, no stop frame — the disconnect alone must tear down.

    assert _wait_children_gone(baseline), "child process still alive after disconnect"

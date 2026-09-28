"""Tests for the read-only simulation REST endpoints.

Pins the frontend contract: failures return HTTP 200 with an
``{"error": ...}`` body, never a 4xx.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from econ.api.main import app
from econ.economic_platform.tests.helpers import make_platform, register_agent


async def build_run(tmp_path, sim_id: str = "testsim001") -> str:
    """Create runs/<sim_id>/ with a manifest and a small but real run DB."""
    run_dir = tmp_path / "runs" / sim_id
    run_dir.mkdir(parents=True)
    db_path = run_dir / "simulation.db"

    platform, _ = make_platform(db_path=str(db_path))
    await register_agent(platform, 1, name="seller", produces=("crude_oil",))
    await register_agent(platform, 2, name="buyer", agent_type="consumer")
    produced = await platform.produce(1, ("crude_oil", 10, 5.0))
    await platform.list_good(1, (produced["good_id"], 10.0, 10))
    await platform.place_bid(2, ("crude_oil", 10.0, 3))
    await platform.clear_market()  # clears at 10
    platform.db.commit()
    platform.db.close()

    (run_dir / "manifest.json").write_text(json.dumps({
        "simulation_id": sim_id,
        "db_path": str(db_path),
        "chroma_dir": str(run_dir / "chroma"),
    }))
    return sim_id


async def test_simulation_get_endpoints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # run_storage resolves runs/ against the CWD
    sim_id = await build_run(tmp_path)
    client = TestClient(app)

    assert client.get("/simulate/list").json() == {"simulations": [sim_id]}

    snap = client.get(f"/simulate/{sim_id}/snapshot")
    assert snap.status_code == 200
    data = snap.json()
    assert sorted(data.keys()) == [
        "agents", "balance_history", "price_history", "transactions",
    ]
    assert [a["name"] for a in data["agents"]] == ["seller", "buyer"]
    assert data["transactions"][0]["buyer"] == "buyer"
    assert len(data["price_history"]) == 1

    agents = client.get(f"/simulate/{sim_id}/agents").json()
    assert [a["name"] for a in agents["agents"]] == ["seller", "buyer"]

    history = client.get(f"/simulate/{sim_id}/agent/seller/history").json()
    assert sorted(history.keys()) == [
        "agent_name", "balance_steps", "inventory", "ledger", "traces",
    ]
    assert history["agent_name"] == "seller"
    assert history["traces"]
    assert history["ledger"]


async def test_error_shapes_are_http_200_with_error_body(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sim_id = await build_run(tmp_path)
    client = TestClient(app)

    missing = client.get("/simulate/nope/snapshot")
    assert missing.status_code == 200
    assert missing.json() == {"error": "Simulation not found"}

    assert client.get("/simulate/nope/agents").json() == {"agents": []}

    unknown_agent = client.get(f"/simulate/{sim_id}/agent/ghost/history").json()
    assert unknown_agent == {"error": "Agent 'ghost' not found"}

    # Manifest exists but its DB is gone → "Database not found", still 200.
    broken_dir = tmp_path / "runs" / "brokenrun"
    broken_dir.mkdir(parents=True)
    (broken_dir / "manifest.json").write_text(json.dumps({
        "simulation_id": "brokenrun",
        "db_path": str(broken_dir / "gone.db"),
    }))
    assert client.get("/simulate/brokenrun/snapshot").json() == {"error": "Database not found"}

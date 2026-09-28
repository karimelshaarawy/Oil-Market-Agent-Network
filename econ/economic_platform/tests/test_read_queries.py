"""Tests for the shared read-only run-database reader and run artifacts."""
from __future__ import annotations

import json

from econ.economic_platform.read_queries import SimulationDBReader
from econ.economic_platform.tests.helpers import make_platform, register_agent
from econ.report.run_artifacts import scenario_summary, scenario_used_for_events


async def seeded_run_db(tmp_path) -> str:
    """Build a real run DB: two agents, one production, one listing, one trade."""
    db_path = str(tmp_path / "run.db")
    platform, _ = make_platform(db_path=db_path)
    await register_agent(platform, 1, name="seller", produces=("crude_oil",))
    await register_agent(platform, 2, name="buyer", agent_type="consumer")
    produced = await platform.produce(1, ("crude_oil", 10, 5.0))
    await platform.list_good(1, (produced["good_id"], 10.0, 10))
    await platform.place_bid(2, ("crude_oil", 10.0, 3))
    await platform.clear_market()  # clears at 10
    platform.record_agent_reflection(1, 0, "sold some crude")
    platform.db.commit()
    platform.db.close()
    return db_path


async def test_reader_overview_and_agent_queries(tmp_path):
    reader = SimulationDBReader(await seeded_run_db(tmp_path))
    assert reader.exists()
    assert not SimulationDBReader(str(tmp_path / "missing.db")).exists()

    assert [a["name"] for a in reader.agents_overview()] == ["seller", "buyer"]
    assert reader.max_step() == 0
    assert len(reader.price_history()) == 1

    tx = reader.transactions()
    assert (tx[0]["buyer"], tx[0]["seller"], tx[0]["good_name"]) == ("buyer", "seller", "crude_oil")
    assert reader.balance_history()

    assert reader.agent_row("seller")["agent_id"] == 1
    assert reader.agent_row("nobody") is None
    assert reader.traces(1)
    assert reader.ledger(1)
    assert reader.balance_steps(1)
    assert reader.agent_inventory(2) == [
        {"name": "crude_oil", "quantity": 3, "avg_unit_cost": 10.0}
    ]
    assert reader.recent_reflection_rows(1, 8)[0]["reflection"] == "sold some crude"
    assert reader.recent_ledger_rows(1, 30)


async def test_reader_report_summary_rows(tmp_path):
    reader = SimulationDBReader(await seeded_run_db(tmp_path))

    balances = reader.balances_after_debt_rows()
    assert {r["name"] for r in balances} == {"seller", "buyer"}
    assert balances[0]["debt"] == 0

    summary = reader.transaction_summary_rows()
    assert summary[0]["tx_count"] == 1
    assert summary[0]["avg_price"] == 10.0

    assert reader.price_by_step_rows()[0]["step"] == 0
    assert reader.loan_summary_rows() == []
    assert reader.reflection_overview_rows()[0]["name"] == "seller"


async def test_run_artifacts_scenario_resolution(tmp_path):
    db_path = await seeded_run_db(tmp_path)

    # No manifest → legacy behavior: scenario considered used, but no summary file.
    assert scenario_used_for_events(db_path) is True
    assert scenario_summary(db_path) == "No persisted scenario summary was found for this run."

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"params": {"use_generated_events": False}}))
    assert scenario_used_for_events(db_path) is False
    assert scenario_summary(db_path) == (
        "Scenario seed context was not used to generate events for this run."
    )

    manifest.write_text(json.dumps({"params": {"use_generated_events": True}}))
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "scenario_summary.md").write_text("OPEC cut " * 600)
    text = scenario_summary(db_path, max_chars=3000)
    assert len(text) == 3000
    assert scenario_summary(db_path, max_chars=2500)[:8] == "OPEC cut"

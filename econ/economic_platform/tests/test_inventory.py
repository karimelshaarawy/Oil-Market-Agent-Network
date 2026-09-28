"""Characterization tests for produce / refine / FIFO inventory consumption."""
from __future__ import annotations

from econ.economic_platform.tests.helpers import (
    balance_of,
    ledger_rows,
    make_platform,
    register_agent,
)


async def test_produce_rejects_non_positive_unit_cost():
    platform, _ = make_platform()
    await register_agent(platform, 1)

    result = await platform.produce(1, ("crude_oil", 10, 0.0))
    assert result["success"] is False
    assert "unit_cost must be greater than 0" in result["error"]


async def test_produce_enforces_production_restriction():
    platform, _ = make_platform()
    await register_agent(platform, 1, produces=("crude_oil",))

    result = await platform.produce(1, ("fuel", 5, 2.0))
    assert result["success"] is False
    assert "not authorised to produce 'fuel'" in result["error"]


async def test_produce_debits_cost_and_creates_good_and_ledger():
    platform, events = make_platform()
    await register_agent(platform, 1, balance=1000.0, produces=("crude_oil",))

    result = await platform.produce(1, ("crude_oil", 10, 5.0))
    assert result == {
        "success": True,
        "good_id": result["good_id"],
        "good_name": "crude_oil",
        "quantity": 10,
        "cost_incurred": 50.0,
    }
    assert balance_of(platform, 1) == 950.0

    good = platform.db.execute(
        "SELECT * FROM good WHERE good_id = ?", (result["good_id"],)
    ).fetchone()
    assert good["producer_id"] == 1
    assert good["quantity"] == 10
    assert good["unit_cost"] == 5.0

    rows = ledger_rows(platform, 1)
    assert rows[-1]["category"] == "production"
    assert rows[-1]["amount"] == -50.0

    assert events[-1]["action"] == "produce"
    assert events[-1]["balance"] == 950.0


async def test_produce_insufficient_balance():
    platform, _ = make_platform()
    await register_agent(platform, 1, balance=10.0)

    result = await platform.produce(1, ("crude_oil", 10, 5.0))
    assert result["success"] is False
    assert "Insufficient balance" in result["error"]
    assert balance_of(platform, 1) == 10.0


async def test_refine_fifo_cost_basis_and_break_even():
    platform, _ = make_platform()
    # Unrestricted producer (empty produces list = no restriction).
    await register_agent(platform, 1, balance=1000.0)

    await platform.produce(1, ("crude_oil", 5, 2.0))
    await platform.produce(1, ("crude_oil", 5, 3.0))
    # Balance: 1000 - 10 - 15 = 975.

    result = await platform.refine(1, ("crude_oil", 8, "fuel", 4, 1.0))
    assert result["success"] is True
    # FIFO: 5 @ 2.0 + 3 @ 3.0 = 19.0 input cost basis.
    assert result["input_cost_basis"] == 19.0
    assert result["conversion_cost"] == 4.0
    assert result["total_output_cost"] == 23.0
    assert result["break_even_unit_cost"] == 5.75
    assert result["output_qty"] == 4

    # Conversion cost debited: 975 - 4 = 971.
    assert balance_of(platform, 1) == 971.0

    remaining = platform.db.execute(
        "SELECT quantity, unit_cost FROM good "
        "WHERE producer_id = 1 AND name = 'crude_oil' AND quantity > 0"
    ).fetchall()
    assert [(r["quantity"], r["unit_cost"]) for r in remaining] == [(2, 3.0)]

    fuel = platform.db.execute(
        "SELECT quantity, unit_cost FROM good WHERE good_id = ?",
        (result["output_good_id"],),
    ).fetchone()
    assert fuel["quantity"] == 4
    assert fuel["unit_cost"] == 5.75

    rows = ledger_rows(platform, 1)
    assert rows[-1]["category"] == "refinement"
    assert rows[-1]["amount"] == -4.0


async def test_refine_enforces_output_restriction():
    platform, _ = make_platform()
    await register_agent(platform, 1, produces=("crude_oil",))
    await platform.produce(1, ("crude_oil", 10, 2.0))

    result = await platform.refine(1, ("crude_oil", 5, "fuel", 3, 1.0))
    assert result["success"] is False
    assert "not authorised to produce 'fuel' via refine" in result["error"]


async def test_refine_rejects_insufficient_input_inventory():
    platform, _ = make_platform()
    await register_agent(platform, 1)
    await platform.produce(1, ("crude_oil", 3, 2.0))

    result = await platform.refine(1, ("crude_oil", 5, "fuel", 2, 1.0))
    assert result["success"] is False
    assert "Insufficient 'crude_oil' in inventory: 3 units" in result["error"]


async def test_consume_inventory_partial_fifo():
    platform, _ = make_platform()
    await register_agent(platform, 1)
    await platform.produce(1, ("crude_oil", 3, 2.0))

    consumed, cost_basis = platform.inventory.consume_fifo(1, "crude_oil", 5)
    assert consumed == 3
    assert cost_basis == 6.0

    left = platform.db.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM good "
        "WHERE producer_id = 1 AND name = 'crude_oil'"
    ).fetchone()[0]
    assert left == 0

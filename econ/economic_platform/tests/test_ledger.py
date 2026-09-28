"""Characterization tests for balance/ledger behavior."""
from __future__ import annotations

from econ.economic_platform.tests.helpers import (
    balance_of,
    ledger_rows,
    make_platform,
    register_agent,
)


async def test_credit_and_debit_move_balance():
    platform, _ = make_platform()
    await register_agent(platform, 1, balance=100.0)

    platform.ledger.credit(1, 50.0)
    assert balance_of(platform, 1) == 150.0

    assert platform.ledger.debit(1, 30.0) is True
    assert balance_of(platform, 1) == 120.0


async def test_debit_insufficient_returns_false_without_mutation():
    platform, _ = make_platform()
    await register_agent(platform, 1, balance=10.0)

    assert platform.ledger.debit(1, 10.01) is False
    assert balance_of(platform, 1) == 10.0


async def test_agent_balance_unknown_agent_is_zero():
    platform, _ = make_platform()
    assert platform.ledger.balance(999) == 0.0


async def test_record_ledger_rounds_to_4dp():
    platform, _ = make_platform()
    await register_agent(platform, 1)

    platform.ledger.record(1, "test", 10.123456, "rounding check")
    rows = ledger_rows(platform, 1)
    assert len(rows) == 1
    assert rows[0]["amount"] == 10.1235
    assert rows[0]["category"] == "test"
    assert rows[0]["step"] == 0


async def test_step_vs_all_time_financials_split_by_sign():
    platform, _ = make_platform()
    await register_agent(platform, 1)

    platform.ledger.record(1, "sale", 100.0)
    platform.ledger.record(1, "purchase", -30.0)
    platform.clock.tick()
    platform.ledger.record(1, "sale", 50.0)

    result = await platform.check_balance(1)
    assert result["success"] is True
    assert result["this_step_financials"] == {
        "step": 1,
        "income": 50.0,
        "expenses": 0.0,
        "net": 50.0,
    }
    assert result["all_time_financials"] == {
        "total_income": 150.0,
        "total_expenses": 30.0,
        "net_profit": 120.0,
    }


async def test_record_agent_reflection_persists_and_skips_blank():
    platform, _ = make_platform()
    await register_agent(platform, 1)

    platform.record_agent_reflection(1, 3, "  prices are rising  ")
    platform.record_agent_reflection(1, 3, "   ")

    rows = platform.db.execute(
        "SELECT agent_id, step, reflection FROM agent_reflection"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["reflection"] == "prices are rising"
    assert rows[0]["step"] == 3

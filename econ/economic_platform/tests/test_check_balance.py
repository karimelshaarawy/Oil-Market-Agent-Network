"""Characterization test pinning the exact check_balance response shape."""
from __future__ import annotations

from econ.economic_platform.tests.helpers import (
    DictProfileStore,
    make_platform,
    register_agent,
)


async def test_check_balance_unknown_agent():
    platform, _ = make_platform()
    result = await platform.check_balance(42)
    assert result == {"success": False, "error": "agent_id 42 not found"}


async def test_check_balance_full_response_shape():
    needs = [{"good_name": "fuel", "quantity_per_step": 1}]
    platform, _ = make_platform(
        profile_store=DictProfileStore({1: {"consumption_needs": needs}})
    )
    await register_agent(platform, 1, balance=1000.0, produces=("crude_oil",))
    await register_agent(platform, 2, agent_type="bank", balance=1000.0)

    produced = await platform.produce(1, ("crude_oil", 10, 5.0))
    await platform.list_good(1, (produced["good_id"], 12.0, 6))
    req = await platform.request_loan(1, (2, 100.0, None))
    await platform.approve_loan(2, (req["request_id"], None, None))

    platform.clock.time_step = 2
    result = await platform.check_balance(1)

    assert sorted(result.keys()) == sorted([
        "success", "balance", "agent_type", "sector", "inventory",
        "consumption_needs", "own_active_listings", "active_loans",
        "this_step_financials", "all_time_financials",
    ])
    assert result["success"] is True
    assert result["balance"] == 1050.0  # 1000 - 50 production + 100 loan
    assert result["agent_type"] == "firm"
    assert result["sector"] == "energy"
    assert result["consumption_needs"] == needs

    assert result["inventory"] == [{
        "name": "crude_oil",
        "total_quantity": 4,
        "avg_unit_cost": 5.0,
        "latest_unit_cost": 5.0,
    }]

    listing = result["own_active_listings"][0]
    assert sorted(listing.keys()) == sorted([
        "listing_id", "good_name", "ask_price", "quantity_available",
        "created_at", "steps_listed",
    ])
    assert listing["created_at"] == 0
    assert listing["steps_listed"] == 2  # listed at step 0, now step 2

    loan = result["active_loans"][0]
    assert sorted(loan.keys()) == sorted([
        "loan_id", "lender_id", "amount", "interest_rate", "due_at",
        "steps_overdue", "current_repayment_due",
    ])

    assert result["this_step_financials"] == {
        "step": 2, "income": 0.0, "expenses": 0.0, "net": 0.0,
    }
    assert result["all_time_financials"] == {
        "total_income": 100.0,
        "total_expenses": 50.0,
        "net_profit": 50.0,
    }

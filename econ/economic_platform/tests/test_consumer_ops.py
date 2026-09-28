"""Characterization tests for consumer operating needs and income grants."""
from __future__ import annotations

import json

from econ.economic_platform.tests.helpers import (
    DictProfileStore,
    balance_of,
    ledger_rows,
    make_platform,
    register_agent,
)

FUEL_NEED = {
    "good_name": "fuel",
    "quantity_per_step": 4,
    "reference_price": 10.0,
    "price_pass_through": 0.5,
    "revenue_per_unit": 20.0,
    "shortage_penalty_per_unit": 15.0,
}


def consume_traces(platform, agent_id):
    rows = platform.db.execute(
        "SELECT info FROM trace WHERE agent_id = ? AND action = 'consume_need'",
        (agent_id,),
    ).fetchall()
    return [json.loads(r["info"]) for r in rows]


async def test_consumer_ops_pass_through_revenue():
    profiles = {2: {"consumption_needs": [FUEL_NEED]}}
    platform, _ = make_platform(profile_store=DictProfileStore(profiles))
    await register_agent(platform, 1, balance=1000.0)
    produced = await platform.produce(1, ("fuel", 10, 5.0))
    await platform.list_good(1, (produced["good_id"], 12.0, 10))
    await register_agent(platform, 2, agent_type="consumer", balance=1000.0)
    await platform.place_bid(2, ("fuel", 12.0, 4))
    await platform.clear_market()  # ask 12 vs bid 12 → clears at 12
    assert balance_of(platform, 2) == 952.0  # 1000 - 4 * 12

    platform.clock.tick()
    await platform.apply_consumer_needs()

    # avg consumed cost 12.0 vs reference 10.0 → pressure 0.2;
    # revenue/unit = 20 * (1 + 0.5 * 0.2) = 22.0; revenue = 4 * 22 = 88.
    assert balance_of(platform, 2) == 1040.0
    rows = ledger_rows(platform, 2)
    assert rows[-1]["category"] == "operating_revenue"
    assert rows[-1]["amount"] == 88.0

    trace = consume_traces(platform, 2)[-1]
    # Demand is price-elastic now: at clearing price 12 vs reference 10 the
    # default-elasticity (0.4) target rounds back to the base 4, so the
    # consumed/revenue figures are unchanged, plus the new diagnostic fields.
    assert trace == {
        "good_name": "fuel",
        "base_required": 4,
        "market_price": 12.0,
        "required": 4,
        "consumed": 4,
        "shortage": 0,
        "avg_consumed_unit_cost": 12.0,
        "revenue_per_unit": 22.0,
        "operating_revenue": 88.0,
        "shortage_penalty": 0.0,
    }


async def test_consumer_ops_shortage_penalty_can_go_negative():
    need = dict(FUEL_NEED, quantity_per_step=2)
    platform, _ = make_platform(
        profile_store=DictProfileStore({2: {"consumption_needs": [need]}})
    )
    await register_agent(platform, 2, agent_type="consumer", balance=10.0)

    platform.clock.tick()
    await platform.apply_consumer_needs()

    assert balance_of(platform, 2) == -20.0  # 10 - 2 * 15
    rows = ledger_rows(platform, 2)
    assert rows[-1]["category"] == "shortage_penalty"
    assert rows[-1]["amount"] == -30.0

    trace = consume_traces(platform, 2)[-1]
    assert trace["consumed"] == 0
    assert trace["shortage"] == 2
    # Nothing consumed and no price history → falls back to reference price.
    assert trace["avg_consumed_unit_cost"] == 10.0
    assert trace["operating_revenue"] == 0.0
    assert trace["shortage_penalty"] == 30.0


async def test_consumer_ops_fallback_to_recent_average_price():
    need = dict(FUEL_NEED, quantity_per_step=1, shortage_penalty_per_unit=0.0)
    platform, _ = make_platform(
        profile_store=DictProfileStore({2: {"consumption_needs": [need]}})
    )
    await register_agent(platform, 2, agent_type="consumer", balance=100.0)
    platform.ctx.execute(
        "INSERT INTO price_history (good_name, price, quantity, timestamp) "
        "VALUES ('fuel', 14.0, 1, 0), ('fuel', 16.0, 1, 0)",
        commit=True,
    )

    platform.clock.tick()
    await platform.apply_consumer_needs()

    trace = consume_traces(platform, 2)[-1]
    assert trace["avg_consumed_unit_cost"] == 15.0


async def test_consumer_ops_skipped_at_step_zero_and_when_disabled():
    profiles = DictProfileStore({2: {"consumption_needs": [FUEL_NEED]}})
    platform, _ = make_platform(profile_store=profiles)
    await register_agent(platform, 2, agent_type="consumer", balance=10.0)

    await platform.apply_consumer_needs()  # step 0 → no consumer ops
    assert balance_of(platform, 2) == 10.0

    disabled, _ = make_platform(
        profile_store=profiles, consumer_operations_enabled=False
    )
    await register_agent(disabled, 2, agent_type="consumer", balance=10.0)
    disabled.clock.tick()
    await disabled.apply_consumer_needs()
    assert balance_of(disabled, 2) == 10.0


async def test_income_grant_credited_each_update():
    platform, _ = make_platform(consumer_income_per_step=25.0)
    await register_agent(platform, 1, agent_type="consumer", balance=0.0)
    await register_agent(platform, 2, agent_type="firm", balance=0.0)

    await platform.update_market_state()

    assert balance_of(platform, 1) == 25.0
    assert balance_of(platform, 2) == 0.0  # only consumers get income
    rows = ledger_rows(platform, 1)
    assert rows[-1]["category"] == "income_grant"
    assert rows[-1]["amount"] == 25.0

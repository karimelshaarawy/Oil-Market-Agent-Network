"""Tests for price-elastic (endogenous) demand.

Covers the pure demand-curve helper and its effect on consumer-needs accounting:
a higher clearing price lowers the operating target, which in turn lowers both
consumption-driven revenue and the shortage baseline.
"""
from __future__ import annotations

import json

from econ.core.demand import effective_quantity, target_from_need
from econ.economic_platform.tests.helpers import (
    DictProfileStore,
    make_platform,
    register_agent,
)


# ── Pure curve ───────────────────────────────────────────────────────────────

def test_curve_returns_base_at_reference_price():
    assert effective_quantity(40, 45.0, 45.0, elasticity=0.5) == 40


def test_curve_falls_as_price_rises():
    base, ref = 40, 45.0
    low = effective_quantity(base, ref, 30.0, elasticity=0.5)
    at = effective_quantity(base, ref, 45.0, elasticity=0.5)
    high = effective_quantity(base, ref, 90.0, elasticity=0.5)
    assert low > at > high


def test_inelastic_barely_moves_elastic_moves_a_lot():
    base, ref, price = 40, 45.0, 90.0  # price doubled
    inelastic = effective_quantity(base, ref, price, elasticity=0.1)
    elastic = effective_quantity(base, ref, price, elasticity=0.9)
    assert inelastic > elastic
    assert inelastic >= 36          # ~within 10% of base
    assert elastic <= 24            # cut by roughly half


def test_curve_clamps_to_floor_and_cap():
    base, ref = 40, 45.0
    # Extreme high price → clamped to floor (default 0.5 * base = 20).
    assert effective_quantity(base, ref, 100000.0, elasticity=0.9) == 20
    # Extreme low price → clamped to cap (default 2.0 * base = 80).
    assert effective_quantity(base, ref, 0.01, elasticity=0.9) == 80


def test_curve_falls_back_to_base_without_price():
    assert effective_quantity(40, 45.0, None, elasticity=0.5) == 40
    assert effective_quantity(40, 45.0, 0.0, elasticity=0.5) == 40


def test_small_need_does_not_round_away_to_zero():
    # A base-1 need at an extreme price clamps to the default 0.5 floor; half-up
    # rounding keeps it at 1 unit (banker's rounding would zero it out).
    assert effective_quantity(1, 45.0, 100000.0, elasticity=0.9) == 1
    assert effective_quantity(1, 45.0, 45.0, elasticity=0.9) == 1


def test_target_from_need_reads_fields():
    need = {
        "good_name": "fuel",
        "quantity_per_step": 40,
        "reference_price": 45.0,
        "elasticity": 0.9,
        "min_quantity_fraction": 0.25,
    }
    # Honours the per-need floor (0.25 * 40 = 10) at an extreme price.
    assert target_from_need(need, 100000.0) == 10


# ── Accounting integration ───────────────────────────────────────────────────

ELASTIC_NEED = {
    "good_name": "fuel",
    "quantity_per_step": 10,
    "reference_price": 10.0,
    "revenue_per_unit": 20.0,
    "shortage_penalty_per_unit": 15.0,
    "elasticity": 1.0,
    "price_pass_through": 0.0,
}


def _consume_trace(platform, agent_id):
    row = platform.db.execute(
        "SELECT info FROM trace WHERE agent_id = ? AND action = 'consume_need' "
        "ORDER BY timestamp DESC LIMIT 1",
        (agent_id,),
    ).fetchone()
    return json.loads(row["info"])


async def test_high_clearing_price_shrinks_required_and_shortage():
    """With unit elasticity, doubling the price halves the operating target —
    so a consumer holding nothing is short the *reduced* amount, not the base."""
    platform, _ = make_platform(
        profile_store=DictProfileStore({2: {"consumption_needs": [ELASTIC_NEED]}})
    )
    await register_agent(platform, 2, agent_type="consumer", balance=1000.0)
    # Record a clearing price of 20 (2x the reference of 10).
    platform.ctx.execute(
        "INSERT INTO price_history (good_name, price, quantity, timestamp) "
        "VALUES ('fuel', 20.0, 5, 0)",
        commit=True,
    )

    platform.clock.tick()
    await platform.apply_consumer_needs()

    trace = _consume_trace(platform, 2)
    assert trace["base_required"] == 10
    assert trace["market_price"] == 20.0
    assert trace["required"] == 5          # 10 * (10/20)^1 = 5
    assert trace["consumed"] == 0
    assert trace["shortage"] == 5          # short the reduced target, not 10
    # Penalty is assessed against the reduced target: 5 * 15 = 75 (not 150).
    assert trace["shortage_penalty"] == 75.0


async def test_low_price_does_not_manufacture_shortage_penalty():
    """Cheap input: the elastic target rises above base, but a consumer holding
    the base amount is NOT penalised for failing to expand consumption."""
    platform, _ = make_platform(
        profile_store=DictProfileStore({2: {"consumption_needs": [ELASTIC_NEED]}})
    )
    await register_agent(platform, 2, agent_type="consumer", balance=1000.0)
    platform.ctx.execute(
        "INSERT INTO good (producer_id, name, quantity, unit_cost, created_at) "
        "VALUES (2, 'fuel', 10, 1.0, 0)",  # holds exactly the base need
        commit=True,
    )
    platform.ctx.execute(
        "INSERT INTO price_history (good_name, price, quantity, timestamp) "
        "VALUES ('fuel', 5.0, 5, 0)",  # half the reference price
        commit=True,
    )

    platform.clock.tick()
    await platform.apply_consumer_needs()

    trace = _consume_trace(platform, 2)
    assert trace["base_required"] == 10
    assert trace["required"] == 20         # target doubled at half price (cap 2x)
    assert trace["consumed"] == 10
    assert trace["shortage"] == 0          # inelastic core (base 10) fully met
    assert trace["shortage_penalty"] == 0.0


async def test_low_price_still_penalises_below_the_core():
    """Below the base need at a low price is still a real shortage — penalty is
    assessed against the base core (10), not the inflated target (20)."""
    platform, _ = make_platform(
        profile_store=DictProfileStore({2: {"consumption_needs": [ELASTIC_NEED]}})
    )
    await register_agent(platform, 2, agent_type="consumer", balance=1000.0)
    platform.ctx.execute(
        "INSERT INTO good (producer_id, name, quantity, unit_cost, created_at) "
        "VALUES (2, 'fuel', 6, 1.0, 0)",   # holds less than the base need
        commit=True,
    )
    platform.ctx.execute(
        "INSERT INTO price_history (good_name, price, quantity, timestamp) "
        "VALUES ('fuel', 5.0, 5, 0)",
        commit=True,
    )

    platform.clock.tick()
    await platform.apply_consumer_needs()

    trace = _consume_trace(platform, 2)
    assert trace["required"] == 20
    assert trace["consumed"] == 6
    assert trace["shortage"] == 4          # 10 (core) − 6 consumed
    assert trace["shortage_penalty"] == 60.0   # 4 × 15

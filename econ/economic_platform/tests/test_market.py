"""Characterization tests for the call-auction market: listings, sealed bids,
uniform-price clearing, transport friction, pro-rata at the margin, and
auto-cancel of stale asks."""
from __future__ import annotations

from econ.economic_platform.tests.helpers import (
    FlatTransportCosts,
    balance_of,
    ledger_rows,
    make_platform,
    register_agent,
)


async def seller_with_listing(platform, agent_id=1, *, qty=10, unit_cost=5.0,
                              ask_price=10.0, list_qty=None):
    await register_agent(platform, agent_id, balance=1000.0)
    produced = await platform.produce(agent_id, ("crude_oil", qty, unit_cost))
    listed = await platform.list_good(
        agent_id, (produced["good_id"], ask_price, list_qty or qty)
    )
    assert listed["success"]
    return produced, listed


# ── Listings (resting asks) ────────────────────────────────────────────────

async def test_list_good_rejects_unknown_or_foreign_good():
    platform, _ = make_platform()
    await register_agent(platform, 1)

    result = await platform.list_good(1, (999, 10.0, 5))
    assert result["success"] is False
    assert "not found or not owned" in result["error"]


async def test_list_good_rejects_over_quantity():
    platform, _ = make_platform()
    await register_agent(platform, 1)
    produced = await platform.produce(1, ("crude_oil", 3, 2.0))

    result = await platform.list_good(1, (produced["good_id"], 10.0, 5))
    assert result["success"] is False
    assert "Only 3 units available" in result["error"]


async def test_list_good_decrements_inventory_and_creates_listing():
    platform, _ = make_platform()
    _, listed = await seller_with_listing(platform, qty=10, list_qty=6)

    good_qty = platform.db.execute(
        "SELECT quantity FROM good WHERE producer_id = 1"
    ).fetchone()["quantity"]
    assert good_qty == 4

    listing = platform.db.execute(
        "SELECT * FROM market_listing WHERE listing_id = ?",
        (listed["listing_id"],),
    ).fetchone()
    assert listing["seller_id"] == 1
    assert listing["good_name"] == "crude_oil"
    assert listing["ask_price"] == 10.0
    assert listing["quantity_available"] == 6
    assert listed["quantity_listed"] == 6


async def test_list_good_warns_below_avg_cost():
    platform, _ = make_platform()
    _, listed = await seller_with_listing(platform, qty=10, unit_cost=5.0,
                                          ask_price=4.0)
    assert "warning" in listed and "below your average unit cost" in listed["warning"]


async def test_observe_market_excludes_own_listings_sorted_by_price():
    platform, _ = make_platform()
    await seller_with_listing(platform, agent_id=1, ask_price=10.0)
    await register_agent(platform, 2, balance=1000.0)
    p1 = await platform.produce(2, ("fuel", 5, 3.0))
    await platform.list_good(2, (p1["good_id"], 20.0, 3))
    p2 = await platform.produce(2, ("fuel", 5, 3.0))
    await platform.list_good(2, (p2["good_id"], 15.0, 2))

    result = await platform.observe_market(2)
    assert result["success"] is True
    # Agent 2 sees only agent 1's listing, not its own two.
    assert [(l["seller_id"], l["ask_price"]) for l in result["listings"]] == [(1, 10.0)]

    result = await platform.observe_market(3)
    assert [l["ask_price"] for l in result["listings"]] == [10.0, 15.0, 20.0]


async def test_update_listing_price_validation_and_success():
    platform, _ = make_platform()
    _, listed = await seller_with_listing(platform, agent_id=1, ask_price=10.0)
    await register_agent(platform, 2)

    bad = await platform.update_listing_price(1, (listed["listing_id"], 0))
    assert bad["error"] == "new_price must be positive."

    foreign = await platform.update_listing_price(2, (listed["listing_id"], 5.0))
    assert "does not belong to you" in foreign["error"]

    ok = await platform.update_listing_price(1, (listed["listing_id"], 8.5))
    assert ok["success"] is True
    assert ok["old_price"] == 10.0
    assert ok["new_price"] == 8.5


# ── Sealed bids + escrow ────────────────────────────────────────────────────

async def test_place_bid_escrows_funds():
    platform, events = make_platform()
    await register_agent(platform, 2, balance=1000.0)

    bid = await platform.place_bid(2, ("crude_oil", 12.0, 4))
    assert bid["success"] is True
    assert bid["quantity_submitted"] == 4
    assert bid["escrow"] == 48.0
    assert balance_of(platform, 2) == 952.0  # 48 locked in escrow
    assert events[-1]["action"] == "place_bid"


async def test_place_bid_shrinks_to_affordable_quantity():
    platform, _ = make_platform()
    await register_agent(platform, 2, balance=25.0)

    bid = await platform.place_bid(2, ("crude_oil", 10.0, 5))
    assert bid["success"] is True
    assert bid["quantity_submitted"] == 2          # 25 // 10
    assert bid["escrow"] == 20.0
    assert "warning" in bid
    assert balance_of(platform, 2) == 5.0


async def test_place_bid_rejected_when_unaffordable():
    platform, _ = make_platform()
    await register_agent(platform, 2, balance=5.0)

    bid = await platform.place_bid(2, ("crude_oil", 10.0, 1))
    assert bid["success"] is False
    assert "Insufficient balance to escrow" in bid["error"]
    assert balance_of(platform, 2) == 5.0


# ── Clearing ────────────────────────────────────────────────────────────────

async def test_clearing_uniform_midpoint_price():
    platform, events = make_platform()
    _, listed = await seller_with_listing(platform, agent_id=1, qty=10,
                                          unit_cost=5.0, ask_price=10.0)
    seller_balance_before = balance_of(platform, 1)  # 950 after production
    await register_agent(platform, 2, balance=1000.0)
    await platform.place_bid(2, ("crude_oil", 14.0, 4))

    summaries = await platform.clear_market()
    # midpoint of marginal ask 10 and marginal bid 14 = 12.
    assert summaries == [{
        "type": "market_clearing", "step": 0, "good": "crude_oil",
        "clearing_price": 12.0, "quantity": 4,
    }]

    # Buyer pays 4 * 12 = 48 (escrowed 56, refunded 8); seller receives 48.
    assert balance_of(platform, 2) == 952.0
    assert balance_of(platform, 1) == seller_balance_before + 48.0

    listing = platform.db.execute(
        "SELECT quantity_available FROM market_listing WHERE listing_id = ?",
        (listed["listing_id"],),
    ).fetchone()
    assert listing["quantity_available"] == 6

    tx = platform.db.execute("SELECT * FROM market_transaction").fetchone()
    assert (tx["buyer_id"], tx["seller_id"], tx["price"], tx["quantity"]) == (2, 1, 12.0, 4)

    ph = platform.db.execute("SELECT good_name, price, quantity FROM price_history").fetchone()
    assert (ph["good_name"], ph["price"], ph["quantity"]) == ("crude_oil", 12.0, 4)

    buyer_good = platform.db.execute(
        "SELECT quantity, unit_cost FROM good WHERE producer_id = 2"
    ).fetchone()
    assert (buyer_good["quantity"], buyer_good["unit_cost"]) == (4, 12.0)

    assert ledger_rows(platform, 2)[-1]["category"] == "purchase"
    assert ledger_rows(platform, 2)[-1]["amount"] == -48.0
    assert ledger_rows(platform, 1)[-1]["category"] == "sale"
    assert ledger_rows(platform, 1)[-1]["amount"] == 48.0
    assert events[-1]["type"] == "market_clearing"


async def test_clearing_applies_transport_surcharge():
    platform, _ = make_platform(transport_costs=FlatTransportCosts(0.1))
    await seller_with_listing(platform, agent_id=1, qty=10, unit_cost=5.0,
                              ask_price=10.0)
    seller_before = balance_of(platform, 1)  # 950
    await register_agent(platform, 2, balance=1000.0)
    await platform.place_bid(2, ("crude_oil", 14.0, 2))

    await platform.clear_market()
    # clearing base = 12; buyer pays 12*1.1=13.2/unit; seller gets base only.
    assert balance_of(platform, 1) == seller_before + 24.0           # 2 * 12 base
    assert balance_of(platform, 2) == 1000.0 - 24.0 - 2.4            # base + transport

    tx = platform.db.execute("SELECT price, total_paid FROM market_transaction").fetchone()
    assert (tx["price"], tx["total_paid"]) == (13.2, 26.4)
    ph = platform.db.execute("SELECT price FROM price_history").fetchone()
    assert ph["price"] == 12.0  # price history records the base clearing price

    cats = [r["category"] for r in ledger_rows(platform, 2)]
    assert "purchase" in cats and "transport_fee" in cats


async def test_clearing_prorata_at_margin():
    platform, _ = make_platform()
    # Two sellers both list at the same marginal price 10.
    await seller_with_listing(platform, agent_id=1, qty=10, ask_price=10.0)
    await seller_with_listing(platform, agent_id=3, qty=10, ask_price=10.0)
    await register_agent(platform, 2, balance=1000.0)
    await platform.place_bid(2, ("crude_oil", 12.0, 6))

    await platform.clear_market()
    # 6 units shared pro-rata across two equal 10-unit asks → 3 each, @ midpoint 11.
    rows = platform.db.execute(
        "SELECT seller_id, quantity, price FROM market_transaction ORDER BY seller_id"
    ).fetchall()
    assert [(r["seller_id"], r["quantity"], r["price"]) for r in rows] == [
        (1, 3, 11.0), (3, 3, 11.0),
    ]


async def test_no_crossing_refunds_escrow_and_keeps_listing():
    platform, _ = make_platform()
    _, listed = await seller_with_listing(platform, agent_id=1, ask_price=20.0)
    await register_agent(platform, 2, balance=1000.0)
    await platform.place_bid(2, ("crude_oil", 10.0, 3))  # below the ask

    summaries = await platform.clear_market()
    assert summaries == []
    assert balance_of(platform, 2) == 1000.0  # full escrow refunded
    assert platform.db.execute(
        "SELECT quantity_available FROM market_listing WHERE listing_id = ?",
        (listed["listing_id"],),
    ).fetchone()["quantity_available"] == 10


# ── Listing upkeep ──────────────────────────────────────────────────────────

async def test_update_market_state_purges_exhausted_listings():
    platform, _ = make_platform()
    _, listed = await seller_with_listing(platform, agent_id=1, qty=2, ask_price=10.0)
    await register_agent(platform, 2, balance=100.0)
    await platform.place_bid(2, ("crude_oil", 10.0, 2))
    await platform.clear_market()

    assert platform.db.execute("SELECT COUNT(*) FROM market_listing").fetchone()[0] == 1
    await platform.update_market_state()
    assert platform.db.execute("SELECT COUNT(*) FROM market_listing").fetchone()[0] == 0


async def test_auto_cancel_returns_stale_stock_to_inventory():
    platform, _ = make_platform(auto_cancel_steps=2)
    _, listed = await seller_with_listing(platform, agent_id=1, qty=10, ask_price=10.0)
    # All 10 units listed → none left in inventory.
    assert platform.db.execute(
        "SELECT quantity FROM good WHERE producer_id = 1"
    ).fetchone()["quantity"] == 0

    platform.clock.tick()  # step 1: steps_listed = 1 < 2 → kept
    await platform.update_market_state()
    assert platform.db.execute("SELECT COUNT(*) FROM market_listing").fetchone()[0] == 1

    platform.clock.tick()  # step 2: steps_listed = 2 >= 2 → cancelled
    await platform.update_market_state()
    assert platform.db.execute("SELECT COUNT(*) FROM market_listing").fetchone()[0] == 0
    assert platform.db.execute(
        "SELECT quantity FROM good WHERE producer_id = 1"
    ).fetchone()["quantity"] == 10  # stock returned to the seller


async def test_check_price_history_empty_and_average():
    platform, _ = make_platform()
    await register_agent(platform, 1)

    empty = await platform.check_price_history(1, "crude_oil")
    assert empty == {
        "success": True,
        "good_name": "crude_oil",
        "prices": [],
        "message": "No clearing prices recorded for this good yet.",
    }

    platform.ctx.execute(
        "INSERT INTO price_history (good_name, price, quantity, timestamp) "
        "VALUES ('crude_oil', 10.0, 1, 0), ('crude_oil', 14.0, 2, 0)",
        commit=True,
    )
    result = await platform.check_price_history(1, "crude_oil")
    assert result["average_price"] == 12.0
    assert len(result["prices"]) == 2


async def test_search_goods_and_agents():
    platform, _ = make_platform()
    _, _ = await seller_with_listing(platform, agent_id=1, ask_price=10.0)
    await register_agent(platform, 2, agent_type="bank", sector="finance")

    goods = await platform.search_goods(2, "crude")
    assert len(goods["listings"]) == 1

    own = await platform.search_goods(1, "crude")
    assert own["listings"] == []

    agents = await platform.search_agents(1, "bank")
    assert [a["agent_id"] for a in agents["agents"]] == [2]

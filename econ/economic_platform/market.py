"""Market listings, sealed bids, and the per-step call-auction clearing.

The market is a **batch call auction**: agents submit sell orders (resting
``market_listing`` asks) and per-step buy orders (sealed bids), and once per
step every good is cleared at a single uniform price. There is no immediate
execution and no posted-price buying — nothing trades until ``clear()`` runs.

Design (see the market-clearing design decisions):
- **Uniform price, volume-maximising midpoint (k=0.5).** The clearing price is
  the midpoint of the marginal matched ask and marginal matched bid.
- **Pro-rata at the margin.** Orders priced better than the clearing price fill
  fully; orders sitting at the marginal price share the remaining quota
  proportionally to their size.
- **Sealed bids.** Bids are transient (per-step, in memory) and never visible to
  other agents; asks rest on the book across steps.
- **Single global auction + transport friction.** One clearing price per good
  across all regions; buyers are matched to sellers preferring same-region pairs
  first, and a transport surcharge is applied per cross-region matched pair at
  settlement.
- **Escrow at submission.** A bid locks ``limit_price * quantity`` from the
  bidder's balance when placed; at clearing the filled units pay the (lower)
  uniform clearing price and the unused escrow is refunded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from econ.economic_platform.context import PlatformContext
from econ.economic_platform.ledger import LedgerService
from econ.economic_platform.typing import ActionType

logger = logging.getLogger(__name__)


@dataclass
class _Bid:
    """A sealed buy order awaiting the current step's clearing."""

    agent_id: int
    good_name: str
    limit_price: float
    quantity: int          # escrowed quantity (may be shrunk to fit balance)
    escrow: float          # credits locked = limit_price * quantity
    filled: int = 0        # set during clearing


@dataclass
class _Allocation:
    """A side's per-order fill quantities after applying pro-rata at the margin."""

    fills: dict[int, int] = field(default_factory=dict)  # order_key -> units


class MarketService:
    def __init__(self, ctx: PlatformContext, ledger: LedgerService) -> None:
        self.ctx = ctx
        self.ledger = ledger
        # Sealed bids submitted during the current step, cleared in clear().
        self._pending_bids: list[_Bid] = []
        # Uniform clearing price per good for the current clear() invocation.
        self._last_clearing_price: dict[str, float] = {}

    # ── Read helpers ─────────────────────────────────────────────────────

    def recent_average_price(self, good_name: str) -> float | None:
        row = self.ctx.execute(
            "SELECT AVG(price) AS avg_price FROM price_history WHERE good_name = ?",
            (good_name,),
        ).fetchone()
        if row is None or row["avg_price"] is None:
            return None
        return float(row["avg_price"])

    def last_clearing_price(self, good_name: str) -> float | None:
        """Price the good cleared at most recently.

        Prefers this step's clearing price (set during ``clear()``, available to
        consumer-needs accounting which runs right after), then falls back to the
        latest recorded clearing price in ``price_history``. ``None`` if the good
        has never cleared.
        """
        price = self._last_clearing_price.get(good_name)
        if price:
            return float(price)
        row = self.ctx.execute(
            "SELECT price FROM price_history WHERE good_name = ? "
            "ORDER BY timestamp DESC, id DESC LIMIT 1",
            (good_name,),
        ).fetchone()
        if row is None or row["price"] is None:
            return None
        return float(row["price"])

    def own_listings(self, agent_id: int, step: int) -> list[dict]:
        """The agent's active listings — what's on sale and for how long."""
        rows = self.ctx.execute(
            "SELECT listing_id, good_name, ask_price, quantity_available, created_at, "
            "       (? - created_at) AS steps_listed "
            "FROM market_listing "
            "WHERE seller_id = ? AND quantity_available > 0 "
            "ORDER BY good_name, ask_price ASC",
            (step, agent_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def _avg_unit_cost(self, agent_id: int, good_name: str) -> float | None:
        row = self.ctx.execute(
            "SELECT CASE WHEN SUM(quantity) > 0 "
            "            THEN SUM(quantity * unit_cost) / SUM(quantity) END AS avg_cost "
            "FROM good WHERE producer_id = ? AND name = ? AND quantity > 0",
            (agent_id, good_name),
        ).fetchone()
        if row is None or row["avg_cost"] is None:
            return None
        return round(float(row["avg_cost"]), 4)

    # ── Listing upkeep ────────────────────────────────────────────────────

    def purge_exhausted(self) -> None:
        """Remove fully-sold listings from the market."""
        self.ctx.execute(
            "DELETE FROM market_listing WHERE quantity_available <= 0",
            commit=True,
        )

    def auto_cancel_stale(self, step: int, max_steps: int) -> None:
        """Cancel asks that have rested unfilled for ``max_steps`` or more.

        The remaining stock is returned to the seller's inventory (the original
        ``good`` row, preserving its cost basis) and the listing is deleted, so
        the seller must re-list at a fresh price. No price is changed — price
        discovery is the auction's job, not a hidden decay.
        """
        if max_steps <= 0:
            return
        stale = self.ctx.execute(
            "SELECT listing_id, good_id, quantity_available FROM market_listing "
            "WHERE quantity_available > 0 AND (? - created_at) >= ?",
            (step, max_steps),
        ).fetchall()
        for row in stale:
            self.ctx.execute(
                "UPDATE good SET quantity = quantity + ? WHERE good_id = ?",
                (row["quantity_available"], row["good_id"]),
            )
            self.ctx.execute(
                "DELETE FROM market_listing WHERE listing_id = ?",
                (row["listing_id"],),
            )
        if stale:
            self.ctx.db.commit()

    def reset_pending_bids(self) -> None:
        self._pending_bids = []

    # ── Observation ───────────────────────────────────────────────────────

    async def observe_market(self, agent_id: int) -> dict:
        """Return resting asks (excluding the agent's own) and recent clearing
        prices. Bids are sealed and never returned.
        """
        listings = self.ctx.execute(
            "SELECT listing_id, seller_id, good_name, ask_price, quantity_available "
            "FROM market_listing "
            "WHERE quantity_available > 0 AND seller_id != ? "
            "ORDER BY ask_price ASC",
            (agent_id,),
        ).fetchall()

        recent_tx = self.ctx.execute(
            "SELECT good_name, price, quantity, timestamp "
            "FROM price_history "
            "ORDER BY timestamp DESC, id DESC LIMIT ?",
            (self.ctx.price_history_window,)
        ).fetchall()

        self.ctx.record_trace(agent_id, ActionType.OBSERVE_MARKET.value, {})
        return {
            "success": True,
            "time_step": self.ctx.clock.now(),
            "listings": [dict(r) for r in listings],
            "recent_transactions": [dict(r) for r in recent_tx],
        }

    # ── Sell orders (resting asks) ─────────────────────────────────────────

    async def list_good(self, agent_id: int, message) -> dict:
        """Put produced goods on the market as a resting sell order (ask).

        message: (good_id: int, ask_price: float, quantity: int)
        """
        good_id, ask_price, quantity = message
        good_id = int(good_id)
        ask_price = float(ask_price)
        quantity = int(quantity)
        ts = self.ctx.clock.now()

        good = self.ctx.execute(
            "SELECT * FROM good WHERE good_id = ? AND producer_id = ?",
            (good_id, agent_id)
        ).fetchone()
        if good is None:
            return {"success": False,
                    "error": f"good_id {good_id} not found or not owned by agent {agent_id}"}

        if good["quantity"] < quantity:
            return {"success": False,
                    "error": f"Only {good['quantity']} units available, requested {quantity}"}

        self.ctx.execute(
            "UPDATE good SET quantity = quantity - ? WHERE good_id = ?",
            (quantity, good_id), commit=True,
        )
        cursor = self.ctx.execute(
            "INSERT INTO market_listing "
            "(seller_id, good_id, good_name, ask_price, quantity_available, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, good_id, good["name"], ask_price, quantity, ts),
            commit=True,
        )
        listing_id = cursor.lastrowid

        # Cost basis of the batch being listed (info-nudge only — not enforced).
        batch_cost = float(good["unit_cost"] or 0.0)
        below_cost = batch_cost > 0 and ask_price < batch_cost
        self.ctx.record_trace(agent_id, ActionType.LIST_GOOD.value,
                              {"good_id": good_id, "good_name": good["name"],
                               "ask_price": ask_price, "quantity": quantity,
                               "listing_id": listing_id, "below_cost": below_cost})
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "list_good",
            "good": good["name"],
            "qty": quantity,
            "price": ask_price,
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": f"Listed {quantity} {good['name']} @ ${ask_price:.2f}",
        })
        result = {"success": True, "listing_id": listing_id,
                  "good_name": good["name"], "ask_price": ask_price,
                  "quantity_listed": quantity}
        if below_cost:
            result["warning"] = (
                f"Ask {ask_price:.2f} is below your average unit cost "
                f"{batch_cost:.2f} — you will sell at a loss if it clears."
            )
        return result

    async def update_listing_price(self, agent_id: int, message) -> dict:
        """Change the ask price on one of the agent's own resting sell orders.

        Use this when an ask keeps failing to clear: lower it toward the recent
        clearing price to win the auction, or raise it if the market moved up.

        message: (listing_id: int, new_price: float)
        """
        listing_id, new_price = message
        listing_id = int(listing_id)
        new_price = float(new_price)

        if new_price <= 0:
            return {"success": False, "error": "new_price must be positive."}

        listing = self.ctx.execute(
            "SELECT * FROM market_listing "
            "WHERE listing_id = ? AND seller_id = ? AND quantity_available > 0",
            (listing_id, agent_id),
        ).fetchone()
        if listing is None:
            return {
                "success": False,
                "error": f"listing_id {listing_id} not found, already sold out, "
                         "or does not belong to you.",
            }

        old_price = listing["ask_price"]
        self.ctx.execute(
            "UPDATE market_listing SET ask_price = ? WHERE listing_id = ?",
            (new_price, listing_id),
            commit=True,
        )
        self.ctx.record_trace(agent_id, ActionType.UPDATE_LISTING_PRICE.value, {
            "listing_id": listing_id,
            "good_name": listing["good_name"],
            "old_price": old_price,
            "new_price": new_price,
            "quantity_available": listing["quantity_available"],
        })
        return {
            "success": True,
            "listing_id": listing_id,
            "good_name": listing["good_name"],
            "old_price": old_price,
            "new_price": new_price,
            "quantity_available": listing["quantity_available"],
        }

    # ── Buy orders (sealed bids) ───────────────────────────────────────────

    async def place_bid(self, agent_id: int, message) -> dict:
        """Submit a sealed buy order into this step's call auction.

        message: (good_name: str, limit_price: float, quantity: int)

        The bid does NOT execute immediately. ``limit_price * quantity`` is
        escrowed from your balance now; at end-of-step clearing all matched
        units trade at one uniform clearing price (<= your limit), and unused
        escrow is refunded. If your balance can't cover the full escrow, the
        quantity is shrunk to what you can afford.
        """
        good_name, limit_price, quantity = message
        good_name = str(good_name).strip()
        limit_price = float(limit_price)
        quantity = int(quantity)
        ts = self.ctx.clock.now()

        if not good_name:
            return {"success": False, "error": "good_name must be provided."}
        if limit_price <= 0:
            return {"success": False, "error": "limit_price must be positive."}
        if quantity <= 0:
            return {"success": False, "error": "quantity must be positive."}

        balance = self.ledger.balance(agent_id)
        affordable = int(balance // limit_price)
        if affordable <= 0:
            return {"success": False,
                    "error": f"Insufficient balance to escrow any units at "
                             f"limit {limit_price:.2f} (balance {balance:.2f})."}
        filled_qty = min(quantity, affordable)
        escrow = round(limit_price * filled_qty, 4)
        if not self.ledger.debit(agent_id, escrow):
            return {"success": False,
                    "error": f"Could not escrow {escrow:.2f} credits."}

        self._pending_bids.append(_Bid(
            agent_id=agent_id,
            good_name=good_name,
            limit_price=round(limit_price, 4),
            quantity=filled_qty,
            escrow=escrow,
        ))

        avg_cost = self._avg_unit_cost(agent_id, good_name)
        self.ctx.record_trace(agent_id, ActionType.PLACE_BID.value, {
            "good_name": good_name,
            "limit_price": round(limit_price, 4),
            "quantity": filled_qty,
            "escrow": escrow,
        })
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "place_bid",
            "good": good_name,
            "qty": filled_qty,
            "price": round(limit_price, 4),
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": f"Bid {filled_qty} {good_name} @ ≤${limit_price:.2f}",
        })
        result = {"success": True, "good_name": good_name,
                  "limit_price": round(limit_price, 4),
                  "quantity_submitted": filled_qty, "escrow": escrow,
                  "note": "Bid queued for end-of-step clearing; not yet filled."}
        if filled_qty < quantity:
            result["warning"] = (
                f"Requested {quantity} but only {filled_qty} could be escrowed "
                f"with your balance."
            )
        if avg_cost is not None and limit_price < avg_cost:
            # Informational only for resellers (speculators) holding the good.
            result["note_below_holding_cost"] = (
                f"Your limit {limit_price:.2f} is below your average holding "
                f"cost {avg_cost:.2f} for {good_name}."
            )
        return result

    # ── Call-auction clearing ──────────────────────────────────────────────

    async def clear(self, step: int) -> list[dict]:
        """Clear every good with crossing supply and demand at a uniform price.

        Runs once per step (after agent actions, before consumer needs). Returns
        a per-good clearing summary. Unfilled bids are refunded their escrow;
        unfilled asks rest on the book.
        """
        bids = self._pending_bids
        self._pending_bids = []
        self._last_clearing_price = {}
        if not bids:
            # Still nothing to do for the demand side; supply just rests.
            return []

        goods = sorted({b.good_name for b in bids})
        summaries: list[dict] = []
        for good_name in goods:
            summary = await self._clear_good(step, good_name,
                                             [b for b in bids if b.good_name == good_name])
            if summary is not None:
                summaries.append(summary)

        # Refund escrow for every bid based on what actually filled.
        for bid in bids:
            spent = round(bid.filled * self._last_clearing_price.get(bid.good_name, 0.0), 4)
            refund = round(bid.escrow - spent, 4)
            if refund > 0:
                self.ledger.credit(bid.agent_id, refund)
        return summaries

    async def _clear_good(self, step: int, good_name: str, bids: list[_Bid]) -> dict | None:
        self._last_clearing_price[good_name] = 0.0

        ask_rows = self.ctx.execute(
            "SELECT listing_id, seller_id, good_id, ask_price, quantity_available "
            "FROM market_listing "
            "WHERE good_name = ? AND quantity_available > 0 "
            "ORDER BY ask_price ASC, listing_id ASC",
            (good_name,),
        ).fetchall()
        asks = [dict(r) for r in ask_rows]
        if not asks or not bids:
            return None

        # Bids: highest limit first; deterministic tie-break by agent_id.
        bids_sorted = sorted(
            enumerate(bids),
            key=lambda ib: (-ib[1].limit_price, ib[1].agent_id, ib[0]),
        )

        clearing_price, marg_ask, marg_bid = self._compute_clearing_price(asks, bids_sorted)
        if clearing_price is None:
            return None  # no crossing
        self._last_clearing_price[good_name] = clearing_price

        # Pro-rata-at-the-margin allocation, targeting the matched volume.
        q_star = self._matched_volume(asks, bids_sorted)
        ask_fills = self._allocate(
            [(a["listing_id"], round(a["ask_price"], 4), a["quantity_available"]) for a in asks],
            q_star, marg_ask, better=lambda price, marg: price < marg,
        )
        bid_fills = self._allocate(
            [(i, round(b.limit_price, 4), b.quantity) for i, b in bids_sorted],
            q_star, marg_bid, better=lambda price, marg: price > marg,
        )

        # Pair buyers <-> sellers, preferring same-region (lowest transport).
        ask_index = {a["listing_id"]: a for a in asks}
        pairs = self._match_pairs(ask_fills, bid_fills, ask_index, bids)

        # Settle every matched pair at the uniform clearing price.
        traded_qty = await self._settle(step, good_name, clearing_price, pairs,
                                        ask_index, bids)
        if traded_qty <= 0:
            return None

        self.ctx.execute(
            "INSERT INTO price_history (good_name, price, quantity, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (good_name, clearing_price, traded_qty, step),
            commit=True,
        )
        summary = {
            "type": "market_clearing",
            "step": step,
            "good": good_name,
            "clearing_price": clearing_price,
            "quantity": traded_qty,
        }
        await self.ctx.emit(summary)
        logger.info("Cleared %s @ %.4f x%d (step %d)",
                    good_name, clearing_price, traded_qty, step)
        return summary

    @staticmethod
    def _matched_volume(asks: list[dict], bids_sorted) -> int:
        """Total units that cross (cheapest asks vs highest bids)."""
        a = b = 0
        ra = asks[0]["quantity_available"] if asks else 0
        rb = bids_sorted[0][1].quantity if bids_sorted else 0
        q = 0
        while a < len(asks) and b < len(bids_sorted):
            ask_p = round(asks[a]["ask_price"], 4)
            bid_p = round(bids_sorted[b][1].limit_price, 4)
            if ask_p > bid_p:
                break
            t = min(ra, rb)
            q += t
            ra -= t
            rb -= t
            if ra == 0:
                a += 1
                ra = asks[a]["quantity_available"] if a < len(asks) else 0
            if rb == 0:
                b += 1
                rb = bids_sorted[b][1].quantity if b < len(bids_sorted) else 0
        return q

    def _compute_clearing_price(self, asks: list[dict], bids_sorted):
        """Return (clearing_price, marginal_ask_price, marginal_bid_price).

        Walks cheapest asks against highest bids; the last crossing pair gives
        the marginal prices, and the clearing price is their midpoint (k=0.5).
        """
        a = b = 0
        ra = asks[0]["quantity_available"]
        rb = bids_sorted[0][1].quantity
        marg_ask = marg_bid = None
        while a < len(asks) and b < len(bids_sorted):
            ask_p = round(asks[a]["ask_price"], 4)
            bid_p = round(bids_sorted[b][1].limit_price, 4)
            if ask_p > bid_p:
                break
            marg_ask, marg_bid = ask_p, bid_p
            t = min(ra, rb)
            ra -= t
            rb -= t
            if ra == 0:
                a += 1
                ra = asks[a]["quantity_available"] if a < len(asks) else 0
            if rb == 0:
                b += 1
                rb = bids_sorted[b][1].quantity if b < len(bids_sorted) else 0
        if marg_ask is None:
            return None, None, None
        return round((marg_ask + marg_bid) / 2.0, 4), marg_ask, marg_bid

    @staticmethod
    def _allocate(orders, total_q: int, marginal_price: float, better) -> dict[int, int]:
        """Allocate ``total_q`` units across ``orders`` = [(key, price, qty), ...].

        Orders strictly better-priced than the margin fill fully; orders at the
        marginal price share the remaining quota pro-rata (deterministic).
        """
        fills: dict[int, int] = {}
        used = 0
        at_margin = []
        for key, price, qty in orders:
            if better(price, marginal_price):
                fills[key] = qty
                used += qty
            elif price == marginal_price:
                at_margin.append((key, qty))
        quota = total_q - used
        group_total = sum(q for _, q in at_margin)
        if quota > 0 and group_total > 0:
            fracs = []
            assigned = 0
            for key, qty in at_margin:
                raw = quota * qty / group_total
                base = min(qty, int(raw))
                fills[key] = fills.get(key, 0) + base
                assigned += base
                fracs.append((raw - int(raw), key, qty))
            remaining = quota - assigned
            # Distribute leftover one unit at a time by largest fractional part.
            fracs.sort(key=lambda f: (-f[0], f[1]))
            idx = 0
            guard = 0
            while remaining > 0 and fracs and guard < 100000:
                _, key, qty = fracs[idx % len(fracs)]
                if fills.get(key, 0) < qty:
                    fills[key] = fills.get(key, 0) + 1
                    remaining -= 1
                idx += 1
                guard += 1
        return fills

    def _match_pairs(self, ask_fills, bid_fills, ask_index, bids) -> list[dict]:
        """Greedily pair buyer units to seller units, preferring same-region
        (lowest transport cost) and skipping self-trades.
        """
        # Remaining sellable units per listing.
        sellers = [
            {"listing_id": lid, "seller_id": ask_index[lid]["seller_id"], "rem": units}
            for lid, units in ask_fills.items() if units > 0
        ]
        buyers = [
            {"bid_idx": i, "agent_id": bids[i].agent_id, "rem": units}
            for i, units in bid_fills.items() if units > 0
        ]
        # Deterministic order: buyers by agent_id then bid index.
        buyers.sort(key=lambda x: (x["agent_id"], x["bid_idx"]))

        pairs: list[dict] = []
        for buyer in buyers:
            while buyer["rem"] > 0:
                candidates = [
                    s for s in sellers
                    if s["rem"] > 0 and s["seller_id"] != buyer["agent_id"]
                ]
                if not candidates:
                    break  # only self-supply left → units go unfilled
                candidates.sort(key=lambda s: (
                    self.ctx.transport_costs.get_cost(s["seller_id"], buyer["agent_id"]),
                    s["seller_id"], s["listing_id"],
                ))
                seller = candidates[0]
                units = min(buyer["rem"], seller["rem"])
                pairs.append({
                    "listing_id": seller["listing_id"],
                    "seller_id": seller["seller_id"],
                    "buyer_id": buyer["agent_id"],
                    "bid_idx": buyer["bid_idx"],
                    "units": units,
                })
                seller["rem"] -= units
                buyer["rem"] -= units
        return pairs

    async def _settle(self, step, good_name, clearing_price, pairs, ask_index, bids) -> int:
        """Execute every matched pair at the uniform clearing price."""
        traded = 0
        for pair in pairs:
            units = pair["units"]
            if units <= 0:
                continue
            seller_id = pair["seller_id"]
            buyer_id = pair["buyer_id"]
            listing_id = pair["listing_id"]

            transport_rate = self.ctx.transport_costs.get_cost(seller_id, buyer_id)
            base_total = round(clearing_price * units, 4)
            transport_fee = round(base_total * transport_rate, 4)
            effective_unit = round(clearing_price * (1 + transport_rate), 4)
            effective_total = round(base_total + transport_fee, 4)

            # Reduce the resting ask.
            self.ctx.execute(
                "UPDATE market_listing SET quantity_available = quantity_available - ? "
                "WHERE listing_id = ?",
                (units, listing_id), commit=True,
            )
            # Seller receives the base clearing price (transport is a friction loss).
            self.ledger.credit(seller_id, base_total)
            self.ledger.record(
                seller_id, "sale", base_total,
                f"Sold {units} × {good_name} @ {clearing_price:.2f}/unit "
                f"(cleared) to agent {buyer_id}",
            )
            # Buyer: escrow already covered the base cost; pay transport on top.
            bids[pair["bid_idx"]].filled += units
            self.ledger.record(
                buyer_id, "purchase", -base_total,
                f"Bought {units} × {good_name} @ {clearing_price:.2f}/unit "
                f"(cleared) from agent {seller_id}",
            )
            if transport_fee > 0:
                self.ledger.force_debit(buyer_id, transport_fee)
                self.ledger.record(
                    buyer_id, "transport_fee", -transport_fee,
                    f"Transport on {units} × {good_name} from agent {seller_id} "
                    f"(+{transport_rate*100:.0f}%)",
                )
            # Transfer goods into the buyer's inventory at effective cost basis.
            buyer_good = self.ctx.execute(
                "INSERT INTO good (producer_id, name, quantity, unit_cost, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (buyer_id, good_name, units, effective_unit, step),
                commit=True,
            )
            tx = self.ctx.execute(
                "INSERT INTO market_transaction "
                "(buyer_id, seller_id, good_name, price, quantity, total_paid, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (buyer_id, seller_id, good_name, effective_unit, units,
                 effective_total, step),
                commit=True,
            )
            self.ctx.record_trace(buyer_id, ActionType.PLACE_BID.value, {
                "result": "filled", "good_name": good_name,
                "clearing_price": clearing_price, "quantity": units,
                "effective_price": effective_unit, "total_paid": effective_total,
                "seller_id": seller_id, "transaction_id": tx.lastrowid,
                "acquired_good_id": buyer_good.lastrowid,
            })
            await self.ctx.emit({
                "type": "trade",
                "step": step,
                "buyer": self.ctx.agent_name(buyer_id),
                "buyer_id": buyer_id,
                "seller": self.ctx.agent_name(seller_id),
                "seller_id": seller_id,
                "good": good_name,
                "qty": units,
                "price": effective_unit,
                "total": effective_total,
                "buyer_balance": round(self.ledger.balance(buyer_id), 2),
                "seller_balance": round(self.ledger.balance(seller_id), 2),
                "summary": (
                    f"{self.ctx.agent_name(buyer_id)} bought {units} "
                    f"{good_name} from {self.ctx.agent_name(seller_id)} "
                    f"@ ${effective_unit:.2f} (cleared)"
                ),
            })
            traded += units
        return traded

    # ── Misc reads ──────────────────────────────────────────────────────────

    async def check_price_history(self, agent_id: int, message) -> dict:
        """Return recent clearing prices for a given good.

        message: good_name (str)
        """
        good_name = message
        rows = self.ctx.execute(
            "SELECT price, quantity, timestamp FROM price_history "
            "WHERE good_name = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
            (good_name, self.ctx.price_history_window)
        ).fetchall()

        self.ctx.record_trace(agent_id, ActionType.CHECK_PRICE_HISTORY.value,
                              {"good_name": good_name})
        if not rows:
            return {"success": True, "good_name": good_name, "prices": [],
                    "message": "No clearing prices recorded for this good yet."}
        prices = [{"price": r["price"], "quantity": r["quantity"],
                   "timestamp": r["timestamp"]} for r in rows]
        avg_price = round(sum(p["price"] for p in prices) / len(prices), 4)
        return {"success": True, "good_name": good_name,
                "prices": prices, "average_price": avg_price}

    async def search_goods(self, agent_id: int, message) -> dict:
        """Search resting asks by good name keyword.

        message: query (str)
        """
        query = f"%{message}%"
        rows = self.ctx.execute(
            "SELECT listing_id, seller_id, good_name, ask_price, quantity_available "
            "FROM market_listing "
            "WHERE good_name LIKE ? AND quantity_available > 0 AND seller_id != ? "
            "ORDER BY ask_price ASC",
            (query, agent_id),
        ).fetchall()
        self.ctx.record_trace(agent_id, ActionType.SEARCH_GOODS.value,
                              {"query": message})
        return {"success": True, "listings": [dict(r) for r in rows]}

    async def search_agents(self, agent_id: int, message) -> dict:
        """Search registered agents by name or type.

        message: query (str)
        """
        query = f"%{message}%"
        rows = self.ctx.execute(
            "SELECT agent_id, name, agent_type, sector FROM agent "
            "WHERE name LIKE ? OR agent_type LIKE ? OR sector LIKE ?",
            (query, query, query)
        ).fetchall()
        self.ctx.record_trace(agent_id, ActionType.SEARCH_AGENTS.value,
                              {"query": message})
        return {"success": True, "agents": [dict(r) for r in rows]}

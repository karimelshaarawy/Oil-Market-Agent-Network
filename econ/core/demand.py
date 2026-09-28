"""Price-elastic demand curve.

A single pure function defines the demand curve so it is computed identically
in two places that must agree:

- :mod:`econ.economic_platform.consumer_ops` — the *accounting* side, which
  scales operating revenue and shortage penalties off the price-adjusted target
  (so a consumer is never penalised for rationally buying less at a high price).
- :mod:`econ.economic_agent.agent_environment` — the *prompt* side, which shows
  each consumer its current operating target so the LLM's bids line up with the
  curve.

The curve is constant-elasticity (CES-style):

    effective = base * (reference_price / price) ** elasticity

clamped to ``[floor_fraction * base, cap_multiple * base]``. ``elasticity`` is
per-need (heterogeneous: an "inelastic" airline ~0.1, a "price-sensitive"
retailer ~0.9). ``price <= 0`` or a missing reference falls back to ``base``.
"""
from __future__ import annotations

import math

# Fallbacks used when a consumption_need omits the explicit field.
DEFAULT_DEMAND_ELASTICITY = 0.4
DEFAULT_DEMAND_FLOOR_FRACTION = 0.5   # never demand less than 50% of base need
DEFAULT_DEMAND_CAP_MULTIPLE = 2.0     # never demand more than 2x base need


def _round_units(value: float) -> int:
    """Round to whole units, half-up.

    Python's built-in ``round`` is half-to-even, so ``round(0.5) == 0`` — which
    would silently zero out a small need sitting at its floor (e.g. a base-1
    need clamped to the default 0.5 floor). Half-up keeps ``0.5 -> 1`` so a
    positive need with a non-trivial floor never vanishes, while an explicitly
    near-zero floor is still allowed to reach 0.
    """
    return int(math.floor(value + 0.5))


def effective_quantity(
    base: float,
    reference_price: float,
    price: float | None,
    elasticity: float = DEFAULT_DEMAND_ELASTICITY,
    floor_fraction: float = DEFAULT_DEMAND_FLOOR_FRACTION,
    cap_multiple: float = DEFAULT_DEMAND_CAP_MULTIPLE,
) -> int:
    """Return the price-adjusted operating target, as a non-negative integer.

    Args:
        base:            Baseline quantity per step (``quantity_per_step``).
        reference_price: Price at which demand equals ``base``.
        price:           The market price the consumer faces. ``None`` or
                         non-positive → no adjustment (returns ``base``).
        elasticity:      Demand elasticity (>= 0). 0 = perfectly inelastic.
        floor_fraction:  Lower clamp as a fraction of ``base`` (inelastic core).
        cap_multiple:    Upper clamp as a multiple of ``base``.
    """
    base = max(0.0, float(base))
    if base <= 0:
        return 0
    ref = float(reference_price or 0.0)
    if price is None or price <= 0 or ref <= 0 or elasticity <= 0:
        return _round_units(base)

    raw = base * (ref / float(price)) ** float(elasticity)

    lo = floor_fraction * base
    hi = cap_multiple * base
    if lo > hi:  # defensive: a mis-configured floor above the cap
        lo, hi = hi, lo
    clamped = min(max(raw, lo), hi)
    return _round_units(clamped)


def target_from_need(need: dict, price: float | None) -> int:
    """Price-adjusted operating target for one ``consumption_needs`` entry.

    Reads ``quantity_per_step``, ``reference_price``, and the optional
    ``elasticity`` / ``min_quantity_fraction`` / ``max_quantity_multiple``
    fields (falling back to module defaults), then applies the demand curve.
    Centralised so the accounting and prompt sides never diverge.
    """
    base = float(need.get("quantity_per_step", 0) or 0)
    reference_price = float(need.get("reference_price", 0.0) or 0.0)
    elasticity = float(need.get("elasticity", DEFAULT_DEMAND_ELASTICITY) or 0.0)
    floor_fraction = float(
        need.get("min_quantity_fraction", DEFAULT_DEMAND_FLOOR_FRACTION)
    )
    cap_multiple = float(
        need.get("max_quantity_multiple", DEFAULT_DEMAND_CAP_MULTIPLE)
    )
    return effective_quantity(
        base, reference_price, price, elasticity, floor_fraction, cap_multiple
    )

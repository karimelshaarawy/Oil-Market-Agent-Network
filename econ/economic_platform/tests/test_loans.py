"""Characterization tests for the endogenous-credit lifecycle.

Borrowers file applications (request_loan); the bank adjudicates next step
(approve_loan / deny_loan). Approval disburses funds and creates the loan; the
repay() path is unchanged from the posted-rate days.
"""
from __future__ import annotations

from econ.economic_platform.tests.helpers import (
    balance_of,
    ledger_rows,
    make_platform,
    register_agent,
)


async def _bank_and_borrower(platform):
    await register_agent(platform, 1, agent_type="bank", balance=1000.0)
    await register_agent(platform, 2, balance=0.0)


# ── request_loan ───────────────────────────────────────────────────────────

async def test_request_loan_queues_pending_no_funds_move():
    platform, events = make_platform()
    await _bank_and_borrower(platform)

    req = await platform.request_loan(2, (1, 400.0, 0.06))
    assert req["success"] is True
    assert req["request_id"] == 1
    # No money moves on application.
    assert balance_of(platform, 2) == 0.0
    assert balance_of(platform, 1) == 1000.0

    row = platform.db.execute(
        "SELECT status, proposed_rate FROM loan_request WHERE request_id = 1"
    ).fetchone()
    assert row["status"] == "pending"
    assert row["proposed_rate"] == 0.06
    assert any(e.get("action") == "request_loan" for e in events)


async def test_request_loan_rejects_non_bank_lender():
    platform, _ = make_platform()
    await register_agent(platform, 1, balance=1000.0)   # a firm, not a bank
    await register_agent(platform, 2, balance=0.0)
    result = await platform.request_loan(2, (1, 100.0, None))
    assert result["success"] is False
    assert "not a bank" in result["error"]


async def test_request_loan_blocks_duplicate_pending():
    platform, _ = make_platform()
    await _bank_and_borrower(platform)
    await platform.request_loan(2, (1, 100.0, None))
    dup = await platform.request_loan(2, (1, 50.0, None))
    assert dup["success"] is False
    assert "pending request" in dup["error"]


async def test_request_loan_blocked_while_overdue():
    platform, _ = make_platform()
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 100.0, None))
    approved = await platform.approve_loan(1, (req["request_id"], None, None))

    platform.clock.time_step = approved["due_at"] + 1
    blocked = await platform.request_loan(2, (1, 50.0, None))
    assert blocked["success"] is False
    assert "overdue loan" in blocked["error"]


# ── approve_loan ─────────────────────────────────────────────────────────────

async def test_approve_full_amount_disburses_and_creates_loan():
    platform, events = make_platform()
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 400.0, 0.06))

    ok = await platform.approve_loan(1, (req["request_id"], None, None))
    assert ok["success"] is True
    assert ok["approved_amount"] == 400.0
    assert ok["partial"] is False
    assert ok["interest_rate"] == 0.06   # borrower's proposal, within band
    assert ok["due_at"] == 10            # step 0 + default loan_duration_steps

    assert balance_of(platform, 2) == 400.0
    assert balance_of(platform, 1) == 600.0

    status = platform.db.execute(
        "SELECT status, loan_id FROM loan_request WHERE request_id = ?",
        (req["request_id"],),
    ).fetchone()
    assert status["status"] == "approved"
    assert status["loan_id"] == ok["loan_id"]

    assert ledger_rows(platform, 2)[-1]["category"] == "loan_received"
    assert ledger_rows(platform, 1)[-1]["category"] == "loan_issued"
    assert any(e.get("action") == "approve_loan" for e in events)


async def test_approve_partial_amount():
    platform, _ = make_platform()
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 400.0, None))

    ok = await platform.approve_loan(1, (req["request_id"], 0.10, 250.0))
    assert ok["approved_amount"] == 250.0
    assert ok["partial"] is True
    assert ok["interest_rate"] == 0.10
    assert balance_of(platform, 2) == 250.0
    assert balance_of(platform, 1) == 750.0


async def test_approve_clamps_rate_to_band():
    platform, _ = make_platform(min_interest_rate=0.02, max_interest_rate=0.20)
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 100.0, None))
    ok = await platform.approve_loan(1, (req["request_id"], 0.99, None))
    assert ok["interest_rate"] == 0.20   # clamped down to the max


async def test_approve_amount_capped_at_requested():
    platform, _ = make_platform()
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 100.0, None))
    ok = await platform.approve_loan(1, (req["request_id"], None, 999.0))
    assert ok["approved_amount"] == 100.0   # cannot exceed requested
    assert ok["partial"] is False


async def test_approve_blocked_when_bank_short_on_funds():
    platform, _ = make_platform()
    await register_agent(platform, 1, agent_type="bank", balance=50.0)
    await register_agent(platform, 2, balance=0.0)
    req = await platform.request_loan(2, (1, 100.0, None))
    result = await platform.approve_loan(1, (req["request_id"], None, None))
    assert result["success"] is False
    assert "Insufficient balance" in result["error"]
    # Request stays pending so the bank can approve a smaller amount.
    status = platform.db.execute(
        "SELECT status FROM loan_request WHERE request_id = ?",
        (req["request_id"],),
    ).fetchone()["status"]
    assert status == "pending"


async def test_approve_only_own_requests():
    platform, _ = make_platform()
    await register_agent(platform, 1, agent_type="bank", balance=1000.0)
    await register_agent(platform, 9, agent_type="bank", balance=1000.0)
    await register_agent(platform, 2, balance=0.0)
    req = await platform.request_loan(2, (1, 100.0, None))
    # A different bank cannot act on bank 1's request.
    result = await platform.approve_loan(9, (req["request_id"], None, None))
    assert result["success"] is False
    assert "not addressed to you" in result["error"]


# ── deny_loan + expiry ───────────────────────────────────────────────────────

async def test_deny_loan_records_reason():
    platform, events = make_platform()
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 100.0, None))
    result = await platform.deny_loan(1, (req["request_id"], "debt-to-asset too high"))
    assert result["success"] is True
    assert result["reason"] == "debt-to-asset too high"
    row = platform.db.execute(
        "SELECT status, reason FROM loan_request WHERE request_id = ?",
        (req["request_id"],),
    ).fetchone()
    assert row["status"] == "denied"
    assert row["reason"] == "debt-to-asset too high"
    assert balance_of(platform, 2) == 0.0   # nothing disbursed
    assert any(e.get("action") == "deny_loan" for e in events)


async def test_expire_stale_requests():
    platform, _ = make_platform()
    await _bank_and_borrower(platform)
    req = await platform.request_loan(2, (1, 100.0, None))   # requested_at = 0

    platform.loans.expire_stale_requests(step=3, max_steps=3)
    row = platform.db.execute(
        "SELECT status FROM loan_request WHERE request_id = ?",
        (req["request_id"],),
    ).fetchone()
    assert row["status"] == "expired"
    # An expired request can no longer be approved.
    result = await platform.approve_loan(1, (req["request_id"], None, None))
    assert result["success"] is False


async def test_pending_requests_for_lender_includes_dossier():
    platform, _ = make_platform()
    await register_agent(platform, 1, agent_type="bank", balance=1000.0)
    await register_agent(platform, 2, balance=300.0, sector="transportation")
    await platform.request_loan(2, (1, 250.0, 0.07))

    desk = platform.loans.pending_requests_for_lender(1, step=0)
    assert len(desk) == 1
    entry = desk[0]
    assert entry["borrower_id"] == 2
    assert entry["amount"] == 250.0
    assert entry["proposed_rate"] == 0.07
    assert entry["fraction_of_your_capital"] == 0.25  # 250 / 1000
    dossier = entry["applicant"]
    assert dossier["balance"] == 300.0
    assert dossier["sector"] == "transportation"
    assert dossier["outstanding_debt"] == 0.0
    assert dossier["overdue_loans"] == 0


# ── repay (unchanged behaviour) ──────────────────────────────────────────────

async def test_repay_on_time_principal_plus_interest():
    platform, _ = make_platform()
    await register_agent(platform, 1, agent_type="bank", balance=1000.0)
    await register_agent(platform, 2, balance=50.0)
    req = await platform.request_loan(2, (1, 100.0, 0.05))
    loan = await platform.approve_loan(1, (req["request_id"], None, None))

    result = await platform.repay(2, loan["loan_id"])
    assert result["success"] is True
    assert result["amount_repaid"] == 105.0   # 100 * 1.05
    assert balance_of(platform, 2) == 45.0     # 50 + 100 - 105
    assert balance_of(platform, 1) == 1005.0   # 1000 - 100 + 105

    repaid = platform.db.execute(
        "SELECT repaid FROM loan WHERE loan_id = ?", (loan["loan_id"],)
    ).fetchone()["repaid"]
    assert repaid == 1


async def test_repay_overdue_adds_penalty():
    platform, _ = make_platform()
    await register_agent(platform, 1, agent_type="bank", balance=1000.0)
    await register_agent(platform, 2, balance=50.0)
    req = await platform.request_loan(2, (1, 100.0, 0.05))
    loan = await platform.approve_loan(1, (req["request_id"], None, None))

    platform.clock.time_step = loan["due_at"] + 2
    result = await platform.repay(2, loan["loan_id"])
    # 100 * 1.05 + 2 * 100 * 0.05 * 0.1 = 106.0
    assert result["amount_repaid"] == 106.0

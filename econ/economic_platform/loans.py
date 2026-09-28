"""Loan lifecycle: applications, bank adjudication, repayment, and reporting.

Credit is endogenous and bank-adjudicated. A borrower files a ``loan_request``
(no escrow); the bank sees pending requests in its observation and decides per
applicant — ``approve_loan`` (set rate, optionally a smaller amount) or
``deny_loan``. Approval disburses funds and creates the ``loan`` row. Two hard
invariants are always enforced regardless of bank judgment: a borrower with an
overdue loan cannot receive new credit, and the bank cannot lend money it does
not have. The ``max_borrow_fraction`` cap is a *soft* signal shown to the bank,
not a hard limit.
"""
from __future__ import annotations

from econ.economic_platform.context import PlatformContext
from econ.economic_platform.ledger import LedgerService
from econ.economic_platform.typing import ActionType


class LoanService:
    def __init__(self, ctx: PlatformContext, ledger: LedgerService) -> None:
        self.ctx = ctx
        self.ledger = ledger

    # ── Hard invariants (always enforced) ──────────────────────────────────

    def _overdue_loan(self, borrower_id: int, step: int) -> dict | None:
        row = self.ctx.execute(
            "SELECT loan_id, due_at FROM loan "
            "WHERE borrower_id = ? AND repaid = 0 AND due_at < ?",
            (borrower_id, step),
        ).fetchone()
        return dict(row) if row else None

    def active_loans(self, agent_id: int, step: int) -> list[dict]:
        """Outstanding loans, annotated with overdue penalties when late."""
        raw_loans = self.ctx.execute(
            "SELECT loan_id, lender_id, amount, interest_rate, due_at "
            "FROM loan WHERE borrower_id = ? AND repaid = 0",
            (agent_id,)
        ).fetchall()
        loans = []
        for loan in raw_loans:
            entry = dict(loan)
            steps_overdue = max(0, step - loan["due_at"])
            if steps_overdue > 0:
                current_repayment_due = round(
                    loan["amount"] * (1 + loan["interest_rate"])
                    + steps_overdue * loan["amount"] * loan["interest_rate"] * 0.1,
                    4,
                )
                penalty_per_step = round(
                    loan["amount"] * loan["interest_rate"] * 0.1, 4
                )
                entry["steps_overdue"] = steps_overdue
                entry["current_repayment_due"] = current_repayment_due
                entry["WARNING"] = (
                    f"OVERDUE by {steps_overdue} step(s) — penalty growing by "
                    f"{penalty_per_step:.2f} cr/step. Call repay(loan_id={loan['loan_id']}) "
                    "immediately. You cannot receive new credit until this is repaid."
                )
            else:
                entry["steps_overdue"] = 0
                entry["current_repayment_due"] = round(
                    loan["amount"] * (1 + loan["interest_rate"]), 4
                )
            loans.append(entry)
        return loans

    # ── Loan applications (borrower side) ───────────────────────────────────

    async def request_loan(self, agent_id: int, message) -> dict:
        """File a loan application with a bank. No funds move until the bank
        approves it (next step); nothing is escrowed.

        message: (lender_id: int, amount: float, proposed_rate: float | None)
        """
        if isinstance(message, (list, tuple)):
            lender_id = message[0]
            amount = message[1]
            proposed_rate = message[2] if len(message) > 2 else None
        else:  # tolerate a bare lender_id (no amount) defensively
            return {"success": False, "error": "request_loan needs (lender_id, amount)."}
        lender_id = int(lender_id)
        amount = float(amount)
        proposed_rate = None if proposed_rate is None else float(proposed_rate)
        ts = self.ctx.clock.now()

        if amount <= 0:
            return {"success": False, "error": "amount must be positive."}

        lender = self.ctx.execute(
            "SELECT agent_type FROM agent WHERE agent_id = ?", (lender_id,)
        ).fetchone()
        if lender is None:
            return {"success": False, "error": f"lender_id {lender_id} not found"}
        if lender["agent_type"] != "bank":
            return {"success": False,
                    "error": f"agent {lender_id} is not a bank; loans are bank-only."}

        overdue = self._overdue_loan(agent_id, ts)
        if overdue:
            return {
                "success": False,
                "error": (
                    f"You have an overdue loan (loan_id={overdue['loan_id']}, "
                    f"due step {overdue['due_at']}). Repay it before applying for "
                    "new credit."
                ),
            }

        # One outstanding application per borrower→lender pair at a time.
        existing = self.ctx.execute(
            "SELECT request_id FROM loan_request "
            "WHERE borrower_id = ? AND lender_id = ? AND status = 'pending'",
            (agent_id, lender_id),
        ).fetchone()
        if existing:
            return {
                "success": False,
                "error": (
                    f"You already have a pending request (request_id="
                    f"{existing['request_id']}) with this bank. Wait for a decision."
                ),
            }

        cursor = self.ctx.execute(
            "INSERT INTO loan_request "
            "(borrower_id, lender_id, amount, proposed_rate, status, requested_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (agent_id, lender_id, amount, proposed_rate, ts),
            commit=True,
        )
        request_id = cursor.lastrowid
        self.ctx.record_trace(agent_id, ActionType.REQUEST_LOAN.value,
                              {"lender_id": lender_id, "amount": amount,
                               "proposed_rate": proposed_rate, "request_id": request_id})
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "request_loan",
            "amount": amount,
            "to_agent": self.ctx.agent_name(lender_id),
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": (
                f"Applied to borrow ${amount:.2f} from "
                f"{self.ctx.agent_name(lender_id)}"
            ),
        })
        return {"success": True, "request_id": request_id, "amount": amount,
                "lender_id": lender_id, "proposed_rate": proposed_rate,
                "note": "Application queued; the bank decides next step."}

    # ── Adjudication (bank side) ────────────────────────────────────────────

    def _pending_request(self, request_id: int, lender_id: int) -> dict | None:
        row = self.ctx.execute(
            "SELECT * FROM loan_request "
            "WHERE request_id = ? AND lender_id = ? AND status = 'pending'",
            (request_id, lender_id),
        ).fetchone()
        return dict(row) if row else None

    async def approve_loan(self, agent_id: int, message) -> dict:
        """Approve a pending loan request. The bank sets the per-loan rate and
        may approve a smaller amount than requested.

        message: (request_id: int, rate: float | None, approved_amount: float | None)
        rate=None falls back to the borrower's proposed_rate, then the scenario
        reference rate; it is always clamped to [min_interest_rate, max_interest_rate].
        approved_amount=None approves the full requested amount.
        """
        if isinstance(message, (list, tuple)):
            request_id = int(message[0])
            rate = message[1] if len(message) > 1 else None
            approved_amount = message[2] if len(message) > 2 else None
        else:
            request_id, rate, approved_amount = int(message), None, None
        ts = self.ctx.clock.now()

        req = self._pending_request(request_id, agent_id)
        if req is None:
            return {"success": False,
                    "error": f"request_id {request_id} not found, already decided, "
                             "or not addressed to you."}
        borrower_id = int(req["borrower_id"])
        requested = float(req["amount"])

        # Amount: default to requested, never exceed it.
        approved_amount = requested if approved_amount is None else float(approved_amount)
        if approved_amount <= 0:
            return {"success": False, "error": "approved_amount must be positive."}
        approved_amount = round(min(approved_amount, requested), 4)

        # Rate: borrower's proposal → bank override → reference; clamped to band.
        if rate is None:
            rate = req["proposed_rate"] if req["proposed_rate"] is not None else self.ctx.interest_rate
        rate = round(min(max(float(rate), self.ctx.min_interest_rate),
                         self.ctx.max_interest_rate), 4)

        # Hard invariant 1: a borrower who went overdue since applying is auto-denied.
        overdue = self._overdue_loan(borrower_id, ts)
        if overdue:
            reason = (f"borrower has an overdue loan (loan_id={overdue['loan_id']}) "
                      "and is not eligible for new credit")
            await self._mark_denied(req, reason, ts)
            return {"success": False, "request_id": request_id,
                    "error": f"Auto-denied: {reason}.", "status": "denied"}

        # Hard invariant 2: the bank cannot lend money it does not have.
        bank_balance = self.ledger.balance(agent_id)
        if bank_balance < approved_amount:
            return {"success": False, "request_id": request_id,
                    "error": (f"Insufficient balance to fund {approved_amount:.2f} "
                              f"(you hold {bank_balance:.2f}). Approve a smaller amount.")}

        due_at = ts + self.ctx.loan_duration_steps
        self.ledger.debit(agent_id, approved_amount)
        self.ledger.credit(borrower_id, approved_amount)
        cursor = self.ctx.execute(
            "INSERT INTO loan "
            "(lender_id, borrower_id, amount, interest_rate, borrowed_at, due_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, borrower_id, approved_amount, rate, ts, due_at),
            commit=True,
        )
        loan_id = cursor.lastrowid
        self.ctx.execute(
            "UPDATE loan_request SET status = 'approved', approved_amount = ?, "
            "approved_rate = ?, loan_id = ?, decided_at = ? WHERE request_id = ?",
            (approved_amount, rate, loan_id, ts, request_id),
            commit=True,
        )
        self.ledger.record(
            borrower_id, "loan_received", approved_amount,
            f"Loan #{loan_id} approved: {approved_amount:.2f} from agent {agent_id} "
            f"@ {rate*100:.1f}% (due step {due_at})",
        )
        self.ledger.record(
            agent_id, "loan_issued", -approved_amount,
            f"Issued loan #{loan_id}: {approved_amount:.2f} to agent {borrower_id} "
            f"@ {rate*100:.1f}%",
        )
        self.ctx.record_trace(agent_id, ActionType.APPROVE_LOAN.value,
                              {"request_id": request_id, "borrower_id": borrower_id,
                               "approved_amount": approved_amount, "rate": rate,
                               "loan_id": loan_id, "due_at": due_at})
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "approve_loan",
            "amount": approved_amount,
            "to_agent": self.ctx.agent_name(borrower_id),
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": (
                f"Approved ${approved_amount:.2f} for "
                f"{self.ctx.agent_name(borrower_id)} @ {rate*100:.1f}%"
            ),
        })
        return {"success": True, "request_id": request_id, "loan_id": loan_id,
                "borrower_id": borrower_id, "approved_amount": approved_amount,
                "interest_rate": rate, "due_at": due_at,
                "partial": approved_amount < requested}

    async def deny_loan(self, agent_id: int, message) -> dict:
        """Deny a pending loan request.

        message: (request_id: int, reason: str)
        """
        if isinstance(message, (list, tuple)):
            request_id = int(message[0])
            reason = str(message[1]) if len(message) > 1 and message[1] else "no reason given"
        else:
            request_id, reason = int(message), "no reason given"
        ts = self.ctx.clock.now()

        req = self._pending_request(request_id, agent_id)
        if req is None:
            return {"success": False,
                    "error": f"request_id {request_id} not found, already decided, "
                             "or not addressed to you."}
        await self._mark_denied(req, reason, ts)
        return {"success": True, "request_id": request_id, "status": "denied",
                "reason": reason}

    async def _mark_denied(self, req: dict, reason: str, ts: int) -> None:
        self.ctx.execute(
            "UPDATE loan_request SET status = 'denied', reason = ?, decided_at = ? "
            "WHERE request_id = ?",
            (reason, ts, req["request_id"]),
            commit=True,
        )
        self.ctx.record_trace(int(req["lender_id"]), ActionType.DENY_LOAN.value,
                              {"request_id": req["request_id"],
                               "borrower_id": req["borrower_id"], "reason": reason})
        await self.ctx.emit({
            "type": "agent_action",
            "step": ts,
            "agent": self.ctx.agent_name(int(req["lender_id"])),
            "agent_id": int(req["lender_id"]),
            "action": "deny_loan",
            "to_agent": self.ctx.agent_name(int(req["borrower_id"])),
            "balance": round(self.ledger.balance(int(req["lender_id"])), 2),
            "summary": (
                f"Denied {self.ctx.agent_name(int(req['borrower_id']))}'s "
                f"${float(req['amount']):.2f} request: {reason}"
            ),
        })

    # ── Lifecycle upkeep ────────────────────────────────────────────────────

    def expire_stale_requests(self, step: int, max_steps: int) -> None:
        """Auto-expire pending requests the bank left undecided for too long."""
        if max_steps <= 0:
            return
        self.ctx.execute(
            "UPDATE loan_request SET status = 'expired', "
            "reason = 'no decision within the review window', decided_at = ? "
            "WHERE status = 'pending' AND (? - requested_at) >= ?",
            (step, step, max_steps),
            commit=True,
        )

    # ── Bank's loan desk (read) ─────────────────────────────────────────────

    def pending_requests_for_lender(self, lender_id: int, step: int) -> list[dict]:
        """Pending applications addressed to this bank, each with an applicant
        dossier so the bank can judge credit risk in one observation.
        """
        rows = self.ctx.execute(
            "SELECT request_id, borrower_id, amount, proposed_rate, requested_at "
            "FROM loan_request WHERE lender_id = ? AND status = 'pending' "
            "ORDER BY requested_at, request_id",
            (lender_id,),
        ).fetchall()
        bank_balance = self.ledger.balance(lender_id)
        requests: list[dict] = []
        for row in rows:
            borrower_id = int(row["borrower_id"])
            requests.append({
                "request_id": row["request_id"],
                "borrower_id": borrower_id,
                "borrower": self.ctx.agent_name(borrower_id),
                "amount": round(float(row["amount"]), 4),
                "proposed_rate": row["proposed_rate"],
                "steps_waiting": max(0, step - int(row["requested_at"])),
                "fraction_of_your_capital": (
                    round(float(row["amount"]) / bank_balance, 4)
                    if bank_balance > 0 else None
                ),
                "soft_cap_fraction": self.ctx.max_borrow_fraction,
                "applicant": self._applicant_dossier(borrower_id, step),
            })
        return requests

    def _applicant_dossier(self, borrower_id: int, step: int) -> dict:
        agent = self.ctx.execute(
            "SELECT name, agent_type, sector, region, balance "
            "FROM agent WHERE agent_id = ?",
            (borrower_id,),
        ).fetchone()
        if agent is None:
            return {"agent_id": borrower_id, "error": "unknown agent"}

        inv = self.ctx.execute(
            "SELECT COALESCE(SUM(quantity * unit_cost), 0) AS inv_value "
            "FROM good WHERE producer_id = ? AND quantity > 0",
            (borrower_id,),
        ).fetchone()

        loan_stats = self.ctx.execute(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN repaid = 0 THEN amount * (1 + interest_rate) END), 0) AS outstanding, "
            "  SUM(CASE WHEN repaid = 1 THEN 1 ELSE 0 END) AS loans_repaid, "
            "  SUM(CASE WHEN repaid = 0 AND due_at < ? THEN 1 ELSE 0 END) AS overdue_count "
            "FROM loan WHERE borrower_id = ?",
            (step, borrower_id),
        ).fetchone()

        return {
            "agent_id": borrower_id,
            "sector": agent["sector"],
            "region": agent["region"],
            "balance": round(float(agent["balance"]), 2),
            "inventory_value": round(float(inv["inv_value"]), 2),
            "outstanding_debt": round(float(loan_stats["outstanding"]), 2),
            "loans_repaid": int(loan_stats["loans_repaid"] or 0),
            "overdue_loans": int(loan_stats["overdue_count"] or 0),
        }

    async def repay(self, agent_id: int, message) -> dict:
        """Repay an outstanding loan (principal + accrued interest).

        message: loan_id (int)
        """
        loan_id = int(message)

        loan = self.ctx.execute(
            "SELECT * FROM loan WHERE loan_id = ? AND borrower_id = ? AND repaid = 0",
            (loan_id, agent_id)
        ).fetchone()
        if loan is None:
            return {"success": False,
                    "error": f"loan_id {loan_id} not found or already repaid"}

        steps_overdue = max(0, self.ctx.clock.now() - loan["due_at"])
        repayment = round(
            loan["amount"] * (1 + loan["interest_rate"]) +
            steps_overdue * loan["amount"] * loan["interest_rate"] * 0.1,
            4,
        )

        if not self.ledger.debit(agent_id, repayment):
            return {"success": False,
                    "error": f"Insufficient balance to repay {repayment:.2f}"}

        self.ledger.credit(loan["lender_id"], repayment)
        self.ctx.execute(
            "UPDATE loan SET repaid = 1 WHERE loan_id = ?",
            (loan_id,), commit=True,
        )
        self.ledger.record(
            agent_id, "loan_repaid", -repayment,
            f"Repaid loan #{loan_id}: {repayment:.2f} to agent {loan['lender_id']}",
        )
        self.ledger.record(
            loan["lender_id"], "loan_repayment_received", repayment,
            f"Received repayment of loan #{loan_id}: {repayment:.2f} from agent {agent_id}",
        )
        self.ctx.record_trace(agent_id, ActionType.REPAY.value,
                              {"loan_id": loan_id, "amount_repaid": repayment,
                               "lender_id": loan["lender_id"]})
        await self.ctx.emit({
            "type": "agent_action",
            "step": self.ctx.clock.now(),
            "agent": self.ctx.agent_name(agent_id),
            "agent_id": agent_id,
            "action": "repay",
            "amount": repayment,
            "to_agent": self.ctx.agent_name(loan["lender_id"]),
            "balance": round(self.ledger.balance(agent_id), 2),
            "summary": (
                f"Repaid loan #{loan_id}: {repayment:.2f} "
                f"to {self.ctx.agent_name(loan['lender_id'])}"
            ),
        })
        return {"success": True, "loan_id": loan_id,
                "amount_repaid": repayment, "lender_id": loan["lender_id"]}

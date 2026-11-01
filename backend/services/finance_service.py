"""
backend/services/finance_service.py
=====================================
Core financial business logic services for Student Finance Management.

Services
--------
InvoiceService          — Invoice creation, lifecycle management
ScholarshipService      — Eligibility evaluation & award recording
PaymentService          — Payment recording & allocation
BalanceService          — Student balance calculations
AuditService            — Audit event recording
FinanceValidationService — Business-rule validation
FinanceReadService      — Read-only query helpers for API layer

Design principles
-----------------
* All monetary values are integer paise throughout.
* Outstanding balance is always DERIVED, never stored.
* No financial record is ever deleted — statuses and audit events only.
* Cross-student allocation is guarded before every PaymentAllocation INSERT.
* All services accept an open sqlite3.Connection; callers manage transactions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.services.finance_policy import FinancePolicy, ScholarshipRule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Transfer Objects (lightweight — not Pydantic, no HTTP concerns)
# ---------------------------------------------------------------------------


@dataclass
class StudentBalance:
    """Calculated financial position for one student (optionally per term)."""
    student_id: int
    term_id: Optional[int]
    total_invoiced_paise: int = 0
    total_scholarship_credit_paise: int = 0
    total_paid_paise: int = 0
    total_refunded_paise: int = 0
    overdue_paise: int = 0
    outstanding_paise: int = 0
    overpayment_paise: int = 0

    @property
    def net_payable_paise(self) -> int:
        """Invoiced minus scholarship credits."""
        return max(0, self.total_invoiced_paise - self.total_scholarship_credit_paise)


@dataclass
class ValidationResult:
    valid: bool
    violations: List[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.violations.append(msg)
        self.valid = False


def processed_refunds_by_student_term(
    conn: sqlite3.Connection,
    student_ids: Optional[List[int]] = None,
) -> Dict[Tuple[int, int], int]:
    """Allocate processed refunds across a payment's invoice terms by paid share."""
    if student_ids is not None and not student_ids:
        return {}

    filter_sql = ""
    params: List[int] = []
    if student_ids is not None:
        placeholders = ",".join("?" for _ in student_ids)
        filter_sql = f"AND p.student_id IN ({placeholders})"
        params.extend(student_ids)

    refunds = conn.execute(
        f"""SELECT r.refund_id, r.payment_id, r.refund_amount_paise, p.student_id
            FROM Refunds r
            JOIN Payments p ON p.payment_id = r.payment_id
            WHERE r.status = 'processed' {filter_sql}
            ORDER BY r.refund_id""",
        params,
    ).fetchall()
    if not refunds:
        return {}

    payment_ids = sorted({row["payment_id"] for row in refunds})
    placeholders = ",".join("?" for _ in payment_ids)
    weights = conn.execute(
        f"""SELECT pa.payment_id, i.term_id,
                   SUM(pa.allocated_amount_paise) AS allocated_paise
            FROM PaymentAllocations pa
            JOIN Payments p ON p.payment_id = pa.payment_id
            JOIN InvoiceLines il ON il.line_id = pa.line_id
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
            WHERE pa.payment_id IN ({placeholders})
              AND p.status IN ('cleared', 'refunded')
              AND p.student_id = en.student_id
            GROUP BY pa.payment_id, i.term_id""",
        payment_ids,
    ).fetchall()
    terms_by_payment: Dict[int, List[Tuple[int, int]]] = {}
    for row in weights:
        terms_by_payment.setdefault(row["payment_id"], []).append(
            (row["term_id"], row["allocated_paise"])
        )

    totals: Dict[Tuple[int, int], int] = {}
    for refund in refunds:
        term_weights = terms_by_payment.get(refund["payment_id"], [])
        weight_total = sum(weight for _, weight in term_weights)
        if weight_total <= 0:
            continue

        amount = refund["refund_amount_paise"]
        shares = [
            (term_id, amount * weight // weight_total, amount * weight % weight_total)
            for term_id, weight in term_weights
        ]
        remainder = amount - sum(share for _, share, _ in shares)
        remainder_order = sorted(shares, key=lambda item: (-item[2], item[0]))
        extra_terms = {term_id for term_id, _, _ in remainder_order[:remainder]}
        for term_id, share, _ in shares:
            if term_id in extra_terms:
                share += 1
            key = (refund["student_id"], term_id)
            totals[key] = totals.get(key, 0) + share
    return totals


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------


class AuditService:
    """
    Appends records to the AuditEvents table.

    All writes are INSERT-only; no row is ever updated or deleted.
    """

    @staticmethod
    def log(
        conn: sqlite3.Connection,
        entity_type: str,
        entity_id: int,
        event_type: str,
        field_changed: Optional[str] = None,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        performed_by: str = "system",
        performed_at: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Insert an audit event and return its audit_id.

        Parameters
        ----------
        entity_type : str   e.g. "Invoice", "Payment"
        entity_id   : int   Primary key of the entity
        event_type  : str   e.g. "CREATE", "STATUS_CHANGE"
        performed_at: str | None  ISO datetime; uses DB default if None
        """
        old_json = json.dumps(old_value) if old_value is not None else None
        new_json = json.dumps(new_value) if new_value is not None else None

        sql = """
            INSERT INTO AuditEvents
                (entity_type, entity_id, event_type, field_changed,
                 old_value, new_value, performed_by, performed_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        ts = performed_at or _now_iso()
        cur = conn.execute(sql, (
            entity_type, entity_id, event_type, field_changed,
            old_json, new_json, performed_by, ts, notes,
        ))
        return cur.lastrowid


# ---------------------------------------------------------------------------
# InvoiceService
# ---------------------------------------------------------------------------


class InvoiceService:
    """
    Creates and manages Invoices and InvoiceLines.

    Invoice number format: INV-STU-{student_id:06d}-{year}-{seq:06d}
    """

    def __init__(self, policy: Optional[FinancePolicy] = None) -> None:
        self._policy = policy or FinancePolicy()

    def create_invoice(
        self,
        conn: sqlite3.Connection,
        enrollment_id: int,
        term_id: int,
        issue_date: str,
        seq: int,
        status: str = "issued",
        notes: Optional[str] = None,
    ) -> int:
        """
        Create an Invoice for a given enrollment + term.

        Parameters
        ----------
        seq : int   Global sequence number for the invoice number.

        Returns
        -------
        invoice_id : int
        """
        # Resolve student_id from enrollment
        row = conn.execute(
            """SELECT e.student_id, e.fee_schedule_id
               FROM Enrollments e WHERE e.enrollment_id = ?""",
            (enrollment_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"enrollment_id={enrollment_id} not found")

        student_id = row["student_id"]
        year = date.fromisoformat(issue_date).year
        inv_number = f"INV-STU-{student_id:06d}-{year}-{seq:06d}"

        # Check for duplicate invoice_number (safe rerun)
        existing = conn.execute(
            "SELECT invoice_id FROM Invoices WHERE invoice_number = ?",
            (inv_number,),
        ).fetchone()
        if existing:
            return existing["invoice_id"]

        # Check no existing non-cancelled invoice for same enrollment+term
        dup = conn.execute(
            """SELECT invoice_id FROM Invoices
               WHERE enrollment_id = ? AND term_id = ?
               AND status NOT IN ('cancelled', 'refunded')""",
            (enrollment_id, term_id),
        ).fetchone()
        if dup:
            return dup["invoice_id"]

        due_date = self._policy.calculate_due_date(issue_date)

        cur = conn.execute(
            """INSERT INTO Invoices
                   (invoice_number, enrollment_id, term_id, issue_date, due_date, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (inv_number, enrollment_id, term_id, issue_date, due_date, status, notes),
        )
        invoice_id = cur.lastrowid
        AuditService.log(conn, "Invoice", invoice_id, "CREATE",
                         new_value={"invoice_number": inv_number, "status": status})
        return invoice_id

    def add_fee_lines_from_schedule(
        self,
        conn: sqlite3.Connection,
        invoice_id: int,
        fee_schedule_id: int,
    ) -> int:
        """
        Copy FeeScheduleLines for *fee_schedule_id* into InvoiceLines.

        Returns
        -------
        int : number of lines added
        """
        # Check not already populated
        existing = conn.execute(
            "SELECT COUNT(*) FROM InvoiceLines WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()[0]
        if existing > 0:
            return 0

        lines = conn.execute(
            """SELECT fsl_id, fee_type, description, amount_paise
               FROM FeeScheduleLines
               WHERE schedule_id = ?
               ORDER BY sort_order, fsl_id""",
            (fee_schedule_id,),
        ).fetchall()

        count = 0
        for fsl in lines:
            conn.execute(
                """INSERT INTO InvoiceLines
                       (invoice_id, fee_type, description, amount_paise,
                        is_scholarship_credit, fsl_id)
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (invoice_id, fsl["fee_type"], fsl["description"],
                 fsl["amount_paise"], fsl["fsl_id"]),
            )
            count += 1

        return count

    def add_scholarship_credit_line(
        self,
        conn: sqlite3.Connection,
        invoice_id: int,
        scholarship_name: str,
        credit_amount_paise: int,
    ) -> int:
        """
        Add a negative credit line to the invoice for a scholarship award.

        Returns
        -------
        line_id : int
        """
        cur = conn.execute(
            """INSERT INTO InvoiceLines
                   (invoice_id, fee_type, description, amount_paise, is_scholarship_credit)
               VALUES (?, 'Scholarship Credit', ?, ?, 1)""",
            (invoice_id, f"Scholarship: {scholarship_name}", -abs(credit_amount_paise)),
        )
        return cur.lastrowid

    def update_status(
        self,
        conn: sqlite3.Connection,
        invoice_id: int,
        new_status: str,
    ) -> None:
        """Update invoice status and log the change."""
        old = conn.execute(
            "SELECT status FROM Invoices WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()
        if old is None:
            raise ValueError(f"invoice_id={invoice_id} not found")
        conn.execute(
            "UPDATE Invoices SET status = ?, updated_at = ? WHERE invoice_id = ?",
            (new_status, _now_iso(), invoice_id),
        )
        AuditService.log(conn, "Invoice", invoice_id, "STATUS_CHANGE",
                         field_changed="status",
                         old_value=old["status"], new_value=new_status)

    def refresh_status(
        self,
        conn: sqlite3.Connection,
        invoice_id: int,
        reference_date: Optional[str] = None,
    ) -> str:
        """
        Recalculate and update invoice status based on payment allocations.

        Returns the new status string.
        """
        ref_date = reference_date or date.today().isoformat()

        # Invoice total (sum of lines, excluding scholarship credits for this check)
        totals = conn.execute(
            """SELECT
                   SUM(CASE WHEN amount_paise > 0 THEN amount_paise ELSE 0 END) AS gross,
                   SUM(CASE WHEN amount_paise < 0 THEN ABS(amount_paise) ELSE 0 END) AS credits
               FROM InvoiceLines WHERE invoice_id = ?""",
            (invoice_id,),
        ).fetchone()
        gross = totals["gross"] or 0
        credits = totals["credits"] or 0
        net_due = max(0, gross - credits)

        # Total cleared allocations
        paid = conn.execute(
            """SELECT COALESCE(SUM(pa.allocated_amount_paise), 0) AS paid
               FROM PaymentAllocations pa
               JOIN InvoiceLines il ON il.line_id = pa.line_id
               JOIN Payments p ON p.payment_id = pa.payment_id
               WHERE il.invoice_id = ? AND p.status = 'cleared'""",
            (invoice_id,),
        ).fetchone()["paid"]

        current = conn.execute(
            "SELECT status, due_date FROM Invoices WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()
        if current is None:
            return "unknown"
        if current["status"] in ("cancelled", "refunded"):
            return current["status"]

        if net_due == 0:
            new_status = "paid"
        elif paid >= net_due:
            new_status = "paid"
        elif paid > 0:
            new_status = "partially_paid"
        elif ref_date > current["due_date"]:
            new_status = "overdue"
        else:
            new_status = "issued"

        if new_status != current["status"]:
            self.update_status(conn, invoice_id, new_status)
        return new_status

    def cancel_invoice(
        self,
        conn: sqlite3.Connection,
        invoice_id: int,
        reason: str = "cancelled",
    ) -> None:
        """Cancel an invoice. Cannot cancel if there are cleared allocations."""
        allocated = conn.execute(
            """SELECT COALESCE(SUM(pa.allocated_amount_paise), 0) AS paid
               FROM PaymentAllocations pa
               JOIN InvoiceLines il ON il.line_id = pa.line_id
               JOIN Payments p ON p.payment_id = pa.payment_id
               WHERE il.invoice_id = ? AND p.status = 'cleared'""",
            (invoice_id,),
        ).fetchone()["paid"]
        if allocated > 0:
            raise ValueError(
                f"Cannot cancel invoice_id={invoice_id}: "
                f"{allocated} paise already cleared."
            )
        self.update_status(conn, invoice_id, "cancelled")
        AuditService.log(conn, "Invoice", invoice_id, "CANCELLED", notes=reason)


# ---------------------------------------------------------------------------
# ScholarshipService
# ---------------------------------------------------------------------------


class ScholarshipService:
    """
    Evaluates scholarship eligibility and records awards in the Eligibility table.
    """

    def __init__(self, policy: Optional[FinancePolicy] = None) -> None:
        self._policy = policy or FinancePolicy()

    def ensure_scholarship_catalogue(self, conn: sqlite3.Connection) -> Dict[str, int]:
        """
        Insert scholarship master records (from policy rules) if not present.

        Returns
        -------
        dict: scholarship_code → scholarship_id
        """
        code_to_id: Dict[str, int] = {}
        for rule in self._policy.scholarship_rules:
            existing = conn.execute(
                "SELECT scholarship_id FROM Scholarships WHERE scholarship_code = ?",
                (rule.code,),
            ).fetchone()
            if existing:
                code_to_id[rule.code] = existing["scholarship_id"]
                continue
            cur = conn.execute(
                """INSERT INTO Scholarships
                       (scholarship_code, scholarship_name, description,
                        scholarship_type, max_amount_paise, percentage_discount,
                        is_renewable, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                (rule.code, rule.name, rule.description, rule.scholarship_type,
                 rule.max_amount_paise, rule.percentage_discount,
                 1 if rule.is_renewable else 0),
            )
            code_to_id[rule.code] = cur.lastrowid
        return code_to_id

    def evaluate_eligibility(
        self,
        student: Dict[str, Any],
        enrollment: Dict[str, Any],
        program: Dict[str, Any],
        term: Dict[str, Any],
        academic_score: int,          # 0–100 synthetic score
        extracurricular_score: int,   # 0–100 synthetic score
        metro_cities: Optional[set] = None,
    ) -> List[Tuple[ScholarshipRule, int]]:
        """
        Evaluate which scholarship rules this student qualifies for.

        Returns
        -------
        List of (rule, eligible_fee_amount_paise) tuples.
        eligible_fee_amount_paise is the sum of applicable fee types from
        the enrollment's fee schedule.
        """
        results = []
        city = (student.get("city") or "").lower()
        if metro_cities is None:
            metro_cities = {"mumbai", "delhi", "bengaluru", "hyderabad",
                            "chennai", "kolkata", "pune", "ahmedabad"}
        dob_str = student.get("date_of_birth", "1990-01-01")
        ref = date.fromisoformat(term.get("start_date", "2024-01-01"))
        try:
            age = (ref - date.fromisoformat(dob_str)).days // 365
        except Exception:
            age = 20
        gender = student.get("gender", "O")
        level = program.get("level", "UG")
        dept = program.get("department", "")
        year_of_study = enrollment.get("year_of_study", 1)

        for rule in self._policy.scholarship_rules:
            # Level filter
            if rule.allowed_program_levels and level not in rule.allowed_program_levels:
                continue
            # Department filter
            if rule.allowed_departments and dept not in rule.allowed_departments:
                continue
            # Gender filter
            if rule.allowed_genders and gender not in rule.allowed_genders:
                continue
            # Age filters
            if rule.min_age is not None and age < rule.min_age:
                continue
            if rule.max_age is not None and age > rule.max_age:
                continue
            # Year of study filters
            if rule.min_year_of_study is not None and year_of_study < rule.min_year_of_study:
                continue
            if rule.max_year_of_study is not None and year_of_study > rule.max_year_of_study:
                continue
            # Score filter (use academic for merit/govt, extracurricular for sports)
            required_score = rule.min_score or 0
            score = extracurricular_score if rule.scholarship_type == "Sports" else academic_score
            if score < required_score:
                continue
            # Need-based: must be from non-metro
            if rule.scholarship_type == "Need-based" and city in metro_cities:
                continue

            # Calculate eligible fee amount from fee schedule lines
            eligible_fee = enrollment.get("_eligible_fee_by_type", {})
            applicable_amount = sum(
                eligible_fee.get(ft, 0) for ft in rule.applicable_fee_types
            )
            if applicable_amount <= 0:
                continue

            award = self._policy.calculate_award_amount(rule, applicable_amount)
            if award > 0:
                results.append((rule, award))

        return results

    def award_scholarship(
        self,
        conn: sqlite3.Connection,
        student_id: int,
        scholarship_id: int,
        term_id: int,
        enrollment_id: int,
        awarded_amount_paise: int,
        applied_date: str,
        status: str = "approved",
    ) -> Optional[int]:
        """
        Insert an Eligibility record (scholarship award).

        Returns eligibility_id or None if already exists (idempotent).
        """
        existing = conn.execute(
            """SELECT eligibility_id FROM Eligibility
               WHERE student_id = ? AND scholarship_id = ? AND term_id = ?""",
            (student_id, scholarship_id, term_id),
        ).fetchone()
        if existing:
            return None

        approved_date = applied_date if status in ("approved", "disbursed") else None
        disbursed_date = applied_date if status == "disbursed" else None

        cur = conn.execute(
            """INSERT INTO Eligibility
                   (student_id, scholarship_id, term_id, enrollment_id,
                    awarded_amount_paise, status, applied_date,
                    approved_date, disbursed_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (student_id, scholarship_id, term_id, enrollment_id,
             awarded_amount_paise, status, applied_date,
             approved_date, disbursed_date),
        )
        elig_id = cur.lastrowid
        AuditService.log(conn, "Eligibility", elig_id, "CREATE",
                         new_value={"awarded_amount_paise": awarded_amount_paise,
                                    "status": status})
        return elig_id


# ---------------------------------------------------------------------------
# PaymentService
# ---------------------------------------------------------------------------


class PaymentService:
    """Records payments and manages payment allocations."""

    def record_payment(
        self,
        conn: sqlite3.Connection,
        student_id: int,
        payment_reference: str,
        payment_date: str,
        amount_paise: int,
        payment_method: str,
        status: str = "cleared",
        transaction_id: Optional[str] = None,
        bank_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Insert a Payment record.

        Returns
        -------
        payment_id : int
        """
        if amount_paise <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        existing = conn.execute(
            "SELECT payment_id FROM Payments WHERE payment_reference = ?",
            (payment_reference,),
        ).fetchone()
        if existing:
            return existing["payment_id"]

        cur = conn.execute(
            """INSERT INTO Payments
                   (payment_reference, student_id, payment_date, amount_paise,
                    payment_method, status, transaction_id, bank_name, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payment_reference, student_id, payment_date, amount_paise,
             payment_method, status, transaction_id, bank_name, notes),
        )
        payment_id = cur.lastrowid
        AuditService.log(conn, "Payment", payment_id, "CREATE",
                         new_value={"amount_paise": amount_paise, "status": status})
        return payment_id

    def allocate_payment(
        self,
        conn: sqlite3.Connection,
        payment_id: int,
        line_id: int,
        allocated_amount_paise: int,
        db_manager=None,
    ) -> Optional[int]:
        """
        Allocate part of a payment to an InvoiceLine.

        Validates:
        - Payment and line belong to same student
        - Allocated amount ≤ remaining unallocated payment
        - Allocated amount ≤ remaining unpaid invoice line
        - Payment status is 'cleared'

        Returns
        -------
        allocation_id or None if already exists.
        """
        if allocated_amount_paise <= 0:
            raise ValueError("Allocation amount must be greater than zero.")

        # Already allocated?
        existing = conn.execute(
            "SELECT allocation_id FROM PaymentAllocations WHERE payment_id=? AND line_id=?",
            (payment_id, line_id),
        ).fetchone()
        if existing:
            return None

        # Cross-student guard
        if db_manager:
            db_manager.validate_allocation(conn, payment_id, line_id)
        else:
            self._validate_same_student(conn, payment_id, line_id)

        # Payment must be cleared
        pay = conn.execute(
            "SELECT amount_paise, status FROM Payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if pay is None:
            raise ValueError(f"payment_id={payment_id} not found")
        if pay["status"] != "cleared":
            raise ValueError(
                f"Payment {payment_id} has status '{pay['status']}'; "
                "only 'cleared' payments can be allocated."
            )

        # Check remaining unallocated payment balance
        already_alloc = conn.execute(
            """SELECT COALESCE(SUM(allocated_amount_paise), 0)
               FROM PaymentAllocations WHERE payment_id = ?""",
            (payment_id,),
        ).fetchone()[0]
        remaining_pay = pay["amount_paise"] - already_alloc
        if allocated_amount_paise > remaining_pay:
            raise ValueError(
                f"Cannot allocate {allocated_amount_paise} paise from payment {payment_id}: "
                f"only {remaining_pay} paise remaining."
            )

        # Check remaining invoice line balance
        line = conn.execute(
            "SELECT amount_paise FROM InvoiceLines WHERE line_id = ?", (line_id,)
        ).fetchone()
        if line is None:
            raise ValueError(f"line_id={line_id} not found")
        line_amount = line["amount_paise"]
        if line_amount <= 0:
            raise ValueError(f"line_id={line_id} is a credit line (amount_paise={line_amount})")

        already_paid_on_line = conn.execute(
            """SELECT COALESCE(SUM(pa.allocated_amount_paise), 0)
               FROM PaymentAllocations pa
               JOIN Payments p ON p.payment_id = pa.payment_id
               WHERE pa.line_id = ? AND p.status = 'cleared'""",
            (line_id,),
        ).fetchone()[0]
        remaining_line = line_amount - already_paid_on_line
        if allocated_amount_paise > remaining_line:
            raise ValueError(
                f"Cannot allocate {allocated_amount_paise} paise to line {line_id}: "
                f"only {remaining_line} paise outstanding."
            )

        cur = conn.execute(
            """INSERT INTO PaymentAllocations (payment_id, line_id, allocated_amount_paise)
               VALUES (?, ?, ?)""",
            (payment_id, line_id, allocated_amount_paise),
        )
        allocation_id = cur.lastrowid
        AuditService.log(conn, "PaymentAllocation", allocation_id, "CREATE",
                         new_value={"payment_id": payment_id, "line_id": line_id,
                                    "allocated_amount_paise": allocated_amount_paise})
        return allocation_id

    def _validate_same_student(
        self, conn: sqlite3.Connection, payment_id: int, line_id: int
    ) -> None:
        row = conn.execute(
            """SELECT p.student_id AS pay_s,
                      e.student_id AS inv_s
               FROM Payments p,
                    InvoiceLines il
                    JOIN Invoices i ON i.invoice_id = il.invoice_id
                    JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
               WHERE p.payment_id = ? AND il.line_id = ?""",
            (payment_id, line_id),
        ).fetchone()
        if row and row["pay_s"] != row["inv_s"]:
            raise ValueError(
                f"Cross-student allocation: payment belongs to student {row['pay_s']} "
                f"but line belongs to student {row['inv_s']}"
            )

    def record_refund(
        self,
        conn: sqlite3.Connection,
        payment_id: int,
        refund_reference: str,
        refund_date: str,
        refund_amount_paise: int,
        reason: str,
        refund_method: str,
        status: str = "processed",
    ) -> int:
        """
        Record a refund against a payment.

        Validates that refund amount ≤ refundable balance of the payment.

        Returns
        -------
        refund_id : int
        """
        if refund_amount_paise <= 0:
            raise ValueError("Refund amount must be greater than zero.")

        existing = conn.execute(
            "SELECT refund_id FROM Refunds WHERE refund_reference = ?",
            (refund_reference,),
        ).fetchone()
        if existing:
            return existing["refund_id"]

        # Refundable = payment amount − already refunded
        pay = conn.execute(
            "SELECT amount_paise, status FROM Payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if pay is None:
            raise ValueError(f"payment_id={payment_id} not found")

        already_refunded = conn.execute(
            """SELECT COALESCE(SUM(refund_amount_paise), 0)
               FROM Refunds
               WHERE payment_id = ? AND status IN ('processed', 'pending')""",
            (payment_id,),
        ).fetchone()[0]
        refundable = pay["amount_paise"] - already_refunded
        if refund_amount_paise > refundable:
            raise ValueError(
                f"Refund of {refund_amount_paise} paise exceeds "
                f"refundable amount {refundable} paise for payment {payment_id}."
            )

        cur = conn.execute(
            """INSERT INTO Refunds
                   (refund_reference, payment_id, refund_date, refund_amount_paise,
                    reason, refund_method, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (refund_reference, payment_id, refund_date, refund_amount_paise,
             reason, refund_method, status),
        )
        refund_id = cur.lastrowid
        AuditService.log(conn, "Refund", refund_id, "CREATE",
                         new_value={"refund_amount_paise": refund_amount_paise,
                                    "status": status})
        return refund_id

    def reverse_payment(
        self,
        conn: sqlite3.Connection,
        payment_id: int,
        reason: str = "reversed",
    ) -> None:
        """Mark a payment as reversed. Cannot reverse if allocations exist."""
        alloc_count = conn.execute(
            "SELECT COUNT(*) FROM PaymentAllocations WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()[0]
        if alloc_count > 0:
            raise ValueError(
                f"Cannot reverse payment {payment_id}: "
                f"{alloc_count} allocation(s) exist."
            )
        conn.execute(
            "UPDATE Payments SET status = 'reversed', updated_at = ? WHERE payment_id = ?",
            (_now_iso(), payment_id),
        )
        AuditService.log(conn, "Payment", payment_id, "STATUS_CHANGE",
                         field_changed="status", old_value="cleared",
                         new_value="reversed", notes=reason)


# ---------------------------------------------------------------------------
# BalanceService
# ---------------------------------------------------------------------------


class BalanceService:
    """
    Derives student financial position from source records.

    All calculations use only committed, FK-valid database rows.
    No balance is ever stored — always derived on demand.
    """

    @staticmethod
    def get_student_balance(
        conn: sqlite3.Connection,
        student_id: int,
        term_id: Optional[int] = None,
        reference_date: Optional[str] = None,
    ) -> StudentBalance:
        """
        Calculate the financial position for *student_id*, optionally
        filtered to *term_id*.

        Calculation policy
        ------------------
        total_invoiced       = SUM(InvoiceLines.amount_paise) where amount > 0
                               for non-cancelled invoices
        scholarship_credits  = SUM(ABS(InvoiceLines.amount_paise))
                               where is_scholarship_credit = 1 and invoice not cancelled
        total_paid           = SUM(PaymentAllocations.allocated_amount_paise)
                               where Payment.status = 'cleared'
        total_refunded       = SUM(Refunds.refund_amount_paise)
                               where Refunds.status = 'processed'
        net_payable          = total_invoiced − scholarship_credits
        outstanding          = max(0, net_payable − total_paid + total_refunded)
        overpayment          = max(0, total_paid − total_refunded − net_payable)
        overdue              = outstanding on overdue invoices
        """
        ref_date = reference_date or date.today().isoformat()
        term_filter = "AND i.term_id = :term_id" if term_id else ""
        params: Dict[str, Any] = {
            "student_id": student_id,
            "term_id": term_id,
        }

        # 1. Total invoiced and scholarship credits
        fee_rows = conn.execute(
            f"""
            SELECT il.amount_paise, il.is_scholarship_credit
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
            WHERE e.student_id = :student_id
              AND i.status NOT IN ('cancelled', 'refunded')
              {term_filter}
            """,
            params,
        ).fetchall()

        total_invoiced = sum(r["amount_paise"] for r in fee_rows
                             if r["amount_paise"] > 0 and not r["is_scholarship_credit"])
        scholarship_credits = sum(abs(r["amount_paise"]) for r in fee_rows
                                  if r["is_scholarship_credit"])

        # 2. Total cleared payments allocated to this student's invoices
        paid_rows = conn.execute(
            f"""
            SELECT COALESCE(SUM(pa.allocated_amount_paise), 0) AS paid
            FROM PaymentAllocations pa
            JOIN InvoiceLines il ON il.line_id = pa.line_id
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
            JOIN Payments p ON p.payment_id = pa.payment_id
            WHERE e.student_id = :student_id
              AND p.status = 'cleared'
              AND i.status NOT IN ('cancelled', 'refunded')
              {term_filter}
            """,
            params,
        ).fetchone()
        total_paid = paid_rows["paid"] or 0

        # 3. Total processed refunds for student's cleared payments
        if term_id is None:
            refund_rows = conn.execute(
                """SELECT COALESCE(SUM(r.refund_amount_paise), 0)
                   FROM Refunds r
                   JOIN Payments p ON p.payment_id = r.payment_id
                   WHERE p.student_id = ? AND r.status = 'processed'""",
                (student_id,),
            ).fetchone()
            total_refunded = refund_rows[0] or 0
        else:
            total_refunded = processed_refunds_by_student_term(
                conn, [student_id]
            ).get((student_id, term_id), 0)

        # 4. Overdue amounts
        overdue_rows = conn.execute(
            f"""
            SELECT il.amount_paise,
                   il.is_scholarship_credit,
                   COALESCE(
                       (SELECT SUM(pa.allocated_amount_paise)
                        FROM PaymentAllocations pa
                        JOIN Payments p ON p.payment_id = pa.payment_id
                        WHERE pa.line_id = il.line_id AND p.status = 'cleared'),
                       0
                   ) AS line_paid
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
            WHERE e.student_id = :student_id
              AND i.status = 'overdue'
              {term_filter}
            """,
            params,
        ).fetchall()

        overdue_total = 0
        for r in overdue_rows:
            if r["amount_paise"] > 0 and not r["is_scholarship_credit"]:
                unpaid = max(0, r["amount_paise"] - r["line_paid"])
                overdue_total += unpaid

        # Derived
        net_payable = max(0, total_invoiced - scholarship_credits)
        outstanding = max(0, net_payable - total_paid + total_refunded)
        overpayment = max(0, total_paid - total_refunded - net_payable)

        return StudentBalance(
            student_id=student_id,
            term_id=term_id,
            total_invoiced_paise=total_invoiced,
            total_scholarship_credit_paise=scholarship_credits,
            total_paid_paise=total_paid,
            total_refunded_paise=total_refunded,
            overdue_paise=overdue_total,
            outstanding_paise=outstanding,
            overpayment_paise=overpayment,
        )


# ---------------------------------------------------------------------------
# FinanceValidationService
# ---------------------------------------------------------------------------


class FinanceValidationService:
    """
    Business-rule validation checks — run against the live DB.

    Returns ValidationResult with accumulated violations.
    Distinct from row-level DB constraints.
    """

    @staticmethod
    def validate_invoice_line_totals(
        conn: sqlite3.Connection, invoice_id: int
    ) -> ValidationResult:
        result = ValidationResult(valid=True)
        lines = conn.execute(
            "SELECT amount_paise FROM InvoiceLines WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchall()
        if not lines:
            result.add(f"Invoice {invoice_id} has no lines")
        return result

    @staticmethod
    def validate_payment_allocations(
        conn: sqlite3.Connection, student_id: int
    ) -> ValidationResult:
        result = ValidationResult(valid=True)

        # Over-allocation check: any payment allocated more than its amount?
        rows = conn.execute(
            """
            SELECT p.payment_id, p.amount_paise,
                   COALESCE(SUM(pa.allocated_amount_paise), 0) AS total_allocated
            FROM Payments p
            LEFT JOIN PaymentAllocations pa ON pa.payment_id = p.payment_id
            WHERE p.student_id = ? AND p.status = 'cleared'
            GROUP BY p.payment_id, p.amount_paise
            HAVING total_allocated > p.amount_paise
            """,
            (student_id,),
        ).fetchall()
        for r in rows:
            result.add(
                f"Payment {r['payment_id']}: allocated {r['total_allocated']} "
                f"> amount {r['amount_paise']}"
            )

        # Over-paid line check
        over_lines = conn.execute(
            """
            SELECT il.line_id, il.amount_paise,
                   COALESCE(SUM(pa.allocated_amount_paise), 0) AS total_allocated
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
            LEFT JOIN PaymentAllocations pa ON pa.line_id = il.line_id
            WHERE e.student_id = ? AND il.amount_paise > 0
            GROUP BY il.line_id, il.amount_paise
            HAVING total_allocated > il.amount_paise
            """,
            (student_id,),
        ).fetchall()
        for r in over_lines:
            result.add(
                f"InvoiceLine {r['line_id']}: allocated {r['total_allocated']} "
                f"> amount {r['amount_paise']}"
            )
        return result

    @staticmethod
    def validate_scholarship_awards(
        conn: sqlite3.Connection, student_id: int
    ) -> ValidationResult:
        result = ValidationResult(valid=True)
        rows = conn.execute(
            """SELECT e.eligibility_id, e.awarded_amount_paise, sc.max_amount_paise
               FROM Eligibility e
               JOIN Scholarships sc ON sc.scholarship_id = e.scholarship_id
               WHERE e.student_id = ?
                 AND e.status IN ('approved', 'disbursed')
                 AND sc.max_amount_paise IS NOT NULL""",
            (student_id,),
        ).fetchall()
        for r in rows:
            if r["awarded_amount_paise"] > r["max_amount_paise"]:
                result.add(
                    f"Eligibility {r['eligibility_id']}: awarded "
                    f"{r['awarded_amount_paise']} > max {r['max_amount_paise']}"
                )
        return result

    @staticmethod
    def validate_refund_limits(
        conn: sqlite3.Connection, student_id: int
    ) -> ValidationResult:
        result = ValidationResult(valid=True)
        rows = conn.execute(
            """
            SELECT p.payment_id, p.amount_paise,
                   COALESCE(SUM(r.refund_amount_paise), 0) AS total_refunded
            FROM Payments p
            LEFT JOIN Refunds r ON r.payment_id = p.payment_id
                AND r.status IN ('processed', 'pending')
            WHERE p.student_id = ?
            GROUP BY p.payment_id, p.amount_paise
            HAVING total_refunded > p.amount_paise
            """,
            (student_id,),
        ).fetchall()
        for r in rows:
            result.add(
                f"Payment {r['payment_id']}: refunded {r['total_refunded']} "
                f"> original {r['amount_paise']}"
            )
        return result

    @staticmethod
    def validate_fk_integrity(conn: sqlite3.Connection) -> ValidationResult:
        result = ValidationResult(valid=True)
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        for r in rows:
            result.add(f"FK violation: table={r[0]} rowid={r[1]} parent={r[2]}")
        return result

    @staticmethod
    def validate_no_duplicate_active_invoices(
        conn: sqlite3.Connection,
    ) -> ValidationResult:
        result = ValidationResult(valid=True)
        dups = conn.execute(
            """SELECT enrollment_id, term_id, COUNT(*) AS cnt
               FROM Invoices i
               WHERE status NOT IN ('cancelled', 'refunded')
                 AND (
                     NOT EXISTS (
                         SELECT 1 FROM InvoiceLines il
                         WHERE il.invoice_id = i.invoice_id
                     )
                     OR EXISTS (
                         SELECT 1 FROM InvoiceLines il
                         WHERE il.invoice_id = i.invoice_id
                           AND il.fee_type NOT IN (
                               'Hostel', 'Transport', 'Miscellaneous', 'Late Fee'
                           )
                     )
                 )
               GROUP BY enrollment_id, term_id
               HAVING cnt > 1"""
        ).fetchall()
        for d in dups:
            result.add(
                f"Duplicate active invoices for enrollment={d['enrollment_id']} "
                f"term={d['term_id']}: {d['cnt']} invoices"
            )
        return result


# ---------------------------------------------------------------------------
# FinanceReadService — read-only queries for the API layer
# ---------------------------------------------------------------------------


class FinanceReadService:
    """
    Read-only query helpers that return dicts suitable for Pydantic schemas.
    """

    @staticmethod
    def get_student(conn: sqlite3.Connection, student_id: int) -> Optional[Dict]:
        row = conn.execute(
            "SELECT * FROM Students WHERE student_id = ?", (student_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def list_students(
        conn: sqlite3.Connection,
        page: int = 1,
        page_size: int = 50,
        status: Optional[str] = None,
    ) -> Tuple[List[Dict], int]:
        offset = (page - 1) * page_size
        where = "WHERE status = ?" if status else ""
        params = [status] if status else []
        total = conn.execute(
            f"SELECT COUNT(*) FROM Students {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM Students {where} ORDER BY student_id LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        return [dict(r) for r in rows], total

    @staticmethod
    def list_programs(conn: sqlite3.Connection) -> List[Dict]:
        rows = conn.execute("SELECT * FROM Programs ORDER BY program_id").fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_student_enrollments(
        conn: sqlite3.Connection, student_id: int
    ) -> List[Dict]:
        rows = conn.execute(
            """SELECT e.*, p.program_name, p.program_code, p.level,
                      t.term_name, t.term_code
               FROM Enrollments e
               JOIN Programs p ON p.program_id = e.program_id
               JOIN Terms t ON t.term_id = e.term_id
               WHERE e.student_id = ?
               ORDER BY e.term_id""",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def list_student_invoices(
        conn: sqlite3.Connection,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        offset = (page - 1) * page_size
        total = conn.execute(
            """SELECT COUNT(*) FROM Invoices i
               JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
               WHERE e.student_id = ?""",
            (student_id,),
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT i.*, t.term_name
               FROM Invoices i
               JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
               JOIN Terms t ON t.term_id = i.term_id
               WHERE e.student_id = ?
               ORDER BY i.issue_date DESC
               LIMIT ? OFFSET ?""",
            (student_id, page_size, offset),
        ).fetchall()
        return [dict(r) for r in rows], total

    @staticmethod
    def get_invoice_with_lines(
        conn: sqlite3.Connection, invoice_id: int
    ) -> Optional[Dict]:
        inv = conn.execute(
            "SELECT * FROM Invoices WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()
        if not inv:
            return None
        lines = conn.execute(
            "SELECT * FROM InvoiceLines WHERE invoice_id = ? ORDER BY line_id",
            (invoice_id,),
        ).fetchall()
        result = dict(inv)
        result["lines"] = [dict(l) for l in lines]
        result["total_paise"] = sum(l["amount_paise"] for l in lines)
        return result

    @staticmethod
    def list_scholarships(
        conn: sqlite3.Connection,
    ) -> List[Dict]:
        rows = conn.execute(
            "SELECT * FROM Scholarships ORDER BY scholarship_id"
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_student_eligibility(
        conn: sqlite3.Connection, student_id: int
    ) -> List[Dict]:
        rows = conn.execute(
            """SELECT e.*, sc.scholarship_name, sc.scholarship_code,
                      sc.scholarship_type, t.term_name
               FROM Eligibility e
               JOIN Scholarships sc ON sc.scholarship_id = e.scholarship_id
               JOIN Terms t ON t.term_id = e.term_id
               WHERE e.student_id = ?
               ORDER BY e.applied_date""",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def list_student_payments(
        conn: sqlite3.Connection,
        student_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        offset = (page - 1) * page_size
        total = conn.execute(
            "SELECT COUNT(*) FROM Payments WHERE student_id = ?", (student_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT * FROM Payments WHERE student_id = ?
               ORDER BY payment_date DESC LIMIT ? OFFSET ?""",
            (student_id, page_size, offset),
        ).fetchall()
        return [dict(r) for r in rows], total

    @staticmethod
    def get_payment_allocations(
        conn: sqlite3.Connection, payment_id: int
    ) -> List[Dict]:
        rows = conn.execute(
            """SELECT pa.*, il.fee_type, il.amount_paise AS line_amount,
                      i.invoice_number
               FROM PaymentAllocations pa
               JOIN InvoiceLines il ON il.line_id = pa.line_id
               JOIN Invoices i ON i.invoice_id = il.invoice_id
               WHERE pa.payment_id = ?""",
            (payment_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def list_student_refunds(
        conn: sqlite3.Connection, student_id: int
    ) -> List[Dict]:
        rows = conn.execute(
            """SELECT r.* FROM Refunds r
               JOIN Payments p ON p.payment_id = r.payment_id
               WHERE p.student_id = ?
               ORDER BY r.refund_date""",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def get_financial_summary(
        conn: sqlite3.Connection,
        student_id: int,
        term_id: Optional[int] = None,
    ) -> Dict:
        balance = BalanceService.get_student_balance(conn, student_id, term_id)
        student = conn.execute(
            "SELECT student_code, first_name, last_name FROM Students WHERE student_id = ?",
            (student_id,),
        ).fetchone()
        return {
            "student_id": student_id,
            "student_code": student["student_code"] if student else None,
            "student_name": f"{student['first_name']} {student['last_name']}" if student else None,
            "term_id": term_id,
            "total_invoiced_paise": balance.total_invoiced_paise,
            "total_invoiced_inr": balance.total_invoiced_paise / 100,
            "scholarship_credits_paise": balance.total_scholarship_credit_paise,
            "scholarship_credits_inr": balance.total_scholarship_credit_paise / 100,
            "net_payable_paise": balance.net_payable_paise,
            "net_payable_inr": balance.net_payable_paise / 100,
            "total_paid_paise": balance.total_paid_paise,
            "total_paid_inr": balance.total_paid_paise / 100,
            "total_refunded_paise": balance.total_refunded_paise,
            "total_refunded_inr": balance.total_refunded_paise / 100,
            "outstanding_paise": balance.outstanding_paise,
            "outstanding_inr": balance.outstanding_paise / 100,
            "overdue_paise": balance.overdue_paise,
            "overdue_inr": balance.overdue_paise / 100,
            "overpayment_paise": balance.overpayment_paise,
            "overpayment_inr": balance.overpayment_paise / 100,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

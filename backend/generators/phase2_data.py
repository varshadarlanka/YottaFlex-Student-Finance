"""
backend/generators/phase2_data.py
====================================
Phase 2 synthetic data generators: Invoices, Scholarships, Payments,
PaymentAllocations, Refunds, and AuditEvents.

Design
------
* Builds on top of the Phase 1 master data already in the DB.
* Reads live DB records for all FK references.
* Uses the same fixed seed (20261022) with forked child RNGs per entity.
* All monetary values are integer paise.
* INSERT OR IGNORE / duplicate-check patterns make reruns safe.

Full-mode targets
-----------------
  Invoices          ~30,000
  Scholarships      ~15,000 awards
  Payments          ~50,000
  Allocations       proportional to payments
  Refunds           ~5% of cleared payments
  Audit events      auto-generated per insert
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.config import GenerationConfig, PAYMENT_METHODS
from backend.database.db_manager import DatabaseManager
from backend.id_generator import IDGenerator
from backend.seed_manager import SeededRandom
from backend.services.finance_policy import FinancePolicy
from backend.services.finance_service import (
    AuditService,
    InvoiceService,
    PaymentService,
    ScholarshipService,
)

logger = logging.getLogger(__name__)

_METRO_CITIES = {"mumbai", "delhi", "bengaluru", "hyderabad",
                 "chennai", "kolkata", "pune", "ahmedabad"}


# ---------------------------------------------------------------------------
# InvoiceGenerator
# ---------------------------------------------------------------------------


class InvoiceGenerator:
    """
    Generates one Invoice (+ InvoiceLines) per enrollment.

    Target: ~1 invoice per enrollment → ~30,000 in full mode.
    For 'withdrawn'/'deferred' enrollments, status stays 'cancelled'.
    """

    def __init__(
        self,
        config: GenerationConfig,
        rng: SeededRandom,
        id_gen: IDGenerator,
        policy: Optional[FinancePolicy] = None,
    ) -> None:
        self._cfg = config
        self._rng = rng
        self._id_gen = id_gen
        self._svc = InvoiceService(policy or FinancePolicy())

    def generate(self, conn: sqlite3.Connection) -> Dict[str, int]:
        """Generate invoices for all enrollments that don't already have one."""
        enrollments = conn.execute(
            """SELECT e.enrollment_id, e.student_id, e.program_id, e.term_id,
                      e.fee_schedule_id, e.enrollment_date, e.status,
                      t.start_date AS term_start
               FROM Enrollments e
               JOIN Terms t ON t.term_id = e.term_id
               ORDER BY e.enrollment_id"""
        ).fetchall()

        stats = {"invoices_created": 0, "lines_created": 0, "skipped": 0}
        rng = self._rng

        for enr in enrollments:
            enr_id = enr["enrollment_id"]
            term_id = enr["term_id"]
            enr_status = enr["status"]
            fee_schedule_id = enr["fee_schedule_id"]
            term_start = enr["term_start"]

            # Issue date: 7–14 days before term start
            try:
                ts = date.fromisoformat(term_start)
            except Exception:
                ts = date(2024, 1, 1)
            issue_offset = rng.randint(-14, -7)
            issue_date = (ts + timedelta(days=issue_offset)).isoformat()

            seq = self._id_gen.invoice_number()   # gets next INV counter
            # Extract sequence number from "INV-00000001" → 1
            seq_num = int(seq.split("-")[-1])

            # Determine invoice status based on enrollment status
            if enr_status in ("withdrawn", "deferred"):
                inv_status = "cancelled"
            else:
                inv_status = "issued"

            try:
                inv_id = self._svc.create_invoice(
                    conn=conn,
                    enrollment_id=enr_id,
                    term_id=term_id,
                    issue_date=issue_date,
                    seq=seq_num,
                    status=inv_status,
                )
            except Exception as exc:
                logger.debug("Invoice skip for enrollment %d: %s", enr_id, exc)
                stats["skipped"] += 1
                continue

            # Only check if we actually created a new invoice (not skipped by create_invoice)
            # Add fee lines from the fee schedule
            if fee_schedule_id and inv_status != "cancelled":
                lines_added = self._svc.add_fee_lines_from_schedule(
                    conn, inv_id, fee_schedule_id
                )
                stats["lines_created"] += lines_added

            stats["invoices_created"] += 1

        logger.info(
            "Invoices: %d created, %d lines, %d skipped.",
            stats["invoices_created"], stats["lines_created"], stats["skipped"],
        )
        return stats

    def generate_supplementary(
        self,
        conn: sqlite3.Connection,
        target_invoice_count: Optional[int] = None,
    ) -> Dict[str, int]:
        """Generate supplementary invoices (hostel, transport, additional charges)
        and late-fee invoices to reach the ~30K invoice target."""
        stats = {"invoices_created": 0, "lines_created": 0}
        rng = self._rng.fork("supp_inv")
        policy = self._svc._policy

        enrollments = conn.execute(
            """SELECT e.enrollment_id, e.student_id, e.term_id,
                      t.start_date AS term_start, e.status
               FROM Enrollments e
               JOIN Terms t ON t.term_id = e.term_id
               WHERE e.status IN ('enrolled', 'completed')
               ORDER BY e.enrollment_id"""
        ).fetchall()

        selected_enrollment_ids = None
        if target_invoice_count is not None:
            current_count = conn.execute(
                "SELECT COUNT(*) FROM Invoices"
            ).fetchone()[0]
            additional_needed = max(0, target_invoice_count - current_count)
            existing_supplementary = {
                row["enrollment_id"]
                for row in conn.execute(
                    """SELECT DISTINCT i.enrollment_id
                       FROM Invoices i
                       JOIN InvoiceLines il ON il.invoice_id = i.invoice_id
                       WHERE il.fee_type IN ('Hostel', 'Transport', 'Miscellaneous')"""
                ).fetchall()
            }
            eligible = [
                row
                for row in enrollments
                if row["enrollment_id"] not in existing_supplementary
            ]
            if additional_needed > len(eligible):
                raise RuntimeError(
                    f"Cannot reach {target_invoice_count} invoices: "
                    f"only {len(eligible)} eligible supplementary invoices remain"
                )
            selected_enrollment_ids = {
                row["enrollment_id"]
                for row in rng.sample(eligible, additional_needed)
            }

        for enr in enrollments:
            if selected_enrollment_ids is not None:
                if enr["enrollment_id"] not in selected_enrollment_ids:
                    continue
            elif rng.random() > 0.62:
                continue

            sid = enr["student_id"]
            try:
                ts = date.fromisoformat(enr["term_start"])
            except Exception:
                ts = date(2024, 1, 1)
            issue_date = (ts + timedelta(days=rng.randint(30, 55))).isoformat()
            due_date = policy.calculate_due_date(issue_date)

            seq = self._id_gen.invoice_number()
            seq_num = int(seq.split("-")[-1])
            year = ts.year
            inv_number = f"INV-STU-{sid:06d}-{year}-{seq_num:06d}"

            existing = conn.execute(
                "SELECT invoice_id FROM Invoices WHERE invoice_number = ?",
                (inv_number,),
            ).fetchone()
            if existing:
                continue

            cur = conn.execute(
                """INSERT INTO Invoices
                   (invoice_number, enrollment_id, term_id, issue_date, due_date, status)
                   VALUES (?, ?, ?, ?, ?, 'issued')""",
                (inv_number, enr["enrollment_id"], enr["term_id"],
                 issue_date, due_date),
            )
            inv_id = cur.lastrowid

            supp_lines = [
                ("Hostel", "Hostel accommodation fee",
                 rng.randint(15000, 40000) * 100),
                ("Transport", "Campus transport fee",
                 rng.randint(3000, 8000) * 100),
            ]
            if rng.random() < 0.40:
                supp_lines.append(
                    ("Miscellaneous", "Misc. institutional charges",
                     rng.randint(1000, 5000) * 100)
                )

            for fee_type, desc, amount in supp_lines:
                conn.execute(
                    """INSERT INTO InvoiceLines
                       (invoice_id, fee_type, description, amount_paise, is_scholarship_credit)
                       VALUES (?, ?, ?, ?, 0)""",
                    (inv_id, fee_type, desc, amount),
                )
                stats["lines_created"] += 1

            AuditService.log(conn, "Invoice", inv_id, "CREATE",
                             new_value={"invoice_number": inv_number,
                                        "status": "issued",
                                        "type": "supplementary"})
            stats["invoices_created"] += 1

        # Late fee invoices for overdue invoices
        ref_date = date(2025, 6, 1).isoformat()
        overdue_invoices = conn.execute(
            """SELECT i.invoice_id, i.enrollment_id, i.term_id, i.due_date,
                      e.student_id
               FROM Invoices i
               JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
               WHERE i.status IN ('issued', 'overdue', 'partially_paid')
                 AND i.due_date < ?
               ORDER BY i.invoice_id""",
            (ref_date,),
        ).fetchall()

        for oi in overdue_invoices:
            if rng.random() > 0.70:
                continue

            remaining = conn.execute(
                """SELECT COALESCE(
                       SUM(CASE WHEN il.amount_paise > 0 THEN il.amount_paise ELSE 0 END), 0
                   ) - COALESCE(
                       (SELECT SUM(pa.allocated_amount_paise)
                        FROM PaymentAllocations pa
                        JOIN InvoiceLines il2 ON il2.line_id = pa.line_id
                        JOIN Payments p ON p.payment_id = pa.payment_id
                        WHERE il2.invoice_id = ? AND p.status = 'cleared'), 0
                   ) AS outstanding
                   FROM InvoiceLines il WHERE il.invoice_id = ?""",
                (oi["invoice_id"], oi["invoice_id"]),
            ).fetchone()["outstanding"]

            if remaining <= 0:
                continue

            try:
                due_dt = date.fromisoformat(oi["due_date"])
                days_over = (date.fromisoformat(ref_date) - due_dt).days
            except Exception:
                days_over = 30
            late_fee = policy.calculate_late_fee(remaining, days_over)
            if late_fee <= 0:
                continue

            sid = oi["student_id"]
            seq = self._id_gen.invoice_number()
            seq_num = int(seq.split("-")[-1])
            issue_d = ref_date
            inv_number = f"INV-STU-{sid:06d}-2025-{seq_num:06d}"
            existing = conn.execute(
                "SELECT invoice_id FROM Invoices WHERE invoice_number = ?",
                (inv_number,),
            ).fetchone()
            if existing:
                continue

            due_d = policy.calculate_due_date(issue_d)
            cur = conn.execute(
                """INSERT INTO Invoices
                   (invoice_number, enrollment_id, term_id, issue_date, due_date, status)
                   VALUES (?, ?, ?, ?, ?, 'issued')""",
                (inv_number, oi["enrollment_id"], oi["term_id"],
                 issue_d, due_d),
            )
            late_inv_id = cur.lastrowid
            conn.execute(
                """INSERT INTO InvoiceLines
                   (invoice_id, fee_type, description, amount_paise, is_scholarship_credit)
                   VALUES (?, 'Late Fee', 'Late payment penalty', ?, 0)""",
                (late_inv_id, late_fee),
            )
            stats["lines_created"] += 1
            AuditService.log(conn, "Invoice", late_inv_id, "CREATE",
                             new_value={"invoice_number": inv_number,
                                        "status": "issued",
                                        "type": "late_fee"})
            stats["invoices_created"] += 1

        logger.info(
            "Supplementary invoices: %d created, %d lines.",
            stats["invoices_created"], stats["lines_created"],
        )
        return stats


# ---------------------------------------------------------------------------
# ScholarshipGenerator
# ---------------------------------------------------------------------------


class ScholarshipGenerator:
    """
    Evaluates scholarship eligibility and records awards.

    Uses a deterministic academic_score derived from student_id and program_id
    to ensure reproducibility without storing scores in the DB.

    Target: ~15,000 awards in full mode.
    """

    def __init__(
        self,
        config: GenerationConfig,
        rng: SeededRandom,
        policy: Optional[FinancePolicy] = None,
    ) -> None:
        self._cfg = config
        self._rng = rng
        self._svc = ScholarshipService(policy or FinancePolicy())
        self._policy = policy or FinancePolicy()

    def generate(
        self,
        conn: sqlite3.Connection,
        target_award_count: Optional[int] = None,
    ) -> Dict[str, int]:
        stats = {"scholarships_inserted": 0, "awards_created": 0, "evaluated": 0}

        # Ensure scholarship catalogue exists
        code_to_id = self._svc.ensure_scholarship_catalogue(conn)
        stats["scholarships_inserted"] = len(code_to_id)

        # Load students, enrollments, programs, terms + fee schedule lines
        students_by_id: Dict[int, Dict] = {
            r["student_id"]: dict(r)
            for r in conn.execute("SELECT * FROM Students").fetchall()
        }
        programs_by_id: Dict[int, Dict] = {
            r["program_id"]: dict(r)
            for r in conn.execute("SELECT * FROM Programs").fetchall()
        }
        terms_by_id: Dict[int, Dict] = {
            r["term_id"]: dict(r)
            for r in conn.execute("SELECT * FROM Terms").fetchall()
        }

        # Eligible fee amounts per (schedule_id, fee_type)
        fsl_amounts: Dict[Tuple[int, str], int] = {}
        for fsl in conn.execute(
            "SELECT schedule_id, fee_type, amount_paise FROM FeeScheduleLines"
        ).fetchall():
            key = (fsl["schedule_id"], fsl["fee_type"])
            fsl_amounts[key] = fsl_amounts.get(key, 0) + fsl["amount_paise"]

        enrollments = conn.execute(
            """SELECT e.enrollment_id, e.student_id, e.program_id, e.term_id,
                      e.fee_schedule_id, e.year_of_study, e.status
               FROM Enrollments e
               WHERE e.status NOT IN ('withdrawn', 'deferred')
               ORDER BY e.enrollment_id"""
        ).fetchall()

        rng = self._rng

        for enr in enrollments:
            stats["evaluated"] += 1
            sid = enr["student_id"]
            pid = enr["program_id"]
            tid = enr["term_id"]
            fs_id = enr["fee_schedule_id"]
            enr_id = enr["enrollment_id"]

            student = students_by_id.get(sid, {})
            program = programs_by_id.get(pid, {})
            term = terms_by_id.get(tid, {})

            if not student or not program or not term:
                continue

            # Deterministic synthetic scores based on student+program id
            academic_score = (sid * 37 + pid * 13) % 101   # 0-100
            extra_score = (sid * 53 + pid * 7 + 11) % 101  # 0-100

            # Build eligible fee amounts by type for this enrollment
            eligible_by_type: Dict[str, int] = {}
            if fs_id:
                for fee_type in ["Tuition", "Exam", "Library", "Sports", "Lab",
                                  "Development", "Research", "Material", "Stipend Admin"]:
                    amt = fsl_amounts.get((fs_id, fee_type), 0)
                    if amt > 0:
                        eligible_by_type[fee_type] = amt

            enr_dict = dict(enr)
            enr_dict["_eligible_fee_by_type"] = eligible_by_type

            awards = self._svc.evaluate_eligibility(
                student=student,
                enrollment=enr_dict,
                program=program,
                term=term,
                academic_score=academic_score,
                extracurricular_score=extra_score,
                metro_cities=_METRO_CITIES,
            )

            for rule, award_amount in awards:
                if (
                    target_award_count is not None
                    and stats["awards_created"] >= target_award_count
                ):
                    break
                scholarship_id = code_to_id.get(rule.code)
                if not scholarship_id:
                    continue

                term_start = term.get("start_date", "2024-01-01")
                elig_id = self._svc.award_scholarship(
                    conn=conn,
                    student_id=sid,
                    scholarship_id=scholarship_id,
                    term_id=tid,
                    enrollment_id=enr_id,
                    awarded_amount_paise=award_amount,
                    applied_date=term_start,
                    status="disbursed",
                )
                if elig_id is not None:
                    stats["awards_created"] += 1

                    # Apply scholarship as credit line on the invoice
                    inv = conn.execute(
                        """SELECT i.invoice_id FROM Invoices i
                           WHERE i.enrollment_id = ? AND i.status NOT IN ('cancelled','refunded')
                           LIMIT 1""",
                        (enr_id,),
                    ).fetchone()
                    if inv:
                        # Check no duplicate credit line for same scholarship
                        existing_credit = conn.execute(
                            """SELECT COUNT(*) FROM InvoiceLines
                               WHERE invoice_id = ? AND description = ? AND is_scholarship_credit = 1""",
                            (inv["invoice_id"], f"Scholarship: {rule.name}"),
                        ).fetchone()[0]
                        if existing_credit == 0:
                            from backend.services.finance_service import InvoiceService
                            inv_svc = InvoiceService(self._policy)
                            inv_svc.add_scholarship_credit_line(
                                conn, inv["invoice_id"], rule.name, award_amount
                            )

            if (
                target_award_count is not None
                and stats["awards_created"] >= target_award_count
            ):
                break

        logger.info(
            "Scholarships: %d in catalogue, %d awards created, %d enrollments evaluated.",
            stats["scholarships_inserted"], stats["awards_created"], stats["evaluated"],
        )
        return stats


# ---------------------------------------------------------------------------
# PaymentGenerator
# ---------------------------------------------------------------------------


class PaymentGenerator:
    """
    Generates Payment records and PaymentAllocations.

    Payment strategy
    ----------------
    * 'active'/'completed' status enrollments with issued invoices get payments.
    * 70% of invoiced students pay in full; 20% partially; 10% pay nothing.
    * Failed/pending payments: ~5% of all payment attempts.
    * Cleared payments are allocated to invoice lines immediately.

    Target: ~50,000 payments in full mode.
    """

    def __init__(
        self,
        config: GenerationConfig,
        rng: SeededRandom,
        id_gen: IDGenerator,
        policy: Optional[FinancePolicy] = None,
    ) -> None:
        self._cfg = config
        self._rng = rng
        self._id_gen = id_gen
        self._svc = PaymentService()
        self._policy = policy or FinancePolicy()

    def generate(self, conn: sqlite3.Connection) -> Dict[str, int]:
        stats = {
            "payments_created": 0,
            "allocations_created": 0,
            "refunds_created": 0,
            "payments_skipped": 0,
        }
        rng = self._rng

        # Load all issued/partially_paid/overdue invoices with their student
        invoices = conn.execute(
            """SELECT i.invoice_id, i.enrollment_id, i.term_id, i.issue_date,
                      i.due_date, i.status,
                      e.student_id,
                      s.city
               FROM Invoices i
               JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
               JOIN Students s ON s.student_id = e.student_id
               WHERE i.status NOT IN ('cancelled', 'refunded')
               ORDER BY i.invoice_id"""
        ).fetchall()

        inv_svc = InvoiceService(self._policy)
        payment_ids_for_refund: List[int] = []

        for inv in invoices:
            inv_id = inv["invoice_id"]
            sid = inv["student_id"]
            issue_date_str = inv["issue_date"]

            # Compute net amount due
            line_totals = conn.execute(
                """SELECT
                    COALESCE(SUM(CASE WHEN amount_paise > 0 THEN amount_paise ELSE 0 END), 0) AS gross,
                    COALESCE(SUM(CASE WHEN amount_paise < 0 THEN ABS(amount_paise) ELSE 0 END), 0) AS credits
                   FROM InvoiceLines WHERE invoice_id = ?""",
                (inv_id,),
            ).fetchone()
            net_due = max(0, (line_totals["gross"] or 0) - (line_totals["credits"] or 0))

            if net_due == 0:
                # Zero-due invoice (fully covered by scholarships)
                inv_svc.update_status(conn, inv_id, "paid")
                continue

            # Payment probability
            pay_roll = rng.random()
            if pay_roll < 0.10:
                # 10% — no payment
                continue
            elif pay_roll < 0.30:
                # 20% — partial: pay 30–80% of net_due
                pay_fraction = rng.uniform(0.3, 0.8)
                pay_amount = max(100, int(net_due * pay_fraction))
                pay_amount = (pay_amount // 100) * 100  # round to nearest rupee
            else:
                # 70% — full payment
                pay_amount = net_due

            # Payment date: 1–25 days after issue
            try:
                issue_dt = date.fromisoformat(issue_date_str)
            except Exception:
                issue_dt = date(2024, 1, 1)
            pay_offset = rng.randint(1, 25)
            pay_date = (issue_dt + timedelta(days=pay_offset)).isoformat()

            # Payment method — weighted towards UPI/NetBanking
            method = rng.choices(
                PAYMENT_METHODS,
                weights=[5, 25, 25, 5, 10, 5, 15, 5, 5],
                k=1,
            )[0]

            # Status: 95% cleared, 5% failed/pending
            pay_roll2 = rng.random()
            if pay_roll2 < 0.03:
                pay_status = "failed"
            elif pay_roll2 < 0.05:
                pay_status = "pending"
            else:
                pay_status = "cleared"

            pay_ref = self._id_gen.payment_reference()
            txn_id = f"TXN{sid:06d}{rng.randint(100000, 999999)}"

            try:
                pay_id = self._svc.record_payment(
                    conn=conn,
                    student_id=sid,
                    payment_reference=pay_ref,
                    payment_date=pay_date,
                    amount_paise=pay_amount,
                    payment_method=method,
                    status=pay_status,
                    transaction_id=txn_id,
                )
                stats["payments_created"] += 1

                # Only allocate cleared payments
                if pay_status == "cleared":
                    alloc_count = self._allocate_to_invoice(
                        conn, pay_id, inv_id, pay_amount
                    )
                    stats["allocations_created"] += alloc_count

                    # Refresh invoice status after allocation
                    inv_svc.refresh_status(conn, inv_id)

                    # Candidate for refund (small chance)
                    if rng.random() < 0.05:
                        payment_ids_for_refund.append(pay_id)

            except Exception as exc:
                logger.debug("Payment skip for invoice %d: %s", inv_id, exc)
                stats["payments_skipped"] += 1

        # Generate refunds for a sample of cleared payments
        refund_rng = rng.fork("refunds_sub")
        for pay_id in payment_ids_for_refund:
            pay = conn.execute(
                "SELECT student_id, amount_paise, payment_date, payment_method, status FROM Payments WHERE payment_id = ?",
                (pay_id,),
            ).fetchone()
            if not pay or pay["status"] != "cleared":
                continue

            # Check if already has refund
            existing = conn.execute(
                "SELECT COUNT(*) FROM Refunds WHERE payment_id = ?", (pay_id,)
            ).fetchone()[0]
            if existing > 0:
                continue

            refund_amount = max(100, int(pay["amount_paise"] * refund_rng.uniform(0.1, 0.5)))
            refund_amount = (refund_amount // 100) * 100
            try:
                pay_dt = date.fromisoformat(pay["payment_date"])
            except Exception:
                pay_dt = date(2024, 6, 1)
            refund_date = (pay_dt + timedelta(days=refund_rng.randint(5, 30))).isoformat()
            ref_ref = self._id_gen.refund_reference()

            try:
                self._svc.record_refund(
                    conn=conn,
                    payment_id=pay_id,
                    refund_reference=ref_ref,
                    refund_date=refund_date,
                    refund_amount_paise=refund_amount,
                    reason="Student request",
                    refund_method=pay["payment_method"],
                    status="processed",
                )
                stats["refunds_created"] += 1
            except Exception as exc:
                logger.debug("Refund skip for payment %d: %s", pay_id, exc)

        logger.info(
            "Payments: %d created, %d allocations, %d refunds, %d skipped.",
            stats["payments_created"],
            stats["allocations_created"],
            stats["refunds_created"],
            stats["payments_skipped"],
        )
        return stats

    def generate_supplementary(
        self,
        conn: sqlite3.Connection,
        target_payment_count: Optional[int] = None,
    ) -> Dict[str, int]:
        """Generate additional installment and follow-up payments to reach ~50K target."""
        stats = {"payments_created": 0, "allocations_created": 0, "refunds_created": 0}
        rng = self._rng.fork("supp_pay")

        # Single bulk query: all invoice lines with remaining balance
        all_lines = conn.execute(
            """SELECT il.invoice_id, il.line_id, il.amount_paise,
                      i.issue_date, e.student_id,
                      COALESCE(pa_sum.paid, 0) AS already_paid,
                      invoice_totals.gross,
                      invoice_totals.credits,
                      COALESCE(invoice_paid.paid, 0) AS invoice_paid
               FROM InvoiceLines il
               JOIN Invoices i ON i.invoice_id = il.invoice_id
               JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
               JOIN (
                   SELECT invoice_id,
                          SUM(CASE WHEN amount_paise > 0
                                     AND is_scholarship_credit = 0
                                   THEN amount_paise ELSE 0 END) AS gross,
                          SUM(CASE WHEN is_scholarship_credit = 1
                                   THEN ABS(amount_paise) ELSE 0 END) AS credits
                   FROM InvoiceLines
                   GROUP BY invoice_id
               ) invoice_totals ON invoice_totals.invoice_id = il.invoice_id
               LEFT JOIN (
                   SELECT il.invoice_id,
                          SUM(pa.allocated_amount_paise) AS paid
                   FROM PaymentAllocations pa
                   JOIN Payments p ON p.payment_id = pa.payment_id
                   JOIN InvoiceLines il ON il.line_id = pa.line_id
                   WHERE p.status = 'cleared'
                   GROUP BY il.invoice_id
               ) invoice_paid ON invoice_paid.invoice_id = il.invoice_id
               LEFT JOIN (
                   SELECT pa.line_id, SUM(pa.allocated_amount_paise) AS paid
                   FROM PaymentAllocations pa
                   JOIN Payments p ON p.payment_id = pa.payment_id
                   WHERE p.status = 'cleared'
                   GROUP BY pa.line_id
               ) pa_sum ON pa_sum.line_id = il.line_id
               WHERE i.status IN ('issued', 'partially_paid', 'overdue')
                 AND il.amount_paise > 0
                 AND il.amount_paise > COALESCE(pa_sum.paid, 0)
               ORDER BY il.invoice_id, il.line_id"""
        ).fetchall()

        # Group by invoice
        inv_data: Dict[int, Dict] = {}
        for row in all_lines:
            inv_id = row["invoice_id"]
            if inv_id not in inv_data:
                inv_data[inv_id] = {
                    "student_id": row["student_id"],
                    "issue_date": row["issue_date"],
                    "lines": [],
                    "remaining": max(
                        0,
                        row["gross"] - row["credits"] - row["invoice_paid"],
                    ),
                }
            unpaid = row["amount_paise"] - row["already_paid"]
            inv_data[inv_id]["lines"].append((row["line_id"], unpaid))

        pay_rows = []
        alloc_rows = []
        payment_slots = None
        if target_payment_count is not None:
            payment_slots = max(
                0,
                target_payment_count
                - conn.execute("SELECT COUNT(*) FROM Payments").fetchone()[0],
            )

        for inv_id, data in inv_data.items():
            if payment_slots is not None and len(pay_rows) >= payment_slots:
                break
            sid = data["student_id"]
            remaining = data["remaining"]
            unpaid_lines = list(data["lines"])

            num_payments = (
                3
                if target_payment_count is not None
                else rng.choices([1, 2, 3], weights=[40, 35, 25], k=1)[0]
            )

            for pi in range(num_payments):
                if payment_slots is not None and len(pay_rows) >= payment_slots:
                    break
                if remaining <= 0:
                    break

                if pi < num_payments - 1:
                    pay_amount = max(100, int(remaining * rng.uniform(0.30, 0.55)))
                else:
                    pay_amount = remaining
                pay_amount = (pay_amount // 100) * 100
                if pay_amount <= 0:
                    break

                try:
                    issue_dt = date.fromisoformat(data["issue_date"])
                except Exception:
                    issue_dt = date(2024, 6, 1)
                pay_date = (issue_dt + timedelta(
                    days=rng.randint(28 + pi * 18, 55 + pi * 22)
                )).isoformat()

                method = rng.choices(
                    PAYMENT_METHODS, weights=[5, 25, 25, 5, 10, 5, 15, 5, 5], k=1,
                )[0]
                pay_ref = self._id_gen.payment_reference()
                txn_id = f"TXN{sid:06d}{rng.randint(100000, 999999)}"
                pay_status = "failed" if rng.random() < 0.03 else "cleared"

                pay_rows.append((
                    pay_ref, sid, pay_date, pay_amount,
                    method, pay_status, txn_id,
                    inv_id, pi,  # extra context for allocation
                ))

                if pay_status == "cleared":
                    alloc_remaining = pay_amount
                    new_unpaid = []
                    for line_id, line_unpaid in unpaid_lines:
                        if alloc_remaining <= 0:
                            new_unpaid.append((line_id, line_unpaid))
                            continue
                        alloc = min(alloc_remaining, line_unpaid)
                        alloc_rows.append((pay_ref, line_id, alloc))
                        alloc_remaining -= alloc
                        leftover = line_unpaid - alloc
                        if leftover > 0:
                            new_unpaid.append((line_id, leftover))
                    unpaid_lines = new_unpaid
                    remaining -= pay_amount

        # Batch insert payments
        pay_ref_to_id: Dict[str, int] = {}
        for row in pay_rows:
            pay_ref = row[0]
            cur = conn.execute(
                """INSERT OR IGNORE INTO Payments
                   (payment_reference, student_id, payment_date, amount_paise,
                    payment_method, status, transaction_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                row[:7],
            )
            if cur.lastrowid:
                pay_ref_to_id[pay_ref] = cur.lastrowid
                stats["payments_created"] += 1

        # Batch insert allocations
        for pay_ref, line_id, alloc_amount in alloc_rows:
            pay_id = pay_ref_to_id.get(pay_ref)
            if pay_id:
                conn.execute(
                    """INSERT OR IGNORE INTO PaymentAllocations
                       (payment_id, line_id, allocated_amount_paise)
                       VALUES (?, ?, ?)""",
                    (pay_id, line_id, alloc_amount),
                )
                stats["allocations_created"] += 1

        logger.info(
            "Supplementary payments: %d created, %d allocations.",
            stats["payments_created"], stats["allocations_created"],
        )
        return stats

    def _allocate_to_invoice(
        self,
        conn: sqlite3.Connection,
        payment_id: int,
        invoice_id: int,
        total_pay_amount: int,
    ) -> int:
        """
        Allocate payment across the invoice's fee lines (non-credit lines only).
        Returns number of allocations created.
        """
        lines = conn.execute(
            """SELECT il.line_id, il.amount_paise,
                      COALESCE(
                          (SELECT SUM(pa.allocated_amount_paise)
                           FROM PaymentAllocations pa
                           JOIN Payments p ON p.payment_id = pa.payment_id
                           WHERE pa.line_id = il.line_id AND p.status = 'cleared'),
                          0
                      ) AS already_paid
               FROM InvoiceLines il
               WHERE il.invoice_id = ? AND il.amount_paise > 0
               ORDER BY il.line_id""",
            (invoice_id,),
        ).fetchall()

        remaining = total_pay_amount
        count = 0
        for line in lines:
            if remaining <= 0:
                break
            unpaid = max(0, line["amount_paise"] - line["already_paid"])
            if unpaid == 0:
                continue
            alloc = min(remaining, unpaid)
            try:
                result = self._svc.allocate_payment(
                    conn=conn,
                    payment_id=payment_id,
                    line_id=line["line_id"],
                    allocated_amount_paise=alloc,
                )
                if result is not None:
                    count += 1
                    remaining -= alloc
            except Exception as exc:
                logger.debug("Alloc skip line %d: %s", line["line_id"], exc)
        return count


# ---------------------------------------------------------------------------
# Phase2Generator — orchestrates all Phase 2 generators
# ---------------------------------------------------------------------------


class Phase2Generator:
    """
    Orchestrates Phase 2 generation in correct dependency order:

    1. Scholarships catalogue (from policy)
    2. Invoices + InvoiceLines
    3. Scholarship eligibility + credit lines
    4. Payments + PaymentAllocations + Refunds
    5. Audit events (auto-generated by each service)
    """

    def __init__(
        self,
        config: GenerationConfig,
        seed: int,
        policy: Optional[FinancePolicy] = None,
    ) -> None:
        self._cfg = config
        self._policy = policy or FinancePolicy()
        self._main_rng = SeededRandom(seed)
        self._id_gen = IDGenerator()

    def run(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Execute full Phase 2 generation. Returns stats dict."""
        stats: Dict[str, Any] = {}

        # --- Step 1: Invoices ---
        inv_rng = self._main_rng.fork("invoices_p2")
        inv_gen = InvoiceGenerator(self._cfg, inv_rng, self._id_gen, self._policy)
        stats["invoices"] = inv_gen.generate(conn)

        # --- Step 2: Scholarships ---
        sch_rng = self._main_rng.fork("scholarships_p2")
        sch_gen = ScholarshipGenerator(self._cfg, sch_rng, self._policy)
        stats["scholarships"] = sch_gen.generate(conn)

        # --- Step 3: Payments, Allocations, Refunds ---
        pay_rng = self._main_rng.fork("payments_p2")
        pay_gen = PaymentGenerator(self._cfg, pay_rng, self._id_gen, self._policy)
        stats["payments"] = pay_gen.generate(conn)

        return stats

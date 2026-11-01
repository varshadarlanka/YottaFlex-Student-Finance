"""
backend/reconciliation/reconciler.py
======================================
Student-level and term-level financial reconciliation.

Reconciliation formula (all amounts in integer paise):
  net_payable    = sum(InvoiceLines.amount_paise WHERE NOT cancelled/refunded)
                   (scholarship credit lines have negative amount, so they
                    automatically reduce net_payable when summed)
  total_paid     = sum(PaymentAllocations.allocated_amount_paise
                       WHERE Payments.status = 'cleared')
  total_refunded = sum(Refunds.refund_amount_paise WHERE status = 'processed')
  outstanding    = max(0, net_payable - total_paid)
  overpayment    = max(0, total_paid - total_refunded - net_payable)

Business rules:
  * Failed and pending payments are excluded from total_paid.
  * Reversed and refunded payments only count their allocations if still cleared.
  * Cancelled and refunded invoices are excluded from fee totals.
  * Reversed transactions are excluded.
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.services.finance_service import processed_refunds_by_student_term

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ReconciliationRecord
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationRecord:
    student_id: int
    student_code: str
    student_name: str
    term_id: Optional[int]
    term_name: Optional[str]
    total_invoiced_paise: int
    scholarship_credits_paise: int
    net_payable_paise: int
    total_paid_paise: int
    total_refunded_paise: int
    outstanding_paise: int
    overpayment_paise: int
    # Comparison fields (if snapshot exists)
    snapshot_outstanding_paise: Optional[int] = None
    snapshot_difference_paise: Optional[int] = None
    is_reconciled: bool = True
    reconciliation_note: str = ""

    def as_dict(self) -> Dict:
        d = asdict(self)
        # Add INR values for readability
        for key in list(d.keys()):
            if key.endswith("_paise") and d[key] is not None:
                inr_key = key.replace("_paise", "_inr")
                d[inr_key] = round(d[key] / 100, 2)
        return d


# ---------------------------------------------------------------------------
# ReconciliationReport
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationReport:
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    total_students_reconciled: int = 0
    total_terms_checked: int = 0
    reconciled_ok: int = 0
    reconciliation_failures: int = 0
    total_outstanding_paise: int = 0
    total_overpayment_paise: int = 0
    total_invoiced_paise: int = 0
    total_paid_paise: int = 0
    total_refunded_paise: int = 0
    total_scholarship_credits_paise: int = 0
    records: List[ReconciliationRecord] = field(default_factory=list)

    def summary_dict(self) -> Dict:
        return {
            "generated_at": self.generated_at,
            "total_students_reconciled": self.total_students_reconciled,
            "total_terms_checked": self.total_terms_checked,
            "reconciled_ok": self.reconciled_ok,
            "reconciliation_failures": self.reconciliation_failures,
            "total_outstanding_inr": round(self.total_outstanding_paise / 100, 2),
            "total_overpayment_inr": round(self.total_overpayment_paise / 100, 2),
            "total_invoiced_inr": round(self.total_invoiced_paise / 100, 2),
            "total_paid_inr": round(self.total_paid_paise / 100, 2),
            "total_refunded_inr": round(self.total_refunded_paise / 100, 2),
            "total_scholarship_credits_inr": round(self.total_scholarship_credits_paise / 100, 2),
        }


# ---------------------------------------------------------------------------
# FinancialReconciler
# ---------------------------------------------------------------------------


class FinancialReconciler:
    """
    Performs student-level and term-level financial reconciliation.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile_all(
        self,
        term_id: Optional[int] = None,
        student_ids: Optional[List[int]] = None,
        limit: Optional[int] = None,
    ) -> ReconciliationReport:
        """
        Reconcile all students (or a subset).

        Parameters
        ----------
        term_id      : filter to a specific academic term (None = all terms)
        student_ids  : list of specific student IDs (None = all students)
        limit        : maximum students to reconcile (for quick checks)
        """
        conn = self._connect()
        report = ReconciliationReport()

        try:
            students = self._fetch_students(conn, student_ids, limit)
            terms = self._fetch_terms(conn, term_id)

            report.total_students_reconciled = len(students)
            report.total_terms_checked = len(terms)

            sid_list = [s["student_id"] for s in students]
            tid_list = [t["term_id"] for t in terms]

            if not sid_list or not tid_list:
                return report

            invoiced, scholarships, paid = self._bulk_financials(
                conn, sid_list, tid_list
            )
            refunded = processed_refunds_by_student_term(conn, sid_list)
            snapshots = self._bulk_snapshots(conn, sid_list, tid_list)

            stu_map = {s["student_id"]: s for s in students}
            term_map = {t["term_id"]: t for t in terms}

            for sid in sid_list:
                stu = stu_map[sid]
                for tid in tid_list:
                    term = term_map[tid]
                    total_invoiced = invoiced.get((sid, tid), 0)
                    scholarship_credits = scholarships.get((sid, tid), 0)
                    total_paid = paid.get((sid, tid), 0)
                    total_refunded = refunded.get((sid, tid), 0)

                    net_payable = max(0, total_invoiced - scholarship_credits)
                    outstanding = max(0, net_payable - total_paid + total_refunded)
                    overpayment = max(0, total_paid - total_refunded - net_payable)

                    snapshot_outstanding = None
                    snapshot_diff = None
                    is_reconciled = True
                    note = "OK"

                    snap_val = snapshots.get((sid, tid))
                    if snap_val is not None:
                        snapshot_outstanding = snap_val
                        snapshot_diff = snapshot_outstanding - outstanding
                        if abs(snapshot_diff) > 0:
                            is_reconciled = False
                            note = (
                                f"Balance snapshot disagrees: reported={snapshot_outstanding} "
                                f"ledger={outstanding} diff={snapshot_diff}"
                            )

                    rec = ReconciliationRecord(
                        student_id=sid,
                        student_code=stu["student_code"],
                        student_name=f"{stu['first_name']} {stu['last_name']}",
                        term_id=tid,
                        term_name=term["term_name"],
                        total_invoiced_paise=total_invoiced,
                        scholarship_credits_paise=scholarship_credits,
                        net_payable_paise=net_payable,
                        total_paid_paise=total_paid,
                        total_refunded_paise=total_refunded,
                        outstanding_paise=outstanding,
                        overpayment_paise=overpayment,
                        snapshot_outstanding_paise=snapshot_outstanding,
                        snapshot_difference_paise=snapshot_diff,
                        is_reconciled=is_reconciled,
                        reconciliation_note=note,
                    )
                    report.records.append(rec)

                    report.total_invoiced_paise += total_invoiced
                    report.total_scholarship_credits_paise += scholarship_credits
                    report.total_paid_paise += total_paid
                    report.total_refunded_paise += total_refunded
                    report.total_outstanding_paise += outstanding
                    report.total_overpayment_paise += overpayment

                    if is_reconciled:
                        report.reconciled_ok += 1
                    else:
                        report.reconciliation_failures += 1

        finally:
            conn.close()

        logger.info(
            "Reconciliation complete: %d students, %d records, %d failures",
            report.total_students_reconciled,
            len(report.records),
            report.reconciliation_failures,
        )
        return report

    def reconcile_overall_summary(self) -> Dict:
        """Return aggregate totals across the entire database."""
        conn = self._connect()
        try:
            total_invoiced = conn.execute(
                """SELECT COALESCE(SUM(il.amount_paise), 0)
                   FROM InvoiceLines il
                   JOIN Invoices i ON i.invoice_id = il.invoice_id
                   WHERE i.status NOT IN ('cancelled', 'refunded')
                     AND il.is_scholarship_credit = 0"""
            ).fetchone()[0]

            scholarship_credits = conn.execute(
                """SELECT COALESCE(SUM(ABS(il.amount_paise)), 0)
                   FROM InvoiceLines il
                   JOIN Invoices i ON i.invoice_id = il.invoice_id
                   WHERE i.status NOT IN ('cancelled', 'refunded')
                     AND il.is_scholarship_credit = 1"""
            ).fetchone()[0]

            total_paid = conn.execute(
                """SELECT COALESCE(SUM(pa.allocated_amount_paise), 0)
                   FROM PaymentAllocations pa
                   JOIN Payments p ON p.payment_id = pa.payment_id
                   JOIN InvoiceLines il ON il.line_id = pa.line_id
                   JOIN Invoices i ON i.invoice_id = il.invoice_id
                   WHERE p.status = 'cleared'
                     AND i.status NOT IN ('cancelled', 'refunded')"""
            ).fetchone()[0]

            total_refunded = conn.execute(
                """SELECT COALESCE(SUM(refund_amount_paise), 0)
                   FROM Refunds WHERE status = 'processed'"""
            ).fetchone()[0]

            net_payable = max(0, total_invoiced - scholarship_credits)
            outstanding = max(0, net_payable - total_paid + total_refunded)
            overpayment = max(0, total_paid - total_refunded - net_payable)

            return {
                "total_invoiced_paise": total_invoiced,
                "total_invoiced_inr": round(total_invoiced / 100, 2),
                "scholarship_credits_paise": scholarship_credits,
                "scholarship_credits_inr": round(scholarship_credits / 100, 2),
                "net_payable_paise": net_payable,
                "net_payable_inr": round(net_payable / 100, 2),
                "total_paid_paise": total_paid,
                "total_paid_inr": round(total_paid / 100, 2),
                "total_refunded_paise": total_refunded,
                "total_refunded_inr": round(total_refunded / 100, 2),
                "outstanding_paise": outstanding,
                "outstanding_inr": round(outstanding / 100, 2),
                "overpayment_paise": overpayment,
                "overpayment_inr": round(overpayment / 100, 2),
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Bulk query helpers (replace per-student-term N+1 queries)
    # ------------------------------------------------------------------

    @staticmethod
    def _bulk_financials(
        conn: sqlite3.Connection,
        sid_list: List[int],
        tid_list: List[int],
    ) -> Tuple[Dict, Dict, Dict]:
        """Return (invoiced, scholarships, paid) dicts keyed by (student_id, term_id)."""
        s_ph = ",".join("?" * len(sid_list))
        t_ph = ",".join("?" * len(tid_list))
        params: list = sid_list + tid_list

        rows = conn.execute(
            f"""SELECT en.student_id, i.term_id,
                       COALESCE(SUM(CASE WHEN il.is_scholarship_credit = 0
                                         THEN il.amount_paise ELSE 0 END), 0) AS invoiced,
                       COALESCE(SUM(CASE WHEN il.is_scholarship_credit = 1
                                         THEN ABS(il.amount_paise) ELSE 0 END), 0) AS scholarships
                FROM InvoiceLines il
                JOIN Invoices i ON i.invoice_id = il.invoice_id
                JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
                WHERE en.student_id IN ({s_ph})
                  AND i.term_id IN ({t_ph})
                  AND i.status NOT IN ('cancelled', 'refunded')
                GROUP BY en.student_id, i.term_id""",
            params,
        ).fetchall()

        invoiced: Dict[Tuple[int, int], int] = {}
        scholarships: Dict[Tuple[int, int], int] = {}
        for r in rows:
            key = (r["student_id"], r["term_id"])
            invoiced[key] = r["invoiced"]
            scholarships[key] = r["scholarships"]

        paid_rows = conn.execute(
            f"""SELECT en.student_id, i.term_id,
                       COALESCE(SUM(pa.allocated_amount_paise), 0) AS paid
                FROM PaymentAllocations pa
                JOIN Payments p ON p.payment_id = pa.payment_id
                JOIN InvoiceLines il ON il.line_id = pa.line_id
                JOIN Invoices i ON i.invoice_id = il.invoice_id
                JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
                WHERE en.student_id IN ({s_ph})
                  AND i.term_id IN ({t_ph})
                  AND p.status = 'cleared'
                  AND i.status NOT IN ('cancelled', 'refunded')
                GROUP BY en.student_id, i.term_id""",
            params,
        ).fetchall()

        paid: Dict[Tuple[int, int], int] = {}
        for r in paid_rows:
            paid[(r["student_id"], r["term_id"])] = r["paid"]

        return invoiced, scholarships, paid

    @staticmethod
    def _bulk_snapshots(
        conn: sqlite3.Connection,
        sid_list: List[int],
        tid_list: List[int],
    ) -> Dict[Tuple[int, int], int]:
        """Return latest snapshot outstanding keyed by (student_id, term_id)."""
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='BalanceSnapshots'"
        ).fetchone()
        if not has_table:
            return {}
        s_ph = ",".join("?" * len(sid_list))
        t_ph = ",".join("?" * len(tid_list))
        rows = conn.execute(
            f"""SELECT student_id, term_id, reported_outstanding_paise
                FROM BalanceSnapshots
                WHERE student_id IN ({s_ph})
                  AND term_id IN ({t_ph})
                ORDER BY student_id, term_id, snapshot_date DESC, snapshot_id DESC""",
            sid_list + tid_list,
        ).fetchall()
        result: Dict[Tuple[int, int], int] = {}
        for r in rows:
            key = (r["student_id"], r["term_id"])
            result.setdefault(key, r["reported_outstanding_paise"])
        return result

    def _fetch_students(
        self,
        conn: sqlite3.Connection,
        student_ids: Optional[List[int]],
        limit: Optional[int],
    ) -> List[sqlite3.Row]:
        if student_ids:
            placeholders = ",".join("?" * len(student_ids))
            q = f"SELECT * FROM Students WHERE student_id IN ({placeholders}) ORDER BY student_id"
            rows = conn.execute(q, student_ids).fetchall()
        elif limit:
            rows = conn.execute(
                "SELECT * FROM Students ORDER BY student_id LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM Students ORDER BY student_id").fetchall()
        return rows

    def _fetch_terms(
        self, conn: sqlite3.Connection, term_id: Optional[int]
    ) -> List[sqlite3.Row]:
        if term_id:
            rows = conn.execute(
                "SELECT * FROM Terms WHERE term_id = ?", (term_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM Terms ORDER BY term_id").fetchall()
        return rows

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

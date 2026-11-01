"""
backend/anomaly/detector.py
============================
Anomaly detection and validation engine.

Checks business rules independently (no ground-truth dependency):

1. Payment allocation totals vs. payment amounts.
2. Scholarship awards vs. eligible fees.
3. Duplicate invoices (same enrollment+term, both non-cancelled).
4. Refund totals vs. net refundable amounts.
5. Balance snapshots vs. ledger calculations.

For each detected issue, generates a DetectedIssue with:
- Unique issue_id, issue_type, severity, detection message
- Expected value, actual value, difference
- Related entity IDs
- Detection timestamp

Ground truth is NEVER used for detection — only for post-hoc evaluation.
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.services.finance_service import processed_refunds_by_student_term

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DetectedIssue data class
# ---------------------------------------------------------------------------


@dataclass
class DetectedIssue:
    issue_id: str
    issue_type: str
    entity_type: str
    entity_id: Any
    related_ids: Dict[str, Any]
    severity: str          # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    message: str
    expected_value: Any
    actual_value: Any
    difference: Optional[Any]
    detected_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    ground_truth_match: Optional[bool] = None   # set during evaluation

    def as_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """
    Business-rule validation and anomaly detection engine.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self.issues: List[DetectedIssue] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all_checks(self) -> List[DetectedIssue]:
        """Run all five checks and return detected issues."""
        self.issues = []
        conn = self._connect()
        try:
            self._check_payment_alloc_exceeds(conn)
            self._check_scholarship_exceeds_fees(conn)
            self._check_duplicate_invoices(conn)
            self._check_refund_exceeds_net_paid(conn)
            self._check_balance_disagrees_ledger(conn)
        finally:
            conn.close()
        logger.info("Detection complete: %d issues found", len(self.issues))
        return self.issues

    def get_summary(self) -> Dict:
        """Return a detection summary dict."""
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for issue in self.issues:
            by_type[issue.issue_type] = by_type.get(issue.issue_type, 0) + 1
            by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
        return {
            "total_detected": len(self.issues),
            "by_type": by_type,
            "by_severity": by_severity,
        }

    # ------------------------------------------------------------------
    # Check 1: Payment allocations exceed payment amount
    # ------------------------------------------------------------------

    def _check_payment_alloc_exceeds(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """SELECT pa.payment_id,
                      p.amount_paise AS payment_amount,
                      p.student_id,
                      SUM(pa.allocated_amount_paise) AS total_allocated
               FROM PaymentAllocations pa
               JOIN Payments p ON p.payment_id = pa.payment_id
               WHERE p.status IN ('cleared', 'refunded')
               GROUP BY pa.payment_id
               HAVING total_allocated > payment_amount"""
        ).fetchall()

        for row in rows:
            diff = row["total_allocated"] - row["payment_amount"]
            issue = DetectedIssue(
                issue_id=f"DET-A-{row['payment_id']:06d}",
                issue_type="PAYMENT_ALLOC_EXCEEDS_PAYMENT",
                entity_type="Payment",
                entity_id=row["payment_id"],
                related_ids={"student_id": row["student_id"]},
                severity="CRITICAL",
                message=(
                    f"Payment {row['payment_id']} total allocations "
                    f"{row['total_allocated']} paise exceed payment amount "
                    f"{row['payment_amount']} paise by {diff} paise"
                ),
                expected_value=row["payment_amount"],
                actual_value=row["total_allocated"],
                difference=diff,
            )
            self.issues.append(issue)

        logger.info("Check A: found %d over-allocated payments", len(rows))

    # ------------------------------------------------------------------
    # Check 2: Scholarship awards exceed eligible fees
    # ------------------------------------------------------------------

    def _check_scholarship_exceeds_fees(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """SELECT e.eligibility_id, e.student_id, e.scholarship_id,
                      e.term_id, e.awarded_amount_paise,
                      COALESCE(fees.total_fee, 0) AS eligible_fee
               FROM Eligibility e
               JOIN Scholarships s ON s.scholarship_id = e.scholarship_id
               LEFT JOIN (
                   SELECT eligible.eligibility_id,
                          SUM(il.amount_paise) AS total_fee
                   FROM Eligibility eligible
                   JOIN Scholarships scholarship
                     ON scholarship.scholarship_id = eligible.scholarship_id
                   JOIN Invoices i
                     ON i.enrollment_id = eligible.enrollment_id
                    AND i.term_id = eligible.term_id
                   JOIN InvoiceLines il ON il.invoice_id = i.invoice_id
                   WHERE il.is_scholarship_credit = 0
                     AND il.amount_paise > 0
                     AND i.status NOT IN ('cancelled', 'refunded')
                     AND (
                         (scholarship.scholarship_code = 'MERIT-ACADEMIC'
                          AND il.fee_type = 'Tuition')
                         OR (scholarship.scholarship_code = 'ACCESS-SUPPORT'
                             AND il.fee_type IN ('Tuition', 'Development'))
                         OR (scholarship.scholarship_code = 'GOV-WOMEN-STEM'
                             AND il.fee_type IN ('Tuition', 'Lab'))
                         OR (scholarship.scholarship_code = 'SPORTS-EXCELLENCE'
                             AND il.fee_type IN ('Sports', 'Tuition', 'Development'))
                         OR (scholarship.scholarship_code = 'RESEARCH-GRANT'
                             AND il.fee_type IN ('Research', 'Library', 'Tuition'))
                     )
                   GROUP BY eligible.eligibility_id
               ) fees ON fees.eligibility_id = e.eligibility_id
               WHERE e.status IN ('approved', 'disbursed')
                 AND e.awarded_amount_paise > COALESCE(fees.total_fee, 0)"""
        ).fetchall()

        for row in rows:
            diff = row["awarded_amount_paise"] - row["eligible_fee"]
            issue = DetectedIssue(
                issue_id=f"DET-B-{row['eligibility_id']:06d}",
                issue_type="SCHOLARSHIP_EXCEEDS_FEES",
                entity_type="Eligibility",
                entity_id=row["eligibility_id"],
                related_ids={
                    "student_id": row["student_id"],
                    "scholarship_id": row["scholarship_id"],
                    "term_id": row["term_id"],
                },
                severity="HIGH",
                message=(
                    f"Eligibility {row['eligibility_id']}: awarded "
                    f"{row['awarded_amount_paise']} paise exceeds eligible "
                    f"fees {row['eligible_fee']} paise by {diff} paise"
                ),
                expected_value=row["eligible_fee"],
                actual_value=row["awarded_amount_paise"],
                difference=diff,
            )
            self.issues.append(issue)

        logger.info("Check B: found %d over-awarded scholarships", len(rows))

    # ------------------------------------------------------------------
    # Check 3: Duplicate invoices
    # ------------------------------------------------------------------

    def _check_duplicate_invoices(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """SELECT i.invoice_id, i.invoice_number, i.enrollment_id, i.term_id,
                      en.student_id,
                      MIN(i.invoice_id) OVER (
                          PARTITION BY i.enrollment_id, i.term_id
                      ) AS original_id,
                      COUNT(*) OVER (
                          PARTITION BY i.enrollment_id, i.term_id
                      ) AS grp_cnt
               FROM Invoices i
               JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
               WHERE i.status NOT IN ('cancelled', 'refunded')
                 AND (
                     NOT EXISTS (
                         SELECT 1 FROM InvoiceLines il WHERE il.invoice_id = i.invoice_id
                     )
                     OR EXISTS (
                         SELECT 1 FROM InvoiceLines il WHERE il.invoice_id = i.invoice_id
                           AND il.fee_type NOT IN ('Hostel','Transport','Miscellaneous','Late Fee')
                     )
                 )"""
        ).fetchall()

        count = 0
        for row in rows:
            if row["grp_cnt"] > 1 and row["invoice_id"] != row["original_id"]:
                issue = DetectedIssue(
                    issue_id=f"DET-C-{row['invoice_id']:06d}",
                    issue_type="DUPLICATE_INVOICE",
                    entity_type="Invoice",
                    entity_id=row["invoice_id"],
                    related_ids={
                        "original_invoice_id": row["original_id"],
                        "student_id": row["student_id"],
                        "enrollment_id": row["enrollment_id"],
                        "term_id": row["term_id"],
                    },
                    severity="HIGH",
                    message=(
                        f"Invoice {row['invoice_id']} ({row['invoice_number']}) is a duplicate "
                        f"of invoice {row['original_id']} for enrollment "
                        f"{row['enrollment_id']} term {row['term_id']}"
                    ),
                    expected_value=1,
                    actual_value=row["grp_cnt"],
                    difference=row["grp_cnt"] - 1,
                )
                self.issues.append(issue)
                count += 1

        logger.info("Check C: found %d duplicate invoices", count)

    # ------------------------------------------------------------------
    # Check 4: Refund exceeds net paid
    # ------------------------------------------------------------------

    def _check_refund_exceeds_net_paid(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """SELECT r.payment_id, p.amount_paise AS payment_amount,
                      p.student_id,
                      SUM(r.refund_amount_paise) AS total_refunded
               FROM Refunds r
               JOIN Payments p ON p.payment_id = r.payment_id
               WHERE r.status IN ('processed', 'pending')
               GROUP BY r.payment_id
               HAVING total_refunded > payment_amount"""
        ).fetchall()

        for row in rows:
            diff = row["total_refunded"] - row["payment_amount"]
            issue = DetectedIssue(
                issue_id=f"DET-D-{row['payment_id']:06d}",
                issue_type="REFUND_EXCEEDS_NET_PAID",
                entity_type="Payment",
                entity_id=row["payment_id"],
                related_ids={"student_id": row["student_id"]},
                severity="CRITICAL",
                message=(
                    f"Payment {row['payment_id']} total refunds "
                    f"{row['total_refunded']} paise exceed payment amount "
                    f"{row['payment_amount']} paise by {diff} paise"
                ),
                expected_value=row["payment_amount"],
                actual_value=row["total_refunded"],
                difference=diff,
            )
            self.issues.append(issue)

        logger.info("Check D: found %d excess refund payments", len(rows))

    # ------------------------------------------------------------------
    # Check 5: Balance snapshot disagrees with ledger
    # ------------------------------------------------------------------

    def _check_balance_disagrees_ledger(self, conn: sqlite3.Connection) -> None:
        tbl_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='BalanceSnapshots'"
        ).fetchone()
        if not tbl_exists:
            logger.info("BalanceSnapshots table not found - skipping check E")
            return

        rows = conn.execute(
            """SELECT bs.snapshot_id, bs.student_id, bs.term_id,
                      bs.reported_outstanding_paise, bs.snapshot_rank,
                      COALESCE(inv.total_invoiced, 0) AS total_invoiced,
                      COALESCE(inv.scholarship_credit, 0) AS scholarship_credit,
                      COALESCE(pa_agg.total_paid, 0) AS total_paid
               FROM (
                   SELECT *, ROW_NUMBER() OVER (
                       PARTITION BY student_id, term_id
                       ORDER BY snapshot_date DESC, snapshot_id DESC
                   ) AS snapshot_rank
                   FROM BalanceSnapshots
               ) bs
               LEFT JOIN (
                   SELECT en.student_id, i.term_id,
                          SUM(CASE WHEN il.is_scholarship_credit = 0
                                     AND il.amount_paise > 0
                                   THEN il.amount_paise ELSE 0 END) AS total_invoiced,
                          SUM(CASE WHEN il.is_scholarship_credit = 1
                                   THEN ABS(il.amount_paise) ELSE 0 END) AS scholarship_credit
                   FROM InvoiceLines il
                   JOIN Invoices i ON i.invoice_id = il.invoice_id
                   JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
                   WHERE i.status NOT IN ('cancelled', 'refunded')
                   GROUP BY en.student_id, i.term_id
               ) inv ON inv.student_id = bs.student_id AND inv.term_id = bs.term_id
               LEFT JOIN (
                   SELECT en.student_id, i.term_id,
                          SUM(pa.allocated_amount_paise) AS total_paid
                   FROM PaymentAllocations pa
                   JOIN Payments p ON p.payment_id = pa.payment_id
                   JOIN InvoiceLines il ON il.line_id = pa.line_id
                   JOIN Invoices i ON i.invoice_id = il.invoice_id
                   JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
                   WHERE p.status = 'cleared'
                     AND i.status NOT IN ('cancelled', 'refunded')
                   GROUP BY en.student_id, i.term_id
               ) pa_agg ON pa_agg.student_id = bs.student_id AND pa_agg.term_id = bs.term_id"""
        ).fetchall()

        refunds = processed_refunds_by_student_term(conn)
        count = 0
        for row in rows:
            if row["snapshot_rank"] != 1:
                continue
            net_payable = max(0, row["total_invoiced"] - row["scholarship_credit"])
            ledger_outstanding = max(
                0,
                net_payable
                - row["total_paid"]
                + refunds.get((row["student_id"], row["term_id"]), 0),
            )

            diff = abs(row["reported_outstanding_paise"] - ledger_outstanding)
            if diff > 0:
                issue = DetectedIssue(
                    issue_id=f"DET-E-{row['snapshot_id']:06d}",
                    issue_type="BALANCE_DISAGREES_LEDGER",
                    entity_type="BalanceSnapshot",
                    entity_id=row["snapshot_id"],
                    related_ids={
                        "student_id": row["student_id"],
                        "term_id": row["term_id"],
                    },
                    severity="MEDIUM",
                    message=(
                        f"BalanceSnapshot {row['snapshot_id']} for student {row['student_id']} "
                        f"term {row['term_id']}: reported outstanding "
                        f"{row['reported_outstanding_paise']} paise, "
                        f"ledger calculates {ledger_outstanding} paise (diff={diff})"
                    ),
                    expected_value=ledger_outstanding,
                    actual_value=row["reported_outstanding_paise"],
                    difference=row["reported_outstanding_paise"] - ledger_outstanding,
                )
                self.issues.append(issue)
                count += 1

        logger.info("Check E: found %d balance snapshot discrepancies", count)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

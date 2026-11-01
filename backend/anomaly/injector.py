"""
backend/anomaly/injector.py
============================
Controlled anomaly injection module.

Seed: 20261022 (fixed for reproducibility).

Five anomaly types
------------------
A. PAYMENT_ALLOC_EXCEEDS_PAYMENT   — total allocated > payment amount
B. SCHOLARSHIP_EXCEEDS_FEES        — awarded scholarship > eligible fee total
C. DUPLICATE_INVOICE               — same student/enrollment/term, second invoice
D. REFUND_EXCEEDS_NET_PAID         — refund > net refundable amount
E. BALANCE_DISAGREES_LEDGER        — stored snapshot != ledger calculation

Rules
-----
* Every record carries issue_type and ground_truth = True.
* Anomaly records are traceable to original entity IDs.
* Primary-key / foreign-key constraints are never disabled.
* Baseline records are never randomly corrupted.
* Reproducible with seed 20261022.
"""
from __future__ import annotations

import csv
import json
import logging
import random
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SEED = 20261022


@dataclass
class GroundTruthRecord:
    issue_id: str
    issue_type: str
    entity_type: str
    entity_id: Any
    related_ids: Dict[str, Any]
    description: str
    ground_truth: bool = True
    injected_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    )
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


class AnomalyInjector:
    """Injects the five controlled anomaly records into a populated database."""

    MARKER_PREFIX = "ANOMALY-INJECTED-"

    def __init__(self, db_path: str | Path, seed: int = SEED) -> None:
        self._db_path = str(db_path)
        self._rng = random.Random(seed)
        self._ground_truth: List[GroundTruthRecord] = []

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _marker_sql(self, conn: sqlite3.Connection, marker: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM AuditEvents WHERE notes = ? LIMIT 1",
            (marker,),
        ).fetchone()
        return row is not None

    def _register_marker(
        self,
        conn: sqlite3.Connection,
        marker: str,
        record: GroundTruthRecord,
    ) -> None:
        conn.execute(
            """
            INSERT INTO AuditEvents (
                entity_type, entity_id, event_type, field_changed,
                old_value, new_value, performed_by, notes
            ) VALUES (?, ?, 'ANOMALY_INJECT', 'anomaly', ?, ?, 'system', ?)
            """,
            (
                record.entity_type,
                record.entity_id,
                json.dumps({"status": "before"}, sort_keys=True),
                json.dumps(
                    {
                        "issue_type": record.issue_type,
                        "ground_truth": record.as_dict(),
                    },
                    sort_keys=True,
                ),
                marker,
            ),
        )

    def _make_record(
        self,
        issue_type: str,
        entity_type: str,
        entity_id: Any,
        related_ids: Dict[str, Any],
        description: str,
        details: Dict[str, Any],
    ) -> GroundTruthRecord:
        record = GroundTruthRecord(
            issue_id=f"GT-{issue_type}-{entity_id}",
            issue_type=issue_type,
            entity_type=entity_type,
            entity_id=entity_id,
            related_ids=related_ids,
            description=description,
            details=details,
        )
        self._ground_truth.append(record)
        return record

    def _ensure_balance_snapshot_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS BalanceSnapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL REFERENCES Students(student_id)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
                term_id INTEGER NOT NULL REFERENCES Terms(term_id)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
                reported_outstanding_paise INTEGER NOT NULL,
                snapshot_date TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
            )
            """
        )

    def inject_all(self) -> List[GroundTruthRecord]:
        """Inject all five anomaly types. Returns the ground-truth list."""
        conn = self._connect()
        try:
            conn.execute("BEGIN")
            self._ground_truth = []
            self._inject_a_payment_alloc_exceeds(conn)
            self._inject_b_scholarship_exceeds_fees(conn)
            self._inject_c_duplicate_invoice(conn)
            self._inject_d_refund_exceeds_net_paid(conn)
            self._inject_e_balance_disagrees_ledger(conn)
            self._ground_truth = self._load_ground_truth(conn)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._ground_truth

    def get_ground_truth(self) -> List[GroundTruthRecord]:
        conn = self._connect()
        try:
            self._ground_truth = self._load_ground_truth(conn)
        finally:
            conn.close()
        return list(self._ground_truth)

    def _load_ground_truth(
        self, conn: sqlite3.Connection
    ) -> List[GroundTruthRecord]:
        issue_types = {
            "A": "PAYMENT_ALLOC_EXCEEDS_PAYMENT",
            "B": "SCHOLARSHIP_EXCEEDS_FEES",
            "C": "DUPLICATE_INVOICE",
            "D": "REFUND_EXCEEDS_NET_PAID",
            "E": "BALANCE_DISAGREES_LEDGER",
        }
        rows = conn.execute(
            """SELECT entity_type, entity_id, new_value, performed_at, notes
               FROM AuditEvents
               WHERE event_type = 'ANOMALY_INJECT'
                 AND notes LIKE ?
               ORDER BY audit_id""",
            (self.MARKER_PREFIX + "%",),
        ).fetchall()
        records: List[GroundTruthRecord] = []
        seen_markers = set()
        for row in rows:
            marker = row["notes"]
            suffix = marker.removeprefix(self.MARKER_PREFIX)
            issue_type = issue_types.get(suffix)
            if issue_type is None or marker in seen_markers:
                continue
            seen_markers.add(marker)

            new_value = json.loads(row["new_value"] or "{}")
            payload = new_value.get("ground_truth")
            if payload is not None:
                records.append(GroundTruthRecord(**payload))
                continue

            # Older injections stored only the marker and issue type.
            records.append(
                GroundTruthRecord(
                    issue_id=f"GT-{issue_type}-{row['entity_id']}",
                    issue_type=issue_type,
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    related_ids={},
                    description=f"Previously injected {issue_type} anomaly.",
                    injected_at=row["performed_at"] or "",
                )
            )
        return records

    def export_ground_truth(
        self,
        output_dir: str | Path | None = None,
        base_name: str = "ground_truth",
    ) -> Dict[str, Path]:
        out_dir = Path(output_dir) if output_dir is not None else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / f"{base_name}.csv"
        json_path = out_dir / f"{base_name}.json"

        rows = [gt.as_dict() for gt in self._ground_truth]
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "issue_id",
                    "issue_type",
                    "entity_type",
                    "entity_id",
                    "related_ids",
                    "description",
                    "ground_truth",
                    "injected_at",
                    "details",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "issue_id": row["issue_id"],
                        "issue_type": row["issue_type"],
                        "entity_type": row["entity_type"],
                        "entity_id": row["entity_id"],
                        "related_ids": json.dumps(row["related_ids"], sort_keys=True),
                        "description": row["description"],
                        "ground_truth": row["ground_truth"],
                        "injected_at": row["injected_at"],
                        "details": json.dumps(row["details"], sort_keys=True),
                    }
                )

        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, sort_keys=True)

        return {"csv": csv_path, "json": json_path}

    def __len__(self) -> int:
        return len(self._ground_truth)

    def _inject_a_payment_alloc_exceeds(self, conn: sqlite3.Connection) -> None:
        marker = self.MARKER_PREFIX + "A"
        if self._marker_sql(conn, marker):
            return

        payment = conn.execute(
            """
            SELECT p.payment_id, p.student_id, p.amount_paise,
                   COALESCE(SUM(pa.allocated_amount_paise), 0) AS allocated_total
            FROM Payments p
            LEFT JOIN PaymentAllocations pa ON pa.payment_id = p.payment_id
            WHERE p.status = 'cleared'
            GROUP BY p.payment_id
            HAVING allocated_total < p.amount_paise
            ORDER BY p.payment_id
            LIMIT 1
            """
        ).fetchone()
        if payment is None:
            payment = conn.execute(
                """
                SELECT payment_id, student_id, amount_paise
                FROM Payments
                WHERE status = 'cleared'
                ORDER BY payment_id
                LIMIT 1
                """
            ).fetchone()
        if payment is None:
            raise RuntimeError("No valid cleared payment exists for anomaly A")

        line = conn.execute(
            """
            SELECT il.line_id, en.student_id
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
            WHERE en.student_id = ?
              AND il.line_id NOT IN (
                  SELECT pa.line_id FROM PaymentAllocations pa
                  WHERE pa.payment_id = ?
              )
            ORDER BY il.line_id
            LIMIT 1
            """,
            (payment["student_id"], payment["payment_id"]),
        ).fetchone()

        existing_alloc = conn.execute(
            "SELECT COALESCE(SUM(allocated_amount_paise), 0) FROM PaymentAllocations WHERE payment_id = ?",
            (payment["payment_id"],),
        ).fetchone()[0]
        extra_amount = max(2500, payment["amount_paise"] - existing_alloc + 2500)

        if line is not None:
            conn.execute(
                "INSERT INTO PaymentAllocations (payment_id, line_id, allocated_amount_paise) VALUES (?, ?, ?)",
                (payment["payment_id"], line["line_id"], extra_amount),
            )
        else:
            existing_pa = conn.execute(
                "SELECT line_id, allocated_amount_paise FROM PaymentAllocations WHERE payment_id = ? ORDER BY line_id LIMIT 1",
                (payment["payment_id"],),
            ).fetchone()
            if existing_pa is None:
                raise RuntimeError("No invoice line exists for anomaly A")
            line = {"line_id": existing_pa["line_id"]}
            conn.execute(
                "UPDATE PaymentAllocations SET allocated_amount_paise = ? WHERE payment_id = ? AND line_id = ?",
                (existing_pa["allocated_amount_paise"] + extra_amount, payment["payment_id"], existing_pa["line_id"]),
            )

        record = self._make_record(
            "PAYMENT_ALLOC_EXCEEDS_PAYMENT",
            "Payment",
            payment["payment_id"],
            {"student_id": payment["student_id"], "line_id": line["line_id"]},
            f"Payment {payment['payment_id']} exceeds the original payment amount after allocation.",
            {
                "payment_amount_paise": payment["amount_paise"],
                "allocated_total_paise": existing_alloc + extra_amount,
                "excess_paise": extra_amount,
            },
        )
        self._register_marker(conn, marker, record)

    def _inject_b_scholarship_exceeds_fees(self, conn: sqlite3.Connection) -> None:
        marker = self.MARKER_PREFIX + "B"
        if self._marker_sql(conn, marker):
            return

        elig = conn.execute(
            """
            SELECT e.eligibility_id, e.student_id, e.term_id, e.awarded_amount_paise,
                   e.scholarship_id
            FROM Eligibility e
            WHERE e.status IN ('approved', 'disbursed')
            ORDER BY e.eligibility_id
            LIMIT 1
            """
        ).fetchone()
        if elig is None:
            # create a fresh award record using a real student + scholarship + term
            base = conn.execute(
                """
                SELECT e.student_id, e.term_id, e.enrollment_id, s.scholarship_id
                FROM Enrollments e
                CROSS JOIN Scholarships s
                ORDER BY e.enrollment_id, s.scholarship_id
                LIMIT 1
                """
            ).fetchone()
            if base is None:
                raise RuntimeError("No valid eligibility context exists for anomaly B")
            cursor = conn.execute(
                """
                INSERT INTO Eligibility (student_id, scholarship_id, term_id, awarded_amount_paise,
                status, applied_date, enrollment_id, approved_date, disbursed_date)
                VALUES (?, ?, ?, 1000, 'disbursed', date('now'), ?, date('now'), date('now'))
                """,
                (base["student_id"], base["scholarship_id"], base["term_id"], base["enrollment_id"]),
            )
            elig = conn.execute(
                "SELECT eligibility_id, student_id, term_id, awarded_amount_paise, scholarship_id FROM Eligibility WHERE eligibility_id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        if elig is None:
            raise RuntimeError("No valid eligibility exists for anomaly B")

        eligible_fee = conn.execute(
            """
            SELECT COALESCE(SUM(il.amount_paise), 0)
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
            WHERE en.student_id = ?
              AND i.term_id = ?
              AND il.is_scholarship_credit = 0
              AND i.status NOT IN ('cancelled', 'refunded')
            """,
            (elig["student_id"], elig["term_id"]),
        ).fetchone()[0]
        if eligible_fee <= 0:
            enroll = conn.execute(
                "SELECT enrollment_id, term_id FROM Enrollments WHERE student_id = ? ORDER BY enrollment_id LIMIT 1",
                (elig["student_id"],),
            ).fetchone()
            if enroll is not None:
                invoice = conn.execute(
                    "SELECT invoice_id FROM Invoices WHERE enrollment_id = ? AND status NOT IN ('cancelled', 'refunded') ORDER BY invoice_id LIMIT 1",
                    (enroll["enrollment_id"],),
                ).fetchone()
                if invoice is None:
                    next_id = conn.execute("SELECT COALESCE(MAX(invoice_id), 0) + 1 FROM Invoices").fetchone()[0]
                    conn.execute(
                        "INSERT INTO Invoices (invoice_number, enrollment_id, term_id, issue_date, due_date, status, notes) VALUES (?, ?, ?, date('now'), date('now'), 'issued', 'Phase 3 fee creation for scholarship anomaly')",
                        (f"INV-B-{next_id:06d}", enroll["enrollment_id"], enroll["term_id"]),
                    )
                    invoice = conn.execute(
                        "SELECT invoice_id FROM Invoices WHERE invoice_number = ?",
                        (f"INV-B-{next_id:06d}",),
                    ).fetchone()
                if invoice is not None:
                    conn.execute(
                        "INSERT INTO InvoiceLines (invoice_id, fee_type, description, amount_paise, is_scholarship_credit) VALUES (?, 'Tuition', 'Inserted eligibility anomaly fee', 150000, 0)",
                        (invoice["invoice_id"],),
                    )
                    eligible_fee = 150000
            if eligible_fee <= 0:
                raise RuntimeError("No eligible fee total exists for anomaly B")

        new_award = eligible_fee + 5000
        conn.execute(
            "UPDATE Eligibility SET awarded_amount_paise = ?, updated_at = ? WHERE eligibility_id = ?",
            (new_award, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), elig["eligibility_id"]),
        )

        record = self._make_record(
            "SCHOLARSHIP_EXCEEDS_FEES",
            "Eligibility",
            elig["eligibility_id"],
            {"student_id": elig["student_id"], "scholarship_id": elig["scholarship_id"], "term_id": elig["term_id"]},
            f"Eligibility {elig['eligibility_id']} award exceeds eligible fee total.",
            {
                "eligible_fee_paise": eligible_fee,
                "awarded_amount_paise": new_award,
                "excess_paise": new_award - eligible_fee,
            },
        )
        self._register_marker(conn, marker, record)

    def _inject_c_duplicate_invoice(self, conn: sqlite3.Connection) -> None:
        marker = self.MARKER_PREFIX + "C"
        if self._marker_sql(conn, marker):
            return

        enrollment = conn.execute(
            """
            SELECT e.enrollment_id, e.student_id, e.term_id
            FROM Enrollments e
            WHERE EXISTS (
                SELECT 1 FROM Invoices i
                WHERE i.enrollment_id = e.enrollment_id
                  AND i.status NOT IN ('cancelled', 'refunded')
            )
            ORDER BY e.enrollment_id
            LIMIT 1
            """
        ).fetchone()
        if enrollment is None:
            raise RuntimeError("No enrollment exists for anomaly C")

        next_seq = conn.execute("SELECT COALESCE(MAX(invoice_id), 0) + 1 FROM Invoices").fetchone()[0]
        duplicate_invoice_number = f"INV-DUP-{next_seq:06d}"

        cursor = conn.execute(
            """
            INSERT INTO Invoices (
                invoice_number, enrollment_id, term_id, issue_date, due_date,
                status, notes
            ) VALUES (?, ?, ?, ?, ?, 'issued', 'Duplicate invoice injected for Phase 3 validation')
            """,
            (
                duplicate_invoice_number,
                enrollment["enrollment_id"],
                enrollment["term_id"],
                date.today().isoformat(),
                date.today().isoformat(),
            ),
        )

        record = self._make_record(
            "DUPLICATE_INVOICE",
            "Invoice",
            cursor.lastrowid,
            {
                "student_id": enrollment["student_id"],
                "enrollment_id": enrollment["enrollment_id"],
                "term_id": enrollment["term_id"],
            },
            f"Invoice {duplicate_invoice_number} duplicates an existing invoice for the same enrollment and term.",
            {
                "duplicate_invoice_number": duplicate_invoice_number,
                "enrollment_id": enrollment["enrollment_id"],
                "term_id": enrollment["term_id"],
            },
        )
        self._register_marker(conn, marker, record)

    def _inject_d_refund_exceeds_net_paid(self, conn: sqlite3.Connection) -> None:
        marker = self.MARKER_PREFIX + "D"
        if self._marker_sql(conn, marker):
            return

        payment = conn.execute(
            """
            SELECT p.payment_id, p.student_id, p.amount_paise,
                   COALESCE(SUM(r.refund_amount_paise), 0) AS refund_total
            FROM Payments p
            LEFT JOIN Refunds r ON r.payment_id = p.payment_id AND r.status IN ('processed', 'pending')
            WHERE p.status IN ('cleared', 'refunded')
            GROUP BY p.payment_id
            HAVING refund_total < p.amount_paise
            ORDER BY p.payment_id
            LIMIT 1
            """
        ).fetchone()
        if payment is None:
            payment = conn.execute(
                "SELECT payment_id, student_id, amount_paise FROM Payments WHERE status = 'cleared' ORDER BY payment_id LIMIT 1"
            ).fetchone()
        if payment is None:
            raise RuntimeError("No valid payment exists for anomaly D")

        refund_amount = payment["amount_paise"] + 2500
        cursor = conn.execute(
            """
            INSERT INTO Refunds (
                refund_reference, payment_id, refund_date, refund_amount_paise,
                reason, refund_method, status, processed_by, notes
            ) VALUES (?, ?, ?, ?, 'Phase 3 refund validation anomaly', 'NetBanking', 'processed', 'system', 'Injected refund anomaly')
            """,
            (
                f"REF-{payment['payment_id']:06d}-PH3",
                payment["payment_id"],
                date.today().isoformat(),
                refund_amount,
            ),
        )

        record = self._make_record(
            "REFUND_EXCEEDS_NET_PAID",
            "Payment",
            payment["payment_id"],
            {"student_id": payment["student_id"], "refund_id": cursor.lastrowid},
            f"Refund {cursor.lastrowid} on payment {payment['payment_id']} exceeds the net refundable amount.",
            {
                "payment_amount_paise": payment["amount_paise"],
                "refund_amount_paise": refund_amount,
                "excess_paise": refund_amount - payment["amount_paise"],
            },
        )
        self._register_marker(conn, marker, record)

    def _inject_e_balance_disagrees_ledger(self, conn: sqlite3.Connection) -> None:
        marker = self.MARKER_PREFIX + "E"
        if self._marker_sql(conn, marker):
            return

        self._ensure_balance_snapshot_table(conn)

        student_term = conn.execute(
            """
            SELECT s.student_id, e.term_id
            FROM Students s
            JOIN Enrollments e ON e.student_id = s.student_id
            ORDER BY s.student_id, e.term_id
            LIMIT 1
            """
        ).fetchone()
        if student_term is None:
            raise RuntimeError("No student/term exists for anomaly E")

        student_id = student_term["student_id"]
        term_id = student_term["term_id"]

        total_invoiced = conn.execute(
            """
            SELECT COALESCE(SUM(il.amount_paise), 0)
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
            WHERE en.student_id = ? AND i.term_id = ?
              AND i.status NOT IN ('cancelled', 'refunded')
              AND il.is_scholarship_credit = 0
            """,
            (student_id, term_id),
        ).fetchone()[0]

        scholarship_credits = conn.execute(
            """
            SELECT COALESCE(SUM(ABS(il.amount_paise)), 0)
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
            WHERE en.student_id = ? AND i.term_id = ?
              AND il.is_scholarship_credit = 1
              AND i.status NOT IN ('cancelled', 'refunded')
            """,
            (student_id, term_id),
        ).fetchone()[0]

        total_paid = conn.execute(
            """
            SELECT COALESCE(SUM(pa.allocated_amount_paise), 0)
            FROM PaymentAllocations pa
            JOIN InvoiceLines il ON il.line_id = pa.line_id
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments en ON en.enrollment_id = i.enrollment_id
            JOIN Payments p ON p.payment_id = pa.payment_id
            WHERE en.student_id = ? AND i.term_id = ? AND p.status = 'cleared'
            """,
            (student_id, term_id),
        ).fetchone()[0]

        net_payable = max(0, total_invoiced - scholarship_credits)
        ledger_outstanding = max(0, net_payable - total_paid)
        reported_outstanding = ledger_outstanding + 2500

        cursor = conn.execute(
            """
            INSERT INTO BalanceSnapshots (
                student_id, term_id, reported_outstanding_paise
            ) VALUES (?, ?, ?)
            """,
            (student_id, term_id, reported_outstanding),
        )

        record = self._make_record(
            "BALANCE_DISAGREES_LEDGER",
            "BalanceSnapshot",
            cursor.lastrowid,
            {"student_id": student_id, "term_id": term_id},
            f"Balance snapshot for student {student_id} term {term_id} disagrees with ledger.",
            {
                "ledger_outstanding_paise": ledger_outstanding,
                "reported_outstanding_paise": reported_outstanding,
                "difference_paise": reported_outstanding - ledger_outstanding,
            },
        )
        self._register_marker(conn, marker, record)


def export_ground_truth(
    db_path: str | Path,
    output_dir: str | Path | None = None,
    base_name: str = "ground_truth",
) -> Dict[str, Path]:
    """Inject anomalies and export CSV/JSON ground truth."""
    injector = AnomalyInjector(db_path)
    injector.inject_all()
    return injector.export_ground_truth(output_dir=output_dir, base_name=base_name)


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Inject the five controlled anomalies and export ground truth.")
    parser.add_argument("--db", default=str(Path("backend/database/student_finance.db")), help="Path to SQLite database")
    parser.add_argument("--out-dir", default=".", help="Directory to write ground_truth.csv/json files")
    parser.add_argument("--base-name", default="ground_truth", help="Base name for exported files")
    args = parser.parse_args()

    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    exports = export_ground_truth(db_path=db_path, output_dir=out_dir, base_name=args.base_name)
    print(f"Injected ground truth: {list(exports.keys())}")
    print(f"CSV: {exports['csv']}")
    print(f"JSON: {exports['json']}")


if __name__ == "__main__":
    _cli()

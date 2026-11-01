"""Phase 3 validation tests for anomaly injection, detection, and evaluation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.anomaly.detector import AnomalyDetector
from backend.anomaly.evaluator import AnomalyEvaluator
from backend.anomaly.injector import AnomalyInjector
from backend.config import DEFAULT_SEED, GenerationMode
from backend.generators.generate_data import run_generation
from backend.services.finance_service import PaymentService


@pytest.fixture
def fresh_phase3_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "phase3.db"
    run_generation(GenerationMode.STARTER, db_path, DEFAULT_SEED, reset=False)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Find a line that still has remaining unpaid balance so the
        # allocation will not be rejected by the PaymentService validator.
        row = conn.execute(
            """
            SELECT e.student_id, i.invoice_id, il.line_id, il.amount_paise,
                   COALESCE(
                       (SELECT SUM(pa.allocated_amount_paise)
                        FROM PaymentAllocations pa
                        WHERE pa.line_id = il.line_id), 0
                   ) AS already_paid
            FROM InvoiceLines il
            JOIN Invoices i ON i.invoice_id = il.invoice_id
            JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
            WHERE i.status NOT IN ('cancelled', 'refunded')
              AND il.amount_paise > 0
              AND il.is_scholarship_credit = 0
            ORDER BY e.student_id, i.invoice_id, il.line_id
            """
        ).fetchall()

        # Pick the first line with remaining capacity
        target = None
        for r in row:
            remaining = r["amount_paise"] - r["already_paid"]
            if remaining > 0:
                target = r
                break

        if target is None:
            raise AssertionError("No invoice line with remaining unpaid balance exists for Phase 3 test")

        payment_service = PaymentService()
        remaining = target["amount_paise"] - target["already_paid"]
        payment_amount = 100_000
        allocated_amount = min(remaining, min(40_000, max(10_000, target["amount_paise"] // 2)))
        payment_id = payment_service.record_payment(
            conn=conn,
            student_id=target["student_id"],
            payment_reference="PH3-A-VALID-0001",
            payment_date="2026-10-01",
            amount_paise=payment_amount,
            payment_method="UPI",
            status="cleared",
            transaction_id="PH3-A-VALID-0001",
        )
        payment_service.allocate_payment(
            conn=conn,
            payment_id=payment_id,
            line_id=target["line_id"],
            allocated_amount_paise=allocated_amount,
        )
        conn.commit()
    finally:
        conn.close()

    return db_path


def test_phase3_injects_all_five_anomaly_types(fresh_phase3_db: Path):
    injector = AnomalyInjector(fresh_phase3_db)
    ground_truth = injector.inject_all()

    assert len(ground_truth) == 5
    assert {gt.issue_type for gt in ground_truth} == {
        "PAYMENT_ALLOC_EXCEEDS_PAYMENT",
        "SCHOLARSHIP_EXCEEDS_FEES",
        "DUPLICATE_INVOICE",
        "REFUND_EXCEEDS_NET_PAID",
        "BALANCE_DISAGREES_LEDGER",
    }


def test_phase3_detector_matches_ground_truth(fresh_phase3_db: Path):
    injector = AnomalyInjector(fresh_phase3_db)
    ground_truth = injector.inject_all()
    detected = AnomalyDetector(fresh_phase3_db).run_all_checks()
    result = AnomalyEvaluator().evaluate(detected, ground_truth)

    assert result.ground_truth_count == 5
    assert result.detected_count == 5
    assert result.false_negatives == 0
    assert result.false_positives == 0
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1_score == 1.0


def test_phase3_ground_truth_survives_new_injector_and_repeat(fresh_phase3_db: Path):
    injector = AnomalyInjector(fresh_phase3_db)
    first = injector.inject_all()
    before = sqlite3.connect(fresh_phase3_db).execute(
        "SELECT COUNT(*) FROM AuditEvents WHERE notes LIKE 'ANOMALY-INJECTED-%'"
    ).fetchone()[0]

    persisted = AnomalyInjector(fresh_phase3_db).get_ground_truth()
    repeated = AnomalyInjector(fresh_phase3_db).inject_all()
    after = sqlite3.connect(fresh_phase3_db).execute(
        "SELECT COUNT(*) FROM AuditEvents WHERE notes LIKE 'ANOMALY-INJECTED-%'"
    ).fetchone()[0]

    assert len(first) == len(persisted) == len(repeated) == 5
    assert {record.issue_type for record in persisted} == {
        record.issue_type for record in first
    }
    assert before == after == 5


def test_evaluator_does_not_count_duplicate_detection_twice():
    from backend.anomaly.detector import DetectedIssue
    from backend.anomaly.injector import GroundTruthRecord

    label = GroundTruthRecord(
        issue_id="GT-PAYMENT-1",
        issue_type="PAYMENT_ALLOC_EXCEEDS_PAYMENT",
        entity_type="Payment",
        entity_id=1,
        related_ids={},
        description="Injected over-allocation",
    )
    detections = [
        DetectedIssue(
            issue_id=f"DET-{index}",
            issue_type=label.issue_type,
            entity_type="Payment",
            entity_id=1,
            related_ids={},
            severity="CRITICAL",
            message="Over-allocation",
            expected_value=100,
            actual_value=101,
            difference=1,
        )
        for index in range(2)
    ]

    result = AnomalyEvaluator().evaluate(detections, [label])

    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 0
    assert result.precision == 0.5


def test_phase3_reconciliation_detects_balance_mismatch(fresh_phase3_db: Path):
    injector = AnomalyInjector(fresh_phase3_db)
    injector.inject_all()

    from backend.reconciliation.reconciler import FinancialReconciler

    report = FinancialReconciler(fresh_phase3_db).reconcile_all()
    assert report.reconciliation_failures >= 1

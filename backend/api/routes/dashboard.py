from __future__ import annotations

import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_db
from backend.api.schemas import DashboardSummaryOut
from backend.reconciliation.reconciler import FinancialReconciler

router = APIRouter()


@router.get("/dashboard", response_model=DashboardSummaryOut, summary="Dashboard summary")
@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryOut,
    summary="Dashboard summary",
)
def dashboard_summary(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    """Return summary metrics derived from the live database."""
    try:
        students = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
        invoices = conn.execute("SELECT COUNT(*) FROM Invoices").fetchone()[0]
        payments = conn.execute("SELECT COUNT(*) FROM Payments").fetchone()[0]
        refunds = conn.execute("SELECT COUNT(*) FROM Refunds").fetchone()[0]
        scholarships = conn.execute("SELECT COUNT(*) FROM Scholarships").fetchone()[0]
        total_invoiced = conn.execute(
            """SELECT COALESCE(SUM(il.amount_paise), 0)
               FROM InvoiceLines il
               JOIN Invoices i ON i.invoice_id = il.invoice_id
               WHERE i.status NOT IN ('cancelled', 'refunded')
                 AND il.is_scholarship_credit = 0
                 AND il.amount_paise > 0"""
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
            "SELECT COALESCE(SUM(refund_amount_paise), 0) FROM Refunds WHERE status = 'processed'"
        ).fetchone()[0]
        db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
        reconciliation = FinancialReconciler(db_path).reconcile_all()
        outstanding = reconciliation.total_outstanding_paise
        return {
            "students": students,
            "invoices": invoices,
            "payments": payments,
            "refunds": refunds,
            "scholarships": scholarships,
            "total_invoiced_paise": total_invoiced,
            "total_invoiced_inr": total_invoiced / 100,
            "total_paid_paise": total_paid,
            "total_paid_inr": total_paid / 100,
            "total_refunded_paise": total_refunded,
            "total_refunded_inr": total_refunded / 100,
            "outstanding_paise": outstanding,
            "outstanding_inr": outstanding / 100,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dashboard summary unavailable: {exc}") from exc

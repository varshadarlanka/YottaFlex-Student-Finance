"""
backend/api/routes/global_views.py
====================================
Global list endpoints for invoices, payments, refunds, and student search.

These supplement the existing student-scoped endpoints so the frontend
can show all-records tables with pagination.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_db
from backend.api.schemas import PaginatedResponse
from backend.database.db_manager import EXPECTED_TABLES

router = APIRouter()


@router.get("/data-counts", summary="Get row counts for every database table")
def get_data_counts(conn: sqlite3.Connection = Depends(get_db)):
    """Return exact live row counts for all schema tables."""
    counts = {
        table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in EXPECTED_TABLES
    }
    return {"table_count": len(counts), "total_rows": sum(counts.values()), "tables": counts}


# -------------------------------------------------------------------
# Student search
# -------------------------------------------------------------------

@router.get("/students/search", response_model=PaginatedResponse, summary="Search students by name or code")
def search_students(
    q: Annotated[str, Query(min_length=1, description="Search query (name or student code)")],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Search students by first name, last name, or student code (case-insensitive)."""
    pattern = f"%{q}%"
    where = """WHERE (first_name LIKE ? OR last_name LIKE ? OR student_code LIKE ?
               OR (first_name || ' ' || last_name) LIKE ?)"""
    params = [pattern, pattern, pattern, pattern]
    offset = (page - 1) * page_size

    total = conn.execute(
        f"SELECT COUNT(*) FROM Students {where}", params
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM Students {where} ORDER BY student_id LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=[dict(r) for r in rows])


# -------------------------------------------------------------------
# All invoices
# -------------------------------------------------------------------

@router.get("/invoices", response_model=PaginatedResponse, summary="List all invoices")
def list_all_invoices(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[Optional[str], Query()] = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    where = "WHERE i.status = ?" if status else ""
    params = [status] if status else []

    total = conn.execute(
        f"SELECT COUNT(*) FROM Invoices i {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""SELECT i.invoice_id, i.invoice_number, i.enrollment_id, i.term_id,
                   i.issue_date, i.due_date, i.status, i.notes,
                   t.term_name, e.student_id,
                   s.student_code, s.first_name, s.last_name,
                   COALESCE((SELECT SUM(il.amount_paise) FROM InvoiceLines il
                             WHERE il.invoice_id = i.invoice_id), 0) AS total_paise,
                   COALESCE((SELECT SUM(pa.allocated_amount_paise)
                             FROM PaymentAllocations pa
                             JOIN InvoiceLines il2 ON il2.line_id = pa.line_id
                             JOIN Payments p ON p.payment_id = pa.payment_id
                             WHERE il2.invoice_id = i.invoice_id AND p.status = 'cleared'), 0) AS paid_paise
            FROM Invoices i
            JOIN Enrollments e ON e.enrollment_id = i.enrollment_id
            JOIN Students s ON s.student_id = e.student_id
            JOIN Terms t ON t.term_id = i.term_id
            {where}
            ORDER BY i.issue_date DESC, i.invoice_id DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d['total_inr'] = d['total_paise'] / 100
        d['paid_inr'] = d['paid_paise'] / 100
        d['outstanding_paise'] = max(0, d['total_paise'] - d['paid_paise'])
        d['outstanding_inr'] = d['outstanding_paise'] / 100
        items.append(d)
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


# -------------------------------------------------------------------
# All payments
# -------------------------------------------------------------------

@router.get("/payments", response_model=PaginatedResponse, summary="List all payments")
def list_all_payments(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[Optional[str], Query()] = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    where = "WHERE p.status = ?" if status else ""
    params = [status] if status else []

    total = conn.execute(
        f"SELECT COUNT(*) FROM Payments p {where}", params
    ).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""SELECT p.payment_id, p.payment_reference, p.student_id,
                   p.payment_date, p.amount_paise, p.payment_method,
                   p.transaction_id, p.bank_name, p.status,
                   s.student_code, s.first_name, s.last_name
            FROM Payments p
            JOIN Students s ON s.student_id = p.student_id
            {where}
            ORDER BY p.payment_date DESC, p.payment_id DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d['amount_inr'] = d['amount_paise'] / 100
        items.append(d)
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


# -------------------------------------------------------------------
# All refunds
# -------------------------------------------------------------------

@router.get("/refunds", response_model=PaginatedResponse, summary="List all refunds")
def list_all_refunds(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    conn: sqlite3.Connection = Depends(get_db),
):
    total = conn.execute("SELECT COUNT(*) FROM Refunds").fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        """SELECT r.refund_id, r.refund_reference, r.payment_id,
                  r.refund_date, r.refund_amount_paise, r.reason,
                  r.refund_method, r.status,
                  p.student_id,
                  s.student_code, s.first_name, s.last_name
           FROM Refunds r
           JOIN Payments p ON p.payment_id = r.payment_id
           JOIN Students s ON s.student_id = p.student_id
           ORDER BY r.refund_date DESC, r.refund_id DESC
           LIMIT ? OFFSET ?""",
        [page_size, offset],
    ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d['refund_amount_inr'] = d['refund_amount_paise'] / 100
        items.append(d)
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)

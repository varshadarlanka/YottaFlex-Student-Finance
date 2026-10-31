"""backend/api/routes/payments.py — Payment, allocation and refund endpoints."""
from __future__ import annotations

import sqlite3
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.api.deps import get_db
from backend.api.schemas import PaymentOut, AllocationOut, RefundOut, PaginatedResponse
from backend.services.finance_service import FinanceReadService

router = APIRouter()


@router.get(
    "/students/{student_id}/payments",
    response_model=PaginatedResponse,
    summary="List student payments",
)
def list_student_payments(
    student_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    conn: sqlite3.Connection = Depends(get_db),
):
    """List all payment transactions for a student, newest first."""
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    rows, total = FinanceReadService.list_student_payments(
        conn, student_id, page, page_size
    )
    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        items=[PaymentOut.from_row(r) for r in rows],
    )


@router.get(
    "/payments/{payment_id}/allocations",
    response_model=list[AllocationOut],
    summary="Get payment allocations",
)
def get_payment_allocations(
    payment_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return all invoice-line allocations for a specific payment."""
    pay = conn.execute(
        "SELECT payment_id FROM Payments WHERE payment_id = ?", (payment_id,)
    ).fetchone()
    if pay is None:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
    rows = FinanceReadService.get_payment_allocations(conn, payment_id)
    return [AllocationOut.from_row(r) for r in rows]


@router.get(
    "/students/{student_id}/refunds",
    response_model=list[RefundOut],
    summary="List student refunds",
)
def list_student_refunds(
    student_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return all refunds issued against this student's payments."""
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    rows = FinanceReadService.list_student_refunds(conn, student_id)
    return [RefundOut.from_row(r) for r in rows]

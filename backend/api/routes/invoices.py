"""backend/api/routes/invoices.py — Invoice and InvoiceLine endpoints."""
from __future__ import annotations

import sqlite3
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.api.deps import get_db
from backend.api.schemas import InvoiceOut, InvoiceDetailOut, PaginatedResponse
from backend.services.finance_service import FinanceReadService

router = APIRouter()


@router.get(
    "/students/{student_id}/invoices",
    response_model=PaginatedResponse,
    summary="List student invoices",
)
def list_student_invoices(
    student_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    conn: sqlite3.Connection = Depends(get_db),
):
    """List all invoices for a student, newest first."""
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    rows, total = FinanceReadService.list_student_invoices(conn, student_id, page, page_size)
    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        items=[InvoiceOut(**r) for r in rows],
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetailOut,
    summary="Get invoice details with lines",
)
def get_invoice(invoice_id: int, conn: sqlite3.Connection = Depends(get_db)):
    """Return invoice with all its line items, including scholarship credits."""
    data = FinanceReadService.get_invoice_with_lines(conn, invoice_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
    return InvoiceDetailOut.from_dict(data)

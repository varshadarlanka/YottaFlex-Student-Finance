"""backend/api/routes/balance.py — Student financial summary endpoint."""
from __future__ import annotations

import sqlite3
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.api.deps import get_db
from backend.api.schemas import FinancialSummaryOut
from backend.services.finance_service import FinanceReadService

router = APIRouter()


@router.get(
    "/students/{student_id}/balance",
    response_model=FinancialSummaryOut,
    summary="Get student financial summary",
)
def get_student_balance(
    student_id: int,
    term_id: Annotated[
        Optional[int],
        Query(description="Filter balance to a specific term"),
    ] = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Return the complete financial position for a student.

    Optionally filtered to a specific academic term.
    All amounts are derived from source records — never stored.

    Balance formula:
    - outstanding = max(0, net_payable − total_paid + total_refunded)
    - overpayment = max(0, total_paid − total_refunded − net_payable)
    - net_payable  = total_invoiced − scholarship_credits
    """
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")

    summary = FinanceReadService.get_financial_summary(conn, student_id, term_id)
    return FinancialSummaryOut(**summary)

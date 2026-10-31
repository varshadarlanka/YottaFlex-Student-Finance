"""backend/api/routes/scholarships.py — Scholarship and eligibility endpoints."""
from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from backend.api.deps import get_db
from backend.api.schemas import ScholarshipOut, EligibilityOut
from backend.services.finance_service import FinanceReadService

router = APIRouter()


@router.get(
    "/scholarships",
    response_model=list[ScholarshipOut],
    summary="List all scholarships",
)
def list_scholarships(conn: sqlite3.Connection = Depends(get_db)):
    """Return the scholarship master catalogue."""
    rows = FinanceReadService.list_scholarships(conn)
    return [ScholarshipOut.from_row(r) for r in rows]


@router.get(
    "/students/{student_id}/scholarships",
    response_model=list[EligibilityOut],
    summary="Get student scholarship eligibility",
)
def get_student_scholarships(
    student_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return all scholarship eligibility records for a student."""
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    rows = FinanceReadService.get_student_eligibility(conn, student_id)
    return [EligibilityOut.from_row(r) for r in rows]

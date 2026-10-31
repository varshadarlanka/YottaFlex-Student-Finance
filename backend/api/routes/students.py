"""
backend/api/routes/students.py
================================
Student list and detail endpoints.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_db
from backend.api.schemas import StudentOut, PaginatedResponse
from backend.services.finance_service import FinanceReadService

router = APIRouter()


@router.get("/students", response_model=PaginatedResponse, summary="List students")
def list_students(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="Items per page")] = 50,
    status: Annotated[Optional[str], Query(description="Filter by student status")] = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    List students with optional status filter and pagination.

    Valid statuses: active, inactive, graduated, withdrawn, suspended
    """
    if status and status not in (
        "active", "inactive", "graduated", "withdrawn", "suspended"
    ):
        raise HTTPException(status_code=422, detail=f"Invalid status: {status}")

    rows, total = FinanceReadService.list_students(conn, page, page_size, status)
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[StudentOut(**r) for r in rows],
    )


@router.get(
    "/students/{student_id}",
    response_model=StudentOut,
    summary="Get student details",
)
def get_student(
    student_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Get a single student by their numeric student_id."""
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return StudentOut(**student)


@router.get(
    "/students/{student_id}/enrollments",
    response_model=list,
    summary="Get student enrollments",
)
def get_student_enrollments(
    student_id: int,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return all enrollments for a student, including program and term info."""
    student = FinanceReadService.get_student(conn, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return FinanceReadService.get_student_enrollments(conn, student_id)

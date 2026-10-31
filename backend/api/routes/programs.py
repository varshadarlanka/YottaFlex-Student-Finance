"""backend/api/routes/programs.py — Program endpoints."""
from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from backend.api.deps import get_db
from backend.api.schemas import ProgramOut
from backend.services.finance_service import FinanceReadService

router = APIRouter()


@router.get("/programs", response_model=list[ProgramOut], summary="List all programs")
def list_programs(conn: sqlite3.Connection = Depends(get_db)):
    """Return all academic programmes."""
    rows = FinanceReadService.list_programs(conn)
    return [ProgramOut(**r) for r in rows]


@router.get("/programs/{program_id}", response_model=ProgramOut, summary="Get program details")
def get_program(program_id: int, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM Programs WHERE program_id = ?", (program_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Program {program_id} not found")
    return ProgramOut(**dict(row))

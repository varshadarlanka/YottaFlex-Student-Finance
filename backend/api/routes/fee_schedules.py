"""backend/api/routes/fee_schedules.py — Fee schedule and term endpoints for the frontend."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_db

router = APIRouter()


@router.get("/terms", summary="List all academic terms")
def list_terms(conn: sqlite3.Connection = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT term_id, term_code, term_name, start_date, end_date, is_active FROM Terms ORDER BY term_id"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/fee-schedules", summary="List all fee schedules with program and term info")
def list_fee_schedules(conn: sqlite3.Connection = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT fs.schedule_id, fs.program_id, fs.term_id, fs.schedule_name,
                  fs.effective_from, fs.effective_to, fs.status,
                  p.program_name, p.program_code,
                  t.term_name, t.term_code
           FROM FeeSchedules fs
           JOIN Programs p ON p.program_id = fs.program_id
           JOIN Terms t ON t.term_id = fs.term_id
           ORDER BY fs.schedule_id"""
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/fee-schedules/{schedule_id}/lines", summary="Get fee schedule line items")
def get_fee_schedule_lines(
    schedule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> List[Dict[str, Any]]:
    fs = conn.execute(
        "SELECT schedule_id FROM FeeSchedules WHERE schedule_id = ?", (schedule_id,)
    ).fetchone()
    if fs is None:
        raise HTTPException(status_code=404, detail=f"Fee schedule {schedule_id} not found")
    rows = conn.execute(
        """SELECT fsl_id, schedule_id, fee_type, description, amount_paise,
                  is_mandatory, sort_order
           FROM FeeScheduleLines
           WHERE schedule_id = ?
           ORDER BY sort_order, fsl_id""",
        (schedule_id,),
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['amount_inr'] = d['amount_paise'] / 100
        result.append(d)
    return result

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_db
from backend.reconciliation.reconciler import FinancialReconciler

router = APIRouter()


@router.get("/reconciliation", summary="Financial reconciliation report")
def reconciliation_report(
    term_id: Optional[int] = Query(default=None),
    student_id: Optional[int] = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> Dict[str, Any]:
    db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
    reconciler = FinancialReconciler(db_path)
    report = reconciler.reconcile_all(term_id=term_id, student_ids=[student_id] if student_id else None)
    return {
        "summary": report.summary_dict(),
        "records": [r.as_dict() for r in report.records],
    }

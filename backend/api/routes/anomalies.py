from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from backend.anomaly.detector import AnomalyDetector
from backend.anomaly.evaluator import AnomalyEvaluator
from backend.anomaly.injector import AnomalyInjector
from backend.api.deps import get_db

router = APIRouter()


@router.get("/anomalies/detect", summary="Detect anomalies in the current database")
def detect_anomalies(conn: sqlite3.Connection = Depends(get_db)) -> List[Dict[str, Any]]:
    issues = AnomalyDetector(conn.execute("PRAGMA database_list").fetchall()[0][2]).run_all_checks()
    return [issue.as_dict() for issue in issues]


@router.post("/anomalies/inject", summary="Inject the five baseline anomalies")
def inject_anomalies(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
    injector = AnomalyInjector(db_path)
    ground_truth = injector.inject_all()
    return {"injected": len(ground_truth), "issue_types": [gt.issue_type for gt in ground_truth]}


@router.get("/anomalies/evaluate", summary="Evaluate detected issues against ground truth")
def evaluate_anomalies(conn: sqlite3.Connection = Depends(get_db)) -> Dict[str, Any]:
    db_path = conn.execute("PRAGMA database_list").fetchall()[0][2]
    injector = AnomalyInjector(db_path)
    ground_truth = injector.get_ground_truth()
    if not ground_truth:
        ground_truth = injector.inject_all()
    issues = AnomalyDetector(db_path).run_all_checks()
    result = AnomalyEvaluator().evaluate(issues, ground_truth)
    return result.as_dict()

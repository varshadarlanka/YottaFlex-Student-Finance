"""
backend/api/deps.py
====================
FastAPI dependency injection helpers.
"""
from __future__ import annotations

import sqlite3
from typing import Generator

from fastapi import HTTPException

from backend.database.db_manager import DatabaseManager, DEFAULT_DB_PATH


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Yield a database connection per request.
    Commits on clean exit, rolls back on exception.
    """
    manager = DatabaseManager(db_path=DEFAULT_DB_PATH)
    conn = manager._raw_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def require_student(conn: sqlite3.Connection, student_id: int) -> dict:
    """Raise 404 if student does not exist."""
    row = conn.execute(
        "SELECT * FROM Students WHERE student_id = ?", (student_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return dict(row)

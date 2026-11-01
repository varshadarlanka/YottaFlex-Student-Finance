"""
backend/api/__init__.py
========================
FastAPI application factory for Student Finance Management.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.routes import (
    students,
    programs,
    invoices,
    scholarships,
    payments,
    balance,
    dashboard,
    anomalies,
    reconciliation,
    exports,
    fee_schedules,
    global_views,
)
from backend.database.db_manager import DatabaseManager, DEFAULT_DB_PATH

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = DatabaseManager(db_path=DEFAULT_DB_PATH)
    manager.initialise()
    if manager.db_path.exists():
        conn = manager._raw_connection()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("SELECT 1 FROM Students LIMIT 1")
            logger.info("Database warmed up (WAL mode, busy_timeout set).")
        except Exception as exc:
            logger.warning("Database warm-up query failed: %s", exc)
        finally:
            conn.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Student Finance Management API",
        description=(
            "RESTful API for the YottaFlex Student Finance Management system. "
            "Provides endpoints for students, programs, invoices, scholarships, "
            "payments, and financial summaries."
        ),
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Register routers — global_views first so /students/search is matched
    # before /students/{student_id}
    app.include_router(global_views.router, prefix="/api/v1", tags=["Global Views"])
    app.include_router(students.router, prefix="/api/v1", tags=["Students"])
    app.include_router(programs.router, prefix="/api/v1", tags=["Programs"])
    app.include_router(invoices.router, prefix="/api/v1", tags=["Invoices"])
    app.include_router(scholarships.router, prefix="/api/v1", tags=["Scholarships"])
    app.include_router(payments.router, prefix="/api/v1", tags=["Payments"])
    app.include_router(balance.router, prefix="/api/v1", tags=["Balance"])
    app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
    app.include_router(anomalies.router, prefix="/api/v1", tags=["Anomalies"])
    app.include_router(reconciliation.router, prefix="/api/v1", tags=["Reconciliation"])
    app.include_router(exports.router, prefix="/api/v1", tags=["Exports"])
    app.include_router(fee_schedules.router, prefix="/api/v1", tags=["Fee Schedules"])

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "service": "student-finance-management"}

    return app


app = create_app()

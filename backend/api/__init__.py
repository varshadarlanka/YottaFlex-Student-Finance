"""
backend/api/__init__.py
========================
FastAPI application factory for Student Finance Management.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.routes import (
    students,
    programs,
    invoices,
    scholarships,
    payments,
    balance,
)


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
    )

    # Register routers
    app.include_router(students.router, prefix="/api/v1", tags=["Students"])
    app.include_router(programs.router, prefix="/api/v1", tags=["Programs"])
    app.include_router(invoices.router, prefix="/api/v1", tags=["Invoices"])
    app.include_router(scholarships.router, prefix="/api/v1", tags=["Scholarships"])
    app.include_router(payments.router, prefix="/api/v1", tags=["Payments"])
    app.include_router(balance.router, prefix="/api/v1", tags=["Balance"])

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "service": "student-finance-management"}

    return app


app = create_app()

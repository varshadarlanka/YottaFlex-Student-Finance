# backend/database/__init__.py
"""
Student Finance Management — database package.

Exposes the DatabaseManager and ORM-like model dataclasses so that
other packages can import directly from `backend.database`.
"""

from .db_manager import DatabaseManager
from .models import (
    Term,
    Program,
    Student,
    FeeSchedule,
    FeeScheduleLine,
    Enrollment,
    Invoice,
    InvoiceLine,
    Scholarship,
    Eligibility,
    Payment,
    PaymentAllocation,
    Refund,
    AuditEvent,
)

__all__ = [
    "DatabaseManager",
    "Term",
    "Program",
    "Student",
    "FeeSchedule",
    "FeeScheduleLine",
    "Enrollment",
    "Invoice",
    "InvoiceLine",
    "Scholarship",
    "Eligibility",
    "Payment",
    "PaymentAllocation",
    "Refund",
    "AuditEvent",
]

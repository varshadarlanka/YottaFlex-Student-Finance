"""
backend/api/schemas.py
=======================
Pydantic v2 response schemas for the Student Finance Management API.

All monetary values are provided in BOTH paise (integer) and INR (float)
for convenience.  The paise values are authoritative.
"""
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------


class StudentOut(BaseModel):
    student_id: int
    student_code: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: Optional[str] = None
    email: str
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    status: str
    created_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


class ProgramOut(BaseModel):
    program_id: int
    program_code: str
    program_name: str
    department: Optional[str] = None
    duration_years: int
    level: str
    is_active: int

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------


class EnrollmentOut(BaseModel):
    enrollment_id: int
    student_id: int
    program_id: int
    term_id: int
    enrollment_date: str
    status: str
    year_of_study: int
    fee_schedule_id: Optional[int] = None
    program_name: Optional[str] = None
    program_code: Optional[str] = None
    level: Optional[str] = None
    term_name: Optional[str] = None
    term_code: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


class InvoiceLineOut(BaseModel):
    line_id: int
    invoice_id: int
    fee_type: str
    description: Optional[str] = None
    amount_paise: int
    amount_inr: float = 0.0
    is_scholarship_credit: int
    fsl_id: Optional[int] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: dict) -> "InvoiceLineOut":
        row = dict(row)
        row["amount_inr"] = row["amount_paise"] / 100
        return cls(**row)


class InvoiceOut(BaseModel):
    invoice_id: int
    invoice_number: str
    enrollment_id: int
    term_id: int
    issue_date: str
    due_date: str
    status: str
    notes: Optional[str] = None
    term_name: Optional[str] = None

    model_config = {"from_attributes": True}


class InvoiceDetailOut(InvoiceOut):
    lines: List[InvoiceLineOut] = []
    total_paise: int = 0
    total_inr: float = 0.0

    model_config = {"from_attributes": True}

    @classmethod
    def from_dict(cls, d: dict) -> "InvoiceDetailOut":
        lines = [InvoiceLineOut.from_row(l) for l in d.get("lines", [])]
        total = d.get("total_paise", 0)
        return cls(
            **{k: v for k, v in d.items() if k not in ("lines", "total_paise")},
            lines=lines,
            total_paise=total,
            total_inr=total / 100,
        )


# ---------------------------------------------------------------------------
# Scholarships
# ---------------------------------------------------------------------------


class ScholarshipOut(BaseModel):
    scholarship_id: int
    scholarship_code: str
    scholarship_name: str
    description: Optional[str] = None
    scholarship_type: str
    max_amount_paise: Optional[int] = None
    max_amount_inr: Optional[float] = None
    percentage_discount: Optional[float] = None
    is_renewable: int
    is_active: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: dict) -> "ScholarshipOut":
        row = dict(row)
        if row.get("max_amount_paise") is not None:
            row["max_amount_inr"] = row["max_amount_paise"] / 100
        return cls(**row)


class EligibilityOut(BaseModel):
    eligibility_id: int
    student_id: int
    scholarship_id: int
    term_id: int
    enrollment_id: Optional[int] = None
    awarded_amount_paise: int
    awarded_amount_inr: float = 0.0
    status: str
    applied_date: str
    approved_date: Optional[str] = None
    disbursed_date: Optional[str] = None
    scholarship_name: Optional[str] = None
    scholarship_code: Optional[str] = None
    scholarship_type: Optional[str] = None
    term_name: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: dict) -> "EligibilityOut":
        row = dict(row)
        row["awarded_amount_inr"] = row["awarded_amount_paise"] / 100
        return cls(**row)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


class PaymentOut(BaseModel):
    payment_id: int
    payment_reference: str
    student_id: int
    payment_date: str
    amount_paise: int
    amount_inr: float = 0.0
    payment_method: str
    status: str
    transaction_id: Optional[str] = None
    bank_name: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: dict) -> "PaymentOut":
        row = dict(row)
        row["amount_inr"] = row["amount_paise"] / 100
        return cls(**row)


class AllocationOut(BaseModel):
    allocation_id: int
    payment_id: int
    line_id: int
    allocated_amount_paise: int
    allocated_amount_inr: float = 0.0
    allocated_at: str
    fee_type: Optional[str] = None
    line_amount: Optional[int] = None
    invoice_number: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: dict) -> "AllocationOut":
        row = dict(row)
        row["allocated_amount_inr"] = row["allocated_amount_paise"] / 100
        return cls(**row)


class RefundOut(BaseModel):
    refund_id: int
    refund_reference: str
    payment_id: int
    refund_date: str
    refund_amount_paise: int
    refund_amount_inr: float = 0.0
    reason: str
    refund_method: str
    status: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: dict) -> "RefundOut":
        row = dict(row)
        row["refund_amount_inr"] = row["refund_amount_paise"] / 100
        return cls(**row)


# ---------------------------------------------------------------------------
# Balance / Financial Summary
# ---------------------------------------------------------------------------


class FinancialSummaryOut(BaseModel):
    student_id: int
    student_code: Optional[str] = None
    student_name: Optional[str] = None
    term_id: Optional[int] = None
    total_invoiced_paise: int
    total_invoiced_inr: float
    scholarship_credits_paise: int
    scholarship_credits_inr: float
    net_payable_paise: int
    net_payable_inr: float
    total_paid_paise: int
    total_paid_inr: float
    total_refunded_paise: int
    total_refunded_inr: float
    outstanding_paise: int
    outstanding_inr: float
    overdue_paise: int
    overdue_inr: float
    overpayment_paise: int
    overpayment_inr: float

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ErrorOut(BaseModel):
    detail: str

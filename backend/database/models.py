"""
backend/database/models.py
============================
Python dataclasses mirroring each database table.

Design principles
-----------------
* One dataclass per table.  Field names match column names exactly so
  that ``dict(sqlite3.Row)`` can be unpacked directly with ``**row``.
* Monetary amounts are typed as ``int`` (paise).  No floats.
* Optional columns are typed ``Optional[...]`` with default ``None``.
* Statuses are typed as ``str`` rather than Enum to keep the models
  database-agnostic; validation belongs in service-layer code.
* ``created_at`` / ``updated_at`` are ``str`` (ISO-8601 TEXT from SQLite).
* Dataclasses are intentionally plain (no ORM magic) for maximum
  portability — they can be serialised to JSON, fed into APIs, or
  converted to other formats without import dependencies.

Financial note
--------------
All ``amount_paise`` / ``awarded_amount_paise`` / ``refund_amount_paise`` /
``allocated_amount_paise`` fields store **integer paise**.
To convert to INR: divide by 100.
To convert from INR: multiply by 100 and round to nearest integer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Supporting tables
# ---------------------------------------------------------------------------


@dataclass
class Term:
    """Represents one academic period (e.g. "2024 Odd Semester")."""

    term_id: Optional[int]          # None before DB insert
    term_code: str                  # Unique institutional code e.g. "2024-SEM1"
    term_name: str
    start_date: str                 # YYYY-MM-DD
    end_date: str                   # YYYY-MM-DD
    is_active: int = 1              # 1 = active, 0 = closed
    created_at: Optional[str] = None


@dataclass
class Program:
    """Academic programme offered by the institution."""

    program_id: Optional[int]
    program_code: str               # Unique e.g. "BTECH-CSE"
    program_name: str
    duration_years: int
    level: str                      # "UG" | "PG" | "PhD" | "Diploma" | "Certificate"
    department: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Core entity tables
# ---------------------------------------------------------------------------


@dataclass
class Student:
    """
    Core student identity record.

    Financial state is never stored here — it is derived from Invoices,
    Payments, and PaymentAllocations.
    """

    student_id: Optional[int]
    student_code: str               # Unique institutional ID
    first_name: str
    last_name: str
    date_of_birth: str              # YYYY-MM-DD
    email: str                      # Unique
    gender: Optional[str] = None    # "M" | "F" | "O"
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    status: str = "active"          # active | inactive | graduated | withdrawn | suspended
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class FeeSchedule:
    """
    Versioned fee structure for a (Program, Term) combination.

    A single programme can have multiple FeeSchedules across terms, or
    multiple versions within one term (only one should be 'active').
    """

    schedule_id: Optional[int]
    program_id: int
    term_id: int
    schedule_name: str
    effective_from: str             # YYYY-MM-DD
    effective_to: Optional[str] = None
    status: str = "active"          # draft | active | superseded | archived
    created_at: Optional[str] = None


@dataclass
class FeeScheduleLine:
    """Individual fee component within a FeeSchedule."""

    fsl_id: Optional[int]
    schedule_id: int
    fee_type: str                   # "Tuition" | "Lab" | "Library" | …
    amount_paise: int               # ≥ 0; in paise
    description: Optional[str] = None
    is_mandatory: int = 1           # 1 = mandatory, 0 = optional
    sort_order: int = 0
    created_at: Optional[str] = None


@dataclass
class Enrollment:
    """
    Links a Student to a Program for one Term.

    One student may have multiple enrollments (different terms or
    different programmes — though the UNIQUE constraint on
    (student_id, program_id, term_id) prevents duplicates in the DB).
    """

    enrollment_id: Optional[int]
    student_id: int
    program_id: int
    term_id: int
    enrollment_date: str            # YYYY-MM-DD
    status: str = "enrolled"        # enrolled | completed | withdrawn | suspended | deferred
    year_of_study: int = 1
    fee_schedule_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Invoice:
    """
    Billing document generated per (Enrollment, Term).

    **Outstanding balance is DERIVED, not stored:**
    ::

        balance = sum(InvoiceLines.amount_paise)
                - sum(PaymentAllocations.allocated_amount_paise)
                  [for allocations on this invoice's lines]

    Never store a separately computed balance column here.
    """

    invoice_id: Optional[int]
    invoice_number: str             # Unique human-readable reference
    enrollment_id: int
    term_id: int
    issue_date: str                 # YYYY-MM-DD
    due_date: str                   # YYYY-MM-DD; ≥ issue_date
    status: str = "draft"           # draft | issued | partially_paid | paid |
                                    # overdue | cancelled | refunded
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class InvoiceLine:
    """
    A single charge or credit item on an Invoice.

    ``amount_paise`` may be negative for credit/scholarship lines
    (``is_scholarship_credit = 1``).  Charge lines must be ≥ 0.
    """

    line_id: Optional[int]
    invoice_id: int
    fee_type: str                   # "Tuition" | "Lab" | "Scholarship Credit" | …
    amount_paise: int               # negative for credit lines
    description: Optional[str] = None
    is_scholarship_credit: int = 0  # 1 = credit line
    fsl_id: Optional[int] = None    # traceable back to FeeScheduleLines
    created_at: Optional[str] = None


@dataclass
class Scholarship:
    """Master catalogue entry for a scholarship or grant."""

    scholarship_id: Optional[int]
    scholarship_code: str           # Unique e.g. "MERIT-GOLD"
    scholarship_name: str
    scholarship_type: str           # Merit | Need-based | Government | Sports |
                                    # Minority | Special | Other
    description: Optional[str] = None
    max_amount_paise: Optional[int] = None   # cap; actual award is in Eligibility
    percentage_discount: Optional[float] = None  # 0–100; alternative to fixed amount
    is_renewable: int = 0
    is_active: int = 1
    created_at: Optional[str] = None


@dataclass
class Eligibility:
    """
    Bridge connecting a Student to a Scholarship for a given Term.

    Stores the actual awarded amount (within the scholarship's cap).
    UNIQUE on (student_id, scholarship_id, term_id).
    """

    eligibility_id: Optional[int]
    student_id: int
    scholarship_id: int
    term_id: int
    awarded_amount_paise: int       # ≥ 0; in paise
    status: str = "pending"         # pending | approved | disbursed | rejected | cancelled
    applied_date: str = ""          # YYYY-MM-DD
    enrollment_id: Optional[int] = None
    approved_date: Optional[str] = None
    disbursed_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Payment:
    """
    A payment transaction made by a student.

    Payments are linked to a *student* (not directly to an invoice) so
    they can be allocated across one or more invoice lines via
    PaymentAllocations.

    ``amount_paise`` must be > 0 (enforced by DB CHECK constraint).
    """

    payment_id: Optional[int]
    payment_reference: str          # Unique e.g. "PAY-2024-00001"
    student_id: int
    payment_date: str               # YYYY-MM-DD
    amount_paise: int               # > 0; in paise
    payment_method: str             # Cash | UPI | NetBanking | ChequeDD |
                                    # CardDebit | CardCredit | NEFT | RTGS | Other
    status: str = "pending"         # pending | cleared | failed | reversed | refunded
    transaction_id: Optional[str] = None
    bank_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class PaymentAllocation:
    """
    Allocates a portion of a Payment to a specific InvoiceLine.

    Many-to-many bridge between Payments and InvoiceLines.
    UNIQUE on (payment_id, line_id) — a payment can only be applied
    to each invoice line once.

    Cross-student allocation is prevented at the service level via
    ``DatabaseManager.validate_allocation()``.
    """

    allocation_id: Optional[int]
    payment_id: int
    line_id: int
    allocated_amount_paise: int     # > 0; in paise
    allocated_at: Optional[str] = None


@dataclass
class Refund:
    """
    A refund issued against a specific Payment.

    Partial refunds are supported.  Multiple refunds per payment are
    allowed, but the total of all refunds must not exceed the payment
    amount (enforced at service level).
    """

    refund_id: Optional[int]
    refund_reference: str           # Unique e.g. "REF-2024-00001"
    payment_id: int
    refund_date: str                # YYYY-MM-DD
    refund_amount_paise: int        # > 0; in paise
    reason: str
    refund_method: str              # Cash | UPI | NetBanking | …
    status: str = "pending"         # pending | processed | failed | cancelled
    processed_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class BalanceSnapshot:
    """Stored point-in-time balance used for reconciliation checks."""

    snapshot_id: Optional[int]
    student_id: int
    term_id: int
    reported_outstanding_paise: int
    snapshot_date: Optional[str] = None


@dataclass
class AuditEvent:
    """
    Immutable audit trail record.

    Rows are NEVER updated or deleted — only inserted.  The entity_type
    and entity_id identify the affected record; old_value / new_value
    store JSON snapshots of what changed.
    """

    audit_id: Optional[int]
    entity_type: str                # "Student" | "Invoice" | "Payment" | …
    entity_id: int
    event_type: str                 # "CREATE" | "STATUS_CHANGE" | "UPDATE" | …
    performed_at: Optional[str] = None
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    performed_by: Optional[str] = None
    notes: Optional[str] = None

"""
backend/validators.py
=====================
Validation utilities for the Student Finance Management backend.

These functions are called by service-layer code and by tests to verify
generated data before and after database insertion.

None of these functions modify the database — they only raise exceptions
or return True/False.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.config import (
    ENROLLMENT_STATUSES,
    FEE_SCHEDULE_STATUSES,
    INVOICE_STATUSES,
    PAYMENT_METHODS,
    PAYMENT_STATUSES,
    PROGRAM_LEVELS,
    REFUND_STATUSES,
    SCHOLARSHIP_TYPES,
    STUDENT_STATUSES,
)

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when a data validation rule is violated."""


def require(condition: bool, message: str) -> None:
    """Raise ValidationError with *message* if *condition* is False."""
    if not condition:
        raise ValidationError(message)


# ---------------------------------------------------------------------------
# Field-level validators
# ---------------------------------------------------------------------------


def validate_date_string(value: str, field_name: str = "date") -> date:
    """
    Parse an ISO-8601 date string (YYYY-MM-DD) and return a date object.

    Raises
    ------
    ValidationError
        If the string cannot be parsed as a valid date.
    """
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            f"{field_name} must be a valid YYYY-MM-DD date string; got: {value!r}"
        ) from exc


def validate_date_range(
    start_str: str,
    end_str: str,
    start_name: str = "start_date",
    end_name: str = "end_date",
) -> Tuple[date, date]:
    """
    Validate that *end* > *start* and return both as date objects.

    Raises
    ------
    ValidationError
    """
    start = validate_date_string(start_str, start_name)
    end = validate_date_string(end_str, end_name)
    require(end > start, f"{end_name} ({end}) must be after {start_name} ({start})")
    return start, end


def validate_paise(value: Any, field_name: str = "amount_paise", allow_zero: bool = True) -> int:
    """
    Validate that *value* is a non-negative integer representing paise.

    Parameters
    ----------
    allow_zero : bool
        If True, 0 is valid.  If False, value must be > 0.

    Raises
    ------
    ValidationError
    """
    require(isinstance(value, int), f"{field_name} must be an integer (paise); got {type(value).__name__}")
    if allow_zero:
        require(value >= 0, f"{field_name} must be >= 0; got {value}")
    else:
        require(value > 0, f"{field_name} must be > 0; got {value}")
    return value


def validate_status(value: str, allowed: List[str], field_name: str = "status") -> str:
    """
    Validate that *value* is in the allowed status list.

    Raises
    ------
    ValidationError
    """
    require(
        value in allowed,
        f"{field_name} must be one of {allowed}; got {value!r}",
    )
    return value


def validate_email(email: str) -> str:
    """
    Basic email format check (not RFC 5322 complete — just sanity check).

    Raises
    ------
    ValidationError
    """
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    require(bool(re.match(pattern, email)), f"Invalid email format: {email!r}")
    return email


# ---------------------------------------------------------------------------
# Entity-level validators
# ---------------------------------------------------------------------------


def validate_student_row(row: Dict[str, Any]) -> None:
    """Validate a student dict before insertion."""
    require("student_code" in row and row["student_code"], "student_code is required")
    require("first_name" in row and row["first_name"], "first_name is required")
    require("last_name" in row and row["last_name"], "last_name is required")
    require("email" in row and row["email"], "email is required")
    validate_email(row["email"])
    validate_date_string(row.get("date_of_birth", ""), "date_of_birth")
    validate_status(row.get("status", "active"), STUDENT_STATUSES, "student status")


def validate_program_row(row: Dict[str, Any]) -> None:
    """Validate a program dict before insertion."""
    require("program_code" in row and row["program_code"], "program_code is required")
    require("program_name" in row and row["program_name"], "program_name is required")
    require(
        isinstance(row.get("duration_years"), int) and row["duration_years"] > 0,
        "duration_years must be a positive integer",
    )
    validate_status(row.get("level", ""), PROGRAM_LEVELS, "program level")


def validate_term_row(row: Dict[str, Any]) -> None:
    """Validate a term dict before insertion."""
    require("term_code" in row and row["term_code"], "term_code is required")
    require("term_name" in row and row["term_name"], "term_name is required")
    validate_date_range(row["start_date"], row["end_date"])


def validate_fee_schedule_row(row: Dict[str, Any]) -> None:
    """Validate a fee schedule dict before insertion."""
    require(isinstance(row.get("program_id"), int), "program_id must be int")
    require(isinstance(row.get("term_id"), int), "term_id must be int")
    require("schedule_name" in row and row["schedule_name"], "schedule_name is required")
    validate_date_string(row["effective_from"], "effective_from")
    validate_status(row.get("status", "active"), FEE_SCHEDULE_STATUSES, "fee schedule status")


def validate_fee_schedule_line_row(row: Dict[str, Any]) -> None:
    """Validate a fee schedule line dict before insertion."""
    require(isinstance(row.get("schedule_id"), int), "schedule_id must be int")
    require("fee_type" in row and row["fee_type"], "fee_type is required")
    validate_paise(row.get("amount_paise"), "amount_paise", allow_zero=True)


def validate_enrollment_row(row: Dict[str, Any]) -> None:
    """Validate an enrollment dict before insertion."""
    require(isinstance(row.get("student_id"), int), "student_id must be int")
    require(isinstance(row.get("program_id"), int), "program_id must be int")
    require(isinstance(row.get("term_id"), int), "term_id must be int")
    validate_date_string(row.get("enrollment_date", ""), "enrollment_date")
    validate_status(
        row.get("status", "enrolled"), ENROLLMENT_STATUSES, "enrollment status"
    )
    require(
        isinstance(row.get("year_of_study", 1), int) and row["year_of_study"] >= 1,
        "year_of_study must be >= 1",
    )


# ---------------------------------------------------------------------------
# Post-generation integrity checks (run against the live DB)
# ---------------------------------------------------------------------------


def verify_integrity(conn: sqlite3.Connection) -> List[str]:
    """
    Run a suite of post-generation integrity checks against the database.

    Returns
    -------
    list[str]
        List of violation messages.  Empty list means all checks passed.
    """
    violations: List[str] = []

    def check(sql: str, label: str) -> None:
        count = conn.execute(sql).fetchone()[0]
        if count > 0:
            violations.append(f"{label}: {count} violation(s)")

    # Orphaned enrollments (student not in Students)
    check(
        """SELECT COUNT(*) FROM Enrollments e
           WHERE NOT EXISTS (SELECT 1 FROM Students s WHERE s.student_id = e.student_id)""",
        "Enrollments with missing student_id",
    )

    # Orphaned enrollments (program not in Programs)
    check(
        """SELECT COUNT(*) FROM Enrollments e
           WHERE NOT EXISTS (SELECT 1 FROM Programs p WHERE p.program_id = e.program_id)""",
        "Enrollments with missing program_id",
    )

    # Orphaned enrollments (term not in Terms)
    check(
        """SELECT COUNT(*) FROM Enrollments e
           WHERE NOT EXISTS (SELECT 1 FROM Terms t WHERE t.term_id = e.term_id)""",
        "Enrollments with missing term_id",
    )

    # Duplicate student codes
    check(
        """SELECT COUNT(*) FROM (
               SELECT student_code FROM Students GROUP BY student_code HAVING COUNT(*) > 1
           )""",
        "Duplicate student_code values",
    )

    # Duplicate emails
    check(
        """SELECT COUNT(*) FROM (
               SELECT email FROM Students GROUP BY email HAVING COUNT(*) > 1
           )""",
        "Duplicate student email values",
    )

    # Duplicate program codes
    check(
        """SELECT COUNT(*) FROM (
               SELECT program_code FROM Programs GROUP BY program_code HAVING COUNT(*) > 1
           )""",
        "Duplicate program_code values",
    )

    # Duplicate term codes
    check(
        """SELECT COUNT(*) FROM (
               SELECT term_code FROM Terms GROUP BY term_code HAVING COUNT(*) > 1
           )""",
        "Duplicate term_code values",
    )

    # Fee schedule lines with non-integer or negative amount_paise
    check(
        """SELECT COUNT(*) FROM FeeScheduleLines
           WHERE amount_paise < 0 OR typeof(amount_paise) != 'integer'""",
        "FeeScheduleLines with invalid amount_paise",
    )

    # Terms with invalid date ordering
    check(
        """SELECT COUNT(*) FROM Terms WHERE end_date <= start_date""",
        "Terms with end_date <= start_date",
    )

    # FeeSchedules with invalid effective_from
    check(
        """SELECT COUNT(*) FROM FeeSchedules WHERE effective_from IS NULL OR effective_from = ''""",
        "FeeSchedules with missing effective_from",
    )

    # Orphaned FeeScheduleLines
    check(
        """SELECT COUNT(*) FROM FeeScheduleLines fsl
           WHERE NOT EXISTS (SELECT 1 FROM FeeSchedules fs WHERE fs.schedule_id = fsl.schedule_id)""",
        "FeeScheduleLines with missing schedule_id",
    )

    return violations

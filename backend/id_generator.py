"""
backend/id_generator.py
========================
Deterministic ID generation for all entities.

Requirements
------------
* IDs must be unique.
* IDs must be reproducible for the same seed + configuration.
* No random UUIDs.
* No timestamp-based IDs.
* IDs are generated from a sequential counter, zero-padded to a fixed width,
  prefixed per entity type.

Conventions
-----------
| Entity          | Format              | Example               |
|-----------------|---------------------|-----------------------|
| Student         | STU-{n:06d}         | STU-000001            |
| Program         | PROG-{code}         | PROG-BTECH-CSE        |
| Term            | TERM-{year}-{name}  | TERM-2026-FALL        |
| Enrollment      | ENR-{n:08d}         | ENR-00000001          |
| FeeSchedule     | FS-{prog}-{term}    | FS-PROG01-TERM-2026-FALL |
| InvoiceNumber   | INV-{n:08d}         | INV-00000001          |
| PaymentRef      | PAY-{n:08d}         | PAY-00000001          |
| RefundRef       | REF-{n:08d}         | REF-00000001          |
| ScholarshipCode | SC-{type}-{n:04d}   | SC-MERIT-0001         |

All counters start at 1.
"""

from __future__ import annotations


class IDGenerator:
    """
    Stateful counter-based ID generator.

    Create one instance per generation session.  Pass it to every
    generator so all IDs remain globally sequential and unique within
    a generation run.

    The generator is NOT thread-safe; use a single instance per process.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def _next(self, prefix: str) -> int:
        """Increment and return the next counter value for *prefix*."""
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return self._counters[prefix]

    # ------------------------------------------------------------------
    # Entity-specific generators
    # ------------------------------------------------------------------

    def student_code(self) -> str:
        """Return next student code: STU-000001, STU-000002, …"""
        return f"STU-{self._next('STU'):06d}"

    def enrollment_id_code(self) -> str:
        """Return next enrollment reference: ENR-00000001, …"""
        return f"ENR-{self._next('ENR'):08d}"

    def invoice_number(self) -> str:
        """Return next invoice number: INV-00000001, …"""
        return f"INV-{self._next('INV'):08d}"

    def payment_reference(self) -> str:
        """Return next payment reference: PAY-00000001, …"""
        return f"PAY-{self._next('PAY'):08d}"

    def refund_reference(self) -> str:
        """Return next refund reference: REF-00000001, …"""
        return f"REF-{self._next('REF'):08d}"

    def scholarship_code(self, stype: str) -> str:
        """Return next scholarship code: SC-MERIT-0001, …"""
        key = f"SC-{stype.upper()}"
        return f"{key}-{self._next(key):04d}"

    def reset(self, prefix: str | None = None) -> None:
        """
        Reset counter(s).

        Parameters
        ----------
        prefix : str | None
            Reset only this prefix if given; reset all counters if None.
        """
        if prefix is None:
            self._counters.clear()
        else:
            self._counters.pop(prefix, None)

    def current(self, prefix: str) -> int:
        """Return current counter value without incrementing (0 if unused)."""
        return self._counters.get(prefix, 0)


# ---------------------------------------------------------------------------
# Stateless helpers for fixed IDs derived from business keys
# (no counter state required)
# ---------------------------------------------------------------------------


def make_program_code(index: int, slug: str) -> str:
    """
    Build a stable program code from an index and a slug.

    Examples
    --------
    >>> make_program_code(1, "BTECH-CSE")
    'PROG-01-BTECH-CSE'
    """
    return f"PROG-{index:02d}-{slug}"


def make_term_code(year: int, season: str) -> str:
    """
    Build a term code from year and season name.

    Examples
    --------
    >>> make_term_code(2026, "FALL")
    'TERM-2026-FALL'
    """
    return f"TERM-{year}-{season.upper()}"


def make_fee_schedule_code(program_code: str, term_code: str) -> str:
    """
    Build a fee schedule name from program and term codes.

    Examples
    --------
    >>> make_fee_schedule_code("PROG-01-BTECH-CSE", "TERM-2026-FALL")
    'FS-PROG-01-BTECH-CSE-TERM-2026-FALL'
    """
    return f"FS-{program_code}-{term_code}"

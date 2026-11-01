"""
tests/test_database.py
======================
Comprehensive test suite for the Student Finance Management database layer.

All tests use a temporary SQLite database created in a pytest tmp_path
fixture — the production database at backend/database/student_finance.db
is never touched.

Test categories
---------------
1.  Initialisation — DB file created, schema applied.
2.  Table existence — all 11 core + supporting tables present.
3.  Primary-key enforcement — duplicate PKs are rejected.
4.  Foreign-key enforcement — invalid FKs are rejected.
5.  Unique-constraint enforcement — duplicate unique values rejected.
6.  Status CHECK constraints — invalid statuses rejected.
7.  Monetary CHECK constraints — negative amounts rejected where prohibited.
8.  PRAGMA foreign_key_check — no violations in a clean database.
9.  Cross-student allocation guard (service-level validation).
10. Audit event insert — AuditEvents table accepts new rows.
"""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so that
# `from backend.database import ...` works regardless of where pytest is run.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.db_manager import (
    DatabaseManager,
    EXPECTED_TABLES,
    CORE_ENTITY_TABLES,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def tmp_manager(tmp_path: Path) -> DatabaseManager:
    """Return an initialised DatabaseManager backed by a temporary DB file."""
    db_file = tmp_path / "test_student_finance.db"
    manager = DatabaseManager(db_path=db_file)
    manager.initialise()
    return manager


@pytest.fixture()
def conn(tmp_manager: DatabaseManager):
    """Yield an open connection from tmp_manager."""
    with tmp_manager.connection() as c:
        yield c


def test_initialise_closes_its_sqlite_connection(tmp_path: Path, monkeypatch):
    manager = DatabaseManager(db_path=tmp_path / "closed-after-init.db")
    connections = []
    original_connect = manager._raw_connection

    def track_connection():
        connection = original_connect()
        connections.append(connection)
        return connection

    monkeypatch.setattr(manager, "_raw_connection", track_connection)
    manager.initialise()

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connections[0].execute("SELECT 1")


# ===========================================================================
# Helper utilities
# ===========================================================================


def _insert_term(conn: sqlite3.Connection, *, term_code: str = "T001") -> int:
    """Insert a minimal Term and return its term_id."""
    cur = conn.execute(
        """INSERT INTO Terms (term_code, term_name, start_date, end_date)
           VALUES (?, 'Test Term', '2024-01-01', '2024-06-30')""",
        (term_code,),
    )
    return cur.lastrowid


def _insert_program(conn: sqlite3.Connection, *, prog_code: str = "P001") -> int:
    cur = conn.execute(
        """INSERT INTO Programs (program_code, program_name, duration_years, level)
           VALUES (?, 'Test Program', 4, 'UG')""",
        (prog_code,),
    )
    return cur.lastrowid


def _insert_student(
    conn: sqlite3.Connection,
    *,
    code: str = "STU001",
    email: str = "stu001@example.com",
) -> int:
    cur = conn.execute(
        """INSERT INTO Students
               (student_code, first_name, last_name, date_of_birth, email)
           VALUES (?, 'Alice', 'Smith', '2000-01-01', ?)""",
        (code, email),
    )
    return cur.lastrowid


def _insert_fee_schedule(
    conn: sqlite3.Connection, program_id: int, term_id: int, *, sc_code: str = "FS1"
) -> int:
    cur = conn.execute(
        """INSERT INTO FeeSchedules
               (program_id, term_id, schedule_name, effective_from, status)
           VALUES (?, ?, 'Default', '2024-01-01', 'active')""",
        (program_id, term_id),
    )
    return cur.lastrowid


def _insert_enrollment(
    conn: sqlite3.Connection, student_id: int, program_id: int, term_id: int
) -> int:
    cur = conn.execute(
        """INSERT INTO Enrollments
               (student_id, program_id, term_id, enrollment_date)
           VALUES (?, ?, ?, '2024-01-15')""",
        (student_id, program_id, term_id),
    )
    return cur.lastrowid


def _insert_invoice(conn: sqlite3.Connection, enrollment_id: int, term_id: int) -> int:
    cur = conn.execute(
        """INSERT INTO Invoices
               (invoice_number, enrollment_id, term_id, issue_date, due_date)
           VALUES ('INV-0001', ?, ?, '2024-01-15', '2024-02-15')""",
        (enrollment_id, term_id),
    )
    return cur.lastrowid


def _insert_invoice_line(conn: sqlite3.Connection, invoice_id: int) -> int:
    cur = conn.execute(
        """INSERT INTO InvoiceLines (invoice_id, fee_type, amount_paise)
           VALUES (?, 'Tuition', 100000)""",
        (invoice_id,),
    )
    return cur.lastrowid


def _insert_payment(
    conn: sqlite3.Connection,
    student_id: int,
    *,
    ref: str = "PAY-0001",
    amount: int = 50000,
) -> int:
    cur = conn.execute(
        """INSERT INTO Payments
               (payment_reference, student_id, payment_date, amount_paise,
                payment_method, status)
           VALUES (?, ?, '2024-01-20', ?, 'UPI', 'cleared')""",
        (ref, student_id, amount),
    )
    return cur.lastrowid


# ===========================================================================
# 1. Initialisation
# ===========================================================================


class TestInitialisation:
    def test_db_file_created(self, tmp_path: Path) -> None:
        """Database file must exist after initialise()."""
        db_file = tmp_path / "init_test.db"
        assert not db_file.exists()
        manager = DatabaseManager(db_path=db_file)
        manager.initialise()
        assert db_file.exists(), "Database file was not created."

    def test_initialise_idempotent(self, tmp_manager: DatabaseManager) -> None:
        """Calling initialise() twice must not raise or corrupt the schema."""
        tmp_manager.initialise()  # second call
        found, missing = tmp_manager.verify_tables()
        assert missing == [], f"Tables disappeared after second init: {missing}"

    def test_invoice_enrollment_term_lookup_index(self, tmp_manager: DatabaseManager) -> None:
        with tmp_manager.connection() as conn:
            columns = [
                row["name"]
                for row in conn.execute(
                    "PRAGMA index_info('idx_invoices_enrollment_term')"
                )
            ]

        assert columns == ["enrollment_id", "term_id"]

    def test_default_path_is_relative(self) -> None:
        """Default DB path must not be an absolute machine-specific path."""
        from backend.database.db_manager import DEFAULT_DB_PATH

        assert DEFAULT_DB_PATH.is_absolute() is False or str(
            DEFAULT_DB_PATH
        ).startswith(
            str(PROJECT_ROOT)
        ), (
            "DEFAULT_DB_PATH should be within the project root, not a machine-specific path."
        )


# ===========================================================================
# 2. Table existence
# ===========================================================================


class TestTableExistence:
    def test_all_expected_tables_exist(self, tmp_manager: DatabaseManager) -> None:
        found, missing = tmp_manager.verify_tables()
        assert missing == [], f"Missing tables: {missing}"

    def test_core_entity_tables_exist(self, tmp_manager: DatabaseManager) -> None:
        existing = set(tmp_manager.get_table_names())
        for table in CORE_ENTITY_TABLES:
            assert table in existing, f"Core entity table missing: {table}"

    @pytest.mark.parametrize(
        "table",
        [
            "Students", "Programs", "Terms", "FeeSchedules", "FeeScheduleLines",
            "Enrollments", "Invoices", "InvoiceLines", "Scholarships", "Eligibility",
            "Payments", "PaymentAllocations", "Refunds", "BalanceSnapshots",
            "AuditEvents",
        ],
    )
    def test_individual_table_exists(
        self, tmp_manager: DatabaseManager, table: str
    ) -> None:
        existing = set(tmp_manager.get_table_names())
        assert table in existing, f"Table '{table}' not found in database."


# ===========================================================================
# 3. Primary-key enforcement
# ===========================================================================


class TestPrimaryKeyEnforcement:
    def test_duplicate_student_code_rejected(self, conn: sqlite3.Connection) -> None:
        _insert_student(conn, code="DUPSTU", email="a@example.com")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_student(conn, code="DUPSTU", email="b@example.com")

    def test_duplicate_term_code_rejected(self, conn: sqlite3.Connection) -> None:
        _insert_term(conn, term_code="DUP-TERM")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_term(conn, term_code="DUP-TERM")

    def test_duplicate_program_code_rejected(self, conn: sqlite3.Connection) -> None:
        _insert_program(conn, prog_code="DUP-PROG")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_program(conn, prog_code="DUP-PROG")

    def test_duplicate_invoice_number_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        eid = _insert_enrollment(conn, sid, pid, tid)
        _insert_invoice(conn, eid, tid)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_invoice(conn, eid, tid)  # same invoice_number "INV-0001"

    def test_duplicate_payment_reference_rejected(self, conn: sqlite3.Connection) -> None:
        sid = _insert_student(conn)
        _insert_payment(conn, sid, ref="PAY-DUP")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_payment(conn, sid, ref="PAY-DUP")


# ===========================================================================
# 4. Foreign-key enforcement
# ===========================================================================


class TestForeignKeyEnforcement:
    def test_enrollment_invalid_student_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Enrollments
                       (student_id, program_id, term_id, enrollment_date)
                   VALUES (99999, ?, ?, '2024-01-15')""",
                (pid, tid),
            )

    def test_enrollment_invalid_program_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Enrollments
                       (student_id, program_id, term_id, enrollment_date)
                   VALUES (?, 99999, ?, '2024-01-15')""",
                (sid, tid),
            )

    def test_invoice_invalid_enrollment_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Invoices
                       (invoice_number, enrollment_id, term_id, issue_date, due_date)
                   VALUES ('INV-BAD', 99999, ?, '2024-01-01', '2024-02-01')""",
                (tid,),
            )

    def test_invoice_line_invalid_invoice_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO InvoiceLines (invoice_id, fee_type, amount_paise)
                   VALUES (99999, 'Tuition', 100000)"""
            )

    def test_payment_invalid_student_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Payments
                       (payment_reference, student_id, payment_date,
                        amount_paise, payment_method)
                   VALUES ('PAY-BAD', 99999, '2024-01-01', 50000, 'UPI')"""
            )

    def test_allocation_invalid_payment_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        eid = _insert_enrollment(conn, sid, pid, tid)
        inv_id = _insert_invoice(conn, eid, tid)
        line_id = _insert_invoice_line(conn, inv_id)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO PaymentAllocations
                       (payment_id, line_id, allocated_amount_paise)
                   VALUES (99999, ?, 10000)""",
                (line_id,),
            )

    def test_allocation_invalid_line_rejected(self, conn: sqlite3.Connection) -> None:
        sid = _insert_student(conn)
        pay_id = _insert_payment(conn, sid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO PaymentAllocations
                       (payment_id, line_id, allocated_amount_paise)
                   VALUES (?, 99999, 10000)""",
                (pay_id,),
            )

    def test_refund_invalid_payment_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Refunds
                       (refund_reference, payment_id, refund_date,
                        refund_amount_paise, reason, refund_method)
                   VALUES ('REF-BAD', 99999, '2024-01-25', 5000,
                           'Test', 'UPI')"""
            )

    def test_fee_schedule_invalid_program_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO FeeSchedules
                       (program_id, term_id, schedule_name, effective_from)
                   VALUES (99999, ?, 'Bad', '2024-01-01')""",
                (tid,),
            )

    def test_eligibility_invalid_scholarship_rejected(
        self, conn: sqlite3.Connection
    ) -> None:
        tid = _insert_term(conn)
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Eligibility
                       (student_id, scholarship_id, term_id,
                        awarded_amount_paise, applied_date)
                   VALUES (?, 99999, ?, 50000, '2024-01-01')""",
                (sid, tid),
            )

    def test_fk_definitions_exist(self, tmp_manager: DatabaseManager) -> None:
        """Verify that PRAGMA foreign_key_list returns definitions for key tables."""
        fk_list = tmp_manager.verify_foreign_keys()
        tables_with_fk = {fk["table"] for fk in fk_list}
        required = {
            "Enrollments", "Invoices", "InvoiceLines",
            "PaymentAllocations", "Refunds", "Eligibility",
        }
        missing = required - tables_with_fk
        assert not missing, f"Tables missing FK definitions: {missing}"


# ===========================================================================
# 5. Unique-constraint enforcement
# ===========================================================================


class TestUniqueConstraints:
    def test_student_email_unique(self, conn: sqlite3.Connection) -> None:
        _insert_student(conn, code="S1", email="unique@test.com")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_student(conn, code="S2", email="unique@test.com")

    def test_scholarship_code_unique(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO Scholarships
                   (scholarship_code, scholarship_name, scholarship_type)
               VALUES ('SC-01', 'Merit Gold', 'Merit')"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Scholarships
                       (scholarship_code, scholarship_name, scholarship_type)
                   VALUES ('SC-01', 'Merit Silver', 'Merit')"""
            )

    def test_enrollment_unique_per_student_program_term(
        self, conn: sqlite3.Connection
    ) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        _insert_enrollment(conn, sid, pid, tid)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_enrollment(conn, sid, pid, tid)

    def test_eligibility_unique_per_student_scholarship_term(
        self, conn: sqlite3.Connection
    ) -> None:
        tid = _insert_term(conn)
        sid = _insert_student(conn)
        sc_id = conn.execute(
            """INSERT INTO Scholarships
                   (scholarship_code, scholarship_name, scholarship_type)
               VALUES ('SC-U01', 'Test', 'Merit')"""
        ).lastrowid
        conn.execute(
            """INSERT INTO Eligibility
                   (student_id, scholarship_id, term_id,
                    awarded_amount_paise, applied_date)
               VALUES (?, ?, ?, 10000, '2024-01-01')""",
            (sid, sc_id, tid),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Eligibility
                       (student_id, scholarship_id, term_id,
                        awarded_amount_paise, applied_date)
                   VALUES (?, ?, ?, 10000, '2024-01-01')""",
                (sid, sc_id, tid),
            )

    def test_allocation_unique_per_payment_line(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        eid = _insert_enrollment(conn, sid, pid, tid)
        inv_id = _insert_invoice(conn, eid, tid)
        line_id = _insert_invoice_line(conn, inv_id)
        pay_id = _insert_payment(conn, sid)
        conn.execute(
            """INSERT INTO PaymentAllocations
                   (payment_id, line_id, allocated_amount_paise)
               VALUES (?, ?, 10000)""",
            (pay_id, line_id),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO PaymentAllocations
                       (payment_id, line_id, allocated_amount_paise)
                   VALUES (?, ?, 5000)""",
                (pay_id, line_id),
            )


# ===========================================================================
# 6. Status CHECK constraints
# ===========================================================================


class TestStatusConstraints:
    def test_invalid_student_status_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Students
                       (student_code, first_name, last_name,
                        date_of_birth, email, status)
                   VALUES ('S-INV', 'Bad', 'Status', '2000-01-01',
                           'bad@test.com', 'invalid_status')"""
            )

    def test_invalid_invoice_status_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        eid = _insert_enrollment(conn, sid, pid, tid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Invoices
                       (invoice_number, enrollment_id, term_id,
                        issue_date, due_date, status)
                   VALUES ('INV-STAT', ?, ?, '2024-01-01', '2024-02-01',
                           'not_a_status')""",
                (eid, tid),
            )

    def test_invalid_payment_status_rejected(self, conn: sqlite3.Connection) -> None:
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Payments
                       (payment_reference, student_id, payment_date,
                        amount_paise, payment_method, status)
                   VALUES ('PAY-STAT', ?, '2024-01-01', 50000, 'UPI',
                           'bogus_status')""",
                (sid,),
            )

    def test_invalid_enrollment_status_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Enrollments
                       (student_id, program_id, term_id,
                        enrollment_date, status)
                   VALUES (?, ?, ?, '2024-01-01', 'bad_status')""",
                (sid, pid, tid),
            )

    def test_invalid_refund_status_rejected(self, conn: sqlite3.Connection) -> None:
        sid = _insert_student(conn)
        pay_id = _insert_payment(conn, sid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Refunds
                       (refund_reference, payment_id, refund_date,
                        refund_amount_paise, reason, refund_method, status)
                   VALUES ('REF-STAT', ?, '2024-01-25', 5000,
                           'Test', 'UPI', 'bad_status')""",
                (pay_id,),
            )

    def test_invalid_payment_method_rejected(self, conn: sqlite3.Connection) -> None:
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Payments
                       (payment_reference, student_id, payment_date,
                        amount_paise, payment_method)
                   VALUES ('PAY-MTH', ?, '2024-01-01', 50000,
                           'Bitcoin')""",
                (sid,),
            )

    def test_invalid_scholarship_type_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Scholarships
                       (scholarship_code, scholarship_name, scholarship_type)
                   VALUES ('SC-BAD', 'Bad Scholarship', 'NotAType')"""
            )

    def test_invalid_program_level_rejected(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Programs
                       (program_code, program_name, duration_years, level)
                   VALUES ('P-BAD', 'Bad Program', 3, 'NotALevel')"""
            )


# ===========================================================================
# 7. Monetary CHECK constraints
# ===========================================================================


class TestMonetaryConstraints:
    def test_negative_payment_rejected(self, conn: sqlite3.Connection) -> None:
        """Payments must be strictly positive."""
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Payments
                       (payment_reference, student_id, payment_date,
                        amount_paise, payment_method)
                   VALUES ('PAY-NEG', ?, '2024-01-01', -1000, 'UPI')""",
                (sid,),
            )

    def test_zero_payment_rejected(self, conn: sqlite3.Connection) -> None:
        """Zero-value payments must be rejected (amount_paise > 0)."""
        sid = _insert_student(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Payments
                       (payment_reference, student_id, payment_date,
                        amount_paise, payment_method)
                   VALUES ('PAY-ZERO', ?, '2024-01-01', 0, 'UPI')""",
                (sid,),
            )

    def test_negative_allocation_rejected(self, conn: sqlite3.Connection) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        eid = _insert_enrollment(conn, sid, pid, tid)
        inv_id = _insert_invoice(conn, eid, tid)
        line_id = _insert_invoice_line(conn, inv_id)
        pay_id = _insert_payment(conn, sid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO PaymentAllocations
                       (payment_id, line_id, allocated_amount_paise)
                   VALUES (?, ?, -500)""",
                (pay_id, line_id),
            )

    def test_negative_refund_rejected(self, conn: sqlite3.Connection) -> None:
        sid = _insert_student(conn)
        pay_id = _insert_payment(conn, sid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Refunds
                       (refund_reference, payment_id, refund_date,
                        refund_amount_paise, reason, refund_method)
                   VALUES ('REF-NEG', ?, '2024-01-25', -500,
                           'Error', 'UPI')""",
                (pay_id,),
            )

    def test_negative_fee_schedule_line_rejected(
        self, conn: sqlite3.Connection
    ) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        fs_id = _insert_fee_schedule(conn, pid, tid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO FeeScheduleLines
                       (schedule_id, fee_type, amount_paise)
                   VALUES (?, 'Lab', -1000)""",
                (fs_id,),
            )

    def test_negative_eligibility_amount_rejected(
        self, conn: sqlite3.Connection
    ) -> None:
        tid = _insert_term(conn)
        sid = _insert_student(conn)
        sc_id = conn.execute(
            """INSERT INTO Scholarships
                   (scholarship_code, scholarship_name, scholarship_type)
               VALUES ('SC-NEG', 'Neg Test', 'Merit')"""
        ).lastrowid
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO Eligibility
                       (student_id, scholarship_id, term_id,
                        awarded_amount_paise, applied_date)
                   VALUES (?, ?, ?, -1000, '2024-01-01')""",
                (sid, sc_id, tid),
            )

    def test_positive_fee_schedule_line_accepted(
        self, conn: sqlite3.Connection
    ) -> None:
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        fs_id = _insert_fee_schedule(conn, pid, tid)
        conn.execute(
            """INSERT INTO FeeScheduleLines
                   (schedule_id, fee_type, amount_paise)
               VALUES (?, 'Tuition', 200000)""",
            (fs_id,),
        )
        row = conn.execute(
            "SELECT amount_paise FROM FeeScheduleLines WHERE schedule_id=?", (fs_id,)
        ).fetchone()
        assert row["amount_paise"] == 200000

    def test_invoice_line_negative_credit_accepted(
        self, conn: sqlite3.Connection
    ) -> None:
        """Negative invoice lines (scholarship credits) are explicitly allowed."""
        tid = _insert_term(conn)
        pid = _insert_program(conn)
        sid = _insert_student(conn)
        eid = _insert_enrollment(conn, sid, pid, tid)
        inv_id = _insert_invoice(conn, eid, tid)
        conn.execute(
            """INSERT INTO InvoiceLines
                   (invoice_id, fee_type, amount_paise, is_scholarship_credit)
               VALUES (?, 'Scholarship Credit', -50000, 1)""",
            (inv_id,),
        )
        row = conn.execute(
            """SELECT amount_paise FROM InvoiceLines
               WHERE invoice_id=? AND is_scholarship_credit=1""",
            (inv_id,),
        ).fetchone()
        assert row["amount_paise"] == -50000


# ===========================================================================
# 8. PRAGMA foreign_key_check
# ===========================================================================


class TestForeignKeyCheck:
    def test_no_fk_violations_empty_db(self, tmp_manager: DatabaseManager) -> None:
        """An empty initialised database must have zero FK violations."""
        violations = tmp_manager.run_foreign_key_check()
        assert violations == [], f"FK violations found: {violations}"

    def test_no_fk_violations_with_data(self, tmp_manager: DatabaseManager) -> None:
        """A database with valid data must also have zero FK violations."""
        with tmp_manager.connection() as conn:
            tid = _insert_term(conn)
            pid = _insert_program(conn)
            sid = _insert_student(conn)
            eid = _insert_enrollment(conn, sid, pid, tid)
            inv_id = _insert_invoice(conn, eid, tid)
            _insert_invoice_line(conn, inv_id)
            pay_id = _insert_payment(conn, sid)

        violations = tmp_manager.run_foreign_key_check()
        assert violations == [], f"FK violations found: {violations}"


# ===========================================================================
# 9. Cross-student allocation guard (service-level)
# ===========================================================================


class TestCrossStudentAllocationGuard:
    def test_same_student_allocation_allowed(
        self, tmp_manager: DatabaseManager
    ) -> None:
        with tmp_manager.connection() as conn:
            tid = _insert_term(conn)
            pid = _insert_program(conn)
            sid = _insert_student(conn)
            eid = _insert_enrollment(conn, sid, pid, tid)
            inv_id = _insert_invoice(conn, eid, tid)
            line_id = _insert_invoice_line(conn, inv_id)
            pay_id = _insert_payment(conn, sid)

            # Should not raise
            tmp_manager.validate_allocation(conn, pay_id, line_id)

    def test_cross_student_allocation_rejected(
        self, tmp_manager: DatabaseManager
    ) -> None:
        from backend.database.db_manager import DatabaseError

        with tmp_manager.connection() as conn:
            tid = _insert_term(conn)
            pid = _insert_program(conn)

            # Student 1 — payment owner
            sid1 = _insert_student(conn, code="S-CROSS-1", email="cross1@test.com")
            pay_id = _insert_payment(conn, sid1, ref="PAY-CROSS")

            # Student 2 — invoice owner
            sid2 = _insert_student(conn, code="S-CROSS-2", email="cross2@test.com")
            eid2 = _insert_enrollment(conn, sid2, pid, tid)
            inv_id2 = _insert_invoice(conn, eid2, tid)
            line_id2 = _insert_invoice_line(conn, inv_id2)

            with pytest.raises(DatabaseError, match="Cross-student"):
                tmp_manager.validate_allocation(conn, pay_id, line_id2)


# ===========================================================================
# 10. Audit events
# ===========================================================================


class TestAuditEvents:
    def test_audit_event_insert(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO AuditEvents
                   (entity_type, entity_id, event_type, performed_by, new_value)
               VALUES ('Student', 1, 'CREATE', 'system',
                       '{"student_code":"STU001"}')"""
        )
        row = conn.execute(
            "SELECT entity_type, event_type FROM AuditEvents LIMIT 1"
        ).fetchone()
        assert row["entity_type"] == "Student"
        assert row["event_type"] == "CREATE"

    def test_audit_event_preserves_old_and_new(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """INSERT INTO AuditEvents
                   (entity_type, entity_id, event_type, field_changed,
                    old_value, new_value, performed_by)
               VALUES ('Invoice', 42, 'STATUS_CHANGE', 'status',
                       'draft', 'issued', 'admin')"""
        )
        row = conn.execute(
            "SELECT old_value, new_value FROM AuditEvents WHERE entity_id=42"
        ).fetchone()
        assert row["old_value"] == "draft"
        assert row["new_value"] == "issued"

    def test_multiple_audit_events_per_entity(self, conn: sqlite3.Connection) -> None:
        for i, event_type in enumerate(["CREATE", "STATUS_CHANGE", "UPDATE"]):
            conn.execute(
                """INSERT INTO AuditEvents
                       (entity_type, entity_id, event_type)
                   VALUES ('Payment', 99, ?)""",
                (event_type,),
            )
        count = conn.execute(
            "SELECT COUNT(*) FROM AuditEvents WHERE entity_id=99"
        ).fetchone()[0]
        assert count == 3


# ===========================================================================
# 11. Bonus — happy-path data insertion
# ===========================================================================


class TestHappyPath:
    """Verify that a full valid data insertion chain succeeds end-to-end."""

    def test_full_financial_chain(self, tmp_manager: DatabaseManager) -> None:
        with tmp_manager.connection() as conn:
            tid = _insert_term(conn, term_code="2024-SEM1")
            pid = _insert_program(conn, prog_code="BTECH-CSE")
            fs_id = _insert_fee_schedule(conn, pid, tid)
            conn.execute(
                """INSERT INTO FeeScheduleLines
                       (schedule_id, fee_type, amount_paise, is_mandatory)
                   VALUES (?, 'Tuition', 200000, 1)""",
                (fs_id,),
            )
            sid = _insert_student(conn, code="STU-HAPPY", email="happy@test.com")
            eid = _insert_enrollment(conn, sid, pid, tid)
            inv_id = _insert_invoice(conn, eid, tid)
            line_id = _insert_invoice_line(conn, inv_id)  # 100000 paise
            pay_id = _insert_payment(conn, sid, ref="PAY-HAPPY", amount=50000)

            # Service-level guard
            tmp_manager.validate_allocation(conn, pay_id, line_id)

            conn.execute(
                """INSERT INTO PaymentAllocations
                       (payment_id, line_id, allocated_amount_paise)
                   VALUES (?, ?, 50000)""",
                (pay_id, line_id),
            )

            # Verify outstanding balance (derived)
            invoice_total = conn.execute(
                "SELECT SUM(amount_paise) FROM InvoiceLines WHERE invoice_id=?",
                (inv_id,),
            ).fetchone()[0]
            allocated_total = conn.execute(
                """SELECT SUM(pa.allocated_amount_paise)
                   FROM PaymentAllocations pa
                   JOIN InvoiceLines il ON il.line_id = pa.line_id
                   WHERE il.invoice_id=?""",
                (inv_id,),
            ).fetchone()[0]
            outstanding = invoice_total - (allocated_total or 0)
            assert invoice_total == 100000
            assert allocated_total == 50000
            assert outstanding == 50000

        violations = tmp_manager.run_foreign_key_check()
        assert violations == []

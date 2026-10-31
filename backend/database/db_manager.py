"""
backend/database/db_manager.py
================================
DatabaseManager — centralised SQLite connection and schema management.

Responsibilities
----------------
* Resolve the database path (configurable; defaults to
  backend/database/student_finance.db relative to the project root).
* Open connections with ``PRAGMA foreign_keys = ON`` enforced.
* Apply the SQL schema idempotently (CREATE TABLE IF NOT EXISTS).
* Verify that all expected tables exist after initialisation.
* Verify foreign-key definitions (sqlite_master introspection).
* Run ``PRAGMA foreign_key_check`` and surface any violations.
* Provide a context-manager helper for safe transaction handling.
* Close connections safely.
* Emit clear, structured error messages.

Design notes
------------
* Monetary values are always INTEGER paise.  This module enforces no
  monetary rules itself — that responsibility belongs to service-layer
  code.  The schema's CHECK constraints are the first line of defence.
* Cross-student payment allocations cannot be prevented purely by FK
  constraints in SQLite (no multi-table CHECK).  A ``validate_allocation``
  helper is provided for service-layer callers to call before inserting
  into PaymentAllocations.
* All connections are opened in autocommit=False mode so that callers
  must commit explicitly (or use the ``transaction`` context manager).
"""

import contextlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default path: resolve relative to *this file* so the module works from
# any working directory without machine-specific absolute paths.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).parent
DEFAULT_DB_PATH = _THIS_DIR / "student_finance.db"
_SCHEMA_PATH = _THIS_DIR / "schema.sql"

# All tables defined in the schema, used for verification.
EXPECTED_TABLES: List[str] = [
    "Terms",
    "Programs",
    "Students",
    "FeeSchedules",
    "FeeScheduleLines",
    "Enrollments",
    "Invoices",
    "InvoiceLines",
    "Scholarships",
    "Eligibility",
    "Payments",
    "PaymentAllocations",
    "Refunds",
    "AuditEvents",
]

# The 11 core entity tables required by the specification.
CORE_ENTITY_TABLES: List[str] = [
    "Students",
    "Programs",
    "FeeSchedules",
    "Enrollments",
    "Invoices",
    "InvoiceLines",
    "Scholarships",
    "Eligibility",
    "Payments",
    "PaymentAllocations",
    "Refunds",
]


class DatabaseError(Exception):
    """Raised when a database operation fails in a recoverable way."""


class DatabaseManager:
    """
    Manages the SQLite database lifecycle for Student Finance Management.

    Parameters
    ----------
    db_path : str | Path | None
        Filesystem path to the SQLite database file.
        Defaults to ``DEFAULT_DB_PATH`` when *None*.

    Usage
    -----
    ::

        manager = DatabaseManager()
        manager.initialise()

        with manager.connection() as conn:
            conn.execute("SELECT 1")

        # or with explicit transaction control
        with manager.connection() as conn:
            with manager.transaction(conn):
                conn.execute("INSERT INTO Students ...")
    """

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self._schema_path = _SCHEMA_PATH

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """
        Initialise the database: create the file (if needed) and apply the
        schema.  Safe to call multiple times — uses ``IF NOT EXISTS`` DDL.
        """
        logger.info("Initialising database at: %s", self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        schema_sql = self._load_schema()

        try:
            with self._raw_connection() as conn:
                conn.executescript(schema_sql)
                conn.commit()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Schema application failed: {exc}\nDB path: {self.db_path}"
            ) from exc

        logger.info("Database initialised successfully.")

    @contextlib.contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Yield a database connection with foreign keys enabled.
        The connection is committed and closed on clean exit; rolled back
        and closed on exception.

        Yields
        ------
        sqlite3.Connection
        """
        conn = self._raw_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(
        self, conn: sqlite3.Connection
    ) -> Generator[sqlite3.Connection, None, None]:
        """
        Wrap an explicit savepoint transaction on *conn*.
        Useful for nested transactions or fine-grained rollback control.

        Parameters
        ----------
        conn : sqlite3.Connection
            An open connection obtained via :meth:`connection`.

        Yields
        ------
        sqlite3.Connection
        """
        conn.execute("SAVEPOINT sfm_tx")
        try:
            yield conn
            conn.execute("RELEASE SAVEPOINT sfm_tx")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT sfm_tx")
            raise

    def verify_tables(self) -> Tuple[List[str], List[str]]:
        """
        Check that all expected tables exist in the database.

        Returns
        -------
        (found_tables, missing_tables)
            Both lists contain table names.  ``missing_tables`` is empty
            when the schema is complete.

        Raises
        ------
        DatabaseError
            When the database file cannot be opened.
        """
        try:
            with self.connection() as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Could not read table list: {exc}") from exc

        existing = {row[0] for row in rows}
        found = [t for t in EXPECTED_TABLES if t in existing]
        missing = [t for t in EXPECTED_TABLES if t not in existing]

        if missing:
            logger.warning("Missing tables: %s", missing)
        else:
            logger.info("All %d expected tables are present.", len(EXPECTED_TABLES))

        return found, missing

    def verify_foreign_keys(self) -> List[dict]:
        """
        Introspect foreign-key definitions for all tables using
        ``PRAGMA foreign_key_list``.

        Returns
        -------
        list[dict]
            Each dict has keys: table, id, seq, from_col, to_table, to_col,
            on_update, on_delete, match.
        """
        fk_list: List[dict] = []
        try:
            with self.connection() as conn:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                for (table_name,) in tables:
                    rows = conn.execute(
                        f"PRAGMA foreign_key_list({table_name})"
                    ).fetchall()
                    for row in rows:
                        fk_list.append(
                            {
                                "table": table_name,
                                "id": row[0],
                                "seq": row[1],
                                "from_col": row[3],
                                "to_table": row[2],
                                "to_col": row[4],
                                "on_update": row[5],
                                "on_delete": row[6],
                                "match": row[7],
                            }
                        )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Foreign-key introspection failed: {exc}") from exc

        logger.info("Found %d foreign-key definitions.", len(fk_list))
        return fk_list

    def run_foreign_key_check(self) -> List[dict]:
        """
        Execute ``PRAGMA foreign_key_check`` and return any violations.

        Returns
        -------
        list[dict]
            Empty list means no violations.  Each dict has keys:
            table, rowid, parent, fkid.

        Raises
        ------
        DatabaseError
            On connection or PRAGMA error.
        """
        violations: List[dict] = []
        try:
            with self.connection() as conn:
                rows = conn.execute("PRAGMA foreign_key_check").fetchall()
                for row in rows:
                    violations.append(
                        {
                            "table": row[0],
                            "rowid": row[1],
                            "parent": row[2],
                            "fkid": row[3],
                        }
                    )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Foreign-key check failed: {exc}") from exc

        if violations:
            logger.error("Foreign-key violations found: %s", violations)
        else:
            logger.info("Foreign-key check passed — no violations.")

        return violations

    def validate_allocation(
        self, conn: sqlite3.Connection, payment_id: int, line_id: int
    ) -> None:
        """
        Service-level guard: ensure that the Payment and the InvoiceLine
        belong to the **same student** before inserting a PaymentAllocation.

        SQLite cannot enforce multi-table consistency in a single CHECK
        constraint, so this method must be called explicitly before every
        INSERT into PaymentAllocations.

        Parameters
        ----------
        conn : sqlite3.Connection
        payment_id : int
        line_id : int

        Raises
        ------
        DatabaseError
            If the payment and invoice line belong to different students.
        ValueError
            If the payment_id or line_id do not exist.
        """
        row = conn.execute(
            """
            SELECT p.student_id AS pay_student,
                   s.student_id AS inv_student
            FROM Payments p
            JOIN InvoiceLines il ON il.line_id = ?
            JOIN Invoices i      ON i.invoice_id = il.invoice_id
            JOIN Enrollments e   ON e.enrollment_id = i.enrollment_id
            JOIN Students s      ON s.student_id = e.student_id
            WHERE p.payment_id = ?
            """,
            (line_id, payment_id),
        ).fetchone()

        if row is None:
            raise ValueError(
                f"payment_id={payment_id} or line_id={line_id} not found."
            )

        pay_student, inv_student = row
        if pay_student != inv_student:
            raise DatabaseError(
                f"Cross-student allocation rejected: "
                f"payment belongs to student_id={pay_student} but "
                f"invoice line belongs to student_id={inv_student}."
            )

    def get_table_names(self) -> List[str]:
        """Return the list of all table names currently in the database."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        """No-op — connections are managed per-request.  Provided for API symmetry."""
        logger.debug("DatabaseManager.close() called (no persistent connection to close).")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _raw_connection(self) -> sqlite3.Connection:
        """
        Open a raw SQLite connection with:
        * Row factory set to ``sqlite3.Row`` for dict-like access.
        * Foreign-key enforcement enabled.
        * isolation_level=None disabled so that we manage transactions
          ourselves (autocommit turned off via BEGIN).
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Verify FK pragma took effect
        fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        if fk_enabled != 1:
            logger.warning(
                "PRAGMA foreign_keys could not be enabled on this connection."
            )
        return conn

    def _load_schema(self) -> str:
        """Load and return the SQL schema as a string."""
        if not self._schema_path.exists():
            raise DatabaseError(
                f"Schema file not found: {self._schema_path}\n"
                "Ensure backend/database/schema.sql is present."
            )
        return self._schema_path.read_text(encoding="utf-8")

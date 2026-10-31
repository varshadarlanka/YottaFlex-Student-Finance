"""
backend/generators/generate_data.py
=====================================
Main data generation entry point.

Commands
--------
    # Starter mode (50 students, quick dev/test):
    python -m backend.generators.generate_data --mode starter

    # Full mode (10,000 students, production scale):
    python -m backend.generators.generate_data --mode full

    # Full mode with explicit reset (DESTRUCTIVE — wipes and regenerates):
    python -m backend.generators.generate_data --mode full --reset

    # Custom seed:
    python -m backend.generators.generate_data --mode full --seed 99999

Generation order (dependency order)
-------------------------------------
1. Programs   (no dependencies)
2. Terms      (no dependencies)
3. FeeSchedules + FeeScheduleLines (depends on Programs + Terms)
4. Students   (no dependencies)
5. Enrollments (depends on Students + Programs + Terms + FeeSchedules)

Safety rules
------------
* The database is initialised (schema applied) if it does not exist.
* If the database already has data, the script will NOT overwrite it
  unless --reset is explicitly passed.
* --reset drops and recreates the database file (destructive!).
* All generation is wrapped in a single transaction per entity type.
* On any error, the entire generation is rolled back — no partial data.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.config import (
    DEFAULT_DB_PATH,
    DEFAULT_SEED,
    GenerationConfig,
    GenerationMode,
    get_config,
)
from backend.database.db_manager import DatabaseManager
from backend.generators.enrollments import EnrollmentGenerator
from backend.generators.fee_data import FeeScheduleGenerator
from backend.generators.programs import ProgramGenerator
from backend.generators.students import StudentGenerator
from backend.generators.terms import TermGenerator
from backend.id_generator import IDGenerator
from backend.logging_config import setup_logging
from backend.seed_manager import SeededRandom
from backend.validators import verify_integrity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_separator(title: str = "") -> None:
    w = 60
    if title:
        print(f"\n{'=' * w}")
        print(f"  {title}")
        print(f"{'=' * w}")
    else:
        print(f"{'=' * w}")


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _print_summary(conn: sqlite3.Connection) -> None:
    _print_separator("GENERATION SUMMARY")
    tables = [
        ("Programs",          "Programs"),
        ("Terms",             "Terms"),
        ("Fee Schedules",     "FeeSchedules"),
        ("Fee Schedule Lines","FeeScheduleLines"),
        ("Students",          "Students"),
        ("Enrollments",       "Enrollments"),
    ]
    for label, table in tables:
        count = _count(conn, table)
        print(f"  {label:<25} {count:>8,} rows")
    _print_separator()


def _has_existing_data(conn: sqlite3.Connection) -> bool:
    """Return True if any generated data already exists."""
    for table in ["Students", "Programs", "Terms"]:
        if _count(conn, table) > 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Core generation pipeline
# ---------------------------------------------------------------------------


def run_generation(
    mode: GenerationMode,
    db_path: Path,
    seed: int,
    reset: bool = False,
) -> None:
    """
    Execute the full generation pipeline.

    Parameters
    ----------
    mode : GenerationMode
    db_path : Path
    seed : int
    reset : bool
        If True, delete and recreate the DB (destructive).
    """
    setup_logging("INFO")
    _print_separator(f"Student Finance Management — Data Generation")
    print(f"  Mode : {mode.value}")
    print(f"  Seed : {seed}")
    print(f"  DB   : {db_path}")
    print(f"  Reset: {reset}")

    # ---- Reset handling ------------------------------------------------
    if reset:
        if db_path.exists():
            print(f"\n  [RESET] Deleting existing database: {db_path}")
            db_path.unlink()
        else:
            print(f"\n  [RESET] No existing database found — will create fresh.")

    # ---- Initialise DB -------------------------------------------------
    manager = DatabaseManager(db_path=db_path)
    manager.initialise()

    # ---- Check for existing data (guard against accidental overwrites) --
    with manager.connection() as conn:
        if not reset and _has_existing_data(conn):
            print(
                "\n  [WARNING] Database already contains data.\n"
                "  Use --reset to wipe and regenerate, or check existing data.\n"
                "  Existing records will be SKIPPED (INSERT OR IGNORE).\n"
            )

    # ---- Seed setup ----------------------------------------------------
    config: GenerationConfig = get_config(mode, seed=seed)
    main_rng = SeededRandom(seed=seed)
    id_gen = IDGenerator()

    # Fork independent child RNGs per generator type
    prog_rng  = main_rng.fork("programs")
    term_rng  = main_rng.fork("terms")
    fee_rng   = main_rng.fork("fee_data")
    stu_rng   = main_rng.fork("students")
    enr_rng   = main_rng.fork("enrollments")

    # ---- 1. Programs ---------------------------------------------------
    _print_separator("Step 1/5: Programs")
    prog_gen = ProgramGenerator()
    prog_gen.build()
    with manager.connection() as conn:
        prog_gen.insert(conn)

    # Reload programs from DB (to get actual program_id values)
    with manager.connection() as conn:
        program_rows = [
            dict(row) for row in conn.execute(
                "SELECT program_id, program_code, program_name, duration_years, level "
                "FROM Programs ORDER BY program_id"
            ).fetchall()
        ]
    print(f"  Programs in DB : {len(program_rows)}")

    # ---- 2. Terms ------------------------------------------------------
    _print_separator("Step 2/5: Terms")
    term_gen = TermGenerator(config)
    term_gen.build()
    with manager.connection() as conn:
        term_gen.insert(conn)

    with manager.connection() as conn:
        term_rows = [
            dict(row) for row in conn.execute(
                "SELECT term_id, term_code, term_name, start_date, end_date "
                "FROM Terms ORDER BY term_id"
            ).fetchall()
        ]
    print(f"  Terms in DB    : {len(term_rows)}")

    # ---- 3. Fee Schedules + Lines --------------------------------------
    _print_separator("Step 3/5: Fee Schedules + Lines")
    fee_gen = FeeScheduleGenerator(
        config=config,
        rng=fee_rng,
        program_rows=program_rows,
        term_rows=term_rows,
    )
    fee_gen.build()
    with manager.connection() as conn:
        fee_stats = fee_gen.insert(conn)
    print(f"  FeeSchedules   : {fee_stats['schedules_inserted']} new, "
          f"{fee_stats['schedules_skipped']} skipped")
    print(f"  FeeSchedLines  : {fee_stats['lines_inserted']} new")

    # ---- 4. Students ---------------------------------------------------
    _print_separator("Step 4/5: Students")
    stu_gen = StudentGenerator(config, stu_rng, id_gen)
    stu_gen.build()
    with manager.connection() as conn:
        stu_stats = stu_gen.insert(conn)
    print(f"  Students       : {stu_stats['inserted']} new, "
          f"{stu_stats['skipped']} skipped")

    # ---- 5. Enrollments ------------------------------------------------
    _print_separator("Step 5/5: Enrollments")
    enr_gen = EnrollmentGenerator(config, enr_rng)
    with manager.connection() as conn:
        enr_gen.build_from_db(conn)
    with manager.connection() as conn:
        enr_stats = enr_gen.insert(conn)
    print(f"  Enrollments    : {enr_stats['inserted']} new, "
          f"{enr_stats['skipped']} skipped")

    # ---- Integrity check -----------------------------------------------
    _print_separator("Integrity Check")
    with manager.connection() as conn:
        violations = verify_integrity(conn)
        fk_violations = manager.run_foreign_key_check()

    if violations:
        print("  [FAIL] Data integrity violations:")
        for v in violations:
            print(f"    - {v}")
    else:
        print("  [OK] All integrity checks passed.")

    if fk_violations:
        print("  [FAIL] Foreign-key violations:")
        for v in fk_violations:
            print(f"    - {v}")
    else:
        print("  [OK] PRAGMA foreign_key_check: 0 violations.")

    # ---- Summary -------------------------------------------------------
    with manager.connection() as conn:
        _print_summary(conn)

    print("\n  Generation complete.\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Student Finance Management — Synthetic Data Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backend.generators.generate_data --mode starter
  python -m backend.generators.generate_data --mode full
  python -m backend.generators.generate_data --mode full --reset
  python -m backend.generators.generate_data --mode full --seed 12345 --db /tmp/test.db
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["starter", "full"],
        default="full",
        help="Generation mode: 'starter' (50 students) or 'full' (10,000 students).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to the SQLite database file (default: backend/database/student_finance.db).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help=(
            "DESTRUCTIVE: delete and recreate the database before generating. "
            "Required if you want to regenerate from scratch."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    mode = GenerationMode(args.mode)

    try:
        run_generation(
            mode=mode,
            db_path=db_path,
            seed=args.seed,
            reset=args.reset,
        )
    except Exception as exc:
        logger.error("Generation failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

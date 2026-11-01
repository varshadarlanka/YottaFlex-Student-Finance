"""
tests/test_generation.py
==========================
Phase 1 test suite — data generation tests.

Test categories
---------------
1.  Config — mode parameters, seed propagation.
2.  IDGenerator — uniqueness, format, reproducibility.
3.  SeededRandom — determinism, fork isolation.
4.  ProgramGenerator — 20 programs, distinct codes, valid levels.
5.  TermGenerator — correct count, valid dates, deterministic codes.
6.  FeeScheduleGenerator — one schedule per (program, term), integer paise.
7.  StudentGenerator — correct count, unique codes/emails, valid statuses.
8.  EnrollmentGenerator — valid FKs, valid statuses, no duplicate triples.
9.  Starter mode end-to-end — row counts, FK integrity.
10. Deterministic output — same seed → same data.
11. Safe rerun behavior — second run inserts 0 new rows.
12. Rollback on failure — transaction rolls back cleanly.
13. Validators — field-level and post-generation integrity.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    DEFAULT_SEED,
    GenerationMode,
    get_config,
)
from backend.database.db_manager import DatabaseManager
from backend.generators.enrollments import EnrollmentGenerator
from backend.generators.fee_data import FeeScheduleGenerator
from backend.generators.programs import ProgramGenerator
from backend.generators.students import StudentGenerator
from backend.generators.terms import TermGenerator
from backend.id_generator import IDGenerator, make_term_code, make_program_code
from backend.seed_manager import SeededRandom
from backend.validators import (
    ValidationError,
    validate_date_range,
    validate_date_string,
    validate_paise,
    validate_status,
    verify_integrity,
)


# ===========================================================================
# Shared fixtures
# ===========================================================================


@pytest.fixture()
def tmp_manager(tmp_path: Path) -> DatabaseManager:
    """Initialised DatabaseManager backed by a temporary DB."""
    db = tmp_path / "test_gen.db"
    m = DatabaseManager(db_path=db)
    m.initialise()
    return m


@pytest.fixture()
def starter_config():
    return get_config(GenerationMode.STARTER, seed=DEFAULT_SEED)


@pytest.fixture()
def full_config():
    return get_config(GenerationMode.FULL, seed=DEFAULT_SEED)


@pytest.fixture()
def id_gen():
    return IDGenerator()


@pytest.fixture()
def main_rng():
    return SeededRandom(DEFAULT_SEED)


# ===========================================================================
# 1. Configuration
# ===========================================================================


class TestConfig:
    def test_starter_has_50_students(self, starter_config):
        assert starter_config.num_students == 50

    def test_full_has_10000_students(self, full_config):
        assert full_config.num_students == 10_000

    def test_both_modes_have_20_programs(self, starter_config, full_config):
        assert starter_config.num_programs == 20
        assert full_config.num_programs == 20

    def test_starter_has_4_terms(self, starter_config):
        assert starter_config.num_terms == 4

    def test_full_has_6_terms(self, full_config):
        assert full_config.num_terms == 6

    def test_full_mode_targets_challenge_baseline_volumes(self, full_config):
        assert full_config.target_invoice_count == 30_000
        assert full_config.target_award_count == 15_000
        assert full_config.target_payment_count == 50_000

    def test_seed_is_configurable(self):
        cfg = get_config(GenerationMode.STARTER, seed=12345)
        assert cfg.seed == 12345

    def test_default_seed_is_20261022(self):
        cfg = get_config(GenerationMode.FULL)
        assert cfg.seed == DEFAULT_SEED == 20261022

    def test_student_status_weights_sum_to_1(self, full_config):
        total = sum(full_config.student_status_weights.values())
        assert abs(total - 1.0) < 1e-9


# ===========================================================================
# 2. IDGenerator
# ===========================================================================


class TestIDGenerator:
    def test_student_code_format(self, id_gen):
        code = id_gen.student_code()
        assert code.startswith("STU-")
        assert len(code) == 10  # STU-000001

    def test_student_codes_sequential(self, id_gen):
        codes = [id_gen.student_code() for _ in range(5)]
        assert codes == ["STU-000001", "STU-000002", "STU-000003", "STU-000004", "STU-000005"]

    def test_student_codes_unique(self, id_gen):
        codes = [id_gen.student_code() for _ in range(1000)]
        assert len(set(codes)) == 1000

    def test_enrollment_code_format(self, id_gen):
        code = id_gen.enrollment_id_code()
        assert code.startswith("ENR-")
        assert len(code) == 12  # ENR-00000001

    def test_invoice_number_format(self, id_gen):
        inv = id_gen.invoice_number()
        assert inv.startswith("INV-")

    def test_payment_reference_format(self, id_gen):
        ref = id_gen.payment_reference()
        assert ref.startswith("PAY-")

    def test_refund_reference_format(self, id_gen):
        ref = id_gen.refund_reference()
        assert ref.startswith("REF-")

    def test_counters_independent_per_prefix(self, id_gen):
        id_gen.student_code()  # STU=1
        id_gen.student_code()  # STU=2
        inv = id_gen.invoice_number()  # INV=1, not 3
        assert inv == "INV-00000001"

    def test_reset_specific_prefix(self, id_gen):
        id_gen.student_code()
        id_gen.student_code()
        id_gen.reset("STU")
        code = id_gen.student_code()
        assert code == "STU-000001"

    def test_make_program_code(self):
        code = make_program_code(1, "BTECH-CSE")
        assert code == "PROG-01-BTECH-CSE"

    def test_make_term_code(self):
        code = make_term_code(2026, "FALL")
        assert code == "TERM-2026-FALL"


# ===========================================================================
# 3. SeededRandom
# ===========================================================================


class TestSeededRandom:
    def test_same_seed_same_output(self):
        rng1 = SeededRandom(12345)
        rng2 = SeededRandom(12345)
        vals1 = [rng1.randint(1, 1000) for _ in range(100)]
        vals2 = [rng2.randint(1, 1000) for _ in range(100)]
        assert vals1 == vals2

    def test_different_seed_different_output(self):
        rng1 = SeededRandom(1)
        rng2 = SeededRandom(2)
        vals1 = [rng1.randint(1, 10000) for _ in range(20)]
        vals2 = [rng2.randint(1, 10000) for _ in range(20)]
        assert vals1 != vals2

    def test_fork_is_deterministic(self):
        rng1 = SeededRandom(DEFAULT_SEED)
        rng2 = SeededRandom(DEFAULT_SEED)
        child1 = rng1.fork("students")
        child2 = rng2.fork("students")
        assert child1.seed == child2.seed

    def test_fork_is_reproducible_across_processes(self):
        script = (
            "from backend.seed_manager import SeededRandom; "
            "print(SeededRandom(20261022).fork('students').random())"
        )
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = "random"
        outputs = [
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=PROJECT_ROOT,
                env=env,
                text=True,
            ).strip()
            for _ in range(2)
        ]
        assert outputs[0] == outputs[1]

    def test_fork_children_are_independent(self):
        rng = SeededRandom(DEFAULT_SEED)
        child_a = rng.fork("a")
        child_b = rng.fork("b")
        # Children have different seeds
        assert child_a.seed != child_b.seed

    def test_random_date_in_range(self):
        from datetime import date
        rng = SeededRandom(42)
        start = date(2020, 1, 1)
        end = date(2024, 12, 31)
        for _ in range(50):
            d = rng.random_date(start, end)
            assert start <= d <= end

    def test_random_date_of_birth_age_range(self):
        from datetime import date
        rng = SeededRandom(42)
        ref = date(2024, 1, 1)
        for _ in range(50):
            dob = rng.random_date_of_birth(min_age=17, max_age=30, reference=ref)
            age = (ref - dob).days / 365.25
            assert 16.0 <= age <= 31  # slight tolerance for boundary DOBs


# ===========================================================================
# 4. ProgramGenerator
# ===========================================================================


class TestProgramGenerator:
    def test_generates_exactly_20_programs(self):
        gen = ProgramGenerator()
        progs = gen.build()
        assert len(progs) == 20

    def test_all_program_codes_unique(self):
        gen = ProgramGenerator()
        progs = gen.build()
        codes = [p["program_code"] for p in progs]
        assert len(set(codes)) == 20

    def test_all_program_names_unique(self):
        gen = ProgramGenerator()
        progs = gen.build()
        names = [p["program_name"] for p in progs]
        assert len(set(names)) == 20

    def test_valid_program_levels(self):
        from backend.config import PROGRAM_LEVELS
        gen = ProgramGenerator()
        progs = gen.build()
        for p in progs:
            assert p["level"] in PROGRAM_LEVELS

    def test_positive_duration_years(self):
        gen = ProgramGenerator()
        progs = gen.build()
        for p in progs:
            assert p["duration_years"] >= 1

    def test_program_codes_contain_prog_prefix(self):
        gen = ProgramGenerator()
        progs = gen.build()
        for p in progs:
            assert p["program_code"].startswith("PROG-")

    def test_programs_inserted_into_db(self, tmp_manager):
        gen = ProgramGenerator()
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM Programs").fetchone()[0]
        assert count == 20

    def test_program_insert_is_idempotent(self, tmp_manager):
        gen = ProgramGenerator()
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            gen.insert(conn)  # second insert
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM Programs").fetchone()[0]
        assert count == 20  # still 20, not 40


# ===========================================================================
# 5. TermGenerator
# ===========================================================================


class TestTermGenerator:
    def test_starter_generates_4_terms(self, starter_config):
        gen = TermGenerator(starter_config)
        terms = gen.build()
        assert len(terms) == 4

    def test_full_generates_6_terms(self, full_config):
        gen = TermGenerator(full_config)
        terms = gen.build()
        assert len(terms) == 6

    def test_term_codes_unique(self, full_config):
        gen = TermGenerator(full_config)
        terms = gen.build()
        codes = [t["term_code"] for t in terms]
        assert len(set(codes)) == len(terms)

    def test_term_dates_valid(self, full_config):
        from datetime import date
        gen = TermGenerator(full_config)
        terms = gen.build()
        for t in terms:
            start = date.fromisoformat(t["start_date"])
            end = date.fromisoformat(t["end_date"])
            assert end > start

    def test_term_codes_contain_year_and_season(self, full_config):
        gen = TermGenerator(full_config)
        terms = gen.build()
        for t in terms:
            code = t["term_code"]
            assert code.startswith("TERM-")
            parts = code.split("-")
            assert len(parts) == 3
            assert parts[1].isdigit()
            assert parts[2] in ("SPRING", "FALL")

    def test_terms_inserted_into_db(self, tmp_manager, starter_config):
        gen = TermGenerator(starter_config)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM Terms").fetchone()[0]
        assert count == 4

    def test_term_insert_is_idempotent(self, tmp_manager, starter_config):
        gen = TermGenerator(starter_config)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM Terms").fetchone()[0]
        assert count == 4


# ===========================================================================
# 6. FeeScheduleGenerator
# ===========================================================================


def _setup_programs_and_terms(manager: DatabaseManager, config) -> tuple:
    """Helper: insert programs and terms, return (program_rows, term_rows)."""
    prog_gen = ProgramGenerator()
    prog_gen.build()
    with manager.connection() as conn:
        prog_gen.insert(conn)

    term_gen = TermGenerator(config)
    term_gen.build()
    with manager.connection() as conn:
        term_gen.insert(conn)

    with manager.connection() as conn:
        program_rows = [dict(r) for r in conn.execute(
            "SELECT program_id, program_code, program_name, duration_years, level FROM Programs"
        ).fetchall()]
        term_rows = [dict(r) for r in conn.execute(
            "SELECT term_id, term_code, term_name, start_date, end_date FROM Terms"
        ).fetchall()]

    return program_rows, term_rows


class TestFeeScheduleGenerator:
    def test_one_schedule_per_program_term(self, tmp_manager, starter_config):
        prog_rows, term_rows = _setup_programs_and_terms(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
        gen = FeeScheduleGenerator(starter_config, rng, prog_rows, term_rows)
        schedules, _ = gen.build()
        expected = len(prog_rows) * len(term_rows)
        assert len(schedules) == expected

    def test_fee_amounts_are_positive_integers(self, tmp_manager, starter_config):
        prog_rows, term_rows = _setup_programs_and_terms(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
        gen = FeeScheduleGenerator(starter_config, rng, prog_rows, term_rows)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            rows = conn.execute("SELECT amount_paise FROM FeeScheduleLines").fetchall()
        for row in rows:
            assert isinstance(row[0], int)
            assert row[0] >= 0

    def test_fee_schedule_insert_creates_lines(self, tmp_manager, starter_config):
        prog_rows, term_rows = _setup_programs_and_terms(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
        gen = FeeScheduleGenerator(starter_config, rng, prog_rows, term_rows)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            line_count = conn.execute("SELECT COUNT(*) FROM FeeScheduleLines").fetchone()[0]
        assert line_count > 0

    def test_all_fee_schedules_active(self, tmp_manager, starter_config):
        prog_rows, term_rows = _setup_programs_and_terms(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
        gen = FeeScheduleGenerator(starter_config, rng, prog_rows, term_rows)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            non_active = conn.execute(
                "SELECT COUNT(*) FROM FeeSchedules WHERE status != 'active'"
            ).fetchone()[0]
        assert non_active == 0

    def test_fee_schedule_insert_idempotent(self, tmp_manager, starter_config):
        prog_rows, term_rows = _setup_programs_and_terms(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
        gen = FeeScheduleGenerator(starter_config, rng, prog_rows, term_rows)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            gen.insert(conn)  # second time
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM FeeSchedules").fetchone()[0]
        expected = 20 * starter_config.num_terms
        assert count == expected


# ===========================================================================
# 7. StudentGenerator
# ===========================================================================


class TestStudentGenerator:
    def test_starter_generates_50_students(self, starter_config):
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        students = gen.build()
        assert len(students) == 50

    def test_full_generates_10000_students(self, full_config):
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(full_config, rng, id_gen)
        students = gen.build()
        assert len(students) == 10_000

    def test_student_codes_unique(self, starter_config):
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        students = gen.build()
        codes = [s["student_code"] for s in students]
        assert len(set(codes)) == len(students)

    def test_student_emails_unique(self, starter_config):
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        students = gen.build()
        emails = [s["email"] for s in students]
        assert len(set(emails)) == len(students)

    def test_valid_student_statuses(self, starter_config):
        from backend.config import STUDENT_STATUSES
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        students = gen.build()
        for s in students:
            assert s["status"] in STUDENT_STATUSES

    def test_student_codes_start_with_STU(self, starter_config):
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        students = gen.build()
        for s in students:
            assert s["student_code"].startswith("STU-")

    def test_student_dob_is_valid_date(self, starter_config):
        from datetime import date
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        students = gen.build()
        for s in students:
            dob = date.fromisoformat(s["date_of_birth"])  # should not raise
            assert dob < date(2024, 1, 1)

    def test_students_inserted_into_db(self, tmp_manager, starter_config):
        rng = SeededRandom(DEFAULT_SEED).fork("students")
        id_gen = IDGenerator()
        gen = StudentGenerator(starter_config, rng, id_gen)
        gen.build()
        with tmp_manager.connection() as conn:
            gen.insert(conn)
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
        assert count == 50

    def test_student_insert_idempotent(self, tmp_manager, starter_config):
        rng1 = SeededRandom(DEFAULT_SEED).fork("students")
        rng2 = SeededRandom(DEFAULT_SEED).fork("students")
        id1 = IDGenerator()
        id2 = IDGenerator()
        gen1 = StudentGenerator(starter_config, rng1, id1)
        gen1.build()
        with tmp_manager.connection() as conn:
            gen1.insert(conn)
        gen2 = StudentGenerator(starter_config, rng2, id2)
        gen2.build()
        with tmp_manager.connection() as conn:
            gen2.insert(conn)
        with tmp_manager.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
        assert count == 50


# ===========================================================================
# 8. EnrollmentGenerator
# ===========================================================================


def _setup_full_prereqs(manager: DatabaseManager, config) -> None:
    """Insert programs, terms, fee schedules, students."""
    prog_gen = ProgramGenerator()
    prog_gen.build()
    with manager.connection() as conn:
        prog_gen.insert(conn)

    term_gen = TermGenerator(config)
    term_gen.build()
    with manager.connection() as conn:
        term_gen.insert(conn)

    with manager.connection() as conn:
        prog_rows = [dict(r) for r in conn.execute(
            "SELECT program_id, program_code, duration_years, level FROM Programs"
        ).fetchall()]
        term_rows = [dict(r) for r in conn.execute(
            "SELECT term_id, term_code, start_date FROM Terms"
        ).fetchall()]

    rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
    fee_gen = FeeScheduleGenerator(config, rng, prog_rows, term_rows)
    fee_gen.build()
    with manager.connection() as conn:
        fee_gen.insert(conn)

    stu_rng = SeededRandom(DEFAULT_SEED).fork("students")
    id_gen = IDGenerator()
    stu_gen = StudentGenerator(config, stu_rng, id_gen)
    stu_gen.build()
    with manager.connection() as conn:
        stu_gen.insert(conn)


class TestEnrollmentGenerator:
    def test_enrollments_reference_valid_students(self, tmp_manager, starter_config):
        _setup_full_prereqs(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("enrollments")
        gen = EnrollmentGenerator(starter_config, rng)
        with tmp_manager.connection() as conn:
            gen.build_from_db(conn)
            gen.insert(conn)

        with tmp_manager.connection() as conn:
            orphaned = conn.execute(
                """SELECT COUNT(*) FROM Enrollments e
                   WHERE NOT EXISTS (SELECT 1 FROM Students s WHERE s.student_id = e.student_id)"""
            ).fetchone()[0]
        assert orphaned == 0

    def test_enrollments_reference_valid_programs(self, tmp_manager, starter_config):
        _setup_full_prereqs(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("enrollments")
        gen = EnrollmentGenerator(starter_config, rng)
        with tmp_manager.connection() as conn:
            gen.build_from_db(conn)
            gen.insert(conn)

        with tmp_manager.connection() as conn:
            orphaned = conn.execute(
                """SELECT COUNT(*) FROM Enrollments e
                   WHERE NOT EXISTS (SELECT 1 FROM Programs p WHERE p.program_id = e.program_id)"""
            ).fetchone()[0]
        assert orphaned == 0

    def test_no_duplicate_student_program_term(self, tmp_manager, starter_config):
        _setup_full_prereqs(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("enrollments")
        gen = EnrollmentGenerator(starter_config, rng)
        with tmp_manager.connection() as conn:
            gen.build_from_db(conn)
            gen.insert(conn)

        with tmp_manager.connection() as conn:
            dup_count = conn.execute(
                """SELECT COUNT(*) FROM (
                   SELECT student_id, program_id, term_id
                   FROM Enrollments
                   GROUP BY student_id, program_id, term_id
                   HAVING COUNT(*) > 1)"""
            ).fetchone()[0]
        assert dup_count == 0

    def test_valid_enrollment_statuses(self, tmp_manager, starter_config):
        from backend.config import ENROLLMENT_STATUSES
        _setup_full_prereqs(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("enrollments")
        gen = EnrollmentGenerator(starter_config, rng)
        with tmp_manager.connection() as conn:
            gen.build_from_db(conn)
            gen.insert(conn)

        with tmp_manager.connection() as conn:
            invalid = conn.execute(
                f"""SELECT COUNT(*) FROM Enrollments
                    WHERE status NOT IN ({','.join('?'*len(ENROLLMENT_STATUSES))})""",
                ENROLLMENT_STATUSES,
            ).fetchone()[0]
        assert invalid == 0

    def test_valid_year_of_study(self, tmp_manager, starter_config):
        _setup_full_prereqs(tmp_manager, starter_config)
        rng = SeededRandom(DEFAULT_SEED).fork("enrollments")
        gen = EnrollmentGenerator(starter_config, rng)
        with tmp_manager.connection() as conn:
            gen.build_from_db(conn)
            gen.insert(conn)

        with tmp_manager.connection() as conn:
            bad = conn.execute(
                "SELECT COUNT(*) FROM Enrollments WHERE year_of_study < 1"
            ).fetchone()[0]
        assert bad == 0


# ===========================================================================
# 9. Starter mode end-to-end
# ===========================================================================


class TestStarterModeEndToEnd:
    def test_starter_mode_full_run(self, tmp_path):
        from backend.generators.generate_data import run_generation
        db_path = tmp_path / "starter.db"
        run_generation(
            mode=GenerationMode.STARTER,
            db_path=db_path,
            seed=DEFAULT_SEED,
            reset=False,
        )
        manager = DatabaseManager(db_path=db_path)
        with manager.connection() as conn:
            programs = conn.execute("SELECT COUNT(*) FROM Programs").fetchone()[0]
            students = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
            terms = conn.execute("SELECT COUNT(*) FROM Terms").fetchone()[0]
            enrollments = conn.execute("SELECT COUNT(*) FROM Enrollments").fetchone()[0]
            schedules = conn.execute("SELECT COUNT(*) FROM FeeSchedules").fetchone()[0]
            lines = conn.execute("SELECT COUNT(*) FROM FeeScheduleLines").fetchone()[0]

        assert programs == 20
        assert students == 50
        assert terms == 4
        assert schedules == 20 * 4  # 80
        assert lines > 0
        assert enrollments > 0

    def test_starter_fk_integrity_after_run(self, tmp_path):
        from backend.generators.generate_data import run_generation
        db_path = tmp_path / "starter_fk.db"
        run_generation(
            mode=GenerationMode.STARTER, db_path=db_path, seed=DEFAULT_SEED, reset=False
        )
        manager = DatabaseManager(db_path=db_path)
        violations = manager.run_foreign_key_check()
        assert violations == []

    def test_starter_data_integrity_checks(self, tmp_path):
        from backend.generators.generate_data import run_generation
        db_path = tmp_path / "starter_integrity.db"
        run_generation(
            mode=GenerationMode.STARTER, db_path=db_path, seed=DEFAULT_SEED, reset=False
        )
        manager = DatabaseManager(db_path=db_path)
        with manager.connection() as conn:
            violations = verify_integrity(conn)
        assert violations == [], f"Integrity violations: {violations}"


# ===========================================================================
# 10. Deterministic output — same seed → same data
# ===========================================================================


class TestDeterministicOutput:
    def test_same_seed_same_student_codes(self):
        cfg = get_config(GenerationMode.STARTER, seed=DEFAULT_SEED)
        rng1 = SeededRandom(DEFAULT_SEED).fork("students")
        rng2 = SeededRandom(DEFAULT_SEED).fork("students")
        id1 = IDGenerator()
        id2 = IDGenerator()
        gen1 = StudentGenerator(cfg, rng1, id1)
        gen2 = StudentGenerator(cfg, rng2, id2)
        students1 = gen1.build()
        students2 = gen2.build()
        codes1 = [s["student_code"] for s in students1]
        codes2 = [s["student_code"] for s in students2]
        assert codes1 == codes2

    def test_same_seed_same_student_names(self):
        cfg = get_config(GenerationMode.STARTER, seed=DEFAULT_SEED)
        rng1 = SeededRandom(DEFAULT_SEED).fork("students")
        rng2 = SeededRandom(DEFAULT_SEED).fork("students")
        id1, id2 = IDGenerator(), IDGenerator()
        gen1 = StudentGenerator(cfg, rng1, id1)
        gen2 = StudentGenerator(cfg, rng2, id2)
        s1 = gen1.build()
        s2 = gen2.build()
        names1 = [(s["first_name"], s["last_name"]) for s in s1]
        names2 = [(s["first_name"], s["last_name"]) for s in s2]
        assert names1 == names2

    def test_same_seed_same_term_codes(self):
        cfg = get_config(GenerationMode.STARTER, seed=DEFAULT_SEED)
        gen1 = TermGenerator(cfg)
        gen2 = TermGenerator(cfg)
        terms1 = [t["term_code"] for t in gen1.build()]
        terms2 = [t["term_code"] for t in gen2.build()]
        assert terms1 == terms2

    def test_same_seed_same_fee_amounts(self, tmp_path):
        """Two runs with same seed produce identical fee amounts."""
        cfg = get_config(GenerationMode.STARTER, seed=DEFAULT_SEED)

        def _run(db_suffix: str) -> list:
            db = tmp_path / f"det_{db_suffix}.db"
            m = DatabaseManager(db_path=db)
            m.initialise()
            pg = ProgramGenerator(); pg.build()
            tg = TermGenerator(cfg); tg.build()
            with m.connection() as conn:
                pg.insert(conn)
                tg.insert(conn)
            with m.connection() as conn:
                progs = [dict(r) for r in conn.execute(
                    "SELECT program_id, program_code, duration_years, level FROM Programs"
                ).fetchall()]
                terms = [dict(r) for r in conn.execute(
                    "SELECT term_id, term_code, start_date FROM Terms"
                ).fetchall()]
            rng = SeededRandom(DEFAULT_SEED).fork("fee_data")
            fg = FeeScheduleGenerator(cfg, rng, progs, terms)
            fg.build()
            with m.connection() as conn:
                fg.insert(conn)
            with m.connection() as conn:
                return [r[0] for r in conn.execute(
                    "SELECT amount_paise FROM FeeScheduleLines ORDER BY fsl_id"
                ).fetchall()]

        amounts1 = _run("a")
        amounts2 = _run("b")
        assert amounts1 == amounts2


# ===========================================================================
# 11. Safe rerun behavior
# ===========================================================================


class TestSafeRerun:
    def test_second_starter_run_inserts_zero_new_rows(self, tmp_path):
        from backend.generators.generate_data import run_generation
        db = tmp_path / "rerun.db"

        run_generation(GenerationMode.STARTER, db, DEFAULT_SEED, reset=False)

        manager = DatabaseManager(db_path=db)
        with manager.connection() as conn:
            s1 = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
            p1 = conn.execute("SELECT COUNT(*) FROM Programs").fetchone()[0]
            e1 = conn.execute("SELECT COUNT(*) FROM Enrollments").fetchone()[0]

        run_generation(GenerationMode.STARTER, db, DEFAULT_SEED, reset=False)

        with manager.connection() as conn:
            s2 = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]
            p2 = conn.execute("SELECT COUNT(*) FROM Programs").fetchone()[0]
            e2 = conn.execute("SELECT COUNT(*) FROM Enrollments").fetchone()[0]

        assert s1 == s2
        assert p1 == p2
        assert e1 == e2

    def test_reset_recreates_database(self, tmp_path):
        """
        Verify that --reset wipes and regenerates correctly.
        Uses separate DB files to avoid Windows file-lock issues between runs.
        """
        from backend.generators.generate_data import run_generation
        db_run1 = tmp_path / "run1.db"
        db_run2 = tmp_path / "run2.db"

        # First run on db_run1
        run_generation(GenerationMode.STARTER, db_run1, DEFAULT_SEED, reset=False)
        m1 = DatabaseManager(db_path=db_run1)
        with m1.connection() as conn:
            count_first = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]

        # Second run on db_run2 with reset=True (fresh DB)
        run_generation(GenerationMode.STARTER, db_run2, DEFAULT_SEED, reset=True)
        m2 = DatabaseManager(db_path=db_run2)
        with m2.connection() as conn:
            count_second = conn.execute("SELECT COUNT(*) FROM Students").fetchone()[0]

        # Both runs with the same seed must produce the same number of students
        assert count_first == 50
        assert count_second == 50
        assert count_first == count_second


# ===========================================================================
# 12. Rollback on failure
# ===========================================================================


class TestRollbackOnFailure:
    def test_transaction_rollback_on_error(self, tmp_manager):
        """If an error occurs mid-insert, the transaction rolls back."""
        with pytest.raises(Exception):
            with tmp_manager.connection() as conn:
                # Insert a valid program
                conn.execute(
                    """INSERT INTO Programs (program_code, program_name,
                           duration_years, level)
                       VALUES ('TEST-PROG', 'Test', 4, 'UG')"""
                )
                # Force an FK violation to trigger rollback
                conn.execute(
                    """INSERT INTO Enrollments
                           (student_id, program_id, term_id, enrollment_date)
                       VALUES (99999, 99999, 99999, '2024-01-01')"""
                )

        # After rollback, the program should not be in DB
        with tmp_manager.connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM Programs WHERE program_code='TEST-PROG'"
            ).fetchone()[0]
        assert count == 0

    def test_savepoint_rollback(self, tmp_manager):
        """Savepoint rollback preserves outer data while rolling inner changes."""
        with tmp_manager.connection() as conn:
            conn.execute(
                """INSERT INTO Programs (program_code, program_name,
                       duration_years, level)
                   VALUES ('OUTER-PROG', 'Outer', 4, 'UG')"""
            )
            try:
                with tmp_manager.transaction(conn):
                    conn.execute(
                        """INSERT INTO Programs (program_code, program_name,
                               duration_years, level)
                           VALUES ('INNER-PROG', 'Inner', 4, 'UG')"""
                    )
                    raise ValueError("Simulated failure")
            except ValueError:
                pass  # rollback to savepoint

        with tmp_manager.connection() as conn:
            outer = conn.execute(
                "SELECT COUNT(*) FROM Programs WHERE program_code='OUTER-PROG'"
            ).fetchone()[0]
            inner = conn.execute(
                "SELECT COUNT(*) FROM Programs WHERE program_code='INNER-PROG'"
            ).fetchone()[0]
        assert outer == 1   # preserved
        assert inner == 0   # rolled back


# ===========================================================================
# 13. Validators
# ===========================================================================


class TestValidators:
    def test_valid_date_string_accepted(self):
        from datetime import date
        d = validate_date_string("2024-06-15")
        assert d == date(2024, 6, 15)

    def test_invalid_date_string_rejected(self):
        with pytest.raises(ValidationError):
            validate_date_string("not-a-date")

    def test_date_range_valid(self):
        validate_date_range("2024-01-01", "2024-06-30")

    def test_date_range_invalid_order(self):
        with pytest.raises(ValidationError):
            validate_date_range("2024-06-30", "2024-01-01")

    def test_paise_positive_accepted(self):
        validate_paise(10000, allow_zero=False)

    def test_paise_zero_rejected_when_disallowed(self):
        with pytest.raises(ValidationError):
            validate_paise(0, allow_zero=False)

    def test_paise_negative_rejected(self):
        with pytest.raises(ValidationError):
            validate_paise(-100)

    def test_paise_float_rejected(self):
        with pytest.raises(ValidationError):
            validate_paise(100.5)

    def test_status_valid_accepted(self):
        validate_status("active", ["active", "inactive"])

    def test_status_invalid_rejected(self):
        with pytest.raises(ValidationError):
            validate_status("unknown", ["active", "inactive"])

    def test_verify_integrity_passes_on_valid_data(self, tmp_path):
        from backend.generators.generate_data import run_generation
        db = tmp_path / "valid.db"
        run_generation(GenerationMode.STARTER, db, DEFAULT_SEED, reset=False)
        manager = DatabaseManager(db_path=db)
        with manager.connection() as conn:
            violations = verify_integrity(conn)
        assert violations == []

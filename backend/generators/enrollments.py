"""
backend/generators/enrollments.py
====================================
Generates student enrollment records.

Design
------
* Each student is enrolled in 1–N terms based on avg_terms_per_student.
* A student can be enrolled in at most one program per term (enforced by DB UNIQUE).
* Students are assigned a program at their first enrollment; subsequent
  enrollments (different terms) use the same program (continuing student model).
* About 10% of students switch programs mid-way to model reality.
* year_of_study increments with each subsequent term enrollment.
* Enrollment status is weighted per config.enrollment_status_weights.
* The fee_schedule_id is looked up from FeeSchedules for the (program, term) pair.
* Enrollment dates are chosen within the term start date + 30 days window.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.config import GenerationConfig
from backend.seed_manager import SeededRandom
from backend.validators import validate_enrollment_row

logger = logging.getLogger(__name__)


class EnrollmentGenerator:
    """
    Generates enrollment records for all students.

    Parameters
    ----------
    config : GenerationConfig
    rng : SeededRandom
        Child RNG forked with label "enrollments".
    """

    def __init__(self, config: GenerationConfig, rng: SeededRandom) -> None:
        self._config = config
        self._rng = rng
        self._enrollments: List[Dict[str, Any]] = []

    def build_from_db(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """
        Generate enrollment records by reading students, programs, terms,
        and fee schedules from the database.

        This approach ensures all FK references are valid — we only
        reference IDs that actually exist.

        Returns
        -------
        list[dict]
            Each dict contains enrollment fields ready for insertion.
        """
        # Load existing data from DB
        students = conn.execute(
            "SELECT student_id, student_code, status FROM Students ORDER BY student_id"
        ).fetchall()

        programs = conn.execute(
            "SELECT program_id, program_code, duration_years, level FROM Programs ORDER BY program_id"
        ).fetchall()

        terms = conn.execute(
            "SELECT term_id, term_code, start_date FROM Terms ORDER BY term_id"
        ).fetchall()

        # Build fee schedule lookup: (program_id, term_id) → schedule_id
        fee_schedule_lookup: Dict[Tuple[int, int], int] = {}
        rows = conn.execute(
            "SELECT schedule_id, program_id, term_id FROM FeeSchedules WHERE status='active'"
        ).fetchall()
        for row in rows:
            fee_schedule_lookup[(row["program_id"], row["term_id"])] = row["schedule_id"]

        if not students or not programs or not terms:
            logger.warning("No students/programs/terms found — skipping enrollment generation.")
            self._enrollments = []
            return []

        rng = self._rng
        avg_terms = self._config.avg_terms_per_student

        status_items = list(self._config.enrollment_status_weights.keys())
        status_weights = list(self._config.enrollment_status_weights.values())

        self._enrollments = []
        # Track (student_id, program_id, term_id) to prevent duplicates
        seen_triples: Set[Tuple[int, int, int]] = set()

        for student in students:
            sid = student["student_id"]
            student_status = student["status"]

            # Determine how many terms this student will enroll in
            # Poisson-like: mostly 1–3 terms, rarely more
            num_terms_for_student = max(
                1,
                min(
                    len(terms),
                    round(rng.uniform(0.5, avg_terms * 1.8)),
                ),
            )

            # Pick a starting term index for this student
            start_term_idx = rng.randint(0, max(0, len(terms) - num_terms_for_student))

            # Assign a primary program for this student
            primary_program = rng.choice(programs)
            program_switched = False

            for year_of_study, term_offset in enumerate(
                range(start_term_idx, start_term_idx + num_terms_for_student), start=1
            ):
                if term_offset >= len(terms):
                    break

                term = terms[term_offset]
                tid = term["term_id"]
                term_start = date.fromisoformat(term["start_date"])

                # Occasionally switch program (new program, different term = new enrollment)
                if (
                    not program_switched
                    and year_of_study > 1
                    and rng.random() < 0.05  # 5% chance of program switch per term
                ):
                    primary_program = rng.choice(programs)
                    program_switched = True
                    year_of_study = 1  # reset year of study for new program

                pid = primary_program["program_id"]

                triple = (sid, pid, tid)
                if triple in seen_triples:
                    continue
                seen_triples.add(triple)

                # Enrollment date: within first 30 days of term start
                enroll_offset = rng.randint(0, 30)
                enrollment_date = (term_start + timedelta(days=enroll_offset)).isoformat()

                # Enrollment status: completed/withdrawn for early terms; enrolled for recent
                if term_offset < len(terms) - 2:
                    status = rng.weighted_choice(
                        ["completed", "withdrawn", "enrolled"],
                        [0.65, 0.15, 0.20],
                    )
                else:
                    status = rng.weighted_choice(status_items, status_weights)

                # If student is withdrawn/graduated, mark enrollment accordingly
                if student_status == "withdrawn" and status == "enrolled":
                    status = "withdrawn"
                elif student_status == "graduated" and status == "enrolled":
                    status = "completed"

                fee_schedule_id = fee_schedule_lookup.get((pid, tid))

                row: Dict[str, Any] = {
                    "student_id":     sid,
                    "program_id":     pid,
                    "term_id":        tid,
                    "enrollment_date": enrollment_date,
                    "status":         status,
                    "year_of_study":  max(1, year_of_study),
                    "fee_schedule_id": fee_schedule_id,
                    "notes":          None,
                }
                validate_enrollment_row(row)
                self._enrollments.append(row)

        logger.debug("Built %d enrollment records.", len(self._enrollments))
        return self._enrollments

    def insert(self, conn: sqlite3.Connection, batch_size: int = 500) -> Dict[str, int]:
        """
        Insert enrollment records into the database.

        Uses INSERT OR IGNORE to handle the UNIQUE(student_id, program_id, term_id)
        constraint gracefully on reruns.

        Returns
        -------
        dict with inserted and skipped counts.
        """
        if not self._enrollments:
            logger.warning("No enrollments built — call build_from_db() first.")
            return {"inserted": 0, "skipped": 0}

        before_count = conn.execute("SELECT COUNT(*) FROM Enrollments").fetchone()[0]

        batch: List[Dict[str, Any]] = []

        def _flush(b: List[Dict[str, Any]]) -> None:
            conn.executemany(
                """INSERT OR IGNORE INTO Enrollments
                       (student_id, program_id, term_id, enrollment_date,
                        status, year_of_study, fee_schedule_id, notes)
                   VALUES (:student_id, :program_id, :term_id, :enrollment_date,
                           :status, :year_of_study, :fee_schedule_id, :notes)""",
                b,
            )

        for row in self._enrollments:
            batch.append(row)
            if len(batch) >= batch_size:
                _flush(batch)
                batch.clear()

        if batch:
            _flush(batch)

        after_count = conn.execute("SELECT COUNT(*) FROM Enrollments").fetchone()[0]
        inserted = after_count - before_count
        skipped = len(self._enrollments) - inserted

        logger.info(
            "Enrollments: %d inserted, %d skipped (duplicates or conflicts).",
            inserted,
            skipped,
        )
        return {"inserted": inserted, "skipped": skipped}

    def get_enrollments(self) -> List[Dict[str, Any]]:
        return self._enrollments

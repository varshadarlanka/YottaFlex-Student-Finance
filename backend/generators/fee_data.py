"""
backend/generators/fee_data.py
================================
Generates FeeSchedules and FeeScheduleLines.

Design
------
* One active FeeSchedule per (Program, Term) pair.
* Each FeeSchedule gets its lines from the FEE_COMPONENTS catalogue
  for the programme level (UG, PG, PhD, Diploma, Certificate).
* Fee amounts are deterministically seeded — same seed → same amounts.
* All amounts are stored as integer paise (1 INR = 100 paise).
* Amounts are rounded to the nearest 100 paise (₹1 granularity).
* Uses INSERT OR IGNORE for safe reruns.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Tuple

from backend.config import FEE_COMPONENTS, GenerationConfig
from backend.id_generator import make_fee_schedule_code
from backend.seed_manager import SeededRandom
from backend.validators import validate_fee_schedule_line_row, validate_fee_schedule_row

logger = logging.getLogger(__name__)


class FeeScheduleGenerator:
    """
    Generates FeeSchedules and FeeScheduleLines for every (program, term) pair.

    Parameters
    ----------
    config : GenerationConfig
    rng : SeededRandom
        Child RNG forked from the main RNG with label "fee_data".
    program_rows : list[dict]
        Programme records already inserted into the DB (must include
        ``program_id``, ``program_code``, ``level``).
    term_rows : list[dict]
        Term records already inserted into the DB (must include
        ``term_id``, ``term_code``, ``start_date``).
    """

    def __init__(
        self,
        config: GenerationConfig,
        rng: SeededRandom,
        program_rows: List[Dict[str, Any]],
        term_rows: List[Dict[str, Any]],
    ) -> None:
        self._config = config
        self._rng = rng
        self._programs = program_rows
        self._terms = term_rows
        self._schedules: List[Dict[str, Any]] = []   # clean DB rows
        self._meta: List[Dict[str, Any]] = []          # private metadata per schedule
        self._lines: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Build phase (no DB required)
    # ------------------------------------------------------------------

    def build(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Generate all FeeSchedule and FeeScheduleLine dicts in memory.

        Returns
        -------
        (schedules, lines)
        """
        self._schedules = []
        self._meta = []
        self._lines = []

        # schedule_name → schedule dict (for deduplication in dry builds)
        seen_schedule_names: set = set()

        for prog in self._programs:
            prog_id = prog.get("program_id")
            prog_code = prog["program_code"]
            level = prog["level"]
            components = FEE_COMPONENTS.get(level, FEE_COMPONENTS["UG"])

            for term in self._terms:
                term_id = term.get("term_id")
                term_code = term["term_code"]
                schedule_name = make_fee_schedule_code(prog_code, term_code)

                if schedule_name in seen_schedule_names:
                    continue  # skip duplicates in dry-run mode
                seen_schedule_names.add(schedule_name)

                # Determine effective dates from the term
                effective_from = term["start_date"]

                # Clean DB row (no private keys)
                sched: Dict[str, Any] = {
                    "program_id":     prog_id,
                    "term_id":        term_id,
                    "schedule_name":  schedule_name,
                    "effective_from": effective_from,
                    "effective_to":   None,
                    "status":         "active",
                }
                # Private metadata stored separately — never mutated
                meta: Dict[str, Any] = {
                    "prog_code":  prog_code,
                    "term_code":  term_code,
                    "level":      level,
                    "components": components,
                }
                validate_fee_schedule_row(sched)
                self._schedules.append(sched)
                self._meta.append(meta)

        logger.debug("Built %d fee schedule records.", len(self._schedules))
        return self._schedules, self._lines

    def _build_lines_for_schedule(
        self,
        schedule_id: int,
        prog_code: str,
        level: str,
        components: list,
    ) -> List[Dict[str, Any]]:
        """Generate FeeScheduleLine dicts for one schedule."""
        lines = []
        for sort_order, (fee_type, desc, min_inr, max_inr, mandatory) in enumerate(
            components, start=1
        ):
            # Deterministic amount: seed the amount from prog+fee_type
            # Use rng to pick a value in the INR range, then convert to paise
            # Round to nearest 100 paise (₹1)
            raw_inr = self._rng.randint(min_inr, max_inr)
            # Round to nearest 500 INR for realism
            rounded_inr = round(raw_inr / 500) * 500
            if rounded_inr < min_inr:
                rounded_inr = min_inr
            amount_paise = rounded_inr * 100  # INR → paise

            line: Dict[str, Any] = {
                "schedule_id":  schedule_id,
                "fee_type":     fee_type,
                "description":  desc,
                "amount_paise": amount_paise,
                "is_mandatory": 1 if mandatory else 0,
                "sort_order":   sort_order,
            }
            validate_fee_schedule_line_row(line)
            lines.append(line)
        return lines

    # ------------------------------------------------------------------
    # Insert phase (requires DB)
    # ------------------------------------------------------------------

    def insert(self, conn: sqlite3.Connection) -> Dict[str, int]:
        """
        Insert all FeeSchedules and FeeScheduleLines.

        Schedules are inserted first; their IDs are used for lines.
        Idempotent: checks by schedule_name before inserting.

        Returns
        -------
        dict with keys: schedules_inserted, schedules_skipped, lines_inserted
        """
        if not self._schedules:
            self.build()

        stats = {"schedules_inserted": 0, "schedules_skipped": 0, "lines_inserted": 0}
        all_lines: List[Dict[str, Any]] = []

        for sched, meta in zip(self._schedules, self._meta):
            # Read metadata without mutating the schedule dict
            prog_code  = meta["prog_code"]
            level      = meta["level"]
            components = meta["components"]

            # Check if this schedule already exists (by schedule_name)
            existing = conn.execute(
                "SELECT schedule_id FROM FeeSchedules WHERE schedule_name = ?",
                (sched["schedule_name"],),
            ).fetchone()

            if existing:
                schedule_id = existing[0]
                stats["schedules_skipped"] += 1
            else:
                cur = conn.execute(
                    """INSERT INTO FeeSchedules
                           (program_id, term_id, schedule_name, effective_from,
                            effective_to, status)
                       VALUES (:program_id, :term_id, :schedule_name, :effective_from,
                               :effective_to, :status)""",
                    sched,
                )
                schedule_id = cur.lastrowid
                stats["schedules_inserted"] += 1

            # Generate lines for this schedule (skip if already have lines)
            existing_lines = conn.execute(
                "SELECT COUNT(*) FROM FeeScheduleLines WHERE schedule_id = ?",
                (schedule_id,),
            ).fetchone()[0]

            if existing_lines == 0:
                lines = self._build_lines_for_schedule(
                    schedule_id, prog_code, level, components
                )
                for line in lines:
                    conn.execute(
                        """INSERT INTO FeeScheduleLines
                               (schedule_id, fee_type, description,
                                amount_paise, is_mandatory, sort_order)
                           VALUES (:schedule_id, :fee_type, :description,
                                   :amount_paise, :is_mandatory, :sort_order)""",
                        line,
                    )
                    stats["lines_inserted"] += 1
                    all_lines.append(line)

        logger.info(
            "FeeSchedules: %d inserted, %d skipped. FeeScheduleLines: %d inserted.",
            stats["schedules_inserted"],
            stats["schedules_skipped"],
            stats["lines_inserted"],
        )
        self._lines = all_lines
        return stats

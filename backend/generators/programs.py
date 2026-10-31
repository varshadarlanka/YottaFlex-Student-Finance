"""
backend/generators/programs.py
================================
Generates 20 distinct academic programs.

Design
------
* The 20 programs are defined as a static catalogue rather than being
  randomly chosen — this ensures diversity and avoids 20 copies of the
  same type.
* Program codes are deterministic: PROG-{index:02d}-{slug}.
* All 20 programs are generated regardless of mode (starter uses the
  same programs as full so fees and enrollments stay consistent).
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List

from backend.id_generator import make_program_code
from backend.validators import validate_program_row

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static programme catalogue — 20 distinct, realistic programmes.
# Layout: (slug, name, department, duration_years, level)
# ---------------------------------------------------------------------------
_PROGRAM_CATALOGUE: List[tuple] = [
    # UG — 4 yr
    ("BTECH-CSE",   "B.Tech Computer Science & Engineering",  "Engineering",         4, "UG"),
    ("BTECH-ECE",   "B.Tech Electronics & Communication Eng", "Engineering",         4, "UG"),
    ("BTECH-MECH",  "B.Tech Mechanical Engineering",          "Engineering",         4, "UG"),
    ("BTECH-CIVIL", "B.Tech Civil Engineering",               "Engineering",         4, "UG"),
    ("BTECH-EEE",   "B.Tech Electrical & Electronics Eng",    "Engineering",         4, "UG"),
    ("BCA",         "Bachelor of Computer Applications",      "Computing",           3, "UG"),
    ("BSC-PHY",     "B.Sc Physics",                           "Sciences",            3, "UG"),
    ("BSC-CHEM",    "B.Sc Chemistry",                         "Sciences",            3, "UG"),
    ("BCOM-GEN",    "B.Com General",                          "Commerce",            3, "UG"),
    ("BBA",         "Bachelor of Business Administration",    "Management",          3, "UG"),
    # PG — 2 yr
    ("MTECH-CSE",   "M.Tech Computer Science & Engineering",  "Engineering",         2, "PG"),
    ("MBA-FIN",     "MBA Finance",                            "Management",          2, "PG"),
    ("MBA-MKTG",    "MBA Marketing",                          "Management",          2, "PG"),
    ("MCA",         "Master of Computer Applications",        "Computing",           2, "PG"),
    ("MSC-DATA",    "M.Sc Data Science",                      "Sciences",            2, "PG"),
    # PhD — 3 yr
    ("PHD-CSE",     "Ph.D Computer Science",                  "Research",            3, "PhD"),
    ("PHD-MGMT",    "Ph.D Management",                        "Research",            3, "PhD"),
    # Diploma — 1 yr
    ("DIP-CS",      "Diploma in Computer Science",            "Computing",           1, "Diploma"),
    ("DIP-ELEC",    "Diploma in Electronics",                 "Engineering",         1, "Diploma"),
    # Certificate — 0.5 yr → stored as 1 yr (min duration_years=1)
    ("CERT-AIML",   "Certificate in AI & Machine Learning",   "Computing",           1, "Certificate"),
]

assert len(_PROGRAM_CATALOGUE) == 20, "Programme catalogue must contain exactly 20 programmes."


class ProgramGenerator:
    """
    Generates all 20 academic programmes and inserts them into the database.

    The programme list is static to guarantee diversity.  The same 20
    programmes are used in both starter and full modes.
    """

    def __init__(self) -> None:
        self._programmes: List[Dict[str, Any]] = []

    def build(self) -> List[Dict[str, Any]]:
        """
        Build the list of 20 programme dicts.

        Returns
        -------
        list[dict]
            Each dict matches the Programs table columns.
        """
        self._programmes = []
        for idx, (slug, name, dept, dur, level) in enumerate(_PROGRAM_CATALOGUE, start=1):
            code = make_program_code(idx, slug)
            row: Dict[str, Any] = {
                "program_code":   code,
                "program_name":   name,
                "department":     dept,
                "duration_years": dur,
                "level":          level,
                "is_active":      1,
            }
            validate_program_row(row)
            self._programmes.append(row)

        logger.debug("Built %d programme records.", len(self._programmes))
        return self._programmes

    def insert(self, conn: sqlite3.Connection) -> List[int]:
        """
        Insert all programmes into the database within the given connection.

        Uses INSERT OR IGNORE to make reruns safe — if a program with the
        same program_code already exists it is skipped.

        Parameters
        ----------
        conn : sqlite3.Connection
            An open, FK-enabled connection (not yet committed).

        Returns
        -------
        list[int]
            Row-IDs of newly inserted rows (already-existing rows are 0).
        """
        if not self._programmes:
            self.build()

        ids: List[int] = []
        for row in self._programmes:
            cur = conn.execute(
                """INSERT OR IGNORE INTO Programs
                       (program_code, program_name, department,
                        duration_years, level, is_active)
                   VALUES (:program_code, :program_name, :department,
                           :duration_years, :level, :is_active)""",
                row,
            )
            ids.append(cur.lastrowid or 0)

        inserted = sum(1 for i in ids if i > 0)
        skipped = len(ids) - inserted
        logger.info(
            "Programs: %d inserted, %d already existed (skipped).",
            inserted,
            skipped,
        )
        return ids

    def get_programmes(self) -> List[Dict[str, Any]]:
        """Return built programme list (calls build() if not yet done)."""
        if not self._programmes:
            self.build()
        return self._programmes

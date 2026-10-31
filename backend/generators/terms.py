"""
backend/generators/terms.py
============================
Generates academic terms (semesters).

Design
------
* Terms follow a two-semester pattern per year: SPRING and FALL.
* A SPRING term runs Jan–Jun; a FALL term runs Jul–Dec.
* The base_year determines which calendar years are covered.
* For 4 terms (starter): 2024-SPRING, 2024-FALL, 2025-SPRING, 2025-FALL
* For 6 terms (full):    + 2026-SPRING, 2026-FALL
* Term codes are deterministic: TERM-{year}-{season}.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List

from backend.config import GenerationConfig
from backend.id_generator import make_term_code
from backend.validators import validate_term_row

logger = logging.getLogger(__name__)

# Term season definitions: (season_name, month_start, day_start, month_end, day_end)
_SEASONS = [
    ("SPRING", 1, 1,  6, 30),
    ("FALL",   7, 1, 12, 31),
]


class TermGenerator:
    """
    Generates academic term records.

    Produces ``config.num_terms`` terms, cycling through SPRING/FALL
    seasons starting from ``config.base_year``.
    """

    def __init__(self, config: GenerationConfig) -> None:
        self._config = config
        self._terms: List[Dict[str, Any]] = []

    def build(self) -> List[Dict[str, Any]]:
        """
        Build term records.

        Returns
        -------
        list[dict]
            Each dict matches the Terms table columns.
        """
        self._terms = []
        num_terms = self._config.num_terms
        base_year = self._config.base_year
        season_pool = _SEASONS  # cycle through seasons

        year = base_year
        season_idx = 0

        for _ in range(num_terms):
            season_name, m_start, d_start, m_end, d_end = season_pool[season_idx]
            term_code = make_term_code(year, season_name)
            term_name = f"{year} {season_name.capitalize()} Semester"

            start_date = f"{year}-{m_start:02d}-{d_start:02d}"
            end_date = f"{year}-{m_end:02d}-{d_end:02d}"

            row: Dict[str, Any] = {
                "term_code":  term_code,
                "term_name":  term_name,
                "start_date": start_date,
                "end_date":   end_date,
                "is_active":  1,
            }
            validate_term_row(row)
            self._terms.append(row)

            # Advance season
            season_idx += 1
            if season_idx >= len(season_pool):
                season_idx = 0
                year += 1

        logger.debug("Built %d term records.", len(self._terms))
        return self._terms

    def insert(self, conn: sqlite3.Connection) -> List[int]:
        """
        Insert all terms into the database.

        Uses INSERT OR IGNORE to make reruns safe.

        Returns
        -------
        list[int]
            Lastrowids (0 for already-existing rows).
        """
        if not self._terms:
            self.build()

        ids: List[int] = []
        for row in self._terms:
            cur = conn.execute(
                """INSERT OR IGNORE INTO Terms
                       (term_code, term_name, start_date, end_date, is_active)
                   VALUES (:term_code, :term_name, :start_date, :end_date, :is_active)""",
                row,
            )
            ids.append(cur.lastrowid or 0)

        inserted = sum(1 for i in ids if i > 0)
        logger.info(
            "Terms: %d inserted, %d already existed (skipped).",
            inserted,
            len(ids) - inserted,
        )
        return ids

    def get_terms(self) -> List[Dict[str, Any]]:
        if not self._terms:
            self.build()
        return self._terms

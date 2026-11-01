"""
backend/config.py
==================
Centralised configuration for the Student Finance Management backend.

All generation parameters, mode definitions, seed values, and status
constants live here.  No hardcoded numbers anywhere else in the backend.

Usage
-----
    from backend.config import get_config, GenerationMode

    cfg = get_config(GenerationMode.FULL)
    print(cfg.num_students)   # 10000
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Project root — used for default paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "backend" / "database" / "student_finance.db"

# ---------------------------------------------------------------------------
# Fixed random seed (required by the challenge)
# ---------------------------------------------------------------------------
DEFAULT_SEED: int = 20261022

# ---------------------------------------------------------------------------
# Generation modes
# ---------------------------------------------------------------------------


class GenerationMode(str, Enum):
    STARTER = "starter"
    FULL = "full"


# ---------------------------------------------------------------------------
# Fee components per program level (amount ranges in INR; converted to paise)
# Layout: (fee_type, description, base_inr_min, base_inr_max, is_mandatory)
# ---------------------------------------------------------------------------
FEE_COMPONENTS: Dict[str, List[Tuple[str, str, int, int, bool]]] = {
    "UG": [
        ("Tuition",        "Tuition fee",          80_000, 150_000, True),
        ("Exam",           "Examination fee",        3_000,   6_000, True),
        ("Library",        "Library access fee",     2_000,   4_000, True),
        ("Sports",         "Sports & fitness fee",   1_500,   3_000, False),
        ("Lab",            "Laboratory usage fee",   4_000,  12_000, False),
        ("Development",    "Campus development fee", 5_000,  10_000, True),
    ],
    "PG": [
        ("Tuition",        "Tuition fee",         120_000, 220_000, True),
        ("Exam",           "Examination fee",        4_000,   8_000, True),
        ("Library",        "Library access fee",     3_000,   5_000, True),
        ("Lab",            "Laboratory usage fee",   5_000,  15_000, False),
        ("Development",    "Campus development fee", 6_000,  12_000, True),
        ("Research",       "Research resource fee",  8_000,  20_000, False),
    ],
    "PhD": [
        ("Tuition",        "PhD programme fee",    150_000, 300_000, True),
        ("Exam",           "Thesis examination fee",  5_000,  10_000, True),
        ("Library",        "Library & journal fee",   4_000,   8_000, True),
        ("Research",       "Research resource fee",  15_000,  40_000, True),
        ("Stipend Admin",  "Stipend administration",  2_000,   5_000, False),
    ],
    "Diploma": [
        ("Tuition",        "Diploma tuition fee",   40_000,  80_000, True),
        ("Exam",           "Examination fee",         2_000,   4_000, True),
        ("Library",        "Library access fee",      1_000,   2_500, True),
        ("Lab",            "Laboratory usage fee",    2_000,   6_000, False),
        ("Development",    "Campus development fee",  3_000,   6_000, True),
    ],
    "Certificate": [
        ("Tuition",        "Certificate course fee", 20_000, 50_000, True),
        ("Exam",           "Examination fee",          1_500,  3_000, True),
        ("Material",       "Course material fee",      2_000,  5_000, True),
    ],
}

# ---------------------------------------------------------------------------
# Valid statuses (kept in sync with schema CHECK constraints)
# ---------------------------------------------------------------------------
STUDENT_STATUSES = ["active", "inactive", "graduated", "withdrawn", "suspended"]
ENROLLMENT_STATUSES = ["enrolled", "completed", "withdrawn", "suspended", "deferred"]
INVOICE_STATUSES = ["draft", "issued", "partially_paid", "paid", "overdue",
                    "cancelled", "refunded"]
FEE_SCHEDULE_STATUSES = ["draft", "active", "superseded", "archived"]
PAYMENT_STATUSES = ["pending", "cleared", "failed", "reversed", "refunded"]
REFUND_STATUSES = ["pending", "processed", "failed", "cancelled"]
SCHOLARSHIP_TYPES = ["Merit", "Need-based", "Government", "Sports",
                     "Minority", "Special", "Other"]
PAYMENT_METHODS = ["Cash", "UPI", "NetBanking", "ChequeDD",
                   "CardDebit", "CardCredit", "NEFT", "RTGS", "Other"]
PROGRAM_LEVELS = ["UG", "PG", "PhD", "Diploma", "Certificate"]

# ---------------------------------------------------------------------------
# Indian cities, states, and pincodes used for address generation
# ---------------------------------------------------------------------------
INDIAN_CITIES: List[Tuple[str, str, str]] = [
    # (city, state, pincode_prefix)
    ("Mumbai",       "Maharashtra",       "400"),
    ("Delhi",        "Delhi",             "110"),
    ("Bengaluru",    "Karnataka",         "560"),
    ("Hyderabad",    "Telangana",         "500"),
    ("Chennai",      "Tamil Nadu",        "600"),
    ("Kolkata",      "West Bengal",       "700"),
    ("Pune",         "Maharashtra",       "411"),
    ("Ahmedabad",    "Gujarat",           "380"),
    ("Jaipur",       "Rajasthan",         "302"),
    ("Lucknow",      "Uttar Pradesh",     "226"),
    ("Surat",        "Gujarat",           "395"),
    ("Kanpur",       "Uttar Pradesh",     "208"),
    ("Nagpur",       "Maharashtra",       "440"),
    ("Indore",       "Madhya Pradesh",    "452"),
    ("Bhopal",       "Madhya Pradesh",    "462"),
    ("Visakhapatnam","Andhra Pradesh",    "530"),
    ("Patna",        "Bihar",             "800"),
    ("Vadodara",     "Gujarat",           "390"),
    ("Coimbatore",   "Tamil Nadu",        "641"),
    ("Bhubaneswar",  "Odisha",            "751"),
]

GENDERS = ["M", "F", "O"]
GENDER_WEIGHTS = [0.48, 0.48, 0.04]


# ---------------------------------------------------------------------------
# Generation configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class GenerationConfig:
    """All parameters that drive synthetic data generation."""

    mode: GenerationMode
    seed: int

    # Counts
    num_students: int
    num_programs: int
    num_terms: int

    # Enrollment density
    # Average number of terms a student enrolls across
    avg_terms_per_student: float

    target_invoice_count: int | None = None
    target_award_count: int | None = None
    target_payment_count: int | None = None

    # Probability a student is still 'active' vs graduated/withdrawn/etc
    student_status_weights: Dict[str, float] = field(default_factory=dict)
    enrollment_status_weights: Dict[str, float] = field(default_factory=dict)

    # Reference year for term generation
    base_year: int = 2024

    def __post_init__(self) -> None:
        if not self.student_status_weights:
            self.student_status_weights = {
                "active": 0.72,
                "graduated": 0.15,
                "withdrawn": 0.07,
                "suspended": 0.04,
                "inactive": 0.02,
            }
        if not self.enrollment_status_weights:
            self.enrollment_status_weights = {
                "enrolled": 0.70,
                "completed": 0.18,
                "withdrawn": 0.07,
                "suspended": 0.03,
                "deferred": 0.02,
            }

    @property
    def total_expected_enrollments(self) -> int:
        """Rough estimate of total enrollments based on density."""
        return int(self.num_students * self.avg_terms_per_student)

    @property
    def total_expected_fee_schedules(self) -> int:
        return self.num_programs * self.num_terms

    @property
    def total_expected_fsl(self) -> int:
        # Average ~5 lines per schedule
        return self.total_expected_fee_schedules * 5


def get_config(
    mode: GenerationMode = GenerationMode.FULL,
    seed: int = DEFAULT_SEED,
) -> GenerationConfig:
    """
    Return a GenerationConfig for the specified mode.

    Parameters
    ----------
    mode : GenerationMode
        STARTER for quick dev/test; FULL for production-scale.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    GenerationConfig
    """
    if mode == GenerationMode.STARTER:
        return GenerationConfig(
            mode=mode,
            seed=seed,
            num_students=50,
            num_programs=20,       # same programs as full; avoid divergence
            num_terms=4,
            avg_terms_per_student=1.5,
            base_year=2024,
        )
    else:  # FULL
        return GenerationConfig(
            mode=mode,
            seed=seed,
            num_students=10_000,
            num_programs=20,
            num_terms=6,
            avg_terms_per_student=2.8,
            target_invoice_count=30_000,
            target_award_count=15_000,
            target_payment_count=50_000,
            base_year=2024,
        )

# Data Generation — Student Finance Management

> **Phase:** Part 2 — Backend Foundation & Master Data Generation
> **Branch:** `phase-1-foundation`

---

## 1. Architecture Overview

```
backend/
├── config.py            ← Centralised config: modes, seed, constants
├── id_generator.py      ← Deterministic, sequential ID generation
├── seed_manager.py      ← SeededRandom — reproducible RNG with fork()
├── validators.py        ← Field-level and post-generation integrity checks
├── logging_config.py    ← Centralised logging setup
└── generators/
    ├── __init__.py
    ├── programs.py      ← ProgramGenerator (20 distinct programmes)
    ├── terms.py         ← TermGenerator (SPRING/FALL semesters)
    ├── fee_data.py      ← FeeScheduleGenerator (schedules + lines)
    ├── students.py      ← StudentGenerator (10,000 students)
    ├── enrollments.py   ← EnrollmentGenerator (student ↔ program ↔ term)
    ├── phase2_data.py   ← Invoices, scholarships, payments, allocations, refunds
    └── generate_data.py ← CLI entry point & pipeline orchestrator
```

### Pipeline (dependency order)

```
1. Programs        ─── no dependencies
2. Terms           ─── no dependencies
3. FeeSchedules    ─── requires Programs + Terms
   └─ FeeScheduleLines
4. Students        ─── no dependencies
5. Enrollments     ─── requires Students + Programs + Terms + FeeSchedules
6. Invoices        ─── generated from Enrollments and FeeScheduleLines
7. Scholarships    ─── evaluates awards and applies invoice credits
8. Payments        ─── creates payments, allocations, and refunds
9. Supplementary   ─── fills full-mode targets on a fresh DB and generates
                       balance snapshots; then validates integrity
```

---

## 2. Configuration Options

All configuration lives in [`backend/config.py`](file:///backend/config.py).

### Generation Modes

| Parameter | Starter | Full |
|-----------|---------|------|
| `num_students` | 50 | 10,000 |
| `num_programs` | 20 | 20 |
| `num_terms` | 4 | 6 |
| `avg_terms_per_student` | 1.5 | 2.8 |
| `target_invoice_count` | — | 30,000 |
| `target_award_count` | — | 15,000 |
| `target_payment_count` | — | 50,000 |

> Both modes use **exactly the same 20 programmes** and the **same generation logic** — only scale differs.

### Fixed Seed

```python
DEFAULT_SEED = 20261022
```

The seed is passed to `SeededRandom` which wraps Python's `random.Random`. The same seed always produces identical data.

### Fee Component Templates

Defined in `FEE_COMPONENTS` dict, keyed by programme level (`UG`, `PG`, `PhD`, `Diploma`, `Certificate`). Each entry specifies:
- `fee_type` — category name
- `description` — human-readable description
- `base_inr_min`, `base_inr_max` — amount range in INR
- `is_mandatory` — whether all students pay this fee

---

## 3. ID Conventions

All IDs are **deterministic** (same seed → same IDs) and **sequential** (no UUIDs, no timestamps).

| Entity | Format | Example |
|--------|--------|---------|
| Student | `STU-{n:06d}` | `STU-000001` |
| Program | `PROG-{idx:02d}-{slug}` | `PROG-01-BTECH-CSE` |
| Term | `TERM-{year}-{season}` | `TERM-2024-SPRING` |
| FeeSchedule | `FS-{program_code}-{term_code}` | `FS-PROG-01-BTECH-CSE-TERM-2024-SPRING` |
| Enrollment | `ENR-{n:08d}` | `ENR-00000001` |
| Invoice | `INV-{n:08d}` | `INV-00000001` |
| Payment | `PAY-{n:08d}` | `PAY-00000001` |
| Refund | `REF-{n:08d}` | `REF-00000001` |

---

## 4. Reproducibility Design

```
SeededRandom(seed=20261022)
│
├─ fork("programs")   → ProgramGenerator  RNG (independent stream)
├─ fork("terms")      → TermGenerator     RNG (independent stream)
├─ fork("fee_data")   → FeeScheduleGenerator RNG
├─ fork("students")   → StudentGenerator  RNG
└─ fork("enrollments")→ EnrollmentGenerator RNG
```

Each `fork()` creates a child `SeededRandom` with a hash-derived seed, so:
- Adding a new sub-generator does NOT shift any other sub-generator's output.
- Each sub-generator produces exactly the same sequence for the same parent seed.

---

## 5. Generation Commands

### Starter Mode (50 students — fast development/testing)

```bash
python -m backend.generators.generate_data --mode starter
```

### Full Mode (10,000 students — production scale)

```bash
python -m backend.generators.generate_data --mode full
```

### Force Reset (DESTRUCTIVE — wipes DB and regenerates)

```bash
python -m backend.generators.generate_data --mode full --reset
```

> ⚠️ `--reset` deletes and recreates the database file. All existing data is permanently lost. The script will **not** wipe the database unless `--reset` is explicitly passed.

### Custom Seed or DB Path

```bash
python -m backend.generators.generate_data --mode full --seed 12345 --db /path/to/custom.db
```

### All CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--mode` | `full` | `starter` or `full` |
| `--seed` | `20261022` | Random seed for reproducibility |
| `--db` | `backend/database/student_finance.db` | SQLite database path |
| `--reset` | `False` | Destructive reset before generation |

---

## 6. Expected Row Counts

### Starter Mode (seed = 20261022)

| Entity | Expected |
|--------|----------|
| Programs | 20 |
| Terms | 4 |
| FeeSchedules | 80 (20 programs × 4 terms) |
| FeeScheduleLines | ~452 |
| Students | 50 |
| Enrollments | ~75–90 (depends on avg_terms) |

### Full Mode (seed = 20261022)

| Entity | Expected |
|--------|----------|
| Programs | 20 |
| Terms | 6 |
| FeeSchedules | 120 (20 programs × 6 terms) |
| FeeScheduleLines | ~678 |
| Students | 10,000 |
| Enrollments | Seeded; supports the 15,000 eligible award target |
| Invoices | 30,000 |
| Eligibility awards | 15,000 |
| Payments | 50,000 |

For a fresh full-mode database, generation validates these three required
financial volumes and raises an error with the actual counts if a target was
not reached. It does not delete or reduce records in a non-empty database.

---

## 7. Safe Rerun Behaviour

All insert operations use `INSERT OR IGNORE` or explicit existence checks, so:
- Running the generator twice without `--reset` inserts **0 new rows** on the second run.
- This is verified by `tests/test_generation.py::TestSafeRerun`.

---

## 8. Rollback Guarantee

- Programs, terms, and fee schedules are each committed in separate connections.
- Students and enrollments use batch inserts with rollback on failure.
- If any error occurs during generation, the affected connection's changes are rolled back.
- A partial dataset (e.g., students without enrollments) can occur if later steps fail, but earlier committed steps are preserved. Use `--reset` to start clean.

---

## 9. Data Quality

### Student Data
- Names from pools of 130+ Indian first names and 100+ Indian last names.
- Emails guaranteed unique via `{first}.{last}.{seq}@institution.edu`.
- Phone numbers follow Indian mobile format: `+91[6-9]XXXXXXXXX`.
- Date of birth: age 17–30 at the reference date.
- Addresses use 20 real Indian cities with correct state and pincode prefix.

### Fee Data
- Fee amounts are seeded from the RNG, rounded to the nearest ₹500.
- All amounts stored as **integer paise** (₹1 = 100 paise).
- Fees originate from the FEE_COMPONENTS catalogue per programme level.
- Students do not have individually assigned random fees — fees flow from FeeSchedules.

### Enrollment Data
- Enrollments read live DB student/program/term IDs — no orphaned FKs possible.
- The UNIQUE (student_id, program_id, term_id) constraint prevents duplicates.
- `year_of_study` increments per consecutive term enrollment.
- `fee_schedule_id` is looked up from FeeSchedules for the (program, term) pair.

---

## 10. Known Limitations

| Limitation | Notes |
|-----------|-------|
| Enrollment count is approximate | Depends on random term selection per student |
| Program switch rate is 5% | Some students may appear in 2 programs |
| Starter enrollment count varies slightly | Due to RNG state at enrollment phase |
| Windows file-lock on reset | Initialization now closes its SQLite handle explicitly; callers must still close active connections before resetting a database. |

---

## 11. Running Tests

```bash
# Phase 1 generation tests only:
python -m pytest tests/test_generation.py -v

# Part 1 database tests only:
python -m pytest tests/test_database.py -v

# All tests together:
python -m pytest tests/ -v
```

Full-scale repeatability across separate processes, including the seed
`20261022`, was verified by comparing all non-timestamp row values in two
independently generated full databases. See
[`reproducibility_report.md`](./reproducibility_report.md). Runtime timestamps
are expected to vary.

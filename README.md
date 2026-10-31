# Student Finance Management

> **YottaFlex AI Recruitment Challenge**  
> A production-grade Student Finance Management system built with Python and SQLite.

---

## Project Overview

This application manages the complete financial lifecycle of students at an academic institution — from enrollment and fee scheduling through invoicing, payments, scholarship eligibility, and refunds.

The project is built in five phases:

| Phase | Description | Status |
|-------|-------------|--------|
| **Part 1** | Database Foundation | ✅ Complete |
| **Part 2** | Backend & Data Generation | ✅ Complete |
| Part 3 | Business Logic & API Layer | 🔜 Upcoming |
| Part 4 | Frontend & Dashboard | 🔜 Upcoming |
| Part 5 | Anomaly Detection & Validation | 🔜 Upcoming |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Database | SQLite 3 |
| DB Library | `sqlite3` (stdlib) |
| Testing | `pytest` 9.x |
| Data Generation | Pure Python (deterministic) |

---

## Project Structure

```
Student Finance Management/
├── backend/
│   ├── __init__.py
│   ├── config.py            ← Generation modes, seed, fee templates, statuses
│   ├── id_generator.py      ← Deterministic sequential ID generation
│   ├── seed_manager.py      ← Reproducible RNG with fork() for sub-generators
│   ├── validators.py        ← Field-level and post-generation integrity checks
│   ├── logging_config.py    ← Centralised logging
│   ├── database/
│   │   ├── __init__.py
│   │   ├── schema.sql       ← Full DDL: 14 tables, constraints, indexes
│   │   ├── db_manager.py    ← Connection management, FK checks, transaction helpers
│   │   ├── models.py        ← Python dataclasses for all 14 tables
│   │   └── student_finance.db   ← SQLite database (git-ignored)
│   └── generators/
│       ├── __init__.py
│       ├── programs.py      ← 20 distinct academic programmes (static catalogue)
│       ├── terms.py         ← Academic terms (SPRING/FALL semesters)
│       ├── fee_data.py      ← Fee schedules and fee schedule lines
│       ├── students.py      ← Student records with Indian synthetic data
│       ├── enrollments.py   ← Student ↔ program ↔ term enrollments
│       └── generate_data.py ← CLI entry point
│
├── docs/
│   ├── architecture.md      ← System architecture, ER diagrams, design decisions
│   ├── data_dictionary.md   ← Column-level documentation for all 14 tables
│   └── data_generation.md   ← Generator architecture, commands, row counts
│
├── tests/
│   ├── __init__.py
│   ├── test_database.py     ← Part 1: 64 database tests
│   └── test_generation.py   ← Part 2: 81 generation tests
│
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Prerequisites

```bash
python --version   # Python 3.11+ required
pip show pytest    # pytest must be installed
```

If pytest is missing:
```bash
pip install pytest
```

### 2. Initialize and Generate (Starter Mode — 50 students)

```bash
python -m backend.generators.generate_data --mode starter
```

### 3. Generate Full Dataset (10,000 students)

```bash
python -m backend.generators.generate_data --mode full
```

### 4. Force Regeneration from Scratch

```bash
python -m backend.generators.generate_data --mode full --reset
```

> ⚠️ `--reset` permanently deletes the database before regenerating.

### 5. Run All Tests

```bash
python -m pytest tests/ -v
```

---

## Database Schema

The database contains **14 tables** (11 core entities + 3 supporting):

### Core Entities
| Table | Description |
|-------|-------------|
| `Students` | Student identity registry |
| `Programs` | Academic programmes offered |
| `FeeSchedules` | Fee structures per programme+term |
| `Enrollments` | Student ↔ programme ↔ term links |
| `Invoices` | Billing documents |
| `InvoiceLines` | Individual charge/credit items |
| `Scholarships` | Scholarship catalogue |
| `Eligibility` | Student ↔ scholarship awards |
| `Payments` | Student payment transactions |
| `PaymentAllocations` | Payment ↔ invoice line allocations |
| `Refunds` | Refunds against payments |

### Supporting Tables
| Table | Description |
|-------|-------------|
| `Terms` | Academic periods (SPRING/FALL semesters) |
| `FeeScheduleLines` | Fee components within a schedule |
| `AuditEvents` | Immutable audit trail for all changes |

**Key design decisions:**
- All monetary values stored as **integer paise** (1 INR = 100 paise) — no floats.
- Outstanding balances are **derived** from InvoiceLines and PaymentAllocations — never stored.
- Foreign keys enforced via `PRAGMA foreign_keys = ON` per connection.
- `AuditEvents` has no FK constraints to entity tables — preserves history even if entities are deleted.

---

## Data Generation

### Fixed Seed
All generation uses seed `20261022` by default. The same seed always produces identical data.

### Modes

| Mode | Students | Programs | Terms | FeeSchedules |
|------|----------|----------|-------|-------------|
| `starter` | 50 | 20 | 4 | 80 |
| `full` | 10,000 | 20 | 6 | 120 |

### CLI Reference

```bash
python -m backend.generators.generate_data [OPTIONS]

Options:
  --mode    starter|full    Generation mode (default: full)
  --seed    INT             Random seed (default: 20261022)
  --db      PATH            Database path (default: backend/database/student_finance.db)
  --reset                   Destructive reset before generation
```

---

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| `test_database.py` (Part 1) | 64 | ✅ All passing |
| `test_generation.py` (Part 2) | 81 | ✅ All passing |
| **Total** | **145** | **✅ All passing** |

### Run Tests

```bash
# All tests:
python -m pytest tests/ -v

# Part 1 only (database schema):
python -m pytest tests/test_database.py -v

# Part 2 only (data generation):
python -m pytest tests/test_generation.py -v
```

---

## Git Branches

| Branch | Description |
|--------|-------------|
| `master` | Part 1 baseline (database foundation) |
| `phase-1-foundation` | Part 2: backend foundation + data generation *(current)* |

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/architecture.md`](docs/architecture.md) | System architecture, ER diagrams, design decisions |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | Column-level documentation for all 14 tables |
| [`docs/data_generation.md`](docs/data_generation.md) | Generator architecture, commands, expected counts |

---

## Financial Data Design

> **Outstanding balance is always derived — never stored.**

```sql
-- Invoice outstanding balance:
SELECT
    SUM(il.amount_paise) AS total,
    COALESCE(SUM(pa.allocated_amount_paise), 0) AS paid,
    SUM(il.amount_paise) - COALESCE(SUM(pa.allocated_amount_paise), 0) AS outstanding
FROM InvoiceLines il
LEFT JOIN PaymentAllocations pa ON pa.line_id = il.line_id
WHERE il.invoice_id = ?
```

All monetary amounts in the database are stored as `INTEGER` paise. To display in INR, divide by 100.

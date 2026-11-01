# Student Finance Management

> **YottaFlex AI Recruitment Challenge**  
> A production-grade Student Finance Management system built with Python, FastAPI, SQLite, and a Vanilla JS frontend.

---

## Project Overview

This application manages the complete financial lifecycle of students at an academic institution — from enrollment and fee scheduling through invoicing, payments, scholarship eligibility, refunds, anomaly detection, and reconciliation.

| Phase | Description | Status |
|-------|-------------|--------|
| **Part 1** | Database Foundation (15 tables, schema, models) | ✅ Complete |
| **Phase 1** | Backend Foundation + Master Data Generation | ✅ Complete |
| **Phase 2** | Financial Business Logic, API & Data Generation | ✅ Complete |
| **Phase 3** | Anomaly Detection, Reconciliation & Validation | ✅ Complete |
| **Frontend** | 10-Page Admin Dashboard | ✅ Complete |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Database | SQLite 3 |
| Backend Framework | FastAPI 0.121+ |
| Schema Validation | Pydantic 2.x |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Frontend Tooling | Vite 6 |
| Testing | `pytest` 9.x |
| Data Generation | Pure Python (deterministic, seed 20261022) |

---

## Project Structure

```
Student Finance Management/
├── backend/
│   ├── __init__.py
│   ├── config.py                ← Generation modes, seed, fee templates
│   ├── id_generator.py          ← Deterministic sequential ID generation
│   ├── seed_manager.py          ← Reproducible RNG with fork()
│   ├── validators.py            ← Field-level and integrity checks
│   ├── logging_config.py        ← Centralised logging
│   ├── database/
│   │   ├── schema.sql           ← Full DDL: 15 tables, constraints, indexes
│   │   ├── db_manager.py        ← Connection management, FK checks
│   │   ├── models.py            ← Python dataclasses for all 15 tables
│   │   └── student_finance.db   ← SQLite database (git-ignored)
│   ├── generators/
│   │   ├── programs.py          ← 20 academic programmes
│   │   ├── terms.py             ← Academic terms (SPRING/FALL)
│   │   ├── fee_data.py          ← Fee schedules and lines
│   │   ├── students.py          ← Student records (Indian synthetic data)
│   │   ├── enrollments.py       ← Student-programme-term enrolments
│   │   ├── phase2_data.py       ← Invoices, payments, scholarships, refunds
│   │   └── generate_data.py     ← CLI entry point
│   ├── services/
│   │   └── finance_service.py   ← Read-only queries, payment & balance services
│   ├── api/
│   │   ├── __init__.py          ← FastAPI app factory + router registration
│   │   ├── schemas.py           ← Pydantic v2 response models
│   │   └── routes/
│   │       ├── students.py      ← Student list, detail, enrolments
│   │       ├── invoices.py      ← Student invoices, invoice detail
│   │       ├── payments.py      ← Student payments, allocations, refunds
│   │       ├── scholarships.py  ← Scholarship catalogue, eligibility
│   │       ├── balance.py       ← Student financial summary
│   │       ├── dashboard.py     ← Aggregate dashboard metrics
│   │       ├── anomalies.py     ← Detect, inject, evaluate anomalies
│   │       ├── reconciliation.py← Financial reconciliation
│   │       ├── exports.py       ← CSV/JSON/SQL data exports
│   │       ├── fee_schedules.py ← Terms, fee schedules, fee lines
│   │       └── global_views.py  ← Global invoices, payments, refunds, search
│   ├── anomaly/
│   │   ├── detector.py          ← 5-check anomaly detector
│   │   ├── evaluator.py         ← Precision/Recall/F1 evaluator
│   │   └── injector.py          ← Controlled anomaly injection (5 types)
│   ├── reconciliation/
│   │   └── reconciler.py        ← Student×Term financial reconciliation
│   └── exports/
│       └── exporter.py          ← Multi-format data export
│
├── frontend/
│   ├── package.json             ← Vite 6 dependency
│   ├── vite.config.js           ← Dev proxy → FastAPI backend
│   ├── index.html               ← App shell with sidebar navigation
│   └── src/
│       ├── css/style.css        ← Responsive dashboard CSS
│       └── js/
│           ├── api.js           ← API client (all endpoints)
│           ├── utils.js         ← Formatting helpers (INR, dates, pagination)
│           ├── components.js    ← 9 page renderers + detail views
│           └── app.js           ← Hash router, sidebar, health check
│
├── docs/
│   ├── architecture.md          ← System architecture, ER diagrams
│   ├── data_dictionary.md       ← Column-level documentation (15 tables)
│   ├── data_generation.md       ← Generator architecture, row counts
│   ├── api_documentation.md     ← API endpoint reference
│   └── business_rules.md        ← Financial rules and constraints
│
├── tests/
│   ├── test_database.py         ← Schema, constraints, and integrity tests
│   ├── test_generation.py       ← Generator and determinism tests
│   ├── test_phase2.py           ← Financial service and API tests
│   ├── test_phase3.py           ← Anomaly and reconciliation tests
│   └── test_exports.py          ← Export formats, downloads, and manifests
│
├── .gitignore
└── README.md
```

---

## Quick Start

### 1. Prerequisites

```bash
python --version   # Python 3.11+ required
pip install fastapi uvicorn pydantic pytest
```

### 2. Generate the Database

```bash
# Starter mode (50 students — fast, for development):
python -m backend.generators.generate_data --mode starter

# Full dataset (10,000 students — production):
python -m backend.generators.generate_data --mode full
```

### 3. Start the Backend API

```bash
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

API docs available at: `http://127.0.0.1:8000/docs`

### 4. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend available at: `http://localhost:5173`

### 5. Run All Tests

```bash
python -m pytest tests/ -v
```

---

## Database Schema

**15 tables** — 11 core entities + 4 supporting:

### Core Entities
| Table | Description |
|-------|-------------|
| `Students` | Student identity registry (10,000 in full mode) |
| `Programs` | 20 academic programmes |
| `FeeSchedules` | Fee structures per programme+term |
| `Enrollments` | Student-programme-term links |
| `Invoices` | Billing documents |
| `InvoiceLines` | Individual charge/credit items |
| `Scholarships` | Scholarship catalogue (5 types) |
| `Eligibility` | Student scholarship awards |
| `Payments` | Student payment transactions |
| `PaymentAllocations` | Payment-to-invoice-line allocations |
| `Refunds` | Refunds against payments |

### Supporting Tables
| Table | Description |
|-------|-------------|
| `Terms` | Academic periods (SPRING/FALL semesters) |
| `FeeScheduleLines` | Fee components within a schedule |
| `BalanceSnapshots` | Reported student-term balances for ledger comparison |
| `AuditEvents` | Immutable audit trail |

**Key design decisions:**
- All monetary values stored as **integer paise** (1 INR = 100 paise) — no floats.
- Outstanding balances are **derived** from InvoiceLines and PaymentAllocations — never stored.
- Foreign keys enforced via `PRAGMA foreign_keys = ON` per connection.

---

## Frontend — 10-Page Dashboard

| Page | Description | API Endpoint |
|------|-------------|-------------|
| Dashboard | Aggregate metrics (counts, totals) | `GET /api/v1/dashboard/summary` |
| Students | Paginated list + search + detail view | `GET /api/v1/students`, `/students/search` |
| Programs | Programme catalogue | `GET /api/v1/programs` |
| Invoices | Global invoice list + detail with lines | `GET /api/v1/invoices` |
| Scholarships | Catalogue + student eligibility | `GET /api/v1/scholarships` |
| Payments | Global payments + allocation drill-down | `GET /api/v1/payments` |
| Refunds | Global refund list | `GET /api/v1/refunds` |
| Reconciliation | Student×Term financial reconciliation | `GET /api/v1/reconciliation` |
| Anomalies | Detect anomalies + evaluate P/R/F1 | `GET /api/v1/anomalies/detect` |
| Data Exports | Download CSV or JSON archives with ground truth | `GET /api/v1/export/{csv,json}/download` |

---

## Anomaly Detection

Five controlled anomaly types are injected and detected:

| Type | Description |
|------|-------------|
| `PAYMENT_ALLOC_EXCEEDS_PAYMENT` | Total allocated > payment amount |
| `SCHOLARSHIP_EXCEEDS_FEES` | Awarded scholarship > eligible fee total |
| `DUPLICATE_INVOICE` | Same student/enrollment/term, duplicate invoice |
| `REFUND_EXCEEDS_NET_PAID` | Refund > net refundable amount |
| `BALANCE_DISAGREES_LEDGER` | Stored snapshot != ledger calculation |

**Audited full-database evaluation** (the five intentional labels remain in the database):
- Precision: **1.0000**
- Recall: **1.0000**
- F1 Score: **1.0000**

---

## Data Generation

### Fixed Seed
All generation uses seed `20261022`. The same seed always produces identical data.
Fresh full-mode generation targets exactly 30,000 invoices, 15,000 valid
scholarship awards, and 50,000 payments; the generator fails explicitly if
these targets cannot be met. Existing non-empty databases are never truncated
to fit the targets.

### Modes

| Mode | Students | Programs | Terms | Enrollments | Invoices |
|------|----------|----------|-------|-------------|----------|
| `starter` | 50 | 20 | 4 | ~91 | ~91 |
| `full` | 10,000 | 20 | 6 | ~28,000 | 30,000 |

### CLI Reference

```bash
python -m backend.generators.generate_data [OPTIONS]

Options:
  --mode    starter|full    Generation mode (default: full)
  --seed    INT             Random seed (default: 20261022)
  --db      PATH            Database path
  --reset                   Destructive reset before generation
```

---

## Test Results

The test suite includes database, export, generation, business logic, and
anomaly/reconciliation tests. Current verified run: **233 passed, 2 skipped**
(235 collected).

---

## API Endpoints

| Group | Endpoints |
|-------|-----------|
| Health | `GET /health` |
| Dashboard | `GET /api/v1/dashboard/summary` |
| Students | `GET /api/v1/students`, `GET /api/v1/students/{id}`, `GET /api/v1/students/{id}/enrollments`, `GET /api/v1/students/search` |
| Programs | `GET /api/v1/programs`, `GET /api/v1/programs/{id}` |
| Fee Schedules | `GET /api/v1/terms`, `GET /api/v1/fee-schedules`, `GET /api/v1/fee-schedules/{id}/lines` |
| Invoices | `GET /api/v1/invoices`, `GET /api/v1/students/{id}/invoices`, `GET /api/v1/invoices/{id}` |
| Scholarships | `GET /api/v1/scholarships`, `GET /api/v1/students/{id}/scholarships` |
| Payments | `GET /api/v1/payments`, `GET /api/v1/students/{id}/payments`, `GET /api/v1/payments/{id}/allocations` |
| Refunds | `GET /api/v1/refunds`, `GET /api/v1/students/{id}/refunds` |
| Balance | `GET /api/v1/students/{id}/balance` |
| Reconciliation | `GET /api/v1/reconciliation` |
| Anomalies | `GET /api/v1/anomalies/detect`, `POST /api/v1/anomalies/inject`, `GET /api/v1/anomalies/evaluate` |
| Exports | `GET /api/v1/export/csv`, `GET /api/v1/export/json`, `GET /api/v1/export/csv/download`, `GET /api/v1/export/json/download` |

Full API docs: start the backend and visit `http://127.0.0.1:8000/docs`

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/architecture.md`](docs/architecture.md) | System architecture, ER diagrams, design decisions |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | Column-level documentation for all 15 tables |
| [`docs/data_generation.md`](docs/data_generation.md) | Generator architecture, commands, expected counts |
| [`docs/api_documentation.md`](docs/api_documentation.md) | API endpoint reference |
| [`docs/business_rules.md`](docs/business_rules.md) | Financial rules and constraints |
| [`docs/validation_summary.md`](docs/validation_summary.md) | Database, exports, finance, anomalies, API, and test evidence |
| [`docs/reproducibility_report.md`](docs/reproducibility_report.md) | Seed 20261022 reproducibility evidence and limits |
| [`exports/source_manifest.json`](exports/source_manifest.json) | Export file SHA-256 hashes and database row-count manifest |

`exports/source_manifest.json` records source table row counts and SHA-256
hashes for the canonical CSV/JSON/ground-truth/SQL export files. The frontend
download page returns ZIP archives containing the 15 tables plus the matching
`ground_truth.csv` or `ground_truth.json`.

---

## Financial Data Design

> **Outstanding balance is always derived — never stored.**

The finance service derives `net_payable` from fee lines minus scholarship
credits, then derives outstanding from cleared allocations and processed
refunds. It aggregates each ledger separately to avoid multiplying invoice
amounts when a line has multiple payment allocations. All monetary values are
stored as integer paise; divide by 100 only for INR display. See
[`docs/data_dictionary.md`](docs/data_dictionary.md#17-financial-calculation-rules).

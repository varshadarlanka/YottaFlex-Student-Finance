# Architecture — Student Finance Management

> **Phase:** Part 1 — Database Foundation  
> **Stack:** Python 3.11+, SQLite 3, `sqlite3` (stdlib), `pytest`

---

## 1. Overview

The Student Finance Management system is built in five phases. This document covers Phase 1: the database foundation that all subsequent phases depend on.

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase Dependency Stack                     │
├─────────────────────────────────────────────────────────────┤
│  Phase 5 — Validation & Anomaly Detection                   │
│  Phase 4 — Data Generation                                  │
│  Phase 3 — Frontend / Dashboard                             │
│  Phase 2 — Business Logic / API Layer                       │
│  ─────────────────────────────────────────────────────────  │
│  Phase 1 — Database Foundation  ◄ YOU ARE HERE              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Project Layout

```
Student Finance Management/
├── backend/
│   └── database/
│       ├── __init__.py          # Package; exports DatabaseManager + models
│       ├── schema.sql           # DDL: all tables, constraints, indexes
│       ├── db_manager.py        # Connection management, verification, guards
│       ├── models.py            # Python dataclasses mirroring every table
│       └── student_finance.db  # SQLite database file (created on init)
│
├── docs/
│   ├── data_dictionary.md       # Column-level documentation for every table
│   └── architecture.md          # This file
│
└── tests/
    └── test_database.py         # pytest test suite (uses tmp_path fixtures)
```

---

## 3. Database Architecture

### 3.1 Technology Choices

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | SQLite | Zero-configuration, file-based, cross-platform, no server needed |
| Library | `sqlite3` (stdlib) | No external dependencies; always available |
| Money storage | INTEGER paise | Avoids all floating-point rounding errors |
| FK enforcement | `PRAGMA foreign_keys = ON` per connection | SQLite default is OFF; enforced in `_raw_connection()` |
| Transactions | Manual `BEGIN` / `COMMIT` / `ROLLBACK` via context managers | Explicit control; no silent partial commits |

### 3.2 Entity-Relationship Diagram

```
Terms ─────────────────────────────────────────────────────────────────┐
 │                                                                       │
 ├──< FeeSchedules (program_id, term_id) >── Programs                  │
 │         │                                                             │
 │         └──< FeeScheduleLines                                         │
 │                    │ (fsl_id)                                         │
 │                    └────────────────────────────────┐                 │
 │                                                     │                 │
 └──< Enrollments (student_id, program_id, term_id) >── Students        │
           │                             │                               │
           └──< Invoices (term_id) ──────┘                              │
                    │                                                    │
                    └──< InvoiceLines (fsl_id?) ──< PaymentAllocations ─┘
                                                          │
                                                     Payments (student_id)
                                                          │
                                                     Refunds

Students ──< Eligibility >── Scholarships
AuditEvents (append-only; references all tables by name+id)
```

### 3.3 Financial Data Flow

```
1. Programme → FeeSchedule → FeeScheduleLines
   (defines what fees apply to a programme for a term)

2. Student → Enrollment (attaches to programme + term + fee schedule)

3. Enrollment → Invoice (billing document generated)
   Invoice → InvoiceLines (charges copied from FeeScheduleLines +
                            scholarship credit lines from Eligibility)

4. Student → Payment (money received)
   Payment → PaymentAllocations → InvoiceLines (money applied to charges)

5. Payment → Refunds (money returned)

6. All status changes → AuditEvents (immutable trail)
```

---

## 4. DatabaseManager

`backend/database/db_manager.py` provides the central access layer.

### 4.1 Responsibilities

| Method | Purpose |
|--------|---------|
| `__init__(db_path)` | Resolve DB path; default = `backend/database/student_finance.db` |
| `initialise()` | Create DB file, apply schema idempotently |
| `connection()` | Context manager yielding a FK-enabled connection |
| `transaction(conn)` | Savepoint-based nested transaction context manager |
| `verify_tables()` | Check all 14 expected tables exist |
| `verify_foreign_keys()` | Introspect FK definitions via `PRAGMA foreign_key_list` |
| `run_foreign_key_check()` | Execute `PRAGMA foreign_key_check`; return violations |
| `validate_allocation(conn, payment_id, line_id)` | Cross-student allocation guard |
| `get_table_names()` | Return current table list |
| `close()` | No-op (connections are per-request) |

### 4.2 Connection Contract

Every connection produced by `connection()`:
1. Has `PRAGMA foreign_keys = ON` enforced.
2. Uses `sqlite3.Row` as the row factory (dict-like access).
3. Auto-commits on clean exit; rolls back on exception.
4. Is closed after the `with` block exits (no persistent connection pool).

### 4.3 Cross-Student Allocation Guard

SQLite cannot enforce cross-table consistency in a `CHECK` constraint.
The `validate_allocation()` method must be called by every service that inserts into `PaymentAllocations`:

```python
manager.validate_allocation(conn, payment_id=p_id, line_id=l_id)
# Only insert if no DatabaseError is raised
conn.execute("INSERT INTO PaymentAllocations ...")
```

Internally it traces:
```
PaymentAllocations.payment_id → Payments.student_id
PaymentAllocations.line_id → InvoiceLines.invoice_id → Invoices.enrollment_id
                           → Enrollments.student_id
```
And raises `DatabaseError` if the two `student_id` values differ.

---

## 5. Models

`backend/database/models.py` contains Python `@dataclass` definitions for all 14 tables.

### Design Principles

- Field names **match column names exactly** — `dict(sqlite3.Row)` can be unpacked with `**row` to construct a model.
- Surrogate PKs default to `Optional[int] = None` (None before DB insert).
- All monetary fields are typed `int` (paise). No `float`.
- Statuses are typed `str` (not Enum) to stay database-agnostic.
- Models carry no ORM magic — they are plain data containers safe to serialise to JSON.

### Future Evolution

In Phase 2, service-layer classes will:
1. Accept raw `sqlite3.Row` results.
2. Construct model dataclasses.
3. Apply business rules.
4. Return models to API handlers or frontend layers.

---

## 6. Schema Design Decisions

### 6.1 Surrogate Keys
All tables use `INTEGER PRIMARY KEY AUTOINCREMENT` surrogate keys. Natural keys (student codes, invoice numbers) are enforced as UNIQUE but are not PKs to:
- Avoid cascading updates when natural keys change.
- Simplify FK references.

### 6.2 Monetary Storage
All money is stored as `INTEGER` paise:
```
₹100.50 → 10050 paise
```
- Prevents floating-point drift in summations.
- `SUM()` in SQLite returns integer when all inputs are integers.
- INR conversion: `paise / 100` (display only; never store the converted value).

### 6.3 Derived Balances
**Outstanding invoice balances are never stored as columns.** They are always calculated:
```sql
SELECT
    SUM(il.amount_paise) AS total,
    COALESCE(SUM(pa.allocated_amount_paise), 0) AS allocated,
    SUM(il.amount_paise) - COALESCE(SUM(pa.allocated_amount_paise), 0) AS outstanding
FROM InvoiceLines il
LEFT JOIN PaymentAllocations pa ON pa.line_id = il.line_id
WHERE il.invoice_id = ?
```
This prevents balance drift from partial updates or bugs.

### 6.4 Audit Trail
`AuditEvents` has **no foreign keys** to entity tables deliberately — if an entity were ever deleted, its audit history must survive. The `entity_type` + `entity_id` pair provides a soft reference.

### 6.5 FK Cascade Semantics
| Relationship | ON UPDATE | ON DELETE |
|-------------|-----------|-----------|
| Enrollment → Student | CASCADE | RESTRICT |
| Invoice → Enrollment | CASCADE | RESTRICT |
| InvoiceLine → Invoice | CASCADE | RESTRICT |
| PaymentAllocation → Payment | CASCADE | RESTRICT |
| PaymentAllocation → InvoiceLine | CASCADE | RESTRICT |
| Refund → Payment | CASCADE | RESTRICT |
| Eligibility → Student | CASCADE | RESTRICT |
| Enrollment.fee_schedule_id | CASCADE | SET NULL |
| InvoiceLine.fsl_id | CASCADE | SET NULL |

`RESTRICT` is used everywhere financial history could be lost. `SET NULL` is used for optional traceability links.

### 6.6 Anomaly Compatibility
The schema is designed to support Phase 5 anomaly detection:
- **Status constraints** catch invalid state transitions.
- **Monetary constraints** catch negative/zero values where forbidden.
- **Unique constraints** catch duplicate records.
- **FK constraints** catch orphaned records.
- Business-rule anomalies (over-allocation, stale invoice status, cross-term payment) can be represented as valid rows that pass DB constraints but fail service-level validation — which is exactly what anomaly detection validators will check.

---

## 7. How Future Phases Interact with the Database

### Phase 2 — Business Logic / API
```
API Layer → Service Classes → DatabaseManager.connection() → SQLite
```
- Service classes import `DatabaseManager` from `backend.database`.
- Each request opens a connection, performs operations, and closes it.
- `validate_allocation()` is called before every payment allocation insert.
- Audit events are written at the end of every state-changing operation.

### Phase 3 — Frontend / Dashboard
```
Frontend → HTTP → API Layer → Service Classes → DatabaseManager
```
- Balances are computed at query time, never cached as columns.
- Dashboard aggregations use `GROUP BY` queries against `Invoices` + `InvoiceLines` + `PaymentAllocations`.

### Phase 4 — Data Generation
```
DataGenerator → DatabaseManager.connection() → Batch INSERT
```
- Uses the same `DatabaseManager` so all constraints are enforced during generation.
- Inserts are wrapped in transactions for performance.
- `validate_allocation()` is called for every generated allocation.

### Phase 5 — Validation / Anomaly Detection
```
Validator → DatabaseManager.connection() → SELECT queries → Analysis
```
- Validators query derived balances and compare against expected ranges.
- Anomalies are injected at the service layer (valid DB rows with invalid business semantics).
- Detection logic reads `AuditEvents` to reconstruct historical state.

---

## 8. Initialisation

```bash
# From the project root:
python -c "
from backend.database.db_manager import DatabaseManager
m = DatabaseManager()
m.initialise()
found, missing = m.verify_tables()
print('Tables created:', found)
print('Missing:', missing)
violations = m.run_foreign_key_check()
print('FK violations:', violations)
"
```

## 9. Running Tests

```bash
# From the project root:
python -m pytest tests/test_database.py -v
```

Tests use `tmp_path` fixtures and never touch `student_finance.db`.

---

## 10. Known Limitations (Phase 1)

| Limitation | Mitigation in Later Phases |
|-----------|---------------------------|
| No connection pooling | Phase 2 can add a lightweight pool if needed |
| No WAL mode enabled | Can be added in `_raw_connection()` for better write concurrency |
| Cross-student guard is service-only, not DB constraint | Enforced in all service classes in Phase 2 |
| No full-text search on student names | Phase 3 can add FTS5 virtual table |
| No soft-delete pattern | Lifecycle statuses serve this purpose |
| Timestamps are TEXT, not SQLite `datetime` type | SQLite stores all datetimes as TEXT/INTEGER/REAL; TEXT ISO-8601 is the recommended approach |

-- =============================================================================
-- Student Finance Management — SQLite Schema
-- =============================================================================
-- Design principles:
--   • All monetary values stored as INTEGER paise (1 INR = 100 paise) to avoid
--     floating-point rounding errors.
--   • Foreign keys enforced via PRAGMA foreign_keys = ON (must be set per
--     connection — SQLite does not enable this by default).
--   • Lifecycle statuses are enforced with CHECK constraints.
--   • Audit trail is append-only (AuditEvents); financial history is never
--     silently overwritten.
--   • Negative monetary amounts are prohibited except where explicitly noted
--     (e.g., credit-note invoice lines may carry a negative amount).
--   • All tables use "CREATE TABLE IF NOT EXISTS" so the schema can be
--     re-applied without duplication.
--   • Timestamps use ISO-8601 TEXT (YYYY-MM-DDTHH:MM:SS) stored as TEXT.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 1. Terms
-- Purpose: Academic periods (e.g., "2024 Odd Semester", "2025 Annual").
--          Separates calendar concerns from fee and enrollment logic, making
--          it easy to add new terms without touching other tables.
-- Cardinality: one Term → many FeeSchedules, many Enrollments, many Invoices
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Terms (
    term_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    term_code      TEXT    NOT NULL UNIQUE,          -- e.g. "2024-SEM1"
    term_name      TEXT    NOT NULL,
    start_date     TEXT    NOT NULL,                 -- YYYY-MM-DD
    end_date       TEXT    NOT NULL,                 -- YYYY-MM-DD
    is_active      INTEGER NOT NULL DEFAULT 1        -- 1=active, 0=closed
        CHECK (is_active IN (0, 1)),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),

    CHECK (end_date > start_date)
);

CREATE INDEX IF NOT EXISTS idx_terms_code ON Terms(term_code);

-- ---------------------------------------------------------------------------
-- 2. Programs
-- Purpose: Academic programs offered by the institution (e.g., "B.Tech CSE").
-- Cardinality: one Program → many FeeSchedules, many Enrollments
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Programs (
    program_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    program_code   TEXT    NOT NULL UNIQUE,          -- e.g. "BTECH-CSE"
    program_name   TEXT    NOT NULL,
    department     TEXT,
    duration_years INTEGER NOT NULL
        CHECK (duration_years > 0),
    level          TEXT    NOT NULL                  -- "UG", "PG", "PhD", "Diploma"
        CHECK (level IN ('UG', 'PG', 'PhD', 'Diploma', 'Certificate')),
    is_active      INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_programs_code ON Programs(program_code);

-- ---------------------------------------------------------------------------
-- 3. Students
-- Purpose: Core student registry. Contains only identity/contact data.
--          Financial and academic data live in related tables.
-- Cardinality: one Student → many Enrollments, Payments, Eligibility records
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Students (
    student_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    student_code   TEXT    NOT NULL UNIQUE,          -- institutional ID, e.g. "STU-2024-001"
    first_name     TEXT    NOT NULL,
    last_name      TEXT    NOT NULL,
    date_of_birth  TEXT    NOT NULL,                 -- YYYY-MM-DD
    gender         TEXT
        CHECK (gender IN ('M', 'F', 'O', NULL)),
    email          TEXT    NOT NULL UNIQUE,
    phone          TEXT,
    address_line1  TEXT,
    address_line2  TEXT,
    city           TEXT,
    state          TEXT,
    pincode        TEXT,
    status         TEXT    NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'graduated', 'withdrawn', 'suspended')),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_students_code  ON Students(student_code);
CREATE INDEX IF NOT EXISTS idx_students_email ON Students(email);
CREATE INDEX IF NOT EXISTS idx_students_status ON Students(status);

-- ---------------------------------------------------------------------------
-- 4. FeeSchedules
-- Purpose: A versioned fee structure for a (Program, Term) pair.
--          Allows different fee structures per term and per program.
-- Cardinality: one FeeSchedule → many FeeScheduleLines
--              one Program + one Term → typically one active FeeSchedule
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS FeeSchedules (
    schedule_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id     INTEGER NOT NULL REFERENCES Programs(program_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    term_id        INTEGER NOT NULL REFERENCES Terms(term_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    schedule_name  TEXT    NOT NULL,
    effective_from TEXT    NOT NULL,                 -- YYYY-MM-DD
    effective_to   TEXT,                             -- NULL = open-ended
    status         TEXT    NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'superseded', 'archived')),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),

    -- Prevent two active schedules for same program+term
    UNIQUE (program_id, term_id, status)
        -- Note: SQLite unique ignores multiple NULLs, but status is NOT NULL,
        -- so this correctly blocks duplicate active rows.
);

CREATE INDEX IF NOT EXISTS idx_feeschedules_program  ON FeeSchedules(program_id);
CREATE INDEX IF NOT EXISTS idx_feeschedules_term     ON FeeSchedules(term_id);

-- ---------------------------------------------------------------------------
-- 5. FeeScheduleLines
-- Purpose: Individual fee components within a FeeSchedule
--          (e.g., "Tuition", "Lab Fee", "Library Fee").
-- Cardinality: one FeeSchedule → many FeeScheduleLines
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS FeeScheduleLines (
    fsl_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id    INTEGER NOT NULL REFERENCES FeeSchedules(schedule_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    fee_type       TEXT    NOT NULL,                 -- "Tuition", "Lab", "Library", etc.
    description    TEXT,
    amount_paise   INTEGER NOT NULL                  -- stored in paise; 1 INR = 100 paise
        CHECK (amount_paise >= 0),
    is_mandatory   INTEGER NOT NULL DEFAULT 1
        CHECK (is_mandatory IN (0, 1)),
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fsl_schedule ON FeeScheduleLines(schedule_id);

-- ---------------------------------------------------------------------------
-- 6. Enrollments
-- Purpose: Links a Student to a Program for a specific academic term.
--          Tracks enrollment lifecycle (active → graduated / withdrawn etc.).
-- Cardinality: one Student → many Enrollments (one per term typically)
--              one Program → many Enrollments
--              one Enrollment → many Invoices
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Enrollments (
    enrollment_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     INTEGER NOT NULL REFERENCES Students(student_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    program_id     INTEGER NOT NULL REFERENCES Programs(program_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    term_id        INTEGER NOT NULL REFERENCES Terms(term_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    enrollment_date TEXT   NOT NULL,                 -- YYYY-MM-DD
    status         TEXT    NOT NULL DEFAULT 'enrolled'
        CHECK (status IN ('enrolled', 'completed', 'withdrawn', 'suspended', 'deferred')),
    year_of_study  INTEGER NOT NULL DEFAULT 1
        CHECK (year_of_study >= 1),
    fee_schedule_id INTEGER REFERENCES FeeSchedules(schedule_id)
                       ON UPDATE CASCADE ON DELETE SET NULL,
    notes          TEXT,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),

    -- A student can only be enrolled once per program per term
    UNIQUE (student_id, program_id, term_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_student  ON Enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_program  ON Enrollments(program_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_term     ON Enrollments(term_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_status   ON Enrollments(status);

-- ---------------------------------------------------------------------------
-- 7. Invoices
-- Purpose: Billing documents generated per (Enrollment, Term).
--          Outstanding balance is DERIVED: sum(InvoiceLines.amount_paise)
--          minus sum of PaymentAllocations applied to those lines minus
--          scholarship credits. Never stored as a separate column.
-- Cardinality: one Enrollment → many Invoices (e.g., one per term)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Invoices (
    invoice_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT    NOT NULL UNIQUE,           -- human-readable, e.g. "INV-2024-00001"
    enrollment_id  INTEGER NOT NULL REFERENCES Enrollments(enrollment_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    term_id        INTEGER NOT NULL REFERENCES Terms(term_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    issue_date     TEXT    NOT NULL,                  -- YYYY-MM-DD
    due_date       TEXT    NOT NULL,                  -- YYYY-MM-DD
    status         TEXT    NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'issued', 'partially_paid', 'paid', 'overdue',
                          'cancelled', 'refunded')),
    notes          TEXT,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),

    CHECK (due_date >= issue_date)
);

CREATE INDEX IF NOT EXISTS idx_invoices_enrollment ON Invoices(enrollment_id);
CREATE INDEX IF NOT EXISTS idx_invoices_enrollment_term
    ON Invoices(enrollment_id, term_id);
CREATE INDEX IF NOT EXISTS idx_invoices_term       ON Invoices(term_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status     ON Invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_number     ON Invoices(invoice_number);

-- ---------------------------------------------------------------------------
-- 8. InvoiceLines
-- Purpose: Individual charge or credit items on an invoice.
--          Positive amount_paise = charge; negative = credit/discount line
--          (e.g., scholarship credit line).
-- Cardinality: one Invoice → many InvoiceLines
--              one InvoiceLine ← many PaymentAllocations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS InvoiceLines (
    line_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     INTEGER NOT NULL REFERENCES Invoices(invoice_id)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    fee_type       TEXT    NOT NULL,                 -- "Tuition", "Scholarship Credit", etc.
    description    TEXT,
    amount_paise   INTEGER NOT NULL,                 -- may be negative for credits
    is_scholarship_credit INTEGER NOT NULL DEFAULT 0
        CHECK (is_scholarship_credit IN (0, 1)),
    fsl_id         INTEGER REFERENCES FeeScheduleLines(fsl_id)
                       ON UPDATE CASCADE ON DELETE SET NULL,  -- traceability to fee schedule
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_invoice_lines_invoice ON InvoiceLines(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_lines_fsl     ON InvoiceLines(fsl_id);

-- ---------------------------------------------------------------------------
-- 9. Scholarships
-- Purpose: Scholarship/grant definitions (master catalogue).
-- Cardinality: one Scholarship → many Eligibility records (students)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Scholarships (
    scholarship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholarship_code TEXT  NOT NULL UNIQUE,          -- e.g. "MERIT-GOLD"
    scholarship_name TEXT  NOT NULL,
    description    TEXT,
    scholarship_type TEXT  NOT NULL                  -- "Merit", "Need-based", "Government", "Sports"
        CHECK (scholarship_type IN ('Merit', 'Need-based', 'Government', 'Sports',
                                    'Minority', 'Special', 'Other')),
    -- Maximum award is a cap; actual amount is in Eligibility.awarded_amount_paise
    max_amount_paise INTEGER
        CHECK (max_amount_paise IS NULL OR max_amount_paise >= 0),
    -- Percentage discount alternative to fixed amount
    percentage_discount REAL
        CHECK (percentage_discount IS NULL OR
               (percentage_discount >= 0 AND percentage_discount <= 100)),
    is_renewable   INTEGER NOT NULL DEFAULT 0
        CHECK (is_renewable IN (0, 1)),
    is_active      INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_scholarships_code ON Scholarships(scholarship_code);
CREATE INDEX IF NOT EXISTS idx_scholarships_type ON Scholarships(scholarship_type);

-- ---------------------------------------------------------------------------
-- 10. Eligibility
-- Purpose: Bridge table connecting Students and Scholarships.
--          Records the awarded amount for a specific student-scholarship-term.
-- Cardinality: one Student → many Eligibility rows
--              one Scholarship → many Eligibility rows
--              many-to-many between Students and Scholarships
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Eligibility (
    eligibility_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id       INTEGER NOT NULL REFERENCES Students(student_id)
                         ON UPDATE CASCADE ON DELETE RESTRICT,
    scholarship_id   INTEGER NOT NULL REFERENCES Scholarships(scholarship_id)
                         ON UPDATE CASCADE ON DELETE RESTRICT,
    term_id          INTEGER NOT NULL REFERENCES Terms(term_id)
                         ON UPDATE CASCADE ON DELETE RESTRICT,
    enrollment_id    INTEGER REFERENCES Enrollments(enrollment_id)
                         ON UPDATE CASCADE ON DELETE SET NULL,
    awarded_amount_paise INTEGER NOT NULL
        CHECK (awarded_amount_paise >= 0),
    status           TEXT    NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'disbursed', 'rejected', 'cancelled')),
    applied_date     TEXT    NOT NULL,               -- YYYY-MM-DD
    approved_date    TEXT,
    disbursed_date   TEXT,
    notes            TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),

    -- A student can only receive the same scholarship once per term
    UNIQUE (student_id, scholarship_id, term_id)
);

CREATE INDEX IF NOT EXISTS idx_eligibility_student    ON Eligibility(student_id);
CREATE INDEX IF NOT EXISTS idx_eligibility_scholarship ON Eligibility(scholarship_id);
CREATE INDEX IF NOT EXISTS idx_eligibility_term       ON Eligibility(term_id);
CREATE INDEX IF NOT EXISTS idx_eligibility_status     ON Eligibility(status);

-- ---------------------------------------------------------------------------
-- 11. Payments
-- Purpose: Records a payment transaction made by a student.
--          The payment belongs to a student (not an invoice) so it can be
--          allocated across multiple invoices or remain unallocated.
-- Cardinality: one Student → many Payments
--              one Payment → many PaymentAllocations, many Refunds
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Payments (
    payment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_reference TEXT   NOT NULL UNIQUE,        -- e.g. "PAY-2024-00001"
    student_id       INTEGER NOT NULL REFERENCES Students(student_id)
                         ON UPDATE CASCADE ON DELETE RESTRICT,
    payment_date     TEXT    NOT NULL,               -- YYYY-MM-DD
    amount_paise     INTEGER NOT NULL
        CHECK (amount_paise > 0),                    -- payments must be positive
    payment_method   TEXT    NOT NULL
        CHECK (payment_method IN ('Cash', 'UPI', 'NetBanking', 'ChequeDD',
                                  'CardDebit', 'CardCredit', 'NEFT', 'RTGS', 'Other')),
    transaction_id   TEXT,                           -- gateway/bank reference
    bank_name        TEXT,
    status           TEXT    NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'cleared', 'failed', 'reversed', 'refunded')),
    notes            TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_payments_student    ON Payments(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_status     ON Payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_date       ON Payments(payment_date);
CREATE INDEX IF NOT EXISTS idx_payments_reference  ON Payments(payment_reference);

-- ---------------------------------------------------------------------------
-- 12. PaymentAllocations
-- Purpose: Bridge table linking a Payment to specific InvoiceLines.
--          A single payment can be split across multiple invoice lines.
--          An invoice line can accumulate allocations from multiple payments.
--          Cross-student allocations are prevented at service level and through
--          the student_id consistency check documented in db_manager.py.
-- Cardinality: many-to-many between Payments and InvoiceLines
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PaymentAllocations (
    allocation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id      INTEGER NOT NULL REFERENCES Payments(payment_id)
                        ON UPDATE CASCADE ON DELETE RESTRICT,
    line_id         INTEGER NOT NULL REFERENCES InvoiceLines(line_id)
                        ON UPDATE CASCADE ON DELETE RESTRICT,
    allocated_amount_paise INTEGER NOT NULL
        CHECK (allocated_amount_paise > 0),          -- allocations must be positive
    allocated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),

    -- Prevent double-allocation of the same payment to the same invoice line
    UNIQUE (payment_id, line_id)
);

CREATE INDEX IF NOT EXISTS idx_allocations_payment ON PaymentAllocations(payment_id);
CREATE INDEX IF NOT EXISTS idx_allocations_line    ON PaymentAllocations(line_id);

-- ---------------------------------------------------------------------------
-- 13. Refunds
-- Purpose: Records refunds issued against a specific payment.
--          Partial refunds are supported (refund_amount_paise ≤ payment amount).
--          A payment can have multiple refunds (e.g., staged partial refunds).
-- Cardinality: one Payment → many Refunds
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Refunds (
    refund_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    refund_reference TEXT    NOT NULL UNIQUE,        -- e.g. "REF-2024-00001"
    payment_id       INTEGER NOT NULL REFERENCES Payments(payment_id)
                         ON UPDATE CASCADE ON DELETE RESTRICT,
    refund_date      TEXT    NOT NULL,               -- YYYY-MM-DD
    refund_amount_paise INTEGER NOT NULL
        CHECK (refund_amount_paise > 0),
    reason           TEXT    NOT NULL,
    refund_method    TEXT    NOT NULL
        CHECK (refund_method IN ('Cash', 'UPI', 'NetBanking', 'ChequeDD',
                                 'CardDebit', 'CardCredit', 'NEFT', 'RTGS', 'Other')),
    status           TEXT    NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processed', 'failed', 'cancelled')),
    processed_by     TEXT,                           -- staff user identifier
    notes            TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_refunds_payment   ON Refunds(payment_id);
CREATE INDEX IF NOT EXISTS idx_refunds_status    ON Refunds(status);
CREATE INDEX IF NOT EXISTS idx_refunds_reference ON Refunds(refund_reference);

-- ---------------------------------------------------------------------------
-- 14. AuditEvents
-- Purpose: Immutable, append-only audit trail for all financial and status
--          changes across the system. Rows are NEVER updated or deleted.
--          entity_type identifies which table changed; entity_id is its PK.
--          old_value and new_value store JSON snapshots of changed fields.
-- Cardinality: many AuditEvents per entity row; no FK to entity tables
--              (to preserve history even if the entity is somehow deleted).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS AuditEvents (
    audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type    TEXT    NOT NULL,                 -- "Student", "Invoice", "Payment", etc.
    entity_id      INTEGER NOT NULL,
    event_type     TEXT    NOT NULL,                 -- "CREATE", "STATUS_CHANGE", "UPDATE", etc.
    field_changed  TEXT,                             -- column name if single field changed
    old_value      TEXT,                             -- JSON or plain string
    new_value      TEXT,                             -- JSON or plain string
    performed_by   TEXT,                             -- user/system identifier
    performed_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    notes          TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_entity      ON AuditEvents(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_event_type  ON AuditEvents(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_performed_at ON AuditEvents(performed_at);

-- ---------------------------------------------------------------------------
-- 15. BalanceSnapshots
-- Purpose: Point-in-time snapshots of student outstanding balances.
--          Used for reconciliation: the reported_outstanding_paise is compared
--          against the live ledger calculation to detect discrepancies.
-- Cardinality: many snapshots per student-term pair (historical)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS BalanceSnapshots (
    snapshot_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id                 INTEGER NOT NULL REFERENCES Students(student_id)
                                   ON UPDATE CASCADE ON DELETE RESTRICT,
    term_id                    INTEGER NOT NULL REFERENCES Terms(term_id)
                                   ON UPDATE CASCADE ON DELETE RESTRICT,
    reported_outstanding_paise INTEGER NOT NULL,
    snapshot_date              TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_student ON BalanceSnapshots(student_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_term    ON BalanceSnapshots(term_id);

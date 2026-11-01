# Data Dictionary — Student Finance Management

> **Version:** 1.0  
> **Database:** SQLite (`backend/database/student_finance.db`)  
> **Monetary unit:** All amounts stored as **INTEGER paise** (1 INR = 100 paise)  
> **Timestamps:** All stored as ISO-8601 TEXT: `YYYY-MM-DDTHH:MM:SS`

---

## Table of Contents

1. [Terms](#1-terms)
2. [Programs](#2-programs)
3. [Students](#3-students)
4. [FeeSchedules](#4-feeschedules)
5. [FeeScheduleLines](#5-feeschedulelines)
6. [Enrollments](#6-enrollments)
7. [Invoices](#7-invoices)
8. [InvoiceLines](#8-invoicelines)
9. [Scholarships](#9-scholarships)
10. [Eligibility](#10-eligibility)
11. [Payments](#11-payments)
12. [PaymentAllocations](#12-paymentallocations)
13. [Refunds](#13-refunds)
14. [BalanceSnapshots](#14-balancesnapshots)
15. [AuditEvents](#15-auditevents)
16. [Relationship Summary](#16-relationship-summary)
17. [Financial Calculation Rules](#17-financial-calculation-rules)

---

## 1. Terms

**Purpose:** Academic periods (semesters, annual years, trimesters).  
**Cardinality:** One Term → many FeeSchedules, many Enrollments, many Invoices

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `term_id` | INTEGER | PK, AUTOINCREMENT | Surrogate key |
| `term_code` | TEXT | NOT NULL, UNIQUE | Institutional period code e.g. `"2024-SEM1"` |
| `term_name` | TEXT | NOT NULL | Human-readable name e.g. `"2024 Odd Semester"` |
| `start_date` | TEXT | NOT NULL | Period start: `YYYY-MM-DD` |
| `end_date` | TEXT | NOT NULL | Period end: `YYYY-MM-DD`; must be > `start_date` |
| `is_active` | INTEGER | NOT NULL, DEFAULT 1, CHECK IN (0,1) | 1 = active, 0 = closed |
| `created_at` | TEXT | NOT NULL, DEFAULT now | Record creation timestamp |

**Indexes:** `idx_terms_code` on `term_code`

---

## 2. Programs

**Purpose:** Academic programmes offered (e.g., B.Tech CSE, MBA Finance).  
**Cardinality:** One Program → many FeeSchedules, many Enrollments

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `program_id` | INTEGER | PK, AUTOINCREMENT | Surrogate key |
| `program_code` | TEXT | NOT NULL, UNIQUE | Institutional code e.g. `"BTECH-CSE"` |
| `program_name` | TEXT | NOT NULL | Full programme name |
| `department` | TEXT | NULL | Offering department |
| `duration_years` | INTEGER | NOT NULL, CHECK > 0 | Programme length in years |
| `level` | TEXT | NOT NULL, CHECK IN ('UG','PG','PhD','Diploma','Certificate') | Academic level |
| `is_active` | INTEGER | NOT NULL, DEFAULT 1, CHECK IN (0,1) | Active flag |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_programs_code`

---

## 3. Students

**Purpose:** Core student identity registry. Financial state is never stored here — it is derived from invoice and payment tables.  
**Cardinality:** One Student → many Enrollments, Payments, Eligibility records

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `student_id` | INTEGER | PK, AUTOINCREMENT | Surrogate key |
| `student_code` | TEXT | NOT NULL, UNIQUE | Institutional student ID e.g. `"STU-2024-001"` |
| `first_name` | TEXT | NOT NULL | |
| `last_name` | TEXT | NOT NULL | |
| `date_of_birth` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `gender` | TEXT | CHECK IN ('M','F','O', NULL) | Optional |
| `email` | TEXT | NOT NULL, UNIQUE | Contact email; used for login in later phases |
| `phone` | TEXT | NULL | |
| `address_line1` | TEXT | NULL | |
| `address_line2` | TEXT | NULL | |
| `city` | TEXT | NULL | |
| `state` | TEXT | NULL | |
| `pincode` | TEXT | NULL | |
| `status` | TEXT | NOT NULL, DEFAULT 'active', CHECK IN ('active','inactive','graduated','withdrawn','suspended') | Lifecycle status |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | Must be updated on any change |

**Indexes:** `idx_students_code`, `idx_students_email`, `idx_students_status`

---

## 4. FeeSchedules

**Purpose:** Versioned fee structure for a (Program, Term) pair.  
**Cardinality:** One Program + one Term → typically one active FeeSchedule; one FeeSchedule → many FeeScheduleLines

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `schedule_id` | INTEGER | PK, AUTOINCREMENT | |
| `program_id` | INTEGER | NOT NULL, FK → Programs(program_id) | |
| `term_id` | INTEGER | NOT NULL, FK → Terms(term_id) | |
| `schedule_name` | TEXT | NOT NULL | Human-readable name |
| `effective_from` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `effective_to` | TEXT | NULL | Open-ended if NULL |
| `status` | TEXT | NOT NULL, DEFAULT 'active', CHECK IN ('draft','active','superseded','archived') | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

**Unique constraint:** `(program_id, term_id, status)` — prevents two active schedules for the same programme/term  
**Indexes:** `idx_feeschedules_program`, `idx_feeschedules_term`  
**FK semantics:** ON UPDATE CASCADE, ON DELETE RESTRICT

---

## 5. FeeScheduleLines

**Purpose:** Individual fee components within a FeeSchedule (e.g., Tuition ₹20,000, Lab ₹5,000).  
**Cardinality:** One FeeSchedule → many FeeScheduleLines

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `fsl_id` | INTEGER | PK, AUTOINCREMENT | |
| `schedule_id` | INTEGER | NOT NULL, FK → FeeSchedules(schedule_id) | |
| `fee_type` | TEXT | NOT NULL | Category: `"Tuition"`, `"Lab"`, `"Library"`, etc. |
| `description` | TEXT | NULL | Additional detail |
| `amount_paise` | INTEGER | NOT NULL, CHECK ≥ 0 | Fee amount in paise; must be non-negative |
| `is_mandatory` | INTEGER | NOT NULL, DEFAULT 1, CHECK IN (0,1) | 1 = student must pay |
| `sort_order` | INTEGER | NOT NULL, DEFAULT 0 | Display ordering |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_fsl_schedule`

---

## 6. Enrollments

**Purpose:** Records a student's enrolment in a programme for a specific term.  
**Cardinality:** One Student → many Enrollments; One Program → many Enrollments  
**Unique constraint:** `(student_id, program_id, term_id)` — a student cannot be enrolled twice in the same programme/term

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `enrollment_id` | INTEGER | PK, AUTOINCREMENT | |
| `student_id` | INTEGER | NOT NULL, FK → Students(student_id) | |
| `program_id` | INTEGER | NOT NULL, FK → Programs(program_id) | |
| `term_id` | INTEGER | NOT NULL, FK → Terms(term_id) | |
| `enrollment_date` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `status` | TEXT | NOT NULL, DEFAULT 'enrolled', CHECK IN ('enrolled','completed','withdrawn','suspended','deferred') | |
| `year_of_study` | INTEGER | NOT NULL, DEFAULT 1, CHECK ≥ 1 | Current year within the programme |
| `fee_schedule_id` | INTEGER | NULL, FK → FeeSchedules(schedule_id) | Schedule applied; NULL if not yet assigned |
| `notes` | TEXT | NULL | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_enrollments_student`, `idx_enrollments_program`, `idx_enrollments_term`, `idx_enrollments_status`

---

## 7. Invoices

**Purpose:** Billing documents generated per (Enrollment, Term). Outstanding balance is **derived** from InvoiceLines and PaymentAllocations — never stored as a column.  
**Cardinality:** One Enrollment → many Invoices

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `invoice_id` | INTEGER | PK, AUTOINCREMENT | |
| `invoice_number` | TEXT | NOT NULL, UNIQUE | Human-readable reference e.g. `"INV-2024-00001"` |
| `enrollment_id` | INTEGER | NOT NULL, FK → Enrollments(enrollment_id) | |
| `term_id` | INTEGER | NOT NULL, FK → Terms(term_id) | |
| `issue_date` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `due_date` | TEXT | NOT NULL | `YYYY-MM-DD`; must be ≥ `issue_date` |
| `status` | TEXT | NOT NULL, DEFAULT 'draft', CHECK IN ('draft','issued','partially_paid','paid','overdue','cancelled','refunded') | |
| `notes` | TEXT | NULL | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_invoices_enrollment`, `idx_invoices_enrollment_term`
(composite lookup for an enrollment and term), `idx_invoices_term`,
`idx_invoices_status`, `idx_invoices_number`

---

## 8. InvoiceLines

**Purpose:** Individual charge or credit items on an invoice. Negative `amount_paise` is allowed for scholarship credit lines.  
**Cardinality:** One Invoice → many InvoiceLines; One InvoiceLine ← many PaymentAllocations

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `line_id` | INTEGER | PK, AUTOINCREMENT | |
| `invoice_id` | INTEGER | NOT NULL, FK → Invoices(invoice_id) | |
| `fee_type` | TEXT | NOT NULL | `"Tuition"`, `"Scholarship Credit"`, etc. |
| `description` | TEXT | NULL | |
| `amount_paise` | INTEGER | NOT NULL | Positive = charge; negative = credit (scholarship) |
| `is_scholarship_credit` | INTEGER | NOT NULL, DEFAULT 0, CHECK IN (0,1) | 1 = credit line; allows negative amounts |
| `fsl_id` | INTEGER | NULL, FK → FeeScheduleLines(fsl_id) | Traceability to fee schedule component |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_invoice_lines_invoice`, `idx_invoice_lines_fsl`

---

## 9. Scholarships

**Purpose:** Master catalogue of available scholarships and grants.  
**Cardinality:** One Scholarship → many Eligibility records (students)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `scholarship_id` | INTEGER | PK, AUTOINCREMENT | |
| `scholarship_code` | TEXT | NOT NULL, UNIQUE | Unique code e.g. `"MERIT-GOLD"` |
| `scholarship_name` | TEXT | NOT NULL | |
| `description` | TEXT | NULL | |
| `scholarship_type` | TEXT | NOT NULL, CHECK IN ('Merit','Need-based','Government','Sports','Minority','Special','Other') | |
| `max_amount_paise` | INTEGER | NULL, CHECK ≥ 0 | Upper cap; actual award is in Eligibility |
| `percentage_discount` | REAL | NULL, CHECK 0–100 | Alternative to fixed amount |
| `is_renewable` | INTEGER | NOT NULL, DEFAULT 0, CHECK IN (0,1) | Whether it renews each term |
| `is_active` | INTEGER | NOT NULL, DEFAULT 1, CHECK IN (0,1) | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_scholarships_code`, `idx_scholarships_type`

---

## 10. Eligibility

**Purpose:** Bridge table connecting Students and Scholarships for a given Term. Stores actual awarded amount.  
**Cardinality:** Many-to-many between Students and Scholarships; UNIQUE on `(student_id, scholarship_id, term_id)`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `eligibility_id` | INTEGER | PK, AUTOINCREMENT | |
| `student_id` | INTEGER | NOT NULL, FK → Students(student_id) | |
| `scholarship_id` | INTEGER | NOT NULL, FK → Scholarships(scholarship_id) | |
| `term_id` | INTEGER | NOT NULL, FK → Terms(term_id) | |
| `enrollment_id` | INTEGER | NULL, FK → Enrollments(enrollment_id) | Optional linkage to specific enrollment |
| `awarded_amount_paise` | INTEGER | NOT NULL, CHECK ≥ 0 | Actual award in paise |
| `status` | TEXT | NOT NULL, DEFAULT 'pending', CHECK IN ('pending','approved','disbursed','rejected','cancelled') | |
| `applied_date` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `approved_date` | TEXT | NULL | |
| `disbursed_date` | TEXT | NULL | |
| `notes` | TEXT | NULL | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_eligibility_student`, `idx_eligibility_scholarship`, `idx_eligibility_term`, `idx_eligibility_status`

---

## 11. Payments

**Purpose:** Records a payment transaction made by or on behalf of a student. Linked to a student (not an invoice) so one payment can be split across multiple invoices.  
**Cardinality:** One Student → many Payments; One Payment → many PaymentAllocations, many Refunds

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `payment_id` | INTEGER | PK, AUTOINCREMENT | |
| `payment_reference` | TEXT | NOT NULL, UNIQUE | e.g. `"PAY-2024-00001"` |
| `student_id` | INTEGER | NOT NULL, FK → Students(student_id) | Owning student |
| `payment_date` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `amount_paise` | INTEGER | NOT NULL, CHECK > 0 | Must be strictly positive |
| `payment_method` | TEXT | NOT NULL, CHECK IN ('Cash','UPI','NetBanking','ChequeDD','CardDebit','CardCredit','NEFT','RTGS','Other') | |
| `transaction_id` | TEXT | NULL | Gateway or bank reference |
| `bank_name` | TEXT | NULL | |
| `status` | TEXT | NOT NULL, DEFAULT 'pending', CHECK IN ('pending','cleared','failed','reversed','refunded') | |
| `notes` | TEXT | NULL | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

**Indexes:** `idx_payments_student`, `idx_payments_status`, `idx_payments_date`, `idx_payments_reference`

---

## 12. PaymentAllocations

**Purpose:** Many-to-many bridge between Payments and InvoiceLines. A payment can be split across lines; a line can receive allocations from multiple payments.  
**Cardinality:** Many Payments ↔ Many InvoiceLines  
**Unique constraint:** `(payment_id, line_id)` — a payment is applied to each line at most once

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `allocation_id` | INTEGER | PK, AUTOINCREMENT | |
| `payment_id` | INTEGER | NOT NULL, FK → Payments(payment_id) | |
| `line_id` | INTEGER | NOT NULL, FK → InvoiceLines(line_id) | |
| `allocated_amount_paise` | INTEGER | NOT NULL, CHECK > 0 | Portion allocated; must be positive |
| `allocated_at` | TEXT | NOT NULL, DEFAULT now | |

**Cross-student guard:** `DatabaseManager.validate_allocation()` must be called before every INSERT to ensure payment and invoice line belong to the same student.

**Indexes:** `idx_allocations_payment`, `idx_allocations_line`

---

## 13. Refunds

**Purpose:** Refunds issued against a specific payment. Partial refunds supported; multiple refunds per payment allowed.  
**Cardinality:** One Payment → many Refunds

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `refund_id` | INTEGER | PK, AUTOINCREMENT | |
| `refund_reference` | TEXT | NOT NULL, UNIQUE | e.g. `"REF-2024-00001"` |
| `payment_id` | INTEGER | NOT NULL, FK → Payments(payment_id) | |
| `refund_date` | TEXT | NOT NULL | `YYYY-MM-DD` |
| `refund_amount_paise` | INTEGER | NOT NULL, CHECK > 0 | Must be positive |
| `reason` | TEXT | NOT NULL | Reason for refund |
| `refund_method` | TEXT | NOT NULL, CHECK IN ('Cash','UPI','NetBanking','ChequeDD','CardDebit','CardCredit','NEFT','RTGS','Other') | |
| `status` | TEXT | NOT NULL, DEFAULT 'pending', CHECK IN ('pending','processed','failed','cancelled') | |
| `processed_by` | TEXT | NULL | Staff identifier |
| `notes` | TEXT | NULL | |
| `created_at` | TEXT | NOT NULL, DEFAULT now | |
| `updated_at` | TEXT | NOT NULL, DEFAULT now | |

**Service-level rule:** Sum of all refund_amount_paise for a payment must not exceed the payment's amount_paise.

**Indexes:** `idx_refunds_payment`, `idx_refunds_status`, `idx_refunds_reference`

---

## 14. BalanceSnapshots

**Purpose:** Point-in-time student-term balance values used to detect disagreement with the live ledger.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `snapshot_id` | INTEGER | PK, AUTOINCREMENT | |
| `student_id` | INTEGER | NOT NULL, FK → Students | Student whose balance was captured |
| `term_id` | INTEGER | NOT NULL, FK → Terms | Academic term |
| `reported_outstanding_paise` | INTEGER | NOT NULL | Reported balance in integer paise |
| `snapshot_date` | TEXT | NOT NULL, DEFAULT now | Capture timestamp |

**Indexes:** `idx_snapshots_student`, `idx_snapshots_term`

---

## 15. AuditEvents

**Purpose:** Immutable, append-only audit trail. Rows are NEVER updated or deleted. No FK to entity tables (to preserve history even if entities are deleted).  
**Cardinality:** Many AuditEvents per entity row across all tables

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `audit_id` | INTEGER | PK, AUTOINCREMENT | |
| `entity_type` | TEXT | NOT NULL | Which table: `"Student"`, `"Invoice"`, `"Payment"`, etc. |
| `entity_id` | INTEGER | NOT NULL | PK of the affected row |
| `event_type` | TEXT | NOT NULL | `"CREATE"`, `"STATUS_CHANGE"`, `"UPDATE"`, `"DELETE"`, etc. |
| `field_changed` | TEXT | NULL | Column name for single-field changes |
| `old_value` | TEXT | NULL | Previous value (JSON or plain string) |
| `new_value` | TEXT | NULL | New value (JSON or plain string) |
| `performed_by` | TEXT | NULL | User or system component that triggered the change |
| `performed_at` | TEXT | NOT NULL, DEFAULT now | Timestamp of the event |
| `notes` | TEXT | NULL | |

**Indexes:** `idx_audit_entity` on `(entity_type, entity_id)`, `idx_audit_event_type`, `idx_audit_performed_at`

---

## 16. Relationship Summary

```
Terms ──────────────────────────────────────────────────────────────┐
  │                                                                  │
  ├──< FeeSchedules >── Programs                                     │
  │        │                                                         │
  │        └──< FeeScheduleLines                                     │
  │                                                                  │
  └──< Enrollments >── Students ──< Payments                        │
           │                              │                          │
           └──< Invoices >──< InvoiceLines >──< PaymentAllocations ─┘
                               │                     │
                               │               (bridges to Payments)
                               └── [fsl_id → FeeScheduleLines]

Students ──< Eligibility >── Scholarships
Payments ──< Refunds
AuditEvents (polymorphic, no FK, references all tables)
```

### Cardinality Table

| From | To | Cardinality |
|------|----|-------------|
| Student | Enrollment | 1 → N |
| Program | Enrollment | 1 → N |
| Term | Enrollment | 1 → N |
| Enrollment | Invoice | 1 → N |
| Invoice | InvoiceLine | 1 → N |
| FeeSchedule | FeeScheduleLine | 1 → N |
| FeeScheduleLine | InvoiceLine | 1 → N (optional) |
| Student | Payment | 1 → N |
| Payment | PaymentAllocation | 1 → N |
| InvoiceLine | PaymentAllocation | 1 → N |
| Payment | Refund | 1 → N |
| Student | Eligibility | 1 → N |
| Scholarship | Eligibility | 1 → N |
| Student | BalanceSnapshot | 1 → N |
| Term | BalanceSnapshot | 1 → N |
| Student ↔ Scholarship | (via Eligibility) | N → M |
| Payment ↔ InvoiceLine | (via PaymentAllocations) | N → M |

---

## 17. Financial Calculation Rules

### Invoice Total
```
fee_charges = SUM(InvoiceLines.amount_paise)
              WHERE invoice_id = X AND is_scholarship_credit = 0
scholarship_credits = SUM(ABS(InvoiceLines.amount_paise))
                      WHERE invoice_id = X AND is_scholarship_credit = 1
net_payable = max(0, fee_charges - scholarship_credits)
```

### Allocated to Invoice
```
allocated = SUM(PaymentAllocations.allocated_amount_paise)
            for the invoice's lines and cleared payments
```

### Outstanding Balance
```
outstanding = max(0, net_payable - allocated + processed_refunds)
overpayment = max(0, allocated - processed_refunds - net_payable)
```
> **Never store the outstanding balance as a column.** Always derive it.

### Scholarship Credit
Scholarship awards are applied as negative InvoiceLines (`is_scholarship_credit = 1`).  
They reduce net payable and are reported separately from fee charges.

### Payment Unallocated Amount
```
unallocated = payment.amount_paise
            - SUM(PaymentAllocations.allocated_amount_paise WHERE payment_id = X)
```

### Total Refunded for a Payment
```
reported_refunds = SUM(Refunds.refund_amount_paise
                       WHERE payment_id = X AND status = 'processed')
reserved_refunds = SUM(Refunds.refund_amount_paise
                       WHERE payment_id = X AND status IN ('processed', 'pending'))
```
Balance reports count processed refunds. Refund validation reserves pending as
well as processed refunds, and requires their sum not to exceed the payment
amount (except for the labelled refund anomaly).

---

## Export Package Manifest

`exports/source_manifest.json` describes the canonical export package:

| Field | Description |
|-------|-------------|
| `seed` | Generation seed (`20261022` for the audited full dataset) |
| `database` | Source SQLite database filename |
| `table_count` | Number of exported source tables |
| `total_rows` | Sum of source rows across all listed tables |
| `tables[]` | Table name and database row count |
| `artifacts[]` | Root export filename, byte size, and SHA-256 digest |

The package includes CSV and JSON files for all 15 tables, separate
`ground_truth.csv` and `ground_truth.json` files, and `seed.sql`. API download
archives contain the 15 tables in one format plus the matching ground-truth
file. Ground-truth labels are sourced from persisted audit markers; download
does not inject or alter anomalies.

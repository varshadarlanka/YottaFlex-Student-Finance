# Business Rules — Student Finance Management

> **Phase:** 2 — Financial Business Logic
> **Branch:** `phase-2-business-logic`

---

## 1. Invoice Calculation Rules

### 1.1 Invoice Generation
- One invoice is generated per **active enrollment** (non-withdrawn, non-deferred).
- Withdrawn or deferred enrollments receive a `cancelled` invoice.
- Invoice number format: `INV-STU-{student_id:06d}-{year}-{seq:06d}`
- Issue date: 7–14 days before the term start date (deterministic offset from RNG).
- Initial status: `issued` for active enrollments.

### 1.2 Invoice Total
- **Invoice total is never stored.** It is always derived:
  ```
  total = SUM(InvoiceLines.amount_paise)
  ```
- Positive lines = fee charges; negative lines = scholarship credits.
- Net amount due = max(0, SUM(positive lines) − SUM(absolute value of negative lines))

### 1.3 Invoice Due Date
- Due date = issue date + `invoice_due_days` (policy default: 30 days).

### 1.4 Invoice Status Lifecycle
```
draft → issued → partially_paid → paid
                                ↘ overdue
cancelled (no cleared payments)
refunded (post-payment reversal)
```
Status is updated by `InvoiceService.refresh_status()` after each payment allocation.

### 1.5 Invoice Cancellation Rules
- An invoice can be cancelled only if **no cleared payment allocations** exist against it.
- Cancelled invoices are excluded from balance calculations.
- Once cancelled, the record is preserved (never deleted).

---

## 2. Scholarship Eligibility and Award Rules

### 2.1 Scholarship Catalogue (5 scholarships)

| Code | Name | Type | Max Award | Discount |
|------|------|------|-----------|----------|
| `MERIT-ACADEMIC` | Merit Academic Scholarship | Merit | ₹80,000 | 35% of tuition |
| `ACCESS-SUPPORT` | Access Support Grant | Need-based | ₹30,000 | 20% of tuition+dev |
| `GOV-WOMEN-STEM` | Government Women in STEM | Government | ₹55,000 | 30% of tuition+lab |
| `SPORTS-EXCELLENCE` | Sports Excellence Grant | Sports | ₹18,000 | 15% of sports+tuition+dev |
| `RESEARCH-GRANT` | Research Progress Grant | Special | ₹65,000 | 25% of research+library+tuition |

> All `max_amount` figures shown in INR. Stored as integer paise.

### 2.2 Eligibility Criteria

Each scholarship has filters applied in order:
1. **Program level** — e.g. MERIT-ACADEMIC only applies to UG/PG students.
2. **Department** — e.g. GOV-WOMEN-STEM only applies to Engineering/Computing.
3. **Gender** — GOV-WOMEN-STEM only applies to female students (gender=`F`).
4. **Age** — SPORTS-EXCELLENCE capped at age 25.
5. **Year of study** — MERIT-ACADEMIC: years 1–3.
6. **Academic score** — synthetic score derived deterministically from `(student_id * 37 + program_id * 13) % 101`. Merit requires ≥ 88; ACCESS-SUPPORT ≥ 52; GOV-WOMEN-STEM ≥ 60; RESEARCH-GRANT ≥ 55.
7. **Extracurricular score** — `(student_id * 53 + program_id * 7 + 11) % 101`. Sports requires ≥ 78.
8. **City type** — ACCESS-SUPPORT requires non-metro city (not Mumbai/Delhi/Bengaluru/etc.).
9. **Applicable fee types** — only fees matching the rule's `applicable_fee_types` count.

### 2.3 Award Calculation
```python
applicable_fee_total = SUM of fsl.amount_paise for applicable fee types
percentage_award     = applicable_fee_total × (percentage_discount / 100)
award                = min(percentage_award, max_amount_paise)
award                = max(0, min(award, applicable_fee_total))
```

**Guarantee: award ≤ eligible fee total (no overshoot).**

### 2.4 Scholarship Application to Invoice
- Each approved award creates a **negative InvoiceLine** (`is_scholarship_credit = 1`).
- Description: `Scholarship: {scholarship_name}`
- Amount: `-abs(awarded_amount_paise)`.

### 2.5 Uniqueness
- A student can receive the same scholarship only once per term (`UNIQUE(student_id, scholarship_id, term_id)`).

### 2.6 Scholarship Status Lifecycle
```
pending → approved → disbursed
pending → rejected
disbursed → cancelled (reversal)
```

---

## 3. Payment Allocation Rules

### 3.1 Recording Payments
- Payments are recorded against the **student** (not an invoice).
- Supported methods: Cash, UPI, NetBanking, ChequeDD, CardDebit, CardCredit, NEFT, RTGS, Other.

### 3.2 Payment Status
```
pending → cleared (successful)
pending → failed
cleared → reversed (manual reversal)
cleared → refunded (after refund processed)
```
**Only `cleared` payments may be allocated to invoice lines.**

### 3.3 Allocation Constraints
Before every `PaymentAllocations` INSERT, the service validates:
1. **Same student**: `Payments.student_id` must equal `Enrollments.student_id` via `InvoiceLines → Invoices → Enrollments`.
2. **Payment not over-allocated**: `SUM(allocated) ≤ payment.amount_paise`.
3. **Line not over-paid**: `SUM(allocated on line) ≤ InvoiceLine.amount_paise`.
4. **Payment is cleared**: status must be `cleared`.
5. **No duplicate allocation**: one payment cannot be allocated to the same line twice.

### 3.4 Payment Strategy (Synthetic Data)
| Scenario | Probability |
|----------|-------------|
| Full payment (net_due) | 70% |
| Partial payment (30–80% of net_due) | 20% |
| No payment | 10% |
| Failed/pending (of all attempts) | 5% |

---

## 4. Refund Rules

- Refunds reference a specific payment (not an invoice directly).
- `refund_amount_paise ≤ (payment.amount_paise − already_refunded)`.
- Partial refunds are allowed; multiple refunds per payment allowed.
- Once a refund is `processed`, it reduces the student's `total_paid` in balance calculations.
- Refund history is never deleted.

---

## 5. Balance Formula

```
total_invoiced      = SUM(InvoiceLines.amount_paise WHERE amount_paise > 0
                          AND invoice.status NOT IN ('cancelled'))
scholarship_credits = SUM(ABS(InvoiceLines.amount_paise) WHERE is_scholarship_credit = 1
                          AND invoice.status NOT IN ('cancelled'))
net_payable         = MAX(0, total_invoiced - scholarship_credits)
total_paid          = SUM(PaymentAllocations.allocated_amount_paise
                          WHERE Payment.status = 'cleared'
                          AND invoice.status NOT IN ('cancelled'))
total_refunded      = SUM(Refunds.refund_amount_paise WHERE Refunds.status = 'processed')
outstanding         = MAX(0, net_payable - total_paid + total_refunded)
overpayment         = MAX(0, total_paid - total_refunded - net_payable)
overdue             = SUM of outstanding amounts on invoices with status = 'overdue'
```

**Rules:**
- `outstanding` and `overpayment` are mutually exclusive (both cannot be > 0 simultaneously).
- Failed, pending, and reversed payments are **excluded** from `total_paid`.
- Cancelled invoices are **excluded** from all balance calculations.
- Balance is **always derived on demand** — never stored in any column.

---

## 6. Late Fee Assumptions

Late fees are **disabled** in the current implementation.

```python
FinancePolicy.late_fee_enabled = False
FinancePolicy.late_fee_rate_bps = 0
FinancePolicy.late_fee_grace_days = 0
```

Overdue invoices are identified by comparing `due_date` to the reference date. No additional late fee charge is currently applied. This can be enabled in a future phase via `FinancePolicy`.

---

## 7. Lifecycle Transitions

### Invoice
| Event | Action |
|-------|--------|
| Enrollment created | Invoice generated with status `issued` |
| Enrollment withdrawn | Invoice status set to `cancelled` |
| Payment allocated | `refresh_status()` called → possibly `partially_paid` or `paid` |
| Past due date, unpaid | Status → `overdue` (on next refresh) |
| Manual cancel (no payments) | Status → `cancelled` |

### Payment
| Event | Action |
|-------|--------|
| Payment received | Record with status `cleared` / `pending` / `failed` |
| Bank bounce | Status changed to `failed` |
| Manual reversal (no allocations) | Status → `reversed` |
| Refund issued | Status → `refunded` (optional; refund status tracks separately) |

### Scholarship
| Event | Action |
|-------|--------|
| Eligibility evaluated | Record inserted with `disbursed` status |
| Manual cancellation | Status → `cancelled` |

---

## 8. Known Limitations

| Limitation | Notes |
|-----------|-------|
| No real-time due-date checking | Invoice statuses refreshed only during generation |
| No instalment plans | Each invoice expects one or more lump-sum payments |
| Late fees not implemented | `late_fee_enabled = False` in policy |
| Score-based eligibility is synthetic | Academic scores derived deterministically from IDs |
| Scholarship not linked to any official score record | By design for Phase 2; Phase 3 may add a StudentProfile table |
| Refund does not automatically update invoice status | Invoice status reflects payment state; refund changes balance only |

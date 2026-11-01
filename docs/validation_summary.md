# YottaFlex Project Validation Summary

**Audit date:** 2026-11-01  
**Database:** `backend/database/student_finance.db`  
**Generation seed:** `20261022`

## Database and export counts

The existing demo database was preserved. Its 15 tables contain 505,231 rows.
The API count endpoint and both local export formats were compared table by
table with SQLite; every count matched.

| Entity | Database | CSV | JSON | API | Status |
|---|---:|---:|---:|---:|---|
| Students | 10,000 | 10,000 | 10,000 | 10,000 | Match |
| Programs | 20 | 20 | 20 | 20 | Match |
| Terms | 6 | 6 | 6 | 6 | Match |
| FeeSchedules | 120 | 120 | 120 | 120 | Match |
| FeeScheduleLines | 678 | 678 | 678 | 678 | Match |
| Enrollments | 18,920 | 18,920 | 18,920 | 18,920 | Match |
| Invoices | 33,937 | 33,937 | 33,937 | 33,937 | Match |
| InvoiceLines | 136,968 | 136,968 | 136,968 | 136,968 | Match |
| Scholarships | 5 | 5 | 5 | 5 | Match |
| Eligibility | 14,732 | 14,732 | 14,732 | 14,732 | Match |
| Payments | 51,963 | 51,963 | 51,963 | 51,963 | Match |
| PaymentAllocations | 112,211 | 112,211 | 112,211 | 112,211 | Match |
| Refunds | 704 | 704 | 704 | 704 | Match |
| BalanceSnapshots | 1,553 | 1,553 | 1,553 | 1,553 | Match |
| AuditEvents | 123,414 | 123,414 | 123,414 | 123,414 | Match |
| **Total** | **505,231** | **505,231** | **505,231** | **505,231** | **Match** |

The CSV and JSON directories each contain exactly 15 files in their intended
format. Thirty redundant, byte-identical wrong-extension copies were removed
from those directories; canonical root exports were preserved. All 15 CSV and
15 JSON exports were parsed and counted against SQLite. The separate
`ground_truth.csv` and `ground_truth.json` each contain five persisted labels,
one for every required anomaly type.

The source manifest records the 15 tables and 33 root artifacts; its recorded
counts and hashes were verified. Importing `seed.sql` into a temporary database
recreated all 15 tables and 505,231 rows; SQLite integrity was `ok` and there
were no FK violations. Both download endpoints returned HTTP 200 ZIP
attachments: CSV archive 5,863,399 bytes and JSON archive 7,333,700 bytes.
Each archive contains 15 table files and the matching ground-truth file.

## Fresh full-mode generation and reproducibility

Two independent empty databases were generated with seed `20261022` and
`PYTHONHASHSEED=random`. Both contained 562,051 rows and met the fresh-database
targets exactly: 10,000 Students, 30,000 Invoices, 15,000 Eligibility awards,
and 50,000 Payments. All 15 non-timestamp table checksums matched; both passed
SQLite integrity and foreign-key checks. Per-table checksums are recorded in
[`reproducibility_report.md`](./reproducibility_report.md). Generation targets
are only enforced on an empty database, avoiding quota-driven additions to
existing data.

## Integrity and financial validation

- Production/demo SQLite integrity: `ok`; foreign-key check: zero violations.
- Duplicate invoice numbers, duplicate eligibility natural keys, duplicate
  payment/line allocation pairs, cross-student allocations, and non-positive
  payments/refunds/allocations: zero.
- Dashboard totals from the API: invoiced ₹3,078,725,766.43, paid
  ₹2,634,419,160.82, refunded ₹25,494,707.00, outstanding ₹117,161,302.29.
- Reconciliation covered 60,000 student-term records: 59,999 reconciled, with
  one intentionally injected snapshot mismatch; per-account totals agree with
  the dashboard.
- One intentional labelled payment-allocation anomaly exceeds payment by 2,500
  paise; one intentional labelled refund anomaly exceeds net paid by 2,500
  paise.
- 5,346 historical late-fee invoice lines total 5,652,275,819 paise. New
  generation has late fees disabled; allocated historical lines were retained.
- 2,381 invoices exceed net payable by 11,246,055,132 paise in aggregate.
  Existing payments were preserved and are reported as account overpayments.

## Anomalies and evaluation

The last completed evaluation returned **5 TP, 0 FP, 0 FN**; precision, recall,
and F1 were each **1.0**. Each required type had one detection matching one
persisted label:

1. `PAYMENT_ALLOC_EXCEEDS_PAYMENT`
2. `SCHOLARSHIP_EXCEEDS_FEES`
3. `DUPLICATE_INVOICE`
4. `REFUND_EXCEEDS_NET_PAID`
5. `BALANCE_DISAGREES_LEDGER`

Ground truth is stored separately from anomaly detection input. A repeat
evaluation returned the same **5 TP, 0 FP, 0 FN** with all metrics at **1.0**.
After adding the invoice `(enrollment_id, term_id)` lookup index, the API
evaluation took 1.54 seconds; the scholarship rule query fell from 126.43
seconds to 0.34 seconds.

## Frontend/API and tests

- The frontend production build passed with `npm run build` in `frontend/`.
- Dashboard, Students, Programs & Fees, Invoices, Scholarships, Payments,
  Refunds, Reconciliation, Anomaly Detection, and Exports routes rendered in
  the browser after the API fixes; no API failures were observed. Search,
  student detail, fee line detail, payment allocation detail, anomaly
  evaluation, and both export actions were exercised. Export API responses
  were independently opened and validated; the browser displayed successful
  “download started” status for CSV and JSON.
- Concurrent Programs & Fees API requests passed five rounds with HTTP 200.
  The root cause of intermittent 500 responses was SQLite connections created
  on one FastAPI worker thread and committed/closed on another. Connections
  now allow the FastAPI thread handoff, and schema initialization is performed
  at application startup rather than on every request.
- Complete Python test suite: **237 passed, 2 skipped**.
- Frontend production build: `npm run build` passed in `frontend/`.
- `git diff --check` passed; Git reported Windows line-ending conversion
  warnings only.

## Scope limitation

The original challenge prompt/checklist was not present in the workspace.
Repository documentation and the requirements provided in the conversation
were used as the available acceptance reference. Existing historical financial
exceptions were preserved rather than altered; manual business approval is
needed before changing them.

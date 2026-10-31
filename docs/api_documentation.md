# API Documentation — Student Finance Management

> **Version:** 2.0.0  
> **Base URL:** `http://localhost:8000/api/v1`  
> **Framework:** FastAPI 0.121.3 + Pydantic 2.x  
> **Authentication:** None (internal service)  
> **Format:** JSON  

---

## Starting the API

```bash
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload
```

Interactive docs: http://localhost:8000/docs  
ReDoc: http://localhost:8000/redoc

---

## Common Response Conventions

| Field naming | Description |
|-------------|-------------|
| `*_paise` | Integer paise value (authoritative) |
| `*_inr` | Float INR value (= paise / 100, for display) |
| Timestamps | ISO-8601 `YYYY-MM-DDTHH:MM:SS` |
| Pagination | All list endpoints return `{total, page, page_size, items}` |

---

## Health Check

### `GET /health`
```json
{"status": "ok", "service": "student-finance-management"}
```

---

## Students

### `GET /api/v1/students`
List students with optional status filter and pagination.

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (≥ 1) |
| `page_size` | int | 50 | Items per page (1–200) |
| `status` | str | — | Filter: `active`, `inactive`, `graduated`, `withdrawn`, `suspended` |

**Response 200:**
```json
{
  "total": 10000,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "student_id": 1,
      "student_code": "STU-000001",
      "first_name": "Arjun",
      "last_name": "Sharma",
      "date_of_birth": "2003-05-12",
      "gender": "M",
      "email": "arjun.sharma.1@institution.edu",
      "phone": "+919876543210",
      "city": "Bengaluru",
      "state": "Karnataka",
      "status": "active",
      "created_at": "2026-01-15T00:00:00"
    }
  ]
}
```

**Errors:** `422` — Invalid status value.

---

### `GET /api/v1/students/{student_id}`
Get full student details.

**Response 200:** Single `StudentOut` object.  
**Response 404:** `{"detail": "Student 9999 not found"}`

---

### `GET /api/v1/students/{student_id}/enrollments`
Get all enrollments for a student.

**Response 200:**
```json
[
  {
    "enrollment_id": 42,
    "student_id": 1,
    "program_id": 3,
    "term_id": 2,
    "enrollment_date": "2024-07-15",
    "status": "enrolled",
    "year_of_study": 1,
    "program_name": "B.Tech Computer Science",
    "program_code": "PROG-01-BTECH-CSE",
    "term_name": "2024 FALL",
    "term_code": "TERM-2024-FALL"
  }
]
```

---

## Programs

### `GET /api/v1/programs`
List all 20 academic programmes.

**Response 200:** Array of `ProgramOut` objects.

### `GET /api/v1/programs/{program_id}`
Get programme details.  
**Response 404:** Program not found.

---

## Invoices

### `GET /api/v1/students/{student_id}/invoices`
List all invoices for a student, newest first.

**Query:** `page`, `page_size` (1–100)

**Response 200:**
```json
{
  "total": 3,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "invoice_id": 101,
      "invoice_number": "INV-STU-000001-2024-000101",
      "enrollment_id": 42,
      "term_id": 2,
      "issue_date": "2024-07-01",
      "due_date": "2024-07-31",
      "status": "paid",
      "term_name": "2024 FALL"
    }
  ]
}
```

---

### `GET /api/v1/invoices/{invoice_id}`
Get invoice detail with all line items.

**Response 200:**
```json
{
  "invoice_id": 101,
  "invoice_number": "INV-STU-000001-2024-000101",
  "enrollment_id": 42,
  "term_id": 2,
  "issue_date": "2024-07-01",
  "due_date": "2024-07-31",
  "status": "paid",
  "total_paise": 1250000,
  "total_inr": 12500.0,
  "lines": [
    {
      "line_id": 301,
      "invoice_id": 101,
      "fee_type": "Tuition",
      "description": "Tuition fee",
      "amount_paise": 1200000,
      "amount_inr": 12000.0,
      "is_scholarship_credit": 0
    },
    {
      "line_id": 302,
      "invoice_id": 101,
      "fee_type": "Scholarship Credit",
      "description": "Scholarship: Merit Academic Scholarship",
      "amount_paise": -420000,
      "amount_inr": -4200.0,
      "is_scholarship_credit": 1
    }
  ]
}
```

**Response 404:** Invoice not found.

---

## Scholarships

### `GET /api/v1/scholarships`
List all scholarships in the master catalogue.

**Response 200:**
```json
[
  {
    "scholarship_id": 1,
    "scholarship_code": "MERIT-ACADEMIC",
    "scholarship_name": "Merit Academic Scholarship",
    "scholarship_type": "Merit",
    "max_amount_paise": 8000000,
    "max_amount_inr": 80000.0,
    "percentage_discount": 35.0,
    "is_renewable": 1,
    "is_active": 1
  }
]
```

---

### `GET /api/v1/students/{student_id}/scholarships`
Get scholarship eligibility records for a student.

**Response 200:**
```json
[
  {
    "eligibility_id": 15,
    "student_id": 1,
    "scholarship_id": 1,
    "term_id": 2,
    "awarded_amount_paise": 420000,
    "awarded_amount_inr": 4200.0,
    "status": "disbursed",
    "applied_date": "2024-07-15",
    "scholarship_name": "Merit Academic Scholarship",
    "scholarship_type": "Merit"
  }
]
```

---

## Payments

### `GET /api/v1/students/{student_id}/payments`
List all payment transactions for a student.

**Query:** `page`, `page_size`

**Response 200:**
```json
{
  "total": 5,
  "items": [
    {
      "payment_id": 200,
      "payment_reference": "PAY-00000200",
      "student_id": 1,
      "payment_date": "2024-07-18",
      "amount_paise": 830000,
      "amount_inr": 8300.0,
      "payment_method": "UPI",
      "status": "cleared"
    }
  ]
}
```

---

### `GET /api/v1/payments/{payment_id}/allocations`
Get all invoice-line allocations for a payment.

**Response 200:**
```json
[
  {
    "allocation_id": 401,
    "payment_id": 200,
    "line_id": 301,
    "allocated_amount_paise": 830000,
    "allocated_amount_inr": 8300.0,
    "allocated_at": "2026-10-31T12:20:12",
    "fee_type": "Tuition",
    "invoice_number": "INV-STU-000001-2024-000101"
  }
]
```

---

### `GET /api/v1/students/{student_id}/refunds`
List all refunds for a student's payments.

**Response 200:**
```json
[
  {
    "refund_id": 10,
    "refund_reference": "REF-00000010",
    "payment_id": 200,
    "refund_date": "2024-08-05",
    "refund_amount_paise": 100000,
    "refund_amount_inr": 1000.0,
    "reason": "Student request",
    "refund_method": "UPI",
    "status": "processed"
  }
]
```

---

## Balance / Financial Summary

### `GET /api/v1/students/{student_id}/balance`
Get complete financial position for a student.

**Query:** `term_id` (optional integer) — filter to a specific term.

**Response 200:**
```json
{
  "student_id": 1,
  "student_code": "STU-000001",
  "student_name": "Arjun Sharma",
  "term_id": null,
  "total_invoiced_paise": 1200000,
  "total_invoiced_inr": 12000.0,
  "scholarship_credits_paise": 420000,
  "scholarship_credits_inr": 4200.0,
  "net_payable_paise": 780000,
  "net_payable_inr": 7800.0,
  "total_paid_paise": 780000,
  "total_paid_inr": 7800.0,
  "total_refunded_paise": 0,
  "total_refunded_inr": 0.0,
  "outstanding_paise": 0,
  "outstanding_inr": 0.0,
  "overdue_paise": 0,
  "overdue_inr": 0.0,
  "overpayment_paise": 0,
  "overpayment_inr": 0.0
}
```

**Balance formula:**
```
net_payable  = total_invoiced − scholarship_credits
outstanding  = max(0, net_payable − total_paid + total_refunded)
overpayment  = max(0, total_paid − total_refunded − net_payable)
```

---

## HTTP Error Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `404` | Resource not found |
| `422` | Validation error (invalid query parameter) |
| `500` | Internal server error (DB failure, logged server-side) |

---

## Known Limitations

- No authentication or authorisation is implemented.
- List endpoints do not support sorting or free-text search.
- The database path is resolved from `DEFAULT_DB_PATH` in `backend/database/db_manager.py`. Override via the `deps.py` dependency.
- No rate limiting is implemented.
- No write endpoints (POST/PUT/PATCH) are exposed in Phase 2.

# AI Prompt History
## YottaFlex Student Finance Management System

**Project:** Student Finance Management System  
**Challenge:** YottaFlex 72-Hour Code Challenge  
**Technology Stack:** Python, FastAPI, SQLite, HTML, CSS, JavaScript  
**AI Tools Used:** ChatGPT, Claude Code, Antigravity

---

## 1. Purpose of AI Assistance

AI tools were used as development assistants throughout the project for:

- Understanding and breaking down the problem statement.
- Database schema design and relationship planning.
- Synthetic data generation strategy.
- Backend and frontend implementation guidance.
- Financial business logic and calculations.
- Anomaly detection and reconciliation.
- Debugging and error resolution.
- Test case development and validation.
- Code review and project auditing.
- Documentation and GitHub preparation.

The candidate reviewed the implementation, tested the application, and verified the major project workflows.

**Note:** The prompts below are reconstructed task descriptions based on the documented project workflow. They are not represented as exact verbatim historical transcripts where original prompt logs are unavailable.

---

# 2. ChatGPT Prompt History

### Prompt 1: Problem Statement Analysis

**Purpose:** Understand the complete YottaFlex challenge.

**Prompt:**

I have received a 72-hour recruitment challenge from YottaFlex. The requirement is to build a Student Finance Management System that calculates tuition fees, applies scholarship eligibility, processes payments, handles refunds, and reconciles student balances.

Analyze the complete problem statement. Explain all requirements, business workflows, entities, relationships, validation rules, anomaly scenarios, expected outputs, and acceptance criteria. Create a structured implementation plan covering the entire project.

### Prompt 2: Technology Stack and Project Architecture

**Purpose:** Plan the application architecture.

**Prompt:**

I want to build the Student Finance Management System using Python, FastAPI, SQLite, and a JavaScript frontend.

Suggest a clean project architecture with separate backend, frontend, database, services, API routes, tests, documentation, and exports directories. Ensure the architecture supports all challenge requirements and can run locally without paid services.

### Prompt 3: Relational Database Design

**Purpose:** Design the 11 required entities.

**Prompt:**

Design a relational SQLite database for the Student Finance Management System.

Include these 11 core entities:

1. Students
2. Programs
3. FeeSchedules
4. Enrollments
5. Invoices
6. InvoiceLines
7. Scholarships
8. Eligibility
9. Payments
10. PaymentAllocations
11. Refunds

Define primary keys, foreign keys, relationships, cardinality, required and optional fields, unique constraints, check constraints, indexes, lifecycle statuses, and effective dates.

Use integer paise for monetary values. Preserve financial transaction history and support anomaly detection.

Generate the SQL schema and explain the relationships.

### Prompt 4: Data Dictionary

**Purpose:** Document all database fields.

**Prompt:**

Create a detailed data dictionary for all 11 core entities in the Student Finance Management System.

For every field specify its name, data type, required or optional status, allowed values, units, uniqueness, default value, and validation rules.

Make sure the documentation matches the SQLite schema.

### Prompt 5: Synthetic Data Generation

**Purpose:** Generate deterministic test data.

**Prompt:**

Design a deterministic synthetic data generation process for the Student Finance Management System.

Generate:
- 10,000 students
- 20 programs
- 30,000 invoices
- 15,000 scholarship awards
- 50,000 payments

Use a fixed random seed of 20261022. Generate parent records before dependent records. Maintain consistent IDs and foreign-key relationships.

Include partial payments, overpayments, fee waivers, term withdrawals, and realistic financial variations.

Generate derived financial values from source records instead of assigning them independently.

### Prompt 6: Financial Business Logic

**Purpose:** Implement student financial calculations.

**Prompt:**

Help design the financial business logic for the Student Finance Management System.

Implement the calculations for:
- Program and term-based tuition fees.
- Invoice generation from eligible fee schedules.
- Scholarship eligibility and awards.
- Payment allocation to invoice lines.
- Student outstanding balances.
- Overpayments.
- Late fees.
- Refund processing.
- Enrollment cancellations and withdrawals.

Ensure that every financial calculation is traceable and historical transactions are preserved.

### Prompt 7: Anomaly Detection

**Purpose:** Implement the five required negative scenarios.

**Prompt:**

Design an anomaly detection module for the Student Finance Management System.

Detect these five required anomaly types:

1. Payment allocation exceeds payment amount.
2. Scholarship exceeds eligible fees.
3. Duplicate invoice generation.
4. Refund exceeds net paid amount.
5. Student balance differs from ledger.

Keep anomaly detection separate from normal financial business logic.

Use issue types and ground-truth labels. Avoid silently modifying unrelated records.

### Prompt 8: Financial Reconciliation

**Purpose:** Verify student balances.

**Prompt:**

Implement a financial reconciliation system that compares student financial balances against their transaction ledger.

Validate invoice amounts, scholarship credits, payment allocations, refunds, outstanding balances, and overpayments.

Identify mismatches and provide detailed explanations for every reconciliation failure. Preserve the original financial records.

### Prompt 9: Ground Truth and Evaluation

**Purpose:** Measure anomaly detection performance.

**Prompt:**

Create a ground-truth dataset for the five required anomaly scenarios.

Implement an evaluator that compares detected anomalies with the ground-truth labels.

Calculate:
- True Positives
- False Positives
- False Negatives
- Precision
- Recall
- F1 Score

Ensure ground-truth labels are not used as input features during anomaly detection.

### Prompt 10: API and Frontend Integration

**Purpose:** Connect the frontend to the backend.

**Prompt:**

Review the FastAPI backend and JavaScript frontend integration for the Student Finance Management System.

Verify that dashboard, students, programs, fee schedules, invoices, payments, scholarships, refunds, reconciliation, anomaly detection, and data export features use the correct API endpoints.

Check request parameters, response structures, pagination, search, filters, error handling, and frontend rendering.

### Prompt 11: Debugging and Error Resolution

**Purpose:** Resolve implementation issues.

**Prompt:**

Analyze the project errors and debug the relevant backend or frontend components.

Identify the root cause before making changes. Apply minimal targeted fixes. Do not modify unrelated modules or remove existing functionality.

After fixing an issue, verify the affected functionality and run the relevant tests.

### Prompt 12: Testing and Validation

**Purpose:** Validate project acceptance criteria.

**Prompt:**

Review the complete Student Finance Management System against the YottaFlex problem statement.

Verify:
- Primary-key uniqueness.
- Foreign-key integrity.
- Valid relationships.
- Financial arithmetic.
- Scholarship eligibility.
- Payment allocation.
- Refund calculations.
- Duplicate invoice detection.
- Reconciliation.
- All five anomaly scenarios.
- Ground-truth evaluation.
- CSV and JSON exports.
- Deterministic data generation.

Report passed checks, failed checks, and known limitations without inventing successful test results.

---

# 3. Claude Code Prompt History

### Prompt 1: Project Structure Review

**Purpose:** Inspect the existing project before implementation.

**Prompt:**

Inspect the Student Finance Management System project structure and understand the existing backend, frontend, database, tests, and documentation.

Identify missing components and implementation gaps against the YottaFlex problem statement.

Do not delete or overwrite existing working functionality. Provide a structured implementation plan.

### Prompt 2: Database Implementation

**Purpose:** Implement the SQLite database foundation.

**Prompt:**

Implement the database foundation using Python sqlite3.

Create:
- backend/database/schema.sql
- backend/database/db_manager.py
- backend/database/models.py
- docs/data_dictionary.md

Implement all 11 required entities with primary keys, foreign keys, constraints, indexes, and appropriate relationships.

Use integer paise for monetary values and preserve transaction history.

### Prompt 3: Backend Business Logic

**Purpose:** Implement financial services and APIs.

**Prompt:**

Implement the Student Finance Management System backend using FastAPI.

Create modular services for students, programs, fee schedules, enrollments, invoices, scholarships, payments, allocations, refunds, and reconciliation.

Expose the required API endpoints. Maintain separation between database access, business logic, and API routes.

Ensure that all financial calculations use the source transaction records.

### Prompt 4: Synthetic Data Generator

**Purpose:** Implement deterministic data generation.

**Prompt:**

Implement a configurable synthetic data generator for the Student Finance Management System.

Use seed 20261022 and generate parent entities before dependent records.

Maintain valid foreign-key references and deterministic IDs.

Generate the required baseline volumes and realistic transaction variations.

Ensure that derived financial values are calculated from source records.

### Prompt 5: Anomaly Detection and Evaluation

**Purpose:** Implement anomaly detection modules.

**Prompt:**

Implement anomaly detection using separate modules for injection, detection, and evaluation.

The five required anomaly types must be supported.

Maintain ground-truth labels independently from detection input. Calculate precision, recall, and F1 score.

Add tests for each anomaly type and ensure anomaly injection can run safely against a test database copy.

### Prompt 6: Reconciliation Engine

**Purpose:** Implement financial ledger reconciliation.

**Prompt:**

Implement a reconciliation engine that compares student balances with financial ledger transactions.

Verify invoices, scholarship credits, payment allocations, refunds, outstanding amounts, and overpayments.

Generate detailed mismatch reports and preserve the underlying transaction history.

### Prompt 7: Frontend Integration

**Purpose:** Complete the frontend functionality.

**Prompt:**

Review and implement the frontend pages for the Student Finance Management System.

Include dashboard, student management, programs and fees, invoices, payments, scholarships, refunds, reconciliation, anomaly detection, and data exports.

Connect each page to the correct FastAPI endpoint. Ensure search, pagination, filtering, detail views, and data display work correctly.

### Prompt 8: Code Review and Bug Fixing

**Purpose:** Inspect and fix project issues.

**Prompt:**

Perform a code review of the existing Student Finance Management System.

Identify backend errors, frontend issues, database inconsistencies, incorrect financial calculations, API integration problems, and missing validation.

Fix issues with minimal changes. Preserve the existing architecture and avoid unrelated modifications.

Run relevant tests after every important fix.

### Prompt 9: Complete Project Audit

**Purpose:** Verify final acceptance requirements.

**Prompt:**

Perform a complete acceptance audit of the YottaFlex Student Finance Management System.

Verify all five required anomaly scenarios, database integrity, financial reconciliation, payment and scholarship calculations, deterministic generation, export functionality, frontend build, and automated tests.

Run the full test suite using:

python -m pytest tests/ -q

Report actual results, including failures, skipped tests, limitations, and any intentionally injected anomalies.

Do not modify the project unnecessarily during the audit.

### Prompt 10: Final Repository Review

**Purpose:** Prepare the project for public GitHub submission.

**Prompt:**

Review the complete project before public GitHub submission.

Check README setup instructions, dependencies, database initialization, backend startup, frontend startup, tests, exports, documentation, and AI prompt history.

Identify secrets, credentials, database files, virtual environments, node_modules, and oversized files that should not be committed.

Preserve the local project data and ensure the public repository contains only appropriate project artifacts.

---

# 4. Antigravity Prompt History

### Prompt 1: Initial Project Planning

**Purpose:** Build the application in structured phases.

**Prompt:**

Build the YottaFlex Student Finance Management System according to the complete recruitment problem statement.

Use Python, FastAPI, SQLite, and a JavaScript frontend.

Divide implementation into three phases:

Phase 1: Database foundation, schema, models, data dictionary, and project structure.

Phase 2: Financial business logic, synthetic data generation, API endpoints, and frontend integration.

Phase 3: Anomaly detection, reconciliation, evaluation, validation, testing, and documentation.

Keep the implementation modular and do not omit any required business entity.

### Prompt 2: Phase 1 - Database Foundation

**Purpose:** Establish database structure.

**Prompt:**

Implement Phase 1 of the YottaFlex Student Finance Management System.

Create the SQLite database schema for all 11 required entities.

Implement primary keys, foreign keys, indexes, unique constraints, check constraints, and relationships.

Create database management utilities and model definitions.

Document the complete schema and data dictionary.

Verify database integrity and foreign-key relationships.

### Prompt 3: Phase 2 - Business Logic and Data Generation

**Purpose:** Implement financial workflows.

**Prompt:**

Implement Phase 2 of the Student Finance Management System.

Create the deterministic synthetic data generator with seed 20261022.

Implement student, program, fee schedule, enrollment, invoice, scholarship, payment, allocation, and refund workflows.

Calculate financial balances, scholarship credits, late fees, outstanding amounts, and overpayments from source transactions.

Implement the FastAPI backend and integrate the frontend.

Maintain valid parent-child relationships and transaction traceability.

### Prompt 4: Phase 3 - Validation and Anomaly Detection

**Purpose:** Implement exception handling and evaluation.

**Prompt:**

Implement Phase 3 of the Student Finance Management System.

Create anomaly injection, detection, and evaluation modules for all five required negative scenarios.

Implement financial reconciliation and ground-truth comparison.

Calculate precision, recall, and F1 score.

Add validation tests for database integrity, business rules, anomaly detection, and reconciliation.

Do not corrupt unrelated baseline data.

### Prompt 5: Frontend Functionality

**Purpose:** Implement the user interface.

**Prompt:**

Build a clean and functional frontend for the Student Finance Management System.

Include:
- Dashboard.
- Students.
- Programs and Fees.
- Fee Schedules.
- Invoices.
- Payments.
- Scholarships.
- Refunds.
- Reconciliation.
- Anomaly Detection.
- Data Exports.

Connect the frontend to the FastAPI backend.

Ensure tables, search, filters, pagination, detail views, and downloads work correctly.

### Prompt 6: Runtime Verification

**Purpose:** Verify real application behavior.

**Prompt:**

Run and verify the Student Finance Management System locally.

Check that the FastAPI backend starts successfully and the frontend connects to the correct API endpoints.

Verify actual data flow from frontend requests to backend services and SQLite queries.

Check that pages load, records display correctly, filters work, and export downloads are generated.

Fix only confirmed issues and preserve existing functionality.

### Prompt 7: Final Acceptance Audit

**Purpose:** Verify challenge requirements.

**Prompt:**

Perform the final YottaFlex acceptance audit.

Verify the five required anomalies, reconciliation, financial calculations, ground truth, deterministic data generation, database integrity, CSV and JSON exports, frontend build, and complete automated test suite.

Compare the implementation with the original problem statement.

Document actual results and known limitations.

Do not claim that any requirement passed unless it has been verified.

---

# 5. AI Usage Transparency and Candidate Responsibility

AI tools were used for development assistance, planning, debugging, code review, and documentation.

The candidate is responsible for understanding the project architecture, financial calculations, database relationships, API workflows, anomaly detection logic, reconciliation rules, and validation results.

The candidate reviewed the application manually and verified important workflows through the user interface, including:

- Dashboard and student records.
- Student search and pagination.
- Program and fee schedule views.
- Invoice details and payment allocations.
- Scholarship lookup and refunds.
- Financial reconciliation.
- Anomaly detection and evaluation.
- CSV and JSON exports.

The candidate should be prepared to explain implementation decisions, assumptions, limitations, and testing results during the technical evaluation.

## 6. Limitations of This Prompt Record

This document is a reconstructed record of the AI-assisted development workflow.

It does not claim to reproduce every original prompt submitted to ChatGPT, Claude Code, or Antigravity word-for-word.

Where original prompt logs are unavailable, task descriptions have been documented transparently instead of presenting invented historical transcripts as exact prompts.

**End of AI Prompt History**

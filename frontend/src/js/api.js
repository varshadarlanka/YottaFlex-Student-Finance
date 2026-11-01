/**
 * api.js — Reusable API client for the FastAPI backend.
 *
 * All endpoints are proxied through Vite's dev server in development.
 * In production the frontend is served from the same origin as the API.
 */

const BASE = '/api/v1';

async function request(path, options = {}) {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Accept': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.json();
}

// ---- Health ----
export function checkHealth() {
  return fetch('/health', { headers: { 'Accept': 'application/json' } })
    .then(r => r.ok);
}

// ---- Dashboard ----
export function getDashboard() {
  return request('/dashboard');
}

// ---- Students ----
export function listStudents(page = 1, pageSize = 20, status = null) {
  let qs = `?page=${page}&page_size=${pageSize}`;
  if (status) qs += `&status=${status}`;
  return request(`/students${qs}`);
}

export function getStudent(studentId) {
  return request(`/students/${studentId}`);
}

export function getStudentEnrollments(studentId) {
  return request(`/students/${studentId}/enrollments`);
}

// ---- Programs ----
export function listPrograms() {
  return request('/programs');
}

export function getProgram(programId) {
  return request(`/programs/${programId}`);
}

// ---- Invoices ----
export function listStudentInvoices(studentId, page = 1, pageSize = 20) {
  return request(`/students/${studentId}/invoices?page=${page}&page_size=${pageSize}`);
}

export function getInvoice(invoiceId) {
  return request(`/invoices/${invoiceId}`);
}

// ---- Scholarships ----
export function listScholarships() {
  return request('/scholarships');
}

export function getStudentScholarships(studentId) {
  return request(`/students/${studentId}/scholarships`);
}

// ---- Payments ----
export function listStudentPayments(studentId, page = 1, pageSize = 20) {
  return request(`/students/${studentId}/payments?page=${page}&page_size=${pageSize}`);
}

export function getPaymentAllocations(paymentId) {
  return request(`/payments/${paymentId}/allocations`);
}

// ---- Refunds ----
export function listStudentRefunds(studentId) {
  return request(`/students/${studentId}/refunds`);
}

// ---- Balance ----
export function getStudentBalance(studentId, termId = null) {
  let qs = '';
  if (termId) qs = `?term_id=${termId}`;
  return request(`/students/${studentId}/balance${qs}`);
}

// ---- Reconciliation ----
export function getReconciliation(termId = null, studentId = null) {
  const params = new URLSearchParams();
  if (termId) params.set('term_id', termId);
  if (studentId) params.set('student_id', studentId);
  const qs = params.toString();
  return request(`/reconciliation${qs ? '?' + qs : ''}`);
}

// ---- Anomaly Detection ----
export function detectAnomalies() {
  return request('/anomalies/detect');
}

export function evaluateAnomalies() {
  return request('/anomalies/evaluate');
}

// ---- Exports ----
export function exportCSV() {
  return request('/export/csv');
}

export function exportJSON() {
  return request('/export/json');
}

export async function downloadExport(format) {
  if (!['csv', 'json'].includes(format)) {
    throw new Error(`Unsupported export format: ${format}`);
  }

  const response = await fetch(`${BASE}/export/${format}/download`, {
    headers: { 'Accept': 'application/zip' },
  });
  if (!response.ok) {
    const body = await response.text();
    let message = body || `HTTP ${response.status}`;
    try {
      const error = JSON.parse(body);
      if (error.detail) message = error.detail;
    } catch {
      // Non-JSON error bodies are displayed as text.
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
    || `yottaflex-${format}-export.zip`;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

// ---- Fee Schedules & Terms (new lightweight endpoints) ----
export function listFeeSchedules() {
  return request('/fee-schedules');
}

export function getFeeScheduleLines(scheduleId) {
  return request(`/fee-schedules/${scheduleId}/lines`);
}

export function listTerms() {
  return request('/terms');
}

// ---- Search: find students by name or code ----
export function searchStudents(query, page = 1, pageSize = 20) {
  return request(`/students/search?q=${encodeURIComponent(query)}&page=${page}&page_size=${pageSize}`);
}

// ---- All invoices (paginated) ----
export function listAllInvoices(page = 1, pageSize = 20, status = null) {
  let qs = `?page=${page}&page_size=${pageSize}`;
  if (status) qs += `&status=${status}`;
  return request(`/invoices${qs}`);
}

// ---- All payments (paginated) ----
export function listAllPayments(page = 1, pageSize = 20, status = null) {
  let qs = `?page=${page}&page_size=${pageSize}`;
  if (status) qs += `&status=${status}`;
  return request(`/payments${qs}`);
}

// ---- All refunds (paginated) ----
export function listAllRefunds(page = 1, pageSize = 20) {
  return request(`/refunds?page=${page}&page_size=${pageSize}`);
}

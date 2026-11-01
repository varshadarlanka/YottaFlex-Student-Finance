/**
 * components.js — Page renderers for all nine pages.
 */
import * as api from './api.js';
import {
  formatINR, formatINRValue, formatNumber, formatDate, capitalize,
  statusBadgeClass, html, render, loadingHTML, emptyHTML, errorHTML,
  debounce, paginationHTML, escapeHTML,
} from './utils.js';

// =====================================================================
// 1. DASHBOARD
// =====================================================================
export async function renderDashboard(container) {
  render(container, loadingHTML('Loading dashboard…'));
  try {
    const d = await api.getDashboard();
    render(container, `
      <div class="page-header"><h1>Dashboard</h1><p>Financial overview across the institution</p></div>
      <div class="cards-grid">
        ${card('Students', formatNumber(d.students), '', 'info')}
        ${card('Invoices', formatNumber(d.invoices), '', 'info')}
        ${card('Payments', formatNumber(d.payments), '', 'success')}
        ${card('Refunds', formatNumber(d.refunds), '', 'warning')}
        ${card('Scholarships', formatNumber(d.scholarships), '', 'info')}
        ${card('Total Invoiced', formatINRValue(d.total_invoiced_inr), '', '')}
        ${card('Total Paid', formatINRValue(d.total_paid_inr), '', 'success')}
        ${card('Total Refunded', formatINRValue(d.total_refunded_inr), '', 'warning')}
        ${card('Outstanding', formatINRValue(d.outstanding_inr), '', 'danger')}
      </div>
    `);
  } catch (e) {
    render(container, errorHTML('Failed to load dashboard', e.message));
  }
}

function card(label, value, sub, variant) {
  return `<div class="stat-card ${variant}">
    <div class="card-label">${label}</div>
    <div class="card-value">${value}</div>
    ${sub ? `<div class="card-sub">${sub}</div>` : ''}
  </div>`;
}

// =====================================================================
// 2. STUDENTS
// =====================================================================
let studentsState = { page: 1, status: null, search: '' };

export async function renderStudents(container) {
  studentsState = { page: 1, status: null, search: '' };
  await loadStudents(container);
}

async function loadStudents(container) {
  render(container, `
    <div class="page-header"><h1>Students</h1><p>Browse and search student records</p></div>
    <div class="panel">
      <div class="panel-header">
        <h2>Student List</h2>
        <div class="search-bar">
          <input class="search-input" id="student-search" placeholder="Search by name or code…" value="${escapeHTML(studentsState.search)}">
          <select class="search-input" id="student-status-filter">
            <option value="">All Statuses</option>
            <option value="active" ${studentsState.status === 'active' ? 'selected' : ''}>Active</option>
            <option value="inactive" ${studentsState.status === 'inactive' ? 'selected' : ''}>Inactive</option>
            <option value="graduated" ${studentsState.status === 'graduated' ? 'selected' : ''}>Graduated</option>
            <option value="withdrawn" ${studentsState.status === 'withdrawn' ? 'selected' : ''}>Withdrawn</option>
            <option value="suspended" ${studentsState.status === 'suspended' ? 'selected' : ''}>Suspended</option>
          </select>
        </div>
      </div>
      <div id="students-table-area">${loadingHTML()}</div>
    </div>
  `);
  bindStudentControls(container);
  await fetchStudents(container);
}

function bindStudentControls(container) {
  const searchInput = container.querySelector('#student-search');
  const statusSelect = container.querySelector('#student-status-filter');
  const doSearch = debounce(async () => {
    studentsState.search = searchInput.value.trim();
    studentsState.page = 1;
    await fetchStudents(container);
  }, 400);
  searchInput?.addEventListener('input', doSearch);
  statusSelect?.addEventListener('change', async () => {
    studentsState.status = statusSelect.value || null;
    studentsState.page = 1;
    await fetchStudents(container);
  });
}

async function fetchStudents(container) {
  const area = container.querySelector('#students-table-area');
  if (!area) return;
  area.innerHTML = loadingHTML();
  try {
    let data;
    if (studentsState.search) {
      data = await api.searchStudents(studentsState.search, studentsState.page, 20);
    } else {
      data = await api.listStudents(studentsState.page, 20, studentsState.status);
    }
    if (!data.items.length) {
      area.innerHTML = emptyHTML('No students found');
      return;
    }
    area.innerHTML = `
      <div class="table-wrapper"><table>
        <thead><tr>
          <th>ID</th><th>Code</th><th>Name</th><th>Email</th><th>Gender</th><th>Status</th><th>Actions</th>
        </tr></thead>
        <tbody>${data.items.map(s => `
          <tr>
            <td>${s.student_id}</td>
            <td>${escapeHTML(s.student_code)}</td>
            <td>${escapeHTML(s.first_name)} ${escapeHTML(s.last_name)}</td>
            <td>${escapeHTML(s.email)}</td>
            <td>${s.gender || '—'}</td>
            <td><span class="badge ${statusBadgeClass(s.status)}">${s.status}</span></td>
            <td><button class="btn btn-primary btn-sm view-student-btn" data-id="${s.student_id}">View</button></td>
          </tr>`).join('')}
        </tbody>
      </table></div>
      ${paginationHTML(data.page, data.page_size, data.total)}
    `;
    area.querySelectorAll('.view-student-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const studentId = Number(btn.dataset.id);
        if (!Number.isInteger(studentId) || studentId < 1) return;
        history.pushState({ fromStudentsList: true }, '', `#students/${studentId}`);
        renderStudentDetail(container, studentId);
      });
    });
    area.querySelectorAll('.pagination-controls .btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        studentsState.page = Number(btn.dataset.page);
        await fetchStudents(container);
      });
    });
  } catch (e) {
    area.innerHTML = errorHTML('Failed to load students', e.message);
  }
}

export async function renderStudentDetail(container, studentId) {
  render(container, loadingHTML('Loading student details…'));
  try {
    const [student, enrollments, balance, invoices] = await Promise.all([
      api.getStudent(studentId),
      api.getStudentEnrollments(studentId),
      api.getStudentBalance(studentId),
      api.listStudentInvoices(studentId),
    ]);
    render(container, `
      <a class="back-link" id="back-to-students" href="#students">← Back to Students</a>
      <div class="page-header"><h1>${escapeHTML(student.first_name)} ${escapeHTML(student.last_name)}</h1>
        <p>${escapeHTML(student.student_code)} · <span class="badge ${statusBadgeClass(student.status)}">${student.status}</span></p>
      </div>

      <div class="panel"><div class="panel-header"><h2>Personal Information</h2></div>
        <div class="panel-body"><div class="detail-grid">
          ${detailItem('Student ID', student.student_id)}
          ${detailItem('Code', student.student_code)}
          ${detailItem('Email', student.email)}
          ${detailItem('Phone', student.phone || '—')}
          ${detailItem('Date of Birth', formatDate(student.date_of_birth))}
          ${detailItem('Gender', student.gender || '—')}
          ${detailItem('Address', [student.address_line1, student.city, student.state, student.pincode].filter(Boolean).join(', ') || '—')}
          ${detailItem('Enrolled Since', formatDate(student.created_at))}
        </div></div>
      </div>

      <div class="panel"><div class="panel-header"><h2>Financial Summary</h2></div>
        <div class="panel-body"><div class="cards-grid">
          ${card('Total Invoiced', formatINRValue(balance.total_invoiced_inr), '', '')}
          ${card('Scholarship Credits', formatINRValue(balance.scholarship_credits_inr), '', 'info')}
          ${card('Net Payable', formatINRValue(balance.net_payable_inr), '', '')}
          ${card('Total Paid', formatINRValue(balance.total_paid_inr), '', 'success')}
          ${card('Total Refunded', formatINRValue(balance.total_refunded_inr), '', 'warning')}
          ${card('Outstanding', formatINRValue(balance.outstanding_inr), '', 'danger')}
          ${card('Overpayment', formatINRValue(balance.overpayment_inr), '', 'info')}
        </div></div>
      </div>

      <div class="panel"><div class="panel-header"><h2>Enrollments (${enrollments.length})</h2></div>
        ${enrollments.length ? `<div class="table-wrapper"><table>
          <thead><tr><th>ID</th><th>Program</th><th>Term</th><th>Year</th><th>Status</th></tr></thead>
          <tbody>${enrollments.map(e => `<tr>
            <td>${e.enrollment_id}</td>
            <td>${escapeHTML(e.program_name || '')} (${escapeHTML(e.program_code || '')})</td>
            <td>${escapeHTML(e.term_name || '')}</td>
            <td>${e.year_of_study}</td>
            <td><span class="badge ${statusBadgeClass(e.status)}">${e.status}</span></td>
          </tr>`).join('')}</tbody>
        </table></div>` : `<div class="panel-body">${emptyHTML('No enrollments')}</div>`}
      </div>

      <div class="panel"><div class="panel-header"><h2>Invoices (${invoices.total})</h2></div>
        ${invoices.items.length ? `<div class="table-wrapper"><table>
          <thead><tr><th>Invoice #</th><th>Term</th><th>Issue Date</th><th>Due Date</th><th>Status</th></tr></thead>
          <tbody>${invoices.items.map(invoice => `<tr>
            <td>${escapeHTML(invoice.invoice_number)}</td>
            <td>${escapeHTML(invoice.term_name || '')}</td>
            <td>${formatDate(invoice.issue_date)}</td>
            <td>${formatDate(invoice.due_date)}</td>
            <td><span class="badge ${statusBadgeClass(invoice.status)}">${escapeHTML(invoice.status)}</span></td>
          </tr>`).join('')}</tbody>
        </table></div>` : `<div class="panel-body">${emptyHTML('No invoices found')}</div>`}
      </div>
    `);
    container.querySelector('#back-to-students')?.addEventListener('click', (event) => {
      event.preventDefault();
      if (history.state?.fromStudentsList) {
        history.back();
      } else {
        history.replaceState(null, '', '#students');
        renderStudents(container);
      }
    });
  } catch (e) {
    render(container, errorHTML('Failed to load student', e.message));
  }
}

function detailItem(label, value) {
  return `<div class="detail-item"><div class="detail-label">${label}</div><div class="detail-value">${value ?? '—'}</div></div>`;
}

// =====================================================================
// 3. PROGRAMS & FEES
// =====================================================================
export async function renderPrograms(container) {
  render(container, loadingHTML('Loading programs…'));
  try {
    const [programs, schedules, terms] = await Promise.all([
      api.listPrograms(),
      api.listFeeSchedules(),
      api.listTerms(),
    ]);
    render(container, `
      <div class="page-header"><h1>Programs & Fees</h1><p>Academic programmes, terms, and fee schedules</p></div>

      <div class="panel"><div class="panel-header"><h2>Academic Terms (${terms.length})</h2></div>
        <div class="table-wrapper"><table>
          <thead><tr><th>ID</th><th>Code</th><th>Name</th><th>Start</th><th>End</th><th>Active</th></tr></thead>
          <tbody>${terms.map(t => `<tr>
            <td>${t.term_id}</td><td>${escapeHTML(t.term_code)}</td><td>${escapeHTML(t.term_name)}</td>
            <td>${formatDate(t.start_date)}</td><td>${formatDate(t.end_date)}</td>
            <td><span class="badge ${t.is_active ? 'badge-success' : 'badge-neutral'}">${t.is_active ? 'Active' : 'Inactive'}</span></td>
          </tr>`).join('')}</tbody>
        </table></div>
      </div>

      <div class="panel"><div class="panel-header"><h2>Programs (${programs.length})</h2></div>
        <div class="table-wrapper"><table>
          <thead><tr><th>ID</th><th>Code</th><th>Name</th><th>Department</th><th>Duration</th><th>Level</th><th>Active</th></tr></thead>
          <tbody>${programs.map(p => `<tr>
            <td>${p.program_id}</td><td>${escapeHTML(p.program_code)}</td><td>${escapeHTML(p.program_name)}</td>
            <td>${escapeHTML(p.department || '—')}</td><td>${p.duration_years} yrs</td><td>${escapeHTML(p.level)}</td>
            <td><span class="badge ${p.is_active ? 'badge-success' : 'badge-neutral'}">${p.is_active ? 'Yes' : 'No'}</span></td>
          </tr>`).join('')}</tbody>
        </table></div>
      </div>

      <div class="panel"><div class="panel-header"><h2>Fee Schedules (${schedules.length})</h2></div>
        <div class="table-wrapper"><table>
          <thead><tr><th>ID</th><th>Program</th><th>Term</th><th>Effective From</th><th>Status</th><th>Details</th></tr></thead>
          <tbody>${schedules.map(fs => `<tr>
            <td>${fs.schedule_id}</td>
            <td>${escapeHTML(fs.program_name)} (${escapeHTML(fs.program_code)})</td>
            <td>${escapeHTML(fs.term_name)}</td>
            <td>${formatDate(fs.effective_from)}</td>
            <td><span class="badge ${statusBadgeClass(fs.status)}">${fs.status}</span></td>
            <td><button class="btn btn-secondary btn-sm view-fs-btn" data-id="${fs.schedule_id}">View Lines</button></td>
          </tr>`).join('')}</tbody>
        </table></div>
        <div id="fs-lines-area"></div>
      </div>
    `);
    container.querySelectorAll('.view-fs-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const area = container.querySelector('#fs-lines-area');
        area.innerHTML = loadingHTML('Loading fee components…');
        try {
          const lines = await api.getFeeScheduleLines(Number(btn.dataset.id));
          if (!lines.length) { area.innerHTML = `<div class="panel-body">${emptyHTML('No fee components')}</div>`; return; }
          area.innerHTML = `<div class="panel-body"><h3 style="margin-bottom:12px;">Fee Components — Schedule #${btn.dataset.id}</h3>
            <table><thead><tr><th>Fee Type</th><th>Description</th><th>Amount</th><th>Mandatory</th></tr></thead>
            <tbody>${lines.map(l => `<tr>
              <td>${escapeHTML(l.fee_type)}</td><td>${escapeHTML(l.description || '—')}</td>
              <td class="amount">${formatINR(l.amount_paise)}</td>
              <td>${l.is_mandatory ? '✔️' : '—'}</td>
            </tr>`).join('')}</tbody></table></div>`;
        } catch (e) { area.innerHTML = `<div class="panel-body">${errorHTML('Failed to load fee lines', e.message)}</div>`; }
        finally { area.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      });
    });
  } catch (e) {
    render(container, errorHTML('Failed to load programs', e.message));
  }
}

// =====================================================================
// 4. INVOICES
// =====================================================================
let invoicesState = { page: 1, status: null };

export async function renderInvoices(container) {
  invoicesState = { page: 1, status: null };
  await loadInvoicesPage(container);
}

async function loadInvoicesPage(container) {
  render(container, `
    <div class="page-header"><h1>Invoices</h1><p>All invoices across students</p></div>
    <div class="panel">
      <div class="panel-header">
        <h2>Invoice List</h2>
        <div class="search-bar">
          <select class="search-input" id="invoice-status-filter">
            <option value="">All Statuses</option>
            <option value="issued">Issued</option>
            <option value="paid">Paid</option>
            <option value="partially_paid">Partially Paid</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>
      <div id="invoices-table-area">${loadingHTML()}</div>
    </div>
  `);
  container.querySelector('#invoice-status-filter')?.addEventListener('change', async (e) => {
    invoicesState.status = e.target.value || null;
    invoicesState.page = 1;
    await fetchInvoices(container);
  });
  await fetchInvoices(container);
}

async function fetchInvoices(container) {
  const area = container.querySelector('#invoices-table-area');
  if (!area) return;
  area.innerHTML = loadingHTML();
  try {
    const data = await api.listAllInvoices(invoicesState.page, 20, invoicesState.status);
    if (!data.items.length) { area.innerHTML = emptyHTML('No invoices found'); return; }
    area.innerHTML = `
      <div class="table-wrapper"><table>
        <thead><tr><th>Invoice #</th><th>Student</th><th>Term</th><th>Issue Date</th><th>Due Date</th>
          <th>Total</th><th>Paid</th><th>Outstanding</th><th>Status</th><th>Details</th></tr></thead>
        <tbody>${data.items.map(inv => `<tr>
          <td>${escapeHTML(inv.invoice_number)}</td>
          <td>${escapeHTML(inv.student_code)} — ${escapeHTML(inv.first_name)} ${escapeHTML(inv.last_name)}</td>
          <td>${escapeHTML(inv.term_name || '')}</td>
          <td>${formatDate(inv.issue_date)}</td><td>${formatDate(inv.due_date)}</td>
          <td class="amount">${formatINR(inv.total_paise)}</td>
          <td class="amount">${formatINR(inv.paid_paise)}</td>
          <td class="amount">${formatINR(inv.outstanding_paise)}</td>
          <td><span class="badge ${statusBadgeClass(inv.status)}">${inv.status}</span></td>
          <td><button class="btn btn-secondary btn-sm view-inv-btn" data-id="${inv.invoice_id}">View</button></td>
        </tr>`).join('')}</tbody>
      </table></div>
      ${paginationHTML(data.page, data.page_size, data.total)}
    `;
    area.querySelectorAll('.view-inv-btn').forEach(btn => {
      btn.addEventListener('click', () => renderInvoiceDetail(container, Number(btn.dataset.id)));
    });
    area.querySelectorAll('.pagination-controls .btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        invoicesState.page = Number(btn.dataset.page);
        await fetchInvoices(container);
      });
    });
  } catch (e) { area.innerHTML = errorHTML('Failed to load invoices', e.message); }
}

async function renderInvoiceDetail(container, invoiceId) {
  render(container, loadingHTML('Loading invoice…'));
  try {
    const inv = await api.getInvoice(invoiceId);
    render(container, `
      <a class="back-link" id="back-to-invoices">← Back to Invoices</a>
      <div class="page-header"><h1>Invoice ${escapeHTML(inv.invoice_number)}</h1>
        <p>Invoice #${inv.invoice_id} · <span class="badge ${statusBadgeClass(inv.status)}">${inv.status}</span></p></div>
      <div class="panel"><div class="panel-header"><h2>Invoice Information</h2></div>
        <div class="panel-body"><div class="detail-grid">
          ${detailItem('Invoice ID', inv.invoice_id)}
          ${detailItem('Invoice Number', inv.invoice_number)}
          ${detailItem('Enrollment ID', inv.enrollment_id)}
          ${detailItem('Term', inv.term_name || inv.term_id)}
          ${detailItem('Issue Date', formatDate(inv.issue_date))}
          ${detailItem('Due Date', formatDate(inv.due_date))}
          ${detailItem('Total Amount', formatINRValue(inv.total_inr))}
          ${detailItem('Status', inv.status)}
        </div></div></div>
      <div class="panel"><div class="panel-header"><h2>Line Items (${inv.lines.length})</h2></div>
        ${inv.lines.length ? `<div class="table-wrapper"><table>
          <thead><tr><th>Line ID</th><th>Fee Type</th><th>Description</th><th>Amount</th><th>Scholarship Credit</th></tr></thead>
          <tbody>${inv.lines.map(l => `<tr>
            <td>${l.line_id}</td><td>${escapeHTML(l.fee_type)}</td><td>${escapeHTML(l.description || '—')}</td>
            <td class="amount">${formatINR(l.amount_paise)}</td>
            <td>${l.is_scholarship_credit ? '<span class="badge badge-info">Yes</span>' : '—'}</td>
          </tr>`).join('')}</tbody>
        </table></div>` : `<div class="panel-body">${emptyHTML('No line items')}</div>`}
      </div>
    `);
    container.querySelector('#back-to-invoices')?.addEventListener('click', () => loadInvoicesPage(container));
  } catch (e) { render(container, errorHTML('Failed to load invoice', e.message)); }
}

// =====================================================================
// 5. SCHOLARSHIPS
// =====================================================================
export async function renderScholarships(container) {
  render(container, loadingHTML('Loading scholarships…'));
  try {
    const scholarships = await api.listScholarships();
    render(container, `
      <div class="page-header"><h1>Scholarships</h1><p>Scholarship catalogue and student awards</p></div>
      <div class="panel"><div class="panel-header"><h2>Scholarship Catalogue (${scholarships.length})</h2></div>
        <div class="table-wrapper"><table>
          <thead><tr><th>ID</th><th>Code</th><th>Name</th><th>Type</th><th>Max Amount</th><th>Discount %</th><th>Renewable</th><th>Active</th></tr></thead>
          <tbody>${scholarships.map(s => `<tr>
            <td>${s.scholarship_id}</td><td>${escapeHTML(s.scholarship_code)}</td><td>${escapeHTML(s.scholarship_name)}</td>
            <td>${escapeHTML(s.scholarship_type)}</td>
            <td class="amount">${s.max_amount_inr != null ? formatINRValue(s.max_amount_inr) : '—'}</td>
            <td>${s.percentage_discount != null ? s.percentage_discount + '%' : '—'}</td>
            <td>${s.is_renewable ? '✔️' : '—'}</td>
            <td><span class="badge ${s.is_active ? 'badge-success' : 'badge-neutral'}">${s.is_active ? 'Yes' : 'No'}</span></td>
          </tr>`).join('')}</tbody>
        </table></div>
      </div>

      <div class="panel"><div class="panel-header"><h2>Student Scholarship Lookup</h2>
        <div class="search-bar">
          <input class="search-input" id="schol-student-id" placeholder="Enter Student ID" type="number" min="1">
          <button class="btn btn-primary btn-sm" id="schol-lookup-btn">Look Up</button>
        </div></div>
        <div id="schol-eligibility-area" class="panel-body">${emptyHTML('Enter a student ID to view their scholarship awards', '🔍')}</div>
      </div>
    `);
    container.querySelector('#schol-lookup-btn')?.addEventListener('click', async () => {
      const sid = Number(container.querySelector('#schol-student-id').value);
      const area = container.querySelector('#schol-eligibility-area');
      if (!sid) { area.innerHTML = errorHTML('Please enter a valid Student ID'); return; }
      area.innerHTML = loadingHTML();
      try {
        const elig = await api.getStudentScholarships(sid);
        if (!elig.length) { area.innerHTML = emptyHTML('No scholarship awards for this student'); return; }
        area.innerHTML = `<table>
          <thead><tr><th>Eligibility ID</th><th>Scholarship</th><th>Term</th><th>Awarded</th><th>Status</th><th>Applied</th><th>Approved</th></tr></thead>
          <tbody>${elig.map(e => `<tr>
            <td>${e.eligibility_id}</td>
            <td>${escapeHTML(e.scholarship_name || '')} (${escapeHTML(e.scholarship_code || '')})</td>
            <td>${escapeHTML(e.term_name || '')}</td>
            <td class="amount">${formatINR(e.awarded_amount_paise)}</td>
            <td><span class="badge ${statusBadgeClass(e.status)}">${e.status}</span></td>
            <td>${formatDate(e.applied_date)}</td>
            <td>${formatDate(e.approved_date)}</td>
          </tr>`).join('')}</tbody>
        </table>`;
      } catch (e) { area.innerHTML = errorHTML('Failed to load scholarships', e.message); }
    });
  } catch (e) { render(container, errorHTML('Failed to load scholarships', e.message)); }
}

// =====================================================================
// 6. PAYMENTS
// =====================================================================
let paymentsState = { page: 1, status: null };

export async function renderPayments(container) {
  paymentsState = { page: 1, status: null };
  await loadPaymentsPage(container);
}

async function loadPaymentsPage(container) {
  render(container, `
    <div class="page-header"><h1>Payments</h1><p>All payment transactions</p></div>
    <div class="panel">
      <div class="panel-header"><h2>Payment List</h2>
        <div class="search-bar">
          <select class="search-input" id="payment-status-filter">
            <option value="">All Statuses</option>
            <option value="cleared">Cleared</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>
      <div id="payments-table-area">${loadingHTML()}</div>
    </div>
  `);
  container.querySelector('#payment-status-filter')?.addEventListener('change', async (e) => {
    paymentsState.status = e.target.value || null;
    paymentsState.page = 1;
    await fetchPayments(container);
  });
  await fetchPayments(container);
}

async function fetchPayments(container) {
  const area = container.querySelector('#payments-table-area');
  if (!area) return;
  area.innerHTML = loadingHTML();
  try {
    const data = await api.listAllPayments(paymentsState.page, 20, paymentsState.status);
    if (!data.items.length) { area.innerHTML = emptyHTML('No payments found'); return; }
    area.innerHTML = `
      <div class="table-wrapper"><table>
        <thead><tr><th>Payment ID</th><th>Reference</th><th>Student</th><th>Date</th><th>Amount</th><th>Method</th><th>Status</th><th>Allocations</th></tr></thead>
        <tbody>${data.items.map(p => `<tr>
          <td>${p.payment_id}</td>
          <td>${escapeHTML(p.payment_reference)}</td>
          <td>${escapeHTML(p.student_code)} — ${escapeHTML(p.first_name)} ${escapeHTML(p.last_name)}</td>
          <td>${formatDate(p.payment_date)}</td>
          <td class="amount">${formatINR(p.amount_paise)}</td>
          <td>${escapeHTML(p.payment_method)}</td>
          <td><span class="badge ${statusBadgeClass(p.status)}">${p.status}</span></td>
          <td><button class="btn btn-secondary btn-sm view-alloc-btn" data-id="${p.payment_id}">View</button></td>
        </tr>`).join('')}</tbody>
      </table></div>
      ${paginationHTML(data.page, data.page_size, data.total)}
    `;
    area.querySelectorAll('.view-alloc-btn').forEach(btn => {
      btn.addEventListener('click', () => renderAllocationDetail(container, Number(btn.dataset.id)));
    });
    area.querySelectorAll('.pagination-controls .btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        paymentsState.page = Number(btn.dataset.page);
        await fetchPayments(container);
      });
    });
  } catch (e) { area.innerHTML = errorHTML('Failed to load payments', e.message); }
}

async function renderAllocationDetail(container, paymentId) {
  render(container, loadingHTML('Loading allocations…'));
  try {
    const allocs = await api.getPaymentAllocations(paymentId);
    render(container, `
      <a class="back-link" id="back-to-payments">← Back to Payments</a>
      <div class="page-header"><h1>Payment #${paymentId} — Allocations</h1></div>
      <div class="panel"><div class="panel-header"><h2>Allocations (${allocs.length})</h2></div>
        ${allocs.length ? `<div class="table-wrapper"><table>
          <thead><tr><th>Allocation ID</th><th>Invoice</th><th>Fee Type</th><th>Line Amount</th><th>Allocated</th><th>Date</th></tr></thead>
          <tbody>${allocs.map(a => `<tr>
            <td>${a.allocation_id}</td>
            <td>${escapeHTML(a.invoice_number || '—')}</td>
            <td>${escapeHTML(a.fee_type || '—')}</td>
            <td class="amount">${a.line_amount != null ? formatINR(a.line_amount) : '—'}</td>
            <td class="amount">${formatINR(a.allocated_amount_paise)}</td>
            <td>${formatDate(a.allocated_at)}</td>
          </tr>`).join('')}</tbody>
        </table></div>` : `<div class="panel-body">${emptyHTML('No allocations for this payment')}</div>`}
      </div>
    `);
    container.querySelector('#back-to-payments')?.addEventListener('click', () => loadPaymentsPage(container));
  } catch (e) { render(container, errorHTML('Failed to load allocations', e.message)); }
}

// =====================================================================
// 7. REFUNDS
// =====================================================================
let refundsState = { page: 1 };

export async function renderRefunds(container) {
  refundsState = { page: 1 };
  await loadRefundsPage(container);
}

async function loadRefundsPage(container) {
  render(container, `
    <div class="page-header"><h1>Refunds</h1><p>All refund transactions</p></div>
    <div class="panel"><div class="panel-header"><h2>Refund List</h2></div>
      <div id="refunds-table-area">${loadingHTML()}</div>
    </div>
  `);
  await fetchRefunds(container);
}

async function fetchRefunds(container) {
  const area = container.querySelector('#refunds-table-area');
  if (!area) return;
  area.innerHTML = loadingHTML();
  try {
    const data = await api.listAllRefunds(refundsState.page, 20);
    if (!data.items.length) { area.innerHTML = emptyHTML('No refunds found'); return; }
    area.innerHTML = `
      <div class="table-wrapper"><table>
        <thead><tr><th>Refund ID</th><th>Reference</th><th>Payment ID</th><th>Student</th><th>Date</th><th>Amount</th><th>Reason</th><th>Method</th><th>Status</th></tr></thead>
        <tbody>${data.items.map(r => `<tr>
          <td>${r.refund_id}</td>
          <td>${escapeHTML(r.refund_reference)}</td>
          <td>${r.payment_id}</td>
          <td>${escapeHTML(r.student_code)} — ${escapeHTML(r.first_name)} ${escapeHTML(r.last_name)}</td>
          <td>${formatDate(r.refund_date)}</td>
          <td class="amount">${formatINR(r.refund_amount_paise)}</td>
          <td>${escapeHTML(r.reason)}</td>
          <td>${escapeHTML(r.refund_method)}</td>
          <td><span class="badge ${statusBadgeClass(r.status)}">${r.status}</span></td>
        </tr>`).join('')}</tbody>
      </table></div>
      ${paginationHTML(data.page, data.page_size, data.total)}
    `;
    area.querySelectorAll('.pagination-controls .btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        refundsState.page = Number(btn.dataset.page);
        await fetchRefunds(container);
      });
    });
  } catch (e) { area.innerHTML = errorHTML('Failed to load refunds', e.message); }
}

// =====================================================================
// 8. RECONCILIATION
// =====================================================================
export async function renderReconciliation(container) {
  render(container, `
    <div class="page-header"><h1>Reconciliation</h1><p>Financial reconciliation across students and terms</p></div>
    <div class="panel"><div class="panel-header"><h2>Reconciliation Filters</h2>
      <div class="search-bar">
        <input class="search-input" id="recon-student-id" placeholder="Student ID (optional)" type="number" min="1">
        <select class="search-input" id="recon-term-filter"><option value="">All Terms</option></select>
        <button class="btn btn-primary btn-sm" id="recon-run-btn">Run Reconciliation</button>
      </div></div>
      <div id="recon-area" class="panel-body">${emptyHTML('Click "Run Reconciliation" to generate report', '⚖️')}</div>
    </div>
  `);
  // Load terms into filter
  try {
    const terms = await api.listTerms();
    const sel = container.querySelector('#recon-term-filter');
    terms.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t.term_id;
      opt.textContent = t.term_name;
      sel.appendChild(opt);
    });
  } catch { /* ignore term load error */ }

  const reconBtn = container.querySelector('#recon-run-btn');
  reconBtn?.addEventListener('click', async () => {
    if (reconBtn.disabled) return;
    reconBtn.disabled = true;
    reconBtn.textContent = 'Running…';
    const area = container.querySelector('#recon-area');
    const termId = container.querySelector('#recon-term-filter').value || null;
    const studentId = container.querySelector('#recon-student-id').value || null;
    area.innerHTML = loadingHTML('Running reconciliation…');
    try {
      const data = await api.getReconciliation(termId, studentId);
      const s = data.summary;
      area.innerHTML = `
        <div class="summary-grid">
          ${summaryItem('Students Reconciled', formatNumber(s.total_students_reconciled))}
          ${summaryItem('Terms Checked', formatNumber(s.total_terms_checked))}
          ${summaryItem('Reconciled OK', formatNumber(s.reconciled_ok), 'var(--success)')}
          ${summaryItem('Failures', formatNumber(s.reconciliation_failures), s.reconciliation_failures > 0 ? 'var(--danger)' : '')}
          ${summaryItem('Total Invoiced', formatINRValue(s.total_invoiced_inr))}
          ${summaryItem('Total Paid', formatINRValue(s.total_paid_inr))}
          ${summaryItem('Total Refunded', formatINRValue(s.total_refunded_inr))}
          ${summaryItem('Scholarship Credits', formatINRValue(s.total_scholarship_credits_inr))}
          ${summaryItem('Outstanding', formatINRValue(s.total_outstanding_inr), 'var(--danger)')}
          ${summaryItem('Overpayment', formatINRValue(s.total_overpayment_inr))}
        </div>
        <h3 style="margin:16px 0 10px;">Reconciliation Records (${data.records.length})</h3>
        ${data.records.length ? `<div class="table-wrapper"><table>
          <thead><tr><th>Student</th><th>Term</th><th>Invoiced</th><th>Scholarship</th><th>Net Payable</th><th>Paid</th><th>Refunded</th><th>Outstanding</th><th>Overpayment</th><th>Status</th></tr></thead>
          <tbody>${data.records.slice(0, 200).map(r => `<tr>
            <td>${escapeHTML(r.student_code)} — ${escapeHTML(r.student_name)}</td>
            <td>${escapeHTML(r.term_name || '—')}</td>
            <td class="amount">${formatINRValue(r.total_invoiced_inr)}</td>
            <td class="amount">${formatINRValue(r.scholarship_credits_inr)}</td>
            <td class="amount">${formatINRValue(r.net_payable_inr)}</td>
            <td class="amount">${formatINRValue(r.total_paid_inr)}</td>
            <td class="amount">${formatINRValue(r.total_refunded_inr)}</td>
            <td class="amount">${formatINRValue(r.outstanding_inr)}</td>
            <td class="amount">${formatINRValue(r.overpayment_inr)}</td>
            <td><span class="badge ${r.is_reconciled ? 'badge-success' : 'badge-danger'}">${r.is_reconciled ? 'OK' : 'Mismatch'}</span></td>
          </tr>`).join('')}</tbody>
        </table></div>
        ${data.records.length > 200 ? '<p style="padding:10px;color:var(--text-secondary)">Showing first 200 records.</p>' : ''}` : emptyHTML('No reconciliation records')}
      `;
    } catch (e) { area.innerHTML = errorHTML('Reconciliation failed', e.message); }
    finally { reconBtn.disabled = false; reconBtn.textContent = 'Run Reconciliation'; }
  });
}

function summaryItem(label, value, color) {
  return `<div class="summary-item">
    <div class="summary-label">${label}</div>
    <div class="summary-value" ${color ? `style="color:${color}"` : ''}>${value}</div>
  </div>`;
}

// =====================================================================
// 9. ANOMALY DETECTION
// =====================================================================
export async function renderAnomalies(container) {
  render(container, `
    <div class="page-header"><h1>Anomaly Detection</h1><p>Detect and evaluate financial anomalies</p></div>
    <div class="panel"><div class="panel-header"><h2>Detection</h2>
      <div class="search-bar">
        <button class="btn btn-primary btn-sm" id="detect-btn">🔍 Run Detection</button>
        <button class="btn btn-secondary btn-sm" id="evaluate-btn">📊 Evaluate (with metrics)</button>
      </div></div>
      <div id="anomaly-area" class="panel-body">${emptyHTML('Click "Run Detection" to scan for anomalies', '🔍')}</div>
    </div>
  `);

  const detectBtn = container.querySelector('#detect-btn');
  const evalBtn = container.querySelector('#evaluate-btn');

  detectBtn?.addEventListener('click', async () => {
    if (detectBtn.disabled) return;
    detectBtn.disabled = true;
    evalBtn.disabled = true;
    detectBtn.textContent = 'Running…';
    const area = container.querySelector('#anomaly-area');
    area.innerHTML = loadingHTML('Running anomaly detection…');
    try {
      const issues = await api.detectAnomalies();
      renderDetectedIssues(area, issues);
    } catch (e) { area.innerHTML = errorHTML('Detection failed', e.message); }
    finally { detectBtn.disabled = false; evalBtn.disabled = false; detectBtn.innerHTML = '🔍 Run Detection'; }
  });

  evalBtn?.addEventListener('click', async () => {
    if (evalBtn.disabled) return;
    detectBtn.disabled = true;
    evalBtn.disabled = true;
    evalBtn.textContent = 'Evaluating…';
    const area = container.querySelector('#anomaly-area');
    area.innerHTML = loadingHTML('Evaluating anomalies…');
    try {
      const result = await api.evaluateAnomalies();
      renderEvaluationResult(area, result);
    } catch (e) { area.innerHTML = errorHTML('Evaluation failed', e.message); }
    finally { detectBtn.disabled = false; evalBtn.disabled = false; evalBtn.innerHTML = '📊 Evaluate (with metrics)'; }
  });
}

// =====================================================================
// 10. EXPORTS
// =====================================================================
export async function renderExports(container) {
  render(container, `
    <div class="page-header"><h1>Data Exports</h1>
      <p>Download all 15 database tables and the five ground-truth labels.</p>
    </div>
    <div class="panel">
      <div class="panel-header"><h2>Download project data</h2></div>
      <div class="panel-body">
        <p>Each archive contains the table exports in the selected format and
          the corresponding <code>ground_truth</code> file.</p>
        <div class="search-bar">
          <button class="btn btn-primary" id="download-csv">Download CSV archive</button>
          <button class="btn btn-secondary" id="download-json">Download JSON archive</button>
        </div>
        <div id="export-status" role="status" aria-live="polite"></div>
      </div>
    </div>
  `);

  const status = container.querySelector('#export-status');
  for (const [format, buttonId] of [
    ['csv', '#download-csv'],
    ['json', '#download-json'],
  ]) {
    const button = container.querySelector(buttonId);
    button?.addEventListener('click', async () => {
      if (button.disabled) return;
      button.disabled = true;
      status.textContent = `Preparing ${format.toUpperCase()} download…`;
      try {
        await api.downloadExport(format);
        status.textContent = `${format.toUpperCase()} archive download started.`;
      } catch (error) {
        status.innerHTML = errorHTML(
          `Failed to download ${format.toUpperCase()} export`,
          error.message,
        );
      } finally {
        button.disabled = false;
      }
    });
  }
}

function renderDetectedIssues(area, issues) {
  if (!issues.length) {
    area.innerHTML = `<div style="padding:20px;text-align:center;color:var(--success);font-weight:600;">
      ✅ No anomalies detected — all records are clean.</div>`;
    return;
  }
  // Count by severity
  const bySeverity = {};
  const byType = {};
  issues.forEach(i => {
    bySeverity[i.severity] = (bySeverity[i.severity] || 0) + 1;
    byType[i.issue_type] = (byType[i.issue_type] || 0) + 1;
  });

  area.innerHTML = `
    <div class="cards-grid" style="margin-bottom:20px;">
      ${card('Total Detected', issues.length, '', 'danger')}
      ${Object.entries(bySeverity).map(([sev, cnt]) =>
        card(sev, cnt, '', sev === 'CRITICAL' ? 'danger' : sev === 'HIGH' ? 'warning' : 'info')).join('')}
    </div>
    <div class="table-wrapper"><table>
      <thead><tr><th>Issue ID</th><th>Type</th><th>Severity</th><th>Entity</th><th>Expected</th><th>Actual</th><th>Difference</th><th>Message</th></tr></thead>
      <tbody>${issues.map(i => `<tr>
        <td>${escapeHTML(i.issue_id)}</td>
        <td>${escapeHTML(i.issue_type)}</td>
        <td><span class="severity-${i.severity.toLowerCase()}">${i.severity}</span></td>
        <td>${escapeHTML(i.entity_type)} #${i.entity_id}</td>
        <td class="amount">${i.expected_value != null ? formatNumber(i.expected_value) : '—'}</td>
        <td class="amount">${i.actual_value != null ? formatNumber(i.actual_value) : '—'}</td>
        <td class="amount">${i.difference != null ? formatNumber(i.difference) : '—'}</td>
        <td style="max-width:300px;word-break:break-word;">${escapeHTML(i.message)}</td>
      </tr>`).join('')}</tbody>
    </table></div>
  `;
}

function renderEvaluationResult(area, result) {
  const precClass = result.precision >= 0.8 ? 'metric-good' : result.precision >= 0.5 ? 'metric-warn' : 'metric-bad';
  const recClass = result.recall >= 0.8 ? 'metric-good' : result.recall >= 0.5 ? 'metric-warn' : 'metric-bad';
  const f1Class = result.f1_score >= 0.8 ? 'metric-good' : result.f1_score >= 0.5 ? 'metric-warn' : 'metric-bad';

  area.innerHTML = `
    <h3 style="margin-bottom:14px;">Evaluation Metrics</h3>
    <div class="metrics-row">
      <div class="metric-box ${precClass}"><div class="metric-value">${(result.precision * 100).toFixed(1)}%</div><div class="metric-label">Precision</div></div>
      <div class="metric-box ${recClass}"><div class="metric-value">${(result.recall * 100).toFixed(1)}%</div><div class="metric-label">Recall</div></div>
      <div class="metric-box ${f1Class}"><div class="metric-value">${(result.f1_score * 100).toFixed(1)}%</div><div class="metric-label">F1 Score</div></div>
      <div class="metric-box"><div class="metric-value">${result.true_positives}</div><div class="metric-label">True Positives</div></div>
      <div class="metric-box"><div class="metric-value">${result.false_positives}</div><div class="metric-label">False Positives</div></div>
      <div class="metric-box"><div class="metric-value">${result.false_negatives}</div><div class="metric-label">False Negatives</div></div>
    </div>
    <div class="cards-grid" style="margin-bottom:20px;">
      ${card('Detected', result.detected_count, '', 'info')}
      ${card('Ground Truth', result.ground_truth_count, '', '')}
    </div>

    ${result.per_type && Object.keys(result.per_type).length ? `
    <h3 style="margin:16px 0 10px;">Per-Type Breakdown</h3>
    <div class="table-wrapper"><table>
      <thead><tr><th>Issue Type</th><th>Ground Truth</th><th>Detected</th><th>TP</th><th>FP</th><th>FN</th></tr></thead>
      <tbody>${Object.entries(result.per_type).map(([type, v]) => `<tr>
        <td>${escapeHTML(type)}</td><td>${v.gt_count}</td><td>${v.detected_count}</td>
        <td>${v.tp}</td><td>${v.fp}</td><td>${v.fn}</td>
      </tr>`).join('')}</tbody>
    </table></div>` : ''}
  `;
}

/**
 * utils.js — Formatting, DOM helpers, and shared utilities.
 */

/** Format paise as Indian Rupee string (₹1,23,456.78) */
export function formatINR(paise) {
  if (paise == null || isNaN(paise)) return '₹0.00';
  const rupees = Number(paise) / 100;
  return '₹' + rupees.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Format INR value directly (already in rupees) */
export function formatINRValue(rupees) {
  if (rupees == null || isNaN(rupees)) return '₹0.00';
  return '₹' + Number(rupees).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Format a plain number with Indian grouping */
export function formatNumber(n) {
  if (n == null || isNaN(n)) return '0';
  return Number(n).toLocaleString('en-IN');
}

/** Format a date string for display */
export function formatDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d)) return dateStr;
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

/** Capitalize first letter */
export function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Return a badge class based on status */
export function statusBadgeClass(status) {
  if (!status) return 'badge-neutral';
  const s = status.toLowerCase();
  if (['active', 'cleared', 'paid', 'processed', 'disbursed', 'approved', 'enrolled', 'completed'].includes(s))
    return 'badge-success';
  if (['pending', 'partially_paid', 'deferred', 'issued'].includes(s))
    return 'badge-warning';
  if (['failed', 'cancelled', 'suspended', 'withdrawn', 'rejected', 'inactive', 'refunded'].includes(s))
    return 'badge-danger';
  return 'badge-info';
}

/** Create an HTML element from a template string */
export function html(strings, ...values) {
  return strings.reduce((result, str, i) =>
    result + str + (values[i] != null ? values[i] : ''), '');
}

/** Set innerHTML safely */
export function render(container, content) {
  if (typeof container === 'string') {
    container = document.querySelector(container);
  }
  if (container) container.innerHTML = content;
}

/** Loading spinner HTML */
export function loadingHTML(message = 'Loading...') {
  return `<div class="loading-container"><div class="spinner"></div><p>${message}</p></div>`;
}

/** Empty state HTML */
export function emptyHTML(message = 'No data found', icon = '📭') {
  return `<div class="empty-state"><span class="empty-icon">${icon}</span><p>${message}</p></div>`;
}

/** Error state HTML */
export function errorHTML(message = 'Something went wrong', detail = '') {
  return `<div class="error-state"><span class="error-icon">⚠️</span><p>${message}</p>${detail ? `<p class="error-detail">${detail}</p>` : ''}</div>`;
}

/** Debounce helper */
export function debounce(fn, delay = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/** Pagination info text */
export function paginationInfo(page, pageSize, total) {
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return `Showing ${start}–${end} of ${formatNumber(total)}`;
}

/** Pagination controls HTML */
export function paginationHTML(page, pageSize, total) {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return '';
  return `
    <div class="pagination">
      <span>${paginationInfo(page, pageSize, total)}</span>
      <div class="pagination-controls">
        <button class="btn btn-secondary btn-sm" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>← Prev</button>
        <span style="padding:5px 8px;font-weight:600;">Page ${page} / ${totalPages}</span>
        <button class="btn btn-secondary btn-sm" data-page="${page + 1}" ${page >= totalPages ? 'disabled' : ''}>Next →</button>
      </div>
    </div>`;
}

/** Escape HTML */
export function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * app.js — Main entry point. Router, sidebar, health check.
 */
import { checkHealth } from './api.js';
import {
  renderDashboard,
  renderStudents,
  renderStudentDetail,
  renderPrograms,
  renderInvoices,
  renderScholarships,
  renderPayments,
  renderRefunds,
  renderReconciliation,
  renderAnomalies,
  renderExports,
} from './components.js';

const pages = {
  dashboard:      renderDashboard,
  students:       renderStudents,
  programs:       renderPrograms,
  invoices:       renderInvoices,
  scholarships:   renderScholarships,
  payments:       renderPayments,
  refunds:        renderRefunds,
  reconciliation: renderReconciliation,
  anomalies:      renderAnomalies,
  exports:        renderExports,
};

let currentPage = 'dashboard';

function getPageContainer() {
  return document.getElementById('page-content');
}

// ---- Routing ----
function navigateTo(page) {
  if (!pages[page]) page = 'dashboard';
  history.replaceState(null, '', `#${page}`);
  renderRouteFromHash();
}

function renderRouteFromHash() {
  const hash = window.location.hash.slice(1);
  const studentDetailMatch = hash.match(/^students\/(\d+)$/);
  const page = studentDetailMatch
    ? 'students'
    : (pages[hash] ? hash : 'dashboard');
  currentPage = page;

  // Update nav active state
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.page === page);
  });

  // Close mobile sidebar
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('sidebar-overlay')?.classList.remove('show');

  // Render page
  const container = getPageContainer();
  if (studentDetailMatch) {
    renderStudentDetail(container, Number(studentDetailMatch[1]));
  } else {
    pages[page](container);
    if (!pages[hash]) {
      history.replaceState(null, '', `#${page}`);
    }
  }
}

// ---- Health Check ----
async function updateHealthStatus() {
  const el = document.getElementById('api-status');
  if (!el) return;
  try {
    const ok = await checkHealth();
    if (ok) {
      el.textContent = '● API Online';
      el.className = 'api-status online';
    } else {
      throw new Error();
    }
  } catch {
    el.textContent = '● API Offline';
    el.className = 'api-status offline';
  }
}

// ---- Mobile sidebar ----
function setupMobileSidebar() {
  // Add mobile header before main content
  const app = document.getElementById('app');
  const mobileHeader = document.createElement('div');
  mobileHeader.className = 'mobile-header';
  mobileHeader.innerHTML = '<button id="mobile-menu-btn">☰</button><h2>💰 Student Finance</h2>';
  app.insertBefore(mobileHeader, app.firstChild);

  // Add overlay
  const overlay = document.createElement('div');
  overlay.id = 'sidebar-overlay';
  overlay.className = 'sidebar-overlay';
  app.appendChild(overlay);

  // Toggle events
  document.getElementById('mobile-menu-btn')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.add('open');
    overlay.classList.add('show');
  });
  overlay.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.remove('open');
    overlay.classList.remove('show');
  });
}

// ---- Init ----
function init() {
  // Nav link clicks
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo(link.dataset.page);
    });
  });

  // Hash changes (back/forward)
  window.addEventListener('hashchange', () => {
    renderRouteFromHash();
  });

  setupMobileSidebar();
  updateHealthStatus();
  setInterval(updateHealthStatus, 30000);

  // Navigate to initial page
  renderRouteFromHash();
}

document.addEventListener('DOMContentLoaded', init);

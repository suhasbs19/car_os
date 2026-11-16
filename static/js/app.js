/* app.js – CAR OS global JavaScript utilities */

// ── Flash message auto-dismiss ────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const flashMsgs = document.querySelectorAll('.flash-msg');
  flashMsgs.forEach(function (msg) {
    // Auto-dismiss after 4 seconds
    setTimeout(function () {
      msg.style.opacity = '0';
      msg.style.transform = 'translateX(20px)';
      msg.style.transition = 'all 0.4s ease';
      setTimeout(function () { msg.remove(); }, 400);
    }, 4000);

    // Click to dismiss
    msg.addEventListener('click', function () {
      msg.style.opacity = '0';
      setTimeout(function () { msg.remove(); }, 300);
    });
  });
});

// ── Confirm delete modal ──────────────────────────────────────
function openDeleteModal(formId, itemName) {
  const modal = document.getElementById('delete-modal');
  const nameEl = document.getElementById('delete-item-name');
  const formEl = document.getElementById('delete-modal-form');

  if (nameEl) nameEl.textContent = itemName || 'this item';
  if (formEl) {
    const source = document.getElementById(formId);
    if (source) {
      formEl.action = source.action;
    }
  }
  if (modal) modal.classList.add('open');
}

function closeDeleteModal() {
  const modal = document.getElementById('delete-modal');
  if (modal) modal.classList.remove('open');
}

// Close modal on backdrop click
document.addEventListener('DOMContentLoaded', function () {
  const modal = document.getElementById('delete-modal');
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeDeleteModal();
    });
  }
});

// ── Health bar animation ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const healthBars = document.querySelectorAll('.health-bar[data-width]');
  healthBars.forEach(function (bar) {
    const w = parseFloat(bar.dataset.width) || 0;
    setTimeout(function () {
      bar.style.width = Math.min(w, 100) + '%';
    }, 100);
  });
});

// ── Search input with debounce ────────────────────────────────
function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

// ── Format currency (₹) ──────────────────────────────────────
function formatINR(value) {
  if (value === null || value === undefined) return 'N/A';
  const v = parseFloat(value);
  if (isNaN(v)) return 'N/A';
  if (v >= 1e5) return '₹' + (v / 1e5).toFixed(2) + 'L';
  if (v >= 1000) return '₹' + (v / 1000).toFixed(1) + 'K';
  return '₹' + v.toFixed(0);
}

// ── Active nav highlight ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
  const navLinks = document.querySelectorAll('.nav-item[data-path]');
  navLinks.forEach(function (link) {
    const path = link.dataset.path;
    if (path && (currentPath === path || currentPath.startsWith(path + '/') ||
        (path === '/dashboard' && currentPath === ''))) {
      link.classList.add('active');
    }
  });
});

// ── Tooltip (title attribute fallback) ───────────────────────
// Uses native title attribute for now; upgrade to custom tooltips later

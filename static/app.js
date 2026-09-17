// --- helpers -----------------------------------------------------------
async function getJSON(url) {
  const res = await fetch(url);
  return { ok: res.ok, status: res.status, data: await res.json() };
}
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return { ok: res.ok, status: res.status, data: await res.json() };
}
function fmt(dtStr) {
  const d = new Date(dtStr);
  return d.toLocaleString();
}

function renderAppointmentsTable(container, items, { showCancel } = { showCancel: true }) {
  if (!items.length) {
    container.innerHTML = '<p class="muted">No appointments found.</p>';
    return;
  }
  const rows = items.map(a => `
    <tr data-id="${a.id}">
      <td>${a.patient_name}</td>
      <td>${a.doctor_name}</td>
      <td>${fmt(a.start_time)}</td>
      <td>${fmt(a.end_time)}</td>
      <td>
        <span class="badge ${a.status}">${a.status}</span>
        ${a.status === 'cancelled' && a.late_fee_applied ? `<span class="badge fee">late fee: ${a.fee_amount}</span>` : ''}
        ${a.status === 'cancelled' && !a.late_fee_applied ? `<span class="badge ok">no fee</span>` : ''}
      </td>
      <td class="actions">
        ${a.status === 'booked' ? `
          <button class="btn btn-small reschedule-btn" data-id="${a.id}">Reschedule</button>
          <button class="btn btn-small complete-btn" data-id="${a.id}">Complete</button>
          ${showCancel ? `<button class="btn btn-small cancel-btn" data-id="${a.id}">Cancel</button>` : ''}
        ` : ''}
      </td>
    </tr>`).join('');

  container.innerHTML = `
    <table class="table">
      <thead><tr><th>Patient</th><th>Doctor</th><th>Start</th><th>End</th><th>Status</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;

  const reloadOwningPanel = () => {
    if (container.id === 'd-results') loadDoctorDay();
    if (container.id === 's-results') runSearch();
  };

  container.querySelectorAll('.cancel-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Cancel this appointment?')) return;
      const { ok, data } = await postJSON(`/api/appointments/${btn.dataset.id}/cancel`, {});
      if (ok) {
        alert(data.late_fee_applied
          ? `Cancelled. Late cancellation fee applied: ${data.fee_amount}`
          : 'Cancelled. No fee (cancelled in good time).');
        reloadOwningPanel();
      } else {
        alert(data.error || 'Could not cancel.');
      }
    });
  });

  container.querySelectorAll('.complete-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const { ok, data } = await postJSON(`/api/appointments/${btn.dataset.id}/complete`, {});
      if (ok) { reloadOwningPanel(); } else { alert(data.error || 'Could not mark complete.'); }
    });
  });

  container.querySelectorAll('.reschedule-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const newStart = prompt('New start time (YYYY-MM-DDTHH:MM), e.g. 2026-10-01T14:30');
      if (!newStart) return;
      const { ok, data } = await postJSON(`/api/appointments/${btn.dataset.id}/reschedule`, { start_time: newStart });
      if (ok) { reloadOwningPanel(); } else { alert(data.error || 'Could not reschedule.'); }
    });
  });
}

function renderPagination(container, meta, onPage) {
  if (meta.pages <= 1) { container.innerHTML = ''; return; }
  let html = '';
  for (let p = 1; p <= meta.pages; p++) {
    html += `<button class="page-btn ${p === meta.page ? 'active' : ''}" data-page="${p}">${p}</button>`;
  }
  container.innerHTML = html;
  container.querySelectorAll('.page-btn').forEach(btn => {
    btn.addEventListener('click', () => onPage(parseInt(btn.dataset.page, 10)));
  });
}

// --- doctors dropdowns ---------------------------------------------------
async function loadDoctorsInto(selectEl) {
  const { data } = await getJSON('/api/doctors');
  selectEl.innerHTML = data.map(d => `<option value="${d.id}">${d.name}${d.specialization ? ' — ' + d.specialization : ''}</option>`).join('');
}

// --- booking ---------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  const bDoctor = document.getElementById('b-doctor');
  const dDoctor = document.getElementById('d-doctor');
  if (bDoctor) loadDoctorsInto(bDoctor);
  if (dDoctor) loadDoctorsInto(dDoctor).then(loadDoctorDay);

  const bookForm = document.getElementById('book-form');
  if (bookForm) {
    bookForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = document.getElementById('book-msg');
      const payload = {
        doctor_id: parseInt(document.getElementById('b-doctor').value, 10),
        patient_name: document.getElementById('b-patient-name').value,
        patient_phone: document.getElementById('b-patient-phone').value,
        start_time: document.getElementById('b-start').value,
        duration_minutes: parseInt(document.getElementById('b-duration').value, 10),
      };
      const { ok, data } = await postJSON('/api/appointments', payload);
      if (ok) {
        msg.textContent = 'Booked successfully.';
        msg.className = 'msg ok';
        bookForm.reset();
        loadDoctorDay();
      } else {
        msg.textContent = data.error || 'Could not book.';
        msg.className = 'msg error';
      }
    });
  }

  const dLoad = document.getElementById('d-load');
  if (dLoad) dLoad.addEventListener('click', () => loadDoctorDay(1));

  const sLoad = document.getElementById('s-load');
  if (sLoad) sLoad.addEventListener('click', () => runSearch(1));

  const clockSetBtn = document.getElementById('clock-set-btn');
  if (clockSetBtn) {
    clockSetBtn.addEventListener('click', async () => {
      const val = document.getElementById('clock-set').value;
      if (!val) return;
      const { data } = await postJSON('/clock', { now: val });
      updateClockDisplay(data.current_time);
      loadOutbox();
      loadDoctorDay();
    });
  }
  const clockAdvanceBtn = document.getElementById('clock-advance-btn');
  if (clockAdvanceBtn) {
    clockAdvanceBtn.addEventListener('click', async () => {
      const { data } = await postJSON('/clock', { advance_minutes: 45 });
      updateClockDisplay(data.current_time);
      loadOutbox();
      loadDoctorDay();
    });
  }
  const outboxRefreshBtn = document.getElementById('outbox-refresh-btn');
  if (outboxRefreshBtn) outboxRefreshBtn.addEventListener('click', loadOutbox);
  if (document.getElementById('outbox-results')) loadOutbox();
});

function updateClockDisplay(iso) {
  const el = document.getElementById('clock-display');
  if (el) el.textContent = iso ? fmt(iso) : 'real time (not overridden yet)';
}

async function loadOutbox() {
  const container = document.getElementById('outbox-results');
  if (!container) return;
  const { data } = await getJSON('/outbox');
  if (!data.length) {
    container.innerHTML = '<p class="muted">No notifications sent yet.</p>';
    return;
  }
  container.innerHTML = `
    <table class="table">
      <thead><tr><th>Patient</th><th>Message</th><th>Sent at</th></tr></thead>
      <tbody>${data.map(n => `<tr><td>${n.patient_name}</td><td>${n.message}</td><td>${fmt(n.created_at)}</td></tr>`).join('')}</tbody>
    </table>`;
}

let dCurrentPage = 1;
async function loadDoctorDay(page) {
  if (page) dCurrentPage = page;
  const doctorId = document.getElementById('d-doctor').value;
  if (!doctorId) return;
  const date = document.getElementById('d-date').value;
  const sort = document.getElementById('d-sort').value;
  const params = new URLSearchParams({ page: dCurrentPage, per_page: 10, sort });
  if (date) params.set('date', date);
  const { data } = await getJSON(`/api/doctors/${doctorId}/appointments?${params}`);
  renderAppointmentsTable(document.getElementById('d-results'), data.items);
  renderPagination(document.getElementById('d-pagination'), data, loadDoctorDay);
}

let sCurrentPage = 1;
async function runSearch(page) {
  if (page) sCurrentPage = page;
  const name = document.getElementById('s-name').value;
  const params = new URLSearchParams({ page: sCurrentPage, per_page: 10, patient: name });
  const { data } = await getJSON(`/api/appointments/search?${params}`);
  renderAppointmentsTable(document.getElementById('s-results'), data.items);
  renderPagination(document.getElementById('s-pagination'), data, runSearch);
}

// Dashboard logic. All DOM is built with textContent / createElement,
// so data from the server can never be interpreted as HTML.

const $ = id => document.getElementById(id);

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) el.append(kid instanceof Node ? kid : document.createTextNode(kid ?? ''));
  return el;
}

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (res.status === 401) { location.href = '/login'; throw new Error('Please sign in again'); }
  const isJson = (res.headers.get('content-type') || '').includes('application/json');
  const data = isJson ? await res.json() : {};
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// The database stores UTC (SQLite CURRENT_TIMESTAMP); show it in the viewer's own time zone.
function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(ts.replace(' ', 'T') + 'Z');
  return isNaN(d) ? ts : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'medium' });
}

function show(id, text, ok) {
  const el = $(id);
  el.textContent = text;
  el.className = 'msg ' + (ok ? 'ok' : 'err');
}

function fillRows(tbody, rows, colSpan, emptyText) {
  tbody.replaceChildren();
  if (!rows.length) {
    tbody.append(h('tr', {}, h('td', { class: 'empty', colspan: colSpan }, emptyText)));
    return;
  }
  rows.forEach(r => tbody.append(r));
}

async function refreshStats() {
  const s = await api('/api/stats');
  $('statLinks').textContent = s.links;
  $('statClicks').textContent = s.clicks;
  $('statRecords').textContent = s.records;
  $('statMessages').textContent = s.messages;
}

// ---------- Tabs ----------
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === btn.dataset.tab));
    refreshStats().catch(() => {});
  });
});

$('logoutBtn').addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' });
  location.href = '/login';
});

// ---------- URL shortener ----------
async function loadUrls() {
  const { urls } = await api('/api/urls');
  const rows = urls.map(u => h('tr', {},
    h('td', {}, h('a', { href: u.short_url, target: '_blank', rel: 'noopener' }, u.short_url)),
    h('td', { class: 'clip', title: u.original_url }, u.original_url),
    h('td', {}, String(u.clicks)),
    h('td', { class: 'nowrap' }, fmtTime(u.created_at)),
    h('td', {},
      h('button', { class: 'secondary small', onclick: () => showStats(u.short_code) }, 'Stats'), ' ',
      h('button', { class: 'danger small', onclick: () => removeUrl(u.short_code) }, 'Delete'))));
  fillRows($('urlRows'), rows, 5, 'No links yet. Create one above.');
}

async function showStats(code) {
  try {
    const s = await api(`/api/urls/${encodeURIComponent(code)}/stats`);
    $('statsCard').hidden = false;
    $('statsTitle').textContent = `Click analytics for /${s.short_code} (${s.total_clicks} total)`;
    fillRows($('statsDays'), s.by_day.map(d => h('tr', {}, h('td', {}, d.day), h('td', {}, String(d.clicks)))),
      2, 'No clicks yet.');
    fillRows($('statsRecent'), s.recent.map(c => h('tr', {},
      h('td', { class: 'nowrap' }, fmtTime(c.clicked_at)),
      h('td', { class: 'clip', title: c.user_agent }, c.referrer || '(direct)'))),
      2, 'No clicks yet.');
    // Keep the table and the summary tiles consistent with the numbers shown here.
    await Promise.all([loadUrls(), refreshStats()]);
  } catch (err) { show('urlMsg', err.message, false); }
}

async function removeUrl(code) {
  if (!confirm(`Delete /${code}? Its click history will be removed too.`)) return;
  try {
    await api(`/api/urls/${encodeURIComponent(code)}`, { method: 'DELETE' });
    $('statsCard').hidden = true;
    await Promise.all([loadUrls(), refreshStats()]);
  } catch (err) { show('urlMsg', err.message, false); }
}

$('shortenForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const data = await api('/api/shorten', {
      method: 'POST',
      body: JSON.stringify({
        url: $('longUrl').value,
        custom_alias: $('customAlias').value,
        mode: $('codeMode').value
      })
    });
    show('urlMsg', `Created ${data.short_url}`, true);
    $('longUrl').value = '';
    $('customAlias').value = '';
    await Promise.all([loadUrls(), refreshStats()]);
  } catch (err) { show('urlMsg', err.message, false); }
});

// ---------- Fake data ----------
let FIELD_LABELS = {};                       // key -> label, loaded from /api/fake-data/fields

const fieldBoxes = () => [...document.querySelectorAll('#fakeFields input')];
const pickedFields = () => fieldBoxes().filter(b => b.checked).map(b => b.value);

function updateFieldCount() {
  $('fieldCount').textContent = `(${pickedFields().length} of ${fieldBoxes().length} selected)`;
}

function setAllFields(on) {
  fieldBoxes().forEach(b => { b.checked = on; });
  updateFieldCount();
}

// Draw one checkbox per field the server offers (the server is the single source of truth).
const fieldsReady = (async () => {
  const catalog = await api('/api/fake-data/fields');
  catalog.fields.forEach(f => { FIELD_LABELS[f.key] = f.label; });
  $('fakeFields').replaceChildren(...catalog.fields.map(f =>
    h('label', { class: 'check' },
      h('input', { type: 'checkbox', value: f.key, checked: true, onchange: updateFieldCount }),
      f.label)));
  updateFieldCount();
})();

$('fieldsAll').addEventListener('click', () => setAllFields(true));
$('fieldsNone').addEventListener('click', () => setAllFields(false));

async function loadFake() {
  await fieldsReady;
  const data = await api('/api/fake-data');       // only the columns that hold data
  $('fakeHead').replaceChildren(...data.fields.map(f => h('th', {}, FIELD_LABELS[f] || f)));
  $('fakeTotal').textContent = `(${data.total} total)`;
  const cellClass = { birthdate: 'nowrap', mobile_number: 'nowrap', zip_code: 'nowrap', address: 'addr' };
  const rows = data.records.map(r => h('tr', {},
    data.fields.map(f => h('td', { class: cellClass[f] || '' }, String(r[f] ?? '')))));
  fillRows($('fakeRows'), rows, Math.max(1, data.fields.length), 'No records yet. Generate some above.');
}

$('fakeForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    await fieldsReady;
    const data = await api('/api/fake-data/generate', {
      method: 'POST',
      body: JSON.stringify({
        count: Number($('fakeCount').value), locale: $('fakeLocale').value, fields: pickedFields()
      })
    });
    show('fakeMsg', `Generated and saved ${data.count} records with ${data.fields.length} field(s) (batch ${data.batch_id}).`, true);
    await Promise.all([loadFake(), refreshStats()]);
  } catch (err) { show('fakeMsg', err.message, false); }
});

$('clearFake').addEventListener('click', async () => {
  if (!confirm('Delete all of your stored fake records?')) return;
  try {
    const data = await api('/api/fake-data', { method: 'DELETE' });
    show('fakeMsg', `Deleted ${data.deleted} records.`, true);
    await Promise.all([loadFake(), refreshStats()]);
  } catch (err) { show('fakeMsg', err.message, false); }
});

// ---------- Messaging ----------
function updateCounter() {
  const n = $('smsBody').value.length;
  const segs = n <= 160 ? 1 : Math.ceil(n / 153);
  $('smsCounter').textContent = `${n} characters · ${segs} segment${segs > 1 ? 's' : ''}`;
}
$('smsBody').addEventListener('input', updateCounter);

async function loadLog() {
  const status = $('statusFilter').value;
  const { messages } = await api('/api/messages' + (status ? `?status=${encodeURIComponent(status)}` : ''));
  const rows = messages.map(m => h('tr', {},
    h('td', {}, String(m.id)),
    h('td', { class: 'nowrap' }, m.recipient),
    h('td', { class: 'clip', title: m.message_body }, m.message_body),
    h('td', {}, String(m.segments)),
    h('td', {}, h('span', { class: 'badge ' + m.status }, m.status)),
    h('td', { class: 'nowrap' }, fmtTime(m.queued_at)),
    h('td', { class: 'nowrap' }, fmtTime(m.finished_at)),
    h('td', {}, m.failure_reason || '')));
  fillRows($('logRows'), rows, 8, 'No messages yet.');
}

$('smsForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const data = await api('/api/messages/send', {
      method: 'POST',
      body: JSON.stringify({ recipient: $('smsTo').value, message: $('smsBody').value })
    });
    const ok = data.status === 'delivered';
    show('smsMsg', ok ? `Delivered to ${data.recipient}` : `Failed: ${data.failure_reason}`, ok);
    await Promise.all([loadLog(), refreshStats()]);
  } catch (err) { show('smsMsg', err.message, false); }
});

$('bulkForm').addEventListener('submit', async e => {
  e.preventDefault();
  try {
    const d = await api('/api/messages/bulk', { method: 'POST', body: JSON.stringify({ message: $('bulkBody').value }) });
    show('bulkMsg', `${d.attempted} sent: ${d.delivered} delivered, ${d.failed} failed` +
      (d.skipped ? `, ${d.skipped} skipped (invalid number)` : ''), true);
    await Promise.all([loadLog(), refreshStats()]);
  } catch (err) { show('bulkMsg', err.message, false); }
});

$('statusFilter').addEventListener('change', () => loadLog().catch(() => {}));
$('refreshLog').addEventListener('click', () => loadLog().catch(() => {}));

// ---------- Initial load ----------
Promise.all([refreshStats(), loadUrls(), loadFake(), loadLog()]).catch(() => {});

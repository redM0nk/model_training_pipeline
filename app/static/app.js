const state = {
  customer: null,
  location: null,
  conveyor: null,
  dates: [],
  selected: new Set(),
};

const $ = (sel) => document.querySelector(sel);
const lists = {
  customers: $('[data-list="customers"]'),
  locations: $('[data-list="locations"]'),
  conveyors: $('[data-list="conveyors"]'),
  dates:     $('[data-list="dates"]'),
};

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function setLoading(ul) {
  ul.innerHTML = '<li class="disabled">Loading…</li>';
}

function clear(ul) { ul.innerHTML = ''; }

function renderSimpleList(ul, items, onClick, selected) {
  clear(ul);
  if (!items.length) {
    ul.innerHTML = '<li class="disabled">— empty —</li>';
    return;
  }
  for (const name of items) {
    const li = document.createElement('li');
    li.textContent = name;
    if (selected === name) li.classList.add('selected');
    li.onclick = () => onClick(name);
    ul.appendChild(li);
  }
}

async function loadCustomers() {
  setLoading(lists.customers);
  const items = await fetchJSON('/api/customers');
  renderSimpleList(lists.customers, items, selectCustomer, state.customer);
}

async function selectCustomer(name) {
  state.customer = name; state.location = null;
  state.conveyor = null; state.dates = []; state.selected.clear();
  renderSimpleList(lists.customers, [...lists.customers.querySelectorAll('li')]
    .map(li => li.textContent), selectCustomer, name);
  clear(lists.conveyors); clear(lists.dates); updateQueueButton();
  setLoading(lists.locations);
  const items = await fetchJSON(`/api/locations?customer=${encodeURIComponent(name)}`);
  renderSimpleList(lists.locations, items, selectLocation, null);
}

async function selectLocation(name) {
  state.location = name; state.conveyor = null;
  state.dates = []; state.selected.clear();
  renderSimpleList(lists.locations, [...lists.locations.querySelectorAll('li')]
    .map(li => li.textContent), selectLocation, name);
  clear(lists.dates); updateQueueButton();
  setLoading(lists.conveyors);
  const items = await fetchJSON(
    `/api/conveyors?customer=${encodeURIComponent(state.customer)}&location=${encodeURIComponent(name)}`);
  renderSimpleList(lists.conveyors, items, selectConveyor, null);
}

async function selectConveyor(name) {
  state.conveyor = name; state.selected.clear();
  renderSimpleList(lists.conveyors, [...lists.conveyors.querySelectorAll('li')]
    .map(li => li.textContent), selectConveyor, name);
  setLoading(lists.dates);
  const items = await fetchJSON(
    `/api/dates?customer=${encodeURIComponent(state.customer)}` +
    `&location=${encodeURIComponent(state.location)}` +
    `&conveyor=${encodeURIComponent(name)}`);
  state.dates = items;
  renderDates();
}

function renderDates() {
  clear(lists.dates);
  if (!state.dates.length) {
    lists.dates.innerHTML = '<li class="disabled">— no dates —</li>';
    updateQueueButton();
    return;
  }
  for (const d of state.dates) {
    const li = document.createElement('li');
    let dotCls = 'novids';
    let label = 'no videos';
    if (d.has_videos && d.has_images) { dotCls = 'done'; label = 'extracted'; }
    else if (d.ready) { dotCls = 'ready'; label = 'ready'; }

    const left = document.createElement('label');
    left.style.display = 'flex'; left.style.alignItems = 'center'; left.style.gap = '8px';
    left.style.flex = '1'; left.style.cursor = 'pointer';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.disabled = !d.has_videos;
    cb.checked = state.selected.has(d.date);
    cb.onchange = () => {
      if (cb.checked) state.selected.add(d.date);
      else state.selected.delete(d.date);
      updateQueueButton();
    };

    const dot = document.createElement('span');
    dot.className = `dot ${dotCls}`;
    dot.style.margin = '0';

    left.appendChild(cb);
    left.appendChild(dot);
    left.appendChild(document.createTextNode(d.date));
    li.appendChild(left);

    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = label;
    li.appendChild(meta);

    lists.dates.appendChild(li);
  }
  updateQueueButton();
}

function updateQueueButton() {
  $('#queue-btn').disabled =
    !(state.customer && state.location && state.conveyor && state.selected.size);
}

$('#queue-btn').onclick = async () => {
  const body = {
    customer: state.customer,
    location: state.location,
    conveyor: state.conveyor,
    dates: [...state.selected],
  };
  await fetchJSON('/api/queue', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  state.selected.clear();
  renderDates();
  refreshQueue();
};

async function refreshQueue() {
  const jobs = await fetchJSON('/api/queue');
  const tbody = $('#queue-body');
  tbody.innerHTML = '';
  jobs.sort((a, b) => b.created_at - a.created_at);
  for (const j of jobs) {
    const tr = document.createElement('tr');
    const created = new Date(j.created_at * 1000).toLocaleString();
    tr.innerHTML = `
      <td class="status-${j.status}">${j.status}</td>
      <td>${j.customer}</td>
      <td>${j.location}</td>
      <td>${j.conveyor}</td>
      <td>${j.recording_date}</td>
      <td>${created}</td>
      <td></td>`;
    if (j.status === 'pending') {
      const btn = document.createElement('button');
      btn.className = 'cancel';
      btn.textContent = 'cancel';
      btn.onclick = async () => {
        await fetchJSON(`/api/queue/${j.id}/cancel`, {method: 'POST'});
        refreshQueue();
      };
      tr.lastElementChild.appendChild(btn);
    }
    tbody.appendChild(tr);
  }
}

async function refreshTmux() {
  try {
    const s = await fetchJSON('/api/tmux/status');
    const el = $('#tmux-status');
    el.textContent = `tmux ${s.target}: ${s.current_command} ${s.idle ? '(idle)' : '(busy)'}`;
    el.className = 'pill ' + (s.idle ? 'idle' : 'busy');
  } catch (e) {
    $('#tmux-status').textContent = 'tmux: error';
  }
}

loadCustomers();
refreshQueue();
refreshTmux();
setInterval(refreshQueue, 5000);
setInterval(refreshTmux, 5000);

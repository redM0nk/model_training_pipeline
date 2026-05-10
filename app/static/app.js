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

function formatGB(bytes) {
  const gb = (bytes || 0) / (1024 ** 3);
  return `${gb.toFixed(2)} GB`;
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

    const top = document.createElement('div');
    top.className = 'date-top';

    const left = document.createElement('label');
    left.className = 'date-left';

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
    top.appendChild(left);

    const metaTop = document.createElement('span');
    metaTop.className = 'meta';
    metaTop.textContent = label;
    top.appendChild(metaTop);

    li.appendChild(top);

    const stats = document.createElement('div');
    stats.className = 'date-stats';

    const vidSpan = document.createElement('span');
    if (d.has_videos) {
      vidSpan.className = 'stat-link';
      vidSpan.textContent = `${d.video_file_count} video${d.video_file_count === 1 ? '' : 's'} · ${formatGB(d.video_total_size)}`;
      vidSpan.title = 'Click to preview videos';
      vidSpan.onclick = (e) => { e.stopPropagation(); openVideoModal(d.date); };
    } else {
      vidSpan.textContent = 'no videos';
    }
    stats.appendChild(vidSpan);

    stats.appendChild(document.createTextNode('    '));

    const imgSpan = document.createElement('span');
    imgSpan.textContent = d.has_images
      ? `${d.image_folder_count} image folder${d.image_folder_count === 1 ? '' : 's'}`
      : 'no images';
    stats.appendChild(imgSpan);

    li.appendChild(stats);

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

function videoErrorMessage(video) {
  const e = video.error;
  if (!e) return 'unknown error';
  const codes = {
    1: 'MEDIA_ERR_ABORTED (load aborted)',
    2: 'MEDIA_ERR_NETWORK (network error)',
    3: 'MEDIA_ERR_DECODE (decode failure — codec not supported)',
    4: 'MEDIA_ERR_SRC_NOT_SUPPORTED (source/format not playable)',
  };
  return `${codes[e.code] || 'code ' + e.code}${e.message ? ' — ' + e.message : ''}`;
}

async function openVideoModal(date) {
  const modal = $('#video-modal');
  const list = $('#video-list');
  const video = $('#video-el');
  const now = $('#video-now');
  const title = $('#video-modal-title');

  title.textContent = `Videos · ${state.customer} / ${state.location} / ${state.conveyor} / ${date}`;
  list.innerHTML = '<li class="disabled">Loading…</li>';
  video.removeAttribute('src');
  video.load();
  now.innerHTML = '';
  modal.classList.remove('hidden');

  try {
    const params = new URLSearchParams({
      customer: state.customer,
      location: state.location,
      conveyor: state.conveyor,
      date,
    });
    const files = await fetchJSON(`/api/videos?${params.toString()}`);
    list.innerHTML = '';
    if (!files.length) {
      list.innerHTML = '<li class="disabled">— no playable videos —</li>';
      return;
    }
    for (const f of files) {
      const li = document.createElement('li');
      const sizeMB = ((f.size || 0) / (1024 * 1024)).toFixed(1);
      li.innerHTML = `<span class="vname"></span><span class="vsize">${sizeMB} MB</span>`;
      li.querySelector('.vname').textContent = f.name;
      const setSource = (src, transcoded) => {
        video.src = src;
        video.load();
        const p = video.play();
        if (p && p.catch) p.catch(() => {});
        now.innerHTML = '';
        const name = document.createElement('div');
        name.textContent = transcoded ? `${f.name} (transcoded)` : f.name;
        now.appendChild(name);
        const a = document.createElement('a');
        a.href = f.url; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Open direct in new tab';
        a.className = 'video-direct-link';
        now.appendChild(a);
      };

      li.onclick = () => {
        for (const el of list.querySelectorAll('li')) el.classList.remove('selected');
        li.classList.add('selected');
        video.onerror = () => {
          now.innerHTML = '';
          const msg = document.createElement('div');
          msg.className = 'video-error';
          msg.textContent = `${f.name} — ${videoErrorMessage(video)}`;
          now.appendChild(msg);
          const btn = document.createElement('button');
          btn.className = 'video-transcode-btn';
          btn.textContent = 'Try transcoded stream (H.264, slow, no seek)';
          btn.onclick = () => {
            video.onerror = () => {
              now.innerHTML = '';
              const m = document.createElement('div');
              m.className = 'video-error';
              m.textContent = `Transcode failed: ${videoErrorMessage(video)}`;
              now.appendChild(m);
            };
            setSource(f.stream_url, true);
          };
          now.appendChild(btn);
          const a = document.createElement('a');
          a.href = f.url; a.target = '_blank'; a.rel = 'noopener';
          a.textContent = 'Open direct in new tab';
          a.className = 'video-direct-link';
          now.appendChild(a);
        };
        setSource(f.url, false);
      };
      list.appendChild(li);
    }
    list.firstElementChild.click();
  } catch (e) {
    list.innerHTML = `<li class="disabled">Error: ${e.message}</li>`;
  }
}

function closeVideoModal() {
  const modal = $('#video-modal');
  const video = $('#video-el');
  modal.classList.add('hidden');
  video.pause();
  video.removeAttribute('src');
  video.load();
}

$('#video-modal-close').onclick = closeVideoModal;
$('#video-modal').onclick = (e) => { if (e.target.id === 'video-modal') closeVideoModal(); };
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('#video-modal').classList.contains('hidden')) closeVideoModal();
});

loadCustomers();
refreshQueue();
refreshTmux();
setInterval(refreshQueue, 5000);
setInterval(refreshTmux, 5000);

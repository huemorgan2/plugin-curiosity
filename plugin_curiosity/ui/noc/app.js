// NOC pane (10.002) — the dense operations wall: role wall, heartbeat, gap
// board, activity, shelf, machinery, chips, past missions. Same overview
// payload and live bridge as the Missions pane.

const PLUGIN = 'plugin-curiosity';
// Agent base path (e.g. "/a/<slug>") from this iframe's own URL — the API
// lives on the agent, so every call is BASE-prefixed. Locally BASE = "".
const BASE = window.location.pathname.split(`/api/p/${PLUGIN}`)[0];
const API = `${BASE}/api/p/${PLUGIN}`;
let TOKEN = localStorage.getItem('luna.token' + BASE) || localStorage.getItem('luna.token') || '';

let DATA = null;
let loadTimer = null;

// ---- shell bridge ----------------------------------------------------------

window.addEventListener('message', (e) => {
  const d = e.data;
  if (!d) return;
  if (d.type === 'luna-auth' && d.token) {
    const first = !TOKEN;
    TOKEN = d.token;
    if (first) load();
  }
  if (d.type === 'luna-plugin-event') {
    if (d.event === 'ui.section.reclick') load();
    if (d.event === 'changed') scheduleLoad();
    if (d.event === 'heartbeat') { beatPulse(); scheduleLoad(); }
  }
});

function requestFreshToken(prev, timeoutMs = 1500) {
  return new Promise((resolve) => {
    let timer;
    const onMsg = (e) => {
      if (e.data && e.data.type === 'luna-auth' && e.data.token && e.data.token !== prev) {
        cleanup(); resolve(true);
      }
    };
    const cleanup = () => { window.removeEventListener('message', onMsg); clearTimeout(timer); };
    window.addEventListener('message', onMsg);
    timer = setTimeout(() => { cleanup(); resolve(false); }, timeoutMs);
    try { window.parent.postMessage({ type: 'luna-request-auth' }, window.location.origin); }
    catch { cleanup(); resolve(false); }
  });
}

async function api(path, _retried) {
  const headers = {};
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const res = await fetch(`${API}${path}`, { headers }); // cookies ride along same-origin (hosted)
  if (res.status === 401 && !_retried) {
    if (await requestFreshToken(TOKEN)) return api(path, true);
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Coalesce bursts of "changed" events into one refetch.
function scheduleLoad() {
  clearTimeout(loadTimer);
  loadTimer = setTimeout(load, 600);
}

// ---- helpers ----------------------------------------------------------------

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? '' : s)
  .replace(/\[\[([^\]]+)\]\]/g, '$1') // agent notes carry [[wiki-link]] markup — owners see plain words
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function show(id, on) { $(id).classList.toggle('hidden', !on); }

function ago(iso) {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  if (!isFinite(ms) || ms < 0) return '';
  const m = Math.floor(ms / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function dateOf(iso) { return iso ? String(iso).slice(0, 10) : ''; }

// ---- render -------------------------------------------------------------------

function render() {
  const o = DATA;
  if (o.blocked) { renderBlocked(o.blocked); return; }
  if (!o.mission) { show('blocked', false); show('app', false); show('empty', true); return; }
  show('blocked', false); show('empty', false); show('app', true);

  const phase = o.state ? o.state.agent_phase : 'setup';
  $('phase-chip').innerHTML = `phase <b>${phase === 'work' ? 'working the mission' : 'onboarding'}</b>`;
  $('chip-autonomy').innerHTML = `autonomy <b>rung ${esc(o.mission.autonomy_rung)}</b>`;
  $('chip-risk').innerHTML = `risk <b>${esc(o.mission.risk_ceiling)}</b>`;

  const pace = o.pace;
  const paceEl = $('pace');
  if (pace) {
    paceEl.className = `chip pace ${pace.band}`;
    paceEl.innerHTML = `pace <b>${esc(pace.band)}</b>`;
  }

  const hb = o.heartbeats && o.heartbeats.latest;
  const pulse = $('pulse');
  pulse.classList.toggle('alive', !!hb);
  $('pulse-label').textContent = hb ? `last pulse ${ago(hb.created_at)}` : 'no pulse yet';

  renderStatus(o, phase, hb);
  renderNoc(o);
  renderHeartbeat(o);
  renderGaps(o);
  renderNext(o);
  renderActivity(o);
  renderShelf(o);
  renderHistory(o);

  $('foot-note').textContent = `plugin-curiosity ${o.plugin_version} · live via the plugin bridge, refetch every 60s as fallback`;
  $('foot-updated').textContent = `updated ${new Date().toLocaleTimeString()}`;
}

function renderBlocked(b) {
  show('app', false); show('empty', false); show('blocked', true);
  const gone = b.missing ?? [];
  if (gone.length) $('blocked-title').textContent =
    `Luna Missions is missing ${gone.join(' and ')} to be able to operate`;
  const deps = $('blocked-deps');
  deps.innerHTML = Object.entries(b.deps).map(([name, why]) => {
    const missing = b.missing.includes(name);
    return `<div class="dep ${missing ? 'missing' : 'present'}">` +
      `<span class="nm">${missing ? '✕' : '✓'} ${esc(name)}</span>` +
      `<span class="why">${esc(why)}</span></div>`;
  }).join('');
  $('blocked-cta').href = `${BASE}/#marketplace`;
}

// Hero: the operational bottom line, computed from the same numbers the
// panels below show in detail.
function renderStatus(o, phase, hb) {
  const incidents = o.noc ? (o.noc.incidents || []).length : 0;
  const gaps = hb ? hb.gaps_open : null;
  const overdue = (o.loops || {}).overdue || 0;
  let line;
  if (incidents > 0) line = `${incidents} incident${incidents === 1 ? '' : 's'} on the score wall — details below`;
  else if (overdue > 0) line = `${overdue} loop${overdue === 1 ? '' : 's'} overdue — otherwise steady`;
  else if (hb) line = `All quiet — heartbeat alive${gaps != null ? `, ${gaps} gap${gaps === 1 ? '' : 's'} still open` : ''}`;
  else line = 'No heartbeat report yet — the first fire lands one';
  $('status-line').textContent = line;
  const bits = [`mission since ${dateOf(o.mission.created_at)}`];
  if (o.setup_percent != null) bits.push(`setup ${o.setup_percent}%`);
  if (hb) bits.push(`streak ${hb.streak}`);
  $('status-meta').textContent = bits.join(' · ');
}

function renderNoc(o) {
  const noc = o.noc;
  show('noc-panel', !!noc && noc.tiles.length > 0);
  if (!noc || !noc.tiles.length) return;
  $('noc-tiles').innerHTML = noc.tiles.map((t) => {
    const st = t.latest ? t.latest.status : 'unscored';
    const up = t.uptime_pct == null ? '' : `<span class="up">${t.uptime_pct}% over ${t.scored_weeks}w</span>`;
    return `<div class="tile ${st}"><div class="crit">${esc(t.criterion)}</div>` +
      `<div class="meas">${esc(t.measure)} → ${esc(t.target)} (${esc(t.horizon)})</div>` +
      `<div class="status-row"><span class="st">${esc(st)}</span>${up}</div>` +
      (t.latest && t.latest.evidence ? `<div class="meas" style="margin-top:6px">${esc(t.latest.evidence)}</div>` : '') +
      `</div>`;
  }).join('');
  $('noc-incidents').innerHTML = (noc.incidents || []).map((i) =>
    `<div class="incident"><span class="d">${esc(i.date)}</span><span class="s ${i.status}">${esc(i.status)}</span><span>${esc(i.criterion)} — ${esc(i.evidence)}</span></div>`
  ).join('');
}

function renderHeartbeat(o) {
  const latest = o.heartbeats && o.heartbeats.latest;
  const recent = (o.heartbeats && o.heartbeats.recent) || [];
  if (!latest) {
    $('hb-latest').innerHTML = '<div class="muted">No reports yet. Luna authors her own heartbeat trigger during setup; every fire ends with a structured report that lands here.</div>';
    $('hb-history').innerHTML = '';
    return;
  }
  $('hb-latest').innerHTML =
    `<div class="hb-now">` +
    `<div class="hb-num"><b>${latest.streak}</b><span>streak</span></div>` +
    `<div class="hb-num"><b>${latest.gaps_open}</b><span>gaps open</span></div>` +
    `<div class="hb-num"><b>${latest.wobbles}</b><span>wobbles</span></div>` +
    `</div>` +
    (latest.note ? `<div class="hb-note">“${esc(latest.note)}”</div>` : '');
  $('hb-history').innerHTML = recent.slice(1, 8).map((h) =>
    `<div class="hb-row"><span class="t">${ago(h.created_at)}</span>` +
    `<span>streak ${h.streak} · ${h.gaps_open} gaps · ${h.wobbles} wobbles</span>` +
    (h.morale ? `<span class="m">${esc(h.morale)}</span>` : '') + `</div>`
  ).join('');
}

function renderGaps(o) {
  const board = o.gap_board || [];
  $('gaps').innerHTML = board.length
    ? board.map((k) =>
        `<div class="gap-kind"><h3>${esc(k.label)}</h3>` +
        k.scopes.map((sc) =>
          `<div class="scope ${sc.status}"><span class="dot"></span><span>${esc(sc.name)}</span>` +
          (sc.evidence ? `<span class="ev">${esc(sc.evidence)}</span>` : '') + `</div>`
        ).join('') + `</div>`
      ).join('')
    : '<div class="muted">No scopes chartered yet — they arrive as Luna inventories what competent means for this role.</div>';
}

function renderNext(o) {
  const items = o.next_up || [];
  $('next').innerHTML = items.length
    ? items.map((n) =>
        `<div class="next-item"><span class="k">${esc(n.kind)}</span><span>${esc(n.title)}` +
        (n.detail ? ` <span class="det">${esc(n.detail)}</span>` : '') + `</span></div>`
      ).join('')
    : '<div class="muted">Nothing scheduled — if this persists, the heartbeat trigger may be missing (the weekly review will catch it).</div>';
}

function renderActivity(o) {
  const acts = o.activity || [];
  $('activity').innerHTML = acts.length
    ? acts.map((a) =>
        `<div class="act"><span class="t">${esc(dateOf(a.at) || a.at)}</span>` +
        `<span class="k ${a.kind}">${esc(a.kind)}</span><span class="x">${esc(a.text)}</span></div>`
      ).join('')
    : '<div class="muted">Quiet so far.</div>';
}

function renderShelf(o) {
  $('wiki').innerHTML = (o.wiki_shelf || []).map((p) => {
    if (!p.exists) {
      return `<div class="page absent"><div class="pt">${esc(p.label)}</div><div class="pr">${esc(p.role)}</div><div class="pa">not written yet</div></div>`;
    }
    const age = p.age_days == null ? '' : p.age_days === 0 ? 'updated today' : `updated ${p.age_days}d ago`;
    const cls = p.age_days == null ? '' : p.age_days <= 2 ? 'fresh' : p.age_days >= 14 ? 'stale' : '';
    return `<div class="page"><div class="pt">${esc(p.title || p.label)}</div>` +
      `<div class="pr">${esc(p.summary || p.role)}</div>` +
      `<div class="pa ${cls}">${age}</div></div>`;
  }).join('');
}

function renderHistory(o) {
  const past = (o.missions || []).filter((m) => !m.active);
  show('history-panel', past.length > 0);
  $('history').innerHTML = past.map((m) =>
    `<div class="hist"><span class="d">${esc(dateOf(m.created_at))}</span><span class="x">${esc(m.statement)}</span>` +
    (m.wiki_id ? `<span class="wk">its wiki lives on: ${esc(m.wiki_id)}</span>` : '') +
    `</div>`
  ).join('');
}

function beatPulse() {
  const p = $('pulse');
  p.classList.remove('beating');
  void p.offsetWidth; // restart the animation
  p.classList.add('beating');
}

// ---- tooltips: only behind the (i) affordances ------------------------------

document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('.help[data-tip]');
  const tip = $('tip');
  if (!el || !el.dataset.tip) { tip.classList.add('hidden'); return; }
  tip.textContent = el.dataset.tip;
  tip.classList.remove('hidden');
  const r = el.getBoundingClientRect();
  tip.style.left = Math.min(r.left, window.innerWidth - 320) + 'px';
  tip.style.top = (r.bottom + 8) + 'px';
});

// ---- boot -------------------------------------------------------------------

async function load() {
  try {
    DATA = await api('/missions/overview');
    render();
  } catch (err) {
    if (!DATA) {
      show('empty', true);
      $('empty').querySelector('.blocked-lead').textContent =
        `Could not reach the agent (${err.message}). Retrying…`;
    }
  }
}

try { window.parent.postMessage({ type: 'luna-ui-ready' }, window.location.origin); } catch {}
if (!TOKEN) {
  try { window.parent.postMessage({ type: 'luna-request-auth' }, window.location.origin); } catch {}
}
load();
setInterval(load, 60000); // fallback poll — the bridge is best-effort by design

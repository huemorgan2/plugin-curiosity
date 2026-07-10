// Missions pane — plugin-curiosity's iframe app (9.002D).
// Mission control for the agent's curiosity: hand-written JS, no framework.
// Auth + live-bridge handshake follow plugin-marketplace's pane verbatim.

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
  $('phase-dial').innerHTML =
    `<span class="seg${phase === 'setup' ? ' on' : ''}" data-tip="Phase one: qualify for the job — understand, inventory, post, get ratified, validate, wire feedback.">setup</span>` +
    `<span class="seg${phase === 'work' ? ' on' : ''}" data-tip="Phase two: execute the role with mastery; the weekly review scores every success criterion.">work</span>`;

  $('chip-autonomy').innerHTML = `autonomy <b>rung ${esc(o.mission.autonomy_rung)}</b>`;
  $('chip-risk').innerHTML = `risk <b>${esc(o.mission.risk_ceiling)}</b>`;

  // pace chip (server-computed — the honest half of contentment)
  const pace = o.pace;
  const paceEl = $('pace');
  if (pace) {
    paceEl.className = `chip pace ${pace.band}`;
    paceEl.innerHTML = `pace <b>${esc(pace.band)}</b>`;
    paceEl.dataset.tip = 'Computed on the server from clock facts, never vibes: ' +
      (pace.reasons || []).join('; ') + '.';
  }

  // heartbeat pulse chip
  const hb = o.heartbeats && o.heartbeats.latest;
  const pulse = $('pulse');
  pulse.classList.toggle('alive', !!hb);
  $('pulse-label').textContent = hb ? `last pulse ${ago(hb.created_at)}` : 'no pulse yet';

  // hero
  $('mission-statement').textContent = o.mission.statement;
  const since = dateOf(o.mission.created_at);
  const stage = o.state && phase === 'setup' ? ` · stage ${o.state.setup_stage}` : '';
  $('mission-meta').textContent = `since ${since}${stage} · ${o.loops.open.length} open loop(s) · ${o.value_log.length} win(s) delivered`;

  const moraleEl = $('morale');
  if (hb && hb.morale) {
    moraleEl.className = `hero-morale ${o.sentiment || 'neutral'}`;
    moraleEl.innerHTML = `<span class="band-dot"></span>feeling <span class="word">“${esc(hb.morale)}”</span><span class="muted">— its own words, ${ago(hb.created_at)}</span>`;
    moraleEl.classList.remove('hidden');
  } else {
    moraleEl.classList.add('hidden');
  }

  renderNeeds(o);
  renderSetup(o, phase);
  renderNoc(o);
  renderGaps(o);
  renderGoals(o);
  renderHeartbeat(o);
  renderNext(o);
  renderActivity(o);
  renderShelf(o);
  renderHistory(o);

  $('foot-note').textContent = `plugin-curiosity ${o.plugin_version} · live via the plugin bridge, refetch every 60s as fallback`;
  $('foot-updated').textContent = `updated ${new Date().toLocaleTimeString()}`;
}

function renderBlocked(b) {
  show('app', false); show('empty', false); show('blocked', true);
  const deps = $('blocked-deps');
  deps.innerHTML = Object.entries(b.deps).map(([name, why]) => {
    const missing = b.missing.includes(name);
    return `<div class="dep ${missing ? 'missing' : 'present'}">` +
      `<span class="nm">${missing ? '✕' : '✓'} ${esc(name)}</span>` +
      `<span class="why">${esc(why)}</span></div>`;
  }).join('');
  $('blocked-cta').href = `${BASE}/#marketplace`;
}

function renderNeeds(o) {
  const needs = o.needs_from_you || [];
  show('needs', needs.length > 0);
  $('needs-list').innerHTML = needs.map((n) => {
    let extra = '';
    if (n.kind === 'ask' && n.unlock) extra = `<span class="why">unlocks: ${esc(n.unlock)}</span>`;
    return `<div class="need"><span class="k">${esc(n.kind)}</span><span>${esc(n.text)}</span>${extra}</div>`;
  }).join('');
}

function renderSetup(o, phase) {
  const s = o.setup;
  show('setup-panel', !!s && phase === 'setup');
  if (!s) return;
  $('setup-ring').style.setProperty('--p', s.percent);
  $('setup-pct').textContent = `${s.percent}%`;
  const cur = s.stages.find((x) => x.status === 'current');
  $('setup-current').innerHTML = cur
    ? `working toward <b>${cur.id} — ${esc(cur.label)}</b>: ${esc(cur.detail)}`
    : '<b>setup complete</b> — graduation to work mode is next';
  $('setup-list').innerHTML = s.stages.map((st) =>
    `<li class="${st.status}"><span class="mark">${st.status === 'done' ? '✓' : st.status === 'current' ? '▸' : ''}</span>` +
    `<span class="sid">${st.id}</span><span><span class="lbl">${esc(st.label)}</span> <span class="det">— ${esc(st.detail)}</span></span></li>`
  ).join('');
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
    : '<div class="muted">No scopes chartered yet — S1 is where the agent inventories what competent means for this role.</div>';
}

function renderGoals(o) {
  const goals = o.goals || [];
  $('goals').innerHTML = goals.length
    ? goals.map((g) =>
        `<div class="goal ${g.status}"><div class="row"><span class="st">${esc(g.status)}</span>` +
        `<span>${esc(g.statement)}</span>` +
        (g.target_date ? `<span class="due">${esc(g.target_date)}</span>` : '') + `</div>` +
        (g.progress_note ? `<div class="note">${esc(g.progress_note)}</div>` : '') + `</div>`
      ).join('')
    : '<div class="muted">No goals committed yet — they arrive with the mission kickoff.</div>';
}

function renderHeartbeat(o) {
  const latest = o.heartbeats && o.heartbeats.latest;
  const recent = (o.heartbeats && o.heartbeats.recent) || [];
  if (!latest) {
    $('hb-latest').innerHTML = '<div class="muted">No reports yet. The agent authors its own heartbeat trigger during setup; every fire ends with a structured report that lands here.</div>';
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
    `<div class="hist"><span class="d">${esc(dateOf(m.created_at))}</span><span class="x">${esc(m.statement)}</span></div>`
  ).join('');
}

function beatPulse() {
  const p = $('pulse');
  p.classList.remove('beating');
  void p.offsetWidth; // restart the animation
  p.classList.add('beating');
}

// ---- tooltips (the "how is this computed" layer) ----------------------------

document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('[data-tip]');
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
    // First paint with no data: show the empty shell rather than a spinner
    // forever; subsequent polls recover silently.
    if (!DATA) {
      show('empty', true);
      $('empty').querySelector('.blocked-lead').textContent =
        `Could not reach the agent (${err.message}). Retrying…`;
    }
  }
}

// Tell the shell we're ready (it replies with luna-auth and starts forwarding
// luna-plugin-event messages), then load with whatever token we have.
try { window.parent.postMessage({ type: 'luna-ui-ready' }, window.location.origin); } catch {}
if (!TOKEN) {
  try { window.parent.postMessage({ type: 'luna-request-auth' }, window.location.origin); } catch {}
}
load();
setInterval(load, 60000); // fallback poll — the bridge is best-effort by design

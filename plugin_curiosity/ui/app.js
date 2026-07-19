// Missions pane (10.002) — the owner-facing summary: mission, job
// description, setup ladder, goals. Everything operational lives in the
// Operational dashboard tab (ui/noc/, embedded since 0.9.5). Auth + live-bridge handshake follow plugin-marketplace's pane.

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
  const frame = document.getElementById('ops-frame');
  // 0.9.5 relay — the ops tab embeds ui/noc/, whose window.parent is THIS
  // page, not the shell. Forward its handshake up and the shell's auth +
  // live-bridge events down, so the embedded wall stays live.
  if (frame && e.source === frame.contentWindow) {
    if (d.type === 'luna-request-auth' || d.type === 'luna-ui-ready') {
      try { window.parent.postMessage(d, window.location.origin); } catch {}
    }
    return;
  }
  if ((d.type === 'luna-auth' || d.type === 'luna-plugin-event') && frame && frame.src) {
    try { frame.contentWindow.postMessage(d, window.location.origin); } catch {}
  }
  if (d.type === 'luna-auth' && d.token) {
    const first = !TOKEN;
    TOKEN = d.token;
    if (first) load();
  }
  if (d.type === 'luna-plugin-event') {
    if (d.event === 'ui.section.reclick') load();
    if (d.event === 'changed') scheduleLoad();
    if (d.event === 'heartbeat') scheduleLoad();
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

function dateOf(iso) { return iso ? String(iso).slice(0, 10) : ''; }

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function shortDate(iso) {
  const d = dateOf(iso);
  if (!d) return '';
  const [, m, day] = d.split('-');
  return `${MONTHS[Number(m) - 1]} ${Number(day)}`;
}

// ---- render -------------------------------------------------------------------

function render() {
  const o = DATA;
  show('loading', false);
  if (o.blocked) { renderBlocked(o.blocked); return; }
  if (!o.mission) { show('blocked', false); show('app', false); show('empty', true); return; }
  show('blocked', false); show('empty', false); show('app', true);

  renderHero(o);
  renderNeeds(o);
  renderPivot(o);
  renderJd(o);
  renderSetup(o);
  renderGoals(o);

  $('foot-note').textContent = `plugin-curiosity ${o.plugin_version} · operations detail lives in the Operational dashboard tab`;
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

// 1 · ACTIVE MISSION — statement, then the agent's own one-line status
// (she writes it via current_state_set and it renders verbatim — the UI
// never invents this sentence; morale detail lives on the ops heartbeat panel)
function renderHero(o) {
  const phase = o.state ? o.state.agent_phase : 'setup';
  $('mission-statement').textContent = o.mission.statement;
  const said = ((o.state && o.state.current_state) || '').trim();
  const fallback = phase === 'work' ? 'working the mission' : 'onboarding';
  $('mission-phase').innerHTML =
    `<span class="state-label">Current state</span> ${said ? esc(said) : `<span class="unsaid">${fallback}</span>`}`;
  const wins = (o.value_log || []).length;
  const open = ((o.loops || {}).open || []).length;
  $('mission-meta').textContent =
    `since ${dateOf(o.mission.created_at)} · ${wins} win${wins === 1 ? '' : 's'} delivered · ${open} open thread${open === 1 ? '' : 's'}`;
}

// Needs strip — asks only; pivots get their own card below
function renderNeeds(o) {
  const needs = (o.needs_from_you || []).filter((n) => n.kind !== 'pivot');
  show('needs', needs.length > 0);
  $('needs-list').innerHTML = needs.map((n) => {
    let extra = '';
    if (n.kind === 'ask' && n.unlock) extra = `<span class="why">unlocks: ${esc(n.unlock)}</span>`;
    return `<div class="need"><span class="k">${esc(n.kind)}</span><span>${esc(n.text)}</span>${extra}</div>`;
  }).join('');
}

// Role pivot card — a big change the owner decides on
function renderPivot(o) {
  const pivot = (o.needs_from_you || []).find((n) => n.kind === 'pivot');
  show('pivot-card', !!pivot);
  if (!pivot) return;
  $('pivot-headline').textContent = 'Big change: the job itself looks different than we thought';
  $('pivot-why').textContent = pivot.text;
}

// 2 · JOB DESCRIPTION — living draft, four blocks, assumption check-dots
const JD_BLOCKS = [
  ['method', 'How I will do the job', 'numbered'],
  ['after_onboarding', 'After onboarding', 'bullet'],
  ['in_30_days', 'In 30 days', 'bullet'],
  ['working_assumptions', 'Working assumptions', 'assumption'],
];

function renderJd(o) {
  const jd = o.job_description;
  const head = $('jd-headline');
  const stamp = $('jd-stamp');
  const blocks = $('jd-blocks');
  if (!jd || !jd.exists) {
    head.textContent = 'I haven’t written my job description yet';
    stamp.textContent = 'It lands with kickoff — the first thing I do after adopting a mission.';
    blocks.innerHTML = '';
    return;
  }
  // real edit history (wiki revisions) beats the coarse pivot stamp; count
  // and date only — revision notes are Luna's internal bookkeeping
  if (jd.revisions && jd.revisions.count) {
    const when = String(jd.revisions.latest || '').slice(0, 10);
    stamp.innerHTML = `Living draft <b>v${esc(jd.role_version)}</b> · ` +
      `${esc(jd.revisions.count)} revision${jd.revisions.count === 1 ? '' : 's'}` +
      (when ? `, last ${esc(when)}` : '') + ' · I keep this current as I learn.';
  } else {
    const rev = jd.latest_pivot
      ? ` · revised ${esc(jd.latest_pivot.date)} — the job changed`
      : '';
    stamp.innerHTML = `Living draft <b>v${esc(jd.role_version)}</b>${rev} · I keep this current as I learn.`;
  }

  if (!jd.shape_ok) {
    head.textContent = 'My job description, as I wrote it';
    blocks.innerHTML =
      '<p class="support dim">This draft doesn’t follow my usual four-block shape yet — here it is verbatim.</p>' +
      `<div class="jd-raw">${esc(jd.raw || '')}</div>`;
    return;
  }

  const method = jd.sections.method;
  head.textContent = (method.items[0] || 'My job, in my own words').replace(/\*\*/g, '');
  blocks.innerHTML = JD_BLOCKS.map(([key, label, kind]) => {
    const sec = jd.sections[key];
    if (!sec) return '';
    const intro = sec.intro ? `<p class="jd-intro">${esc(sec.intro)}</p>` : '';
    const items = sec.items.map((it, i) => {
      const text = esc(it).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
      if (kind === 'numbered') return `<li><span class="n">${i + 1}.</span><span>${text}</span></li>`;
      if (kind === 'assumption') {
        // check-dots: ◐ checking by default; ● when the agent marked it
        // verified; ✕ when it marked it broken/revised
        let cls = 'checking', glyph = '◐';
        if (/^\s*(✓|\[?verified\]?)/i.test(it)) { cls = 'verified'; glyph = '●'; }
        if (/^\s*(✕|\[?(broken|revised|wrong)\]?)/i.test(it)) { cls = 'broken'; glyph = '✕'; }
        return `<li><span class="adot ${cls}">${glyph}</span><span>${text}</span></li>`;
      }
      return `<li><span class="dot"></span><span>${text}</span></li>`;
    }).join('');
    const tag = kind === 'numbered' ? 'ol' : 'ul';
    return `<div class="jd-block"><h3>${esc(label)}</h3>${intro}<${tag}>${items}</${tag}></div>`;
  }).join('');
}

// 3 · SETUP — ring + ability rows (expand → subtasks)
function renderSetup(o) {
  const pct = o.setup_percent;
  const abilities = o.abilities || [];
  show('setup-panel', pct != null || abilities.length > 0);
  if (pct == null && !abilities.length) return;

  const phase = o.state ? o.state.agent_phase : 'setup';
  const p = pct == null ? 0 : pct;
  $('setup-ring').style.setProperty('--p', p);
  $('setup-pct').textContent = `${p}%`;
  $('setup-headline').textContent = phase === 'work'
    ? 'Setup complete — now it’s about the work'
    : `Setup — ${p}% complete`;
  $('setup-support').textContent = phase === 'work'
    ? 'These are the abilities the job runs on. I keep scoring them honestly.'
    : 'Each ability is something I need before I’m fully qualified. Click one to see the checklist behind its number.';

  $('abilities').innerHTML = abilities.map((a) => {
    const subtasks = (a.tasks || []).map((t) =>
      `<div class="subtask ${esc(t.status)}"><span class="dot"></span><span>${esc(t.title)}` +
      (t.note ? ` <span class="note">— ${esc(t.note)}</span>` : '') + `</span></div>`
    ).join('');
    return `<details class="ability">` +
      `<summary><span class="a-tw">▸</span><span class="a-title">${esc(a.title)}</span>` +
      `<span class="a-bar"><i style="width:${a.percent}%"></i></span>` +
      `<span class="a-pct">${a.percent}%</span></summary>` +
      `<div class="subtasks">${subtasks || '<div class="muted">no checklist yet</div>'}</div>` +
      `</details>`;
  }).join('') || '<div class="muted">The qualification ladder lands with kickoff.</div>';
}

// 4 · GOALS — headline, timeline dots, next 2–3 as two-liners

function renderGoals(o) {
  const goals = (o.goals || []).filter((g) => g.target_date).slice()
    .sort((a, b) => String(a.target_date).localeCompare(String(b.target_date)));
  const undated = (o.goals || []).filter((g) => !g.target_date);
  show('goals-panel', goals.length + undated.length > 0);
  if (!goals.length && !undated.length) return;

  // 0.10.0: goals living in the Goal-Seek engine link out to their pane
  const eyebrow = document.querySelector('#goals-panel .eyebrow');
  if (eyebrow && !eyebrow.querySelector('.pane-link') &&
      (o.goals || []).some((g) => g.engine === 'goalseek')) {
    const a = document.createElement('a');
    a.className = 'pane-link';
    a.href = '/p/goals';
    a.target = '_top';
    a.textContent = 'open in Goals pane →';
    a.style.cssText = 'float:right;font-size:11px;color:#8b5cf6;text-decoration:none';
    eyebrow.appendChild(a);
  }

  const upcoming = goals.filter((g) => g.status === 'active' || g.status === 'stalled');
  const next = upcoming[0];
  $('goals-headline').textContent = next
    ? `Next: ${next.statement} — ${shortDate(next.target_date)}`
    : 'All dated goals are settled';

  // 0.9.9: the timeline and the list share one identity — every upcoming
  // goal has ONE number, shown inside its timeline dot AND as the list
  // marker, in the same status color. Hovering either side highlights both.
  const nums = new Map();
  upcoming.slice(0, 3).forEach((g, i) => nums.set(g, i + 1)); // only listed goals get numbers

  // timeline: a numbered dot per upcoming goal (settled goals stay plain
  // dots); the goal card appears on hover, floating above everything.
  const tl = $('goal-timeline');
  if (goals.length >= 2) {
    const t0 = new Date(goals[0].target_date).getTime();
    const t1 = new Date(goals[goals.length - 1].target_date).getTime();
    const span = Math.max(t1 - t0, 1);
    const nextIdx = next ? goals.indexOf(next) : -1;
    tl.innerHTML = '<div class="rail"></div>' + goals.map((g, i) => {
      const x = 6 + 88 * ((new Date(g.target_date).getTime() - t0) / span); // 6%..94%
      const n = nums.get(g) || 0;
      const edge = x < 14 ? 'edge-l' : x > 86 ? 'edge-r' : ''; // keep hover cards inside the panel
      const cls = [g.status, i === nextIdx ? 'next' : '', edge].filter(Boolean).join(' ');
      return `<div class="tl-goal ${cls}"${n ? ` data-n="${n}"` : ''} style="left:${x}%">` +
        `<span class="bubble"><b>${esc(g.statement)}</b>${esc(shortDate(g.target_date))}</span>` +
        `<span class="tdot${n ? ' num' : ''}">${n || ''}</span>` +
        `<span class="tdate">${esc(shortDate(g.target_date))}</span></div>`;
    }).join('');
    tl.classList.remove('hidden');
    // clustered dates collide — walk left to right and clip any label that
    // would overlap its neighbor (it reappears on hover of its dot)
    let lastRight = -Infinity;
    tl.querySelectorAll('.tl-goal .tdate').forEach((d) => {
      const r = d.getBoundingClientRect();
      if (!r.width) return;
      if (r.left < lastRight + 8) d.classList.add('clip');
      else lastRight = r.right;
    });
  } else {
    tl.innerHTML = '';
  }

  // next 2–3, two lines each: required result, then readiness — numbered and
  // colored to mirror their timeline dots
  const READY = { green: '🟢', amber: '🟠', red: '🔴' };
  $('goal-next').innerHTML = upcoming.slice(0, 3).map((g, i) => {
    const result = g.expected_result || g.statement;
    const ready = g.readiness
      ? `<div class="g-ready ${esc(g.readiness)}">${READY[g.readiness] || ''} ${esc(g.readiness_note || g.readiness)}</div>`
      : '';
    const tone = i === 0 ? 'next' : (g.status === 'stalled' ? 'stalled' : 'active');
    return `<li class="g-${tone}" data-n="${i + 1}"><span class="gn">${i + 1}</span><div>` +
      `<div class="g-result">${esc(result)}<span class="due">${esc(shortDate(g.target_date))}</span></div>` +
      ready + `</div></li>`;
  }).join('');
}

// hovering a numbered dot lights up its list row, and vice versa
document.addEventListener('mouseover', (e) => {
  const hit = e.target.closest('.tl-goal[data-n], .goal-next li[data-n]');
  document.querySelectorAll('.linked').forEach((el) => el.classList.remove('linked'));
  if (!hit) return;
  document.querySelectorAll(
    `.tl-goal[data-n="${hit.dataset.n}"], .goal-next li[data-n="${hit.dataset.n}"]`
  ).forEach((el) => el.classList.add('linked'));
});

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
    // First paint with no data: show the empty shell rather than a spinner
    // forever; subsequent polls recover silently.
    if (!DATA) {
      show('loading', false);
      show('empty', true);
      $('empty').querySelector('.blocked-lead').textContent =
        `Could not reach the agent (${err.message}). Retrying…`;
    }
  }
}

// ---- tabs (0.9.5) -----------------------------------------------------------
// Tab 2 lazy-loads ui/noc/ on first open; #ops in the URL deep-links to it
// (replaces the retired NOC sidebar entry).

function setTab(ops) {
  $('tab-missions').classList.toggle('active', !ops);
  $('tab-ops').classList.toggle('active', ops);
  $('tab-missions').setAttribute('aria-selected', String(!ops));
  $('tab-ops').setAttribute('aria-selected', String(ops));
  show('view-missions', !ops);
  show('view-ops', ops);
  if (ops) {
    const frame = $('ops-frame');
    if (!frame.src) frame.src = `noc/?v=${encodeURIComponent(DATA?.plugin_version || '')}`;
  }
  try { history.replaceState(null, '', ops ? '#ops' : '#'); } catch {}
}
$('tab-missions').addEventListener('click', () => setTab(false));
$('tab-ops').addEventListener('click', () => setTab(true));
if (window.location.hash === '#ops') setTab(true);
// deep links also arrive as hash-only navigations (no reload)
window.addEventListener('hashchange', () => setTab(window.location.hash === '#ops'));

// Tell the shell we're ready (it replies with luna-auth and starts forwarding
// luna-plugin-event messages), then load with whatever token we have.
try { window.parent.postMessage({ type: 'luna-ui-ready' }, window.location.origin); } catch {}
if (!TOKEN) {
  try { window.parent.postMessage({ type: 'luna-request-auth' }, window.location.origin); } catch {}
}
load();
setInterval(load, 60000); // fallback poll — the bridge is best-effort by design

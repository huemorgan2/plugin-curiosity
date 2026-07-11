// Missions pane (10.002) — the owner-facing summary: mission, job
// description, setup ladder, goals. Everything operational lives in the NOC
// pane. Auth + live-bridge handshake follow plugin-marketplace's pane.

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

// ---- render -------------------------------------------------------------------

function render() {
  const o = DATA;
  if (o.blocked) { renderBlocked(o.blocked); return; }
  if (!o.mission) { show('blocked', false); show('app', false); show('empty', true); return; }
  show('blocked', false); show('empty', false); show('app', true);

  renderHero(o);
  renderNeeds(o);
  renderPivot(o);
  renderJd(o);
  renderSetup(o);
  renderGoals(o);

  $('foot-note').textContent = `plugin-curiosity ${o.plugin_version} · operations detail lives in the NOC pane`;
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

// 1 · ACTIVE MISSION — statement, plain-word phase, morale
function renderHero(o) {
  const phase = o.state ? o.state.agent_phase : 'setup';
  $('mission-statement').textContent = o.mission.statement;
  $('mission-phase').textContent = phase === 'work'
    ? 'Working the mission — the job is running.'
    : 'Onboarding — I’m setting myself up to do this job well.';
  const wins = (o.value_log || []).length;
  const open = ((o.loops || {}).open || []).length;
  $('mission-meta').textContent =
    `since ${dateOf(o.mission.created_at)} · ${wins} win${wins === 1 ? '' : 's'} delivered · ${open} open thread${open === 1 ? '' : 's'}`;

  const hb = o.heartbeats && o.heartbeats.latest;
  const moraleEl = $('morale');
  if (hb && hb.morale) {
    moraleEl.className = `hero-morale ${o.sentiment || 'neutral'}`;
    moraleEl.innerHTML = `<span class="band-dot"></span>feeling <span class="word">“${esc(hb.morale)}”</span><span class="muted">— her own words, ${ago(hb.created_at)}</span>`;
  } else {
    moraleEl.classList.add('hidden');
  }
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
const STOPWORDS = new Set(['the', 'a', 'an', 'to', 'and', 'of', 'for', 'in', 'on', 'at', 'by', 'with', 'my', 'our', 'first']);

function bubbleWord(statement) {
  const words = String(statement || '').replace(/[^\w\s%€$-]/g, '').split(/\s+/);
  const w = words.find((x) => x && !STOPWORDS.has(x.toLowerCase())) || words[0] || '';
  return w.length > 12 ? w.slice(0, 11) + '…' : w;
}

function bubbleNumber(g) {
  const hay = `${g.statement || ''} ${g.expected_result || ''}`;
  const m = hay.match(/[€$]\s?\d[\d,.]*|\d[\d,.]*\s?%|\b\d[\d,.]*\b/);
  if (m) return m[0].replace(/\s/g, '');
  return shortDate(g.target_date);
}

function renderGoals(o) {
  const goals = (o.goals || []).filter((g) => g.target_date).slice()
    .sort((a, b) => String(a.target_date).localeCompare(String(b.target_date)));
  const undated = (o.goals || []).filter((g) => !g.target_date);
  show('goals-panel', goals.length + undated.length > 0);
  if (!goals.length && !undated.length) return;

  const upcoming = goals.filter((g) => g.status === 'active' || g.status === 'stalled');
  const next = upcoming[0];
  $('goals-headline').textContent = next
    ? `Next: ${next.statement} — ${shortDate(next.target_date)}`
    : 'All dated goals are settled';

  // timeline: dot per dated goal, bubbles on the near ones only
  const tl = $('goal-timeline');
  if (goals.length >= 2) {
    const t0 = new Date(goals[0].target_date).getTime();
    const t1 = new Date(goals[goals.length - 1].target_date).getTime();
    const span = Math.max(t1 - t0, 1);
    const nextIdx = next ? goals.indexOf(next) : -1;
    tl.innerHTML = '<div class="rail"></div>' + goals.map((g, i) => {
      const x = 6 + 88 * ((new Date(g.target_date).getTime() - t0) / span); // 6%..94%
      const far = nextIdx >= 0 && i > nextIdx + 2; // bubbles: past + next 3, dots beyond
      const cls = [g.status, i === nextIdx ? 'next' : '', far ? 'far' : ''].filter(Boolean).join(' ');
      return `<div class="tl-goal ${cls}" style="left:${x}%">` +
        `<span class="bubble"><b>${esc(bubbleWord(g.statement))}</b>${esc(bubbleNumber(g))}</span>` +
        `<span class="tdot"></span><span class="tdate">${esc(shortDate(g.target_date))}</span></div>`;
    }).join('');
    tl.classList.remove('hidden');
  } else {
    tl.innerHTML = '';
  }

  // next 2–3, two lines each: required result, then readiness
  const READY = { green: '🟢', amber: '🟠', red: '🔴' };
  $('goal-next').innerHTML = upcoming.slice(0, 3).map((g, i) => {
    const result = g.expected_result || g.statement;
    const ready = g.readiness
      ? `<div class="g-ready ${esc(g.readiness)}">${READY[g.readiness] || ''} ${esc(g.readiness_note || g.readiness)}</div>`
      : '';
    return `<li><span class="gn">${i + 1}</span><div>` +
      `<div class="g-result">${esc(result)}<span class="due">${esc(shortDate(g.target_date))}</span></div>` +
      ready + `</div></li>`;
  }).join('');
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

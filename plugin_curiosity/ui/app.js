// Missions pane (11.004/M4, 0.16.0) — the journey, not a dashboard. Renders
// DATA.journey (built server-side in journey.py): mission hero, adoption rail,
// now & next, and sections that appear only when their data does. Buttons
// (M0a) post muted "moment" messages into the newest conversation so the agent
// reacts in voice. Machinery lives on tab 2 (ui/noc/, embedded since 0.9.5).

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
  // 0.16.1: the shell acks luna-chat messages (luna 065) — an ack means
  // "Change it" can hand the owner the composer instead of a muted moment.
  if (d.type === 'luna-chat-ack') CHAT_BRIDGE = true;
});

// ---- chat bridge (065, 0.16.1) ----------------------------------------------
// "Change it" should end with the owner typing, not the agent talking. On new
// cores the shell answers a luna-chat ping with luna-chat-ack; then Change-it
// buttons prefill + focus the composer. Old cores never ack → the muted-moment
// fallback below keeps working.

let CHAT_BRIDGE = false;

function pingChatBridge() {
  try { window.parent.postMessage({ type: 'luna-chat', action: 'ping' }, window.location.origin); } catch {}
}
pingChatBridge();

/** Prefill + focus the shell composer. Returns false when the bridge is
 * absent (old core) — caller falls back to a muted moment. */
function prefillChat(text) {
  if (!CHAT_BRIDGE) return false;
  try {
    window.parent.postMessage({ type: 'luna-chat', action: 'prefill', text }, window.location.origin);
    return true;
  } catch { return false; }
}

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

// ---- M0a buttons: muted "moment" messages ------------------------------------
// Contract (luna core): GET  {BASE}/api/conversations       → newest conversation
//                       POST {BASE}/api/conversations/{id}/messages
//                            {content, kind:"muted", channel:"moment", title}
// The agent gets an in-voice reaction turn; the text carries the object id so
// the reaction lands on the right thing.

let toastTimer = null;
function toast(msg, err) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.toggle('err', !!err);
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 4000);
}

async function lunaApi(path, opts, _retried) {
  const headers = Object.assign({}, (opts && opts.headers) || {});
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
  const res = await fetch(`${BASE}${path}`, Object.assign({}, opts, { headers }));
  if (res.status === 401 && !_retried) {
    if (await requestFreshToken(TOKEN)) return lunaApi(path, opts, true);
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function conversationId() {
  // Tolerate both shapes: bare array or {conversations:[...]} / {items:[...]}.
  const raw = await lunaApi('/api/conversations');
  const list = Array.isArray(raw) ? raw : (raw.conversations || raw.items || []);
  if (!list.length) {
    const made = await lunaApi('/api/conversations', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    return made.id;
  }
  const sorted = list.slice().sort((a, b) =>
    String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')));
  return sorted[0].id;
}

async function sendMoment(btn, content, title, tools) {
  const group = btn.closest('.actions');
  const btns = group ? [...group.querySelectorAll('button')] : [btn];
  btns.forEach((b) => { b.disabled = true; });
  try {
    const cid = await conversationId();
    // tools (063): the reaction turn is tool-free by default — buttons that
    // need the agent to RECORD the click name the tools it may call.
    await lunaApi(`/api/conversations/${cid}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, kind: 'muted', channel: 'moment', title,
                             ...(tools && tools.length ? { tools } : {}) }),
    });
    toast('Sent — check chat');
  } catch (err) {
    btns.forEach((b) => { b.disabled = false; });
    toast(`Could not send (${err.message})`, true);
  }
}

// The button texts name the object AND the click, so the agent's reaction turn
// has everything it needs without guessing.
const SAY = {
  confirm: (id) => `The owner clicked "Confirm" on the mission statement (mission id ${id}). ` +
    `Record the confirmation now (mission_confirm) and say what happens next.`,
  changeMission: (id) => `The owner clicked "Change it" on the mission statement (mission id ${id}). ` +
    `Do not confirm it. Ask the owner in chat what should change, in their words.`,
  go: (id, what) => `The owner clicked "Go ahead" on the queued step "${what}" (next_step id ${id}). ` +
    `This click is the owner's explicit approval — start the step now ` +
    `(next_step_start with owner_ok true) and leave the usual note when it lands.`,
  changeStep: (id, what) => `The owner clicked "Change it" on the queued step "${what}" (next_step id ${id}). ` +
    `Do not start it. Ask the owner in chat what should be different.`,
  approve: (id) => `The owner clicked "Approve" on the setup plan (mission id ${id}). ` +
    `Record the plan approval (advance the setup stage) and say what you'll do first.`,
  approveAutomation: (id) => `The owner clicked "Approve" on the automation's sample runs (automation id ${id}). ` +
    `This click is their sign-off — record it now (automation_signoff) and say in one line ` +
    `that it starts under extra watch.`,
};

// Tools each button's reaction turn may call (063) — recording tools plus the
// status line. Talk-only buttons (Change it) stay tool-free on purpose.
const MOMENT_TOOLS = {
  confirm: ['mission_confirm', 'current_state_set'],
  go: ['next_step_start', 'current_state_set'],
  approve: ['phase_advance', 'stage_set', 'current_state_set'],
  approveAutomation: ['automation_signoff', 'current_state_set'],
};

// ---- render -------------------------------------------------------------------

function render() {
  const o = DATA;
  show('loading', false);
  if (o.blocked) { renderBlocked(o.blocked); return; }
  const j = o.journey;
  if (!j) { show('blocked', false); show('app', false); show('empty', true); return; }
  show('blocked', false); show('empty', false); show('app', true);

  const has = (s) => (j.sections || []).includes(s);
  renderHero(j.hero, o);
  renderJourney(j.journey, j.dial);
  renderNowNext(j.now_next);
  show('waiting-panel', has('waiting')); if (has('waiting')) renderWaiting(j.waiting);
  show('services-panel', has('services')); if (has('services')) renderServices(j.services);
  show('when-panel', has('happens_when')); if (has('happens_when')) renderWhen(j.happens_when);
  show('wins-panel', has('wins')); if (has('wins')) renderWins(j.wins);
  show('rules-panel', has('rules')); if (has('rules')) renderRules(j.rules);

  $('foot-note').textContent = `plugin-curiosity ${o.plugin_version} · the machinery lives in the Operational dashboard tab`;
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

// 1 · hero — the mission in the agent's words, owner's words underneath,
// intake Q&A behind a fold. Unconfirmed → Confirm / Change it buttons (M0a).
function renderHero(h, o) {
  $('hero-statement').textContent = h.statement;
  show('hero-confirmed', !!h.confirmed);
  show('hero-actions', !h.confirmed);
  if (h.confirmed) {
    $('hero-confirmed').innerHTML =
      `✓ <b>You confirmed this</b>${h.confirmed_date ? ` · ${esc(h.confirmed_date)}` : ''}`;
  } else {
    const bc = $('btn-confirm'), bx = $('btn-change-mission');
    bc.disabled = false; bx.disabled = false;
    bc.onclick = () => sendMoment(bc, SAY.confirm(h.mission_id), 'Mission confirmed', MOMENT_TOOLS.confirm);
    bx.onclick = () => {
      // 0.16.1: prefer handing the owner the composer (luna 065); muted
      // moment only on cores without the bridge.
      if (!prefillChat('Change the mission: ')) {
        sendMoment(bx, SAY.changeMission(h.mission_id), 'Mission change requested');
      }
    };
  }
  show('hero-said', !!h.you_said);
  if (h.you_said) $('hero-said').innerHTML = `<i>You said:</i> “${esc(h.you_said)}”`;
  const intake = h.intake || [];
  show('howwegothere', intake.length > 0);
  if (intake.length) {
    $('howwegothere-label').textContent = 'How we got here — what I asked, and why';
    $('convo').innerHTML = intake.map((q) =>
      `<div class="luna">${esc(q.you)}</div>` +
      (q.because ? `<div class="you">${esc(q.because)}</div>` : '')
    ).join('');
  }
}

// 2 · the adoption journey rail + the autonomy dial in plain words (11.005)
function renderJourney(j, dial) {
  $('journey-headline').textContent = j.headline;
  $('journey-support').textContent = j.support || '';
  show('journey-support', !!j.support);
  $('journey-rail').innerHTML = j.steps.map((s) => {
    const glyph = s.state === 'done' ? '✓' : '';
    return `<div class="step ${esc(s.state)}">` +
      `<div class="sdot">${glyph}</div>` +
      `<div class="slabel">${esc(s.label)}</div>` +
      `<div class="swhen">${esc(s.when || '')}</div></div>`;
  }).join('');
  $('journey-answers').textContent = j.answers || '';
  show('dial', !!dial);
  if (dial) $('dial').innerHTML =
    `Autonomy right now: <b>${esc(dial.words)}</b> — ${esc(dial.detail)} ${esc(dial.revoke)}`;
}

// 3 · now & next — the running card (live pulse) and the queued card with the
// Go ahead / Change it buttons (M0a).
function stepRows(c, extra) {
  const rows = [
    ['Why', c.why], ['You’ll get', c.produces], ['Costs about', c.cost],
  ].concat(extra || []);
  return `<div class="rows">` + rows.filter(([, v]) => v).map(([k, v]) =>
    `<div class="r"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`
  ).join('') + `</div>`;
}

function renderNowNext(n) {
  const grid = $('now-grid');
  const cards = [];
  if (n.running) {
    const c = n.running;
    cards.push(`<div class="stepcard running">` +
      `<div class="tag"><span class="live"></span>Running now${c.running_for ? ` · ${esc(c.running_for)}` : ''}</div>` +
      `<h3>${esc(c.what)}</h3>` + stepRows(c) + `</div>`);
  }
  if (n.queued) {
    const c = n.queued;
    cards.push(`<div class="stepcard queued">` +
      `<div class="tag">Up next — waiting for your go-ahead</div>` +
      `<h3>${esc(c.what)}</h3>` + stepRows(c) +
      `<div class="actions">` +
      `<button class="btn primary" data-go="${esc(c.id)}" data-what="${esc(c.what)}">Go ahead</button>` +
      `<button class="btn" data-change="${esc(c.id)}" data-what="${esc(c.what)}">Change it</button>` +
      `</div>` +
      (c.hint ? `<div class="hint">${esc(c.hint)}</div>` : '') + `</div>`);
  }
  grid.innerHTML = cards.join('');
  show('nownext-empty', !cards.length);
  if (!cards.length) $('nownext-empty').textContent = n.empty_note || '';
  grid.querySelectorAll('[data-go]').forEach((b) => {
    b.onclick = () => sendMoment(b, SAY.go(b.dataset.go, b.dataset.what), 'Go-ahead given', MOMENT_TOOLS.go);
  });
  grid.querySelectorAll('[data-change]').forEach((b) => {
    b.onclick = () => {
      if (!prefillChat(`Change this step: ${b.dataset.what} — `)) {
        sendMoment(b, SAY.changeStep(b.dataset.change, b.dataset.what), 'Step change requested');
      }
    };
  });
}

// 4 · waiting on you — each blocker named by its unlock; the shared plan
// gets an Approve button (M0a).
function renderWaiting(w) {
  $('waiting-headline').textContent = w.headline;
  $('waits').innerHTML = w.items.map((it, i) => {
    const btn = it.action === 'approve'
      ? `<button class="btn primary" data-approve="${esc(it.object_id)}" data-i="${i}">Approve</button>`
      : it.action === 'approve_automation'
        ? `<button class="btn primary" data-approve-automation="${esc(it.object_id)}" data-i="${i}">Approve</button>` : '';
    const unlock = it.unlock ? ` <span class="unlock">→ unlocks <i>${esc(it.unlock)}</i></span>` : '';
    const cost = it.cost ? ` <span class="unlock">· ${esc(it.cost)}</span>` : '';
    return `<div class="wait"><span class="dot"></span>` +
      `<span><b>${esc(it.text)}</b>${unlock}${cost}</span>${btn}</div>`;
  }).join('');
  $('waiting-keeps').textContent = w.keeps || '';
  show('waiting-keeps', !!w.keeps);
  $('waits').querySelectorAll('[data-approve]').forEach((b) => {
    b.onclick = () => {
      b.disabled = true;
      sendMoment(b, SAY.approve(b.dataset.approve), 'Plan approved', MOMENT_TOOLS.approve);
    };
  });
  $('waits').querySelectorAll('[data-approve-automation]').forEach((b) => {
    b.onclick = () => {
      b.disabled = true;
      sendMoment(b, SAY.approveAutomation(b.dataset.approveAutomation),
        'Sign-off recorded', MOMENT_TOOLS.approveAutomation);
    };
  });
}

// 5 · what I run for you (lands with phase07 automations; the payload is a
// bare list until then — tolerate both shapes)
function renderServices(s) {
  const items = Array.isArray(s) ? s : (s.items || []);
  $('services-headline').textContent = (!Array.isArray(s) && s.headline) || 'Quiet machinery, visible on demand';
  $('sys').innerHTML = items.map((it) =>
    `<div class="sys-row"><span class="sname"><b>${esc(it.name)}</b>` +
    (it.sub ? ` <span class="ssub">${esc(it.sub)}</span>` : '') + `</span>` +
    `<span class="state ${esc(it.state)}">${esc(it.state_label || it.state)}</span></div>`
  ).join('');
}

// 6 · what happens when — honest units: my minutes, your unlocks, real dates
function renderWhen(hw) {
  $('when-headline').textContent = hw.headline;
  $('tl').innerHTML = hw.rows.map((r) =>
    `<div class="tl-row${r.dimmed ? ' dimmed' : ''}">` +
    `<span class="when ${esc(r.tone)}">${esc(r.when)}</span>` +
    `<span class="what"><b>${esc(r.what)}</b>` +
    (r.sub ? ` <span class="sub">${esc(r.sub)}</span>` : '') + `</span></div>`
  ).join('');
}

// 7 · what you got so far — wins with evidence links
function renderWins(w) {
  $('wins-headline').textContent = w.headline;
  $('wins').innerHTML = w.items.map((it) =>
    `<div class="win"><span class="wdot"></span>` +
    `<span><b>${esc(it.title)}</b>` +
    (it.sub ? ` <span class="wsub">${esc(it.sub)}</span>` : '') +
    (it.when ? ` <span class="wsub">· ${esc(it.when)}</span>` : '') + `</span>` +
    (it.link ? `<a href="${esc(it.link)}" target="_blank" rel="noopener">open ↗</a>` : '') +
    `</div>`
  ).join('');
}

// 8 · my rules strip (lands with phase08 boundaries)
function renderRules(r) {
  $('rules-list').innerHTML = (r.items || []).map(esc).join('<i>·</i>');
  $('rules-count').textContent = r.count_line || '';
}

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

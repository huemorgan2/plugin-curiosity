"""journey.py — the owner-facing Missions surface payload (11.004/M4, 0.16.0).

One pure builder, `build_journey`, feeds the rebuilt Missions tab: journey,
not dashboard. Eight blocks, progressively disclosed — a section serializes
only when its data exists, so day one is exactly mission + journey + now &
next and the page grows as the relationship does.

Everything here is OWNER WORDS. Internal shorthand (stage codes, rung
numbers, card statuses, horizon kind enums) never serializes — the builder
translates each into a plain sentence before it leaves this module, and
tests/test_journey.py scans the serialized payload to keep it that way.

The machinery view (abilities, gap board, heartbeats, JD blocks, activity)
stays on the Operational tab — this module deliberately reads only what the
owner-facing page needs.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .scopes import SETUP_STAGES

# --- 11.005: the autonomy dial in plain words --------------------------------
# Keyed by rung, but the NUMBER never serializes — only the words do.
RUNG_WORDS = {
    1: (
        "I ask before anything new",
        "Every new step waits for your go-ahead.",
    ),
    2: (
        "I announce, then act",
        "I say what I'm about to do and give you a window to redirect before I start.",
    ),
    3: (
        "I act on the routine, ask on the new",
        "Agreed routines run on their own; anything new is announced first.",
    ),
    4: (
        "I run the job",
        "I work on my own and report; you steer with feedback.",
    ),
}
REVOKE_SENTENCE = (
    "You can pull this back to asking-first anytime — one sentence in chat."
)


def dial_words(rung: int) -> dict[str, str]:
    """The 11.005 dial: rung as plain words + the revoke promise. Unknown
    rungs clamp to the nearest defined edge — the dial never goes blank."""
    r = min(max(int(rung or 1), 1), max(RUNG_WORDS))
    words, detail = RUNG_WORDS[r]
    return {"words": words, "detail": detail, "revoke": REVOKE_SENTENCE}


def rung_drop_sentence(new_rung: int, dropped: bool) -> str:
    """What the agent says out loud after a visible error (11.005): the drop
    is announced, never silent — and never phrased as a number."""
    words = RUNG_WORDS[min(max(int(new_rung or 1), 1), max(RUNG_WORDS))][0]
    if dropped:
        return (
            f"Because of this, I've moved my own autonomy back a notch — from now on, "
            f"{words.lower()}. I'll re-earn it with clean work; you can change it "
            "anytime with one sentence."
        )
    return (
        "I'm already at asking-first, and I'm staying there until this is solid again."
    )


# --- the six-step adoption journey ------------------------------------------
# Display steps, NOT the internal stage ladder: each is a question the owner
# is entitled to ask, and each derives from real recorded facts.
STEP_DEFS = (
    ("Hear", "did she hear me?"),
    ("Reflect", "did she understand what I actually want?"),
    ("Prove", "is she any good?"),
    ("Agree", "do I agree with how she'll do the job?"),
    ("Earn", "how much rope do I give her?"),
    ("Own", "does it run without me?"),
)

# The one-line tail after the current step's question.
_STEP_ANSWER_TAIL = {
    0: "your mission was saved the moment you said it.",
    1: "confirm my restatement or push back — nothing deep runs before your yes.",
    2: "I prove myself with a first win before asking you for anything.",
    3: "my job description waits for your OK — nothing is agreed until you agree.",
    4: "every access I ask for rides a win you already received.",
    5: "regular check-ins keep flowing, and you can pull any of it back anytime.",
}

_STEP_HEADLINES = {
    0: "You gave me the mission",
    1: "Checking I heard you right",
    2: "Proving myself — your first win comes before any ask",
    3: "The plan is on your desk",
    4: "Earning the setup",
    5: "Running the job — you own the dial",
}


def _short_date(iso: str | None) -> str:
    """'Jul 28' from an ISO timestamp — the journey rail's date stamps."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    return f"{('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')[dt.month - 1]} {dt.day}"


def _stage_index(stage: str | None) -> int:
    try:
        return SETUP_STAGES.index(stage)
    except (ValueError, TypeError):
        return -1


def derive_steps(
    mission: dict[str, Any], first_win_at: str | None
) -> tuple[list[dict[str, Any]], int]:
    """The 6 display steps from recorded facts (testable unit 3):

    Hear    — the mission row exists (it always does here).
    Reflect — the owner confirmed (confirmed_at).
    Prove   — the first value-log win landed.
    Agree   — the job description was approved (stage at/past approval).
    Earn    — the rest of setup; current whenever 1-4 are done and the
              phase is still setup.
    Own     — the work phase.

    Steps are judged independently (weird histories keep their true done
    marks) and "now" is the FIRST not-done step — a mission that confirmed
    but never delivered value points at Prove, no matter the stage.
    """
    in_work = mission.get("agent_phase") == "work"
    done = [
        True,  # Hear — a saved mission is what got us a row at all
        bool(mission.get("confirmed_at")),
        bool(first_win_at),
        _stage_index(mission.get("setup_stage")) >= 3,  # approval ratified
        in_work,  # Earn completes only when setup ends
        False,  # Own is a standing state, never "done"
    ]
    when_done = [
        _short_date(mission.get("created_at")),
        _short_date(mission.get("confirmed_at")),
        _short_date(first_win_at),
        _short_date(mission.get("stage_entered_at")),
        _short_date(mission.get("phase_entered_at")),
        "",
    ]
    current = next((i for i, d in enumerate(done) if not d), len(done) - 1)
    steps: list[dict[str, Any]] = []
    for i, (label, _q) in enumerate(STEP_DEFS):
        if done[i]:
            state, when = "done", when_done[i]
        elif i == current:
            state, when = "now", "now"
        else:
            state, when = "todo", ("your call" if i == len(STEP_DEFS) - 1 else "")
        steps.append({"label": label, "state": state, "when": when})
    return steps, current


# --- honest minutes ----------------------------------------------------------

_MIN_RE = re.compile(r"(\d+)\s*(?:-|–|to\s+)?(\d+)?\s*min", re.IGNORECASE)
_HOUR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to\s+)?(\d+(?:\.\d+)?)?\s*h(?:our)?", re.IGNORECASE)


def minutes_of(text: str | None) -> int | None:
    """Parse '~4 min', 'about 60 to 90 minutes', '1.5 h' into minutes (the
    midpoint of a range). None when the text names no duration — the tally
    only counts what was actually said."""
    t = text or ""
    m = _MIN_RE.search(t)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        return round((lo + hi) / 2)
    h = _HOUR_RE.search(t)
    if h:
        lo = float(h.group(1))
        hi = float(h.group(2)) if h.group(2) else lo
        return round((lo + hi) / 2 * 60)
    return None


def _elapsed_minutes(start_iso: str | None, end_iso: str | None, cap: int = 180) -> int | None:
    try:
        a = datetime.fromisoformat(str(start_iso))
        b = datetime.fromisoformat(str(end_iso))
    except (ValueError, TypeError):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=UTC)
    if b.tzinfo is None:
        b = b.replace(tzinfo=UTC)
    mins = round((b - a).total_seconds() / 60)
    if mins <= 0:
        return None
    return min(mins, cap)  # a card left open across a night is not "my work"


# --- block builders ----------------------------------------------------------


def _hero(
    mission: dict[str, Any], intake: list[dict[str, Any]]
) -> dict[str, Any]:
    origin = (mission.get("origin_statement") or "").strip()
    statement = (mission.get("statement") or "").strip()
    return {
        "statement": statement,
        # the owner's words ride along only when the restatement changed them
        "you_said": origin if origin and origin != statement else "",
        "confirmed": bool(mission.get("confirmed_at")),
        "confirmed_date": _short_date(mission.get("confirmed_at")),
        "mission_id": mission.get("id"),
        # [{you, because}] — the setup answers that shaped the mission
        "intake": intake,
    }


def _journey_block(
    mission: dict[str, Any],
    first_win_at: str | None,
    waiting_count: int,
) -> dict[str, Any]:
    steps, current = derive_steps(mission, first_win_at)
    headline = _STEP_HEADLINES[current]
    if current == 4 and waiting_count:
        thing = "thing" if waiting_count == 1 else "things"
        headline = f"Earning the setup — {waiting_count} {thing} waiting on you"
    question, tail = STEP_DEFS[current][1], _STEP_ANSWER_TAIL[current]
    return {
        "headline": headline,
        "support": (
            "Each step answers one question you're entitled to ask. "
            "We only move when you're ready."
        ),
        "steps": steps,
        "answers": f"“{question}” — {tail}",
    }


def _card(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": step.get("id"),
        "what": step.get("what") or "",
        "why": step.get("why") or "",
        "produces": step.get("produces") or "",
        "cost": step.get("cost_text") or "",
    }


def _now_next(
    next_steps: list[dict[str, Any]],
    mission: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    running = next((s for s in next_steps if s.get("status") == "running"), None)
    queued = next((s for s in next_steps if s.get("status") == "proposed"), None)
    out: dict[str, Any] = {"running": None, "queued": None, "empty_note": ""}
    if running is not None:
        card = _card(running)
        started = running.get("started_at")
        mins = _elapsed_minutes(started, now.isoformat()) if started else None
        card["running_for"] = f"started {mins} min ago" if mins is not None else "in progress"
        out["running"] = card
    if queued is not None:
        card = _card(queued)
        hint = "If you say nothing, I'll go ahead on my own and leave a note — you can stop me anytime."
        try:
            wu = datetime.fromisoformat(str(queued.get("wait_until")))
            if wu.tzinfo is None:
                wu = wu.replace(tzinfo=UTC)
            left = (wu - now).total_seconds() / 3600
            if left > 0:
                approx = max(1, round(left))
                hint = (
                    f"No answer? I'll start on my own in about {approx} h "
                    "and leave a note — you can stop me anytime."
                )
        except (ValueError, TypeError):
            pass
        card["hint"] = hint
        out["queued"] = card
    if running is None and queued is None:
        if mission.get("agent_phase") != "work" and not next_steps:
            out["empty_note"] = (
                "Next up: I read everything we agreed and set the job up properly — "
                "you'll see each step here before it runs."
            )
        else:
            out["empty_note"] = (
                "Between steps — the next card lands here before anything is spent."
            )
    return out


def _waiting(
    loops_open: list[dict[str, Any]], mission: dict[str, Any]
) -> dict[str, Any] | None:
    items: list[dict[str, Any]] = []
    for lp in loops_open:
        if lp.get("kind") == "ask":
            items.append(
                {
                    "text": lp.get("statement") or "",
                    "unlock": lp.get("unlock") or "",
                    "cost": lp.get("human_cost") or "",
                    "action": "",
                    "object_id": lp.get("id"),
                }
            )
        elif "owner" in (lp.get("who") or "").lower():
            items.append(
                {
                    "text": lp.get("statement") or "",
                    "unlock": lp.get("unlock") or "",
                    "cost": lp.get("human_cost") or "",
                    "action": "",
                    "object_id": lp.get("id"),
                }
            )
    # the plan-approval gate gets a real button (M0a): Approve posts a muted
    # moment message carrying the mission id
    if mission.get("agent_phase") == "setup" and mission.get("setup_stage") == "S2":
        items.append(
            {
                "text": "Read my job description and approve it — or say what you'd change.",
                "unlock": "the rest of setup, and the first real work",
                "cost": "about 2 minutes",
                "action": "approve",
                "object_id": mission.get("id"),
            }
        )
    if not items:
        return None
    n = len(items)
    return {
        "headline": (
            "One thing only you can unlock"
            if n == 1
            else f"{n} things only you can unlock"
        ),
        "items": items,
        "keeps": "Nothing is stuck — everything that doesn't need these keeps moving.",
    }


# what-happens-when: unlocks-first spine (phase04 learning — in a mission
# with no real deadline, 0/4 kickoff goals carry dates; whose-move rows and
# agent-minutes ARE the timeline, the date row is the rare case)
_KIND_ORDER = ("awaiting_approval", "on_unlock", "agent_minutes", "date", "rhythm")


def _when_phrase(kind: str, ref: str, target_date: str) -> tuple[str, str]:
    """(when-column text, tone) per horizon — the enum itself never leaves."""
    ref = (ref or "").strip()
    if kind == "awaiting_approval":
        return "After your OK", "you"
    if kind == "on_unlock":
        return (f"Once “{ref}” lands" if ref else "Once its unlock lands"), "you"
    if kind == "agent_minutes":
        if ref.isdigit():
            return f"~{ref} min of my work", "clock"
        return (f"{ref} of my work" if ref else "My own working time"), "clock"
    if kind == "date":
        return (f"By {target_date}" if target_date else "On a real date"), "clock"
    if kind == "rhythm":
        return (ref.capitalize() if ref else "On a rhythm"), "clock"
    return "", ""


def _happens_when(
    goals_list: list[dict[str, Any]], mission: dict[str, Any]
) -> dict[str, Any] | None:
    rows: list[dict[str, Any]] = []
    open_goals = [g for g in goals_list if g.get("status") in ("active", "stalled")]
    for kind in _KIND_ORDER:
        for g in open_goals:
            if (g.get("horizon_kind") or "") != kind:
                continue
            when, tone = _when_phrase(kind, g.get("horizon_ref"), g.get("target_date"))
            sub = (g.get("expected_result") or g.get("why") or "").strip()
            rows.append(
                {
                    "when": when,
                    "tone": tone,
                    "what": g.get("statement") or "",
                    "sub": sub,
                    "dimmed": False,
                }
            )
    if not rows:
        return None
    if mission.get("agent_phase") != "work":
        rows.append(
            {
                "when": "When you say so",
                "tone": "",
                "what": "Setup ends and the real work begins — never before you choose it",
                "sub": "",
                "dimmed": True,
            }
        )
    return {
        "headline": "Promises in honest units — my minutes, your unlocks, real dates only when real",
        "rows": rows,
    }


def _wins(
    value_log: list[dict[str, Any]],
    next_steps: list[dict[str, Any]],
    loops_all: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not value_log:
        return None
    entries = sorted(
        value_log, key=lambda v: str(v.get("delivered_at") or ""), reverse=True
    )
    items = []
    for v in entries[:6]:
        ev = (v.get("evidence") or "").strip()
        items.append(
            {
                "title": v.get("statement") or "",
                "sub": "" if ev.startswith("http") else ev,
                "link": ev if ev.startswith("http") else "",
                "when": _short_date(v.get("delivered_at")),
            }
        )
    # my minutes: what each finished card SAID it would cost; the clamped
    # wall-clock only when the card named no duration
    agent_minutes = 0
    for st in next_steps:
        if st.get("status") != "done":
            continue
        mins = minutes_of(st.get("cost_text"))
        if mins is None:
            mins = _elapsed_minutes(st.get("started_at"), st.get("finished_at"))
        agent_minutes += mins or 0
    # your minutes: the human cost named on asks you already answered
    owner_minutes = 0
    for lp in loops_all:
        if lp.get("kind") == "ask" and lp.get("status") in ("answered", "closed"):
            owner_minutes += minutes_of(lp.get("human_cost")) or 0
    n = len(value_log)
    parts = [f"{n} win{'s' if n != 1 else ''}"]
    if agent_minutes:
        parts.append(f"~{agent_minutes} minutes of my work")
    if owner_minutes:
        parts.append(f"you spent ~{owner_minutes} minutes")
    return {"headline": " · ".join(parts), "items": items}


# --- the assembly ------------------------------------------------------------


def build_journey(
    *,
    mission: dict[str, Any] | None,
    goals_list: list[dict[str, Any]],
    loops_open: list[dict[str, Any]],
    loops_all: list[dict[str, Any]],
    value_log: list[dict[str, Any]],
    next_steps: list[dict[str, Any]],
    intake: list[dict[str, Any]],
    services: list[dict[str, Any]] | None = None,
    rules: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """The Missions-tab payload: 8 blocks, progressively disclosed.

    `services` (what I run for you) arrives with the automation loop
    (phase07) and `rules` (my rules strip) with boundaries (phase08) — both
    default empty and their sections stay hidden until then.
    """
    if mission is None:
        return None
    now = now or datetime.now(UTC)

    first_win_at = min(
        (str(v.get("delivered_at")) for v in value_log if v.get("delivered_at")),
        default=None,
    )
    waiting = _waiting(loops_open, mission)
    waiting_count = len(waiting["items"]) if waiting else 0

    out: dict[str, Any] = {
        "hero": _hero(mission, intake),
        "journey": _journey_block(mission, first_win_at, waiting_count),
        "now_next": _now_next(next_steps, mission, now),
        "waiting": waiting,
        "services": services or [],
        "happens_when": _happens_when(goals_list, mission),
        "wins": _wins(value_log, next_steps, loops_all),
        "rules": rules,
        "dial": dial_words(mission.get("autonomy_rung") or 1),
    }
    sections = ["mission", "journey", "now_next"]
    if out["waiting"]:
        sections.append("waiting")
    if out["services"]:
        sections.append("services")
    if out["happens_when"]:
        sections.append("happens_when")
    if out["wins"]:
        sections.append("wins")
    if out["rules"]:
        sections.append("rules")
    out["sections"] = sections
    return out

"""automations.py — the automation loop (11.006/M5): build → sample sign-off
→ hypercare → run. Every automation is a first-class object the owner can see
on the Missions pane ("What I run for you").

The lifecycle is enforced in the tool layer (flows belong here, not in
prose — handlers refuse out-of-order calls with steering hints):

* **building** — the agent may not leave this state without the go-live gate:
  a kill switch (how the owner stops it), a measurable target, and failure
  detection (how a bad run gets noticed) must all be named.
* **awaiting_your_signoff** — `automation_signoff_request` posts N real
  sample runs (real inputs + would-have outputs). No autonomous run happens
  before `automation_signoff` records the owner's approval — or an explicit
  waiver, stored distinctly (`signoff_kind='waived'`, note required).
* **hypercare** — extra watch: every run is double-checked and reported via
  `automation_run_report`. Exit is promotion math only: `clean_runs` ≥
  CLEAN_RUNS_N across a full weekly cycle with zero corrections; a
  correction RESETS the streak. Promotion is announced with the numbers.
* **running** — a correction here drops the automation straight back to
  hypercare (the streak restarts); it never silently keeps running.
* **paused** — the kill switch (`automation_pause`) works from any live
  state. `automation_resume` re-enters hypercare, never running directly.
* **retired** — needs the owner's explicit OK (adoption alarm → propose
  retiring in chat → `automation_retire(owner_ok=true)`).

Adoption telemetry: `automation_adoption_event` counts owner overrides and
ignored outputs; at ADOPTION_ALARM_N the payload pages the agent — fix the
automation or propose retiring it. An automation nobody uses is a chore.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from luna_sdk import PluginContext, ToolDef
from sqlalchemy import select

from . import gating, telemetry
from .models import Automation, Mission

log = logging.getLogger("plugin-curiosity")

STATES = (
    "building",
    "awaiting_your_signoff",
    "hypercare",
    "running",
    "paused",
    "retired",
)

# hypercare exit: this many consecutive clean runs, across a full weekly
# cycle, with zero corrections since hypercare (re)started
CLEAN_RUNS_N = 5
HYPERCARE_MIN_DAYS = 7

# overrides + ignores at which the adoption alarm pages the agent
ADOPTION_ALARM_N = 3

# owner-facing words per state (the pane's catalog chip): (css, label).
# The enum values above are tool-layer vocabulary; the owner only ever sees
# these plain words.
STATE_WORDS: dict[str, tuple[str, str]] = {
    "building": ("watch", "being built"),
    "awaiting_your_signoff": ("ask", "waiting for your OK"),
    "hypercare": ("watch", "extra watch"),
    "running": ("run", "running"),
    "paused": ("ask", "paused"),
    "retired": ("ask", "retired"),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(t: datetime | None) -> datetime | None:
    """SQLite hands DateTime(timezone=True) back naive — normalize."""
    if t is not None and t.tzinfo is None:
        return t.replace(tzinfo=UTC)
    return t


def _dict(a: Automation) -> dict[str, Any]:
    css, label = STATE_WORDS.get(a.state, ("watch", a.state))
    return {
        "id": str(a.id),
        "what": a.what,
        "scope": a.scope,
        "target": a.target,
        "kill_switch": a.kill_switch,
        "failure_detect": a.failure_detect,
        "state": a.state,
        "state_label": label,
        "state_css": css,
        "samples": a.samples,
        "signoff_at": a.signoff_at.isoformat() if a.signoff_at else None,
        "signoff_kind": a.signoff_kind,
        "signoff_note": a.signoff_note,
        "hypercare_since": (
            a.hypercare_since.isoformat() if a.hypercare_since else None
        ),
        "clean_runs": a.clean_runs,
        "corrections": a.corrections,
        "overrides": a.overrides,
        "ignores": a.ignores,
        "state_note": a.state_note,
        "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
        "promoted_at": a.promoted_at.isoformat() if a.promoted_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def promotion_due(a: Automation, now: datetime) -> bool:
    """Pure hypercare-exit check: streak reached AND a full weekly cycle has
    passed since hypercare (re)started. Corrections already reset the streak,
    so `clean_runs ≥ N` implies zero corrections since the last reset."""
    if a.state != "hypercare" or a.clean_runs < CLEAN_RUNS_N:
        return False
    since = _aware(a.hypercare_since)
    return since is not None and (now - since) >= timedelta(days=HYPERCARE_MIN_DAYS)


class AutomationStore:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def _mission(self, s) -> Mission | None:
        q = (
            select(Mission)
            .where(Mission.active.is_(True))
            .order_by(Mission.created_at.desc())
        )
        return (await s.execute(q)).scalars().first()

    async def _get(self, s, automation_id: str | None) -> Automation:
        """Resolve by id, or the newest non-retired automation when omitted."""
        if automation_id:
            try:
                key = uuid.UUID(str(automation_id))
            except ValueError:
                raise ValueError(
                    f"automation_id {automation_id!r} is not an automation id"
                ) from None
            a = await s.get(Automation, key)
            if a is None:
                raise ValueError(f"no automation with id {automation_id}")
            return a
        q = (
            select(Automation)
            .where(Automation.state != "retired")
            .order_by(Automation.created_at.desc())
        )
        a = (await s.execute(q)).scalars().first()
        if a is None:
            raise ValueError(
                "no automation on file — register one first with "
                "automation_register"
            )
        return a

    async def register(
        self,
        what: str,
        *,
        scope: str = "",
        target: str = "",
        kill_switch: str = "",
        failure_detect: str = "",
    ) -> dict[str, Any]:
        what = (what or "").strip()
        if not what:
            raise ValueError(
                "an automation needs `what` — the one-line job it does"
            )
        async with self._sf() as s:
            m = await self._mission(s)
            if m is None:
                raise ValueError("no active mission — set a mission first")
            a = Automation(
                mission_id=m.id,
                what=what,
                scope=(scope or "").strip(),
                target=(target or "").strip(),
                kill_switch=(kill_switch or "").strip(),
                failure_detect=(failure_detect or "").strip(),
            )
            s.add(a)
            await s.commit()
            await s.refresh(a)
            return _dict(a)

    def _golive_gaps(self, a: Automation) -> list[str]:
        gaps = []
        if not a.kill_switch.strip():
            gaps.append(
                "kill_switch — how the owner stops it, in one plain sentence"
            )
        if not a.target.strip():
            gaps.append("target — the measurable result it exists to hit")
        if not a.failure_detect.strip():
            gaps.append(
                "failure_detect — how a bad run gets noticed without the "
                "owner checking"
            )
        return gaps

    async def signoff_request(
        self, automation_id: str | None = None, *, samples: str = ""
    ) -> dict[str, Any]:
        samples = (samples or "").strip()
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state != "building":
                raise ValueError(
                    f"automation is {a.state!r} — a sign-off request only "
                    "makes sense from 'building'"
                )
            gaps = self._golive_gaps(a)
            if gaps:
                raise ValueError(
                    "go-live gate: this automation cannot leave 'building' "
                    "yet — missing " + "; ".join(gaps) + ". Set them via "
                    "automation_register fields (register a corrected one) "
                    "or fill them before requesting sign-off."
                )
            if not samples:
                raise ValueError(
                    "a sign-off request needs `samples` — a few REAL inputs "
                    "and the outputs this automation would have produced, so "
                    "the owner judges actual work, not a promise"
                )
            a.samples = samples
            a.state = "awaiting_your_signoff"
            await s.commit()
            await s.refresh(a)
            d = _dict(a)
            d["next"] = (
                "the sample runs are on the owner's desk — they approve on "
                "the Missions pane (or in chat), or say what to change. Do "
                "NOT run this automation autonomously before "
                "automation_signoff records their OK (or an explicit waiver)."
            )
            return d

    async def signoff(
        self,
        automation_id: str | None = None,
        *,
        waived: bool = False,
        note: str = "",
    ) -> dict[str, Any]:
        note = (note or "").strip()
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state != "awaiting_your_signoff":
                raise ValueError(
                    f"automation is {a.state!r} — sign-off applies to "
                    "'awaiting_your_signoff' (request sign-off first with "
                    "automation_signoff_request)"
                )
            if waived and not note:
                raise ValueError(
                    "a waiver needs `note` — the owner's words explicitly "
                    "waiving the sample review; a waiver is recorded "
                    "distinctly from an approval and must be quotable"
                )
            now = _utcnow()
            a.signoff_at = now
            a.signoff_kind = "waived" if waived else "approved"
            a.signoff_note = note
            a.state = "hypercare"
            a.hypercare_since = now
            a.clean_runs = 0
            a.corrections = 0
            await s.commit()
            await s.refresh(a)
            d = _dict(a)
            d["next"] = (
                f"hypercare starts now: double-check every run, report each "
                f"with automation_run_report, and post a daily one-liner. It "
                f"promotes itself after {CLEAN_RUNS_N} clean runs across a "
                f"full week with zero corrections."
            )
            return d

    async def run_report(
        self,
        automation_id: str | None = None,
        *,
        ok: bool = True,
        correction_note: str = "",
    ) -> dict[str, Any]:
        correction_note = (correction_note or "").strip()
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state not in ("hypercare", "running"):
                raise ValueError(
                    f"automation is {a.state!r} — run reports apply to "
                    "'hypercare' and 'running' automations only"
                )
            now = _utcnow()
            a.last_run_at = now
            promoted = False
            if ok:
                a.clean_runs += 1
                if promotion_due(a, now):
                    a.state = "running"
                    a.promoted_at = now
                    promoted = True
            else:
                if not correction_note:
                    raise ValueError(
                        "a failed/corrected run needs `correction_note` — "
                        "what went wrong and what you fixed; corrections are "
                        "data, not embarrassments"
                    )
                a.corrections += 1
                a.state_note = correction_note
                a.clean_runs = 0
                if a.state == "running":
                    # a correction in the wild drops it back to extra watch
                    a.state = "hypercare"
                    a.hypercare_since = now
            await s.commit()
            await s.refresh(a)
            d = _dict(a)
            if promoted:
                d["promoted"] = True
                d["announce"] = (
                    f"'{a.what}' graduates from extra watch: "
                    f"{a.clean_runs} clean runs over "
                    f"{(now - _aware(a.hypercare_since)).days} days, "
                    f"0 corrections since the streak began. It now runs "
                    f"normally — the kill switch stays: {a.kill_switch}"
                )
                d["next"] = (
                    "tell the owner in one line, with these numbers — "
                    "promotion is announced, never silent."
                )
            elif not ok and a.state == "hypercare" and a.promoted_at:
                d["next"] = (
                    "it dropped back to extra watch after a correction — "
                    "say so plainly in one line, no guilt."
                )
            return d

    async def adoption_event(
        self, automation_id: str | None = None, *, kind: str = "override"
    ) -> dict[str, Any]:
        if kind not in ("override", "ignore"):
            raise ValueError("kind must be 'override' or 'ignore'")
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state == "retired":
                raise ValueError("automation is retired — nothing to record")
            if kind == "override":
                a.overrides += 1
            else:
                a.ignores += 1
            await s.commit()
            await s.refresh(a)
            d = _dict(a)
            total = a.overrides + a.ignores
            if total >= ADOPTION_ALARM_N:
                d["alarm"] = (
                    f"adoption alarm: the owner has overridden or ignored "
                    f"'{a.what}' {total} times ({a.overrides} overrides, "
                    f"{a.ignores} ignored outputs). An automation nobody "
                    f"uses is a chore — figure out WHY (ask if you must), "
                    f"then either fix it or propose retiring it "
                    f"(automation_retire after the owner agrees). Do not "
                    f"let it keep running unexamined."
                )
            return d

    async def pause(
        self, automation_id: str | None = None, *, note: str = ""
    ) -> dict[str, Any]:
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state in ("paused", "retired"):
                raise ValueError(f"automation is already {a.state}")
            a.state = "paused"
            a.state_note = (note or "").strip()
            await s.commit()
            await s.refresh(a)
            d = _dict(a)
            d["next"] = (
                "paused — nothing runs until automation_resume, which "
                "re-enters extra watch (never straight back to running)."
            )
            return d

    async def resume(self, automation_id: str | None = None) -> dict[str, Any]:
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state != "paused":
                raise ValueError(f"automation is {a.state!r} — resume applies to 'paused'")
            if a.signoff_at is None:
                # paused before sign-off ever happened — back to the gate
                a.state = "building"
            else:
                a.state = "hypercare"
                a.hypercare_since = _utcnow()
                a.clean_runs = 0
            a.state_note = ""
            await s.commit()
            await s.refresh(a)
            return _dict(a)

    async def retire(
        self,
        automation_id: str | None = None,
        *,
        owner_ok: bool = False,
        note: str = "",
    ) -> dict[str, Any]:
        note = (note or "").strip()
        async with self._sf() as s:
            a = await self._get(s, automation_id)
            if a.state == "retired":
                raise ValueError("automation is already retired")
            if not owner_ok:
                raise ValueError(
                    "retiring needs the owner's explicit OK — propose it in "
                    "chat with the adoption numbers, then pass owner_ok=true "
                    "with their words in `note`"
                )
            if not note:
                raise ValueError(
                    "retiring needs `note` — the owner's words agreeing, so "
                    "the record shows whose call it was"
                )
            a.state = "retired"
            a.state_note = note
            await s.commit()
            await s.refresh(a)
            return _dict(a)

    async def list(self, include_retired: bool = False) -> list[dict[str, Any]]:
        async with self._sf() as s:
            q = select(Automation).order_by(Automation.created_at.desc())
            if not include_retired:
                q = q.where(Automation.state != "retired")
            return [_dict(a) for a in (await s.execute(q)).scalars().all()]


def services_block(automations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The Missions-pane "What I run for you" section — plain state words,
    never lifecycle enums. None while no automation exists (the section stays
    hidden; day one is not a catalog)."""
    items = [
        {
            "name": a["what"],
            "sub": a["target"] or a["scope"] or "",
            "state": a["state_css"],
            "state_label": a["state_label"],
        }
        for a in automations
        if a["state"] != "retired"
    ]
    if not items:
        return None
    n = len(items)
    return {
        "headline": f"What I run for you — {n} automation{'s' if n != 1 else ''}",
        "items": items,
    }


def register_tools(ctx: PluginContext, store: AutomationStore) -> None:
    async def _guard(coro) -> dict[str, Any]:
        try:
            out = await coro
        except ValueError as e:
            return {"error": str(e)}
        await telemetry.emit_ui_event(ctx, "changed", {"what": "automation"})
        return out

    async def _register(
        what: str,
        scope: str = "",
        target: str = "",
        kill_switch: str = "",
        failure_detect: str = "",
    ) -> dict[str, Any]:
        return await _guard(
            store.register(
                what,
                scope=scope,
                target=target,
                kill_switch=kill_switch,
                failure_detect=failure_detect,
            )
        )

    async def _signoff_request(
        automation_id: str = "", samples: str = ""
    ) -> dict[str, Any]:
        return await _guard(
            store.signoff_request(automation_id or None, samples=samples)
        )

    async def _signoff(
        automation_id: str = "", waived: bool = False, note: str = ""
    ) -> dict[str, Any]:
        return await _guard(
            store.signoff(automation_id or None, waived=waived, note=note)
        )

    async def _run_report(
        automation_id: str = "", ok: bool = True, correction_note: str = ""
    ) -> dict[str, Any]:
        return await _guard(
            store.run_report(
                automation_id or None, ok=ok, correction_note=correction_note
            )
        )

    async def _adoption(
        automation_id: str = "", kind: str = "override"
    ) -> dict[str, Any]:
        return await _guard(
            store.adoption_event(automation_id or None, kind=kind)
        )

    async def _pause(automation_id: str = "", note: str = "") -> dict[str, Any]:
        return await _guard(store.pause(automation_id or None, note=note))

    async def _resume(automation_id: str = "") -> dict[str, Any]:
        return await _guard(store.resume(automation_id or None))

    async def _retire(
        automation_id: str = "", owner_ok: bool = False, note: str = ""
    ) -> dict[str, Any]:
        return await _guard(
            store.retire(automation_id or None, owner_ok=owner_ok, note=note)
        )

    async def _state(include_retired: bool = False) -> dict[str, Any]:
        try:
            items = await store.list(include_retired=include_retired)
        except ValueError as e:  # pragma: no cover — list never raises today
            return {"error": str(e)}
        return {"automations": items, "count": len(items)}

    _ID = {
        "type": "string",
        "description": (
            "automation id from automation_register (omit = newest live one)"
        ),
    }
    defs: list[tuple[ToolDef, Any]] = [
        (
            ToolDef(
                name="automation_register",
                description=(
                    "Register an automation you are BUILDING for the owner "
                    "(a standing job that will run without them asking). It "
                    "starts in 'building' and shows on their pane "
                    "immediately. Name what it does, its scope (what it may "
                    "touch), a measurable target, the kill switch (how the "
                    "owner stops it, plain words), and failure detection "
                    "(how a bad run gets noticed) — the last three are the "
                    "go-live gate: without them it can never leave "
                    "'building'."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "what": {
                            "type": "string",
                            "description": "the one-line job this automation does",
                        },
                        "scope": {
                            "type": "string",
                            "description": "what it may touch / act on",
                        },
                        "target": {
                            "type": "string",
                            "description": "the measurable result it exists to hit",
                        },
                        "kill_switch": {
                            "type": "string",
                            "description": (
                                "how the owner stops it, in one plain sentence"
                            ),
                        },
                        "failure_detect": {
                            "type": "string",
                            "description": (
                                "how a bad run gets noticed without the owner "
                                "checking"
                            ),
                        },
                    },
                    "required": ["what"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _register,
        ),
        (
            ToolDef(
                name="automation_signoff_request",
                description=(
                    "Put a built automation on the owner's desk: `samples` "
                    "carries a few REAL inputs and the outputs it would have "
                    "produced, so they judge actual work. Refused while the "
                    "go-live gate is unmet (kill switch + measurable target "
                    "+ failure detection). After this, do NOT run it "
                    "autonomously until automation_signoff records their OK."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "automation_id": _ID,
                        "samples": {
                            "type": "string",
                            "description": (
                                "real sample runs: inputs + would-have "
                                "outputs, owner-readable"
                            ),
                        },
                    },
                    "required": ["samples"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _signoff_request,
        ),
        (
            ToolDef(
                name="automation_signoff",
                description=(
                    "Record the owner's sign-off on an automation's sample "
                    "runs — call this when they approved on the pane or in "
                    "chat. It enters hypercare (extra watch). waived=true "
                    "records an EXPLICIT owner waiver instead ('skip the "
                    "review, just run it') — note with their words is then "
                    "required; never waive on your own initiative."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "automation_id": _ID,
                        "waived": {
                            "type": "boolean",
                            "description": (
                                "the owner explicitly waived the sample "
                                "review (recorded distinctly from approval)"
                            ),
                        },
                        "note": {
                            "type": "string",
                            "description": (
                                "the owner's words (REQUIRED for a waiver)"
                            ),
                        },
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _signoff,
        ),
        (
            ToolDef(
                name="automation_run_report",
                description=(
                    "Report one run of a hypercare/running automation. "
                    "ok=true counts toward promotion (5 clean runs across a "
                    "full week, zero corrections → it promotes itself and "
                    "you announce the numbers). ok=false REQUIRES "
                    "correction_note (what went wrong, what you fixed) — it "
                    "resets the streak, and a running automation drops back "
                    "to extra watch. During hypercare, double-check every "
                    "run before reporting it clean."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "automation_id": _ID,
                        "ok": {
                            "type": "boolean",
                            "description": "the run was clean after your double-check",
                        },
                        "correction_note": {
                            "type": "string",
                            "description": (
                                "REQUIRED when ok=false: what went wrong and "
                                "what you fixed"
                            ),
                        },
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _run_report,
        ),
        (
            ToolDef(
                name="automation_adoption_event",
                description=(
                    "Record that the owner overrode an automation's output "
                    "(kind='override') or ignored it (kind='ignore'). Be "
                    "honest — this is the adoption telemetry. Enough of "
                    "them pages you: fix the automation or propose retiring "
                    "it; an automation nobody uses is a chore."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "automation_id": _ID,
                        "kind": {
                            "type": "string",
                            "enum": ["override", "ignore"],
                            "description": "what the owner did with the output",
                        },
                    },
                    "required": ["kind"],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _adoption,
        ),
        (
            ToolDef(
                name="automation_pause",
                description=(
                    "The kill switch: stop an automation NOW (any live "
                    "state). Use it the moment the owner asks, or when "
                    "failure detection fires and you can't fix it in place. "
                    "Resume later with automation_resume — it re-enters "
                    "extra watch, never straight back to running."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "automation_id": _ID,
                        "note": {
                            "type": "string",
                            "description": "why it stopped (owner-readable)",
                        },
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _pause,
        ),
        (
            ToolDef(
                name="automation_resume",
                description=(
                    "Resume a paused automation. It re-enters extra watch "
                    "(hypercare, streak reset) — a pause is a reason to "
                    "re-earn trust, not a checkpoint to skip past. If it "
                    "was paused before any sign-off, it goes back to "
                    "'building'."
                ),
                parameters={
                    "type": "object",
                    "properties": {"automation_id": _ID},
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _resume,
        ),
        (
            ToolDef(
                name="automation_retire",
                description=(
                    "Retire an automation for good — ONLY after the owner "
                    "explicitly agreed in chat (owner_ok=true, their words "
                    "in note). Propose retirement with the adoption numbers "
                    "when the alarm pages you; never retire silently."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "automation_id": _ID,
                        "owner_ok": {
                            "type": "boolean",
                            "description": "the owner explicitly agreed to retire it",
                        },
                        "note": {
                            "type": "string",
                            "description": "the owner's words agreeing (REQUIRED)",
                        },
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _retire,
        ),
        (
            ToolDef(
                name="automation_state",
                description=(
                    "List your automations with their lifecycle state, "
                    "streaks, and adoption counters. include_retired=true "
                    "adds retired ones."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "include_retired": {
                            "type": "boolean",
                            "description": "include retired automations",
                        }
                    },
                    "required": [],
                },
                policy="auto_approve",
                risk_level="low",
            ),
            _state,
        ),
    ]
    for tool_def, handler in defs:
        ctx.tool_registry.register("plugin-curiosity", gating.stamp_group(tool_def), handler)

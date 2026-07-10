"""SQLAlchemy rows for plugin-curiosity: the mission register and the
reflection log (share_thought's cadence ledger). Namespaced `curiosity_*` —
plugin tables share core's database, so the prefix convention from
plugin-wiki applies."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from luna_sdk import UUID, declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Mission(Base):
    """One row per mission; exactly one `active` row at a time (store-enforced).

    `autonomy_rung` (1-4) and `risk_ceiling` are stored and rendered into the
    prompt, but v1 keeps side-effecting tools approval-gated regardless —
    lifting the ceiling later is a tool-policy flip, not new code.
    """

    __tablename__ = "curiosity_missions"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    autonomy_rung: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    risk_ceiling: Mapped[str] = mapped_column(String(16), default="low", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # phase 9A: the two macro-phases. `agent_phase`: "setup" | "work";
    # `setup_stage`: the furthest RATIFIED setup-arc stage (S0..S5).
    agent_phase: Mapped[str] = mapped_column(String(8), default="setup", nullable=False)
    phase_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    setup_stage: Mapped[str] = mapped_column(String(4), default="S0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Reflection(Base):
    """One row per shared (or queued) thought — the guardrail ledger.

    `kind`: "routine" (counts against the daily cap) | "kickoff" | "dream".
    `status`: "posted" | "queued" (created in quiet hours; drained after).
    """

    __tablename__ = "curiosity_reflections"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), default="routine", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="posted", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Goal(Base):
    """One self-set goal in the pursuit of the mission (phase 8.2).

    Luna commits to goals (goal_set), reports movement (goal_update), and the
    weekly review scores them. `status`: "active" | "done" | "stalled" |
    "dropped". `target_date` is free-form text ("2026-07-20", "end of July") —
    the agent reasons about it; nothing fires on it.
    """

    __tablename__ = "curiosity_goals"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target_date: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    progress_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Scope(Base):
    """One area of the role the agent must become competent in (phase 9A).

    `kind` is one of the seven charter dimensions (see scopes.SCOPE_KINDS).
    `status`: "missing" | "in_progress" | "competent" — BOTH directions are
    legal; competent → in_progress is the refix-backward path when a later
    learning invalidates earlier work.
    """

    __tablename__ = "curiosity_scopes"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="missing", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class PlanChange(Base):
    """One dated, append-only entry in the charter's Plan-changes log
    (phase 9A): added/dropped/reopened + the learning that caused it. The
    living-plan audit trail — the [[role-charter]] page renders these in
    insertion order."""

    __tablename__ = "curiosity_plan_changes"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    entry: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Loop(Base):
    """One open loop — a thread that must never silently die (phase 9B).

    `kind`: "question" | "promise" | "waiting_on" | "handoff" | "ask".
    `who`: "owner" | "self" | a person's name. `status`: "open" | "answered" |
    "closed" | "abandoned" (abandoned REQUIRES a resolution — the stated
    reason the owner sees). Asks additionally carry `unlock` (what the grant
    enables), `human_cost` (what it costs the owner), and `value_ref` (the
    value-log entry the ask rides on) — the ask-economics fields.
    """

    __tablename__ = "curiosity_loops"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    who: Mapped[str] = mapped_column(String(120), default="owner", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    unlock: Mapped[str] = mapped_column(Text, default="", nullable=False)
    human_cost: Mapped[str] = mapped_column(Text, default="", nullable=False)
    value_ref: Mapped[_uuid.UUID | None] = mapped_column(UUID(), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    next_nudge_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    nudge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class ValueEntry(Base):
    """One receipt of value delivered to the owner (phase 9B). Evidence is
    REQUIRED (a wiki slug or artifact link) — the value log is what asks ride
    on, so an unevidenced entry would let the agent pay for asks with air."""

    __tablename__ = "curiosity_value_log"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    linked_ask_id: Mapped[_uuid.UUID | None] = mapped_column(UUID(), nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Flag(Base):
    """Tiny key/value state register (phase 8.1: `install_kickoff_sent`)."""

    __tablename__ = "curiosity_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


ALL_TABLES = (
    Mission.__table__,
    Reflection.__table__,
    Goal.__table__,
    Scope.__table__,
    PlanChange.__table__,
    Loop.__table__,
    ValueEntry.__table__,
    Flag.__table__,
)

# Additive column migrations, applied on every load AFTER create(checkfirst):
# create() skips existing tables, so a 0.6.0 database upgrading in place never
# receives the 9A mission columns from metadata alone. DB-side DEFAULTs make
# the backfill safe for existing rows (mirrors 8.2's spec-drift-repair lesson:
# the upgrade path is the path real owners take).
_MISSION_ADDITIVE_COLUMNS = (
    ("agent_phase", "VARCHAR(8) NOT NULL DEFAULT 'setup'"),
    ("phase_entered_at", "TIMESTAMP WITH TIME ZONE"),
    ("setup_stage", "VARCHAR(4) NOT NULL DEFAULT 'S0'"),
)


def apply_additive_migrations(conn) -> list[str]:
    """Sync callable for `conn.run_sync`: ALTER TABLE ADD COLUMN for any 9A
    mission column missing from an existing database. Idempotent; returns the
    columns it added (empty on a current schema)."""
    from sqlalchemy import inspect, text

    existing = {c["name"] for c in inspect(conn).get_columns("curiosity_missions")}
    added: list[str] = []
    for name, ddl in _MISSION_ADDITIVE_COLUMNS:
        if name not in existing:
            conn.execute(text(f"ALTER TABLE curiosity_missions ADD COLUMN {name} {ddl}"))
            added.append(name)
    return added

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
    # 9.001E: when the current stage was entered — feeds the server-computed
    # stage_age_days (agents have no clock) behind the ratification forcing
    # function. NULL on pre-9.001 rows; age falls back to created_at.
    stage_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # phase 10: the living-draft counter — a role_pivot plan change bumps it
    # in the same transaction; the pane's "draft vN" stamp reads it.
    role_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # phase 10: reserved seam — bound when plugin-wiki ships multi-wiki
    # (mission adoption creates a named wiki and stores its id here).
    wiki_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 0.9.10: one line in the agent's own words — what she's doing right now
    # at the mission level. Shown verbatim in the pane hero; the UI never
    # invents this sentence. current_state_at feeds a server-computed age.
    current_state: Mapped[str] = mapped_column(Text, default="", nullable=False)
    current_state_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    # phase 10 goal-readiness triple: what done looks like, whether the agent
    # HAS what the goal needs (green) / partly (amber) / is missing something
    # (red), and the one-line have/missing explanation the pane renders.
    expected_result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    readiness: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    readiness_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 0.10.0 (goal-engine handover): when plugin-goalseek is the engine, this
    # row becomes a POINTER — goalseek_id names the live goal in goal-seek's
    # tables; the local columns freeze as the open-time snapshot. migrated_at
    # marks rows converted by the one-time migration (idempotence key).
    goalseek_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    migrated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    # phase 10: which ability this scope serves (nullable — pre-10 rows and
    # scopes chartered before the abilities exist stay unattached).
    ability_id: Mapped[_uuid.UUID | None] = mapped_column(UUID(), nullable=True)
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
    # phase 10 materiality rule: "refine" — within-ability learning, revised
    # in place; "role_pivot" — the role's SHAPE changed (bumps
    # missions.role_version in the same transaction, surfaces to the owner).
    kind: Mapped[str] = mapped_column(String(16), default="refine", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Ability(Base):
    """One "Ability to …" item of the role's qualification ladder (phase 10).

    The agent decomposes its job into 3-7 abilities (ability_upsert); each
    ability carries 2-6 concrete subtasks whose statuses roll up to a
    server-computed percent. The natural key is (mission_id, slug-of-title)
    so concurrent re-derivations converge instead of duplicating.
    """

    __tablename__ = "curiosity_abilities"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    why: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="building", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AbilityTask(Base):
    """One concrete subtask under an ability (phase 10). Percent math:
    done=1, in_progress=0.5, missing/blocked=0 — computed server-side only
    (agents never do arithmetic)."""

    __tablename__ = "curiosity_ability_tasks"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    ability_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="missing", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_ref: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
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


class HeartbeatReport(Base):
    """One structured self-report per heartbeat fire (9.002 §5).

    The agent ends every heartbeat fire with heartbeat_report(...) — the
    streak becomes DATA (graduation proposals cite it; the weekly review
    audits report-vs-page drift), and `morale` is the agent's own words
    (personality-voiced, never an enum), shown verbatim in the Missions pane
    behind a server-computed sentiment band."""

    __tablename__ = "curiosity_heartbeats"

    id: Mapped[_uuid.UUID] = mapped_column(UUID(), primary_key=True, default=_uuid.uuid4)
    mission_id: Mapped[_uuid.UUID] = mapped_column(UUID(), nullable=False, index=True)
    streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gaps_open: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wobbles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    morale: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
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
    Ability.__table__,
    AbilityTask.__table__,
    Loop.__table__,
    ValueEntry.__table__,
    HeartbeatReport.__table__,
    Flag.__table__,
)

# Additive column migrations, applied on every load AFTER create(checkfirst):
# create() skips existing tables, so an older database upgrading in place
# never receives new columns from metadata alone. DB-side DEFAULTs make the
# backfill safe for existing rows (mirrors 8.2's spec-drift-repair lesson:
# the upgrade path is the path real owners take).
_ADDITIVE_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "curiosity_missions": (
        ("agent_phase", "VARCHAR(8) NOT NULL DEFAULT 'setup'"),
        ("phase_entered_at", "TIMESTAMP WITH TIME ZONE"),
        ("setup_stage", "VARCHAR(4) NOT NULL DEFAULT 'S0'"),
        # 9.001E
        ("stage_entered_at", "TIMESTAMP WITH TIME ZONE"),
        # phase 10
        ("role_version", "INTEGER NOT NULL DEFAULT 1"),
        ("wiki_id", "VARCHAR(64)"),
        # 0.9.10
        ("current_state", "TEXT NOT NULL DEFAULT ''"),
        ("current_state_at", "TIMESTAMP WITH TIME ZONE"),
    ),
    "curiosity_goals": (
        ("expected_result", "TEXT NOT NULL DEFAULT ''"),
        ("readiness", "VARCHAR(8) NOT NULL DEFAULT ''"),
        ("readiness_note", "TEXT NOT NULL DEFAULT ''"),
        # 0.10.0 goal-engine handover
        ("goalseek_id", "VARCHAR(36) NOT NULL DEFAULT ''"),
        ("migrated_at", "TIMESTAMP WITH TIME ZONE"),
    ),
    "curiosity_scopes": (
        # {UUID} resolves per dialect at apply time — Postgres UUID,
        # everything else CHAR(32) (how sqlalchemy's Uuid stores on SQLite)
        ("ability_id", "{UUID}"),
    ),
    "curiosity_plan_changes": (
        ("kind", "VARCHAR(16) NOT NULL DEFAULT 'refine'"),
    ),
}


def apply_additive_migrations(conn) -> list[str]:
    """Sync callable for `conn.run_sync`: ALTER TABLE ADD COLUMN for any
    column missing from an existing database. Idempotent; returns the columns
    it added as 'table.column' (empty on a current schema). A table absent
    entirely is skipped — table.create(checkfirst=True) runs in the same
    on_load and builds it with the full current schema."""
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    uuid_ddl = "UUID" if conn.dialect.name == "postgresql" else "CHAR(32)"
    added: list[str] = []
    for table, columns in _ADDITIVE_COLUMNS.items():
        if not insp.has_table(table):
            continue
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in columns:
            if name not in existing:
                ddl = ddl.replace("{UUID}", uuid_ddl)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                added.append(f"{table}.{name}")
    return added

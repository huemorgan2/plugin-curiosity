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


class Flag(Base):
    """Tiny key/value state register (phase 8.1: `install_kickoff_sent`)."""

    __tablename__ = "curiosity_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


ALL_TABLES = (Mission.__table__, Reflection.__table__, Goal.__table__, Flag.__table__)

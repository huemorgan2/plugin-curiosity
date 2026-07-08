"""SQLAlchemy rows for plugin-curiosity. Single table: the mission register.
Namespaced `curiosity_missions` (not bare `missions`) — plugin tables share
core's database, so the prefix convention from plugin-wiki applies."""

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


ALL_TABLES = (Mission.__table__,)

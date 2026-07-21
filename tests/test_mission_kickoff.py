"""Mission-kickoff artifact (0.12.0 jobs-dojo bugs 3 & 4):
- the prompt hard-requires consulting already-supplied data before asking;
- a succinct persona gets the compact artifact variant.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text as _sql

from plugin_curiosity import research
from plugin_curiosity.prompts import ALREADY_SUPPLIED, COMPACT_ARTIFACT


@pytest.fixture
def kctx(ctx, sf):
    ctx.db_session_factory = sf
    return ctx


async def _seed_identity(sf, **cols) -> None:
    keys = ", ".join(cols)
    async with sf() as s:
        coldefs = ", ".join(f"{k} TEXT" for k in cols)
        await s.execute(_sql(f"CREATE TABLE IF NOT EXISTS identity ({coldefs})"))
        await s.execute(_sql("DELETE FROM identity"))
        placeholders = ", ".join(f":{k}" for k in cols)
        await s.execute(_sql(f"INSERT INTO identity ({keys}) VALUES ({placeholders})"), cols)
        await s.commit()


def _kickoff_content(ctx):
    posts = [p for p in ctx.muted_posts if p["title"] == research.KICKOFF_TITLE]
    assert len(posts) == 1
    return posts[0]["content"]


# ---- Bug 3: the artifact must not re-ask for supplied data -------------------


def test_kickoff_prompt_forbids_reasking_supplied_data():
    text = research._KICKOFF_CONTENT
    assert ALREADY_SUPPLIED in text
    low = ALREADY_SUPPLIED.lower()
    assert "supplied" in low
    assert "re-read" in low and "re-request" in low


# ---- Bug 4: compact persona detection ---------------------------------------


@pytest.mark.asyncio
async def test_prefers_compact_on_verbosity(kctx, sf):
    await _seed_identity(sf, verbosity="compact")
    assert await research._prefers_compact(kctx) is True


@pytest.mark.asyncio
async def test_prefers_compact_on_free_text_instructions(kctx, sf):
    await _seed_identity(sf, verbosity="normal", instructions="please keep it short")
    assert await research._prefers_compact(kctx) is True


@pytest.mark.asyncio
async def test_no_compact_for_default_persona(kctx, sf):
    await _seed_identity(sf, verbosity="normal", instructions="be thorough")
    assert await research._prefers_compact(kctx) is False


@pytest.mark.asyncio
async def test_no_identity_row_defaults_full(kctx, sf):
    await _seed_identity(sf, verbosity="compact")
    async with sf() as s:
        await s.execute(_sql("DELETE FROM identity"))
        await s.commit()
    assert await research._prefers_compact(kctx) is False


# ---- Bug 4: run_kickoff wires the variant in --------------------------------


@pytest.mark.asyncio
async def test_kickoff_appends_compact_variant(kctx, monkeypatch):
    monkeypatch.setattr(research, "KICKOFF_DELAY_S", 0.0)
    await research.run_kickoff(kctx, "grow signups", compact=True)
    assert COMPACT_ARTIFACT in _kickoff_content(kctx)


@pytest.mark.asyncio
async def test_kickoff_omits_compact_for_default(kctx, monkeypatch):
    monkeypatch.setattr(research, "KICKOFF_DELAY_S", 0.0)
    await research.run_kickoff(kctx, "grow signups", compact=False)
    assert COMPACT_ARTIFACT not in _kickoff_content(kctx)

"""Install kickoff (8.1C): once ever, only while missionless, flag-guarded."""

from __future__ import annotations

import pytest

from plugin_curiosity import INSTALL_KICKOFF_FLAG, _flag_get, maybe_send_install_kickoff
from plugin_curiosity.research import INSTALL_KICKOFF_TITLE


@pytest.fixture
def kctx(ctx, sf):
    ctx.db_session_factory = sf
    return ctx


def _kickoff_posts(ctx):
    return [p for p in ctx.muted_posts if p["title"] == INSTALL_KICKOFF_TITLE]


@pytest.mark.asyncio
async def test_fresh_install_no_mission_sends_once(kctx, store, sf):
    assert await maybe_send_install_kickoff(kctx, store) is True
    posts = _kickoff_posts(kctx)
    assert len(posts) == 1
    assert posts[0]["channel"] == "moment" and posts[0]["source"] == "curiosity"
    # no tools allowlist: the reaction turn just speaks
    assert "tools" not in posts[0]
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) == "1"

    # second load: flag short-circuits, nothing new
    assert await maybe_send_install_kickoff(kctx, store) is False
    assert len(_kickoff_posts(kctx)) == 1


@pytest.mark.asyncio
async def test_mission_already_present_skips_forever(kctx, store, sf):
    async def call(name, **kw):
        return await kctx.tool_registry.registered[name][1](**kw)

    await call("mission_set", statement="grow signups", rung=2)
    kctx.muted_posts.clear()  # drop the mission kickoff moment
    assert await maybe_send_install_kickoff(kctx, store) is False
    assert _kickoff_posts(kctx) == []
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) == "skipped: mission present"


@pytest.mark.asyncio
async def test_core_without_send_retries_next_load(kctx, store, sf):
    kctx.send_muted_message = None
    assert await maybe_send_install_kickoff(kctx, store) is False
    # flag NOT set — the send never happened, so the next load retries
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) is None

    async def send(title, content, **kw):
        kctx.muted_posts.append({"title": title, "content": content, **kw})

    kctx.send_muted_message = send
    assert await maybe_send_install_kickoff(kctx, store) is True
    assert len(_kickoff_posts(kctx)) == 1


@pytest.mark.asyncio
async def test_soft_error_result_does_not_burn_flag(kctx, store, sf):
    """post_muted_message reports failures as {"error": ...} WITHOUT raising —
    notably "no target conversation" on a zero-conversation fresh install.
    The flag must survive for a retry on a later load."""

    async def send(title, content, **kw):
        return {"error": "no target conversation", "responded": False}

    kctx.send_muted_message = send
    assert await maybe_send_install_kickoff(kctx, store) is False
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) is None

    async def send_ok(title, content, **kw):
        kctx.muted_posts.append({"title": title, "content": content, **kw})
        return {"ok": True}

    kctx.send_muted_message = send_ok
    assert await maybe_send_install_kickoff(kctx, store) is True
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) == "1"


@pytest.mark.asyncio
async def test_concurrent_double_load_sends_once(kctx, store, sf):
    """QA found the on-load work running twice in one process (bootstrap +
    serving loop) and both runs interleaving inside the send-then-flag window
    → the moment posted twice. The in-process claim must let exactly one
    through."""
    import asyncio

    async def slow_send(title, content, **kw):
        await asyncio.sleep(0.05)  # hold the send open so the runs interleave
        kctx.muted_posts.append({"title": title, "content": content, **kw})
        return {"ok": True}

    kctx.send_muted_message = slow_send
    results = await asyncio.gather(
        maybe_send_install_kickoff(kctx, store),
        maybe_send_install_kickoff(kctx, store),
    )
    assert sorted(results) == [False, True]
    assert len(_kickoff_posts(kctx)) == 1
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) == "1"


@pytest.mark.asyncio
async def test_failed_send_releases_the_claim(kctx, store, sf):
    """A soft-failed send (zero conversations) must release the in-process
    claim so a later load in the SAME process can retry."""

    async def send_fail(title, content, **kw):
        return {"error": "no target conversation"}

    kctx.send_muted_message = send_fail
    assert await maybe_send_install_kickoff(kctx, store) is False

    async def send_ok(title, content, **kw):
        kctx.muted_posts.append({"title": title, "content": content, **kw})
        return {"ok": True}

    kctx.send_muted_message = send_ok
    assert await maybe_send_install_kickoff(kctx, store) is True
    assert len(_kickoff_posts(kctx)) == 1


async def _seed_identity(sf, setup_completed: int | None) -> None:
    from sqlalchemy import text as _sql

    async with sf() as s:
        await s.execute(_sql("CREATE TABLE IF NOT EXISTS identity (setup_completed BOOLEAN)"))
        await s.execute(_sql("DELETE FROM identity"))
        if setup_completed is not None:
            await s.execute(_sql(f"INSERT INTO identity VALUES ({setup_completed})"))
        await s.commit()


@pytest.mark.asyncio
async def test_setup_in_progress_defers_kickoff_without_burning_flag(kctx, store, sf):
    """0.9.13: first-run setup owns the mission ask (mission-first onboarding
    slot) — the kickoff must stay silent AND stay armed while setup runs."""
    await _seed_identity(sf, 0)
    assert await maybe_send_install_kickoff(kctx, store) is False
    assert _kickoff_posts(kctx) == []
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) is None

    # setup finished but still missionless (owner never gave one) → the
    # armed kickoff fires as before
    await _seed_identity(sf, 1)
    assert await maybe_send_install_kickoff(kctx, store) is True
    assert len(_kickoff_posts(kctx)) == 1
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) == "1"


@pytest.mark.asyncio
async def test_identity_table_empty_means_setup_not_started(kctx, store, sf):
    """The identity row is created lazily on the first turn — an EMPTY table
    on a fresh install still means setup lies ahead, so the kickoff defers."""
    await _seed_identity(sf, None)
    assert await maybe_send_install_kickoff(kctx, store) is False
    assert _kickoff_posts(kctx) == []
    assert await _flag_get(sf, INSTALL_KICKOFF_FLAG) is None


@pytest.mark.asyncio
async def test_no_identity_table_keeps_legacy_kickoff(kctx, store, sf):
    """Exotic/old core without the identity table: _setup_incomplete reads
    False and the kickoff behaves exactly as before."""
    assert await maybe_send_install_kickoff(kctx, store) is True
    assert len(_kickoff_posts(kctx)) == 1


def test_install_kickoff_content_asks_for_mission_now():
    from plugin_curiosity.research import INSTALL_KICKOFF_CONTENT

    text = INSTALL_KICKOFF_CONTENT
    assert "no mission yet" in text
    assert "NOW" in text
    assert "end" in text and "question" in text

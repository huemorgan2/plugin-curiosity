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


def test_install_kickoff_content_asks_for_mission_now():
    from plugin_curiosity.research import INSTALL_KICKOFF_CONTENT

    text = INSTALL_KICKOFF_CONTENT
    assert "no mission yet" in text
    assert "NOW" in text
    assert "end" in text and "question" in text

"""10.003 §3 — curiosity 0.9.2: mission-bound wiki, provider-first readers,
unique_name heartbeat provenance. Everything here is FEATURE-DETECTED — every
test has a sibling proving the old-companion fallback still holds, because the
fallbacks are kept forever, not until the next release."""

from __future__ import annotations

import types

import pytest

from conftest import (
    FakeConfigRegistry,
    FakeEvents,
    FakeProviderRegistry,
    FakeToolRegistry,
    FakeWikiProvider,
)

DEFAULT_WIKI = "main"


class MultiWikiProvider:
    """wiki >= 0.7.0 shape: named wikis, `wiki` kwarg on page calls, and the
    extraction API (get_section / get_table / revisions)."""

    def __init__(self) -> None:
        self.wikis: dict[str, dict] = {DEFAULT_WIKI: {"slug": DEFAULT_WIKI, "name": "Main"}}
        self.pages: dict[tuple[str, str], dict] = {}
        self.sections: dict[tuple[str, str, str], dict] = {}
        self.tables: dict[tuple[str, str], dict] = {}
        self.revs: dict[tuple[str, str], list] = {}
        self.create_calls: list[tuple] = []
        self.update_calls: list[tuple] = []
        self.fail_create = False

    async def create_wiki(self, slug: str, name: str, description: str = ""):
        self.create_calls.append((slug, name, description))
        if self.fail_create:
            raise RuntimeError("wiki already exists")
        self.wikis[slug] = {"slug": slug, "name": name, "description": description}
        return self.wikis[slug]

    async def list_wikis(self):
        return list(self.wikis.values())

    async def update_wiki(self, slug: str, name: str | None = None, description: str | None = None):
        self.update_calls.append((slug, name, description))
        return self.wikis.get(slug)

    async def get_page(self, slug: str, wiki: str = DEFAULT_WIKI):
        return self.pages.get((wiki, slug))

    async def upsert_page(self, slug: str, title: str, body: str, summary: str = "",
                          note: str = "", wiki: str = DEFAULT_WIKI):
        self.pages[(wiki, slug)] = {
            "slug": slug, "title": title, "body": body, "summary": summary}
        return self.pages[(wiki, slug)]

    async def get_section(self, slug: str, header: str, wiki: str = DEFAULT_WIKI):
        return self.sections.get((wiki, slug, header.lower()))

    async def get_table(self, slug: str, header: str = "", wiki: str = DEFAULT_WIKI):
        return self.tables.get((wiki, slug))

    async def revisions(self, slug: str, wiki: str = DEFAULT_WIKI):
        return self.revs.get((wiki, slug), [])


class SchedulerRegistry03(FakeToolRegistry):
    """plugin-scheduler 0.3.0 handler signatures: unique_name / purpose /
    created_by are real kwargs (that is what _sync_schedules inspects)."""

    def get(self, name: str):
        if name in self.registered:
            return super().get(name)
        if name == "trigger_create":
            reg = self

            async def _create(name, schedule_expr, target, action_type="agent_prompt",
                              unique_name=False, purpose=None,
                              created_by="plugin-scheduler"):
                kw = {"name": name, "schedule_expr": schedule_expr, "target": target,
                      "unique_name": unique_name, "purpose": purpose,
                      "created_by": created_by}
                reg.trigger_created.append(kw)
                reg.existing_triggers.append(
                    {"id": f"trg-{len(reg.trigger_created)}", "name": name,
                     "target": target, "expr_raw": schedule_expr,
                     "purpose": purpose, "created_by": created_by, "enabled": True})
                return {"id": f"trg-{len(reg.trigger_created)}", "created": True,
                        "expr_cron": "0 9 * * *", "next_run_at": "2026-01-01T09:00:00Z"}

            return types.SimpleNamespace(handler=_create)
        if name == "trigger_update":
            reg = self

            async def _update(id, schedule_expr=None, target=None, action_type=None,
                              enabled=None, purpose=None):
                kw = {"id": id, "schedule_expr": schedule_expr, "target": target,
                      "purpose": purpose}
                reg.trigger_updated.append(kw)
                for t in reg.existing_triggers:
                    if t["id"] == id:
                        if target is not None:
                            t["target"] = target
                        if schedule_expr is not None:
                            t["expr_raw"] = schedule_expr
                        if purpose is not None:
                            t["purpose"] = purpose
                return {"id": id, "expr_cron": "0 9 * * *",
                        "next_run_at": "2026-01-01T09:00:00Z"}

            return types.SimpleNamespace(handler=_update)
        return super().get(name)


def _ctx(store, sf, *, wiki, tool_registry=None):
    from plugin_curiosity.comms import ReflectionLog
    from plugin_curiosity.comms import register_tools as register_comms_tools
    from plugin_curiosity.mission import register_tools

    c = types.SimpleNamespace(
        tool_registry=tool_registry or FakeToolRegistry(),
        provider_registry=FakeProviderRegistry(wiki),
        config_registry=FakeConfigRegistry(),
        events=FakeEvents(),
        db_session_factory=sf,
        muted_posts=[],
    )

    async def send_muted_message(title, content, **kw):
        c.muted_posts.append({"title": title, "content": content, **kw})
        return {"ok": True}

    c.send_muted_message = send_muted_message
    c.reflections = ReflectionLog(sf)
    register_tools(c, store)
    register_comms_tools(c, c.reflections)
    return c


async def call(ctx, name, **kw):
    return await ctx.tool_registry.registered[name][1](**kw)


# ---- wikibind primitives -----------------------------------------------------


def test_slug_for_shape():
    from plugin_curiosity.wikibind import slug_for

    s = slug_for("Grow the newsletter to 5k subs!", "a1b2c3d4-0000")
    assert s == "grow-the-newsletter-to-5k-subs-a1b2c3"
    # same wording, different mission → different slug
    assert slug_for("Grow the newsletter to 5k subs!", "ffffff-1") != s
    # empty statement never yields an empty base
    assert slug_for("", "a1b2c3d4").startswith("mission-")


def test_supports_multi_wiki_detection():
    from plugin_curiosity.wikibind import supports_multi_wiki

    assert supports_multi_wiki(MultiWikiProvider()) is True
    assert supports_multi_wiki(FakeWikiProvider()) is False


@pytest.mark.asyncio
async def test_bind_wiki_old_provider_returns_none(store, sf):
    from plugin_curiosity import wikibind

    ctx = _ctx(store, sf, wiki=FakeWikiProvider())
    assert await wikibind.bind_wiki(ctx, "grow signups", "a1b2c3d4") is None


@pytest.mark.asyncio
async def test_bind_wiki_create_failure_trusts_listing(store, sf):
    from plugin_curiosity import wikibind

    wiki = MultiWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    slug = wikibind.slug_for("grow signups", "a1b2c3d4")
    # pre-existing wiki + create_wiki raising = idempotent re-bind
    wiki.wikis[slug] = {"slug": slug, "name": "grow signups"}
    wiki.fail_create = True
    assert await wikibind.bind_wiki(ctx, "grow signups", "a1b2c3d4") == slug
    # raising with NO listing entry = bind failed, global namespace
    assert await wikibind.bind_wiki(ctx, "other mission", "e5f6a7b8") is None


# ---- mission_set binds the wiki ----------------------------------------------


@pytest.mark.asyncio
async def test_mission_set_binds_and_scopes_seeding(store, sf):
    from plugin_curiosity import wikibind

    wiki = MultiWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    res = await call(ctx, "mission_set", statement="grow signups")
    m = res["mission"]
    slug = wikibind.slug_for("grow signups", m["id"])
    assert m["wiki_id"] == slug
    assert (await store.get())["wiki_id"] == slug  # persisted, not just echoed
    assert slug in wiki.wikis
    # seeded stubs landed in the MISSION wiki, not the global one
    seeded = {s for (w, s) in wiki.pages if w == slug}
    assert "mission" in seeded and "success-criteria" in seeded
    assert not any(w == DEFAULT_WIKI for (w, _) in wiki.pages)
    # every surface now scopes through wiki_kwargs
    assert await wikibind.wiki_kwargs(ctx, sf) == {"wiki": slug}


@pytest.mark.asyncio
async def test_mission_set_old_wiki_keeps_global_namespace(store, sf):
    from plugin_curiosity import wikibind

    wiki = FakeWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    res = await call(ctx, "mission_set", statement="grow signups")
    assert res["mission"]["wiki_id"] in (None, "")
    assert "mission" in wiki.pages  # stubs seeded exactly as pre-0.9.2
    assert await wikibind.wiki_kwargs(ctx, sf) == {}


@pytest.mark.asyncio
async def test_wiki_kwargs_degrades_on_provider_downgrade(store, sf):
    """A mission bound under 0.7.0 whose wiki plugin was later downgraded must
    fall back to global reads — never TypeError."""
    from plugin_curiosity import wikibind

    ctx = _ctx(store, sf, wiki=MultiWikiProvider())
    await call(ctx, "mission_set", statement="grow signups")
    assert (await wikibind.wiki_kwargs(ctx, sf)).get("wiki")
    ctx.provider_registry._wiki = FakeWikiProvider()  # the downgrade
    assert await wikibind.wiki_kwargs(ctx, sf) == {}


@pytest.mark.asyncio
async def test_prompt_fragment_names_the_bound_wiki(store, sf):
    from plugin_curiosity.mission import prompt_fragment

    ctx = _ctx(store, sf, wiki=MultiWikiProvider())
    await call(ctx, "mission_set", statement="grow signups")
    m = await store.get()
    frag = prompt_fragment(m, "setup")
    assert f"wiki='{m['wiki_id']}'" in frag
    # unbound mission carries no wiki line
    assert "Your mission wiki" not in prompt_fragment(
        {**m, "wiki_id": None}, "setup")


# ---- schedule sync: provenance feature-detect ---------------------------------


@pytest.mark.asyncio
async def test_sync_schedules_passes_provenance_to_new_scheduler(store, sf):
    from plugin_curiosity.mission import MISSION_SCHEDULES

    reg = SchedulerRegistry03()
    ctx = _ctx(store, sf, wiki=MultiWikiProvider(), tool_registry=reg)
    await call(ctx, "mission_set", statement="grow signups")
    assert len(reg.trigger_created) == len(MISSION_SCHEDULES)
    for kw in reg.trigger_created:
        assert kw["unique_name"] is True
        assert kw["created_by"] == "plugin-curiosity"
        assert kw["purpose"]  # every MISSION_SCHEDULES spec carries one
    # re-sync converges without duplicates (list-before-create still on)
    await call(ctx, "mission_set", statement="grow signups")
    assert len(reg.trigger_created) == len(MISSION_SCHEDULES)


@pytest.mark.asyncio
async def test_sync_schedules_old_scheduler_gets_no_new_kwargs(store, sf):
    from plugin_curiosity.mission import MISSION_SCHEDULES

    reg = FakeToolRegistry()  # 0.2.x shape: **kw-free explicit old signature
    ctx = _ctx(store, sf, wiki=MultiWikiProvider(), tool_registry=reg)
    await call(ctx, "mission_set", statement="grow signups")
    assert len(reg.trigger_created) == len(MISSION_SCHEDULES)
    for kw in reg.trigger_created:
        assert "unique_name" not in kw
        assert "purpose" not in kw
        assert "created_by" not in kw


@pytest.mark.asyncio
async def test_sync_schedules_backfills_purpose_on_drifted_trigger(store, sf):
    from plugin_curiosity.mission import MISSION_SCHEDULES, _sync_schedules

    reg = SchedulerRegistry03()
    ctx = _ctx(store, sf, wiki=MultiWikiProvider(), tool_registry=reg)
    spec = MISSION_SCHEDULES[0]
    reg.existing_triggers.append(
        {"id": "trg-old", "name": spec["name"], "target": spec["target"],
         "expr_raw": spec["schedule_expr"], "purpose": None, "enabled": True})
    out = await _sync_schedules(ctx)
    assert "updated" in out
    patch = next(u for u in reg.trigger_updated if u["id"] == "trg-old")
    assert patch["purpose"] == spec["purpose"]


# ---- provider-first readers ----------------------------------------------------


def _jd_sections(wiki: MultiWikiProvider, wk: str) -> None:
    from plugin_curiosity.overview import JD_SECTIONS

    for key, heading in JD_SECTIONS:
        wiki.sections[(wk, "job-description", heading)] = {
            "header": heading,
            "text": f"intro for {key}\n- item one\n- item two",
            "items": [f"{key} item one", f"{key} item two"],
            "numbered": False,
        }


@pytest.mark.asyncio
async def test_read_job_description_prefers_provider_extraction(store, sf):
    from plugin_curiosity.overview import read_job_description

    wiki = MultiWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    _jd_sections(wiki, "m-wiki")
    # NO page body — only the provider path can produce this result
    jd = await read_job_description(ctx, {"wiki": "m-wiki"})
    assert jd["shape_ok"] is True
    assert jd["sections"]["method"]["intro"] == "intro for method"
    assert jd["sections"]["in_30_days"]["items"] == [
        "in_30_days item one", "in_30_days item two"]


@pytest.mark.asyncio
async def test_read_job_description_partial_provider_falls_back(store, sf):
    from plugin_curiosity.overview import JD_SECTIONS, read_job_description

    wiki = MultiWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    _jd_sections(wiki, "m-wiki")
    # knock one section out of the provider result → bespoke parser wins
    del wiki.sections[("m-wiki", "job-description", JD_SECTIONS[0][1])]
    body = "\n".join(
        f"## {heading}\n- fallback item" for _, heading in JD_SECTIONS)
    wiki.pages[("m-wiki", "job-description")] = {
        "slug": "job-description", "title": "JD", "body": body}
    jd = await read_job_description(ctx, {"wiki": "m-wiki"})
    assert jd["shape_ok"] is True
    assert jd["sections"]["method"]["items"] == ["fallback item"]


@pytest.mark.asyncio
async def test_read_noc_inputs_provider_table_and_scores(store, sf):
    from plugin_curiosity.overview import read_noc_inputs

    wiki = MultiWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    wiki.tables[("m-wiki", "success-criteria")] = {
        "header": "", "columns": ["Criterion", "Measure", "Target", "Horizon"],
        "rows": [["signups", "weekly count", "500", "30 days"]]}
    wiki.sections[("m-wiki", "success-criteria", "weekly scores")] = {
        "header": "Weekly scores", "text": "",
        "items": ["2026-07-07 | signups | on-track | 320 and climbing",
                  "not a score line"],
        "numbered": False}
    criteria, scores = await read_noc_inputs(ctx, {"wiki": "m-wiki"})
    assert criteria == [{"criterion": "signups", "measure": "weekly count",
                         "target": "500", "horizon": "30 days"}]
    assert scores == [{"date": "2026-07-07", "criterion": "signups",
                       "status": "on-track", "evidence": "320 and climbing"}]


@pytest.mark.asyncio
async def test_read_noc_inputs_halves_fall_back_independently(store, sf):
    from plugin_curiosity.overview import read_noc_inputs

    wiki = MultiWikiProvider()
    ctx = _ctx(store, sf, wiki=wiki)
    # provider has a MALFORMED table (wrong columns) and no scores section →
    # both halves come from the body parsers
    wiki.tables[("m-wiki", "success-criteria")] = {
        "header": "", "columns": ["what", "how"], "rows": [["x", "y"]]}
    wiki.pages[("m-wiki", "success-criteria")] = {
        "slug": "success-criteria", "title": "SC", "body": (
            "| Criterion | Measure | Target | Horizon |\n"
            "| --- | --- | --- | --- |\n"
            "| signups | weekly count | 500 | 30 days |\n"
            "## Weekly scores\n"
            "- 2026-07-07 | signups | met | done\n")}
    criteria, scores = await read_noc_inputs(ctx, {"wiki": "m-wiki"})
    assert criteria and criteria[0]["criterion"] == "signups"
    assert scores and scores[0]["status"] == "met"


@pytest.mark.asyncio
async def test_read_job_description_old_wiki_uses_body_parser(store, sf):
    from plugin_curiosity.overview import JD_SECTIONS, read_job_description

    wiki = FakeWikiProvider()  # no get_section at all
    ctx = _ctx(store, sf, wiki=wiki)
    body = "\n".join(
        f"## {heading}\n- old-provider item" for _, heading in JD_SECTIONS)
    wiki.pages["job-description"] = {
        "slug": "job-description", "title": "JD", "body": body}
    jd = await read_job_description(ctx)
    assert jd["shape_ok"] is True
    assert jd["sections"]["working_assumptions"]["items"] == ["old-provider item"]


# ---- owner words: no stage codes on owner surfaces ------------------------------


@pytest.mark.asyncio
async def test_charter_page_speaks_plain_words(store, sf):
    import re

    from plugin_curiosity.scopes import STAGE_LABELS, ScopeStore, render_charter_page

    await store.set("grow signups")
    sstore = ScopeStore(sf)
    await sstore.add("knowledge", "the domain")
    scopes = await sstore.list()
    for stage in STAGE_LABELS:
        state = {"setup_stage": stage, "agent_phase": "setup", "statement": "grow signups"}
        body = render_charter_page(state, scopes, [])
        assert not re.search(r"\bS\d\b", body), f"{stage} leaks a stage code"
        assert STAGE_LABELS[stage][0] in body


def test_prompts_carry_the_owner_words_rule():
    from plugin_curiosity.prompts import OWNER_WORDS, WIKI_BINDING
    from plugin_curiosity.research import DAILY_RESEARCH_TARGET, HEARTBEAT_NUDGE_CONTENT
    from plugin_curiosity.review import WEEKLY_REVIEW_TARGET

    for surface in (DAILY_RESEARCH_TARGET, WEEKLY_REVIEW_TARGET):
        assert OWNER_WORDS in surface
        assert WIKI_BINDING in surface
    assert WIKI_BINDING in HEARTBEAT_NUDGE_CONTENT


def test_heartbeat_contract_mandates_unique_name():
    from plugin_curiosity.prompts import HEARTBEAT_CONTRACT

    assert "unique_name=true" in HEARTBEAT_CONTRACT
    assert "purpose=" in HEARTBEAT_CONTRACT


# ---- downgraded wiki on a multi-wiki DB: adoption survives ---------------------


class PoisonedSlugProvider(FakeWikiProvider):
    """Old wiki (0.3.2) on a DB the NEW wiki wrote: slug-only lookups see the
    same slug in two namespaces and raise (MultipleResultsFound). Every page
    op blows up; adoption must degrade, never die."""

    def _boom(self):
        raise RuntimeError("Multiple rows were found when one or none was required")

    async def get_page(self, slug):
        self._boom()

    async def upsert_page(self, slug, title, body, **kw):
        self._boom()


@pytest.mark.asyncio
async def test_mission_set_survives_poisoned_slug_wiki(store, sf):
    ctx = _ctx(store, sf, wiki=PoisonedSlugProvider())
    res = await call(ctx, "mission_set", statement="run the workshop calendar")
    assert "error" not in res
    assert res["mission"]["statement"] == "run the workshop calendar"
    assert res["mission"]["wiki_id"] is None  # old provider — bind refused
    assert "skipped" in res["wiki_stubs"] and "wiki degraded" in res["wiki_stubs"]
    assert res["schedules"]  # scheduler sync unaffected by the wiki failure


@pytest.mark.asyncio
async def test_success_criteria_seed_skips_on_poisoned_slug_wiki(store, sf):
    from plugin_curiosity.mission import ensure_success_criteria_page

    await store.set("run the workshop calendar")
    ctx = _ctx(store, sf, wiki=PoisonedSlugProvider())
    result = await ensure_success_criteria_page(ctx, store)
    assert result.startswith("skipped:")

"""Role registry: PLAN 7.1 defaults, validation against profiles, family rule, persistence."""

from __future__ import annotations

import pytest

from tests.llm.helpers import NOW
from yield_guardian.llm.profiles import (
    DOCUMENTED_PROFILES,
    OPENROUTER_MODEL,
    CatalogEntry,
    ProfileCatalog,
    Provider,
)
from yield_guardian.llm.registry import (
    DEFAULT_CHAINS,
    InMemoryRoleAssignmentStore,
    InvalidAssignmentError,
    ModelChoice,
    ModelRegistry,
    ResponseMode,
    Role,
    RoleAssignment,
    choice_for,
    default_mode,
    family_problems,
    policy_effort,
    validate_chain,
)

TEXT, SCHEMA, OBJECT = ResponseMode.TEXT, ResponseMode.JSON_SCHEMA, ResponseMode.JSON_OBJECT


def registry(store: InMemoryRoleAssignmentStore | None = None) -> ModelRegistry:
    return ModelRegistry(
        ProfileCatalog(), store or InMemoryRoleAssignmentStore(), wall_clock=lambda: NOW
    )


def test_defaults_follow_plan_section_7_1() -> None:
    primaries = {role: chain[0].model for role, chain in DEFAULT_CHAINS.items()}
    assert primaries == {
        Role.INVESTIGATOR: OPENROUTER_MODEL,
        Role.WRITER: OPENROUTER_MODEL,
        Role.VERIFIER: OPENROUTER_MODEL,
        Role.CHAT: OPENROUTER_MODEL,
        Role.ROUTER: OPENROUTER_MODEL,
        Role.VISION: OPENROUTER_MODEL,
        Role.OCR: "MinerU2.5-Pro",
    }
    # TokenHarbor first (when its key is set), then Qwen3.8-Flash-Next (the one model that
    # returned long outputs reliably live, 2026-10-14), then DeepSeek, then MiMo. MiMo refused
    # strict json_schema live; every structured default is json_object.
    assert DEFAULT_CHAINS[Role.WRITER] == (
        ModelChoice(model=OPENROUTER_MODEL, response_mode=OBJECT, provider=Provider.OPENROUTER),
        ModelChoice(model="Qwen3.8-Flash-Next", reasoning_effort="none", response_mode=OBJECT),
        ModelChoice(model="DeepSeek-V4.1-Flash", reasoning_effort="low", response_mode=OBJECT),
        ModelChoice(model="MiMo-V2.6-Flash", reasoning_effort="none", response_mode=OBJECT),
    )
    # OCR is Token Factory only; OpenRouter (and for the text roles TokenHarbor) come first.
    assert all(c.provider is Provider.TOKEN_FACTORY for c in DEFAULT_CHAINS[Role.OCR])
    assert all(c.provider is Provider.TOKEN_FACTORY for c in DEFAULT_CHAINS[Role.VISION][1:])
    writer, verifier = DEFAULT_CHAINS[Role.WRITER], DEFAULT_CHAINS[Role.VERIFIER]
    assert family_problems(writer, verifier, ProfileCatalog()) == []
    # After OpenRouter and TokenHarbor, the verifier's first model is outside the writer's families.
    assert DEFAULT_CHAINS[Role.VERIFIER][2].model == "GLM-5.3-Flash"
    assert all(c.response_mode is not SCHEMA for chain in DEFAULT_CHAINS.values() for c in chain)


@pytest.mark.parametrize("role", list(Role))
def test_every_default_chain_is_valid(role: Role) -> None:
    assert validate_chain(role, DEFAULT_CHAINS[role], ProfileCatalog()) == []


def test_default_chains_set_reasoning_effort_explicitly_where_the_model_takes_it() -> None:
    for chain in DEFAULT_CHAINS.values():
        for choice in chain:
            profile = DOCUMENTED_PROFILES[choice.model]
            takes_effort = bool(profile.reasoning_efforts) and profile.kind.value == "chat"
            assert (choice.reasoning_effort is not None) == takes_effort, choice


def test_policy_effort_picks_the_nearest_accepted_value() -> None:
    assert policy_effort(Role.CHAT, DOCUMENTED_PROFILES["GLM-5.3-Flash"]) == "low"  # no none
    assert policy_effort(Role.CHAT, DOCUMENTED_PROFILES["Qwen3.8-27B"]) == "low"
    assert policy_effort(Role.WRITER, DOCUMENTED_PROFILES["Gemma-4-31B-IT"]) == "none"
    assert policy_effort(Role.ROUTER, DOCUMENTED_PROFILES["MiniCPM5-2B"]) is None
    assert policy_effort(Role.OCR, DOCUMENTED_PROFILES["MinerU2.5-Pro"]) is None


def test_default_mode_uses_json_schema_only_where_supported() -> None:
    mimo = DOCUMENTED_PROFILES["MiMo-V2.6-Flash"]
    assert default_mode(Role.VERIFIER, mimo) is OBJECT
    capable = mimo.model_copy(update={"supports_json_schema": True})  # hypothetical model
    assert default_mode(Role.VERIFIER, capable) is SCHEMA
    assert default_mode(Role.VERIFIER, DOCUMENTED_PROFILES["GLM-5.3-Flash"]) is OBJECT
    assert default_mode(Role.CHAT, DOCUMENTED_PROFILES["MiMo-V2.6-Flash"]) is TEXT


@pytest.mark.parametrize(
    ("role", "chain", "problem"),
    [
        (Role.WRITER, [], "the chain is empty"),
        (Role.CHAT, [ModelChoice(model="Nope-1", reasoning_effort="low")], "unknown model"),
        (Role.VERIFIER, [ModelChoice(model="GLM-5.3-Flash", reasoning_effort="xhigh",
                                     response_mode=OBJECT)], "does not accept reasoning_effort 'xhigh'"),
        (Role.WRITER, [ModelChoice(model="Qwen3.8-27B", reasoning_effort="high",
                                   response_mode=OBJECT)], "does not accept reasoning_effort 'high'"),
        (Role.CHAT, [ModelChoice(model="DeepSeek-V4-Flash")], "needs an explicit reasoning_effort"),
        (Role.ROUTER, [ModelChoice(model="MiniCPM5-2B", reasoning_effort="low",
                                   response_mode=OBJECT)], "does not take reasoning_effort"),
        (Role.WRITER, [ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low",
                                   response_mode=SCHEMA)], "does not support strict json_schema"),
        (Role.WRITER, [ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low")],
         "needs json_schema or json_object"),
        (Role.CHAT, [ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low",
                                 response_mode=OBJECT)], "uses text output"),
        (Role.VISION, [ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low",
                                   response_mode=OBJECT)], "does not accept images"),
        (Role.OCR, [ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low")],
         "is not an OCR model"),
        (Role.CHAT, [ModelChoice(model="MinerU2.5-Pro")], "is not a chat model"),
        (Role.CHAT, [ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="none")] * 2,
         "listed twice"),
        (Role.CHAT, [ModelChoice(model=m, reasoning_effort="low") for m in
                     ["DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash", "DeepSeek-V4-Flash-Vision-Exp",
                      "GLM-5.3-Flash", "Qwen3.8-Flash-Next", "Qwen3.8-27B"]], "at most 5"),
    ],
)  # fmt: skip
def test_invalid_chains_are_explained(role: Role, chain: list[ModelChoice], problem: str) -> None:
    problems = validate_chain(role, chain, ProfileCatalog())
    assert any(problem in p for p in problems), problems


def test_withdrawn_models_cannot_be_assigned_and_are_skipped_when_resolving() -> None:
    reg = registry()
    reg.catalog.sync([CatalogEntry(id="GLM-5.3-Flash"), CatalogEntry(id="Qwen3.8-27B")], NOW)
    chain = [ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="none")]
    assert any("missing from the live catalog" in p for p in reg.validate(Role.CHAT, chain))
    resolution = reg.resolve(Role.VERIFIER)
    assert [r.choice.model for r in resolution.usable] == ["GLM-5.3-Flash"]
    assert resolution.skipped == (("DeepSeek-V4-Flash", "not usable (withdrawn)"),)


def test_resolve_can_exclude_the_writer_family() -> None:
    resolution = registry().resolve(Role.VERIFIER, exclude_families=frozenset({"glm"}))
    assert [r.choice.model for r in resolution.usable] == ["DeepSeek-V4-Flash"]
    assert resolution.skipped == (("GLM-5.3-Flash", "family glm excluded"),)


async def test_assign_validates_persists_and_stamps() -> None:
    store = InMemoryRoleAssignmentStore()
    reg = registry(store)
    chain = [
        ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="none"),
        ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low"),
    ]
    saved = await reg.assign(Role.CHAT, chain, actor="engineer@fab")
    assert saved.updated_by == "engineer@fab"
    assert saved.updated_at == NOW
    assert store.saved[Role.CHAT] == saved
    assert reg.assignment(Role.CHAT).primary.model == "DeepSeek-V4-Flash"
    with pytest.raises(InvalidAssignmentError) as caught:
        await reg.assign(Role.CHAT, [ModelChoice(model="GLM-5.3-Flash")], actor="x")
    assert caught.value.problems
    assert reg.assignment(Role.CHAT) == saved  # unchanged after a refused assignment


async def test_the_verifier_must_offer_a_family_other_than_each_writer_model() -> None:
    reg = registry()
    glm_only_writer = [
        ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low", response_mode=OBJECT)
    ]
    await reg.assign(Role.WRITER, glm_only_writer, actor="a")
    only_glm_verifier = [
        ModelChoice(model="GLM-5.3-Flash", reasoning_effort="low", response_mode=OBJECT)
    ]
    with pytest.raises(InvalidAssignmentError, match="outside the glm family"):
        await reg.assign(Role.VERIFIER, only_glm_verifier, actor="a")


async def test_load_ignores_invalid_stored_chains_and_resets_cross_family_conflicts() -> None:
    bad = RoleAssignment(
        role=Role.CHAT, chain=(ModelChoice(model="GLM-5.3-Flash", reasoning_effort="xhigh"),)
    )
    good = RoleAssignment(
        role=Role.ROUTER,
        chain=(
            ModelChoice(model="DeepSeek-V4-Flash", reasoning_effort="none", response_mode=OBJECT),
        ),
    )
    same_family = RoleAssignment(
        role=Role.VERIFIER,
        chain=(ModelChoice(model="MiMo-V2.6-Flash", reasoning_effort="low", response_mode=SCHEMA),),
    )
    writer = RoleAssignment(
        role=Role.WRITER,
        chain=(ModelChoice(model="MiMo-V2.6-Flash", reasoning_effort="low", response_mode=SCHEMA),),
    )
    reg = registry(InMemoryRoleAssignmentStore([bad, good, same_family, writer]))
    warnings = await reg.load()
    assert reg.assignment(Role.CHAT).chain == DEFAULT_CHAINS[Role.CHAT]
    assert reg.assignment(Role.ROUTER).primary.model == "DeepSeek-V4-Flash"
    assert reg.assignment(Role.WRITER).chain == DEFAULT_CHAINS[Role.WRITER]
    assert reg.assignment(Role.VERIFIER).chain == DEFAULT_CHAINS[Role.VERIFIER]
    assert any("stored chain for chat ignored" in w for w in warnings)
    assert any("writer and verifier reset" in w for w in warnings)


async def test_load_turns_a_stored_mimo_json_schema_entry_into_json_object() -> None:
    # Chains saved before MiMo was measured to refuse json_schema keep everything else.
    stored = RoleAssignment(
        role=Role.WRITER,
        chain=(
            ModelChoice(model="MiMo-V2.6-Flash", reasoning_effort="low", response_mode=SCHEMA),
            ModelChoice(model="Qwen3.8-27B", reasoning_effort="medium", response_mode=OBJECT),
        ),
        updated_at=NOW,
        updated_by="admin",
    )
    reg = registry(InMemoryRoleAssignmentStore([stored]))
    warnings = await reg.load()
    loaded = reg.assignment(Role.WRITER)
    assert loaded.chain == (
        ModelChoice(model="MiMo-V2.6-Flash", reasoning_effort="low", response_mode=OBJECT),
        ModelChoice(model="Qwen3.8-27B", reasoning_effort="medium", response_mode=OBJECT),
    )
    assert loaded.chain != DEFAULT_CHAINS[Role.WRITER]  # coerced, not reset
    assert (loaded.updated_by, loaded.updated_at) == ("admin", NOW)
    assert warnings == [
        "stored chain for writer: json_schema changed to json_object for MiMo-V2.6-Flash "
        "(the model does not accept strict json_schema)"
    ]


def test_choice_for_keeps_an_existing_entry_and_adapts_a_new_one() -> None:
    existing = ModelChoice(model="GLM-5.3-Flash", reasoning_effort="high", response_mode=OBJECT)
    profile = DOCUMENTED_PROFILES["GLM-5.3-Flash"]
    assert choice_for(Role.VERIFIER, profile, existing=existing) == existing
    assert choice_for(Role.VERIFIER, profile) == ModelChoice(
        model="GLM-5.3-Flash", reasoning_effort="low", response_mode=OBJECT
    )


def test_undocumented_catalog_models_get_the_conservative_shape() -> None:
    reg = registry()
    reg.catalog.sync([CatalogEntry(id="MiniCPM-V-4.7-1B")], NOW)
    profile = reg.catalog.require("MiniCPM-V-4.7-1B")
    choice = choice_for(Role.WRITER, profile)
    assert choice.reasoning_effort == "low"
    assert choice.response_mode is OBJECT
    assert validate_chain(Role.WRITER, [choice], reg.catalog) == []

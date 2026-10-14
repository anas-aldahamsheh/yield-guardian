"""Capability profiles: transcription of docs/vendor/token-factory.md, catalog sync, points."""

from __future__ import annotations

import pytest

from tests.llm.helpers import NOW
from yield_guardian.llm.errors import ResponseShapeError
from yield_guardian.llm.profiles import (
    CONSERVATIVE_CONTEXT,
    DOCUMENTED_PROFILES,
    Availability,
    CatalogEntry,
    DeveloperRole,
    ModelKind,
    Pricing,
    ProfileCatalog,
    ReasoningControl,
    SystemRule,
    Usage,
    conservative_profile,
    infer_family,
    parse_catalog,
)

# (model, context, images, thinks by default, accepted efforts, system rule, developer rule,
#  json_schema, reasoning tokens reported, pricing input/output/cache read), from the table
# in docs/vendor/token-factory.md, except MiMo's json_schema: the docs list it, but the live
# endpoint refused it with HTTP 400 on 2026-10-14.
DOCUMENTED = [
    ("DeepSeek-V4-Flash", 1_048_576, False, False,
     {"none", "minimal", "low", "medium", "high", "xhigh", "max"}, SystemRule.ANY,
     DeveloperRole.ACCEPTED, False, True, (0.14, 0.28, 0.0028)),
    ("DeepSeek-V4.1-Flash", 1_048_576, True, False,
     {"none", "minimal", "low", "medium", "high", "xhigh", "max"}, SystemRule.ANY,
     DeveloperRole.ACCEPTED, False, True, (0.14, 0.28, 0.0028)),
    ("DeepSeek-V4-Flash-Vision-Exp", 1_048_576, True, False,
     {"none", "minimal", "low", "medium", "high", "xhigh", "max"}, SystemRule.ANY,
     DeveloperRole.ACCEPTED, False, True, (0.14, 0.28, 0.0028)),
    ("MiMo-V2.6-Flash", 1_048_576, True, True, {"none", "low", "medium", "high"},
     SystemRule.ANY, DeveloperRole.ACCEPTED, False, True, (0.14, 0.28, 0.0028)),
    ("GLM-5.3-Flash", 262_144, False, True, {"low", "medium", "high"}, SystemRule.ANY,
     DeveloperRole.MAP_TO_SYSTEM, False, True, (0.15, 0.50, 0.03)),
    ("Qwen3.8-Flash-Next", 262_144, True, True, {"none", "low", "medium", "xhigh"},
     SystemRule.EXACTLY_ONE_FIRST, DeveloperRole.MAP_TO_SYSTEM, False, True,
     (0.15, 0.47, 0.016)),
    ("Qwen3.8-27B", 131_072, True, True, {"low", "medium", "xhigh"},
     SystemRule.AT_MOST_ONE_FIRST, DeveloperRole.MAP_TO_SYSTEM, False, False,
     (0.50, 3.00, 0.05)),
    ("MiniCPM5-2B", 131_072, False, False, set(), SystemRule.ANY, DeveloperRole.MAP_TO_SYSTEM,
     False, False, (0.124, 0.7425, 0.124)),
    ("Gemma-4-31B-IT", 262_144, True, False, {"none"}, SystemRule.AT_MOST_ONE_FIRST,
     DeveloperRole.MAP_TO_SYSTEM, False, False, (0.50, 3.00, 0.05)),
]  # fmt: skip


@pytest.mark.parametrize(
    ("model", "context", "images", "thinks", "efforts", "system", "developer", "schema",
     "reasoning_count", "pricing"),
    DOCUMENTED,
)  # fmt: skip
def test_documented_profile_matches_the_vendor_table(
    model: str,
    context: int,
    images: bool,
    thinks: bool,
    efforts: set[str],
    system: SystemRule,
    developer: DeveloperRole,
    schema: bool,
    reasoning_count: bool,
    pricing: tuple[float, float, float],
) -> None:
    profile = DOCUMENTED_PROFILES[model]
    assert profile.kind is ModelKind.CHAT
    assert profile.context_length == context
    assert profile.accepts_images is images
    assert profile.thinks_by_default is thinks
    assert set(profile.reasoning_efforts) == efforts
    assert profile.system_rule is system
    assert profile.developer_role is developer
    assert profile.supports_json_schema is schema
    assert profile.reports_reasoning_tokens is reasoning_count
    assert profile.pricing is not None
    assert (
        profile.pricing.input_per_mtok,
        profile.pricing.output_per_mtok,
        profile.pricing.cache_read_per_mtok,
    ) == pricing
    # "Every chat model supports streaming, tools, tool_choice and json_object."
    assert profile.supports_tools
    assert profile.supports_streaming
    assert profile.supports_json_object
    assert profile.source == "documented"


def test_no_model_is_known_to_accept_strict_json_schema() -> None:
    # MiMo-V2.6-Flash, the one model documented with it, refused it live (HTTP 400, 2026-10-14).
    assert [m for m, p in DOCUMENTED_PROFILES.items() if p.supports_json_schema] == []
    assert any("refused live" in note for note in DOCUMENTED_PROFILES["MiMo-V2.6-Flash"].notes)


def test_documented_rejections_are_outside_the_accepted_sets() -> None:
    assert "xhigh" not in DOCUMENTED_PROFILES["GLM-5.3-Flash"].reasoning_efforts  # 422
    assert "high" not in DOCUMENTED_PROFILES["Qwen3.8-27B"].reasoning_efforts  # 400
    assert not DOCUMENTED_PROFILES["GLM-5.3-Flash"].accepts_images
    assert DOCUMENTED_PROFILES["MiniCPM5-2B"].reasoning_control is ReasoningControl.NOT_APPLICABLE
    assert DOCUMENTED_PROFILES["Gemma-4-31B-IT"].reasoning_control is ReasoningControl.ON_OFF


def test_mineru_is_an_ocr_model_without_chat_capabilities() -> None:
    profile = DOCUMENTED_PROFILES["MinerU2.5-Pro"]
    assert profile.kind is ModelKind.OCR
    assert not profile.is_chat
    assert not profile.supports_tools
    assert not profile.supports_json_object
    assert not profile.supports_streaming
    assert profile.pricing is None


@pytest.mark.parametrize(
    ("model_id", "family"),
    [
        ("Qwen3.8-27B", "qwen"),
        ("GLM-5.3-Flash", "glm"),
        ("MiniCPM-V-4.7-1B", "minicpm"),
        ("DeepSeek-V4.1-Flash", "deepseek"),
        ("MiMo-V2.6-Flash", "mimo"),
        ("1234", "1234"),
    ],
)
def test_family_comes_from_the_leading_letters(model_id: str, family: str) -> None:
    assert infer_family(model_id) == family


def test_documented_families_match_inference() -> None:
    for model_id, profile in DOCUMENTED_PROFILES.items():
        assert profile.family == infer_family(model_id)


def test_conservative_profile_allows_only_the_universal_shape() -> None:
    profile = conservative_profile("MiniCPM-V-4.7-1B", None)
    assert profile.source == "catalog_only"
    assert profile.context_length == CONSERVATIVE_CONTEXT
    assert profile.input_modalities == frozenset({"text"})
    assert set(profile.reasoning_efforts) == {"low", "medium"}
    assert profile.system_rule is SystemRule.AT_MOST_ONE_FIRST
    assert profile.developer_role is DeveloperRole.MAP_TO_SYSTEM
    assert not profile.supports_json_schema
    assert profile.pricing is None
    assert conservative_profile("X-1", 65_536).context_length == 65_536


def test_parse_catalog_reads_ids_and_tolerates_odd_entries() -> None:
    entries = parse_catalog(
        {
            "object": "list",
            "data": [
                {"id": "A-1", "context_length": 4096},
                {"id": "A-1", "context_length": 1},
                {"id": "B-2", "context_window": "8192"},
                {"id": "C-3", "max_model_len": 0},
                {"id": "D-4", "context_length": True},
                {"id": ""},
                {"name": "no id"},
                "not an object",
            ],
        }
    )
    assert [(e.id, e.context_length) for e in entries] == [
        ("A-1", 4096),
        ("B-2", 8192),
        ("C-3", None),
        ("D-4", None),
    ]
    assert parse_catalog([{"id": "E-5"}])[0].id == "E-5"


def test_parse_catalog_rejects_a_payload_without_a_list() -> None:
    with pytest.raises(ResponseShapeError):
        parse_catalog({"models": {}})


def test_availability_before_and_after_sync() -> None:
    catalog = ProfileCatalog()
    assert catalog.availability("GLM-5.3-Flash") is Availability.NOT_SYNCED
    assert catalog.is_usable("GLM-5.3-Flash")
    assert catalog.availability("Unknown-1") is Availability.UNKNOWN
    report = catalog.sync(
        [
            CatalogEntry(id="GLM-5.3-Flash", context_length=131_072),
            CatalogEntry(id="DeepSeek-V4-Flash", context_length=2_000_000),
            CatalogEntry(id="MiniCPM-V-4.7-1B", context_length=65_536),
        ],
        NOW,
    )
    assert catalog.availability("GLM-5.3-Flash") is Availability.AVAILABLE
    assert catalog.availability("Qwen3.8-27B") is Availability.WITHDRAWN
    assert not catalog.is_usable("Qwen3.8-27B")
    assert report.undocumented == ("MiniCPM-V-4.7-1B",)
    assert "Qwen3.8-27B" in report.withdrawn
    # The catalog may narrow the documented context window, never widen it.
    assert catalog.require("GLM-5.3-Flash").context_length == 131_072
    assert catalog.require("DeepSeek-V4-Flash").context_length == 1_048_576
    assert report.context_restricted == ("GLM-5.3-Flash",)
    unknown = catalog.require("MiniCPM-V-4.7-1B")
    assert unknown.source == "catalog_only"
    assert unknown.context_length == 65_536
    assert catalog.catalog_entry("MiniCPM-V-4.7-1B") is not None


def test_points_bill_reasoning_once_and_cached_tokens_at_the_cache_price() -> None:
    pricing = Pricing(input_per_mtok=0.15, output_per_mtok=0.50, cache_read_per_mtok=0.03)
    usage = Usage(
        prompt_tokens=2000, completion_tokens=400, reasoning_tokens=300, cached_tokens=500
    )
    expected = (1500 * 0.15 + 500 * 0.03 + 400 * 0.50) / 1_000_000
    assert pricing.points(usage) == pytest.approx(expected, rel=1e-12)


def test_points_without_cache_price_or_cache_count_overestimate_never_underestimate() -> None:
    no_cache_price = Pricing(input_per_mtok=1.0, output_per_mtok=2.0)
    assert no_cache_price.points(
        Usage(prompt_tokens=1000, completion_tokens=10, cached_tokens=400)
    ) == pytest.approx((1000 * 1.0 + 10 * 2.0) / 1e6)
    priced = Pricing(input_per_mtok=1.0, output_per_mtok=2.0, cache_read_per_mtok=0.1)
    assert priced.points(Usage(prompt_tokens=100, completion_tokens=0)) == pytest.approx(1e-4)
    # A cached count larger than the prompt is clamped.
    assert priced.points(
        Usage(prompt_tokens=100, completion_tokens=0, cached_tokens=1000)
    ) == pytest.approx(100 * 0.1 / 1e6)


@pytest.mark.parametrize(
    "usage",
    [None, Usage(), Usage(prompt_tokens=10), Usage(completion_tokens=10)],
)
def test_points_are_unknown_without_both_token_counts(usage: Usage | None) -> None:
    assert Pricing(input_per_mtok=1.0, output_per_mtok=1.0).points(usage) is None

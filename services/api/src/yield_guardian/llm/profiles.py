"""Capability profiles of the models served by AMD Token Factory, and catalog sync.

Every documented profile below is transcribed from ``docs/vendor/token-factory.md`` (the
team's summary of the Token Factory documentation, 2026-10-14). Where that page is ambiguous
the profile takes the conservative reading and says so in ``notes``; the request builder then
refuses anything outside the profile instead of letting the gateway reject it.

The live catalog (``GET /v1/models``) changes, so :class:`ProfileCatalog` merges it in:

* a documented model missing from the live catalog is reported as withdrawn;
* a live model that is not documented gets a conservative profile (text only, one system
  message first, ``reasoning_effort`` limited to ``low`` and ``medium`` which the docs say
  work on every chat model, no strict ``json_schema``, pricing unknown);
* the catalog can only *restrict* a documented profile (a smaller context window), never
  widen it, because the meaning of its capability flags is not documented.

Pricing is in points per million tokens. Catalog pricing is kept raw for display and is not
used for arithmetic, because its unit is not documented; ``GET /v1/usage`` stays the
authoritative record of spend.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from yield_guardian.llm.errors import ResponseShapeError
from yield_guardian.llm.messages import ReasoningEffort

Modality = Literal["text", "image", "audio", "document"]


class ModelKind(StrEnum):
    CHAT = "chat"
    OCR = "ocr"


class SystemRule(StrEnum):
    ANY = "any"
    """System messages anywhere, several allowed."""
    EXACTLY_ONE_FIRST = "exactly_one_first"
    """Exactly one system message, at index 0 (Qwen3.8-Flash-Next)."""
    AT_MOST_ONE_FIRST = "at_most_one_first"
    """At most one system message, at index 0 (Qwen3.8-27B, Gemma, unknown models)."""


class DeveloperRole(StrEnum):
    ACCEPTED = "accepted"
    MAP_TO_SYSTEM = "map_to_system"


class ReasoningControl(StrEnum):
    EFFORT = "effort"
    """``reasoning_effort`` takes one of ``reasoning_efforts``."""
    ON_OFF = "on_off"
    """Thinking can only be switched on or off."""
    NOT_APPLICABLE = "not_applicable"
    """The model does not think; ``reasoning_effort`` is never sent."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Usage(_Frozen):
    """Token counts reported by the server. Any field may be missing."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    """``usage.completion_tokens_details.reasoning_tokens``; included in completion_tokens."""
    cached_tokens: int | None = None
    """``usage.prompt_tokens_details.cached_tokens``; included in prompt_tokens."""


class Pricing(_Frozen):
    """Points per one million tokens."""

    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)
    cache_read_per_mtok: float | None = Field(default=None, ge=0)

    def points(self, usage: Usage | None) -> float | None:
        """Estimated points for one call, or None when the token counts are missing.

        Reasoning tokens are part of ``completion_tokens`` (OpenAI convention, which the
        ``completion_tokens_details`` breakdown follows), so they are billed once, as output.
        Cached prompt tokens are billed at the cache-read price when the server reports them;
        a missing count is treated as zero cached tokens, which can only overestimate.
        """
        if usage is None or usage.prompt_tokens is None or usage.completion_tokens is None:
            return None
        cached = min(max(usage.cached_tokens or 0, 0), usage.prompt_tokens)
        cache_price = (
            self.cache_read_per_mtok
            if self.cache_read_per_mtok is not None
            else self.input_per_mtok
        )
        total = (
            (usage.prompt_tokens - cached) * self.input_per_mtok
            + cached * cache_price
            + usage.completion_tokens * self.output_per_mtok
        )
        return total / 1_000_000


class ModelProfile(_Frozen):
    id: str
    family: str
    kind: ModelKind
    context_length: int | None
    input_modalities: frozenset[Modality]
    thinks_by_default: bool | None
    default_effort: ReasoningEffort | None = None
    reasoning_control: ReasoningControl
    reasoning_efforts: frozenset[ReasoningEffort]
    system_rule: SystemRule
    developer_role: DeveloperRole
    supports_tools: bool
    supports_json_object: bool
    supports_json_schema: bool
    supports_streaming: bool
    reports_reasoning_tokens: bool
    pricing: Pricing | None
    source: Literal["documented", "conservative"]
    notes: tuple[str, ...] = ()

    @property
    def accepts_images(self) -> bool:
        return "image" in self.input_modalities

    @property
    def is_chat(self) -> bool:
        return self.kind is ModelKind.CHAT


_DEEPSEEK_EFFORTS: frozenset[ReasoningEffort] = frozenset(
    ("none", "minimal", "low", "medium", "high", "xhigh", "max")
)
_FLASH_PRICING = Pricing(input_per_mtok=0.14, output_per_mtok=0.28, cache_read_per_mtok=0.0028)


def _deepseek(model_id: str, modalities: frozenset[Modality]) -> ModelProfile:
    return ModelProfile(
        id=model_id,
        family="deepseek",
        kind=ModelKind.CHAT,
        context_length=1_048_576,
        input_modalities=modalities,
        thinks_by_default=False,
        reasoning_control=ReasoningControl.EFFORT,
        reasoning_efforts=_DEEPSEEK_EFFORTS,
        system_rule=SystemRule.ANY,
        developer_role=DeveloperRole.ACCEPTED,
        supports_tools=True,
        supports_json_object=True,
        supports_json_schema=False,
        supports_streaming=True,
        reports_reasoning_tokens=True,
        pricing=_FLASH_PRICING,
        source="documented",
    )


_TEXT: frozenset[Modality] = frozenset({"text"})
_TEXT_IMAGE: frozenset[Modality] = frozenset({"text", "image"})

DOCUMENTED_PROFILES: Mapping[str, ModelProfile] = {
    p.id: p
    for p in (
        _deepseek("DeepSeek-V4-Flash", _TEXT),
        _deepseek("DeepSeek-V4.1-Flash", _TEXT_IMAGE),
        _deepseek("DeepSeek-V4-Flash-Vision-Exp", _TEXT_IMAGE),
        ModelProfile(
            id="MiMo-V2.6-Flash",
            family="mimo",
            kind=ModelKind.CHAT,
            context_length=1_048_576,
            input_modalities=frozenset({"text", "image", "audio"}),
            thinks_by_default=True,
            reasoning_control=ReasoningControl.EFFORT,
            reasoning_efforts=frozenset(("none", "low", "medium", "high")),
            system_rule=SystemRule.ANY,
            developer_role=DeveloperRole.ACCEPTED,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=True,
            supports_streaming=True,
            reports_reasoning_tokens=True,
            pricing=_FLASH_PRICING,
            source="documented",
            notes=(
                "'none' turns thinking off.",
                "Docs say 'none and the usual tiers'; read as low, medium and high. Other "
                "values are refused until verified.",
                "The only model documented to accept strict json_schema.",
            ),
        ),
        ModelProfile(
            id="GLM-5.3-Flash",
            family="glm",
            kind=ModelKind.CHAT,
            context_length=262_144,
            input_modalities=_TEXT,
            thinks_by_default=True,
            reasoning_control=ReasoningControl.EFFORT,
            reasoning_efforts=frozenset(("low", "medium", "high")),
            system_rule=SystemRule.ANY,
            developer_role=DeveloperRole.MAP_TO_SYSTEM,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=False,
            supports_streaming=True,
            reports_reasoning_tokens=True,
            pricing=Pricing(input_per_mtok=0.15, output_per_mtok=0.50, cache_read_per_mtok=0.03),
            source="documented",
            notes=(
                "xhigh returns 422; 'none' is not documented, so thinking cannot be turned off.",
                "The developer role returns 422; it is sent as system.",
                "Rejects images.",
            ),
        ),
        ModelProfile(
            id="Qwen3.8-Flash-Next",
            family="qwen",
            kind=ModelKind.CHAT,
            context_length=262_144,
            input_modalities=_TEXT_IMAGE,
            thinks_by_default=True,
            default_effort="xhigh",
            reasoning_control=ReasoningControl.EFFORT,
            reasoning_efforts=frozenset(("none", "low", "medium", "xhigh")),
            system_rule=SystemRule.EXACTLY_ONE_FIRST,
            developer_role=DeveloperRole.MAP_TO_SYSTEM,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=False,
            supports_streaming=True,
            reports_reasoning_tokens=True,
            pricing=Pricing(input_per_mtok=0.15, output_per_mtok=0.47, cache_read_per_mtok=0.016),
            source="documented",
            notes=("Exactly one system message, first; system role only.",),
        ),
        ModelProfile(
            id="Qwen3.8-27B",
            family="qwen",
            kind=ModelKind.CHAT,
            context_length=131_072,
            input_modalities=_TEXT_IMAGE,
            thinks_by_default=True,
            default_effort="xhigh",
            reasoning_control=ReasoningControl.EFFORT,
            reasoning_efforts=frozenset(("low", "medium", "xhigh")),
            system_rule=SystemRule.AT_MOST_ONE_FIRST,
            developer_role=DeveloperRole.MAP_TO_SYSTEM,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=False,
            supports_streaming=True,
            reports_reasoning_tokens=False,
            pricing=Pricing(input_per_mtok=0.50, output_per_mtok=3.00, cache_read_per_mtok=0.05),
            source="documented",
            notes=(
                "high returns 400.",
                "Reasoning tokens are not reported in usage.",
                "Developer role not documented; sent as system (conservative).",
            ),
        ),
        ModelProfile(
            id="MiniCPM5-2B",
            family="minicpm",
            kind=ModelKind.CHAT,
            context_length=131_072,
            input_modalities=_TEXT,
            thinks_by_default=False,
            reasoning_control=ReasoningControl.NOT_APPLICABLE,
            reasoning_efforts=frozenset(),
            system_rule=SystemRule.ANY,
            developer_role=DeveloperRole.MAP_TO_SYSTEM,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=False,
            supports_streaming=True,
            reports_reasoning_tokens=False,
            pricing=Pricing(
                input_per_mtok=0.124, output_per_mtok=0.7425, cache_read_per_mtok=0.124
            ),
            source="documented",
            notes=("No thinking; reasoning_effort is never sent.",),
        ),
        ModelProfile(
            id="Gemma-4-31B-IT",
            family="gemma",
            kind=ModelKind.CHAT,
            context_length=262_144,
            input_modalities=_TEXT_IMAGE,
            thinks_by_default=False,
            reasoning_control=ReasoningControl.ON_OFF,
            reasoning_efforts=frozenset(("none",)),
            system_rule=SystemRule.AT_MOST_ONE_FIRST,
            developer_role=DeveloperRole.MAP_TO_SYSTEM,
            supports_tools=True,
            supports_json_object=True,
            supports_json_schema=False,
            supports_streaming=True,
            reports_reasoning_tokens=False,
            pricing=Pricing(input_per_mtok=0.50, output_per_mtok=3.00, cache_read_per_mtok=0.05),
            source="documented",
            notes=(
                "Thinking is on or off only; the value that switches it on is not documented, "
                "so only 'none' (off) is sent.",
            ),
        ),
        ModelProfile(
            id="MinerU2.5-Pro",
            family="mineru",
            kind=ModelKind.OCR,
            context_length=None,
            input_modalities=frozenset({"document", "image"}),
            thinks_by_default=None,
            reasoning_control=ReasoningControl.NOT_APPLICABLE,
            reasoning_efforts=frozenset(),
            system_rule=SystemRule.ANY,
            developer_role=DeveloperRole.MAP_TO_SYSTEM,
            supports_tools=False,
            supports_json_object=False,
            supports_json_schema=False,
            supports_streaming=False,
            reports_reasoning_tokens=False,
            pricing=None,
            source="documented",
            notes=("Document OCR through POST /v1/ocr only; billed per page ('limited free').",),
        ),
    )
}

EFFORT_ORDER: tuple[ReasoningEffort, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

CONSERVATIVE_CONTEXT = 32_768
"""Context window assumed for an undocumented model whose catalog entry gives none."""

_CONSERVATIVE_EFFORTS: frozenset[ReasoningEffort] = frozenset(("low", "medium"))


def infer_family(model_id: str) -> str:
    """Model family from the id's leading letters: ``Qwen3.8-27B`` -> ``qwen``."""
    match = re.match(r"[A-Za-z]+", model_id)
    return match.group(0).lower() if match else model_id.lower()


def conservative_profile(model_id: str, context_length: int | None) -> ModelProfile:
    """Profile for a model the docs do not describe: only shapes documented to work on every
    chat model are allowed."""
    return ModelProfile(
        id=model_id,
        family=infer_family(model_id),
        kind=ModelKind.CHAT,
        context_length=context_length or CONSERVATIVE_CONTEXT,
        input_modalities=_TEXT,
        thinks_by_default=None,
        reasoning_control=ReasoningControl.EFFORT,
        reasoning_efforts=_CONSERVATIVE_EFFORTS,
        system_rule=SystemRule.AT_MOST_ONE_FIRST,
        developer_role=DeveloperRole.MAP_TO_SYSTEM,
        supports_tools=True,
        supports_json_object=True,
        supports_json_schema=False,
        supports_streaming=True,
        reports_reasoning_tokens=False,
        pricing=None,
        source="conservative",
        notes=(
            "Not in the documentation: text only, one system message first, reasoning_effort "
            "low or medium, json_object only, pricing unknown.",
        ),
    )


class CatalogEntry(_Frozen):
    """One model from ``GET /v1/models``. Only ``id`` is relied on; the rest of the shape is
    not documented and is read tolerantly."""

    id: str
    context_length: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


_CONTEXT_KEYS = ("context_length", "context_window", "max_context_length", "max_model_len")


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def parse_catalog(payload: object) -> list[CatalogEntry]:
    """Parse an OpenAI-style model list (``{"data": [...]}``) or a bare list."""
    items: object = payload.get("data") if isinstance(payload, Mapping) else payload
    if not isinstance(items, list):
        raise ResponseShapeError("model catalog has no 'data' list")
    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id.strip() or model_id in seen:
            continue
        seen.add(model_id)
        context = None
        for key in _CONTEXT_KEYS:
            context = _positive_int(item.get(key))
            if context is not None:
                break
        entries.append(CatalogEntry(id=model_id, context_length=context, raw=dict(item)))
    return entries


class Availability(StrEnum):
    AVAILABLE = "available"
    """Listed by the live catalog."""
    NOT_SYNCED = "not_synced"
    """No catalog has been read yet; documented models are assumed usable."""
    WITHDRAWN = "withdrawn"
    """Documented, but missing from the live catalog."""
    UNKNOWN = "unknown"
    """Neither documented nor listed."""


class CatalogSyncReport(_Frozen):
    synced_at: datetime
    listed: tuple[str, ...]
    undocumented: tuple[str, ...]
    withdrawn: tuple[str, ...]
    context_restricted: tuple[str, ...]


class ProfileCatalog:
    """Documented profiles merged with the live catalog."""

    def __init__(self, documented: Mapping[str, ModelProfile] | None = None) -> None:
        self._documented: dict[str, ModelProfile] = dict(
            DOCUMENTED_PROFILES if documented is None else documented
        )
        self._live: dict[str, CatalogEntry] | None = None
        self._profiles: dict[str, ModelProfile] = dict(self._documented)
        self.last_sync: CatalogSyncReport | None = None

    def sync(self, entries: Sequence[CatalogEntry], at: datetime) -> CatalogSyncReport:
        live = {entry.id: entry for entry in entries}
        profiles: dict[str, ModelProfile] = {}
        restricted: list[str] = []
        for model_id, profile in self._documented.items():
            entry = live.get(model_id)
            if (
                entry is not None
                and entry.context_length is not None
                and profile.context_length is not None
                and entry.context_length < profile.context_length
            ):
                profile = profile.model_copy(update={"context_length": entry.context_length})
                restricted.append(model_id)
            profiles[model_id] = profile
        undocumented = sorted(set(live) - set(self._documented))
        for model_id in undocumented:
            profiles[model_id] = conservative_profile(model_id, live[model_id].context_length)
        self._live = live
        self._profiles = profiles
        report = CatalogSyncReport(
            synced_at=at,
            listed=tuple(sorted(live)),
            undocumented=tuple(undocumented),
            withdrawn=tuple(sorted(set(self._documented) - set(live))),
            context_restricted=tuple(sorted(restricted)),
        )
        self.last_sync = report
        return report

    @property
    def synced(self) -> bool:
        return self._live is not None

    def get(self, model_id: str) -> ModelProfile | None:
        return self._profiles.get(model_id)

    def require(self, model_id: str) -> ModelProfile:
        profile = self._profiles.get(model_id)
        if profile is None:
            raise KeyError(f"no profile for model {model_id!r}")
        return profile

    def availability(self, model_id: str) -> Availability:
        if self._live is None:
            return Availability.NOT_SYNCED if model_id in self._documented else Availability.UNKNOWN
        if model_id in self._live:
            return Availability.AVAILABLE
        if model_id in self._documented:
            return Availability.WITHDRAWN
        return Availability.UNKNOWN

    def is_usable(self, model_id: str) -> bool:
        return self.availability(model_id) in (Availability.AVAILABLE, Availability.NOT_SYNCED)

    def profiles(self) -> list[ModelProfile]:
        return [self._profiles[k] for k in sorted(self._profiles)]

    def catalog_entry(self, model_id: str) -> CatalogEntry | None:
        return None if self._live is None else self._live.get(model_id)


def efforts_text(efforts: Collection[ReasoningEffort]) -> str:
    """Accepted efforts in their natural order, for error messages."""
    order = [e for e in EFFORT_ORDER if e in efforts]
    return ", ".join(order) if order else "(none accepted)"

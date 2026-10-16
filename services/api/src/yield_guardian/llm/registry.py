"""Role-to-model registry (PLAN section 7.1): defaults, fallback chains, validation, storage.

Each role has an ordered chain of :class:`ModelChoice`. The first usable entry serves the
call; later entries are fallbacks. Every chain entry is validated against the model's
profile (and the live catalog once synced) when it is assigned, so the admin cannot select
a combination the gateway would reject:

* every chat role sets ``reasoning_effort`` explicitly (PLAN 7.2), to a value the profile
  accepts; models without thinking take none;
* structured roles (writer, verifier, router) use ``json_schema`` only where the profile
  supports it, otherwise ``json_object`` with Pydantic validation;
* the investigator and chat roles need tool calling, vision needs image input, OCR needs
  the OCR model;
* the verifier chain must always offer a model of a different family from each writer
  model, because the verifier must not grade its own family's work.

Assignments are persisted through :class:`RoleAssignmentStore` (in memory here, a database
table in production).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from yield_guardian.contracts.models import RoleName
from yield_guardian.llm.errors import LlmError
from yield_guardian.llm.messages import ReasoningEffort
from yield_guardian.llm.profiles import (
    EFFORT_ORDER,
    TOKENHARBOR_MODEL,
    Availability,
    ModelKind,
    ModelProfile,
    ProfileCatalog,
    Provider,
    ReasoningControl,
    efforts_text,
)

MAX_CHAIN_LENGTH = 5


class Role(StrEnum):
    INVESTIGATOR = "investigator"
    WRITER = "writer"
    VERIFIER = "verifier"
    CHAT = "chat"
    ROUTER = "router"
    OCR = "ocr"
    VISION = "vision"


class ResponseMode(StrEnum):
    TEXT = "text"
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class ModelChoice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    reasoning_effort: ReasoningEffort | None = None
    response_mode: ResponseMode = ResponseMode.TEXT
    provider: Provider = Provider.TOKEN_FACTORY
    """The endpoint (base URL and key) that serves this entry."""


class RoleAssignment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Role
    chain: Annotated[tuple[ModelChoice, ...], Field(min_length=1, max_length=MAX_CHAIN_LENGTH)]
    updated_at: datetime | None = None
    updated_by: str | None = None

    @property
    def primary(self) -> ModelChoice:
        return self.chain[0]


def _c(model: str, effort: ReasoningEffort | None, mode: ResponseMode) -> ModelChoice:
    return ModelChoice(model=model, reasoning_effort=effort, response_mode=mode)


def _harbor(mode: ResponseMode) -> ModelChoice:
    """The TokenHarbor model, first on every text role; skipped (silently) when
    ``TOKENHARBOR_API_KEY`` is not set, and any failure moves to the next entry. It takes no
    ``reasoning_effort``."""
    return ModelChoice(model=TOKENHARBOR_MODEL, response_mode=mode, provider=Provider.TOKENHARBOR)


_T, _O = ResponseMode.TEXT, ResponseMode.JSON_OBJECT

DEFAULT_CHAINS: dict[Role, tuple[ModelChoice, ...]] = {
    Role.INVESTIGATOR: (
        _harbor(_T),
        _c("DeepSeek-V4.1-Flash", "low", _T),
        _c("GLM-5.3-Flash", "low", _T),
        _c("Qwen3.8-Flash-Next", "low", _T),
    ),
    Role.WRITER: (
        # Measured live on 2026-10-14: Qwen3.8-Flash-Next is the one model that reliably
        # returned long outputs (chat: 1,175 to 1,348 tokens in 43 to 62 s, 4 of 4 calls OK).
        # DeepSeek-V4.1-Flash answered HTTP 500 (upstream 504 call_upstream_timeout) when
        # writing, and MiMo-V2.6-Flash (about 5 tokens/s) and Qwen3.8-27B ran past the writer
        # deadline. All answer in json_object (MiMo refuses strict json_schema) and the report
        # is validated in code. "none" keeps Qwen fast (it is what chat runs live) and is the
        # one MiMo effort the docs name. Not TokenHarbor: live on 2026-10-16 its thinking model
        # spent all 16,384 output tokens reasoning and returned an empty report (89 s).
        _c("Qwen3.8-Flash-Next", "none", _O),
        _c("DeepSeek-V4.1-Flash", "low", _O),
        _c("MiMo-V2.6-Flash", "none", _O),
    ),
    Role.VERIFIER: (
        _c("GLM-5.3-Flash", "low", _O),
        _c("DeepSeek-V4-Flash", "low", _O),
    ),
    Role.CHAT: (
        _harbor(_T),
        _c("Qwen3.8-Flash-Next", "none", _T),
        _c("DeepSeek-V4-Flash", "none", _T),
    ),
    Role.ROUTER: (
        _harbor(_O),
        _c("MiniCPM5-2B", None, _O),
        _c("DeepSeek-V4-Flash", "none", _O),
    ),
    Role.VISION: (
        _c("DeepSeek-V4.1-Flash", "low", _O),
        _c("Qwen3.8-Flash-Next", "low", _O),
    ),
    Role.OCR: (_c("MinerU2.5-Pro", None, _T),),
}

_STRUCTURED_ROLES = frozenset({Role.WRITER, Role.VERIFIER, Role.ROUTER})

ROLE_EFFORT_POLICY: dict[Role, ReasoningEffort | None] = {
    Role.INVESTIGATOR: "low",
    Role.WRITER: "low",
    Role.VERIFIER: "low",
    Role.CHAT: "none",
    Role.ROUTER: "none",
    Role.VISION: "low",
    Role.OCR: None,
}
"""Reasoning effort per role (PLAN 7.1); a model that does not accept the role's value gets
the nearest value it accepts (the lower one on a tie)."""


def role_name(role: Role) -> RoleName:
    return role.value


def policy_effort(role: Role, profile: ModelProfile) -> ReasoningEffort | None:
    if role is Role.OCR or profile.reasoning_control is ReasoningControl.NOT_APPLICABLE:
        return None
    accepted = [e for e in EFFORT_ORDER if e in profile.reasoning_efforts]
    if not accepted:
        return None
    wanted = ROLE_EFFORT_POLICY[role] or "none"
    if wanted in accepted:
        return wanted
    target = EFFORT_ORDER.index(wanted)
    return min(accepted, key=lambda e: (abs(EFFORT_ORDER.index(e) - target), EFFORT_ORDER.index(e)))


def default_mode(role: Role, profile: ModelProfile) -> ResponseMode:
    if role in _STRUCTURED_ROLES or role is Role.VISION:
        return (
            ResponseMode.JSON_SCHEMA if profile.supports_json_schema else ResponseMode.JSON_OBJECT
        )
    return ResponseMode.TEXT


def choice_for(
    role: Role, profile: ModelProfile, *, existing: ModelChoice | None = None
) -> ModelChoice:
    """The chain entry for ``profile`` in ``role``: the existing entry if there is one, else
    the role's policy effort and response mode adapted to the profile."""
    if existing is not None:
        return existing
    return ModelChoice(
        model=profile.id,
        reasoning_effort=policy_effort(role, profile),
        response_mode=default_mode(role, profile),
        provider=profile.provider,
    )


def _effort_problems(choice: ModelChoice, profile: ModelProfile) -> list[str]:
    effort = choice.reasoning_effort
    control = profile.reasoning_control
    if control is ReasoningControl.NOT_APPLICABLE:
        if effort is not None:
            return [f"{profile.id} does not take reasoning_effort (got {effort!r})"]
        return []
    if effort is None:
        return [
            f"{profile.id} needs an explicit reasoning_effort (accepted: "
            f"{efforts_text(profile.reasoning_efforts)})"
        ]
    if effort not in profile.reasoning_efforts:
        return [
            f"{profile.id} does not accept reasoning_effort {effort!r} (accepted: "
            f"{efforts_text(profile.reasoning_efforts)})"
        ]
    return []


def _mode_problems(role: Role, choice: ModelChoice, profile: ModelProfile) -> list[str]:
    mode = choice.response_mode
    problems: list[str] = []
    if mode is ResponseMode.JSON_SCHEMA and not profile.supports_json_schema:
        problems.append(f"{profile.id} does not support strict json_schema")
    if mode is ResponseMode.JSON_OBJECT and not profile.supports_json_object:
        problems.append(f"{profile.id} does not support json_object")
    if role in _STRUCTURED_ROLES and mode is ResponseMode.TEXT:
        problems.append(f"the {role} role needs json_schema or json_object output")
    if role in (Role.INVESTIGATOR, Role.CHAT, Role.OCR) and mode is not ResponseMode.TEXT:
        problems.append(f"the {role} role uses text output")
    return problems


def _role_problems(role: Role, profile: ModelProfile) -> list[str]:
    if role is Role.OCR:
        return [] if profile.kind is ModelKind.OCR else [f"{profile.id} is not an OCR model"]
    if profile.kind is not ModelKind.CHAT:
        return [f"{profile.id} is not a chat model"]
    problems: list[str] = []
    if role in (Role.INVESTIGATOR, Role.CHAT) and not profile.supports_tools:
        problems.append(f"{profile.id} does not support tool calling")
    if role is Role.CHAT and not profile.supports_streaming:
        problems.append(f"{profile.id} does not support streaming")
    if role is Role.VISION and not profile.accepts_images:
        problems.append(f"{profile.id} does not accept images")
    return problems


def validate_chain(role: Role, chain: Sequence[ModelChoice], catalog: ProfileCatalog) -> list[str]:
    """Every reason the chain cannot be assigned to the role (empty when valid)."""
    problems: list[str] = []
    if not chain:
        return ["the chain is empty"]
    if len(chain) > MAX_CHAIN_LENGTH:
        problems.append(f"the chain has {len(chain)} entries; at most {MAX_CHAIN_LENGTH}")
    models = [choice.model for choice in chain]
    duplicates = sorted({m for m in models if models.count(m) > 1})
    if duplicates:
        problems.append(f"models listed twice: {', '.join(duplicates)}")
    for choice in chain:
        profile = catalog.get(choice.model)
        if profile is None:
            problems.append(f"{choice.model}: unknown model (not documented, not in the catalog)")
            continue
        if catalog.availability(choice.model) is Availability.WITHDRAWN:
            problems.append(f"{choice.model}: documented but missing from the live catalog")
        if choice.provider is not profile.provider:
            problems.append(
                f"{choice.model} is served by {profile.provider}, not {choice.provider}"
            )
        problems.extend(_role_problems(role, profile))
        problems.extend(_effort_problems(choice, profile))
        problems.extend(_mode_problems(role, choice, profile))
    return problems


def family_problems(
    writer_chain: Sequence[ModelChoice],
    verifier_chain: Sequence[ModelChoice],
    catalog: ProfileCatalog,
) -> list[str]:
    """For each writer model, the verifier chain must offer a model of another family."""

    def family(choice: ModelChoice) -> str | None:
        profile = catalog.get(choice.model)
        return profile.family if profile else None

    verifier_families = {f for f in map(family, verifier_chain) if f is not None}
    problems: list[str] = []
    for choice in writer_chain:
        writer_family = family(choice)
        if writer_family is not None and not (verifier_families - {writer_family}):
            problems.append(
                f"no verifier model outside the {writer_family} family, which writer "
                f"{choice.model} belongs to"
            )
    return problems


class InvalidAssignmentError(LlmError):
    def __init__(self, role: Role, problems: Sequence[str]) -> None:
        super().__init__(f"invalid chain for role {role}: " + "; ".join(problems))
        self.role = role
        self.problems = list(problems)


@runtime_checkable
class RoleAssignmentStore(Protocol):
    async def load(self) -> Sequence[RoleAssignment]: ...

    async def save(self, assignment: RoleAssignment) -> None: ...


class InMemoryRoleAssignmentStore:
    def __init__(self, initial: Sequence[RoleAssignment] = ()) -> None:
        self.saved: dict[Role, RoleAssignment] = {a.role: a for a in initial}

    async def load(self) -> Sequence[RoleAssignment]:
        return list(self.saved.values())

    async def save(self, assignment: RoleAssignment) -> None:
        self.saved[assignment.role] = assignment


@dataclass(frozen=True, slots=True)
class ResolvedChoice:
    choice: ModelChoice
    profile: ModelProfile


@dataclass(frozen=True, slots=True)
class Resolution:
    role: Role
    usable: tuple[ResolvedChoice, ...]
    skipped: tuple[tuple[str, str], ...] = field(default=())


class ModelRegistry:
    def __init__(
        self,
        catalog: ProfileCatalog,
        store: RoleAssignmentStore,
        *,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        providers: Collection[Provider] = (Provider.TOKEN_FACTORY,),
    ) -> None:
        self.catalog = catalog
        self.providers = frozenset(providers)
        """Providers with a key configured; entries of any other provider are skipped silently
        (TokenHarbor without ``TOKENHARBOR_API_KEY``)."""
        self._store = store
        self._wall_clock = wall_clock
        self._assignments: dict[Role, RoleAssignment] = {
            role: RoleAssignment(role=role, chain=chain) for role, chain in DEFAULT_CHAINS.items()
        }
        self.load_warnings: list[str] = []

    async def load(self) -> list[str]:
        """Apply stored assignments; an invalid stored chain is ignored (the default stays)
        and reported."""
        warnings: list[str] = []
        stored = {a.role: a for a in await self._store.load()}
        for role, saved in stored.items():
            assignment, coerced = self._coerce_schema(saved)
            if coerced:
                warnings.append(
                    f"stored chain for {role}: json_schema changed to json_object for "
                    + ", ".join(coerced)
                    + " (the model does not accept strict json_schema)"
                )
            problems = validate_chain(role, assignment.chain, self.catalog)
            if problems:
                warnings.append(f"stored chain for {role} ignored: " + "; ".join(problems))
            else:
                self._assignments[role] = assignment
        cross = family_problems(
            self._assignments[Role.WRITER].chain,
            self._assignments[Role.VERIFIER].chain,
            self.catalog,
        )
        if cross:
            for role in (Role.WRITER, Role.VERIFIER):
                self._assignments[role] = RoleAssignment(role=role, chain=DEFAULT_CHAINS[role])
            warnings.append("writer and verifier reset to defaults: " + "; ".join(cross))
        self.load_warnings = warnings
        return warnings

    def _coerce_schema(self, assignment: RoleAssignment) -> tuple[RoleAssignment, list[str]]:
        """A stored json_schema entry for a model now known to refuse it (MiMo-V2.6-Flash,
        measured live) becomes json_object; the rest of the chain is kept as saved."""
        coerced: list[str] = []
        chain: list[ModelChoice] = []
        for choice in assignment.chain:
            profile = self.catalog.get(choice.model)
            if (
                choice.response_mode is ResponseMode.JSON_SCHEMA
                and profile is not None
                and not profile.supports_json_schema
                and profile.supports_json_object
            ):
                choice = choice.model_copy(update={"response_mode": ResponseMode.JSON_OBJECT})
                coerced.append(choice.model)
            chain.append(choice)
        if not coerced:
            return assignment, []
        return assignment.model_copy(update={"chain": tuple(chain)}), coerced

    def assignment(self, role: Role) -> RoleAssignment:
        return self._assignments[role]

    def assignments(self) -> list[RoleAssignment]:
        return [self._assignments[role] for role in Role]

    def validate(self, role: Role, chain: Sequence[ModelChoice]) -> list[str]:
        problems = validate_chain(role, chain, self.catalog)
        if role is Role.WRITER:
            problems += family_problems(chain, self._assignments[Role.VERIFIER].chain, self.catalog)
        elif role is Role.VERIFIER:
            problems += family_problems(self._assignments[Role.WRITER].chain, chain, self.catalog)
        return problems

    async def assign(
        self, role: Role, chain: Sequence[ModelChoice], *, actor: str
    ) -> RoleAssignment:
        problems = self.validate(role, chain)
        if problems:
            raise InvalidAssignmentError(role, problems)
        assignment = RoleAssignment(
            role=role, chain=tuple(chain), updated_at=self._wall_clock(), updated_by=actor
        )
        await self._store.save(assignment)
        self._assignments[role] = assignment
        return assignment

    async def reset(self, role: Role, *, actor: str) -> RoleAssignment:
        return await self.assign(role, DEFAULT_CHAINS[role], actor=actor)

    def resolve(self, role: Role, *, exclude_families: frozenset[str] = frozenset()) -> Resolution:
        usable: list[ResolvedChoice] = []
        skipped: list[tuple[str, str]] = []
        for choice in self._assignments[role].chain:
            if choice.provider not in self.providers:
                continue
            profile = self.catalog.get(choice.model)
            availability = self.catalog.availability(choice.model)
            if profile is None or not self.catalog.is_usable(choice.model):
                skipped.append((choice.model, f"not usable ({availability})"))
            elif profile.family in exclude_families:
                skipped.append((choice.model, f"family {profile.family} excluded"))
            else:
                usable.append(ResolvedChoice(choice=choice, profile=profile))
        return Resolution(role=role, usable=tuple(usable), skipped=tuple(skipped))

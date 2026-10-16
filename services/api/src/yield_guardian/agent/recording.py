"""Choosing the recorded demo investigations, and bounding what they can cost (PLAN L11).

Alarm choice (code only, no model, the same on every host with the same bundle):

1. take the alarms the SECOM alarm rules raise on units of the held-out **test** block, at **alarm**
   severity (failure risk at or above the default operating point; T² or SPE beyond its 99.9%
   control limit), in plant order;
2. pick round-robin over the kinds in the order risk, T², SPE: the first risk alarm, the first
   T² alarm, the first SPE alarm, then the second of each, and so on;
3. skip an alarm on a unit already picked, so each run is about a different unit.

The point bound assumes nothing about how long the run's prompts are: each call's prompt is at
most the model's context window minus the call's ``max_tokens``, and its completion (reasoning
included) at most ``max_tokens``. Every model of a role's chain is counted for every call,
because a model can answer, be billed, and fail validation before the next one is tried. A
request the server refused or that failed in transport is assumed unbilled. The bound is
therefore far above any real run; it is what the run cannot exceed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from yield_guardian.agent.graph import InvestigationLimits
from yield_guardian.agent.verifier import VERIFIER_MAX_TOKENS
from yield_guardian.bundles.secom import SecomBundle
from yield_guardian.contracts.investigation import InvestigationTrigger
from yield_guardian.llm.profiles import ProfileCatalog, Provider
from yield_guardian.llm.registry import ModelRegistry, Role
from yield_guardian.science.secom.alarms import AlarmRule, alarm_rules

KINDS = ("risk", "t2", "spe")
SELECTION_RULE = (
    "test-block alarms at alarm severity, in plant order, round-robin over risk, T2, SPE, "
    "one per unit"
)


@dataclass(frozen=True, slots=True)
class ChosenAlarm:
    alarm_id: str
    unit_id: int
    sequence: int
    kind: str
    message: str

    def trigger(self) -> InvestigationTrigger:
        return InvestigationTrigger(kind="alarm", ref=self.alarm_id, question=None)


def choose_alarms(bundle: SecomBundle, count: int) -> list[ChosenAlarm]:
    if count < 1:
        raise ValueError("choose at least one alarm")
    timeline = bundle.timeline
    rules = alarm_rules(bundle)
    by_kind: dict[str, list[AlarmRule]] = {kind: [] for kind in KINDS}
    for sequence, found in enumerate(rules):
        if timeline.block[sequence] != "test":
            continue
        for rule in found:
            if rule.kind in by_kind and rule.severity == "alarm":
                by_kind[rule.kind].append(rule)
    chosen: list[ChosenAlarm] = []
    units: set[int] = set()
    cursors = dict.fromkeys(KINDS, 0)
    while len(chosen) < count and any(cursors[k] < len(by_kind[k]) for k in KINDS):
        for kind in KINDS:
            queue = by_kind[kind]
            while cursors[kind] < len(queue):
                rule = queue[cursors[kind]]
                cursors[kind] += 1
                unit = int(timeline.unit_id[rule.sequence])
                if unit in units:
                    continue
                units.add(unit)
                chosen.append(
                    ChosenAlarm(
                        f"AL-{unit}-{rule.kind}", unit, rule.sequence, rule.kind, rule.message
                    )
                )
                break
            if len(chosen) == count:
                break
    return chosen


@dataclass(frozen=True, slots=True)
class RoleBound:
    role: Role
    calls: int
    max_tokens: int
    models: tuple[str, ...]
    points: float


@dataclass(frozen=True, slots=True)
class InvestigationBound:
    roles: tuple[RoleBound, ...]

    @property
    def points(self) -> float:
        return sum(r.points for r in self.roles)


class UnboundedError(ValueError):
    """A model of a chain has no documented price or context window."""


def _call_bound(catalog: ProfileCatalog, model: str, max_tokens: int) -> float:
    profile = catalog.get(model)
    if profile is None or profile.pricing is None or profile.context_length is None:
        raise UnboundedError(f"{model} has no documented price or context window")
    prompt = max(profile.context_length - max_tokens, 0)
    pricing = profile.pricing
    return (prompt * pricing.input_per_mtok + max_tokens * pricing.output_per_mtok) / 1e6


def investigation_bound(
    registry: ModelRegistry, limits: InvestigationLimits | None = None
) -> InvestigationBound:
    """The most points one investigation can spend with the registry's current chains."""
    limits = limits or InvestigationLimits()
    rounds = 1 + limits.max_revisions
    plan: Sequence[tuple[Role, int, int]] = (
        # each plan call asks for at least one tool call or ends the evidence loop
        (Role.INVESTIGATOR, limits.max_tool_steps, limits.plan_max_tokens),
        (Role.WRITER, rounds, limits.writer_max_tokens),
        (Role.VERIFIER, rounds, VERIFIER_MAX_TOKENS),
    )
    roles = []
    for role, calls, max_tokens in plan:
        # Only Token Factory spends points; a TokenHarbor entry costs none.
        models = tuple(
            c.model for c in registry.assignment(role).chain if c.provider is Provider.TOKEN_FACTORY
        )
        per_call = sum(_call_bound(registry.catalog, m, max_tokens) for m in models)
        roles.append(RoleBound(role, calls, max_tokens, models, calls * per_call))
    return InvestigationBound(tuple(roles))

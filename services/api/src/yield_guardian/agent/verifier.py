"""Report verification (PLAN 7.4), in the plan's order.

1. Schema: the report is a validated :class:`Report` before it gets here (``json_object``
   answers validated by Pydantic; MiMo refused strict ``json_schema`` live on 2026-10-14; an
   answer that fails is retried on the next writer model by the gateway).
2. Numbers: every number in every text field must be listed in ``numbers[]`` and match the
   cited evidence at its JSON Pointer, within the rounding the text shows; a finding or action
   must cite the evidence its numbers come from. Identifiers (units, sensors, wafers, lots,
   alarms, dates) must exist in the evidence.
3. Citations: every evidence ID a finding, an action, a number or a hypothesis cites must exist;
   every source a hypothesis names must be in the knowledge base; a hypothesis assessed
   ``supported`` needs an observation for it, one assessed ``not_supported`` one against it.
4. Wording: causal phrases are rejected (:mod:`yield_guardian.agent.wording`).
5. Claims: a model of a different family from the writer judges whether each finding is
   supported by the evidence it cites.

Checks 1 to 4 are code. Check 5 runs when the code checks pass, or on the last round, so a
report about to be rewritten does not spend a verifier call. A report with remaining errors
after two revisions is shown with the issues flagged (``passed`` false).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from yield_guardian.agent.grounding import EvidenceFacts, redact_unverified
from yield_guardian.agent.numbers import (
    NumberMention,
    appears_in_text,
    magnitude_matches,
    matches,
    names_a_level,
    parse_number,
    scan,
    written_value_matches,
)
from yield_guardian.agent.pointer import PointerError, resolve
from yield_guardian.agent.prompts import VERIFIER_SYSTEM, data_message
from yield_guardian.agent.tools import model_view
from yield_guardian.agent.wording import ASSOCIATION_HINT, causal_phrases
from yield_guardian.contracts.investigation import (
    ClaimVerdict,
    Evidence,
    HypothesisEvidence,
    InvestigationTrigger,
    IssueCode,
    NumberRef,
    Report,
    Verification,
    VerificationIssue,
)
from yield_guardian.llm.errors import LlmError
from yield_guardian.llm.gateway import CallOptions, LlmGateway
from yield_guardian.llm.messages import ChatMessage, ChatRequest
from yield_guardian.llm.registry import Role

VERIFIER_MAX_TOKENS = 2048
CLAIMS_SCHEMA_NAME = "claim_checks"
_ALARM_UNIT = re.compile(r"^AL-(?P<unit>[0-9]+)-")


class ClaimCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_index: int = Field(ge=0)
    verdict: Literal["supported", "partially_supported", "unsupported"]
    note: str = Field(max_length=400)


class ClaimChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimCheck]


@dataclass(frozen=True, slots=True)
class TextField:
    location: str
    text: str
    cites: tuple[str, ...] | None
    """Evidence IDs the containing finding or action cites (None for summary, limitations)."""


def text_fields(report: Report) -> Iterator[TextField]:
    yield TextField("summary", report.summary, None)
    for i, finding in enumerate(report.findings):
        yield TextField(f"findings[{i}].claim", finding.claim, tuple(finding.evidence_ids))
    for i, action in enumerate(report.actions):
        cites = tuple(action.evidence_ids)
        yield TextField(f"actions[{i}].action", action.action, cites)
        yield TextField(f"actions[{i}].rationale", action.rationale, cites)
    for i, limitation in enumerate(report.limitations):
        yield TextField(f"limitations[{i}]", limitation, None)
    for i, hypothesis in enumerate(report.hypotheses):
        observed = (*hypothesis.evidence_for, *hypothesis.evidence_against)
        cites = tuple(item.evidence_id for item in observed)
        yield TextField(f"hypotheses[{i}].hypothesis", hypothesis.hypothesis, cites)
        for side, items in (
            ("evidence_for", hypothesis.evidence_for),
            ("evidence_against", hypothesis.evidence_against),
        ):
            for j, item in enumerate(items):
                location = f"hypotheses[{i}].{side}[{j}].observation"
                yield TextField(location, item.observation, (item.evidence_id,))


REPORT_REDACTION = "[unverified]"
"""Stands in, in the report shown to the engineer, for a number or identifier code could not
verify (the verification lists what it was and why)."""

_TEXT_LIMITS = {
    "summary": 1200,
    "claim": 600,
    "action": 300,
    "rationale": 600,
    "hypothesis": 400,
    "observation": 300,
}


@dataclass(frozen=True, slots=True)
class Redaction:
    location: str
    start: int
    end: int


@dataclass
class CodeCheck:
    issues: list[VerificationIssue]
    numbers_checked: int
    numbers_matched: int
    redactions: list[Redaction] = field(default_factory=list)
    """Spans of text that failed a check: hidden in the report shown to the engineer."""

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def _issue(
    code: IssueCode, location: str, message: str, severity: Literal["error", "warning"] = "error"
) -> VerificationIssue:
    return VerificationIssue(code=code, severity=severity, location=location, message=message)


def trigger_facts(trigger: InvestigationTrigger | None) -> tuple[list[str], list[int]]:
    """Identifiers the trigger itself names (the engineer gave them)."""
    if trigger is None:
        return [], []
    strings = [trigger.ref]
    units: list[int] = []
    if trigger.kind == "unit" and trigger.ref.isdigit():
        units.append(int(trigger.ref))
    alarm = _ALARM_UNIT.match(trigger.ref)
    if trigger.kind == "alarm" and alarm:
        units.append(int(alarm.group("unit")))
    if trigger.kind == "run_alarm":
        strings.extend(trigger.ref.split(":", 1))
    return strings, units


@dataclass(frozen=True, slots=True)
class EvidenceText:
    """A string leaf a number cites (a label such as ``"5% false-alarm rate"``)."""

    text: str


@dataclass(frozen=True, slots=True)
class EvidenceList:
    """A list a count cites ("15 sensors" with the path of the group's sensor list)."""

    length: int


def _resolve_cited(item: Evidence, path: str) -> object:
    """The value at a number's path: in the evidence data, or, for a path starting with
    ``/arguments/``, in the tool arguments the evidence echoes (the model is shown both)."""
    try:
        return resolve(item.data, path)
    except PointerError:
        for prefix, source in (("/arguments/", item.arguments), ("/data/", item.data)):
            if path.startswith(prefix):
                return resolve(source, path[len(prefix) - 1 :])
        raise


class _NumberCheck:
    """Checks one text number against the references listed in ``numbers[]``."""

    def __init__(self, report: Report, evidence: Mapping[str, Evidence]) -> None:
        self.evidence = evidence
        self.refs: list[tuple[NumberRef, NumberMention | None]] = [
            (ref, parse_number(ref.as_written)) for ref in report.numbers
        ]

    @staticmethod
    def _is_percent(ref: NumberRef, written: NumberMention | None) -> bool:
        return ref.unit == "%" or (written is not None and written.percent)

    def candidates(self, mention: NumberMention) -> list[NumberRef]:
        out = []
        for ref, written in self.refs:
            if written is None:
                continue
            same_value = abs(written.value - mention.value) <= 1e-12 * max(1.0, abs(mention.value))
            if same_value and self._is_percent(ref, written) == mention.percent:
                out.append(ref)
        return out

    def evidence_value(self, ref: NumberRef) -> float | EvidenceText | EvidenceList | str:
        """The number at the reference, the evidence text there, or why there is neither."""
        item = self.evidence.get(ref.evidence_id)
        if item is None:
            return f"evidence {ref.evidence_id} does not exist"
        try:
            value = _resolve_cited(item, ref.path)
        except PointerError as exc:
            return f"{ref.path} is not in {ref.evidence_id} ({exc})"
        if isinstance(value, str):
            return EvidenceText(value)
        if isinstance(value, list):
            return EvidenceList(len(value))
        if isinstance(value, bool) or not isinstance(value, int | float):
            return f"{ref.path} in {ref.evidence_id} is not a number or text"
        return float(value)


def check_hypotheses(
    report: Report, evidence: Mapping[str, Evidence], known_sources: Collection[str] | None
) -> list[VerificationIssue]:
    """Sources, evidence IDs and the evidence each assessment needs. ``known_sources`` is every
    source ID of the knowledge base; None when it could not be read, so no source can be
    confirmed."""
    issues: list[VerificationIssue] = []
    for i, hypothesis in enumerate(report.hypotheses):
        location = f"hypotheses[{i}]"
        for source_id in hypothesis.source_ids:
            if known_sources is None:
                message = f"source {source_id!r} not checked: the knowledge base is not available"
                issues.append(_issue("unknown_source", f"{location}.source_ids", message))
            elif source_id not in known_sources:
                message = f"source {source_id!r} is not in the knowledge base"
                issues.append(_issue("unknown_source", f"{location}.source_ids", message))
        for side, items in (
            ("evidence_for", hypothesis.evidence_for),
            ("evidence_against", hypothesis.evidence_against),
        ):
            for j, item in enumerate(items):
                if item.evidence_id not in evidence:
                    issues.append(
                        _issue(
                            "unknown_evidence",
                            f"{location}.{side}[{j}].evidence_id",
                            f"{item.evidence_id} was not returned by a tool in this investigation",
                        )
                    )
        if hypothesis.assessment == "supported" and not hypothesis.evidence_for:
            issues.append(
                _issue(
                    "assessment_without_evidence",
                    f"{location}.assessment",
                    "assessed supported without an observation in evidence_for",
                )
            )
        if hypothesis.assessment == "not_supported" and not hypothesis.evidence_against:
            issues.append(
                _issue(
                    "assessment_without_evidence",
                    f"{location}.assessment",
                    "assessed not_supported without an observation in evidence_against",
                )
            )
    return issues


def check_numbers_and_citations(
    report: Report,
    evidence: Mapping[str, Evidence],
    *,
    trigger: InvestigationTrigger | None = None,
    known_sources: Collection[str] | None = None,
) -> CodeCheck:
    """Rules 2 to 4: numbers, identifiers, citations and wording, by code only."""
    issues: list[VerificationIssue] = check_hypotheses(report, evidence, known_sources)
    strings, units = trigger_facts(trigger)
    facts = EvidenceFacts.build(evidence.values(), strings=strings, units=units)
    numbers = _NumberCheck(report, evidence)
    checked = matched = 0

    for k, ref in enumerate(report.numbers):
        location = f"numbers[{k}]"
        written = parse_number(ref.as_written)
        if ref.evidence_id not in evidence:
            issues.append(
                _issue(
                    "unknown_evidence", location, f"cites {ref.evidence_id}, which does not exist"
                )
            )
        if written is None:
            issues.append(
                _issue(
                    "number_mismatch", location, f"as_written {ref.as_written!r} is not one number"
                )
            )
        elif not written_value_matches(
            written, ref.value, percent=ref.unit == "%" or written.percent
        ):
            issues.append(
                _issue(
                    "number_mismatch",
                    location,
                    f"value {ref.value:g} differs from as_written {ref.as_written!r}",
                )
            )

    for i, finding in enumerate(report.findings):
        for evidence_id in finding.evidence_ids:
            if evidence_id not in evidence:
                issues.append(
                    _issue(
                        "unknown_evidence",
                        f"findings[{i}].evidence_ids",
                        f"{evidence_id} does not exist",
                    )
                )
    for i, action in enumerate(report.actions):
        for evidence_id in action.evidence_ids:
            if evidence_id not in evidence:
                issues.append(
                    _issue(
                        "unknown_evidence",
                        f"actions[{i}].evidence_ids",
                        f"{evidence_id} does not exist",
                    )
                )

    redactions: list[Redaction] = []
    for text_field in text_fields(report):
        location = text_field.location
        found = scan(text_field.text, known_identifiers=facts.known_identifiers)
        for spelled in found.spelled:
            redactions.append(Redaction(location, spelled.start, spelled.end))
            issues.append(
                _issue(
                    "number_not_listed",
                    location,
                    f"'{spelled.text}' is a number in words; write it in digits and list it in numbers[]",
                )
            )
        for identifier in found.identifiers:
            unsupported = facts.unsupported_values(identifier)
            if unsupported:
                redactions.append(Redaction(location, identifier.start, identifier.end))
            for value in unsupported:
                code: IssueCode = (
                    "unknown_evidence" if identifier.kind == "evidence" else "unsupported_claim"
                )
                issues.append(
                    _issue(
                        code,
                        location,
                        f"mentions {identifier.kind} {value}, which no evidence contains",
                    )
                )
        for mention in found.numbers:
            checked += 1
            outcome = _check_mention(mention, text_field, numbers, facts)
            if outcome is None:
                matched += 1
            else:
                issues.append(outcome)
                if outcome.severity == "error" and outcome.code != "missing_citation":
                    redactions.append(Redaction(location, mention.start, mention.end))
                if outcome.code == "missing_citation" or outcome.severity == "warning":
                    matched += 1
        for phrase in causal_phrases(text_field.text):
            issues.append(
                _issue(
                    "causal_wording",
                    location,
                    f"causal wording {phrase.text!r}: the evidence shows association, not "
                    f"cause. {ASSOCIATION_HINT}",
                )
            )
    return CodeCheck(issues, checked, matched, redactions)


def _check_mention(
    mention: NumberMention, text_field: TextField, numbers: _NumberCheck, facts: EvidenceFacts
) -> VerificationIssue | None:
    """None when the number is listed and matches its evidence; else the issue. A percentage
    that names a level ("the 99% limit") is a name: the evidence must name that level."""
    outcome = _check_quantity(mention, text_field, numbers)
    if outcome is None or not names_a_level(text_field.text, mention):
        return outcome
    if facts.names_level(mention):
        return None
    return _issue(
        "number_mismatch",
        text_field.location,
        f"{mention.text} names a level that no evidence names",
    )


def _is_count(mention: NumberMention) -> bool:
    return not mention.percent and mention.decimals == 0 and mention.value >= 0


def _check_quantity(
    mention: NumberMention, text_field: TextField, numbers: _NumberCheck
) -> VerificationIssue | None:
    candidates = numbers.candidates(mention)
    if not candidates:
        return _issue(
            "number_not_listed",
            text_field.location,
            f"{mention.text} is not listed in numbers[] with an evidence ID and path",
        )
    supported: list[NumberRef] = []
    sign_only: list[NumberRef] = []
    reasons: list[str] = []
    for ref in candidates:
        value = numbers.evidence_value(ref)
        if isinstance(value, str):
            reasons.append(value)
            continue
        if isinstance(value, EvidenceList):
            if _is_count(mention) and matches(mention, float(value.length), percent=False):
                supported.append(ref)
            else:
                reasons.append(f"{ref.path} in {ref.evidence_id} is a list of {value.length} items")
            continue
        if isinstance(value, EvidenceText):
            if appears_in_text(mention, value.text):
                supported.append(ref)
            else:
                reasons.append(f"{ref.evidence_id} has the text {value.text[:80]!r} at {ref.path}")
            continue
        percent = ref.unit == "%" or mention.percent
        if matches(mention, value, percent=percent):
            supported.append(ref)
        elif magnitude_matches(mention, value, percent=percent):
            sign_only.append(ref)
        else:
            shown = f"{value * 100:g}%" if percent else f"{value:g}"
            reasons.append(f"{ref.evidence_id} holds {shown} at {ref.path}")
    if supported:
        if text_field.cites is not None and not any(
            ref.evidence_id in text_field.cites for ref in supported
        ):
            sources = ", ".join(sorted({ref.evidence_id for ref in supported}))
            return _issue(
                "missing_citation",
                text_field.location,
                f"{mention.text} comes from {sources}, which {text_field.location} does not cite",
            )
        return None
    if sign_only:
        return _issue(
            "number_mismatch",
            text_field.location,
            f"{mention.text} matches the evidence only without its sign; check the wording "
            "says the direction",
            severity="warning",
        )
    return _issue(
        "number_mismatch",
        text_field.location,
        f"{mention.text} does not match its evidence: " + "; ".join(reasons),
    )


def _redact(text: str, spans: Sequence[Redaction], limit: int | None) -> str:
    out = text
    for span in sorted(spans, key=lambda r: r.start, reverse=True):
        out = out[: span.start] + REPORT_REDACTION + out[span.end :]
    return out if limit is None else out[:limit]


def shown_report(report: Report, redactions: Sequence[Redaction]) -> Report:
    """The report as the engineer sees it: every number or identifier that failed a check is
    replaced by :data:`REPORT_REDACTION`, so no unverified value reaches a reader."""
    if not redactions:
        return report
    by_location: dict[str, list[Redaction]] = {}
    for span in redactions:
        by_location.setdefault(span.location, []).append(span)

    def fix(location: str, text: str, limit: int | None) -> str:
        spans = by_location.get(location)
        return _redact(text, spans, limit) if spans else text

    findings = [
        f.model_copy(update={"claim": fix(f"findings[{i}].claim", f.claim, _TEXT_LIMITS["claim"])})
        for i, f in enumerate(report.findings)
    ]
    actions = [
        a.model_copy(
            update={
                "action": fix(f"actions[{i}].action", a.action, _TEXT_LIMITS["action"]),
                "rationale": fix(f"actions[{i}].rationale", a.rationale, _TEXT_LIMITS["rationale"]),
            }
        )
        for i, a in enumerate(report.actions)
    ]
    limitations = [fix(f"limitations[{i}]", t, None) for i, t in enumerate(report.limitations)]

    def observations(i: int, side: str, items: Sequence[HypothesisEvidence]) -> list[Any]:
        return [
            item.model_copy(
                update={
                    "observation": fix(
                        f"hypotheses[{i}].{side}[{j}].observation",
                        item.observation,
                        _TEXT_LIMITS["observation"],
                    )
                }
            )
            for j, item in enumerate(items)
        ]

    hypotheses = [
        h.model_copy(
            update={
                "hypothesis": fix(
                    f"hypotheses[{i}].hypothesis", h.hypothesis, _TEXT_LIMITS["hypothesis"]
                ),
                "evidence_for": observations(i, "evidence_for", h.evidence_for),
                "evidence_against": observations(i, "evidence_against", h.evidence_against),
            }
        )
        for i, h in enumerate(report.hypotheses)
    ]
    return report.model_copy(
        update={
            "summary": fix("summary", report.summary, _TEXT_LIMITS["summary"]),
            "findings": findings,
            "actions": actions,
            "limitations": limitations,
            "hypotheses": hypotheses,
        }
    )


def verifier_request(report: Report, evidence: Mapping[str, Evidence]) -> ChatRequest:
    findings = []
    for index, finding in enumerate(report.findings):
        cited = [model_view(evidence[e]) for e in finding.evidence_ids if e in evidence]
        findings.append({"finding_index": index, "claim": finding.claim, "evidence": cited})
    return ChatRequest(
        messages=(
            ChatMessage.system(VERIFIER_SYSTEM),
            ChatMessage.user(data_message({"findings": findings})),
        ),
        max_tokens=VERIFIER_MAX_TOKENS,
    )


@dataclass(frozen=True, slots=True)
class ModelCheck:
    claims: list[ClaimVerdict]
    issues: list[VerificationIssue]
    model: str | None


@dataclass(frozen=True, slots=True)
class VerifyResult:
    verification: Verification
    shown: Report
    """The report with every value that failed a check hidden (:func:`shown_report`)."""


class ReportVerifier:
    def __init__(
        self,
        gateway: LlmGateway,
        *,
        family_of: Callable[[str], str | None] | None = None,
    ) -> None:
        self.gateway = gateway
        self._family_of = family_of or self._catalog_family

    def _catalog_family(self, model: str) -> str | None:
        profile = self.gateway.registry.catalog.get(model)
        return profile.family if profile else None

    async def model_check(
        self,
        report: Report,
        evidence: Mapping[str, Evidence],
        *,
        writer_model: str | None,
        options: CallOptions,
    ) -> ModelCheck:
        if not report.findings:
            return ModelCheck([], [], None)
        family = self._family_of(writer_model) if writer_model else None
        call_options = CallOptions(
            correlation_id=options.correlation_id,
            use_cache=options.use_cache,
            exclude_families=frozenset({family}) if family else frozenset(),
            on_record=options.on_record,
        )
        try:
            out = await self.gateway.complete_structured(
                Role.VERIFIER,
                verifier_request(report, evidence),
                ClaimChecks,
                schema_name=CLAIMS_SCHEMA_NAME,
                options=call_options,
            )
        except LlmError as exc:
            message = (
                f"the verifier model was not available ({type(exc).__name__}); claims not checked"
            )
            return ModelCheck(
                [ClaimVerdict(finding_index=i, verdict="not_checked", note=None) for i in range(len(report.findings))],
                [_issue("verifier_unavailable", "findings", message, severity="warning")],
                None,
            )  # fmt: skip
        facts = EvidenceFacts.build(evidence.values())
        verdicts: dict[int, ClaimCheck] = {}
        for claim in out.value.claims:
            if 0 <= claim.finding_index < len(report.findings):
                verdicts.setdefault(claim.finding_index, claim)
        claims: list[ClaimVerdict] = []
        issues: list[VerificationIssue] = []
        for index in range(len(report.findings)):
            location = f"findings[{index}].claim"
            check = verdicts.get(index)
            if check is None:
                claims.append(ClaimVerdict(finding_index=index, verdict="not_checked", note=None))
                issues.append(
                    _issue("verifier_unavailable", location, "the verifier model gave no verdict for this finding", "warning")
                )  # fmt: skip
                continue
            note, _ = redact_unverified(check.note, facts)
            claims.append(
                ClaimVerdict(finding_index=index, verdict=check.verdict, note=note or None)
            )
            if check.verdict == "unsupported":
                issues.append(
                    _issue("unsupported_claim", location, "the verifier model judged this claim unsupported by its cited evidence")
                )  # fmt: skip
            elif check.verdict == "partially_supported":
                issues.append(
                    _issue("unsupported_claim", location, "the verifier model judged this claim only partly supported by its cited evidence", "warning")
                )  # fmt: skip
        return ModelCheck(claims, issues, out.result.model)

    async def verify(
        self,
        report: Report,
        evidence: Sequence[Evidence],
        *,
        trigger: InvestigationTrigger | None,
        revision_round: int,
        last_round: bool,
        writer_model: str | None,
        options: CallOptions,
        known_sources: Collection[str] | None = None,
    ) -> VerifyResult:
        index = {item.evidence_id: item for item in evidence}
        code = check_numbers_and_citations(
            report, index, trigger=trigger, known_sources=known_sources
        )
        if code.has_errors and not last_round:
            model = ModelCheck(
                [ClaimVerdict(finding_index=i, verdict="not_checked", note=None) for i in range(len(report.findings))],
                [],
                None,
            )  # fmt: skip
        else:
            model = await self.model_check(
                report, index, writer_model=writer_model, options=options
            )
        issues = code.issues + model.issues
        verification = Verification(
            passed=not any(issue.severity == "error" for issue in issues),
            rounds=revision_round,
            numbers_checked=code.numbers_checked,
            numbers_matched=code.numbers_matched,
            issues=issues,
            claims=model.claims,
            verifier_model=model.model,
        )
        return VerifyResult(verification, shown_report(report, code.redactions))

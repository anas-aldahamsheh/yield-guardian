"""Routing of an engineer's chat question (PLAN 7.5): rules first, a small model only when the
rules cannot decide.

The rules read the question with code: identifiers (units, alarms, sensors, wafers, lots, defect
patterns, sensor statuses), what kind of answer is asked for, requests for actions and attempts
to change the assistant's rules. Most questions in the console name a unit, a sensor or a wafer,
so most are routed without any model call. Count questions ("how many sensors are dead?") are
answered entirely by code. Only a question the rules cannot place goes to the router model,
whose answer must be one of the closed set of intents; anything else is rejected by validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict

from yield_guardian.agent.numbers import find_identifiers
from yield_guardian.agent.prompts import ROUTER_SYSTEM, data_message
from yield_guardian.contracts.chat import ChatContext, RouteKind
from yield_guardian.contracts.investigation import ToolName
from yield_guardian.contracts.secom import SensorStatus
from yield_guardian.contracts.wafer import WaferLabel
from yield_guardian.llm.errors import LlmError
from yield_guardian.llm.gateway import CallOptions, LlmGateway
from yield_guardian.llm.messages import ChatMessage, ChatRequest
from yield_guardian.llm.registry import Role

Intent = Literal[
    "unit_risk",
    "unit_explanation",
    "unit_fdc",
    "top_sensor_groups",
    "sensor_health",
    "wafer_pattern",
    "similar_wafers",
    "lot_status",
    "pattern_causes",
    "knowledge_search",
    "general",
    "action_request",
    "out_of_scope",
]
INTENTS: tuple[Intent, ...] = get_args(Intent)
REFUSED_INTENTS: frozenset[Intent] = frozenset({"action_request", "out_of_scope"})
CountKind = Literal["sensors_by_status", "significant_groups", "wafers_in_lot"]
ROUTER_MAX_TOKENS = 128
ROUTER_SCHEMA_NAME = "chat_intent"
MAX_ENTITIES = 3
"""Units, wafers or patterns read per question: enough to compare, small enough to answer."""

_I = re.IGNORECASE
_INJECTION = re.compile(
    r"\bignore\s+(?:all\s+|any\s+|the\s+|your\s+|these\s+)*(?:previous\s+|prior\s+|above\s+|"
    r"earlier\s+|system\s+)?(?:instructions|rules|prompts?|guidelines)\b"
    r"|\bdisregard\s+(?:all|any|the|your|these|previous|prior)\b"
    r"|\bsystem\s+prompt\b|\byou\s+are\s+now\b|\bdeveloper\s+mode\b|\bjailbreak"
    r"|\breveal\s+(?:your|the)\s+(?:prompt|instructions|rules)\b"
    r"|\bact\s+as\s+(?:an?\s+)?(?:admin|administrator|root|system)\b",
    _I,
)
_ACTION_VERBS = (
    r"approve|reject|open|create|close|delete|remove|send|email|change|set|update|reset|"
    r"acknowledge|ack|assign|escalate|disable|enable|stop|restart|shut\s+down|halt|scrap|"
    r"release|hold|edit|modify|cancel|dispatch|schedule|order|file|submit|mark"
)
_ACTION = re.compile(
    rf"^\s*(?:please\s+|now\s+|go\s+ahead\s+and\s+)?(?:{_ACTION_VERBS})\b"
    rf"|\b(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:{_ACTION_VERBS})\b"
    rf"|\b(?:i\s+want\s+you\s+to|you\s+should|you\s+must)\s+(?:{_ACTION_VERBS})\b"
    r"|\b(?:open|create|close|raise|file)\s+(?:a\s+|the\s+|an\s+)?work\s+orders?\b",
    _I,
)
_HOW_MANY = re.compile(r"\bhow\s+many\b|\bnumber\s+of\b|\bcount\s+(?:of|the)\b", _I)
_DEICTIC = re.compile(r"\b(?:this|that|it|its|current|selected|here)\b", _I)
_UNIT_WORDS = re.compile(r"\b(?:risk|risky|fail\w*|alarm\w*|unit)\b", _I)
_FDC_WORDS = re.compile(
    r"\b(?:t2|t²|spe|hotelling|control[\s-]+chart|fdc|q[\s-]+statistic|residuals?|"
    r"ewma|cusum)\b",
    _I,
)
_EXPLAIN_WORDS = re.compile(
    r"\b(?:why|explain\w*|explanation|shap|contribut\w*|reasons?|driv\w*|factors?|features?|"
    r"which\s+sensors)\b",
    _I,
)
_SIMILAR_WORDS = re.compile(
    r"\b(?:similar|like|resembl\w*|nearest|neighbou?rs?|closest|look[\s-]*alikes?)\b", _I
)
_WAFER_WORDS = re.compile(r"\b(?:wafers?|pattern|map|defect|class\w*|predict\w*)\b", _I)
_LOT_WORDS = re.compile(r"\blots?\b", _I)
_SENSOR_WORDS = re.compile(
    r"\b(?:sensors?|health\w*|status|dead|watch|maintenance|stuck|frozen|flat\w*|missing|"
    r"broken|calibrat\w*)\b",
    _I,
)
_GROUP_WORDS = re.compile(r"\b(?:sensor\s+groups?|groups?\s+of\s+sensors|which\s+sensors)\b", _I)
_FAILURE_WORDS = re.compile(r"\b(?:fail\w*|yield|associated|important|matter\w*|signific\w*)\b", _I)
_CAUSE_WORDS = re.compile(
    r"\b(?:caus\w*|why|mechanism\w*|origins?|reasons?|sources?|explain\w*|lead\s+to|"
    r"leads\s+to|comes?\s+from|behind|responsible|underlying|attribut\w*|"
    r"produc(?:e|es|ed|ing)|creat(?:e|es|ed|ing)|generat(?:e|es|ed|ing)|form(?:s|ed|ation)|"
    r"trigger(?:s|ed|ing)?|result\w*\s+(?:in|from)|"
    r"root[\s-]+causes?|gives?\s+rise|contribut\w*\s+to)\b",
    _I,
)
_DOMAIN_WORDS = re.compile(
    r"\b(?:units?|wafers?|lots?|dies?|sensors?|alarms?|risk\w*|yield\w*|fail\w*|fab|plant|"
    r"lines?|process\w*|tools?|chambers?|equipment|semiconductor\w*|defects?|patterns?|maps?|"
    r"secom|wm-?811k|t2|t²|spe|fdc|ewma|cusum|control|charts?|statistic\w*|shap|models?|"
    r"predict\w*|investigat\w*|work\s+orders?|reports?|evidence|data\w*|measure\w*|"
    r"health\w*|calibrat\w*|maintenance|anomal\w*|excursion\w*|literature|papers?|"
    r"stud(?:y|ies)|research|etch\w*|lithograph\w*|deposit\w*|polish\w*|cmp|"
    r"temperature|pressure|flow|sample\w*|batch\w*)\b",
    _I,
)
"""Words of the product's scope: the plant's data, wafer maps and the defect literature."""
_OFF_TOPIC = re.compile(
    # creative writing and entertainment
    r"\b(?:poems?|poetry|haikus?|limericks?|sonnets?|lyrics|songs?|stor(?:y|ies)|jokes?|"
    r"riddles?|puns?|essays?|fiction|novels?|movies?|films?|tv\s+shows?|games?|"
    # general knowledge, news and everyday help
    r"capital\s+of|presidents?|prime\s+ministers?|kings?|queens?|celebrit\w*|weather|"
    r"forecast|recipes?|cook\w*|restaurants?|travel\w*|vacation|hotels?|flights?|sports?|"
    r"football|soccer|basketball|baseball|cricket|olympic\w*|world\s+cup|elections?|"
    r"politic\w*|horoscopes?|zodiac|stock\s+prices?|crypto\w*|bitcoin|translate|"
    r"translation|dating|relationship\w*|homework|history\s+of\s+(?:rome|france|the\s+world))\b",
    _I,
)
"""Requests a general assistant would answer; with no word of the scope they are refused."""
_LITERATURE_WORDS = re.compile(
    r"\b(?:papers?|literature|stud(?:y|ies)|publications?|references?|articles?|sources?|"
    r"research)\b",
    _I,
)
_PATTERNS: tuple[tuple[WaferLabel, re.Pattern[str]], ...] = (
    ("Edge-Ring", re.compile(r"\bedge[\s_-]*rings?\b", _I)),
    ("Edge-Loc", re.compile(r"\bedge[\s_-]*loc(?:al|alized)?\b", _I)),
    ("Near-full", re.compile(r"\bnear[\s_-]*full\b", _I)),
    ("Center", re.compile(r"\bcent(?:er|re)\b", _I)),
    ("Donut", re.compile(r"\bdonuts?\b|\bdoughnuts?\b", _I)),
    ("Scratch", re.compile(r"\bscratch(?:es)?\b", _I)),
    ("Random", re.compile(r"\brandom\b", _I)),
    ("Loc", re.compile(r"\bloc(?:al|alized)?\b(?![\s_-]*(?:ring|edge))", _I)),
)
_STATUSES: tuple[tuple[SensorStatus, re.Pattern[str]], ...] = (
    ("dead", re.compile(r"\bdead\b", _I)),
    ("maintenance", re.compile(r"\bmaintenance\b", _I)),
    ("watch", re.compile(r"\bwatch(?:list|ed)?\b", _I)),
    ("ok", re.compile(r"\b(?:ok|okay|healthy)\b", _I)),
)
_ALARM_UNIT = re.compile(r"^AL-(?P<unit>[0-9]+)-")


@dataclass(frozen=True, slots=True)
class Entities:
    units: tuple[int, ...] = ()
    alarms: tuple[str, ...] = ()
    sensors: tuple[str, ...] = ()
    wafers: tuple[str, ...] = ()
    lots: tuple[str, ...] = ()
    patterns: tuple[WaferLabel, ...] = ()
    statuses: tuple[SensorStatus, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {name: list(getattr(self, name)) for name in _ENTITY_FIELDS if getattr(self, name)}


_ENTITY_FIELDS = ("units", "alarms", "sensors", "wafers", "lots", "patterns", "statuses")


@dataclass(frozen=True, slots=True)
class Route:
    intent: Intent
    kind: RouteKind
    entities: Entities
    model_id: str | None = None
    count: CountKind | None = None
    reason: str = ""
    """Why the question is refused (refused intents only); written by code."""
    calls: tuple[tuple[ToolName, dict[str, Any]], ...] = field(default=())
    """Tool calls code makes for this intent; empty when the chat model must choose."""

    @property
    def refused(self) -> bool:
        return self.intent in REFUSED_INTENTS


_CAPABILITIES = re.compile(
    r"^\s*(?:(?:hi|hello|hey)\b[\s,!.]*)?(?:"
    r"what\s+(?:can|could)\s+you\s+(?:do|help(?:\s+me)?(?:\s+with)?|answer|tell\s+me)"
    r"|how\s+(?:can|could|do)\s+you\s+help(?:\s+me)?"
    r"|what\s+(?:do\s+you\s+do|are\s+you(?:\s+for)?|is\s+this(?:\s+chat)?(?:\s+for)?)"
    r"|who\s+are\s+you|what\s+are\s+your\s+(?:capabilities|skills|features)"
    r"|what\s+(?:should|can)\s+i\s+ask(?:\s+you)?|help"
    r"|(?:شو|ايش|إيش|ماذا|ما\s+الذي)\s+(?:بتقدر|تقدر|تستطيع|بتعرف|تعرف)\s*(?:تعمل|تساعدني|تقدم|تقدملي)?(?:\s+فيه|\s+به)?"
    r"|كيف\s+(?:بتقدر\s+|تقدر\s+|يمكنك\s+)?(?:تساعدني|تساعد)"
    r")\s*(?:here|today|for\s+me)?\s*[?!.\uff1f\u061f]*\s*$",
    _I,
)
CAPABILITIES = (
    "I answer questions about this plant's data, from the same records the screens use, and "
    "cite each record I read. You can ask me:\n"
    "- About a unit: its failure risk (experimental), which sensors moved it, and where it sits "
    'on the T² and SPE control charts. For example: "Why is unit 1303 flagged?"\n'
    "- About an alarm: what triggered it and which sensor groups carry it.\n"
    "- About sensors: which are dead, stuck, jumping or drifting, and how many have a status.\n"
    "- About a wafer: its defect pattern, its unknown-pattern score and the most similar past "
    "wafers.\n"
    "- About a lot: its pattern counts and whether they are unusual.\n"
    "- About the literature: known causes of wafer-map patterns such as Edge-Ring or Scratch.\n"
    "I only read and explain. An engineer approves reports and opens work orders in the "
    "interface, and the numbers I give come from the data, never from me."
)


def is_capability_question(question: str) -> bool:
    """ "What can you do?" and its variants: answered by code with a fixed description."""
    return bool(_CAPABILITIES.match(question))


ACTION_REFUSAL = (
    "I can only read and explain the plant data; I cannot take actions. An engineer approves "
    "reports, opens work orders and changes settings in the interface."
)
INJECTION_REFUSAL = (
    "I follow fixed rules and cannot change them; ask a question about the plant data instead."
)
SCOPE_REFUSAL = (
    "I can only answer questions about this plant's data: units, sensors, alarms, wafers, lots "
    "and the literature on wafer defect patterns."
)


def _unique[T](values: list[T]) -> tuple[T, ...]:
    return tuple(dict.fromkeys(values))


def extract_entities(question: str) -> Entities:
    units: list[int] = []
    alarms: list[str] = []
    sensors: list[str] = []
    wafers: list[str] = []
    lots: list[str] = []
    for identifier in find_identifiers(question):
        if identifier.kind == "unit":
            units.extend(int(v) for v in identifier.values)
        elif identifier.kind == "alarm":
            alarms.append(identifier.text)
            match = _ALARM_UNIT.match(identifier.text)
            if match:
                units.append(int(match.group("unit")))
        elif identifier.kind == "sensor":
            sensors.append(identifier.text)
        elif identifier.kind == "wafer":
            wafers.append(identifier.text)
        elif identifier.kind == "lot":
            lots.append(identifier.text)
    patterns = [label for label, pattern in _PATTERNS if pattern.search(question)]
    if "Edge-Loc" in patterns or "Edge-Ring" in patterns:
        patterns = [p for p in patterns if p != "Loc"]
    statuses = [status for status, pattern in _STATUSES if pattern.search(question)]
    return Entities(
        units=_unique(units),
        alarms=_unique(alarms),
        sensors=_unique(sensors),
        wafers=_unique(wafers),
        lots=_unique(lots),
        patterns=_unique(patterns),
        statuses=_unique(statuses),
    )


def with_context(question: str, entities: Entities, context: ChatContext | None) -> Entities:
    """Fill a missing unit, sensor, wafer or lot from what the engineer is looking at, when the
    question points at it ("this unit", "why is it risky") or asks about that kind of thing."""
    if context is None:
        return entities
    deictic = bool(_DEICTIC.search(question))
    update: dict[str, Any] = {}
    if not entities.units and context.unit_id is not None and (deictic or _UNIT_WORDS.search(question) or _FDC_WORDS.search(question) or _EXPLAIN_WORDS.search(question)):  # fmt: skip
        update["units"] = (context.unit_id,)
    if not entities.sensors and context.sensor is not None and (deictic or _SENSOR_WORDS.search(question)):  # fmt: skip
        update["sensors"] = (context.sensor,)
    if not entities.wafers and context.wafer_id is not None and (deictic or _WAFER_WORDS.search(question) or _SIMILAR_WORDS.search(question)):  # fmt: skip
        update["wafers"] = (context.wafer_id,)
    if not entities.lots and context.lot is not None and _LOT_WORDS.search(question):
        update["lots"] = (context.lot,)
    if not update:
        return entities
    return replace(entities, **update)


def _rule_intent(question: str, e: Entities) -> tuple[Intent, CountKind | None] | None:
    if _HOW_MANY.search(question):
        if e.statuses and re.search(r"\bsensors?\b", question, _I) and not e.sensors:
            return "sensor_health", "sensors_by_status"
        if re.search(r"\bsignificant\b", question, _I) and re.search(r"\bgroups?\b", question, _I):
            return "top_sensor_groups", "significant_groups"
        if e.lots and re.search(r"\bwafers?\b", question, _I) and not e.wafers:
            return "lot_status", "wafers_in_lot"
    if e.patterns and _CAUSE_WORDS.search(question) and not e.wafers:
        return "pattern_causes", None
    if e.wafers:
        return ("similar_wafers" if _SIMILAR_WORDS.search(question) else "wafer_pattern"), None
    if e.lots:
        return "lot_status", None
    if e.sensors and (_SENSOR_WORDS.search(question) or not e.units):
        return "sensor_health", None
    if e.units:
        if _FDC_WORDS.search(question):
            return "unit_fdc", None
        if _EXPLAIN_WORDS.search(question):
            return "unit_explanation", None
        return "unit_risk", None
    if _GROUP_WORDS.search(question) and _FAILURE_WORDS.search(question):
        return "top_sensor_groups", None
    if e.statuses and re.search(r"\bsensors?\b", question, _I):
        return "sensor_health", None
    if _LITERATURE_WORDS.search(question) or e.patterns:
        return "knowledge_search", None
    return None


def planned_calls(
    intent: Intent, e: Entities, question: str
) -> tuple[tuple[ToolName, dict[str, Any]], ...]:
    """The tool calls code makes for an intent, or none when the chat model must choose."""
    units = e.units[:MAX_ENTITIES]
    calls: list[tuple[ToolName, dict[str, Any]]] = []
    if intent == "unit_risk":
        calls = [("get_risk", {"unit_id": u}) for u in units]
    elif intent == "unit_explanation":
        for u in units:
            calls += [("get_risk", {"unit_id": u}), ("get_shap", {"unit_id": u, "top_k": 10})]
    elif intent == "unit_fdc":
        for u in units:
            calls += [
                ("get_contributions", {"unit_id": u, "statistic": "t2"}),
                ("get_contributions", {"unit_id": u, "statistic": "spe"}),
            ]
    elif intent == "sensor_health":
        if e.sensors:
            calls = [("get_sensor_health", {"sensors": list(e.sensors[:20])})]
        elif e.statuses:
            calls = [("get_sensor_health", {"statuses": list(e.statuses)})]
    elif intent == "top_sensor_groups":
        calls = [("get_feature_groups", {"significant_only": True, "limit": 20})]
    elif intent == "wafer_pattern":
        calls = [("get_wafer_prediction", {"wafer_id": w}) for w in e.wafers[:MAX_ENTITIES]]
    elif intent == "similar_wafers":
        calls = [("get_similar_wafers", {"wafer_id": w, "k": 5}) for w in e.wafers[:1]]
    elif intent == "lot_status":
        calls = [("get_lot_stats", {"lot": lot}) for lot in e.lots[:MAX_ENTITIES]]
    elif intent == "pattern_causes":
        calls = [
            ("search_knowledge", {"query": f"{p} wafer map pattern cause", "limit": 5})
            for p in e.patterns[:2]
        ]
    elif intent == "knowledge_search":
        query = " ".join(question.split())[:200]
        if len(query) >= 2:
            calls = [("search_knowledge", {"query": query, "limit": 5})]
    return tuple(calls)


def is_off_topic(question: str, entities: Entities) -> bool:
    """A request of a kind outside the product (a poem, trivia, the weather...) that names
    nothing in its scope: no unit, alarm, sensor, wafer or lot, and no word of the plant's data.
    Pattern names are not counted: "random", "center" or "local" are everyday words too."""
    named = replace(entities, patterns=(), statuses=())
    if named.as_json() or _DOMAIN_WORDS.search(question):
        return False
    return bool(_OFF_TOPIC.search(question))


def route_by_rules(question: str, context: ChatContext | None = None) -> Route | None:
    """The route the rules decide, or None when only a model can classify the question."""
    entities = extract_entities(question)
    if _INJECTION.search(question):
        return Route("out_of_scope", "deterministic", entities, reason=INJECTION_REFUSAL)
    if _ACTION.search(question):
        return Route("action_request", "deterministic", entities, reason=ACTION_REFUSAL)
    if is_off_topic(question, entities):
        return Route("out_of_scope", "deterministic", entities, reason=SCOPE_REFUSAL)
    entities = with_context(question, entities, context)
    decided = _rule_intent(question, entities)
    if decided is None:
        return None
    intent, count = decided
    calls = planned_calls(intent, entities, question)
    return Route(intent, "deterministic", entities, count=count, calls=calls)


class RouterAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent


def router_request(question: str) -> ChatRequest:
    return ChatRequest(
        messages=(
            ChatMessage.system(ROUTER_SYSTEM),
            ChatMessage.user(data_message({"question": question})),
        ),
        max_tokens=ROUTER_MAX_TOKENS,
    )


def _reason(intent: Intent) -> str:
    return ACTION_REFUSAL if intent == "action_request" else SCOPE_REFUSAL


class ChatRouter:
    def __init__(self, gateway: LlmGateway) -> None:
        self.gateway = gateway

    async def route(
        self, question: str, context: ChatContext | None, *, options: CallOptions
    ) -> Route:
        decided = route_by_rules(question, context)
        if decided is not None:
            return decided
        entities = with_context(question, extract_entities(question), context)
        try:
            out = await self.gateway.complete_structured(
                Role.ROUTER,
                router_request(question),
                RouterAnswer,
                schema_name=ROUTER_SCHEMA_NAME,
                options=options,
            )
        except LlmError:
            # The chat model, with the tools, can still try; the route says no model decided.
            return Route("general", "deterministic", entities)
        intent = out.value.intent
        reason = _reason(intent) if intent in REFUSED_INTENTS else ""
        calls = planned_calls(intent, entities, question)
        return Route(intent, "model", entities, out.result.model, reason=reason, calls=calls)

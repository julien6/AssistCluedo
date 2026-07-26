from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields, is_dataclass
from datetime import datetime
from types import UnionType
from typing import Any, cast, get_args, get_origin, get_type_hints

JsonScalar = str | int | float | bool | None


def _to_plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


def _convert(value: Any, annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if value is None:
        return None
    if annotation is datetime:
        return datetime.fromisoformat(value)
    if origin is list:
        item_type = args[0] if args else Any
        return [_convert(item, item_type) for item in value]
    if origin is dict:
        return dict(value)
    if origin in (UnionType,):
        non_none = [arg for arg in args if arg is not type(None)]
        return _convert(value, non_none[0]) if len(non_none) == 1 else value
    if isinstance(annotation, type) and is_dataclass(annotation):
        return cast(type[Serializable], annotation).from_dict(value)
    return value


class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return _to_plain(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        values = {}
        hints = get_type_hints(cls)
        for item in fields(cast(Any, cls)):
            if item.name in data:
                values[item.name] = _convert(data[item.name], hints[item.name])
            elif item.default is not MISSING:
                values[item.name] = item.default
            elif item.default_factory is not MISSING:
                values[item.name] = item.default_factory()
            else:
                raise KeyError(item.name)
        return cls(**values)


@dataclass(frozen=True)
class Character(Serializable):
    id: str
    name: str
    public_role: str
    private_role: str | None
    attributes: dict[str, JsonScalar] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    relationship_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Location(Serializable):
    id: str
    name: str
    location_type: str
    parent_id: str | None = None
    attributes: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class WorldObject(Serializable):
    id: str
    name: str
    object_type: str
    location_id: str | None
    owner_id: str | None
    attributes: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class Relationship(Serializable):
    id: str
    source_character_id: str
    target_character_id: str
    relationship_type: str
    attributes: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class TravelEdge(Serializable):
    source_location_id: str
    target_location_id: str
    travel_minutes: int


@dataclass(frozen=True)
class Event(Serializable):
    id: str
    event_type: str
    actor_ids: list[str]
    target_ids: list[str]
    location_id: str | None
    start_time: datetime
    end_time: datetime | None
    object_ids: list[str]
    attributes: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class Fact(Serializable):
    id: str
    subject: str
    predicate: str
    object: JsonScalar
    time: datetime | None
    location_id: str | None
    polarity: bool


@dataclass(frozen=True)
class Trace(Serializable):
    id: str
    trace_type: str
    source_event_ids: list[str]
    fact_ids: list[str]
    reliability: float
    authenticity: float
    truth_mode: str
    attributes: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentPlan(Serializable):
    id: str
    document_type: str
    source_trace_ids: list[str]
    mandatory_fact_ids: list[str]
    forbidden_fact_ids: list[str]
    author_id: str | None
    source_system_id: str | None
    truth_mode: str
    style: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedDocument(Serializable):
    id: str
    plan_id: str
    title: str
    text: str
    visible_metadata: dict[str, JsonScalar]
    extracted_fact_ids: list[str]


@dataclass(frozen=True)
class Choice(Serializable):
    id: str
    text: str


@dataclass(frozen=True)
class QuizQuestion(Serializable):
    id: str
    category: str
    text: str
    choices: list[Choice]
    correct_choice_ids: list[str]
    supporting_fact_ids: list[str]
    supporting_document_ids: list[str]
    difficulty: float
    explanation: str


@dataclass(frozen=True)
class World(Serializable):
    id: str
    characters: list[Character]
    locations: list[Location]
    objects: list[WorldObject]
    relationships: list[Relationship]
    travel_edges: list[TravelEdge] = field(default_factory=list)
    attributes: dict[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundTruth(Serializable):
    culprit_id: str
    victim_id: str
    location_id: str
    weapon_id: str
    motive: str
    incident_time: datetime
    false_lead_character_id: str
    exculpated_character_id: str


@dataclass(frozen=True)
class ProofLink(Serializable):
    conclusion: str
    fact_ids: list[str]
    document_ids: list[str]
    explanation: str


@dataclass(frozen=True)
class ProofGraph(Serializable):
    links: list[ProofLink]


@dataclass(frozen=True)
class Scenario(Serializable):
    id: str
    seed: int
    derived_seeds: dict[str, int]
    pack_id: str
    pack_version: str
    difficulty: str
    framework_version: str
    world: World
    ground_truth: GroundTruth
    events: list[Event]
    facts: list[Fact]
    traces: list[Trace]
    document_plans: list[DocumentPlan]
    documents: list[GeneratedDocument]
    questions: list[QuizQuestion]
    proof_graph: ProofGraph
    content_metadata: dict[str, JsonScalar] = field(default_factory=dict)
    public_introduction: dict[str, JsonScalar] = field(default_factory=dict)

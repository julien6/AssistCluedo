from __future__ import annotations

from assistcluedo.framework.difficulty import DifficultyConfig, get_difficulty
from assistcluedo.framework.documents import DocumentPlanner, DocumentRenderer
from assistcluedo.framework.evaluation import Score, evaluate_answers
from assistcluedo.framework.models import (
    DocumentPlan,
    Event,
    Fact,
    GeneratedDocument,
    GroundTruth,
    ProofGraph,
    QuizQuestion,
    Scenario,
    Trace,
    World,
)
from assistcluedo.framework.pack import Pack, load_pack
from assistcluedo.framework.proof import ProofGraphBuilder
from assistcluedo.framework.questions import QuestionGenerator
from assistcluedo.framework.scenario import ScenarioGenerator
from assistcluedo.framework.timeline import FactEngine, TimelineEngine
from assistcluedo.framework.traces import TraceGenerator
from assistcluedo.framework.validation import ValidationReport, validate_scenario
from assistcluedo.framework.world import WorldGenerator


def generate_world(seed: int, pack_id: str = "classic_manor", difficulty: str = "easy") -> World:
    pack = load_pack(pack_id)
    return WorldGenerator().generate(seed, pack, get_difficulty(difficulty))


def generate_ground_truth(seed: int, world: World, pack: Pack) -> GroundTruth:
    return ScenarioGenerator().generate_ground_truth(seed, world, pack)


def generate_timeline(
    seed: int,
    world: World,
    ground_truth: GroundTruth,
    difficulty: str | DifficultyConfig = "easy",
) -> list[Event]:
    profile = get_difficulty(difficulty) if isinstance(difficulty, str) else difficulty
    return TimelineEngine().generate(seed, world, ground_truth, profile)


def generate_facts(world: World, ground_truth: GroundTruth, events: list[Event]) -> list[Fact]:
    return FactEngine().generate(world, ground_truth, events)


def generate_traces(
    seed: int,
    facts: list[Fact],
    events: list[Event],
    ground_truth: GroundTruth,
) -> list[Trace]:
    return TraceGenerator().generate(seed, facts, events, ground_truth)


def generate_document_plans(traces: list[Trace], events: list[Event], world: World) -> list[DocumentPlan]:
    return DocumentPlanner().generate(traces, events, world)


def generate_documents(
    seed: int,
    world: World,
    ground_truth: GroundTruth,
    facts: list[Fact],
    traces: list[Trace],
    document_plans: list[DocumentPlan],
    pack: Pack,
) -> list[GeneratedDocument]:
    return DocumentRenderer().generate(seed, world, ground_truth, facts, traces, document_plans, pack)


def generate_proof_graph(
    ground_truth: GroundTruth,
    facts: list[Fact],
    documents: list[GeneratedDocument],
) -> ProofGraph:
    return ProofGraphBuilder().build(ground_truth, facts, documents)


def generate_quiz(
    seed: int,
    world: World,
    ground_truth: GroundTruth,
    facts: list[Fact],
    documents: list[GeneratedDocument],
    proof_graph: ProofGraph,
    difficulty: str | DifficultyConfig = "easy",
) -> list[QuizQuestion]:
    profile = get_difficulty(difficulty) if isinstance(difficulty, str) else difficulty
    return QuestionGenerator().generate(seed, world, ground_truth, facts, documents, proof_graph, profile)


def validate_generated_scenario(scenario: Scenario) -> ValidationReport:
    return validate_scenario(scenario)


__all__ = [
    "Score",
    "evaluate_answers",
    "generate_document_plans",
    "generate_documents",
    "generate_facts",
    "generate_ground_truth",
    "generate_proof_graph",
    "generate_quiz",
    "generate_timeline",
    "generate_traces",
    "generate_world",
    "validate_generated_scenario",
]

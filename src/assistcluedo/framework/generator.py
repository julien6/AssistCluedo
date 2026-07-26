from __future__ import annotations

from assistcluedo import __version__
from assistcluedo.framework.difficulty import get_difficulty
from assistcluedo.framework.documents import DocumentPlanner, DocumentRenderer
from assistcluedo.framework.models import GeneratedDocument, Scenario
from assistcluedo.framework.pack import load_pack
from assistcluedo.framework.proof import ProofGraphBuilder
from assistcluedo.framework.questions import QuestionGenerator
from assistcluedo.framework.scenario import ScenarioGenerator
from assistcluedo.framework.seed import derive_seeds, rng_for
from assistcluedo.framework.timeline import FactEngine, TimelineEngine
from assistcluedo.framework.traces import TraceGenerator
from assistcluedo.framework.validation import validate_scenario
from assistcluedo.framework.world import WorldGenerator


def generate_symbolic_scenario(
    seed: int,
    pack_id: str = "classic_manor",
    difficulty: str = "easy",
) -> Scenario:
    pack = load_pack(pack_id)
    difficulty_config = get_difficulty(difficulty)
    derived = derive_seeds(seed)

    world = WorldGenerator().generate(seed, pack, difficulty_config)
    truth = ScenarioGenerator().generate_ground_truth(seed, world, pack)
    events = TimelineEngine().generate(seed, world, truth, difficulty_config)
    facts = FactEngine().generate(world, truth, events)
    traces = TraceGenerator().generate(seed, facts, events, truth)
    plans = DocumentPlanner().generate(traces)
    documents = DocumentRenderer().generate(seed, world, truth, facts, traces, plans, pack)
    proof_graph = ProofGraphBuilder().build(truth, facts, documents)
    questions = QuestionGenerator().generate(
        seed, world, truth, facts, documents, proof_graph, difficulty_config
    )
    documents = _shuffle_documents(seed, documents)

    scenario = Scenario(
        id=f"scenario_{seed:06d}",
        seed=seed,
        derived_seeds=derived,
        pack_id=pack.id,
        pack_version=pack.version,
        difficulty=difficulty_config.id,
        framework_version=__version__,
        world=world,
        ground_truth=truth,
        events=events,
        facts=facts,
        traces=traces,
        document_plans=plans,
        documents=documents,
        questions=questions,
        proof_graph=proof_graph,
    )
    report = validate_scenario(scenario)
    if not report.ok:
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in report.issues[:5])
        raise ValueError(f"Generated scenario failed validation: {details}")
    return scenario


def _shuffle_documents(seed: int, documents: list[GeneratedDocument]) -> list[GeneratedDocument]:
    shuffled = list(documents)
    rng_for(seed, "shuffle").shuffle(shuffled)
    return shuffled

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from assistcluedo.framework.documents import DocumentRenderer
from assistcluedo.framework.models import GeneratedDocument, Scenario
from assistcluedo.framework.pack import load_pack
from assistcluedo.framework.seed import rng_for
from assistcluedo.framework.serialization import read_json, write_json, write_yaml
from assistcluedo.framework.validation import validate_scenario
from assistcluedo.game.player_package import build_player_package, player_introduction_for


def export_scenario(scenario: Scenario, output_dir: Path) -> None:
    report = validate_scenario(scenario)
    if not report.ok:
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in report.issues[:5])
        raise ValueError(f"Cannot export invalid scenario: {details}")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "scenario.json", scenario.to_dict())
    write_json(output_dir / "metadata.json", {
        "scenario_id": scenario.id,
        "seed": scenario.seed,
        "pack_id": scenario.pack_id,
        "pack_version": scenario.pack_version,
        "difficulty": scenario.difficulty,
        "framework_version": scenario.framework_version,
    })
    write_json(output_dir / "seeds.json", scenario.derived_seeds)
    write_yaml(
        output_dir / "config_snapshot.yaml",
        {"pack": scenario.pack_id, "seed": scenario.seed, "difficulty": scenario.difficulty},
    )
    write_yaml(output_dir / "ontology_snapshot.yaml", {"pack_id": scenario.pack_id, "pack_version": scenario.pack_version})
    write_yaml(output_dir / "oracle" / "world.yaml", scenario.world.to_dict())
    write_yaml(output_dir / "oracle" / "ground_truth.yaml", scenario.ground_truth.to_dict())
    write_yaml(output_dir / "oracle" / "timeline.yaml", [event.to_dict() for event in scenario.events])
    write_yaml(output_dir / "oracle" / "facts.yaml", [fact.to_dict() for fact in scenario.facts])
    write_yaml(output_dir / "oracle" / "traces.yaml", [trace.to_dict() for trace in scenario.traces])
    write_yaml(output_dir / "oracle" / "proof_graph.yaml", scenario.proof_graph.to_dict())
    for plan in scenario.document_plans:
        write_json(output_dir / "document_plans" / f"{plan.id}.json", plan.to_dict())
    for document in scenario.documents:
        write_json(output_dir / "generated_documents" / f"{document.id}.json", document.to_dict())
    player_package = build_player_package(scenario)
    write_json(output_dir / "player_package" / "introduction.json", player_package.introduction)
    write_json(
        output_dir / "player_package" / "characters.json",
        [character.to_dict() for character in player_package.characters],
    )
    write_json(
        output_dir / "player_package" / "locations.json",
        [location.to_dict() for location in player_package.locations],
    )
    write_json(
        output_dir / "player_package" / "quiz.json",
        [question.to_dict() for question in player_package.quiz],
    )
    for player_document in player_package.documents:
        write_json(
            output_dir / "player_package" / "documents" / f"{player_document.id}.json",
            player_document.to_dict(),
        )
    write_json(output_dir / "evaluation" / "answer_key.json", {q.id: q.correct_choice_ids for q in scenario.questions})
    write_json(output_dir / "evaluation" / "explanations.json", {q.id: q.explanation for q in scenario.questions})
    write_yaml(output_dir / "evaluation" / "scoring_config.yaml", {"total": 100, "questions": len(scenario.questions)})


def load_exported_scenario(path: Path) -> Scenario:
    return Scenario.from_dict(read_json(path / "scenario.json"))


def regenerate_documents(path: Path, provider: str = "template") -> Scenario:
    if provider != "template":
        raise ValueError("Only the deterministic template provider is available.")
    scenario = load_exported_scenario(path)
    pack = load_pack(scenario.pack_id)
    documents = DocumentRenderer().generate(
        scenario.seed,
        scenario.world,
        scenario.ground_truth,
        scenario.facts,
        scenario.traces,
        scenario.document_plans,
        pack,
    )
    regenerated = replace(scenario, documents=_shuffle_documents(scenario.seed, documents))
    export_scenario(regenerated, path)
    return regenerated


def _shuffle_documents(seed: int, documents: list[GeneratedDocument]) -> list[GeneratedDocument]:
    shuffled = list(documents)
    rng_for(seed, "shuffle").shuffle(shuffled)
    return shuffled


def introduction_for(scenario: Scenario) -> dict[str, object]:
    return player_introduction_for(scenario)

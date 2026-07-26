from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from assistcluedo.framework.access import character_can_access_location
from assistcluedo.framework.api import (
    evaluate_answers,
    generate_document_plans,
    generate_documents,
    generate_facts,
    generate_ground_truth,
    generate_proof_graph,
    generate_quiz,
    generate_timeline,
    generate_traces,
    generate_world,
    validate_generated_scenario,
)
from assistcluedo.framework.difficulty import get_difficulty
from assistcluedo.framework.documents import DocumentPlanner, DocumentRenderer
from assistcluedo.framework.export import export_scenario
from assistcluedo.framework.generator import generate_symbolic_scenario
from assistcluedo.framework.models import Scenario
from assistcluedo.framework.pack import load_pack
from assistcluedo.framework.proof import ProofGraphBuilder
from assistcluedo.framework.questions import QuestionGenerator
from assistcluedo.framework.scenario import ScenarioGenerator
from assistcluedo.framework.seed import derive_seed, derive_seeds
from assistcluedo.framework.timeline import FactEngine, TimelineEngine
from assistcluedo.framework.traces import TraceGenerator
from assistcluedo.framework.validation import (
    DocumentValidator,
    QuestionValidator,
    validate_export,
    validate_scenario,
)
from assistcluedo.framework.world import WorldGenerator
from assistcluedo.game.evaluation import evaluate_scenario
from assistcluedo.game.player_package import build_player_package
from assistcluedo.game.scoring import calculate_score


def test_seed_derivation_is_stable_and_separate() -> None:
    assert derive_seed(42, "world") == derive_seed(42, "world")
    assert derive_seed(42, "world") != derive_seed(42, "quiz")
    assert set(derive_seeds(42)) == {"world", "scenario", "timeline", "traces", "documents", "quiz", "shuffle"}


def test_generation_is_deterministic_and_seed_sensitive() -> None:
    first = generate_symbolic_scenario(42)
    second = generate_symbolic_scenario(42)
    other = generate_symbolic_scenario(43)
    assert first.to_dict() == second.to_dict()
    assert first.to_dict() != other.to_dict()
    assert len(first.world.characters) == 6
    assert len(first.documents) == 14
    assert len(first.questions) == 6


def test_difficulty_scales_case_size() -> None:
    easy = generate_symbolic_scenario(42, difficulty="easy")
    spark = generate_symbolic_scenario(42, difficulty="spark")
    assert len(spark.world.characters) > len(easy.world.characters)
    assert len(spark.world.locations) > len(easy.world.locations)
    assert len(spark.events) > len(easy.events)
    assert len(spark.documents) > len(easy.documents)
    assert len(spark.questions) > len(easy.questions)


def test_scenario_round_trip_without_information_loss() -> None:
    scenario = generate_symbolic_scenario(42)
    reloaded = Scenario.from_dict(scenario.to_dict())
    assert reloaded == scenario


def test_generation_components_can_be_used_independently() -> None:
    seed = 42
    pack = load_pack("classic_manor")
    difficulty = get_difficulty("easy")
    world = WorldGenerator().generate(seed, pack, difficulty)
    truth = ScenarioGenerator().generate_ground_truth(seed, world, pack)
    events = TimelineEngine().generate(seed, world, truth, difficulty)
    facts = FactEngine().generate(world, truth, events)
    traces = TraceGenerator().generate(seed, facts, events, truth)
    plans = DocumentPlanner().generate(traces)
    documents = DocumentRenderer().generate(seed, world, truth, facts, traces, plans, pack)
    proof_graph = ProofGraphBuilder().build(truth, facts, documents)
    questions = QuestionGenerator().generate(seed, world, truth, facts, documents, proof_graph, difficulty)
    assert world.characters
    assert truth.culprit_id
    assert events
    assert facts
    assert traces
    assert plans
    assert documents
    assert proof_graph.links
    assert questions


def test_framework_api_exposes_roadmap_pipeline_functions() -> None:
    seed = 42
    pack = load_pack("classic_manor")
    world = generate_world(seed)
    truth = generate_ground_truth(seed, world, pack)
    events = generate_timeline(seed, world, truth)
    facts = generate_facts(world, truth, events)
    traces = generate_traces(seed, facts, events, truth)
    plans = generate_document_plans(traces)
    documents = generate_documents(seed, world, truth, facts, traces, plans, pack)
    proof_graph = generate_proof_graph(truth, facts, documents)
    questions = generate_quiz(seed, world, truth, facts, documents, proof_graph)
    scenario = replace(
        generate_symbolic_scenario(seed),
        world=world,
        ground_truth=truth,
        events=events,
        facts=facts,
        traces=traces,
        document_plans=plans,
        documents=documents,
        proof_graph=proof_graph,
        questions=questions,
    )
    answers = {question.id: question.correct_choice_ids[0] for question in questions}
    assert validate_generated_scenario(scenario).ok
    assert evaluate_answers(scenario, answers).total == 100


def test_questions_have_one_supported_answer() -> None:
    scenario = generate_symbolic_scenario(42)
    report = validate_scenario(scenario)
    assert report.ok, report.to_dict()
    document_ids = {document.id for document in scenario.documents}
    for question in scenario.questions:
        assert len(question.correct_choice_ids) == 1
        assert question.correct_choice_ids[0] in {choice.id for choice in question.choices}
        assert set(question.supporting_document_ids) <= document_ids
        assert question.supporting_document_ids


def test_world_has_connected_travel_graph() -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    location_ids = {location.id for location in scenario.world.locations}
    assert scenario.world.travel_edges
    assert {edge.travel_minutes for edge in scenario.world.travel_edges} != {1}
    assert {
        edge.source_location_id for edge in scenario.world.travel_edges
    } == location_ids
    assert validate_scenario(scenario).ok


def test_culprit_can_access_weapon_location() -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    culprit = next(
        character for character in scenario.world.characters if character.id == scenario.ground_truth.culprit_id
    )
    weapon = next(obj for obj in scenario.world.objects if obj.id == scenario.ground_truth.weapon_id)
    location = next(loc for loc in scenario.world.locations if loc.id == weapon.location_id)
    assert character_can_access_location(culprit, location)


def test_weapon_state_facts_track_initial_use_and_hide() -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    fact_ids = {fact.id for fact in scenario.facts}
    assert "fact_weapon_initial_location" in fact_ids
    assert "fact_murder_weapon" in fact_ids
    assert "fact_weapon_hidden" in fact_ids
    incident = next(event for event in scenario.events if event.event_type == "main_incident")
    hide = next(event for event in scenario.events if event.event_type == "hide_evidence")
    assert scenario.ground_truth.weapon_id in incident.object_ids
    assert scenario.ground_truth.weapon_id in hide.object_ids
    assert hide.start_time > incident.start_time


def test_spark_quiz_contains_travel_time_question() -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    assert any("travel from" in question.text for question in scenario.questions)


def test_validate_scenario_rejects_disconnected_travel_graph() -> None:
    scenario = generate_symbolic_scenario(42)
    bad_world = replace(scenario.world, travel_edges=[])
    bad_scenario = replace(scenario, world=bad_world)
    report = validate_scenario(bad_scenario)
    assert not report.ok
    assert any(issue.code in {"travel_graph_disconnected", "travel_missing_edge"} for issue in report.issues)


def test_score_calculation() -> None:
    scenario = generate_symbolic_scenario(42)
    answers = {question.id: question.correct_choice_ids[0] for question in scenario.questions}
    score = calculate_score(scenario.questions, answers)
    assert score.total == 100
    assert score.correct == 6
    assert score.weighted_by_category
    assert sum(score.weighted_by_category.values()) == 100


def test_evaluation_report_includes_answer_evidence_snapshot() -> None:
    scenario = generate_symbolic_scenario(42)
    answers = {question.id: question.correct_choice_ids[0] for question in scenario.questions}
    evidence = {scenario.questions[0].id: [scenario.documents[0].id, scenario.documents[1].id]}
    report = evaluate_scenario(scenario, answers, evidence)
    assert report["questions"][0]["opened_document_ids_before_answer"] == evidence[scenario.questions[0].id]
    assert report["questions"][1]["opened_document_ids_before_answer"] == []


def test_evaluation_report_includes_post_game_proof_details() -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    answers = {question.id: question.correct_choice_ids[0] for question in scenario.questions}
    report = evaluate_scenario(scenario, answers)
    first = report["questions"][0]
    assert first["supporting_fact_ids"]
    assert first["supporting_document_ids"]
    assert first["supporting_event_ids"]
    assert len(first["choice_reviews"]) == len(scenario.questions[0].choices)
    assert sum(1 for choice in first["choice_reviews"] if choice["is_correct"]) == 1
    assert all("review" in choice for choice in first["choice_reviews"])


def test_export_structure(tmp_path: Path) -> None:
    scenario = generate_symbolic_scenario(42)
    export_scenario(scenario, tmp_path)
    report = validate_export(tmp_path)
    assert report.ok, report.to_dict()
    assert (tmp_path / "metadata.json").exists()
    assert (tmp_path / "scenario.json").exists()
    assert Scenario.from_dict(json.loads((tmp_path / "scenario.json").read_text())) == scenario
    assert (tmp_path / "oracle" / "ground_truth.yaml").exists()
    assert (tmp_path / "player_package" / "quiz.json").exists()
    assert (tmp_path / "evaluation" / "answer_key.json").exists()


def test_player_package_does_not_expose_oracle_fields(tmp_path: Path) -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    export_scenario(scenario, tmp_path)
    forbidden = {
        "correct_choice_ids",
        "supporting_fact_ids",
        "supporting_document_ids",
        "explanation",
        "extracted_fact_ids",
        "plan_id",
        "private_role",
        "relationship_ids",
    }
    for path in (tmp_path / "player_package").rglob("*.json"):
        data = json.loads(path.read_text())
        encoded = json.dumps(data)
        for key in forbidden:
            assert f'"{key}"' not in encoded


def test_player_package_model_omits_oracle_data() -> None:
    scenario = generate_symbolic_scenario(42, difficulty="spark")
    package = build_player_package(scenario)
    encoded = json.dumps(
        {
            "introduction": package.introduction,
            "characters": [character.to_dict() for character in package.characters],
            "locations": [location.to_dict() for location in package.locations],
            "documents": [document.to_dict() for document in package.documents],
            "quiz": [question.to_dict() for question in package.quiz],
        }
    )
    for key in (
        "correct_choice_ids",
        "supporting_fact_ids",
        "supporting_document_ids",
        "explanation",
        "extracted_fact_ids",
        "plan_id",
        "private_role",
        "relationship_ids",
    ):
        assert f'"{key}"' not in encoded


def test_validate_export_rejects_player_package_oracle_leak(tmp_path: Path) -> None:
    scenario = generate_symbolic_scenario(42)
    export_scenario(scenario, tmp_path)
    quiz_path = tmp_path / "player_package" / "quiz.json"
    quiz = json.loads(quiz_path.read_text(encoding="utf-8"))
    quiz[0]["correct_choice_ids"] = ["c1"]
    quiz_path.write_text(json.dumps(quiz), encoding="utf-8")
    report = validate_export(tmp_path)
    assert not report.ok
    assert any(issue.code == "player_package_forbidden_key" for issue in report.issues)


def test_validate_scenario_rejects_question_without_real_support() -> None:
    scenario = generate_symbolic_scenario(42)
    wrong_document = next(
        document for document in scenario.documents if "fact_badge_access" not in document.extracted_fact_ids
    )
    bad_question = replace(
        scenario.questions[0],
        supporting_fact_ids=["fact_badge_access"],
        supporting_document_ids=[wrong_document.id],
    )
    bad_scenario = replace(scenario, questions=[bad_question, *scenario.questions[1:]])
    report = validate_scenario(bad_scenario)
    assert not report.ok
    assert any(issue.code == "question_fact_not_in_support_documents" for issue in report.issues)


def test_named_document_and_question_validators_are_reusable() -> None:
    scenario = generate_symbolic_scenario(42)
    assert DocumentValidator().validate(scenario.documents, scenario) == []
    assert QuestionValidator().validate(scenario.questions, scenario) == []


def test_document_validator_checks_metadata_and_creation_time() -> None:
    scenario = generate_symbolic_scenario(42)
    document = scenario.documents[0]
    bad_metadata = dict(document.visible_metadata)
    bad_metadata.pop("created_at")
    bad_document = replace(document, visible_metadata=bad_metadata)
    issues = DocumentValidator().validate([bad_document], scenario)
    assert any(issue.code == "document_metadata_missing" for issue in issues)

    bad_metadata["created_at"] = "1900-01-01T00:00:00+00:00"
    bad_document = replace(document, visible_metadata=bad_metadata)
    issues = DocumentValidator().validate([bad_document], scenario)
    assert any(issue.code == "document_created_before_fact" for issue in issues)


def test_document_validator_checks_plan_trace_truth_mode_alignment() -> None:
    scenario = generate_symbolic_scenario(42)
    plan = scenario.document_plans[0]
    document = next(document for document in scenario.documents if document.plan_id == plan.id)
    bad_plan = replace(plan, truth_mode="deceptive" if plan.truth_mode != "deceptive" else "accurate")
    bad_scenario = replace(scenario, document_plans=[bad_plan, *scenario.document_plans[1:]])
    issues = DocumentValidator().validate([document], bad_scenario)
    assert any(issue.code == "plan_trace_truth_mode_mismatch" for issue in issues)

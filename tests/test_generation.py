from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

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
from assistcluedo.framework.contentgen import (
    FallbackContentGenerator,
    ProceduralContentGenerator,
    ScenarioTextResult,
    WorldContentResult,
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
from assistcluedo.framework.textgen import (
    DocumentProfileCatalog,
    FallbackTextGenerator,
    LocalLLMTextGenerator,
    SourceStyleCatalog,
    TemplateTextGenerator,
    TextGenerationRequest,
    TextGenerationResult,
    validate_text_generation_result,
)
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
    assert len(first.documents) == 22
    assert len(first.questions) == 6


def test_seed_changes_visible_world_content_substantially() -> None:
    first = generate_symbolic_scenario(42, difficulty="spark")
    other = generate_symbolic_scenario(43, difficulty="spark")
    first_names = {character.name for character in first.world.characters}
    other_names = {character.name for character in other.world.characters}
    first_locations = {location.name for location in first.world.locations}
    other_locations = {location.name for location in other.world.locations}
    first_objects = {obj.name for obj in first.world.objects}
    other_objects = {obj.name for obj in other.world.objects}
    assert len(first_names & other_names) <= max(1, len(first_names) // 3)
    assert first_locations != other_locations
    assert first_objects != other_objects
    assert first.content_metadata["world_content_provider"] == "procedural"
    assert first.content_metadata["world_content_fallback_used"] is True
    visible_text = json.dumps(
        {
            "world": first.world.to_dict(),
            "documents": [document.to_dict() for document in first.documents],
            "questions": [question.to_dict() for question in first.questions],
            "introduction": first.public_introduction,
        }
    )
    assert "General Hargreaves" not in visible_text


def test_difficulty_scales_case_size() -> None:
    easy = generate_symbolic_scenario(42, difficulty="easy")
    spark = generate_symbolic_scenario(42, difficulty="spark")
    assert len(spark.world.characters) > len(easy.world.characters)
    assert len(spark.world.locations) > len(easy.world.locations)
    assert len(spark.events) > len(easy.events)
    assert len(spark.documents) > len(easy.documents)
    assert len(spark.questions) > len(easy.questions)
    assert len(easy.documents) == 22
    assert len(spark.documents) == 90


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


def test_template_documents_use_source_specific_realistic_formats() -> None:
    scenario = generate_symbolic_scenario(42)
    sms = next(document for document in scenario.documents if document.visible_metadata["type"] == "sms")
    access_log = next(
        document for document in scenario.documents if document.visible_metadata["type"] == "access-control log"
    )
    assert sms.visible_metadata["source_profile"] in {"personal_sms_exchange", "single_sms", "phone_notification"}
    assert any(marker in sms.text for marker in ("quiet", "Come alone", "Keep it between us", "side corridor"))
    assert "Not the dining room" not in sms.text
    assert "|" in access_log.text
    assert any(marker in access_log.text.lower() for marker in ("granted", " ok", "| ok"))
    assert sms.visible_metadata["text_provider"] == "procedural"
    assert sms.visible_metadata["fallback_used"] is True


def test_template_documents_avoid_third_person_investigative_summaries() -> None:
    scenario = generate_symbolic_scenario(7, difficulty="easy")
    combined_text = "\n".join(document.text for document in scenario.documents)
    forbidden_fragments = [
        " appears in a ",
        " appears near ",
        "message asking for a private meeting",
        "Records show ",
        "had a motive:",
        "had a heated argument with",
        " away from the incident location",
        "claimed not to have been near",
        "Treat this statement cautiously",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in combined_text

    by_type = {document.visible_metadata["type"]: document.text for document in scenario.documents}
    assert any(marker in by_type["sms"] for marker in ("Hi", "You there", "Still inside", "From:", "SMS export"))
    assert "From:" in by_type["email"]
    assert "Subject:" in by_type["email"]
    assert "\nI " in by_type["personal note"]
    assert "Detective:" in by_type["witness interview"]
    assert "Witness:" in by_type["witness interview"]
    assert "Telephone exchange log" in by_type["call log"]
    assert "Phone location export" in by_type["gps report"]
    assert any(marker in by_type["receipt"] for marker in ("PETTY CASH RECEIPT", "Counterfoil slip"))


def test_document_plans_include_source_context_for_text_generation() -> None:
    scenario = generate_symbolic_scenario(42)
    sms_plan = next(plan for plan in scenario.document_plans if plan.document_type == "sms")
    interview_plan = next(plan for plan in scenario.document_plans if plan.document_type == "witness interview")
    assert sms_plan.source_system_id == "mobile phone extraction"
    assert sms_plan.style["tone"] == "tense and elliptical"
    assert interview_plan.style["register"] == "spoken transcript"


def test_document_profiles_are_seeded_and_vary_document_shapes() -> None:
    first = generate_symbolic_scenario(42, difficulty="spark")
    second = generate_symbolic_scenario(42, difficulty="spark")
    other = generate_symbolic_scenario(43, difficulty="spark")
    first_profiles = [document.visible_metadata["source_profile"] for document in first.documents]
    assert first_profiles == [document.visible_metadata["source_profile"] for document in second.documents]
    assert first_profiles != [document.visible_metadata["source_profile"] for document in other.documents]
    assert len(set(first_profiles)) > 5


def test_procedural_sms_fallback_has_multiple_realistic_variants() -> None:
    texts = []
    profiles = set()
    for seed in range(1, 12):
        scenario = generate_symbolic_scenario(seed, difficulty="easy")
        sms = next(document for document in scenario.documents if document.visible_metadata["type"] == "sms")
        texts.append(sms.text)
        profiles.add(str(sms.visible_metadata["source_profile"]))
    assert len(set(texts)) >= 3
    assert len(profiles) >= 2
    assert all("message asking for a private meeting" not in text for text in texts)


def test_procedural_documents_include_harmless_realistic_texture() -> None:
    scenario = generate_symbolic_scenario(70, difficulty="easy")
    by_type = {document.visible_metadata["type"]: document.text for document in scenario.documents}
    assert len(by_type["email"].splitlines()) >= 10
    assert any(marker in by_type["email"] for marker in ("secretary", "dinner", "cold coffee", "house is not large"))
    assert any(marker in by_type["call log"] for marker in ("switchboard:", "duration"))
    assert any(marker in by_type["receipt"] for marker in ("terminal:", "clerk"))
    assert any(marker in by_type["personal note"] for marker in ("tea", "clock", "mud", "blue cup", "pencil", "polish"))
    average_lines = sum(len(document.text.splitlines()) for document in scenario.documents) / len(scenario.documents)
    assert average_lines >= 5


def test_procedural_documents_do_not_expose_internal_symbolic_ids() -> None:
    scenario = generate_symbolic_scenario(70, difficulty="easy")
    visible_text = "\n".join(document.text for document in scenario.documents)
    assert "fact_" not in visible_text
    assert "plan_" not in visible_text
    assert "trace_" not in visible_text
    assert "dining_room" not in visible_text
    assert "badge:" not in visible_text
    access_log = next(document.text for document in scenario.documents if document.visible_metadata["type"] == "access-control log")
    assert "cardholder" in access_log
    assert any("|" in line and "-" in line for line in access_log.splitlines())


def test_sms_templates_do_not_hardcode_a_room_contradicting_the_scenario() -> None:
    for seed in range(40, 46):
        scenario = generate_symbolic_scenario(seed, difficulty="easy")
        sms = next(document.text for document in scenario.documents if document.visible_metadata["type"] == "sms")
        assert "Not the dining room" not in sms
        assert "Same quiet place as before" in sms or "Come alone" in sms or "Keep it between us" in sms


def test_source_native_documents_have_profile_specific_artifact_markers() -> None:
    scenario = generate_symbolic_scenario(71, difficulty="easy")
    markers = {
        "sms": ("SMS", "notification", "Mobile extraction"),
        "email": ("Subject:", "Message-ID:"),
        "access-control log": ("credential", "cardholder", "|"),
        "witness interview": ("Statement ref:", "Detective:", "Witness:"),
        "autopsy report": ("Case ref:", "Chain note:"),
        "security report": ("export ref:", "System:", "alert id:"),
        "personal note": ("[recovered from", "I ", "My "),
        "inventory report": ("Sheet ref:", "Item checks:"),
        "gps report": ("export ref:", "confidence"),
        "receipt": ("receipt no:", "terminal:", "clerk"),
        "call log": ("log ref:", "duration"),
        "newspaper clipping": ("Publication:", "Column note:", "Clipping filed:"),
    }
    by_type = {document.visible_metadata["type"]: document.text for document in scenario.documents}
    for document_type, expected_markers in markers.items():
        if document_type in by_type:
            assert any(marker in by_type[document_type] for marker in expected_markers), document_type


def test_text_validation_rejects_internal_id_leaks() -> None:
    class IdLeakingGenerator:
        def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
            return TextGenerationResult(
                title=request.title,
                text="From: Alex\nTo: Blake\nSubject: Tonight\n\nRecords include fact_badge_access and badge:secretary.",
                facts_expressed=list(request.plan.mandatory_fact_ids),
                entities_mentioned=[],
                provider="id-leak",
            )

    scenario = generate_symbolic_scenario(42)
    plan = next(plan for plan in scenario.document_plans if plan.document_type == "email")
    trace = next(trace for trace in scenario.traces if trace.id == plan.source_trace_ids[0])
    facts = [fact for fact in scenario.facts if fact.id in plan.mandatory_fact_ids]
    request = TextGenerationRequest(
        document_id="doc_test",
        title="Test",
        plan=plan,
        trace=trace,
        world=scenario.world,
        truth=scenario.ground_truth,
        facts=facts,
        created_at=scenario.ground_truth.incident_time.isoformat(),
        source_style=SourceStyleCatalog().profile_for(plan.document_type),
        document_profile=DocumentProfileCatalog().profile_for(42, "doc_test", plan.document_type),
    )
    result = IdLeakingGenerator().generate(request)
    with pytest.raises(ValueError, match="internal ids"):
        validate_text_generation_result(request, result)

    snake_case_result = TextGenerationResult(
        title=request.title,
        text="From: Alex\nTo: Blake\nSubject: Tonight\n\nThe dining_room controller row is attached.",
        facts_expressed=list(request.plan.mandatory_fact_ids),
        entities_mentioned=[],
        provider="id-leak",
    )
    with pytest.raises(ValueError, match="internal ids"):
        validate_text_generation_result(request, snake_case_result)


def test_text_generator_fallback_rejects_invalid_primary_output() -> None:
    class InvalidGenerator:
        def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
            return TextGenerationResult(
                title="Invalid",
                text="This omits facts.",
                facts_expressed=[],
                entities_mentioned=[],
                provider="invalid",
            )

    scenario = generate_symbolic_scenario(42)
    plan = scenario.document_plans[0]
    trace = next(trace for trace in scenario.traces if trace.id == plan.source_trace_ids[0])
    facts = [fact for fact in scenario.facts if fact.id in plan.mandatory_fact_ids]
    request = TextGenerationRequest(
        document_id="doc_test",
        title="Test",
        plan=plan,
        trace=trace,
        world=scenario.world,
        truth=scenario.ground_truth,
        facts=facts,
        created_at=scenario.ground_truth.incident_time.isoformat(),
        source_style=SourceStyleCatalog().profile_for(plan.document_type),
        document_profile=DocumentProfileCatalog().profile_for(42, "doc_test", plan.document_type),
    )
    result = FallbackTextGenerator(InvalidGenerator(), TemplateTextGenerator()).generate(request)
    assert result.provider == "template"
    assert result.fallback_used is True


def test_text_generator_fallback_rejects_summary_style_primary_output() -> None:
    class SummaryGenerator:
        def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
            return TextGenerationResult(
                title=request.title,
                text="Records show Clara Hargreaves had a motive.",
                facts_expressed=list(request.plan.mandatory_fact_ids),
                entities_mentioned=[],
                provider="summary",
            )

    scenario = generate_symbolic_scenario(42)
    plan = next(plan for plan in scenario.document_plans if plan.document_type == "email")
    trace = next(trace for trace in scenario.traces if trace.id == plan.source_trace_ids[0])
    facts = [fact for fact in scenario.facts if fact.id in plan.mandatory_fact_ids]
    request = TextGenerationRequest(
        document_id="doc_test",
        title="Test",
        plan=plan,
        trace=trace,
        world=scenario.world,
        truth=scenario.ground_truth,
        facts=facts,
        created_at=scenario.ground_truth.incident_time.isoformat(),
        source_style=SourceStyleCatalog().profile_for(plan.document_type),
        document_profile=DocumentProfileCatalog().profile_for(42, "doc_test", plan.document_type),
    )
    result = FallbackTextGenerator(SummaryGenerator(), TemplateTextGenerator()).generate(request)
    assert result.provider == "template"
    assert result.fallback_used is True


def test_text_generator_fallback_rejects_wrong_source_shape_primary_output() -> None:
    class SmsSummaryGenerator:
        def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
            return TextGenerationResult(
                title=request.title,
                text="Marta Bell sent General Hargreaves a message asking for a private meeting at 20:27.",
                facts_expressed=list(request.plan.mandatory_fact_ids),
                entities_mentioned=[],
                provider="summary",
            )

    scenario = generate_symbolic_scenario(7)
    plan = next(plan for plan in scenario.document_plans if plan.document_type == "sms")
    trace = next(trace for trace in scenario.traces if trace.id == plan.source_trace_ids[0])
    facts = [fact for fact in scenario.facts if fact.id in plan.mandatory_fact_ids]
    request = TextGenerationRequest(
        document_id="doc_test",
        title="Test",
        plan=plan,
        trace=trace,
        world=scenario.world,
        truth=scenario.ground_truth,
        facts=facts,
        created_at=scenario.ground_truth.incident_time.isoformat(),
        source_style=SourceStyleCatalog().profile_for(plan.document_type),
        document_profile=DocumentProfileCatalog().profile_for(7, "doc_test", plan.document_type),
    )
    result = FallbackTextGenerator(SmsSummaryGenerator(), TemplateTextGenerator()).generate(request)
    assert result.provider == "template"
    assert result.fallback_used is True
    assert any(marker in result.text for marker in ("Recovered SMS thread", "SMS export", "Phone notification preview"))


def test_content_generator_fallback_rejects_invalid_llm_world_content() -> None:
    class InvalidContentGenerator:
        def generate_world_content(self, seed, pack, difficulty, world):  # type: ignore[no-untyped-def]
            return WorldContentResult({}, {}, {}, [], "invalid")

        def generate_scenario_texts(self, scenario):  # type: ignore[no-untyped-def]
            return ScenarioTextResult({}, {}, "invalid")

    pack = load_pack("classic_manor")
    difficulty = get_difficulty("easy")
    world = WorldGenerator().generate(42, pack, difficulty)
    result = FallbackContentGenerator(InvalidContentGenerator(), ProceduralContentGenerator()).generate_world_content(
        42,
        pack,
        difficulty,
        world,
    )
    assert result.provider == "procedural"
    assert result.fallback_used is True


def test_local_llm_document_prompt_includes_source_native_grounding(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    capture = tmp_path / "prompt.json"
    script = tmp_path / "capture_llm.py"
    script.write_text(
        f"""import json, pathlib, sys
request = json.loads(sys.stdin.read())
pathlib.Path({str(capture)!r}).write_text(json.dumps(request), encoding='utf-8')
json.dump({{
  'title': request['title'],
  'text': 'From: Alex\\nTo: Blake\\nSubject: Tonight\\nDate: now\\nMessage-ID: <msg-local@blackwood.local>\\n\\nBlake,\\nWe need to settle this privately.',
  'facts_expressed': request['mandatory_fact_ids'],
  'entities_mentioned': [],
}}, sys.stdout)
""",
        encoding="utf-8",
    )
    scenario = generate_symbolic_scenario(42)
    plan = next(plan for plan in scenario.document_plans if plan.document_type == "email")
    trace = next(trace for trace in scenario.traces if trace.id == plan.source_trace_ids[0])
    facts = [fact for fact in scenario.facts if fact.id in plan.mandatory_fact_ids]
    request = TextGenerationRequest(
        document_id="doc_prompt",
        title="Prompt Test",
        plan=plan,
        trace=trace,
        world=scenario.world,
        truth=scenario.ground_truth,
        facts=facts,
        created_at=scenario.ground_truth.incident_time.isoformat(),
        source_style=SourceStyleCatalog().profile_for(plan.document_type),
        document_profile=DocumentProfileCatalog().profile_for(42, "doc_prompt", plan.document_type),
    )
    monkeypatch.setenv("ASSISTCLUEDO_LOCAL_LLM_COMMAND", f"{sys.executable} {script}")
    generated = LocalLLMTextGenerator().generate(request)
    assert generated.provider == "local-llm"
    prompt = json.loads(capture.read_text(encoding="utf-8"))
    grounding = prompt["source_native_grounding"]
    assert grounding["rendered_mandatory_facts"]
    assert "plain_language" in grounding["rendered_mandatory_facts"][0]
    assert "public_entity_labels" in grounding
    assert "knowledge_boundary" in grounding
    assert "public_reference_examples" in grounding


def test_local_llm_content_can_drive_world_and_scenario_texts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    script = tmp_path / "content_llm.py"
    script.write_text(
        """import json, sys
request = json.loads(sys.stdin.read())
if request.get('task') == 'assistcluedo_world_content':
    seed = request['seed']
    json.dump({
      'characters': {
        item['id']: {
          'name': f"LLM {seed} Character {index}",
          'public_role': f"LLM role {index}",
          'description': f"LLM character description {seed}-{index}",
        }
        for index, item in enumerate(request['characters'], start=1)
      },
      'locations': {
        item['id']: {
          'name': f"LLM {seed} Room {index}",
          'description': f"LLM location description {seed}-{index}",
        }
        for index, item in enumerate(request['locations'], start=1)
      },
      'objects': {
        item['id']: {
          'name': f"LLM {seed} Object {index}",
          'description': f"LLM object description {seed}-{index}",
        }
        for index, item in enumerate(request['objects'], start=1)
      },
      'motives': [f"LLM motive {seed} alpha", f"LLM motive {seed} beta", f"LLM motive {seed} gamma"],
    }, sys.stdout)
elif request.get('task') == 'assistcluedo_scenario_texts':
    json.dump({
      'introduction': {
        'title': 'LLM case title',
        'context': 'LLM public case context.',
        'objective': 'LLM objective.',
      },
      'questions': {
        item['id']: {
          'text': 'LLM rewritten ' + item['id'] + ': ' + item['text'],
          'explanation': 'LLM explanation ' + item['id'],
        }
        for item in request['questions']
      },
    }, sys.stdout)
else:
    doc_type = request['document_type']
    if doc_type == 'sms':
        text = 'SMS export\\nFrom: Alex\\nTo: Blake\\nSent: 20:27\\n20:27  Alex: Hi! Are you still there?\\n20:28  Blake: Yes. Keep it quiet.'
    elif doc_type == 'email':
        text = 'From: Alex\\nTo: Blake\\nSubject: Tonight\\nDate: now\\n\\nBlake,\\nWe need to settle this privately.'
    elif doc_type == 'witness interview':
        text = 'Statement ref: WIT-LOCAL | audio quality: usable\\nDetective: What did you notice?\\nWitness: I heard footsteps near the hall.'
    elif doc_type == 'personal note':
        text = '[recovered from desk drawer]\\nI heard voices again tonight. My hands were shaking when I wrote this.'
    elif doc_type in {'access-control log', 'gps report', 'receipt', 'call log'}:
        if doc_type == 'access-control log':
            text = 'timestamp | credential | cardholder | door | result\\n20:27 | LLM-2041 | Alex | Hall | granted'
        elif doc_type == 'gps report':
            text = 'export ref: LOC-LOCAL | source: device cache\\ntimestamp | handset | estimated area | confidence | note\\n20:27 | Alex handset | Hall | medium | local row'
        elif doc_type == 'receipt':
            text = 'receipt no: RCPT-LOCAL | copy: carbon duplicate\\nterminal: service desk\\nline | description | location | clerk\\n01 | signed slip | Hall | desk'
        else:
            text = 'log ref: TEL-LOCAL | exchange clock checked after export\\ntime | extension | party | route note | duration\\n20:27 | house line | Alex | routed near Hall | 00:41'
    elif doc_type == 'inventory report':
        text = 'Sheet ref: INV-LOCAL | second count: pending\\nItem checks:\\n- Object: usual storage listed as Hall. Shelf label slightly torn.'
    elif doc_type == 'autopsy report':
        text = 'Preliminary autopsy note\\nCase ref: ME-LOCAL\\nFindings:\\n- Estimated death window recorded.\\nChain note: worksheet cross-checked.'
    elif doc_type == 'security report':
        text = 'Security maintenance ticket\\nexport ref: SEC-LOCAL | retention: rolling buffer\\nSystem: internal camera network\\nStatus notes:\\n- feed loss recorded.'
    elif doc_type == 'newspaper clipping':
        text = 'Society column clipping\\nPublication: Local LLM Gazette\\nClipping filed: now\\nColumn note: page edge torn\\nGuests were noticed near the hall.'
    else:
        text = 'Preliminary source excerpt\\nObservation recorded in source format.'
    json.dump({
      'title': request['title'],
      'text': text,
      'facts_expressed': request['mandatory_fact_ids'],
      'entities_mentioned': [],
    }, sys.stdout)
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASSISTCLUEDO_LOCAL_LLM_COMMAND", f"{sys.executable} {script}")
    scenario = generate_symbolic_scenario(42, difficulty="easy", max_attempts=1)
    assert all(character.name.startswith("LLM 42 Character") for character in scenario.world.characters)
    assert all(location.name.startswith("LLM 42 Room") for location in scenario.world.locations)
    assert all(obj.name.startswith("LLM 42 Object") for obj in scenario.world.objects)
    assert scenario.ground_truth.motive.startswith("LLM motive 42")
    assert scenario.public_introduction["title"] == "LLM case title"
    assert scenario.questions[0].text.startswith("LLM rewritten q1:")
    assert scenario.documents[0].visible_metadata["text_provider"] == "local-llm"
    assert scenario.content_metadata["world_content_provider"] == "local-llm"


def test_document_validator_checks_metadata_and_creation_time() -> None:
    scenario = generate_symbolic_scenario(42)
    facts_by_id = {fact.id: fact for fact in scenario.facts}
    document = next(
        document
        for document in scenario.documents
        if any(facts_by_id[fact_id].time is not None for fact_id in document.extracted_fact_ids)
    )
    bad_metadata = dict(document.visible_metadata)
    bad_metadata.pop("created_at")
    bad_document = replace(document, visible_metadata=bad_metadata)
    issues = DocumentValidator().validate([bad_document], scenario)
    assert any(issue.code == "document_metadata_missing" for issue in issues)

    bad_metadata["created_at"] = "1900-01-01T00:00:00+00:00"
    bad_document = replace(document, visible_metadata=bad_metadata)
    issues = DocumentValidator().validate([bad_document], scenario)
    assert any(issue.code == "document_created_before_fact" for issue in issues)


def test_document_validator_rejects_visible_internal_ids() -> None:
    scenario = generate_symbolic_scenario(42)
    document = scenario.documents[0]
    bad_document = replace(document, text=f"{document.text}\nraw id: fact_badge_access / dining_room / badge:head_chef")
    issues = DocumentValidator().validate([bad_document], scenario)
    assert any(issue.code == "document_internal_id_leak" for issue in issues)


def test_document_validator_rejects_summary_like_document_text() -> None:
    scenario = generate_symbolic_scenario(42)
    document = next(document for document in scenario.documents if document.visible_metadata["type"] == "email")
    bad_document = replace(
        document,
        text="Subject: Case note\n\nRecords show the culprit had a motive and this indicates responsibility.",
    )
    issues = DocumentValidator().validate([bad_document], scenario)
    assert any(issue.code == "document_source_quality" for issue in issues)


def test_document_validator_checks_plan_trace_truth_mode_alignment() -> None:
    scenario = generate_symbolic_scenario(42)
    plan = scenario.document_plans[0]
    document = next(document for document in scenario.documents if document.plan_id == plan.id)
    bad_plan = replace(plan, truth_mode="deceptive" if plan.truth_mode != "deceptive" else "accurate")
    bad_scenario = replace(scenario, document_plans=[bad_plan, *scenario.document_plans[1:]])
    issues = DocumentValidator().validate([document], bad_scenario)
    assert any(issue.code == "plan_trace_truth_mode_mismatch" for issue in issues)

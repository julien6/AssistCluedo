from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from heapq import heappop, heappush
from itertools import pairwise
from pathlib import Path

from assistcluedo.framework.access import character_can_access_location
from assistcluedo.framework.models import (
    DocumentPlan,
    Fact,
    GeneratedDocument,
    QuizQuestion,
    Scenario,
    Trace,
)
from assistcluedo.framework.serialization import read_json


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    checked: dict[str, int]
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "issues": [issue.__dict__ for issue in self.issues],
        }

    def summary(self) -> str:
        if self.ok:
            counts = ", ".join(f"{key}={value}" for key, value in sorted(self.checked.items()))
            return f"OK: {counts}"
        return f"FAILED: {len(self.issues)} issue(s)"


class DocumentValidator:
    def validate(
        self,
        documents: list[GeneratedDocument],
        scenario: Scenario,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        plans_by_id = {plan.id: plan for plan in scenario.document_plans}
        fact_ids = {fact.id for fact in scenario.facts}
        facts_by_id = {fact.id: fact for fact in scenario.facts}
        traces_by_id = {trace.id: trace for trace in scenario.traces}
        for document in documents:
            if document.plan_id not in plans_by_id:
                issues.append(
                    ValidationIssue("document_unknown_plan", f"{document.id} references {document.plan_id}")
                )
                continue
            if not document.title.strip() or not document.text.strip():
                issues.append(ValidationIssue("document_empty", f"{document.id} has empty title or text"))
            plan = plans_by_id[document.plan_id]
            internal_leaks = _document_internal_id_leaks(document, plan, scenario)
            if internal_leaks:
                issues.append(
                    ValidationIssue(
                        "document_internal_id_leak",
                        f"{document.id} exposes internal ids: {sorted(internal_leaks)}",
                    )
                )
            quality_issues = _document_source_quality_issues(document, plan)
            for issue in quality_issues:
                issues.append(ValidationIssue("document_source_quality", f"{document.id} {issue}"))
            _validate_document_metadata(document, plan, traces_by_id, facts_by_id, issues)
            plan_traces = [traces_by_id[trace_id] for trace_id in plan.source_trace_ids if trace_id in traces_by_id]
            if plan_traces and any(trace.truth_mode != plan.truth_mode for trace in plan_traces):
                issues.append(
                    ValidationIssue("plan_trace_truth_mode_mismatch", f"{plan.id} truth mode does not match source")
                )
            extracted = set(document.extracted_fact_ids)
            for fact_id in extracted:
                if fact_id not in fact_ids:
                    issues.append(ValidationIssue("document_unknown_fact", f"{document.id} extracts {fact_id}"))
            if not set(plan.mandatory_fact_ids) <= extracted:
                issues.append(
                    ValidationIssue("document_missing_mandatory_fact", f"{document.id} omits a mandatory fact")
                )
            leaked = set(plan.forbidden_fact_ids) & extracted
            if leaked:
                issues.append(ValidationIssue("document_forbidden_fact", f"{document.id} leaks {sorted(leaked)}"))
        return issues


def _document_internal_id_leaks(
    document: GeneratedDocument,
    plan: DocumentPlan,
    scenario: Scenario,
) -> set[str]:
    internal_ids = {
        document.id,
        document.plan_id,
        plan.id,
        *plan.source_trace_ids,
        *plan.mandatory_fact_ids,
        *plan.forbidden_fact_ids,
        *[fact.id for fact in scenario.facts],
        *[trace.id for trace in scenario.traces],
        *[character.id for character in scenario.world.characters],
        *[location.id for location in scenario.world.locations],
        *[item.id for item in scenario.world.objects],
    }
    leaks = {
        token
        for token in re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", document.text)
        if token in internal_ids or token.startswith(("fact_", "doc_", "plan_", "trace_"))
    }
    leaks.update(re.findall(r"\bbadge:[a-z][a-z0-9_]*\b", document.text, flags=re.IGNORECASE))
    return leaks


def _document_source_quality_issues(document: GeneratedDocument, plan: DocumentPlan) -> list[str]:
    text = document.text
    lowered = text.lower()
    issues: list[str] = []
    if any(pattern in lowered for pattern in _DOCUMENT_SUMMARY_PATTERNS):
        issues.append("uses investigative-summary phrasing instead of source-native content")
    required_markers = _DOCUMENT_REQUIRED_MARKERS.get(plan.document_type)
    if required_markers and not any(marker in lowered for marker in required_markers):
        issues.append(f"does not look like {plan.document_type}")
    if plan.document_type in {"access-control log", "gps report", "receipt", "call log"} and "|" not in text:
        issues.append("lacks machine/table row structure")
    if plan.document_type == "email" and "subject:" not in lowered:
        issues.append("lacks email subject metadata")
    if plan.document_type == "sms" and not any(marker in lowered for marker in ("sms", "from:", "sent:", "messages", "notification")):
        issues.append("lacks recovered message metadata")
    if len([line for line in text.splitlines() if line.strip()]) < 2:
        issues.append("is too short to support realistic source context")
    return issues


_DOCUMENT_SUMMARY_PATTERNS = (
    "records show ",
    "evidence shows ",
    "the document proves ",
    "this indicates ",
    "the culprit ",
    "investigators learned ",
    "appears near ",
    "appears in a ",
)


_DOCUMENT_REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "sms": ("sms", "notification", "from:", "sent:", "messages"),
    "email": ("from:", "to:", "subject:", "message-id:"),
    "access-control log": ("credential", "cardholder", "controller", "access control"),
    "witness interview": ("detective:", "witness:", "statement ref:", "recorded:"),
    "autopsy report": ("case ref:", "findings", "examiner", "chain note:"),
    "security report": ("export ref:", "system:", "alert id:", "status"),
    "personal note": ("i ", "my ", "me ", "[recovered from"),
    "inventory report": ("sheet ref:", "item checks:", "inventory"),
    "gps report": ("export ref:", "confidence", "handset"),
    "receipt": ("receipt", "terminal:", "clerk", "counterfoil"),
    "call log": ("log ref:", "switchboard:", "duration", "extension"),
    "newspaper clipping": ("publication:", "clipping filed:", "column note:"),
}


def _validate_document_metadata(
    document: GeneratedDocument,
    plan: DocumentPlan,
    traces_by_id: dict[str, Trace],
    facts_by_id: dict[str, Fact],
    issues: list[ValidationIssue],
) -> None:
    metadata = document.visible_metadata
    required_keys = {"type", "reliability", "source", "created_at", "text_provider", "fallback_used"}
    missing = sorted(required_keys - set(metadata))
    if missing:
        issues.append(ValidationIssue("document_metadata_missing", f"{document.id} missing metadata: {missing}"))
    if metadata.get("type") != plan.document_type:
        issues.append(ValidationIssue("document_type_mismatch", f"{document.id} type does not match {plan.id}"))
    if not isinstance(metadata.get("text_provider"), str):
        issues.append(ValidationIssue("document_missing_text_provider", f"{document.id} has no text provider"))
    if not isinstance(metadata.get("fallback_used"), bool):
        issues.append(ValidationIssue("document_invalid_fallback_flag", f"{document.id} has invalid fallback flag"))
    source_traces = [traces_by_id[trace_id] for trace_id in plan.source_trace_ids if trace_id in traces_by_id]
    if source_traces:
        reliability = metadata.get("reliability")
        if not isinstance(reliability, (int, float)):
            issues.append(ValidationIssue("document_invalid_reliability", f"{document.id} has invalid reliability"))
        elif any(float(reliability) != trace.reliability for trace in source_traces):
            issues.append(
                ValidationIssue("document_reliability_mismatch", f"{document.id} reliability does not match source")
            )
    created_at = metadata.get("created_at")
    if not isinstance(created_at, str):
        issues.append(ValidationIssue("document_missing_created_at", f"{document.id} has no creation timestamp"))
        return
    try:
        created_time = datetime.fromisoformat(created_at)
    except ValueError:
        issues.append(ValidationIssue("document_invalid_created_at", f"{document.id} has invalid creation timestamp"))
        return
    mandatory_fact_times: list[datetime] = []
    for fact_id in plan.mandatory_fact_ids:
        if fact_id not in facts_by_id:
            continue
        fact_time = facts_by_id[fact_id].time
        if fact_time is not None:
            mandatory_fact_times.append(fact_time)
    if mandatory_fact_times and created_time < max(mandatory_fact_times):
        issues.append(ValidationIssue("document_created_before_fact", f"{document.id} predates its evidence"))


class QuestionValidator:
    def validate(
        self,
        questions: list[QuizQuestion],
        scenario: Scenario,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        fact_ids = {fact.id for fact in scenario.facts}
        documents_by_id = {document.id: document for document in scenario.documents}
        proof_document_ids = {
            document_id
            for link in scenario.proof_graph.links
            for document_id in link.document_ids
        }
        derived_fact_ids = {"fact_culprit_identity", "fact_murder_location"}
        for question in questions:
            choice_ids = {choice.id for choice in question.choices}
            choice_texts = [choice.text for choice in question.choices]
            if len(question.correct_choice_ids) != 1:
                issues.append(ValidationIssue("question_answer_count", f"{question.id} must have one correct answer"))
            for choice_id in question.correct_choice_ids:
                if choice_id not in choice_ids:
                    issues.append(ValidationIssue("question_unknown_choice", f"{question.id} answer {choice_id} missing"))
            if len(choice_texts) != len(set(choice_texts)):
                issues.append(ValidationIssue("question_duplicate_choice_text", f"{question.id} has duplicate choices"))
            if any(not text.strip() for text in choice_texts):
                issues.append(ValidationIssue("question_empty_choice_text", f"{question.id} has an empty choice"))
            if len(question.choices) < 2:
                issues.append(ValidationIssue("question_too_few_choices", f"{question.id} has too few choices"))
            if not question.explanation.strip():
                issues.append(ValidationIssue("question_missing_explanation", f"{question.id} has no explanation"))
            for fact_id in question.supporting_fact_ids:
                if fact_id not in fact_ids:
                    issues.append(ValidationIssue("question_unknown_fact", f"{question.id} references {fact_id}"))
            if not question.supporting_document_ids:
                issues.append(
                    ValidationIssue("question_without_document_support", f"{question.id} has no document support")
                )
            for document_id in question.supporting_document_ids:
                if document_id not in documents_by_id:
                    issues.append(
                        ValidationIssue("question_unknown_document", f"{question.id} references {document_id}")
                    )
            supported_fact_ids = {
                fact_id
                for document_id in question.supporting_document_ids
                if document_id in documents_by_id
                for fact_id in documents_by_id[document_id].extracted_fact_ids
            }
            unsupported = set(question.supporting_fact_ids) - supported_fact_ids - derived_fact_ids
            if unsupported:
                issues.append(
                    ValidationIssue(
                        "question_fact_not_in_support_documents",
                        f"{question.id} facts not supported by listed documents: {sorted(unsupported)}",
                    )
                )
            if not (
                set(question.supporting_document_ids) & proof_document_ids
                or set(question.supporting_fact_ids) <= supported_fact_ids
            ):
                issues.append(
                    ValidationIssue(
                        "question_without_proof_path",
                        f"{question.id} has no proof-linked document support",
                    )
                )
        return issues


class ScenarioValidator:
    def validate(self, scenario: Scenario) -> ValidationReport:
        issues: list[ValidationIssue] = []
        self._world_references(scenario, issues)
        self._devices(scenario, issues)
        self._travel_graph(scenario, issues)
        self._timeline_constraints(scenario, issues)
        self._trace_references(scenario, issues)
        self._document_plans(scenario, issues)
        self._documents(scenario, issues)
        self._proof_graph(scenario, issues)
        self._quiz(scenario, issues)
        self._player_package_safety(scenario, issues)
        checked = {
            "characters": len(scenario.world.characters),
            "locations": len(scenario.world.locations),
            "objects": len(scenario.world.objects),
            "events": len(scenario.events),
            "facts": len(scenario.facts),
            "traces": len(scenario.traces),
            "document_plans": len(scenario.document_plans),
            "documents": len(scenario.documents),
            "questions": len(scenario.questions),
            "proof_links": len(scenario.proof_graph.links),
        }
        return ValidationReport(ok=not issues, checked=checked, issues=issues)

    def _issue(self, issues: list[ValidationIssue], code: str, message: str) -> None:
        issues.append(ValidationIssue(code, message))

    def _world_references(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        character_ids = {char.id for char in scenario.world.characters}
        location_ids = {loc.id for loc in scenario.world.locations}
        object_ids = {obj.id for obj in scenario.world.objects}
        truth = scenario.ground_truth
        for char_id, label in [(truth.culprit_id, "culprit"), (truth.victim_id, "victim")]:
            if char_id not in character_ids:
                self._issue(issues, "unknown_truth_character", f"Unknown {label}: {char_id}")
        if truth.location_id not in location_ids:
            self._issue(issues, "unknown_truth_location", f"Unknown incident location: {truth.location_id}")
        if truth.weapon_id not in object_ids:
            self._issue(issues, "unknown_truth_object", f"Unknown weapon: {truth.weapon_id}")
        for obj in scenario.world.objects:
            if obj.location_id is not None and obj.location_id not in location_ids:
                self._issue(issues, "unknown_object_location", f"{obj.id} at unknown location {obj.location_id}")
            if obj.owner_id is not None and obj.owner_id not in character_ids:
                self._issue(issues, "unknown_object_owner", f"{obj.id} has unknown owner {obj.owner_id}")
        for relationship in scenario.world.relationships:
            if relationship.source_character_id not in character_ids:
                self._issue(issues, "unknown_relationship_source", f"{relationship.id} has unknown source")
            if relationship.target_character_id not in character_ids:
                self._issue(issues, "unknown_relationship_target", f"{relationship.id} has unknown target")

    def _devices(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        location_ids = {loc.id for loc in scenario.world.locations}
        character_ids = {char.id for char in scenario.world.characters}
        for device in scenario.world.devices:
            if device.location_id not in location_ids:
                self._issue(issues, "unknown_device_location", f"{device.id} at unknown location {device.location_id}")
            if device.owner_character_id is not None and device.owner_character_id not in character_ids:
                self._issue(issues, "unknown_device_owner", f"{device.id} has unknown owner {device.owner_character_id}")

    def _travel_graph(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        location_ids = {loc.id for loc in scenario.world.locations}
        adjacency: dict[str, set[str]] = {location_id: set() for location_id in location_ids}
        for edge in scenario.world.travel_edges:
            if edge.source_location_id not in location_ids:
                self._issue(issues, "travel_unknown_source", f"Unknown travel source {edge.source_location_id}")
                continue
            if edge.target_location_id not in location_ids:
                self._issue(issues, "travel_unknown_target", f"Unknown travel target {edge.target_location_id}")
                continue
            if edge.travel_minutes < 0:
                self._issue(issues, "travel_negative_duration", f"Negative travel time on {edge}")
            adjacency[edge.source_location_id].add(edge.target_location_id)
        if not location_ids:
            self._issue(issues, "travel_no_locations", "World has no locations")
            return
        start = next(iter(location_ids))
        seen = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        if seen != location_ids:
            missing = sorted(location_ids - seen)
            self._issue(issues, "travel_graph_disconnected", f"Unreachable locations: {missing}")

    def _timeline_constraints(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        character_ids = {char.id for char in scenario.world.characters}
        location_ids = {loc.id for loc in scenario.world.locations}
        object_ids = {obj.id for obj in scenario.world.objects}
        characters_by_id = {char.id: char for char in scenario.world.characters}
        locations_by_id = {loc.id: loc for loc in scenario.world.locations}
        occupied: dict[tuple[str, datetime], str | None] = {}
        travel_minutes = _shortest_travel_minutes(scenario)
        per_actor_events: dict[str, list[tuple[datetime, str]]] = {}
        previous_time = None
        for event in scenario.events:
            if previous_time is not None and event.start_time < previous_time:
                self._issue(issues, "timeline_not_sorted", f"{event.id} is out of order")
            previous_time = event.start_time
            if event.end_time is not None and event.end_time < event.start_time:
                self._issue(issues, "event_negative_duration", f"{event.id} ends before it starts")
            for char_id in event.actor_ids + event.target_ids:
                if char_id not in character_ids:
                    self._issue(issues, "event_unknown_character", f"{event.id} references {char_id}")
            if event.location_id is not None and event.location_id not in location_ids:
                self._issue(issues, "event_unknown_location", f"{event.id} references {event.location_id}")
            for object_id in event.object_ids:
                if object_id not in object_ids:
                    self._issue(issues, "event_unknown_object", f"{event.id} references {object_id}")
            for actor_id in event.actor_ids:
                if event.location_id is not None and actor_id in characters_by_id:
                    location = locations_by_id.get(event.location_id)
                    if location is not None and not character_can_access_location(characters_by_id[actor_id], location):
                        self._issue(
                            issues,
                            "actor_location_access_denied",
                            f"{actor_id} cannot access {event.location_id} for {event.id}",
                        )
                key = (actor_id, event.start_time)
                if key in occupied and occupied[key] != event.location_id:
                    self._issue(
                        issues,
                        "actor_double_booked",
                        f"{actor_id} is in two locations at {event.start_time.isoformat()}",
                    )
                occupied[key] = event.location_id
                if event.location_id is not None:
                    per_actor_events.setdefault(actor_id, []).append((event.start_time, event.location_id))
        for actor_id, located_events in per_actor_events.items():
            located_events.sort(key=lambda item: item[0])
            for (previous_at, previous_location), (current_at, current_location) in pairwise(located_events):
                if previous_location == current_location:
                    continue
                required_minutes = travel_minutes.get((previous_location, current_location))
                if required_minutes is None:
                    self._issue(
                        issues,
                        "travel_missing_edge",
                        f"No route for {actor_id}: {previous_location} -> {current_location}",
                    )
                    continue
                actual_minutes = (current_at - previous_at).total_seconds() / 60
                if actual_minutes < required_minutes:
                    self._issue(
                        issues,
                        "travel_time_violation",
                        f"{actor_id} needs {required_minutes} min from {previous_location} to {current_location}, has {actual_minutes:.1f}",
                    )
        truth = scenario.ground_truth
        culprit = characters_by_id.get(truth.culprit_id)
        weapon = next((obj for obj in scenario.world.objects if obj.id == truth.weapon_id), None)
        weapon_location = locations_by_id.get(weapon.location_id) if weapon and weapon.location_id else None
        if culprit and weapon_location and not character_can_access_location(culprit, weapon_location):
            self._issue(
                issues,
                "weapon_access_denied",
                f"{truth.culprit_id} cannot access weapon location {weapon_location.id}",
            )
        incident = next((event for event in scenario.events if event.event_type == "main_incident"), None)
        discovery = next((event for event in scenario.events if event.event_type == "discover_body"), None)
        if incident is None:
            self._issue(issues, "missing_main_incident", "Timeline has no main incident")
        if discovery is None:
            self._issue(issues, "missing_discovery", "Timeline has no discovery event")
        if incident and discovery and discovery.start_time <= incident.start_time:
            self._issue(issues, "discovery_before_incident", "Discovery is not after the incident")
        hide_event = next((event for event in scenario.events if event.event_type == "hide_evidence"), None)
        truth = scenario.ground_truth
        weapon = next((obj for obj in scenario.world.objects if obj.id == truth.weapon_id), None)
        if weapon and weapon.location_id != truth.location_id:
            self._issue(
                issues,
                "weapon_not_initially_at_incident_location",
                f"{truth.weapon_id} starts at {weapon.location_id}, incident is at {truth.location_id}",
            )
        if incident and truth.weapon_id not in incident.object_ids:
            self._issue(issues, "incident_missing_weapon", f"{incident.id} does not use {truth.weapon_id}")
        if hide_event is None:
            self._issue(issues, "missing_hide_evidence", "Timeline has no hide_evidence event")
        elif truth.weapon_id not in hide_event.object_ids:
            self._issue(issues, "hide_evidence_missing_weapon", f"{hide_event.id} does not hide {truth.weapon_id}")
        elif incident and hide_event.start_time <= incident.start_time:
            self._issue(issues, "hide_before_incident", "Weapon is hidden before the incident")

    def _trace_references(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        fact_ids = {fact.id for fact in scenario.facts}
        event_ids = {event.id for event in scenario.events}
        for trace in scenario.traces:
            if not trace.source_event_ids:
                self._issue(issues, "trace_without_event", f"{trace.id} has no source event")
            for event_id in trace.source_event_ids:
                if event_id not in event_ids:
                    self._issue(issues, "trace_unknown_event", f"{trace.id} references {event_id}")
            for fact_id in trace.fact_ids:
                if fact_id not in fact_ids:
                    self._issue(issues, "trace_unknown_fact", f"{trace.id} references {fact_id}")
            if not 0 <= trace.reliability <= 1 or not 0 <= trace.authenticity <= 1:
                self._issue(issues, "trace_invalid_score", f"{trace.id} reliability/authenticity out of range")

    def _document_plans(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        trace_ids = {trace.id for trace in scenario.traces}
        fact_ids = {fact.id for fact in scenario.facts}
        location_ids = {loc.id for loc in scenario.world.locations}
        device_ids = {device.id for device in scenario.world.devices}
        character_ids = {char.id for char in scenario.world.characters}
        for plan in scenario.document_plans:
            if not plan.source_trace_ids:
                self._issue(issues, "plan_without_trace", f"{plan.id} has no trace")
            for trace_id in plan.source_trace_ids:
                if trace_id not in trace_ids:
                    self._issue(issues, "plan_unknown_trace", f"{plan.id} references {trace_id}")
            for fact_id in plan.mandatory_fact_ids + plan.forbidden_fact_ids:
                if fact_id not in fact_ids:
                    self._issue(issues, "plan_unknown_fact", f"{plan.id} references {fact_id}")
            if not plan.retrieval_location_id:
                self._issue(issues, "plan_without_retrieval_location", f"{plan.id} has no retrieval location")
            elif plan.retrieval_location_id not in location_ids:
                self._issue(
                    issues,
                    "plan_unknown_retrieval_location",
                    f"{plan.id} references unknown location {plan.retrieval_location_id}",
                )
            if plan.source_device_id is not None and plan.source_device_id not in device_ids:
                self._issue(issues, "plan_unknown_device", f"{plan.id} references unknown device {plan.source_device_id}")
            if plan.witness_character_id is not None and plan.witness_character_id not in character_ids:
                self._issue(
                    issues,
                    "plan_unknown_witness",
                    f"{plan.id} references unknown witness {plan.witness_character_id}",
                )
            if plan.source_device_id is not None and plan.witness_character_id is not None:
                self._issue(
                    issues,
                    "plan_ambiguous_source",
                    f"{plan.id} has both a device and a witness source",
                )

    def _documents(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        issues.extend(DocumentValidator().validate(scenario.documents, scenario))

    def _proof_graph(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        fact_ids = {fact.id for fact in scenario.facts}
        document_ids = {document.id for document in scenario.documents}
        for link in scenario.proof_graph.links:
            if not link.fact_ids or not link.document_ids:
                self._issue(issues, "proof_link_incomplete", f"{link.conclusion} has no support")
            for fact_id in link.fact_ids:
                if fact_id not in fact_ids:
                    self._issue(issues, "proof_unknown_fact", f"{link.conclusion} references {fact_id}")
            for document_id in link.document_ids:
                if document_id not in document_ids:
                    self._issue(issues, "proof_unknown_document", f"{link.conclusion} references {document_id}")

    def _quiz(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        issues.extend(QuestionValidator().validate(scenario.questions, scenario))

    def _player_package_safety(self, scenario: Scenario, issues: list[ValidationIssue]) -> None:
        forbidden_fact_ids = {"fact_culprit_identity"}
        for document in scenario.documents:
            leaked = forbidden_fact_ids & set(document.extracted_fact_ids)
            if leaked:
                self._issue(issues, "player_document_oracle_leak", f"{document.id} exposes {sorted(leaked)}")


def validate_scenario(scenario: Scenario) -> ValidationReport:
    return ScenarioValidator().validate(scenario)


def _shortest_travel_minutes(scenario: Scenario) -> dict[tuple[str, str], int]:
    location_ids = {loc.id for loc in scenario.world.locations}
    graph: dict[str, list[tuple[str, int]]] = {location_id: [] for location_id in location_ids}
    for edge in scenario.world.travel_edges:
        if edge.source_location_id in location_ids and edge.target_location_id in location_ids:
            graph[edge.source_location_id].append((edge.target_location_id, edge.travel_minutes))
    distances: dict[tuple[str, str], int] = {}
    for source in location_ids:
        queue: list[tuple[int, str]] = [(0, source)]
        best = {source: 0}
        while queue:
            current_distance, current = heappop(queue)
            if current_distance != best[current]:
                continue
            for target, minutes in graph[current]:
                next_distance = current_distance + minutes
                if target not in best or next_distance < best[target]:
                    best[target] = next_distance
                    heappush(queue, (next_distance, target))
        for target, minutes in best.items():
            distances[(source, target)] = minutes
    return distances


def validate_export(path: Path) -> ValidationReport:
    issues: list[ValidationIssue] = []
    required = [
        "scenario.json",
        "metadata.json",
        "seeds.json",
        "config_snapshot.yaml",
        "ontology_snapshot.yaml",
        "player_package/introduction.json",
        "player_package/characters.json",
        "player_package/locations.json",
        "player_package/quiz.json",
        "evaluation/answer_key.json",
        "evaluation/explanations.json",
        "evaluation/scoring_config.yaml",
    ]
    for relative in required:
        if not (path / relative).exists():
            issues.append(ValidationIssue("export_missing_file", f"Missing {relative}"))
    document_dir = path / "player_package" / "documents"
    document_count = len(list(document_dir.glob("*.json"))) if document_dir.exists() else 0
    plan_count = len(list((path / "document_plans").glob("*.json"))) if (path / "document_plans").exists() else 0
    generated_count = (
        len(list((path / "generated_documents").glob("*.json")))
        if (path / "generated_documents").exists()
        else 0
    )
    if document_count == 0:
        issues.append(ValidationIssue("export_no_player_documents", "No player documents exported"))
    if plan_count != generated_count or generated_count != document_count:
        issues.append(
            ValidationIssue(
                "export_document_count_mismatch",
                f"plans={plan_count}, generated={generated_count}, player={document_count}",
            )
        )
    try:
        metadata = read_json(path / "metadata.json")
        quiz = read_json(path / "player_package" / "quiz.json")
        answer_key = read_json(path / "evaluation" / "answer_key.json")
    except (FileNotFoundError, ValueError) as exc:
        issues.append(ValidationIssue("export_unreadable_json", str(exc)))
        metadata = {}
        quiz = []
        answer_key = {}
    question_ids = {str(question.get("id")) for question in quiz if isinstance(question, dict)}
    if set(answer_key) != question_ids:
        issues.append(ValidationIssue("export_answer_key_mismatch", "Answer key does not match quiz"))
    _validate_player_package_files(path, issues)
    try:
        scenario = Scenario.from_dict(read_json(path / "scenario.json"))
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        issues.append(ValidationIssue("export_unreadable_scenario", str(exc)))
    else:
        scenario_report = validate_scenario(scenario)
        for issue in scenario_report.issues:
            issues.append(ValidationIssue(f"scenario_{issue.code}", issue.message))
    checked = {
        "documents": document_count,
        "document_plans": plan_count,
        "generated_documents": generated_count,
        "questions": len(question_ids),
        "metadata_fields": len(metadata),
    }
    return ValidationReport(ok=not issues, checked=checked, issues=issues)


def _validate_player_package_files(path: Path, issues: list[ValidationIssue]) -> None:
    forbidden_keys = {
        "correct_choice_ids",
        "supporting_fact_ids",
        "supporting_document_ids",
        "explanation",
        "extracted_fact_ids",
        "plan_id",
        "source_trace_ids",
        "mandatory_fact_ids",
        "forbidden_fact_ids",
        "ground_truth",
        "proof_graph",
        "private_role",
        "relationship_ids",
    }
    player_root = path / "player_package"
    if not player_root.exists():
        issues.append(ValidationIssue("player_package_missing", "Missing player_package directory"))
        return
    if (player_root / "oracle").exists():
        issues.append(ValidationIssue("player_package_oracle_directory", "Oracle directory exists in player package"))
    for json_path in sorted(player_root.rglob("*.json")):
        try:
            data = read_json(json_path)
        except (FileNotFoundError, ValueError) as exc:
            issues.append(ValidationIssue("player_package_unreadable_json", f"{json_path}: {exc}"))
            continue
        leaked = sorted(_find_forbidden_keys(data, forbidden_keys))
        if leaked:
            relative = json_path.relative_to(path)
            issues.append(
                ValidationIssue(
                    "player_package_forbidden_key",
                    f"{relative} contains forbidden key(s): {', '.join(leaked)}",
                )
            )


def _find_forbidden_keys(data: object, forbidden_keys: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key) in forbidden_keys:
                found.add(str(key))
            found.update(_find_forbidden_keys(value, forbidden_keys))
    elif isinstance(data, list):
        for item in data:
            found.update(_find_forbidden_keys(item, forbidden_keys))
    return found

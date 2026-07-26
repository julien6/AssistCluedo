from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

from assistcluedo.framework.models import DocumentPlan, Fact, GroundTruth, Trace, World
from assistcluedo.framework.naming import entity_name


@dataclass(frozen=True)
class SourceStyle:
    structure: str
    register: str
    realism_guidance: str
    forbidden_behavior: str
    target_length: str


@dataclass(frozen=True)
class TextGenerationRequest:
    document_id: str
    title: str
    plan: DocumentPlan
    trace: Trace
    world: World
    truth: GroundTruth
    facts: list[Fact]
    created_at: str
    source_style: SourceStyle


@dataclass(frozen=True)
class TextGenerationResult:
    title: str
    text: str
    facts_expressed: list[str]
    entities_mentioned: list[str]
    provider: str
    attempts: int = 1
    fallback_used: bool = False


class TextGenerator(Protocol):
    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        ...


class SourceStyleCatalog:
    def profile_for(self, document_type: str) -> SourceStyle:
        profiles = _SOURCE_STYLES
        return profiles.get(
            document_type,
            SourceStyle(
                structure="short investigative file note",
                register="plain administrative",
                realism_guidance="Write as a compact record from an evidence bundle.",
                forbidden_behavior="Do not identify the culprit or infer intent beyond listed facts.",
                target_length="2-4 sentences",
            ),
        )


class TemplateTextGenerator:
    provider = "template"

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        facts = {fact.id: fact for fact in request.facts}
        lines = _template_lines(request, facts)
        entities = _entities_for(request.world, request.facts)
        return TextGenerationResult(
            title=request.title,
            text="\n".join(lines),
            facts_expressed=list(request.plan.mandatory_fact_ids),
            entities_mentioned=entities,
            provider=self.provider,
        )


class MockTextGenerator:
    provider = "mock"

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        return TextGenerationResult(
            title=request.title,
            text=f"[mock {request.document_id}] {'; '.join(request.plan.mandatory_fact_ids)}",
            facts_expressed=list(request.plan.mandatory_fact_ids),
            entities_mentioned=[],
            provider=self.provider,
        )


class OpenAITextGenerator:
    provider = "openai"

    def __init__(self, model: str = "gpt-5-mini") -> None:
        self.model = model

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        try:
            from openai import OpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Install the optional 'openai' package to use --provider openai.") from exc
        client = OpenAI()
        response = client.responses.create(  # pragma: no cover - network/provider dependent
            model=self.model,
            input=_llm_prompt(request),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "assistcluedo_document",
                    "schema": _RESULT_SCHEMA,
                    "strict": True,
                }
            },
        )
        return _result_from_json(response.output_text, self.provider)


class LocalLLMTextGenerator:
    provider = "local-llm"

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("ASSISTCLUEDO_LOCAL_LLM_COMMAND")

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        command = self.command
        if command is None:
            raise RuntimeError("Set ASSISTCLUEDO_LOCAL_LLM_COMMAND to use --provider local-llm.")
        completed = subprocess.run(
            command,
            input=_llm_prompt(request),
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        return _result_from_json(completed.stdout, self.provider)


class FallbackTextGenerator:
    def __init__(self, primary: TextGenerator, fallback: TextGenerator, max_attempts: int = 1) -> None:
        self.primary = primary
        self.fallback = fallback
        self.max_attempts = max_attempts

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.primary.generate(request)
                validate_text_generation_result(request, result)
                return TextGenerationResult(
                    title=result.title,
                    text=result.text,
                    facts_expressed=result.facts_expressed,
                    entities_mentioned=result.entities_mentioned,
                    provider=result.provider,
                    attempts=attempt,
                    fallback_used=False,
                )
            except (RuntimeError, ValueError, subprocess.CalledProcessError):
                pass
        fallback = self.fallback.generate(request)
        validate_text_generation_result(request, fallback)
        return TextGenerationResult(
            title=fallback.title,
            text=fallback.text,
            facts_expressed=fallback.facts_expressed,
            entities_mentioned=fallback.entities_mentioned,
            provider=fallback.provider,
            attempts=self.max_attempts,
            fallback_used=True,
        )


def generator_for(provider: str = "local-llm", fallback: str = "template", max_attempts: int = 1, model: str = "gpt-5-mini") -> TextGenerator:
    primary = _base_generator(provider, model)
    if provider in {"template", "mock"}:
        return primary
    return FallbackTextGenerator(primary, _base_generator(fallback, model), max_attempts=max_attempts)


def validate_text_generation_result(request: TextGenerationRequest, result: TextGenerationResult) -> None:
    if not result.title.strip() or not result.text.strip():
        raise ValueError("Generated document must have a non-empty title and text.")
    expressed = set(result.facts_expressed)
    mandatory = set(request.plan.mandatory_fact_ids)
    forbidden = set(request.plan.forbidden_fact_ids)
    if not mandatory <= expressed:
        raise ValueError(f"Missing mandatory fact(s): {sorted(mandatory - expressed)}")
    if forbidden & expressed:
        raise ValueError(f"Forbidden fact(s) expressed: {sorted(forbidden & expressed)}")
    known_entities = {item.id for group in (request.world.characters, request.world.locations, request.world.objects) for item in group}
    unknown_entities = set(result.entities_mentioned) - known_entities
    if unknown_entities:
        raise ValueError(f"Unknown entities mentioned: {sorted(unknown_entities)}")


def _base_generator(provider: str, model: str) -> TextGenerator:
    if provider == "template":
        return TemplateTextGenerator()
    if provider == "mock":
        return MockTextGenerator()
    if provider == "openai":
        return OpenAITextGenerator(model=model)
    if provider == "local-llm":
        return LocalLLMTextGenerator()
    raise ValueError(f"Unknown text generation provider: {provider}")


def _template_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    document_type = request.plan.document_type
    if document_type == "sms":
        return _sms_lines(request, facts)
    if document_type == "email":
        return _email_lines(request, facts)
    if document_type == "access-control log":
        return _access_log_lines(request, facts)
    if document_type == "witness interview":
        return _witness_lines(request, facts)
    if document_type == "autopsy report":
        return _autopsy_lines(request, facts)
    if document_type == "security report":
        return _security_lines(request, facts)
    if document_type == "personal note":
        return _personal_note_lines(request, facts)
    if document_type == "inventory report":
        return _inventory_lines(request, facts)
    if document_type == "gps report":
        return _gps_lines(request, facts)
    if document_type == "receipt":
        return _receipt_lines(request, facts)
    if document_type == "call log":
        return _call_log_lines(request, facts)
    if document_type == "newspaper clipping":
        return _newspaper_lines(request, facts)
    return _generic_lines(request, facts)


def _sms_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    fact = facts.get("fact_sms_meeting")
    if fact:
        sender = entity_name(request.world, fact.subject)
        recipient = entity_name(request.world, str(fact.object))
        time = _time(fact)
        return [
            f"From: {sender}",
            f"To: {recipient}",
            f"Sent: {time}",
            '"Can we talk before everyone starts asking questions? Not in the dining room. Same quiet place as before."',
        ]
    return _generic_lines(request, facts)


def _email_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    fact = facts.get("fact_motive")
    if fact:
        sender = entity_name(request.world, fact.subject)
        return [
            f"From: {sender}",
            "Subject: The matter you promised to settle",
            "",
            "I have kept this out of the household gossip for longer than I should have.",
            f"The records point to the same pressure again: {fact.object}.",
            "Do not mistake my silence for agreement.",
        ]
    return _generic_lines(request, facts)


def _access_log_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["ACCESS CONTROL EXPORT", "timestamp | credential | door | result"]
    for fact in request.facts:
        if fact.id == "fact_badge_access":
            rows.append(
                f"{_time(fact)} | badge:{fact.subject} | {entity_name(request.world, str(fact.object))} | granted"
            )
    return rows


def _witness_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Witness interview transcript", "Detective: Please describe only what you personally observed."]
    for fact in request.facts:
        if fact.id == "fact_exculpated_alibi":
            rows.append(
                f"Witness: I saw {entity_name(request.world, fact.subject)} in {entity_name(request.world, str(fact.object))} around {_time(fact)}. They looked hurried, but they were not near the incident room."
            )
        elif fact.id == "fact_false_statement":
            rows.append(
                f"Witness: {entity_name(request.world, fact.subject)} insisted they had not gone near {entity_name(request.world, request.truth.location_id)} after dinner. That answer did not sit comfortably with the access records."
            )
        elif fact.id == "fact_witness_seen_culprit":
            rows.append(
                f"Witness: I noticed {entity_name(request.world, fact.subject)} leaving the corridor outside {entity_name(request.world, request.truth.location_id)} at about {_time(fact)}."
            )
    return rows if len(rows) > 2 else _generic_lines(request, facts)


def _autopsy_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Preliminary autopsy note", "Examiner observations:"]
    for fact in request.facts:
        if fact.id == "fact_death_window":
            rows.append(f"- Estimated death window: {fact.object}.")
        elif fact.id == "fact_murder_weapon":
            rows.append(f"- Wound pattern is consistent with a heavy object such as the {entity_name(request.world, str(fact.object))}.")
    rows.append("These findings describe physical consistency, not legal responsibility.")
    return rows


def _security_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Security maintenance report", f"Created: {request.created_at}"]
    for fact in request.facts:
        if fact.id == "fact_camera_disabled":
            rows.append(
                f"The camera covering {entity_name(request.world, request.truth.location_id)} was unavailable from {_time(fact)}. No direct footage exists for that interval."
            )
    return rows if len(rows) > 2 else _generic_lines(request, facts)


def _personal_note_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Personal note recovered from a private desk:"]
    for fact in request.facts:
        if fact.id == "fact_false_lead_argument":
            rows.append(
                f"{entity_name(request.world, fact.subject)} was arguing with {entity_name(request.world, str(fact.object))} again. Money, pride, old promises; it sounded ugly enough for half the house to notice."
            )
    return rows if len(rows) > 1 else _generic_lines(request, facts)


def _inventory_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Household inventory exception report"]
    for fact in request.facts:
        if fact.id == "fact_weapon_initial_location":
            rows.append(f"- Usual storage: {entity_name(request.world, fact.subject)} in {entity_name(request.world, str(fact.object))}.")
        elif fact.id == "fact_weapon_hidden":
            rows.append(f"- Recovery note: {entity_name(request.world, fact.subject)} later found hidden in {entity_name(request.world, str(fact.object))}.")
    return rows


def _gps_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    return _contextual_report_lines(request, "GPS proximity export", "phone location estimate")


def _receipt_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    return _contextual_report_lines(request, "Receipt record", "point-of-sale note")


def _call_log_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    return _contextual_report_lines(request, "Call log extract", "telephony record")


def _newspaper_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    return _contextual_report_lines(request, "Local newspaper clipping", "background mention")


def _contextual_report_lines(request: TextGenerationRequest, heading: str, label: str) -> list[str]:
    rows = [heading]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            action = fact.predicate.removeprefix("context_").replace("_", " ")
            rows.append(
                f"A {label} places {entity_name(request.world, fact.subject)} near {entity_name(request.world, str(fact.object))} at {_time(fact)} ({action})."
            )
    return rows if len(rows) > 1 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _generic_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = [request.source_style.structure.title()]
    for fact in request.facts:
        rows.append(_fact_sentence(request.world, fact, request.truth))
    return rows


def _fact_sentence(world: World, fact: Fact, truth: GroundTruth) -> str:
    t = f" at {_time(fact)}" if fact.time else ""
    if fact.id == "fact_badge_access":
        return f"The badge assigned to {entity_name(world, fact.subject)} opened {entity_name(world, str(fact.object))}{t}."
    if fact.id == "fact_camera_disabled":
        return f"The camera covering {entity_name(world, truth.location_id)} was unavailable starting{t}."
    if fact.id == "fact_death_window":
        return f"The medical estimate puts death in the window {fact.object}."
    if fact.id.startswith("fact_ev_ctx_"):
        return f"{entity_name(world, fact.subject)} appears near {entity_name(world, str(fact.object))}{t}."
    return f"{entity_name(world, fact.subject)} {fact.predicate.replace('_', ' ')} {entity_name(world, str(fact.object))}."


def _time(fact: Fact) -> str:
    return f"{fact.time:%H:%M}" if fact.time else "time not recorded"


def _entities_for(world: World, facts: list[Fact]) -> list[str]:
    known = {item.id for group in (world.characters, world.locations, world.objects) for item in group}
    mentioned: list[str] = []
    for fact in facts:
        for value in (fact.subject, str(fact.object), fact.location_id):
            if value is not None and value in known and value not in mentioned:
                mentioned.append(value)
    return mentioned


def _llm_prompt(request: TextGenerationRequest) -> str:
    payload = {
        "role": "You are the style layer for AssistCluedo evidence documents.",
        "core_philosophy": [
            "The symbolic facts below are the only source of truth.",
            "Your job is to make the document feel realistic for its source, not to decide what happened.",
            "Use everyday texture, institutional formatting, hesitation, omission, or terse system language as appropriate.",
            "Never add a new suspect, location, object, event, time, motive, relationship, confession, or conclusion.",
            "Never identify the culprit unless a mandatory fact explicitly says so.",
            "Do not expose internal IDs in the document text; IDs may appear only in facts_expressed and entities_mentioned.",
            "Return JSON only, with no markdown and no surrounding commentary.",
        ],
        "source_realism_contract": {
            "structure": request.source_style.structure,
            "register": request.source_style.register,
            "guidance": request.source_style.realism_guidance,
            "forbidden_behavior": request.source_style.forbidden_behavior,
            "target_length": request.source_style.target_length,
        },
        "output_rules": {
            "title": "Use the supplied title unless the source format naturally requires a tiny variation.",
            "text": "Naturalistic source text only. No analysis of the case. No hidden oracle summary.",
            "facts_expressed": "Must include every mandatory_fact_id and no forbidden_fact_id.",
            "entities_mentioned": "Known entity IDs mentioned in the text, not names, and no unknown IDs.",
        },
        "document_id": request.document_id,
        "title": request.title,
        "document_type": request.plan.document_type,
        "created_at": request.created_at,
        "source_style": request.source_style.__dict__,
        "truth_mode": request.plan.truth_mode,
        "mandatory_fact_ids": request.plan.mandatory_fact_ids,
        "forbidden_fact_ids": request.plan.forbidden_fact_ids,
        "facts": [
            {
                "id": fact.id,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "object": fact.object,
                "time": fact.time.isoformat() if fact.time else None,
                "location_id": fact.location_id,
                "polarity": fact.polarity,
            }
            for fact in request.facts
        ],
        "known_entities": {
            "characters": [{"id": char.id, "name": char.name, "role": char.public_role} for char in request.world.characters],
            "locations": [{"id": loc.id, "name": loc.name} for loc in request.world.locations],
            "objects": [{"id": obj.id, "name": obj.name} for obj in request.world.objects],
        },
        "required_output": {
            "title": "string",
            "text": "string",
            "facts_expressed": ["fact_id"],
            "entities_mentioned": ["known entity id only"],
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _result_from_json(raw: str, provider: str) -> TextGenerationResult:
    data = json.loads(raw)
    return TextGenerationResult(
        title=str(data["title"]),
        text=str(data["text"]),
        facts_expressed=[str(item) for item in data["facts_expressed"]],
        entities_mentioned=[str(item) for item in data.get("entities_mentioned", [])],
        provider=provider,
    )


_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "text": {"type": "string"},
        "facts_expressed": {"type": "array", "items": {"type": "string"}},
        "entities_mentioned": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "text", "facts_expressed", "entities_mentioned"],
}


_SOURCE_STYLES = {
    "sms": SourceStyle(
        "private phone message",
        "personal and clipped",
        "Make it feel like an ongoing conversation with omitted context.",
        "Do not summarize the investigation or identify legal responsibility.",
        "1-3 short message lines",
    ),
    "email": SourceStyle(
        "email with sender and subject",
        "personal but composed",
        "Use ordinary domestic or professional friction instead of exposition.",
        "Do not reveal the full motive unless it is a mandatory fact.",
        "4-7 lines",
    ),
    "access-control log": SourceStyle(
        "machine export table",
        "terse system log",
        "Use rows, timestamps, credential labels, and access result fields.",
        "Do not include subjective interpretation.",
        "2-5 table rows",
    ),
    "witness interview": SourceStyle(
        "interview transcript",
        "spoken and cautious",
        "Use question-answer phrasing and human uncertainty where appropriate.",
        "Do not let witnesses know facts they could not perceive.",
        "4-8 lines",
    ),
    "autopsy report": SourceStyle(
        "medical report excerpt",
        "clinical",
        "Use careful forensic wording and avoid overclaiming.",
        "Do not identify the culprit.",
        "4-8 lines",
    ),
    "security report": SourceStyle(
        "security maintenance note",
        "administrative",
        "Mention device status and coverage limitations.",
        "Do not infer intent from equipment status.",
        "3-6 lines",
    ),
}

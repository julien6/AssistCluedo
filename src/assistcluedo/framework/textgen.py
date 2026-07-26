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
    def __init__(self, provider: str = "template") -> None:
        self.provider = provider

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
    text = result.text.lower()
    for pattern in _SUMMARY_ANTI_PATTERNS:
        if pattern in text:
            raise ValueError(f"Generated document uses summary-style wording: {pattern}")
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
    if provider == "procedural":
        return TemplateTextGenerator(provider="procedural")
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
            f"Recovered SMS thread - {sender} / {recipient}",
            f"{time}  {sender}: Are you still in the house?",
            f"{time}  {recipient}: For now. Dinner has turned into speeches.",
            f"{time}  {sender}: Then slip away before they notice. Not the dining room.",
            f"{time}  {sender}: Same quiet place as before. I need you to hear this from me.",
        ]
    return _generic_lines(request, facts)


def _email_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    fact = facts.get("fact_motive")
    if fact:
        sender = entity_name(request.world, fact.subject)
        recipient = entity_name(request.world, request.truth.victim_id)
        return [
            f"From: {sender}",
            f"To: {recipient}",
            "Subject: The matter you promised to settle",
            f"Date: {request.created_at}",
            "",
            f"{recipient},",
            "",
            "You asked me to keep this out of tonight's conversation, and I did.",
            f"But I will not keep swallowing the consequences of {fact.object}.",
            "You know exactly who was hurt by that decision, even if you prefer to call it old business.",
            "",
            "We should settle it before the house starts listening.",
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
    rows = [
        "Witness interview transcript",
        f"Recorded: {request.created_at}",
        "Detective: Please describe only what you personally observed.",
    ]
    for fact in request.facts:
        if fact.id == "fact_exculpated_alibi":
            rows.append(
                f"Witness: Around {_time(fact)}, I remember {entity_name(request.world, fact.subject)} in {entity_name(request.world, str(fact.object))}."
            )
            rows.append(
                "Detective: You are certain about the place?"
            )
            rows.append(
                "Witness: Certain enough. I noticed because I had to step around them with a tray."
            )
        elif fact.id == "fact_false_statement":
            rows.append(
                f"Detective: Did {entity_name(request.world, fact.subject)} say where they went after dinner?"
            )
            rows.append(
                f"Witness: They said, very firmly, that they never went near {entity_name(request.world, request.truth.location_id)}."
            )
            rows.append(
                "Detective: Firmly?"
            )
            rows.append(
                "Witness: Too firmly, if you ask me. Like the answer had been rehearsed."
            )
        elif fact.id == "fact_witness_seen_culprit":
            rows.append(
                f"Witness: I noticed {entity_name(request.world, fact.subject)} near the corridor outside {entity_name(request.world, request.truth.location_id)} at about {_time(fact)}."
            )
            rows.append(
                "Detective: Passing through, or leaving?"
            )
            rows.append(
                "Witness: Leaving, I think. They turned away when they saw me."
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
    rows = [
        "Security maintenance ticket",
        f"Opened: {request.created_at}",
        "System: Blackwood internal camera network",
        "Status notes:",
    ]
    for fact in request.facts:
        if fact.id == "fact_camera_disabled":
            rows.append(
                f"- {_time(fact)} feed loss recorded for camera covering {entity_name(request.world, request.truth.location_id)}."
            )
            rows.append(
                "- Recorder continued accepting other channels; outage appears localized to that view."
            )
    return rows if len(rows) > 2 else _generic_lines(request, facts)


def _personal_note_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Undated personal note, folded into a desk blotter:"]
    for fact in request.facts:
        if fact.id == "fact_false_lead_argument":
            rows.append(
                f"{entity_name(request.world, fact.subject)} and {entity_name(request.world, str(fact.object))} started up again tonight."
            )
            rows.append(
                "I could hear the tight voices even with the service door closed."
            )
            rows.append(
                "It was money first, then pride, then one of those old promises nobody is meant to mention."
            )
    return rows if len(rows) > 1 else _generic_lines(request, facts)


def _inventory_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    setting_name = str(request.world.attributes.get("setting_name", "Blackwood Manor"))
    rows = [
        f"{setting_name} - household inventory exception sheet",
        f"Filed: {request.created_at}",
        "Item checks:",
    ]
    for fact in request.facts:
        if fact.id == "fact_weapon_initial_location":
            rows.append(f"- {entity_name(request.world, fact.subject)}: usual storage listed as {entity_name(request.world, str(fact.object))}.")
        elif fact.id == "fact_weapon_hidden":
            rows.append(f"- Recovery update: same item located in {entity_name(request.world, str(fact.object))}; not returned through normal storage.")
    return rows


def _gps_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Phone location export", "timestamp | handset | estimated area | confidence"]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"{_time(fact)} | {entity_name(request.world, fact.subject)} handset | {entity_name(request.world, str(fact.object))} | medium"
            )
    return rows if len(rows) > 2 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _receipt_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["BLACKWOOD MANOR PETTY CASH RECEIPT", f"Printed: {request.created_at}", "line | description | location"]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"01 | signed counterfoil: {entity_name(request.world, fact.subject)} | {entity_name(request.world, str(fact.object))}"
            )
    return rows if len(rows) > 3 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _call_log_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Telephone exchange log", "time | extension | party | route note"]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"{_time(fact)} | house line | {entity_name(request.world, fact.subject)} | routed near {entity_name(request.world, str(fact.object))}"
            )
    return rows if len(rows) > 2 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _newspaper_lines(request: TextGenerationRequest, facts: dict[str, Fact]) -> list[str]:
    rows = ["Blackwood Gazette society column", f"Clipping filed: {request.created_at}"]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"Among the guests noticed near {entity_name(request.world, str(fact.object))} was {entity_name(request.world, fact.subject)}, a familiar face at the manor's Sunday gatherings."
            )
    rows.append("The column makes no claim about the later police inquiry.")
    return rows if len(rows) > 2 else _generic_lines(request, {fact.id: fact for fact in request.facts})


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
        "anti_summary_rules": [
            "Do not write a third-person case summary.",
            "Do not use formulations like '<person> appears in a record at <time> near <place>'.",
            "Do not use formulations like '<person> sent <person> a message asking for a private meeting'.",
            "Do not use formulations like 'Records show <person> had a motive'.",
            "Do not use formulations like '<person> was seen in <place> away from the incident location'.",
            "Do not write evaluator guidance such as 'Treat this statement cautiously'.",
            "The document must look like the source itself: an SMS thread, email, transcript, receipt, call log, device export, diary note, or report excerpt.",
        ],
        "source_shape_examples": {
            "sms": "Use timestamped dialogue lines with speaker names, short replies, incomplete context, and no narrator.",
            "email": "Use From/To/Subject/Date headers and body text addressed directly to the recipient.",
            "witness interview": "Use Detective:/Witness: turns with spoken uncertainty and personally observed details.",
            "access-control log": "Use a machine table with timestamp, credential, door, and result fields.",
            "gps report": "Use a device export table with handset, estimated area, and confidence fields.",
            "receipt": "Use receipt or petty-cash line items, not a prose explanation.",
            "call log": "Use telephone exchange rows with extension, time, party, and route note.",
            "personal note": "Use first-person private writing with implied context, not investigative exposition.",
            "newspaper clipping": "Use a clipped society-column style with public observations only.",
            "autopsy report": "Use clinical headings and restrained forensic observations.",
        },
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


_SUMMARY_ANTI_PATTERNS = (
    " appears in a ",
    "message asking for a private meeting",
    "records show ",
    "away from the incident location",
    "claimed not to have been near",
    "treat this statement cautiously",
)


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
    "personal note": SourceStyle(
        "private handwritten note",
        "intimate and fragmentary",
        "Use first-person memory, household detail, and implied tension.",
        "Do not explain the clue as an investigator would.",
        "3-6 lines",
    ),
    "inventory report": SourceStyle(
        "household inventory exception sheet",
        "clerical",
        "Use item labels, storage locations, and exception language.",
        "Do not infer who moved or used an item unless that fact is mandatory.",
        "3-6 lines",
    ),
    "gps report": SourceStyle(
        "phone location export",
        "technical and terse",
        "Use rows, handset labels, estimated areas, timestamps, and confidence levels.",
        "Do not turn device pings into eyewitness certainty.",
        "2-5 table rows",
    ),
    "receipt": SourceStyle(
        "petty-cash receipt",
        "clerical and mundane",
        "Use receipt rows, counterfoils, signatures, or desk/location annotations.",
        "Do not summarize why the receipt matters.",
        "2-5 lines",
    ),
    "call log": SourceStyle(
        "telephone exchange log",
        "operator/system record",
        "Use routed call rows, extension labels, timestamps, and terse notes.",
        "Do not infer intent from the call.",
        "2-5 table rows",
    ),
    "newspaper clipping": SourceStyle(
        "society column clipping",
        "public, polished, and slightly indirect",
        "Use a periodical excerpt that notices attendance and locations without case analysis.",
        "Do not mention police conclusions or hidden facts.",
        "2-5 lines",
    ),
}

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from random import Random
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
class DocumentProfile:
    id: str
    family: str
    structure: str
    variants_allowed: list[str]
    register: str
    visible_metadata: list[str]
    formatting_conventions: list[str]
    realistic_imperfections: list[str]
    plausible_contents: list[str]
    forbidden_contents: list[str]
    prompt_guidance: str
    validation_family: str


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
    document_profile: DocumentProfile


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


class DocumentProfileCatalog:
    def profile_for(self, seed: int, document_id: str, document_type: str) -> DocumentProfile:
        profiles = _DOCUMENT_PROFILES.get(document_type)
        if not profiles:
            return _DEFAULT_DOCUMENT_PROFILE
        digest = sha256(f"{seed}:{document_id}:{document_type}".encode()).hexdigest()
        index = int(digest[:8], 16) % len(profiles)
        return profiles[index]


class TemplateTextGenerator:
    def __init__(self, provider: str = "template") -> None:
        self.provider = provider

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        facts = {fact.id: fact for fact in request.facts}
        lines = _template_lines(request, facts, _profile_rng(request))
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
    _validate_source_shape(request, result.text)
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


def _template_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    document_type = request.plan.document_type
    if document_type == "sms":
        return _sms_lines(request, facts, rng)
    if document_type == "email":
        return _email_lines(request, facts, rng)
    if document_type == "access-control log":
        return _access_log_lines(request, facts, rng)
    if document_type == "witness interview":
        return _witness_lines(request, facts, rng)
    if document_type == "autopsy report":
        return _autopsy_lines(request, facts, rng)
    if document_type == "security report":
        return _security_lines(request, facts, rng)
    if document_type == "personal note":
        return _personal_note_lines(request, facts, rng)
    if document_type == "inventory report":
        return _inventory_lines(request, facts, rng)
    if document_type == "gps report":
        return _gps_lines(request, facts, rng)
    if document_type == "receipt":
        return _receipt_lines(request, facts, rng)
    if document_type == "call log":
        return _call_log_lines(request, facts, rng)
    if document_type == "newspaper clipping":
        return _newspaper_lines(request, facts, rng)
    return _generic_lines(request, facts)


def _sms_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    fact = facts.get("fact_sms_meeting")
    if fact:
        sender = entity_name(request.world, fact.subject)
        recipient = entity_name(request.world, str(fact.object))
        time = _time(fact)
        if request.document_profile.id == "single_sms":
            opener = rng.choice(["Hi.", "Are you still there?", "Need a minute."])
            followup = rng.choice([
                "I left my glass in the hall so it will look ordinary.",
                "The music is covering half the corridor noise.",
                "Don't answer if anyone is beside you.",
            ])
            return [
                "SMS export",
                f"From: {sender}",
                f"To: {recipient}",
                f"Sent: {time}",
                f"Device: {rng.choice(['kitchen charging shelf', 'hallway coat stand', 'guest-room night table'])}",
                f"Extraction note: {rng.choice(['screen glass cracked at lower edge', 'message recovered from notification cache', 'thread muted after delivery'])}",
                f"{opener} Not the dining room. Same quiet place as before. I need you to hear this from me.",
                followup,
            ]
        if request.document_profile.id == "phone_notification":
            preview_tail = rng.choice([
                "Screen dimmed before full text was captured.",
                "Notification grouped under Messages.",
                "Battery saver active; preview truncated.",
            ])
            return [
                "Phone notification preview",
                f"{time} - {sender}",
                f"App: Messages | Focus mode: {rng.choice(['off', 'personal', 'sleep schedule disabled'])}",
                "Hi - still in the house? Slip away before they notice. Same quiet place as before.",
                preview_tail,
            ]
        return [
            f"Recovered SMS thread - {sender} / {recipient}",
            f"{time}  {sender}: {rng.choice(['Hi.', 'You there?', 'Still inside?'])} Are you still in the house?",
            f"{time}  {recipient}: {rng.choice(['Yes.', 'For now.', 'Still here.'])} Dinner has turned into speeches.",
            f"{time}  {sender}: {rng.choice(['Good.', 'Keep your voice down.', 'Leave your glass if anyone asks.'])}",
            f"{time}  {recipient}: {rng.choice(['People are still in the hall.', 'The coffee is only just being served.', 'Someone is at the piano again.'])}",
            f"{time}  {sender}: Then slip away before they notice. Not the dining room.",
            f"{time}  {sender}: Same quiet place as before. I need you to hear this from me.",
            f"{time}  {recipient}: {rng.choice(['Fine.', 'Make it quick.', 'I am not waiting long.'])}",
        ]
    return _generic_lines(request, facts)


def _email_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    fact = facts.get("fact_motive")
    if fact:
        sender = entity_name(request.world, fact.subject)
        recipient = entity_name(request.world, request.truth.victim_id)
        if request.document_profile.id == "internal_email":
            return [
                f"From: {sender}",
                f"To: {recipient}",
                "Subject: Before this becomes a household matter",
                f"Date: {request.created_at}",
                f"X-Mailer: {rng.choice(['Blackwood webmail', 'OldMail 3.8', 'House office desktop'])}",
                "",
                f"{recipient},",
                "",
                f"I have kept quiet about {fact.object} because you asked me to.",
                "That does not mean I accept the way you have left it.",
                "I had to sit through dinner while everyone pretended nothing was hanging over us.",
                "The lamps in the hall kept dipping every few minutes, which did not help my temper.",
                "We need to settle this tonight, privately.",
                "",
                rng.choice(["Regards,", "Please answer this time,", "Enough silence,"]),
                sender,
            ]
        if request.document_profile.id == "followup_email":
            return [
                f"From: {sender}",
                f"To: {recipient}",
                "Subject: Following up",
                f"Date: {request.created_at}",
                f"Message-ID: <followup-{request.document_id}@blackwood.local>",
                "",
                f"{recipient},",
                "",
                "I am following up because you did not answer me earlier.",
                f"The matter is still {fact.object}, however carefully everyone avoids the words.",
                "Your secretary said you had stepped away, but the house is not large enough for this much avoiding.",
                "I can still hear people laughing downstairs, which makes this all the more absurd.",
                "Please do not make me raise it where others can hear.",
                "",
                sender,
            ]
        return [
            f"From: {sender}",
            f"To: {recipient}",
            f"Subject: {rng.choice(['The matter you promised to settle', 'Tonight', 'A private word'])}",
            f"Date: {request.created_at}",
            f"Draft saved: {rng.choice(['yes', 'no', 'autosave recovered'])}",
            "",
            f"{recipient},",
            "",
            "You asked me to keep this out of tonight's conversation, and I did.",
            f"But I will not keep swallowing the consequences of {fact.object}.",
            "You know exactly who was hurt by that decision, even if you prefer to call it old business.",
            "I am tired of smiling over cold coffee while you change the subject.",
            "The blue folder is still where you left it, which says enough.",
            "",
            "We should settle it before the house starts listening.",
            "",
            sender,
        ]
    return _generic_lines(request, facts)


def _access_log_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    if request.document_profile.id == "badge_audit_trail":
        rows = [
            "Badge audit trail",
            f"controller={rng.choice(['AC-NORTH-02', 'AC-HALL-1', 'MANOR-EDGE'])} export=partial",
            f"operator={rng.choice(['night desk', 'auto-export', 'E.M.'])} checksum={rng.choice(['ok', 'pending', 'manual'])}",
            "date_time | badge_id | zone | direction | status",
        ]
    else:
        rows = [
            "ACCESS CONTROL EXPORT",
            f"panel: {rng.choice(['west service rack', 'main hall controller', 'office subpanel'])}",
            f"batch: {rng.choice(['A17', 'B04', 'K22'])} | clock drift: {rng.choice(['+00:12', '-00:04', '+00:00'])}",
            "timestamp | credential | door | result",
        ]
    for fact in request.facts:
        if fact.id == "fact_badge_access":
            if request.document_profile.id == "badge_audit_trail":
                rows.append(
                    f"{request.created_at} | badge:{fact.subject} | {entity_name(request.world, str(fact.object))} | IN | OK"
                )
                rows.append(f"{request.created_at} | badge:{fact.subject} | controller | latch-check | PASS")
            else:
                rows.append(
                    f"{_time(fact)} | badge:{fact.subject} | {entity_name(request.world, str(fact.object))} | granted"
                )
                rows.append(f"{_time(fact)} | badge:{fact.subject} | controller heartbeat | accepted")
    return rows


def _witness_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = [
        "Witness interview transcript" if request.document_profile.id == "witness_qa_transcript" else "Investigator notes - witness statement",
        f"Recorded: {request.created_at}",
        f"Room note: {rng.choice(['clock audible in corridor', 'tea brought in midway', 'rain against south windows'])}.",
        f"Transcript note: {rng.choice(['several pauses marked only where clear', 'witness asked twice for water', 'recorder placed near green lamp'])}.",
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
            rows.append("Witness: I remember the tray because the spoon kept rattling.")
            rows.append("Detective: Anything else about the room?")
            rows.append(f"Witness: Only that {rng.choice(['the curtains were half drawn', 'someone had left a chair pulled out', 'the fire was nearly gone'])}.")
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
            rows.append("Witness: Sorry, that is how it sounded to me.")
            rows.append("Detective: We will note that as your impression, not as a fact.")
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
            rows.append("Witness: The corridor lamp was flickering, so I would not swear to more than that.")
            rows.append("Detective: Did anyone else pass?")
            rows.append("Witness: I heard steps, but in that house there are always steps.")
    return rows if len(rows) > 2 else _generic_lines(request, facts)


def _autopsy_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = ["Preliminary autopsy note", "Examiner observations:"] if request.document_profile.id == "medical_examiner_note" else [
        "Forensic pathology worksheet",
        f"Logged: {request.created_at}",
            "Findings:",
    ]
    rows.append(f"Case ref: {rng.choice(['PM-09-Blackwood', 'ME/BB/0810', 'BWM-prelim-4'])}")
    for fact in request.facts:
        if fact.id == "fact_death_window":
            rows.append(f"- Estimated death window: {fact.object}.")
            rows.append(f"- Body temperature note taken after instruments were recalibrated at {rng.choice(['08:04', '08:11', '08:18'])}.")
            rows.append("- Stomach contents: light supper; no unusual odor recorded.")
        elif fact.id == "fact_murder_weapon":
            rows.append(f"- Wound pattern is consistent with a heavy object such as the {entity_name(request.world, str(fact.object))}.")
            rows.append(f"- Trace staining noted along one edge; photography reference {rng.choice(['IMG-17B', 'IMG-22C', 'IMG-31A'])}.")
            rows.append("- No final toxicology conclusion in this preliminary excerpt.")
    rows.append("These findings describe physical consistency, not legal responsibility.")
    return rows


def _security_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = (
        [
            "Security maintenance ticket",
            f"Opened: {request.created_at}",
            "System: internal camera network",
            "Status notes:",
            f"Priority: {rng.choice(['P2', 'routine overnight', 'review before breakfast'])}",
        ]
        if request.document_profile.id == "maintenance_ticket"
        else [
            "Camera outage alert",
            f"alert id: {rng.choice(['CAM-771', 'VID-204', 'NVR-55'])}",
            "timestamp | camera zone | status | note",
        ]
    )
    for fact in request.facts:
        if fact.id == "fact_camera_disabled":
            if request.document_profile.id == "maintenance_ticket":
                rows.append(
                    f"- {_time(fact)} feed loss recorded for camera covering {entity_name(request.world, request.truth.location_id)}."
                )
                rows.append("- Recorder accepted other channels; outage appears localized to that view.")
                rows.append(f"- Ticket note: {rng.choice(['no spare technician on site', 'reset deferred until morning', 'cabinet key held at front desk'])}.")
            else:
                rows.append(f"{_time(fact)} | {entity_name(request.world, request.truth.location_id)} | OFFLINE | feed loss")
                rows.append(f"{_time(fact)} | recorder | ONLINE | other channels nominal")
    return rows if len(rows) > 2 else _generic_lines(request, facts)


def _personal_note_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = [
        "Undated personal note, folded into a desk blotter:"
        if request.document_profile.id == "private_diary_fragment"
        else "Torn note, pencil on small writing paper:"
    ]
    rows.append(rng.choice(["The paper smells faintly of lavender drawer liner.", "Corner torn off; no signature visible.", "Written in a hurry, slanting down the page."]))
    for fact in request.facts:
        if fact.id == "fact_false_lead_argument":
            if request.document_profile.id == "door_note":
                rows.append(f"I came by after hearing {entity_name(request.world, fact.subject)} with {entity_name(request.world, str(fact.object))}.")
                rows.append("Too much shouting. Back later if the house calms down.")
                rows.append(rng.choice(["Please do not leave the blue cup on my desk again.", "I put the spare pencil under the blotter.", "The hallway smells of polish tonight."]))
                rows.append(rng.choice(["No one ever shuts that service door properly.", "Could not find the matches either.", "This house carries every word after dinner."]))
            else:
                rows.append(
                    f"I heard {entity_name(request.world, fact.subject)} and {entity_name(request.world, str(fact.object))} start up again tonight."
                )
                rows.append("I could hear the tight voices even with the service door closed.")
                rows.append("It was money first, then pride, then one of those old promises nobody is meant to mention.")
                rows.append(rng.choice(["My tea had gone cold by then.", "The little clock kept losing a minute.", "Someone left mud on the runner again."]))
                rows.append(rng.choice(["I wish I had stayed in my room.", "The whole evening felt too polished.", "Even the silver smelled of polish and rain."]))
    return rows if len(rows) > 1 else _generic_lines(request, facts)


def _inventory_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    setting_name = str(request.world.attributes.get("setting_name", "Blackwood Manor"))
    rows = [
        f"{setting_name} - household inventory exception sheet",
        f"Filed: {request.created_at}",
        f"Checked by: {rng.choice(['E.M.', 'night steward', 'house office'])}",
        f"Cabinet note: {rng.choice(['left hinge stiff', 'top shelf relabelled', 'old tag book missing page 12'])}",
        "Item checks:",
    ]
    for fact in request.facts:
        if fact.id == "fact_weapon_initial_location":
            rows.append(f"- {entity_name(request.world, fact.subject)}: usual storage listed as {entity_name(request.world, str(fact.object))}. Shelf label slightly torn.")
            rows.append(f"  Last routine count: {rng.choice(['initialled only', 'entered in pencil', 'checked before luncheon'])}.")
        elif fact.id == "fact_weapon_hidden":
            rows.append(f"- Recovery update: same item located in {entity_name(request.world, str(fact.object))}; not returned through normal storage. Tag string damp.")
            rows.append("  No note found in the drawer with it.")
    return rows


def _gps_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = [
        "Phone location export",
        f"provider batch: {rng.choice(['loc-cache-18', 'tower-merge-04', 'device-export-7'])}",
        f"map precision: {rng.choice(['indoor estimate', 'low satellite visibility', 'wifi-assisted'])}",
        "timestamp | handset | estimated area | confidence | note",
    ]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"{_time(fact)} | {entity_name(request.world, fact.subject)} handset | {entity_name(request.world, str(fact.object))} | medium | indoor estimate"
            )
    return rows if len(rows) > 2 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _receipt_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = [
        "PETTY CASH RECEIPT" if request.document_profile.id == "petty_cash_receipt" else "Counterfoil slip",
        f"Printed: {request.created_at}",
        f"terminal: {rng.choice(['drawer-2', 'service desk', 'hall printer'])}",
        f"paper roll: {rng.choice(['low', 'replaced after print', 'faint ink at top'])}",
        "line | description | location | clerk",
    ]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"01 | signed counterfoil: {entity_name(request.world, fact.subject)} | {entity_name(request.world, str(fact.object))} | {rng.choice(['M.B.', 'desk', 'initial illegible'])}"
            )
    return rows if len(rows) > 3 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _call_log_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = [
        "Telephone exchange log",
        f"switchboard: {rng.choice(['manual desk', 'west closet', 'house exchange'])}",
        f"operator note: {rng.choice(['line crackle intermittent', 'bell slow to return', 'ink ribbon faint'])}",
        "time | extension | party | route note | duration",
    ]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"{_time(fact)} | house line | {entity_name(request.world, fact.subject)} | routed near {entity_name(request.world, str(fact.object))} | {rng.choice(['00:41', '01:12', 'missed'])}"
            )
    return rows if len(rows) > 2 else _generic_lines(request, {fact.id: fact for fact in request.facts})


def _newspaper_lines(request: TextGenerationRequest, facts: dict[str, Fact], rng: Random) -> list[str]:
    rows = [
        "Society column clipping" if request.document_profile.id == "society_column" else "Local news brief",
        f"Clipping filed: {request.created_at}",
        f"Column note: {rng.choice(['page edge torn', 'ink transfer visible', 'clipped from late edition'])}",
    ]
    for fact in request.facts:
        if fact.id.startswith("fact_ev_ctx_"):
            rows.append(
                f"Among the guests noticed near {entity_name(request.world, str(fact.object))} was {entity_name(request.world, fact.subject)}, a familiar face at the manor's Sunday gatherings."
            )
    rows.append(rng.choice([
        "The evening's flowers were reportedly supplied from the village shop.",
        "Several guests were still discussing the charity raffle as coffee was served.",
        "The household staff kept the west doors closed against the rain.",
    ]))
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
        "generic_document_prompt": (
            "Generate a realistic {document_type} written by the plausible author for the plausible recipient "
            "at the provided date/time, in the context of this investigation. The document must communicate "
            "the mandatory scenario facts and should include harmless contextual texture. Do not mention or imply "
            "information outside the author's plausible knowledge at that moment. Respect the normal structure, "
            "tone, vocabulary, formatting conventions, length, and imperfections of a real document matching "
            "the selected document profile. Do not explain the document type and do not add commentary before "
            "or after it. Output only the document content in the JSON text field."
        ),
        "core_philosophy": [
            "The symbolic facts below are the only source of truth.",
            "Your job is to make the document feel realistic for its source, not to decide what happened.",
            "Use everyday texture, institutional formatting, hesitation, omission, or terse system language as appropriate.",
            "Never add a new suspect, location, object, event, time, motive, relationship, confession, or conclusion.",
            "Never identify the culprit unless a mandatory fact explicitly says so.",
            "Do not expose internal IDs in the document text; IDs may appear only in facts_expressed and entities_mentioned.",
            "Return JSON only, with no markdown and no surrounding commentary.",
        ],
        "harmless_contextual_texture": {
            "purpose": "Add small realistic details that make the document feel lived-in without adding new clues.",
            "allowed": [
                "ordinary greetings, hesitations, sign-offs, or shared-context fragments",
                "mundane times, reference numbers, terminal IDs, extension numbers, initials, or filing marks",
                "ambient details such as dinner noise, rain on windows, corridor lamps, cold tea, paper creases",
                "administrative boilerplate, clipped headers, partial previews, confidence labels, or status codes",
                "minor imperfections such as abbreviations, omitted punctuation, uneven sentence length, or cautious wording",
            ],
            "forbidden": [
                "new alibis, new meetings, new locations, new objects, new times that matter, new relationships",
                "new accusations, confessions, threats, motives, hidden knowledge, or investigative conclusions",
                "details that imply a character saw or knew more than the mandatory facts support",
            ],
        },
        "anti_summary_rules": [
            "Do not write a third-person case summary.",
            "Do not convert the evidence into a detective report.",
            "Do not use formulations like '<person> appears in a record at <time> near <place>'.",
            "Do not use formulations like '<person> sent <person> a message asking for a private meeting'.",
            "Do not use formulations like 'Records show <person> had a motive'.",
            "Do not use formulations like '<person> had a heated argument with <person>'.",
            "Do not use formulations like '<person> was seen in <place> away from the incident location'.",
            "Do not write evaluator guidance such as 'Treat this statement cautiously'.",
            "The document must look like the source itself, not like a police summary about that source.",
        ],
        "document_profile": request.document_profile.__dict__,
        "hard_invariants": _hard_invariants(request.document_profile),
        "source_realism_contract": {
            "structure": request.source_style.structure,
            "register": request.source_style.register,
            "guidance": request.source_style.realism_guidance,
            "forbidden_behavior": request.source_style.forbidden_behavior,
            "target_length": request.source_style.target_length,
        },
        "output_rules": {
            "title": "Use the supplied title unless the source format naturally requires a tiny variation.",
            "text": "Output only the document content. Include realistic harmless texture. No analysis of the case. No hidden oracle summary.",
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
    " appears near ",
    "message asking for a private meeting",
    "records show ",
    " had a motive:",
    " had a heated argument with ",
    "away from the incident location",
    "claimed not to have been near",
    "treat this statement cautiously",
)


_DEFAULT_DOCUMENT_PROFILE = DocumentProfile(
    id="generic_source_excerpt",
    family="source excerpt",
    structure="brief source excerpt",
    variants_allowed=["short note", "file excerpt", "administrative extract"],
    register="plain and source-native",
    visible_metadata=["created_at", "source"],
    formatting_conventions=["Use the conventions of the named source.", "Avoid explanatory headings unless native to the source."],
    realistic_imperfections=["partial context", "terse phrasing"],
    plausible_contents=["mandatory facts", "minor harmless context"],
    forbidden_contents=["case summary", "culprit inference", "forbidden facts"],
    prompt_guidance="Write the source itself, not a summary of what investigators learned from it.",
    validation_family="generic",
)


_DOCUMENT_PROFILES: dict[str, list[DocumentProfile]] = {
    "sms": [
        DocumentProfile(
            "personal_sms_exchange",
            "personal communication",
            "short recovered SMS conversation",
            ["two-to-four timestamped messages", "brief reply chain", "elliptical exchange"],
            "informal, tense, and concise",
            ["sender", "recipient", "sent time"],
            ["speaker labels are allowed", "timestamps may appear per message", "no subject line"],
            ["abbreviations", "omitted punctuation", "shared context", "short replies"],
            ["a request to meet", "tone between sender and recipient", "time of message"],
            ["third-person description that a message was sent", "investigative interpretation"],
            "Generate a realistic SMS exchange. A greeting like 'Hi' or 'You there?' is natural but not required.",
            "personal_message",
        ),
        DocumentProfile(
            "single_sms",
            "personal communication",
            "single exported SMS",
            ["one message with From/To/Sent metadata", "phone extraction snippet"],
            "informal and compressed",
            ["from", "to", "sent"],
            ["compact metadata header", "message body may be one paragraph"],
            ["missing punctuation", "implied prior conversation"],
            ["a private meeting request", "the recipient and time"],
            ["narrator summary", "subject line"],
            "Write one realistic SMS body plus minimal phone-extraction metadata. Do not narrate the clue.",
            "personal_message",
        ),
        DocumentProfile(
            "phone_notification",
            "personal communication",
            "lock-screen or notification preview",
            ["notification preview", "truncated message", "app extraction line"],
            "very short and fragmentary",
            ["time", "sender/app"],
            ["one or two preview lines", "may look truncated"],
            ["ellipsis", "cut-off context", "informal opening"],
            ["sender", "message time", "hint of private meeting"],
            ["full case explanation", "formal prose"],
            "Write a phone notification preview or extraction snippet that contains the required fact naturally.",
            "personal_message",
        ),
    ],
    "email": [
        DocumentProfile(
            "personal_email",
            "email",
            "personal email",
            ["private email", "strained household correspondence"],
            "personal but composed",
            ["from", "to", "subject", "date"],
            ["headers", "greeting", "paragraph body", "optional signature"],
            ["shared context", "controlled emotion", "understatement"],
            ["motive pressure", "direct address to recipient"],
            ["Records show phrasing", "investigative conclusion"],
            "Write a realistic personal email with headers and a body addressed to the recipient.",
            "email",
        ),
        DocumentProfile(
            "internal_email",
            "email",
            "internal workplace-style email",
            ["concise internal email", "household business email"],
            "professional with shared context",
            ["from", "to", "subject", "date"],
            ["concise subject", "short paragraphs", "no over-explaining shared facts"],
            ["indirect wording", "polite pressure"],
            ["motive framed as an unresolved matter", "need for private discussion"],
            ["case summary", "police interpretation"],
            "Write an internal email that assumes the recipient already knows the dispute.",
            "email",
        ),
        DocumentProfile(
            "followup_email",
            "email",
            "follow-up email",
            ["polite follow-up", "unanswered prior message"],
            "polite but strained",
            ["from", "to", "subject", "date"],
            ["brief reference to earlier message", "requested action"],
            ["impatience under formal wording"],
            ["motive as unresolved pressure", "request for response"],
            ["Records show phrasing", "omniscient motive explanation"],
            "Write a follow-up email referring to an earlier unanswered message.",
            "email",
        ),
    ],
    "witness interview": [
        DocumentProfile(
            "witness_qa_transcript",
            "interview",
            "question-and-answer transcript",
            ["Detective/Witness turns", "Q/A transcript"],
            "spoken and cautious",
            ["recorded time", "interviewer"],
            ["speaker labels", "uneven answer length"],
            ["hesitations", "uncertainty", "self-corrections"],
            ["what the witness personally perceived"],
            ["facts the witness could not know", "legal conclusion"],
            "Write interview transcript turns. The witness should sound partial and human.",
            "interview",
        ),
        DocumentProfile(
            "statement_taken_notes",
            "interview",
            "investigator notes from witness statement",
            ["rough notes", "paraphrased statement with quoted fragments"],
            "concise and observational",
            ["recorded time", "witness statement"],
            ["fragments allowed", "question prompts may be abbreviated"],
            ["uncertain wording", "partial recollection"],
            ["witness observation", "reported wording"],
            ["case conclusion", "omniscient correction"],
            "Write notes taken during a statement, preserving uncertainty and source limits.",
            "interview",
        ),
    ],
    "personal note": [
        DocumentProfile(
            "private_diary_fragment",
            "personal note",
            "private diary fragment",
            ["diary fragment", "folded note"],
            "subjective and intimate",
            ["date if natural"],
            ["first person", "short paragraphs or fragments"],
            ["emotion", "incomplete context", "crossed-out feeling implied in wording"],
            ["what the writer heard or felt"],
            ["objective investigative summary", "hidden truth"],
            "Write first-person private writing. It should not sound like a report.",
            "personal_note",
        ),
        DocumentProfile(
            "door_note",
            "personal note",
            "brief handwritten note left for someone",
            ["desk note", "door note", "short reminder"],
            "direct and fragmentary",
            ["optional signature", "optional time"],
            ["very short lines", "minimal greeting"],
            ["shorthand", "missing context"],
            ["writer's practical reason for coming by", "what they heard"],
            ["formal chronology", "case interpretation"],
            "Write a short handwritten-style note left in the house.",
            "personal_note",
        ),
    ],
    "access-control log": [
        DocumentProfile(
            "access_machine_export",
            "security access",
            "machine export table",
            ["access log", "door controller export"],
            "terse and technical",
            ["timestamp", "credential", "door", "result"],
            ["pipe-delimited rows", "system identifiers"],
            ["abbreviated fields", "machine terseness"],
            ["credential use", "door/zone", "access status"],
            ["intent", "motive", "case analysis"],
            "Generate machine-like access rows.",
            "machine_log",
        ),
        DocumentProfile(
            "badge_audit_trail",
            "security access",
            "badge audit trail",
            ["audit trail", "security console extract"],
            "technical and compact",
            ["date_time", "badge_id", "zone", "direction", "status"],
            ["table rows", "short status values"],
            ["cryptic identifiers", "no prose"],
            ["entry event", "location"],
            ["subjective interpretation"],
            "Generate a compact badge audit trail.",
            "machine_log",
        ),
    ],
    "security report": [
        DocumentProfile(
            "maintenance_ticket",
            "security operations",
            "maintenance ticket",
            ["support ticket", "camera fault note"],
            "administrative",
            ["opened", "system", "status"],
            ["field labels", "status notes"],
            ["terse diagnosis", "limited conclusion"],
            ["camera outage", "affected zone"],
            ["intent behind outage", "culprit identity"],
            "Write a security maintenance ticket.",
            "machine_log",
        ),
        DocumentProfile(
            "automatic_security_alert",
            "security operations",
            "automated security alert",
            ["alert row", "system event"],
            "standardized and terse",
            ["timestamp", "zone", "status"],
            ["table rows or alert fields"],
            ["codes", "minimal prose"],
            ["camera/feed status", "location covered"],
            ["human motive", "investigator commentary"],
            "Write a standardized automated security alert.",
            "machine_log",
        ),
    ],
    "gps report": [
        DocumentProfile(
            "phone_location_export",
            "digital system",
            "phone location export",
            ["device export", "location estimate table"],
            "technical and cautious",
            ["timestamp", "handset", "estimated area", "confidence"],
            ["rows", "confidence labels"],
            ["approximation", "medium confidence"],
            ["device/person proximity", "estimated area"],
            ["eyewitness certainty", "intent"],
            "Write a phone location export.",
            "machine_log",
        )
    ],
    "inventory report": [
        DocumentProfile(
            "inventory_exception_sheet",
            "administrative record",
            "household inventory exception sheet",
            ["inventory sheet", "exception report", "recovery update"],
            "clerical and specific",
            ["filed date", "item checks", "storage location"],
            ["bullet list", "item labels", "exception wording"],
            ["dry phrasing", "partial item history"],
            ["object storage", "object recovery location"],
            ["who used the object", "culprit identity"],
            "Write a household inventory exception sheet.",
            "administrative_record",
        ),
        DocumentProfile(
            "workroom_item_check",
            "administrative record",
            "item check note",
            ["checklist", "stock room note"],
            "clerical and abbreviated",
            ["checked time", "item", "status"],
            ["short checklist lines", "status words"],
            ["abbreviations", "missing explanatory context"],
            ["where an object should be or was found"],
            ["case conclusion"],
            "Write a compact item check note.",
            "administrative_record",
        ),
    ],
    "autopsy report": [
        DocumentProfile(
            "medical_examiner_note",
            "medical report",
            "preliminary autopsy note",
            ["medical note", "examiner observations"],
            "clinical and restrained",
            ["examiner", "observations"],
            ["headings", "bullet findings"],
            ["cautious wording", "physical consistency only"],
            ["death window", "wound/object consistency"],
            ["legal responsibility", "motive"],
            "Write a clinical medical examiner note.",
            "medical_report",
        ),
        DocumentProfile(
            "forensic_pathology_worksheet",
            "medical report",
            "forensic pathology worksheet",
            ["worksheet", "preliminary finding extract"],
            "technical and concise",
            ["logged time", "findings"],
            ["numbered or bullet observations"],
            ["hedging", "incomplete final certification"],
            ["death window", "injury pattern"],
            ["culprit conclusion"],
            "Write a forensic pathology worksheet excerpt.",
            "medical_report",
        ),
    ],
    "receipt": [
        DocumentProfile(
            "petty_cash_receipt",
            "financial document",
            "petty-cash receipt",
            ["receipt", "counterfoil", "signed slip"],
            "clerical and mundane",
            ["printed time", "line item", "location"],
            ["compact receipt rows", "counterfoil wording"],
            ["abbreviated descriptions", "ordinary transaction detail"],
            ["presence/location clue", "signature/counterfoil"],
            ["case explanation"],
            "Write a petty-cash receipt or counterfoil artifact.",
            "receipt",
        ),
        DocumentProfile(
            "counterfoil_slip",
            "financial document",
            "counterfoil slip",
            ["signed slip", "desk receipt"],
            "minimal and clerical",
            ["printed time", "signature", "location"],
            ["short rows", "receipt identifiers"],
            ["partial label", "clipped description"],
            ["name and location implied by transaction"],
            ["investigative prose"],
            "Write a short counterfoil slip.",
            "receipt",
        ),
    ],
    "call log": [
        DocumentProfile(
            "telephone_exchange_log",
            "telephony",
            "telephone exchange log",
            ["call log", "switchboard extract"],
            "operator/system terse",
            ["time", "extension", "party", "route note"],
            ["row/table format", "short route notes"],
            ["abbreviations", "system labels"],
            ["call route or presence near a line"],
            ["conversation content not in the log"],
            "Write a compact call log.",
            "machine_log",
        )
    ],
    "newspaper clipping": [
        DocumentProfile(
            "society_column",
            "press",
            "society column clipping",
            ["society column", "local paper mention"],
            "public and polished",
            ["publication", "filed date"],
            ["short paragraph", "public observation"],
            ["indirect phrasing", "social detail"],
            ["who was noticed where", "public context"],
            ["police conclusions", "hidden facts"],
            "Write a clipping from a society column.",
            "press",
        ),
        DocumentProfile(
            "local_news_brief",
            "press",
            "local news brief",
            ["brief article", "local note"],
            "neutral and concise",
            ["publication", "date"],
            ["short news paragraph"],
            ["attribution", "limited public knowledge"],
            ["publicly observable presence/location"],
            ["private motive", "culprit identity"],
            "Write a short local news brief.",
            "press",
        ),
    ],
}


def _validate_source_shape(request: TextGenerationRequest, text: str) -> None:
    family = request.document_profile.validation_family
    lowered = text.lower()
    if family == "personal_message":
        has_message_shape = (
            ":" in text
            or any(marker in lowered for marker in ("from:", "to:", "sent:", "hi", "you there", "still there"))
        )
        if not has_message_shape:
            raise ValueError("Personal messages must look like a message artifact, not a prose summary.")
        if " sent " in lowered and "message" in lowered:
            raise ValueError("Personal messages must not describe a sent message in third person.")
    elif family == "email":
        if "subject:" not in lowered and not lowered.startswith("re:"):
            raise ValueError("Email documents must include email-like subject/context.")
        if "records show" in lowered:
            raise ValueError("Email documents must be correspondence, not a record summary.")
    elif family == "interview":
        if not any(marker in lowered for marker in ("detective:", "witness:", "q:", "a:", "statement taken")):
            raise ValueError("Witness interviews must look like interview notes or transcript material.")
    elif family == "personal_note":
        if not re.search(r"(^|\n|\s)(i|my|me|remember|heard|came by|back later)\b", lowered):
            raise ValueError("Personal notes must read as private writing rather than external reporting.")
    elif family in {"machine_log", "receipt"}:
        if "|" not in text and ":" not in text:
            raise ValueError(f"{request.plan.document_type} must use source-like structured formatting.")


def _hard_invariants(profile: DocumentProfile) -> list[str]:
    return [
        "Do not write a third-person investigative summary.",
        "Do not add facts outside mandatory facts and harmless everyday texture.",
        "Do not reveal forbidden facts or hidden conclusions.",
        "Do not mention information the author/source could not plausibly know.",
        *profile.forbidden_contents,
    ]


def _profile_rng(request: TextGenerationRequest) -> Random:
    digest = sha256(f"{request.document_id}:{request.document_profile.id}:{request.created_at}".encode()).hexdigest()
    return Random(int(digest[:16], 16))


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

from __future__ import annotations

from assistcluedo.framework.models import (
    Device,
    DocumentPlan,
    Event,
    Fact,
    GeneratedDocument,
    GroundTruth,
    JsonScalar,
    Trace,
    World,
)
from assistcluedo.framework.pack import Pack
from assistcluedo.framework.textgen import (
    DocumentProfileCatalog,
    SourceStyleCatalog,
    TextGenerationRequest,
    TextGenerator,
    generator_for,
)


class DocumentPlanner:
    def generate(self, traces: list[Trace], events: list[Event], world: World) -> list[DocumentPlan]:
        event_by_id = {event.id: event for event in events}
        plans = []
        for index, trace in enumerate(traces, start=1):
            provenance = _plan_context_for(trace, event_by_id, world)
            plans.append(
                DocumentPlan(
                    id=f"plan_{index:03d}",
                    document_type=trace.trace_type,
                    source_trace_ids=[trace.id],
                    mandatory_fact_ids=trace.fact_ids,
                    forbidden_fact_ids=["fact_culprit_identity"],
                    author_id=provenance["author_id"],
                    source_system_id=provenance["source_system_id"],
                    truth_mode=trace.truth_mode,
                    retrieval_location_id=provenance["retrieval_location_id"],
                    source_device_id=provenance["source_device_id"],
                    witness_character_id=provenance["witness_character_id"],
                    style=provenance["style"],
                )
            )
        return plans


class DocumentRenderer:
    def generate(
        self,
        seed: int,
        world: World,
        truth: GroundTruth,
        facts: list[Fact],
        traces: list[Trace],
        plans: list[DocumentPlan],
        pack: Pack,
        text_generator: TextGenerator | None = None,
        provider: str = "local-llm",
        fallback: str = "procedural",
        max_attempts: int = 2,
        model: str = "local",
    ) -> list[GeneratedDocument]:
        facts_by_id = {fact.id: fact for fact in facts}
        traces_by_id = {trace.id: trace for trace in traces}
        generator = text_generator or generator_for(provider, fallback=fallback, max_attempts=max_attempts, model=model)
        style_catalog = SourceStyleCatalog()
        profile_catalog = DocumentProfileCatalog()
        documents = []
        for index, plan in enumerate(plans, start=1):
            document_id = f"doc_{index:03d}"
            trace = traces_by_id[plan.source_trace_ids[0]]
            source_times = [
                fact.time
                for fact_id in trace.fact_ids
                if (fact := facts_by_id[fact_id]).time is not None
            ]
            created_at = max(source_times).isoformat() if source_times else truth.incident_time.isoformat()
            title = pack.document_titles.get(plan.document_type, plan.document_type.title())
            request = TextGenerationRequest(
                document_id=document_id,
                title=title,
                plan=plan,
                trace=trace,
                world=world,
                truth=truth,
                facts=[facts_by_id[fact_id] for fact_id in plan.mandatory_fact_ids],
                created_at=created_at,
                source_style=style_catalog.profile_for(plan.document_type),
                document_profile=profile_catalog.profile_for(seed, document_id, plan.document_type),
            )
            result = generator.generate(request)
            documents.append(
                GeneratedDocument(
                    id=document_id,
                    plan_id=plan.id,
                    title=result.title,
                    text=result.text,
                    visible_metadata={
                        "type": plan.document_type,
                        "reliability": trace.reliability,
                        "source": plan.source_system_id or "investigation file",
                        "created_at": created_at,
                        "source_profile": request.document_profile.id,
                        "text_provider": result.provider,
                        "fallback_used": result.fallback_used,
                    },
                    extracted_fact_ids=result.facts_expressed,
                )
            )
        return documents


def _fallback_location_id(world: World) -> str:
    location_ids = {location.id for location in world.locations}
    if "office" in location_ids:
        return "office"
    return next(iter(sorted(location_ids)))


def _device_of_type(world: World, device_type: str) -> Device | None:
    return next((device for device in world.devices if device.device_type == device_type), None)


def _phone_of(world: World, character_id: str | None) -> Device | None:
    if character_id is None:
        return None
    return next(
        (device for device in world.devices if device.device_type == "phone" and device.owner_character_id == character_id),
        None,
    )


def _plan_context_for(
    trace: Trace, event_by_id: dict[str, Event], world: World
) -> dict[str, JsonScalar | dict[str, JsonScalar] | None]:
    document_type = trace.trace_type
    event = event_by_id.get(trace.source_event_ids[0]) if trace.source_event_ids else None
    actor_id = event.actor_ids[0] if event and event.actor_ids else None
    character_ids = {character.id for character in world.characters}
    author_id = actor_id if actor_id in character_ids else None
    source_system_id = document_type if "log" in document_type or "report" in document_type else None
    style: dict[str, JsonScalar] = {
        "truth_mode": trace.truth_mode,
        "surface_noise_level": "medium" if trace.attributes.get("contextual") else "low",
        "omission_strategy": "state only the represented facts; omit hidden conclusions",
        "register": "administrative" if source_system_id else "personal",
    }

    def result(
        *,
        author_id: str | None,
        source_system_id: str | None,
        source_device_id: str | None,
        retrieval_location_id: str | None,
        witness_character_id: str | None,
        style: dict[str, JsonScalar],
    ) -> dict[str, JsonScalar | dict[str, JsonScalar] | None]:
        return {
            "author_id": author_id,
            "source_system_id": source_system_id,
            "source_device_id": source_device_id,
            "retrieval_location_id": retrieval_location_id or _fallback_location_id(world),
            "witness_character_id": witness_character_id,
            "style": style,
        }

    if document_type in ("sms", "call log", "gps report"):
        device = _phone_of(world, author_id)
        return result(
            author_id=author_id,
            source_system_id="mobile phone extraction",
            source_device_id=device.id if device else None,
            retrieval_location_id=device.location_id if device else None,
            witness_character_id=None,
            style={
                **style,
                "register": "private",
                "tone": "tense and elliptical",
                "relationship_context": "the sender expects the recipient to understand the implied meeting place",
            },
        )
    if document_type == "email":
        device = _device_of_type(world, "computer")
        return result(
            author_id=author_id,
            source_system_id="recovered mailbox",
            source_device_id=device.id if device else None,
            retrieval_location_id=device.location_id if device else None,
            witness_character_id=None,
            style={
                **style,
                "register": "personal correspondence",
                "tone": "controlled resentment",
                "relationship_context": "old grievance discussed through household business",
            },
        )
    if document_type == "access-control log":
        device = _device_of_type(world, "badge-reader")
        return result(
            author_id=None,
            source_system_id=source_system_id,
            source_device_id=device.id if device else None,
            retrieval_location_id=device.location_id if device else None,
            witness_character_id=None,
            style=style,
        )
    if document_type == "security report":
        device = _device_of_type(world, "camera-system")
        return result(
            author_id=None,
            source_system_id=source_system_id,
            source_device_id=device.id if device else None,
            retrieval_location_id=device.location_id if device else None,
            witness_character_id=None,
            style=style,
        )
    if document_type == "inventory report":
        device = _device_of_type(world, "archive-cabinet")
        return result(
            author_id=None,
            source_system_id=source_system_id,
            source_device_id=device.id if device else None,
            retrieval_location_id=device.location_id if device else None,
            witness_character_id=None,
            style=style,
        )
    if document_type == "witness interview":
        witness_id = author_id
        witness = next((character for character in world.characters if character.id == witness_id), None)
        return result(
            author_id=None,
            source_system_id="investigator interview notes",
            source_device_id=None,
            retrieval_location_id=witness.current_location_id if witness else None,
            witness_character_id=witness_id,
            style={
                **style,
                "register": "spoken transcript",
                "tone": "cautious and imperfect",
                "relationship_context": "witnesses speak from partial perception",
            },
        )
    # personal note, autopsy report, receipt, newspaper clipping, and any other
    # author-attributable type: a physical document found at the author's location.
    author = next((character for character in world.characters if character.id == author_id), None)
    return result(
        author_id=author_id,
        source_system_id="recovered personal papers" if document_type == "personal note" else source_system_id,
        source_device_id=None,
        retrieval_location_id=author.current_location_id if author else None,
        witness_character_id=None,
        style={
            **style,
            "register": "private note",
            "tone": "subjective and fragmentary",
        }
        if document_type == "personal note"
        else style,
    )

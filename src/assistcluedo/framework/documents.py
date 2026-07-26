from __future__ import annotations

from assistcluedo.framework.models import (
    DocumentPlan,
    Fact,
    GeneratedDocument,
    GroundTruth,
    Trace,
    World,
)
from assistcluedo.framework.naming import entity_name
from assistcluedo.framework.pack import Pack


class DocumentPlanner:
    def generate(self, traces: list[Trace]) -> list[DocumentPlan]:
        plans = []
        for index, trace in enumerate(traces, start=1):
            plans.append(
                DocumentPlan(
                    id=f"plan_{index:03d}",
                    document_type=trace.trace_type,
                    source_trace_ids=[trace.id],
                    mandatory_fact_ids=trace.fact_ids,
                    forbidden_fact_ids=["fact_culprit_identity"],
                    author_id=None,
                    source_system_id=trace.trace_type if "log" in trace.trace_type else None,
                    truth_mode=trace.truth_mode,
                    style={
                        "register": (
                            "administrative"
                            if "log" in trace.trace_type or "report" in trace.trace_type
                            else "personal"
                        )
                    },
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
    ) -> list[GeneratedDocument]:
        facts_by_id = {fact.id: fact for fact in facts}
        traces_by_id = {trace.id: trace for trace in traces}
        documents = []
        for index, plan in enumerate(plans, start=1):
            trace = traces_by_id[plan.source_trace_ids[0]]
            source_times = [
                fact.time
                for fact_id in trace.fact_ids
                if (fact := facts_by_id[fact_id]).time is not None
            ]
            created_at = max(source_times).isoformat() if source_times else truth.incident_time.isoformat()
            body = " ".join(
                _fact_sentence(world, facts_by_id[fact_id], truth)
                for fact_id in plan.mandatory_fact_ids
            )
            if trace.truth_mode == "deceptive":
                body += " Treat this statement cautiously: it conflicts with non-testimonial evidence."
            title = pack.document_titles.get(plan.document_type, plan.document_type.title())
            documents.append(
                GeneratedDocument(
                    id=f"doc_{index:03d}",
                    plan_id=plan.id,
                    title=title,
                    text=body,
                    visible_metadata={
                        "type": plan.document_type,
                        "reliability": trace.reliability,
                        "source": plan.source_system_id or "investigation file",
                        "created_at": created_at,
                    },
                    extracted_fact_ids=plan.mandatory_fact_ids,
                )
            )
        return documents


def _fact_sentence(world: World, fact: Fact, truth: GroundTruth) -> str:
    t = f" at {fact.time:%H:%M}" if fact.time else ""
    if fact.id == "fact_sms_meeting":
        return (
            f"{entity_name(world, fact.subject)} sent {entity_name(world, str(fact.object))} "
            f"a message asking for a private meeting{t}."
        )
    if fact.id == "fact_badge_access":
        return f"The badge assigned to {entity_name(world, fact.subject)} opened {entity_name(world, str(fact.object))}{t}."
    if fact.id == "fact_camera_disabled":
        return f"The camera covering {entity_name(world, truth.location_id)} was unavailable starting{t}."
    if fact.id == "fact_exculpated_alibi":
        return (
            f"{entity_name(world, fact.subject)} was seen in {entity_name(world, str(fact.object))}{t}, "
            "away from the incident location."
        )
    if fact.id == "fact_false_lead_argument":
        return f"{entity_name(world, fact.subject)} had a heated argument with {entity_name(world, str(fact.object))}{t}."
    if fact.id == "fact_false_statement":
        return (
            f"{entity_name(world, fact.subject)} claimed not to have been near "
            f"{entity_name(world, truth.location_id)} after dinner; automated records contradict that claim."
        )
    if fact.id == "fact_witness_seen_culprit":
        return (
            f"A witness saw {entity_name(world, fact.subject)} leaving the corridor outside "
            f"{entity_name(world, truth.location_id)}{t}."
        )
    if fact.id == "fact_death_window":
        return f"The medical estimate puts death in the window {fact.object}."
    if fact.id == "fact_murder_weapon":
        return f"The wound pattern is consistent with the {entity_name(world, str(fact.object))}."
    if fact.id == "fact_weapon_initial_location":
        return f"The {entity_name(world, fact.subject)} was normally kept in {entity_name(world, str(fact.object))}."
    if fact.id == "fact_weapon_hidden":
        return (
            f"The {entity_name(world, fact.subject)} was later found hidden in the "
            f"{entity_name(world, str(fact.object))}."
        )
    if fact.id == "fact_motive":
        return f"Records show {entity_name(world, fact.subject)} had a motive: {fact.object}."
    if fact.id.startswith("fact_ev_ctx_"):
        action = fact.predicate.removeprefix("context_").replace("_", " ")
        return (
            f"{entity_name(world, fact.subject)} appears in a {action} record"
            f"{t} near {entity_name(world, str(fact.object))}."
        )
    return f"{fact.subject} {fact.predicate} {fact.object}."

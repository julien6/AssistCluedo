from __future__ import annotations

from assistcluedo.framework.models import (
    DocumentPlan,
    Fact,
    GeneratedDocument,
    GroundTruth,
    JsonScalar,
    Trace,
    World,
)
from assistcluedo.framework.pack import Pack
from assistcluedo.framework.textgen import (
    SourceStyleCatalog,
    TextGenerationRequest,
    TextGenerator,
    generator_for,
)


class DocumentPlanner:
    def generate(self, traces: list[Trace]) -> list[DocumentPlan]:
        plans = []
        for index, trace in enumerate(traces, start=1):
            author_id, source_system_id, style = _plan_context_for(trace)
            plans.append(
                DocumentPlan(
                    id=f"plan_{index:03d}",
                    document_type=trace.trace_type,
                    source_trace_ids=[trace.id],
                    mandatory_fact_ids=trace.fact_ids,
                    forbidden_fact_ids=["fact_culprit_identity"],
                    author_id=author_id,
                    source_system_id=source_system_id,
                    truth_mode=trace.truth_mode,
                    style=style,
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
        documents = []
        for index, plan in enumerate(plans, start=1):
            trace = traces_by_id[plan.source_trace_ids[0]]
            source_times = [
                fact.time
                for fact_id in trace.fact_ids
                if (fact := facts_by_id[fact_id]).time is not None
            ]
            created_at = max(source_times).isoformat() if source_times else truth.incident_time.isoformat()
            title = pack.document_titles.get(plan.document_type, plan.document_type.title())
            request = TextGenerationRequest(
                document_id=f"doc_{index:03d}",
                title=title,
                plan=plan,
                trace=trace,
                world=world,
                truth=truth,
                facts=[facts_by_id[fact_id] for fact_id in plan.mandatory_fact_ids],
                created_at=created_at,
                source_style=style_catalog.profile_for(plan.document_type),
            )
            result = generator.generate(request)
            documents.append(
                GeneratedDocument(
                    id=f"doc_{index:03d}",
                    plan_id=plan.id,
                    title=result.title,
                    text=result.text,
                    visible_metadata={
                        "type": plan.document_type,
                        "reliability": trace.reliability,
                        "source": plan.source_system_id or "investigation file",
                        "created_at": created_at,
                        "text_provider": result.provider,
                        "fallback_used": result.fallback_used,
                    },
                    extracted_fact_ids=result.facts_expressed,
                )
            )
        return documents


def _plan_context_for(trace: Trace) -> tuple[str | None, str | None, dict[str, JsonScalar]]:
    document_type = trace.trace_type
    source_system_id = document_type if "log" in document_type or "report" in document_type else None
    style: dict[str, JsonScalar] = {
        "truth_mode": trace.truth_mode,
        "surface_noise_level": "medium" if trace.attributes.get("contextual") else "low",
        "omission_strategy": "state only the represented facts; omit hidden conclusions",
        "register": "administrative" if source_system_id else "personal",
    }
    if document_type == "sms":
        return None, "mobile phone extraction", {
            **style,
            "register": "private",
            "tone": "tense and elliptical",
            "relationship_context": "the sender expects the recipient to understand the implied meeting place",
        }
    if document_type == "email":
        return None, "recovered mailbox", {
            **style,
            "register": "personal correspondence",
            "tone": "controlled resentment",
            "relationship_context": "old grievance discussed through household business",
        }
    if document_type == "witness interview":
        return None, "investigator interview notes", {
            **style,
            "register": "spoken transcript",
            "tone": "cautious and imperfect",
            "relationship_context": "witnesses speak from partial perception",
        }
    if document_type == "personal note":
        return None, "recovered personal papers", {
            **style,
            "register": "private note",
            "tone": "subjective and fragmentary",
        }
    return None, source_system_id, style

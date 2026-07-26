from __future__ import annotations

from assistcluedo.framework.models import (
    Fact,
    GeneratedDocument,
    GroundTruth,
    ProofGraph,
    ProofLink,
)


class ProofGraphBuilder:
    def build(self, truth: GroundTruth, facts: list[Fact], documents: list[GeneratedDocument]) -> ProofGraph:
        doc_for_fact = {fact_id: doc.id for doc in documents for fact_id in doc.extracted_fact_ids}
        links = [
            ProofLink(
                "culprit",
                ["fact_sms_meeting", "fact_badge_access", "fact_witness_seen_culprit"],
                [
                    doc_for_fact["fact_sms_meeting"],
                    doc_for_fact["fact_badge_access"],
                    doc_for_fact["fact_witness_seen_culprit"],
                ],
                "The culprit summoned the victim, entered the incident location, and was seen leaving soon after.",
            ),
            ProofLink(
                "location",
                ["fact_badge_access", "fact_death_window"],
                [doc_for_fact["fact_badge_access"], doc_for_fact["fact_death_window"]],
                "Access and medical timing place the fatal incident at the same location.",
            ),
            ProofLink(
                "weapon",
                ["fact_murder_weapon", "fact_weapon_hidden"],
                [doc_for_fact["fact_murder_weapon"], doc_for_fact["fact_weapon_hidden"]],
                "The medical finding matches the missing weapon, which was hidden after the incident.",
            ),
            ProofLink(
                "false_lead",
                ["fact_false_lead_argument", "fact_false_statement"],
                [doc_for_fact["fact_false_lead_argument"], doc_for_fact["fact_false_statement"]],
                "The false lead had a motive-like argument but their account is not enough to overcome the physical evidence.",
            ),
            ProofLink(
                "alibi",
                ["fact_exculpated_alibi"],
                [doc_for_fact["fact_exculpated_alibi"]],
                "The alibi places this suspect away from the incident location near the relevant time.",
            ),
        ]
        return ProofGraph(links)


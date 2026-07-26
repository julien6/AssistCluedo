from __future__ import annotations

import random
from heapq import heappop, heappush

from assistcluedo.framework.difficulty import DifficultyConfig
from assistcluedo.framework.models import (
    Choice,
    Fact,
    GeneratedDocument,
    GroundTruth,
    ProofGraph,
    QuizQuestion,
    World,
)
from assistcluedo.framework.naming import entity_name
from assistcluedo.framework.seed import rng_for


class QuestionGenerator:
    def generate(
        self,
        seed: int,
        world: World,
        truth: GroundTruth,
        facts: list[Fact],
        documents: list[GeneratedDocument],
        proof_graph: ProofGraph,
        difficulty: DifficultyConfig,
    ) -> list[QuizQuestion]:
        rng = rng_for(seed, "quiz")
        culprit_choices, culprit_correct = _choice_set(
            ("correct", entity_name(world, truth.culprit_id)),
            [
                entity_name(world, truth.false_lead_character_id),
                entity_name(world, truth.exculpated_character_id),
                "Cannot be determined",
            ],
            rng,
        )
        location_distractors = [loc.name for loc in world.locations if loc.id != truth.location_id][:3]
        location_choices, location_correct = _choice_set(
            ("correct", entity_name(world, truth.location_id)),
            location_distractors,
            rng,
        )
        weapon_distractors = [
            obj.name for obj in world.objects if obj.id != truth.weapon_id
        ] + ["No weapon can be inferred"]
        weapon_choices, weapon_correct = _choice_set(
            ("correct", entity_name(world, truth.weapon_id)),
            weapon_distractors,
            rng,
        )
        alibi_choices, alibi_correct = _choice_set(
            ("correct", entity_name(world, truth.exculpated_character_id)),
            [
                entity_name(world, truth.culprit_id),
                entity_name(world, truth.false_lead_character_id),
                "General Hargreaves",
            ],
            rng,
        )
        source_choices, source_correct = _choice_set(
            ("correct", "Access-Control Log"),
            ["Personal Note", "Witness Interview denying activity", "Recovered Email"],
            rng,
        )
        ultimate_choices, ultimate_correct = _choice_set(
            ("correct", "Yes"),
            ["No", "Cannot be determined from the available evidence"],
            rng,
        )
        motive_choices, motive_correct = _choice_set(
            ("correct", truth.motive),
            [
                "a routine payroll dispute",
                "a mistaken invitation to dinner",
                "a disagreement about the garden schedule",
            ],
            rng,
        )
        false_lead_choices, false_lead_correct = _choice_set(
            ("correct", entity_name(world, truth.false_lead_character_id)),
            [
                entity_name(world, truth.culprit_id),
                entity_name(world, truth.exculpated_character_id),
                "No false lead exists",
            ],
            rng,
        )
        camera_choices, camera_correct = _choice_set(
            ("correct", "The camera covering the incident location was unavailable."),
            [
                "The autopsy report was forged.",
                "The weapon was never recovered.",
                "The victim left the manor before dinner.",
            ],
            rng,
        )
        death_window = next(fact.object for fact in facts if fact.id == "fact_death_window")
        death_window_choices, death_window_correct = _choice_set(
            ("correct", str(death_window)),
            ["20:05-20:13", "20:27-20:35", "22:10-22:18"],
            rng,
        )
        alibi_fact = next(fact for fact in facts if fact.id == "fact_exculpated_alibi")
        travel_minutes = _shortest_travel_minutes(world)
        required_minutes = travel_minutes.get((str(alibi_fact.object), truth.location_id), 0)
        actual_minutes = int((truth.incident_time - alibi_fact.time).total_seconds() // 60) if alibi_fact.time else 0
        can_reach = actual_minutes >= required_minutes
        travel_correct_text = (
            f"Yes, the route needs about {required_minutes} minutes and there are {actual_minutes} minutes available."
            if can_reach
            else f"No, the route needs about {required_minutes} minutes but only {actual_minutes} minutes are available."
        )
        travel_choices, travel_correct = _choice_set(
            ("correct", travel_correct_text),
            [
                "Yes, because every room is adjacent.",
                "No, because no route exists in the manor.",
                "Cannot be reasoned about from the available documents.",
            ],
            rng,
        )
        questions = [
            QuizQuestion(
                "q1",
                "factual",
                "Who is best supported as the culprit?",
                culprit_choices,
                culprit_correct,
                ["fact_sms_meeting", "fact_badge_access", "fact_witness_seen_culprit"],
                _docs_for(proof_graph, "culprit"),
                0.5,
                "The matching SMS, access record, and sighting point to the same person.",
            ),
            QuizQuestion(
                "q2",
                "factual",
                "Where did the main incident occur?",
                location_choices,
                location_correct,
                ["fact_badge_access", "fact_death_window"],
                _docs_for(proof_graph, "location"),
                0.4,
                "The access record and medical timing support the incident location.",
            ),
            QuizQuestion(
                "q3",
                "causal",
                "Which object was the murder weapon?",
                weapon_choices,
                weapon_correct,
                ["fact_murder_weapon", "fact_weapon_hidden"],
                _docs_for(proof_graph, "weapon"),
                0.5,
                "The autopsy describes the weapon type and the inventory report shows where it was hidden.",
            ),
            QuizQuestion(
                "q4",
                "hypothesis elimination",
                "Which suspect has the strongest alibi?",
                alibi_choices,
                alibi_correct,
                ["fact_exculpated_alibi"],
                _docs_for(proof_graph, "alibi"),
                0.4,
                "The alibi document places this suspect away from the incident location at the key time.",
            ),
            QuizQuestion(
                "q5",
                "source assessment",
                "Which document gives the most direct automated evidence of entry into the incident location?",
                source_choices,
                source_correct,
                ["fact_badge_access"],
                [doc.id for doc in documents if "fact_badge_access" in doc.extracted_fact_ids],
                0.3,
                "The access-control log is automated and directly records entry.",
            ),
            QuizQuestion(
                "q6",
                "ultimate statement",
                f"Did {entity_name(world, truth.culprit_id)} kill {entity_name(world, truth.victim_id)} on Sunday, August 9, in {entity_name(world, truth.location_id)}?",
                ultimate_choices,
                ultimate_correct,
                ["fact_culprit_identity", "fact_murder_location"],
                list(dict.fromkeys(_docs_for(proof_graph, "culprit") + _docs_for(proof_graph, "location"))),
                0.6,
                "The statement matches the symbolic ground truth and is supported by the evidence chain.",
            ),
        ]
        questions.extend(
            [
                QuizQuestion(
                    "q7",
                    "causal",
                    "What motive is supported by the recovered records?",
                    motive_choices,
                    motive_correct,
                    ["fact_motive"],
                    [doc.id for doc in documents if "fact_motive" in doc.extracted_fact_ids],
                    0.6,
                    "The recovered email documents the pressure behind the killing.",
                ),
                QuizQuestion(
                    "q8",
                    "hypothesis elimination",
                    "Who is the main false lead?",
                    false_lead_choices,
                    false_lead_correct,
                    ["fact_false_lead_argument", "fact_false_statement"],
                    _docs_for(proof_graph, "false_lead"),
                    0.6,
                    "This person looks suspicious because of the argument and deceptive statement, but the stronger physical chain points elsewhere.",
                ),
                QuizQuestion(
                    "q9",
                    "source assessment",
                    "What explains the missing direct camera footage?",
                    camera_choices,
                    camera_correct,
                    ["fact_camera_disabled"],
                    [doc.id for doc in documents if "fact_camera_disabled" in doc.extracted_fact_ids],
                    0.5,
                    "The security report says the relevant camera was unavailable during the key interval.",
                ),
                QuizQuestion(
                    "q10",
                    "temporal",
                    "What death window is supported by the autopsy?",
                    death_window_choices,
                    death_window_correct,
                    ["fact_death_window"],
                    [doc.id for doc in documents if "fact_death_window" in doc.extracted_fact_ids],
                    0.5,
                    "The autopsy gives the medical estimate for the death window.",
                ),
                QuizQuestion(
                    "q11",
                    "temporal",
                    f"Could {entity_name(world, truth.exculpated_character_id)} travel from {entity_name(world, str(alibi_fact.object))} to {entity_name(world, truth.location_id)} before the incident?",
                    travel_choices,
                    travel_correct,
                    ["fact_exculpated_alibi", "fact_death_window", "fact_murder_location"],
                    list(
                        dict.fromkeys(
                            _docs_for(proof_graph, "alibi") + _docs_for(proof_graph, "location")
                        )
                    ),
                    0.7,
                    "The alibi time, death window, and manor travel graph determine whether the movement is physically compatible.",
                ),
            ]
        )
        contextual_docs = [
            doc
            for doc in documents
            if any(fact_id.startswith("fact_ev_ctx_") for fact_id in doc.extracted_fact_ids)
        ]
        for index, doc in enumerate(contextual_docs[: max(0, difficulty.questions - 11)], start=12):
            fact_id = doc.extracted_fact_ids[0]
            fact = next(fact for fact in facts if fact.id == fact_id)
            correct_text = f"{entity_name(world, fact.subject)} near {entity_name(world, str(fact.object))}"
            distractors = [
                f"{entity_name(world, truth.culprit_id)} near {entity_name(world, truth.location_id)}",
                f"{entity_name(world, truth.false_lead_character_id)} near {entity_name(world, truth.location_id)}",
                "No contextual record can be read",
            ]
            choices, correct = _choice_set(("correct", correct_text), distractors, rng)
            questions.append(
                QuizQuestion(
                    f"q{index}",
                    "factual",
                    f"What does {doc.title} #{doc.id} report?",
                    choices,
                    correct,
                    [fact_id],
                    [doc.id],
                    0.7,
                    "This answer is read from a contextual document; it may not identify the culprit.",
                )
            )
        return questions[: difficulty.questions]


def _choice_set(
    correct: tuple[str, str], distractors: list[str], rng: random.Random
) -> tuple[list[Choice], list[str]]:
    texts = [correct[1]]
    for text in distractors:
        if text != correct[1] and text not in texts:
            texts.append(text)
        if len(texts) == 4:
            break
    choices = [Choice(f"c{index}", text) for index, text in enumerate(texts, start=1)]
    correct_id = choices[0].id
    rng.shuffle(choices)
    return choices, [correct_id]


def _docs_for(proof_graph: ProofGraph, conclusion: str) -> list[str]:
    for link in proof_graph.links:
        if link.conclusion == conclusion:
            return link.document_ids
    return []


def _shortest_travel_minutes(world: World) -> dict[tuple[str, str], int]:
    location_ids = {loc.id for loc in world.locations}
    graph: dict[str, list[tuple[str, int]]] = {location_id: [] for location_id in location_ids}
    for edge in world.travel_edges:
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

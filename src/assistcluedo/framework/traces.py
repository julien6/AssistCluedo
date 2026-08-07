from __future__ import annotations

from assistcluedo.framework.models import Event, Fact, GroundTruth, Trace


class TraceGenerator:
    def generate(self, seed: int, facts: list[Fact], events: list[Event], truth: GroundTruth) -> list[Trace]:
        traces = [
            Trace("trace_sms", "sms", ["ev_003"], ["fact_sms_meeting"], 0.95, 0.95, "accurate", {}),
            Trace(
                "trace_access",
                "access-control log",
                ["ev_004"],
                ["fact_badge_access"],
                1.0,
                0.98,
                "accurate",
                {},
            ),
            Trace(
                "trace_camera",
                "security report",
                ["ev_005"],
                ["fact_camera_disabled"],
                0.9,
                0.9,
                "incomplete",
                {},
            ),
            Trace(
                "trace_alibi",
                "witness interview",
                ["ev_006_alibi_witness"],
                ["fact_exculpated_alibi"],
                0.85,
                0.9,
                "accurate",
                {},
            ),
            Trace(
                "trace_argument",
                "personal note",
                ["ev_002"],
                ["fact_false_lead_argument"],
                0.75,
                0.85,
                "accurate",
                {},
            ),
            Trace(
                "trace_false_statement",
                "witness interview",
                ["ev_010_false_statement_witness"],
                ["fact_false_statement"],
                0.35,
                0.8,
                "deceptive",
                {},
            ),
            Trace(
                "trace_witness",
                "witness interview",
                ["ev_009"],
                ["fact_witness_seen_culprit"],
                0.8,
                0.85,
                "accurate",
                {},
            ),
            Trace(
                "trace_autopsy",
                "autopsy report",
                ["ev_012"],
                ["fact_death_window", "fact_murder_weapon"],
                0.98,
                0.98,
                "accurate",
                {},
            ),
            Trace(
                "trace_inventory",
                "inventory report",
                ["ev_008"],
                ["fact_weapon_initial_location", "fact_weapon_hidden"],
                0.9,
                0.9,
                "accurate",
                {},
            ),
            Trace("trace_motive", "email", ["ev_002"], ["fact_motive"], 0.8, 0.85, "accurate", {}),
        ]
        trace_types = ["gps report", "receipt", "call log", "newspaper clipping"]
        contextual_events = [event for event in events if event.attributes.get("contextual")]
        for index, event in enumerate(contextual_events, start=1):
            reliability = 0.55 + ((index % 5) * 0.08)
            traces.append(
                Trace(
                    id=f"trace_ctx_{index:03d}",
                    trace_type=trace_types[index % len(trace_types)],
                    source_event_ids=[event.id],
                    fact_ids=[f"fact_{event.id}"],
                    reliability=round(min(reliability, 0.92), 2),
                    authenticity=0.9,
                    truth_mode="irrelevant" if index % 3 else "accurate",
                    attributes={"contextual": True},
                )
            )
        return traces

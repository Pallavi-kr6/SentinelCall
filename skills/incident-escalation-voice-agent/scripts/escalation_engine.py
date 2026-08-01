"""
Escalation engine: given a triaged alert and a responder directory, calls one
tier at a time through CalleClient, escalating to the next tier only when the
current attempt reaches a terminal, unconfirmed state.

Confirmed  -> structured_result["can_dispatch"] == "yes"
Escalate   -> "no", "unknown", not-answered, declined, or needs_escalation
Exhausted  -> ran out of tiers -> "unresolved_escalated"
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from calle_client import CalleClient, mask_phone
from triage_engine import triage

MAX_TIERS = 3

RESULT_SCHEMA = {
    "type": "object",
    "required": ["can_dispatch"],
    "properties": {
        "can_dispatch": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "eta_minutes": {"type": "integer"},
        "alternate_contact": {"type": "string"},
        "needs_escalation": {"type": "boolean"},
    },
    "additionalProperties": False,
}


@dataclass
class AttemptRecord:
    tier: str
    responder_name: str
    responder_phone_masked: str
    call_id: str
    status: str
    structured_result: dict[str, Any] | None
    timestamp: float


@dataclass
class IncidentRecord:
    alert_id: str
    hazard_type: str
    zone: str
    confidence: float
    outcome: str  # "no_call_low_confidence" | "resolved_confirmed" | "unresolved_escalated"
    attempts: list[AttemptRecord] = field(default_factory=list)

    def to_json(self) -> dict:
        d = asdict(self)
        return d


_IN_FLIGHT: set[str] = set()  # alert_id guard against duplicate escalation chains


def build_task_prompt(alert: dict, tier_role: str) -> str:
    return (
        f"Call the on-call {tier_role.replace('_', ' ')} and report a detected "
        f"{alert['hazard_type'].replace('_', ' ')} in zone {alert['zone']} "
        f"(detection confidence {float(alert['confidence']) * 100:.0f}%, "
        f"source {alert.get('source', 'unspecified')}, "
        f"detected at {alert.get('detected_at', 'unspecified time')}). "
        f"Ask them to confirm whether they can dispatch a response now, and "
        f"if not, ask for an estimated time or an alternate contact."
    )


def run_escalation(alert: dict, responder_directory: dict, client: CalleClient) -> IncidentRecord:
    alert_id = alert["alert_id"]
    if alert_id in _IN_FLIGHT:
        raise RuntimeError(f"Escalation already in progress for alert_id={alert_id!r}; refusing duplicate chain.")
    _IN_FLIGHT.add(alert_id)

    try:
        decision = triage(alert)
        record = IncidentRecord(
            alert_id=alert_id,
            hazard_type=alert["hazard_type"],
            zone=alert["zone"],
            confidence=float(alert["confidence"]),
            outcome="no_call_low_confidence",
        )

        if not decision.should_call:
            return record

        zone_roster = responder_directory.get(alert["zone"], {})
        tiers_to_try = decision.tiers[:MAX_TIERS]

        for tier in tiers_to_try:
            responder = zone_roster.get(tier)
            if not responder:
                # Missing roster entry: stop and surface the exact blocker,
                # never guess a number.
                record.outcome = "unresolved_escalated"
                record.attempts.append(
                    AttemptRecord(
                        tier=tier,
                        responder_name="(no roster entry)",
                        responder_phone_masked="—",
                        call_id="",
                        status="skipped_missing_roster_entry",
                        structured_result=None,
                        timestamp=time.time(),
                    )
                )
                continue

            task = build_task_prompt(alert, tier)
            idempotency_key = f"incident:{alert_id}:tier:{tier}"
            outcome = client.place_escalation_call(
                task=task,
                phone=responder["phone"],
                region=responder.get("region", "IN"),
                locale=responder.get("locale", "en-IN"),
                result_schema=RESULT_SCHEMA,
                metadata={"alert_id": alert_id, "tier": tier},
                idempotency_key=idempotency_key,
            )

            record.attempts.append(
                AttemptRecord(
                    tier=tier,
                    responder_name=responder.get("name", "(unnamed)"),
                    responder_phone_masked=mask_phone(responder["phone"]),
                    call_id=outcome.call_id,
                    status=outcome.status,
                    structured_result=outcome.structured_result,
                    timestamp=time.time(),
                )
            )

            confirmed = (
                outcome.structured_result is not None
                and outcome.structured_result.get("can_dispatch") == "yes"
                and not outcome.structured_result.get("needs_escalation", False)
            )
            if confirmed:
                record.outcome = "resolved_confirmed"
                return record
            # otherwise: fall through and try the next tier

        record.outcome = "unresolved_escalated"
        return record
    finally:
        _IN_FLIGHT.discard(alert_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run escalation for one alert JSON object (stdin or --alert-json).")
    parser.add_argument("--alert-json", help="Inline JSON alert. Reads stdin if omitted.")
    parser.add_argument("--roster", default="../assets/responder_directory.sample.json")
    parser.add_argument("--live", action="store_true", help="Place real CALL-E calls (requires CALLE_API_KEY).")
    args = parser.parse_args()

    alert_text = args.alert_json or __import__("sys").stdin.read()
    alert_obj = json.loads(alert_text)
    with open(args.roster) as f:
        roster = json.load(f)

    calle = CalleClient(dry_run=not args.live)
    result = run_escalation(alert_obj, roster, calle)
    print(json.dumps(result.to_json(), indent=2))

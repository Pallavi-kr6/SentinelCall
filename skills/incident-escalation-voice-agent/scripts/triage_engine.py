"""
Triage engine: decides (a) whether an alert clears the confidence floor to be
worth a phone call at all, and (b) which ordered responder tiers to try.

See references/escalation-policy.md for the policy this implements. All
thresholds are operator-tunable defaults, not certified safety values.
"""

from __future__ import annotations

from dataclasses import dataclass

# hazard_type -> (confidence floor to call at all, tier list to escalate through)
SEVERITY_POLICY: dict[str, dict] = {
    "fire": {"floor": 0.85, "tiers": ["zone_warden", "district_control_room", "regional_liaison"]},
    "gas_leak": {"floor": 0.85, "tiers": ["zone_warden", "district_control_room", "regional_liaison"]},
    "structural_collapse": {"floor": 0.85, "tiers": ["zone_warden", "district_control_room", "regional_liaison"]},
    "flood": {"floor": 0.75, "tiers": ["zone_warden", "district_control_room"]},
    "landslide": {"floor": 0.75, "tiers": ["zone_warden", "district_control_room"]},
    "smoke": {"floor": 0.75, "tiers": ["zone_warden", "district_control_room"]},
    "intrusion": {"floor": 0.60, "tiers": ["zone_warden"]},
    "equipment_fault": {"floor": 0.60, "tiers": ["zone_warden"]},
}
DEFAULT_POLICY = {"floor": 0.60, "tiers": ["zone_warden"]}


@dataclass
class TriageDecision:
    should_call: bool
    reason: str
    tiers: list[str]


def triage(alert: dict) -> TriageDecision:
    hazard_type = alert.get("hazard_type", "")
    confidence = float(alert.get("confidence", 0.0))
    policy = SEVERITY_POLICY.get(hazard_type, DEFAULT_POLICY)

    if confidence < policy["floor"]:
        return TriageDecision(
            should_call=False,
            reason=(
                f"confidence {confidence:.2f} below call-worthiness floor "
                f"{policy['floor']:.2f} for hazard_type={hazard_type!r}; "
                f"routed to dashboard review instead of a phone call"
            ),
            tiers=[],
        )

    return TriageDecision(
        should_call=True,
        reason=f"confidence {confidence:.2f} clears floor {policy['floor']:.2f}",
        tiers=list(policy["tiers"]),
    )

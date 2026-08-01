"""
Validates a hazard alert dict against the fields this skill requires.
Mirrors the shape of the repo's `validate-reminder-input.mjs`: returns
{"ok": True, "value": alert} or {"ok": False, "errors": [...]}.
"""

from __future__ import annotations

import json
import sys

REQUIRED_FIELDS = {
    "alert_id": str,
    "hazard_type": str,
    "zone": str,
    "confidence": (int, float),
    "detected_at": str,
    "source": str,
}


def validate_alert(alert: dict) -> dict:
    errors: list[str] = []

    if not isinstance(alert, dict):
        return {"ok": False, "errors": ["alert must be a JSON object"]}

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in alert:
            errors.append(f"missing required field: {field}")
            continue
        if not isinstance(alert[field], expected_type):
            errors.append(f"field {field!r} has wrong type (expected {expected_type})")

    if "confidence" in alert and isinstance(alert["confidence"], (int, float)):
        if not (0.0 <= float(alert["confidence"]) <= 1.0):
            errors.append("confidence must be between 0.0 and 1.0")

    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "value": alert}


if __name__ == "__main__":
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    parsed = json.loads(raw)
    print(json.dumps(validate_alert(parsed), indent=2))

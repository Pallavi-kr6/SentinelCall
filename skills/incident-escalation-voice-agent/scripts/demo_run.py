#!/usr/bin/env python3
"""
End-to-end demo: reads a JSONL file of hazard alerts, validates each one,
runs it through triage + escalation, and prints a clean console log.

Safe by default: runs in dry-run (simulated calls) unless --live is passed
AND CALLE_API_KEY is set. No real phone call happens otherwise.

Usage:
    python demo_run.py --alerts ../../examples/sample_alerts.jsonl
    python demo_run.py --alerts ../../examples/sample_alerts.jsonl --live
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from calle_client import CalleClient
from escalation_engine import run_escalation
from validate_alert_input import validate_alert

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
DIM = "\033[2m"


def _color_for_outcome(outcome: str) -> str:
    return {
        "resolved_confirmed": GREEN,
        "unresolved_escalated": RED,
        "no_call_low_confidence": YELLOW,
    }.get(outcome, RESET)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the incident escalation demo over a set of alerts.")
    parser.add_argument("--alerts", required=True, help="Path to a JSONL file of alerts.")
    parser.add_argument(
        "--roster",
        default=os.path.join(os.path.dirname(__file__), "..", "assets", "responder_directory.sample.json"),
    )
    parser.add_argument("--live", action="store_true", help="Place real CALL-E calls (requires CALLE_API_KEY).")
    args = parser.parse_args()

    if args.live and not os.environ.get("CALLE_API_KEY"):
        print(f"{RED}--live was passed but CALLE_API_KEY is not set. Falling back to dry-run.{RESET}\n")

    with open(args.roster) as f:
        roster = json.load(f)

    client = CalleClient(dry_run=not (args.live and os.environ.get("CALLE_API_KEY")))
    mode = "LIVE (real CALL-E calls)" if not client.dry_run else "DRY-RUN (simulated, no real calls)"
    print(f"{BOLD}SentinelCall demo — mode: {mode}{RESET}\n")

    with open(args.alerts) as f:
        lines = [line for line in f if line.strip()]

    for raw_line in lines:
        alert = json.loads(raw_line)
        v = validate_alert(alert)
        print(f"{BOLD}--- alert {alert.get('alert_id', '?')} ---{RESET}")
        if not v["ok"]:
            print(f"{RED}  invalid alert, skipped: {v['errors']}{RESET}\n")
            continue

        record = run_escalation(alert, roster, client)
        color = _color_for_outcome(record.outcome)
        print(f"  hazard_type={record.hazard_type} zone={record.zone} confidence={record.confidence:.2f}")

        if not record.attempts:
            print(f"  {DIM}no call placed — below confidence floor, routed to dashboard for human review{RESET}")

        for a in record.attempts:
            result_str = json.dumps(a.structured_result) if a.structured_result else "null"
            print(f"  tier={a.tier:<20} responder={a.responder_name:<18} phone={a.responder_phone_masked:<14} "
                  f"status={a.status:<10} result={result_str}")

        print(f"  {color}{BOLD}outcome: {record.outcome}{RESET}\n")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Incident Ops Console — a small, demo-grade FastAPI app that ingests hazard
alerts, runs them through the incident-escalation-voice-agent skill, and
serves a live dashboard of incident status.

This is a runnable demo, not a production app: no auth, no database (an
in-memory list only), and it runs in dry-run (simulated calls) by default.
See skills/incident-escalation-voice-agent/references/safety.md before
pointing it at a real responder directory or CALLE_API_KEY.

Run:
    pip install -r requirements.txt
    python server.py
    # open http://localhost:8000
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

SKILL_SCRIPTS = Path(__file__).resolve().parents[3] / "skills" / "incident-escalation-voice-agent" / "scripts"
SKILL_ASSETS = Path(__file__).resolve().parents[3] / "skills" / "incident-escalation-voice-agent" / "assets"
sys.path.insert(0, str(SKILL_SCRIPTS))

from calle_client import CalleClient  # noqa: E402
from escalation_engine import run_escalation  # noqa: E402
from validate_alert_input import validate_alert  # noqa: E402

app = FastAPI(title="SentinelCall Incident Ops Console")

DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
ROSTER_PATH = SKILL_ASSETS / "responder_directory.sample.json"

_INCIDENTS: list[dict] = []  # in-memory only — demo-grade, not persistent
_client = CalleClient(dry_run=not os.environ.get("CALLE_API_KEY"))


def _load_roster() -> dict:
    with open(ROSTER_PATH) as f:
        return json.load(f)


@app.get("/")
def dashboard_index():
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/incidents")
def list_incidents():
    return JSONResponse(_INCIDENTS)


@app.post("/alerts/ingest")
async def ingest_alert(request: Request):
    alert = await request.json()
    v = validate_alert(alert)
    if not v["ok"]:
        return JSONResponse({"ok": False, "errors": v["errors"]}, status_code=422)

    roster = _load_roster()
    record = run_escalation(alert, roster, _client)
    incident = record.to_json()
    incident["received_at"] = time.time()
    _INCIDENTS.insert(0, incident)  # newest first
    return JSONResponse({"ok": True, "incident": incident})


@app.post("/calle/webhook")
async def calle_webhook(request: Request):
    """
    Terminal call-result webhook receiver, for when this app is wired to a
    live CALL-E call's `webhook_url` instead of (or in addition to) the
    synchronous create_and_wait path used by escalation_engine.py.
    Demo-grade: logs the payload against the matching incident by
    metadata.alert_id if present. Does not verify a webhook signature —
    add that before using this endpoint outside a demo.
    """
    payload = await request.json()
    alert_id = (payload.get("metadata") or {}).get("alert_id")
    for incident in _INCIDENTS:
        if incident.get("alert_id") == alert_id:
            incident.setdefault("webhook_events", []).append(payload)
            break
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

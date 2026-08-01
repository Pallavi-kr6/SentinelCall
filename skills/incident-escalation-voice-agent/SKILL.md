---
name: incident-escalation-voice-agent
description: Turns a hazard-detection alert (from a computer-vision pipeline, a sensor, or a manual report) into a phone escalation chain over CALL-E. Calls the on-call responder for the affected zone, asks them to confirm dispatch, and automatically tries the next tier of a pre-authorized duty roster if nobody confirms. Use for service dispatch and incident-escalation workflows, not for contacting the public or emergency services.
---

# Incident Escalation Voice Agent

Detection systems (CCTV fire/smoke models, flood or structural-strain
sensors, satellite hazard feeds, or a person filing a report) are good at
noticing something is wrong. They are not good at making sure a specific
human being picks up a phone, hears the details, and confirms they're
handling it. That last step — turning a flagged event into a confirmed
human response — is what this skill automates using CALL-E.

This skill does **not** replace a detection system, a control room, or a
public emergency line. It is the calling leg that sits between "something
was flagged" and "a designated on-call person has been reached and has
confirmed what happens next."

## Use it for

- Notifying an on-call safety officer, facility manager, or ward/zone duty
  contact that a hazard was detected, and getting a same-call yes/no on
  whether they can dispatch a response.
- Escalating automatically through a pre-defined duty roster (Tier 1 → Tier
  2 → Tier 3) when a responder doesn't answer, doesn't confirm, or declines.
- Producing a structured, auditable record of who was called, in what
  order, what they were told, and what they confirmed.
- Any similar "detected event → verified human response" workflow: security
  patrol dispatch, facilities/maintenance callouts, community-watch alerts,
  equipment-failure callouts.

## Do not use it to

- Call public emergency numbers (police, fire, ambulance, disaster helplines
  such as 911 / 112 / 100 / 108). Those calls must be placed by a human
  through the official emergency line — this skill is a duty-roster
  notifier, not an emergency dispatcher.
- Contact members of the public, bystanders, or anyone who has not already
  agreed to be on the operator's own on-call/duty roster.
- Infer who to call or what number to use from image content, GPS, or
  device metadata. The responder directory is supplied and maintained by
  the operator, not guessed by the agent.
- Decide, on its own, whether a detected hazard is real. Confidence
  thresholds only gate *whether a call is worth placing*; a human on the
  phone always makes the actual judgment call.
- Create hidden or duplicate escalation chains for the same alert. Every
  tier that gets called is written to the audit trail before the next call
  is placed.

## How it works

```
alert  ->  triage_engine.py   -> severity + ordered responder tiers
       ->  escalation_engine.py -> calle_client.py -> CALL-E (plan_call / run_call)
                                                  -> structured result (can_dispatch, eta, alt_contact)
       -> confirmed?  yes -> stop, log resolution
                      no / no-answer / declined / timed-out -> call next tier
```

1. **Triage** (`scripts/triage_engine.py`) reads the alert (`hazard_type`,
   `confidence`, `zone`, `detected_at`, `source`) and decides: (a) whether
   confidence clears the call-worthy floor at all — low-confidence alerts
   are routed to the dashboard for human review instead of a phone call, and
   (b) which ordered list of responder tiers from the directory should be
   tried.
2. **Escalation** (`scripts/escalation_engine.py`) places one call at a time
   through `scripts/calle_client.py`, using a task prompt built from the
   alert and a strict `result_schema` (see below). It only calls the next
   tier after the current one fails to confirm — never in parallel, and
   never more than the configured number of tiers.
3. **Result schema** every call asks CALL-E to return:
   ```json
   {
     "type": "object",
     "required": ["can_dispatch"],
     "properties": {
       "can_dispatch": {"type": "string", "enum": ["yes", "no", "unknown"]},
       "eta_minutes": {"type": "integer"},
       "alternate_contact": {"type": "string"},
       "needs_escalation": {"type": "boolean"}
     }
   }
   ```
4. **Audit trail** every attempt (tier, masked phone, call status, structured
   result, timestamp) is appended to the incident record before the next
   step runs — nothing is retried or escalated silently.

## Setup

1. Provide a responder directory: a JSON file mapping `zone -> ordered
   tiers -> {name, phone, role}` for people who have already agreed to
   receive duty calls. See `assets/responder_directory.sample.json` for the
   shape (uses fictional reserved numbers — replace with your own roster's
   real E.164 numbers before going live).
2. Set `CALLE_API_KEY` (see the
   [CALL-E install guide](https://open.heycall-e.com/document/mcp-archive/CALL-E-installation-guide.md)).
   Without it, everything runs in deterministic dry-run mode.
3. Run `scripts/demo_run.py` against `examples/sample_alerts.jsonl` to see
   the full triage → call → escalate loop before connecting a real detector
   or a real roster.

## Example prompts

```
Use incident-escalation-voice-agent to handle this alert:
hazard_type=fire, zone=warehouse-4, confidence=0.94, source=cctv-cam-12
Start in dry-run and show me the full escalation trail before placing any real call.
```

```
Wire incident-escalation-voice-agent to our flood-sensor webhook for the
Ward 7 river gauge. Responders are the three names in
assets/responder_directory.sample.json — replace them with our real ward
officer roster first, and confirm each one has agreed to receive duty calls
before this goes live.
```

## Files in this skill

| File | Purpose |
| --- | --- |
| `scripts/calle_client.py` | Thin wrapper over the CALL-E Calls API / SDK, with a seeded dry-run mock. |
| `scripts/triage_engine.py` | Confidence gating and responder-tier selection. |
| `scripts/escalation_engine.py` | Sequential call-and-escalate state machine and audit trail. |
| `scripts/validate_alert_input.py` | Validates an incoming alert against the required schema. |
| `scripts/demo_run.py` | End-to-end CLI demo over `examples/sample_alerts.jsonl`. |
| `references/escalation-policy.md` | Severity tiers, confidence floors, and escalation timing rules. |
| `references/safety.md` | Full safety contract (consent, emergency-number boundary, credential handling). |
| `assets/responder_directory.sample.json` | Fictional sample on-call roster. |

Read `references/safety.md` before pointing this at a real roster.

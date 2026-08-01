# Safety Reference — Incident Escalation Voice Agent

Phone calls placed by this skill are real-world side effects to real
people, often about hazards. These rules are non-negotiable and apply to
`scripts/`, `assets/responder_directory.sample.json`, the demo app in
`apps/python/incident-ops-console`, and any generated variant of this skill.

## Who this skill is allowed to call

- Only numbers present in an operator-maintained, operator-owned responder
  directory (on-call staff, duty officers, facility managers, ward/zone
  contacts) who have already agreed — as part of their role — to receive
  duty calls. This is the same consent basis as an existing pager or
  on-call phone system; this skill does not create a new consent
  relationship on its own.
- Never a member of the public, a bystander, or anyone whose number was
  inferred from image content, device metadata, GPS, or guesswork.
- Never a public emergency number (police, fire, ambulance, disaster
  helplines). If a detected hazard requires an emergency-service call, that
  call must be placed by a human through the official emergency line — this
  skill's job ends at reaching the operator's own on-call roster.

## Treat this as logistics, not judgment

This skill's calls confirm *whether a designated human can dispatch a
response* — they do not diagnose the hazard, and they do not replace a
human's judgment about severity or the right response. Confidence
thresholds only gate whether a call is worth placing (see
`escalation-policy.md`); the phone conversation, and the person on the other
end, remain the actual decision-makers.

## Data handling

- Phone numbers are masked in any dashboard, log line, or summary shown to
  a user (`+1555•••1234`), and demo/documentation numbers use the reserved
  fictional block (`+15550101234`-style) only.
- API keys, OAuth tokens, and webhook secrets are read from environment
  variables only. Nothing in `scripts/` or `apps/` prints or logs a raw
  credential.
- If `CALLE_API_KEY` is missing, the CLI is unavailable, or a required alert
  field is missing or ambiguous, the skill stops and reports the exact
  blocker — it never guesses a phone number, zone, or hazard type.

## Escalation integrity

- One call in flight per incident; the next tier is only dialed after the
  current attempt reaches a terminal state.
- A hard cap on the number of tiers tried (default 3) prevents an unresolved
  incident from calling indefinitely.
- Every attempt is appended to the incident's audit trail *before* the next
  call is placed — there is no retry or escalation that isn't visible in
  the trail.
- No duplicate escalation chains for the same alert ID; `escalation_engine.py`
  keys in-flight incidents by `alert_id` and refuses to start a second chain
  for one already in progress.

## Going live checklist

- [ ] Responder directory contains only your own organization's on-call
      staff, with real E.164 numbers, and every person listed has agreed to
      receive duty calls.
- [ ] Confidence floors in `escalation-policy.md` are set from your
      detector's own validated precision, not the defaults.
- [ ] `CALLE_API_KEY` is set as an environment variable, never committed to
      source control.
- [ ] You've read and accept CALL-E's own terms and regional-calling
      support for every zone in your roster.
- [ ] Someone owns monitoring the incident-ops-console dashboard; this
      skill notifies, it does not supervise itself.

# Escalation Policy Reference

This document defines the default severity model and escalation timing used
by `triage_engine.py` and `escalation_engine.py`. It is a starting policy,
not a fixed standard — operators should tune the thresholds and tier
ordering to their own detection system and duty roster.

## Why a confidence floor exists

Vision-based hazard detectors trade recall for false alarms. Published
results on CCTV fire/smoke detection show single-frame false-alarm rates
above 50% before temporal confirmation, and well-tuned multi-model pipelines
still report false-alarm rates in the single digits after confirmation
logic is applied. A phone escalation chain that fires on every raw detector
frame would train responders to stop trusting it within days. This skill
therefore treats the confidence score as a **call-worthiness gate**, not a
severity score by itself:

- **Below the floor (default `0.60`)**: no call is placed. The alert is
  logged for dashboard review only.
- **At or above the floor**: a call is placed, but the phone conversation —
  not the detector — is what actually confirms the hazard. The result
  schema's `can_dispatch` field is the real decision point.

## Default severity tiers

| Hazard type | Confidence for Tier-1 call | Escalation trigger |
| --- | --- | --- |
| `fire`, `gas_leak`, `structural_collapse` | ≥ 0.85 | no answer, decline, or `can_dispatch != yes` within one call attempt |
| `flood`, `landslide`, `smoke` | ≥ 0.75 | no answer, decline, `can_dispatch != yes`, or `needs_escalation == true` |
| `intrusion`, `equipment_fault`, other | ≥ 0.60 | no answer or decline only |

These are starting values, not a safety certification — set them from your
own detector's validated precision/recall curve.

## Escalation timing rules

- Exactly **one call in flight at a time** per incident. The next tier is
  only called after the current attempt reaches a terminal state
  (confirmed, declined, no-answer, or timeout).
- A configurable **per-call timeout** (default 90 seconds of no terminal
  result) counts as no-answer and triggers escalation.
- A **maximum tier count** (default 3) stops the chain and marks the
  incident `unresolved_escalated` rather than calling indefinitely.
- Every attempt — including ones that don't reach a human — is written to
  the incident's audit trail before the next call starts.

## What "confirmed" means

An incident is marked `resolved_confirmed` only when a call's structured
result has `can_dispatch: "yes"`. `unknown` is treated the same as `no` for
escalation purposes — ambiguity always escalates rather than assuming
coverage.

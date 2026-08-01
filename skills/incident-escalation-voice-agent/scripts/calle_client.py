"""
Thin wrapper around the CALL-E Calls API / Python SDK.

Two modes:

  * dry_run=True (default, and forced whenever CALLE_API_KEY is unset):
    returns a deterministic *simulated* call outcome derived from a hash of
    the idempotency key, so demos are repeatable without placing a real
    call or requiring a CALL-E account.

  * dry_run=False: lazily imports the `calle` package (`pip install
    calle-ai`) and places a real call via `client.calls.create_and_wait`.

The response shape returned by both modes matches the CALL-E Quickstart's
create_and_wait() result: a dict with status, structured_result,
task_completed, completion_confidence, and evidence.
See: https://docs.heycall-e.com/quickstart

This module never logs a raw phone number or API key.
"""

from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass, field
from typing import Any


def mask_phone(phone: str) -> str:
    """Mask all but the last 4 digits of an E.164 number for logs/UI."""
    digits = phone.strip()
    if len(digits) <= 4:
        return "•" * len(digits)
    return "•" * (len(digits) - 4) + digits[-4:]


@dataclass
class CallOutcome:
    call_id: str
    status: str  # "completed" | "no_answer" | "declined" | "timed_out" | "failed"
    task_completed: bool
    completion_confidence: dict[str, Any]
    structured_result: dict[str, Any] | None
    evidence: list[str] = field(default_factory=list)


class CalleClient:
    """Minimal wrapper. Construct once per process."""

    def __init__(self, dry_run: bool | None = None, base_url: str | None = None):
        api_key = os.environ.get("CALLE_API_KEY")
        self.dry_run = dry_run if dry_run is not None else not bool(api_key)
        self.base_url = base_url or os.environ.get("CALLE_BASE_URL")
        self._api_key = api_key
        self._sdk_client = None

        if not self.dry_run:
            try:
                from calle import CalleClient as _RealClient  # pip install calle-ai
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "Live mode requested but the 'calle-ai' package is not "
                    "installed. Run `pip install calle-ai` or omit --live to "
                    "stay in dry-run mode."
                ) from exc
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._sdk_client = _RealClient(**kwargs)

    def place_escalation_call(
        self,
        *,
        task: str,
        phone: str,
        region: str,
        locale: str,
        result_schema: dict[str, Any],
        metadata: dict[str, Any],
        idempotency_key: str,
    ) -> CallOutcome:
        if self.dry_run:
            return self._simulate(idempotency_key=idempotency_key, phone=phone)

        raw = self._sdk_client.calls.create_and_wait(
            task=task,
            recipient={"phone": phone, "region": region, "locale": locale},
            result_schema=result_schema,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )
        return CallOutcome(
            call_id=raw.get("id", idempotency_key),
            status=raw.get("status", "failed"),
            task_completed=bool(raw.get("task_completed")),
            completion_confidence=raw.get("completion_confidence") or {},
            structured_result=raw.get("structured_result"),
            evidence=raw.get("evidence") or [],
        )

    # -- dry-run simulation -------------------------------------------------

    def _simulate(self, *, idempotency_key: str, phone: str) -> CallOutcome:
        """Deterministic pseudo-random outcome seeded from the idempotency key,
        so repeated demo runs are reproducible and every alert doesn't just
        resolve on the first tier."""
        seed = int(hashlib.sha256(idempotency_key.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        roll = rng.random()

        if roll < 0.45:
            return CallOutcome(
                call_id=f"sim_{seed:08x}",
                status="completed",
                task_completed=True,
                completion_confidence={"score": round(rng.uniform(0.8, 0.98), 2), "label": "high"},
                structured_result={
                    "can_dispatch": "yes",
                    "eta_minutes": rng.choice([5, 10, 15, 20]),
                    "alternate_contact": "",
                    "needs_escalation": False,
                },
                evidence=[f"Simulated: on-call responder at {mask_phone(phone)} confirmed dispatch."],
            )
        elif roll < 0.65:
            return CallOutcome(
                call_id=f"sim_{seed:08x}",
                status="completed",
                task_completed=True,
                completion_confidence={"score": round(rng.uniform(0.6, 0.9), 2), "label": "medium"},
                structured_result={
                    "can_dispatch": "no",
                    "eta_minutes": 0,
                    "alternate_contact": "",
                    "needs_escalation": True,
                },
                evidence=[f"Simulated: responder at {mask_phone(phone)} could not dispatch, asked to escalate."],
            )
        elif roll < 0.85:
            return CallOutcome(
                call_id=f"sim_{seed:08x}",
                status="no_answer",
                task_completed=False,
                completion_confidence={"score": 0.0, "label": "low"},
                structured_result=None,
                evidence=[f"Simulated: no answer at {mask_phone(phone)}."],
            )
        else:
            return CallOutcome(
                call_id=f"sim_{seed:08x}",
                status="declined",
                task_completed=True,
                completion_confidence={"score": round(rng.uniform(0.7, 0.95), 2), "label": "high"},
                structured_result={
                    "can_dispatch": "unknown",
                    "eta_minutes": 0,
                    "alternate_contact": "",
                    "needs_escalation": True,
                },
                evidence=[f"Simulated: responder at {mask_phone(phone)} declined this call."],
            )

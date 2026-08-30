"""Versioned deterministic reducer for Objective and Increment events."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contract import (
    ContractError, canonical_payload_digest, closed_values, reducer_version,
    require_transition, validate_authority_receipt_claims, validate_command_envelope,
    validate_effect_readback, validate_exact_fields,
)


def initial_state(subject_kind: str) -> str | None:
    if subject_kind not in closed_values("subject_kind"):
        raise ContractError(f"unknown subject kind {subject_kind}")
    return None


def reduce_events(subject_kind: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Replay canonical events under the contract-frozen reducer/transition graph."""
    state: str | None = initial_state(subject_kind)
    last_authority: str | None = None
    last_effect: dict[str, Any] | None = None
    decisions: dict[str, Mapping[str, Any]] = {}
    effect_keys: set[str] = set()
    version = reducer_version()
    for expected_generation, event in enumerate(events, 1):
        try:
            validate_exact_fields(event, "transition_event")
        except ContractError as error:
            raise ContractError(f"event schema invalid at generation {expected_generation}: {error.detail}") from error
        if event.get("schema_version") != 2 or event.get("reducer_version") != version:
            raise ContractError("event schema/reducer version drifted")
        if event.get("subject_kind") != subject_kind:
            raise ContractError("event subject kind drifted")
        if event.get("generation") != expected_generation:
            raise ContractError("event generation is not contiguous")
        event_kind = event.get("event_kind")
        key = str(event.get("effect_idempotency_key") or "")
        if not key:
            raise ContractError("event idempotency key is missing")
        if event_kind == "human_decision_recorded":
            if key in decisions:
                raise ContractError("decision event idempotency key is duplicated")
            if event.get("from_state") != state or event.get("to_state") != state:
                raise ContractError("human decision record must not mutate reduced state")
            digest = event.get("command_envelope_digest")
            effect_id = event.get("effect_id")
            payload = event.get("payload")
            if not isinstance(digest, str) or not digest.startswith("sha256:") or not isinstance(effect_id, str) or not effect_id:
                raise ContractError("decision must persist command envelope digest and non-empty effect id")
            if not isinstance(payload, Mapping):
                raise ContractError("decision payload is missing")
            try:
                validate_exact_fields(payload, "human_decision_recorded_payload")
            except ContractError as error:
                raise ContractError(f"decision payload schema invalid: {error.detail}") from error
            if payload.get("command_envelope_digest") != digest:
                raise ContractError("decision command envelope digest drifted")
            envelope = payload.get("command_envelope")
            if not isinstance(envelope, Mapping):
                raise ContractError("decision command envelope is missing")
            try:
                validate_command_envelope(envelope)
            except ContractError as error:
                raise ContractError(f"decision command envelope schema invalid: {error.detail}") from error
            claims = payload.get("authority_claims")
            if not isinstance(claims, Mapping):
                raise ContractError("decision authority claims are missing")
            try:
                validate_authority_receipt_claims(claims)
            except ContractError as error:
                raise ContractError(f"decision authority claims schema invalid: {error.detail}") from error
            if type(payload.get("release_evidence_eligible")) is not bool:
                raise ContractError("decision release_evidence_eligible must be bool")
            if canonical_payload_digest(envelope) != digest:
                raise ContractError("decision command envelope canonical digest drifted")
            if canonical_payload_digest(claims) != envelope.get("authority_claims_digest"):
                raise ContractError("decision authority claims digest drifted")
            if (
                envelope.get("subject_kind") != subject_kind
                or envelope.get("subject_id") != event.get("subject_id")
                or envelope.get("effect_id") != effect_id
                or envelope.get("effect_idempotency_key") != key
                or envelope.get("source_state") != state
                or envelope.get("action") != event.get("action")
                or envelope.get("authority_receipt_ref") != event.get("authority_receipt_ref")
                or envelope.get("occurred_at") != event.get("occurred_at")
            ):
                raise ContractError("decision event identity does not match command envelope")
            if event.get("effect_readback") is not None:
                raise ContractError("decision event must not carry effect readback")
            require_transition(subject_kind, str(event.get("action") or ""), state, envelope.get("target_state"))
            decisions[key] = event
            last_authority = str(event.get("authority_receipt_ref") or "") or None
        elif event_kind == "state_transition_committed":
            decision = decisions.get(key)
            if decision is None or key in effect_keys:
                raise ContractError("state transition has no unique preceding decision")
            if event.get("from_state") != state:
                raise ContractError("state transition from_state does not match reducer state")
            envelope = decision.get("payload", {}).get("command_envelope")
            if not isinstance(envelope, Mapping):
                raise ContractError("preceding decision command envelope is missing")
            if (
                event.get("command_envelope_digest") != decision.get("command_envelope_digest")
                or event.get("effect_id") != decision.get("effect_id")
                or event.get("action") != decision.get("action")
                or event.get("authority_receipt_ref") != decision.get("authority_receipt_ref")
                or event.get("to_state") != envelope.get("target_state")
                or event.get("payload") != envelope.get("payload")
                or event.get("occurred_at") != envelope.get("occurred_at")
            ):
                raise ContractError("state transition identity does not match preceding decision")
            require_transition(subject_kind, str(event.get("action") or ""), state, event.get("to_state"))
            readback = event.get("effect_readback")
            if not isinstance(readback, Mapping):
                raise ContractError("state transition effect readback is missing")
            try:
                validate_effect_readback(readback)
            except ContractError as error:
                raise ContractError(f"state transition effect readback schema invalid: {error.detail}") from error
            if readback.get("status") != "applied" or readback.get("exact_match") is not True:
                raise ContractError("state transition requires exact applied effect readback")
            if readback.get("effect_id") != decision.get("effect_id") or readback.get("idempotency_key") != key:
                raise ContractError("effect readback identity does not match persisted decision")
            state = str(event["to_state"])
            effect_keys.add(key)
            last_authority = str(event.get("authority_receipt_ref") or "") or None
            last_effect = dict(readback)
        else:
            raise ContractError(f"unknown transition event kind {event_kind!r}")
    return {
        "reduced_state": state,
        "last_authority_receipt_ref": last_authority,
        "last_effect_readback": last_effect,
        "decision_idempotency_keys": tuple(sorted(decisions)),
        "effect_idempotency_keys": tuple(sorted(effect_keys)),
    }

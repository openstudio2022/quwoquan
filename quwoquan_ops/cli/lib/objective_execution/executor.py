"""Authority-bound executor with immutable pending-command/effect identity."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .authority import AuthorityProvider, AuthorityVerifier, UnavailableAuthorityProvider, reject_projection_authority, verify_authority
from .contract import ObjectiveExecutionError, reducer_version, require_transition, schema_fields, typed_result, validate_authority_receipt_claims, validate_command_envelope, validate_effect_readback, validate_exact_fields
from .journal import CASConflict, WriterLeaseConflict, _append_event_under_lease, _read_events_under_lease, _recover_under_lease, payload_digest, readback, writer_lease
from .reducer import reduce_events


class ConsumableAuthorityProvider(Protocol):
    provider_kind: str
    release_evidence_eligible: bool
    def readback(self, receipt_ref: str) -> Any: ...
    def consume(self, decision_id: str, *, expected_version: str, idempotency_key: str, fingerprint: str, scope: Mapping[str, str], action: str, command_digest: str) -> Any: ...


class EffectAdapter(Protocol):
    def invoke(self, *, action: str, effect_id: str, idempotency_key: str, payload: Mapping[str, Any]) -> None: ...
    def readback(self, *, effect_id: str, idempotency_key: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ExecutorDependencies:
    authority_provider: AuthorityProvider = UnavailableAuthorityProvider()
    authority_verifier: AuthorityVerifier | None = None
    effect_adapter: EffectAdapter | None = None
    after_consume_verified: Any | None = None


def _current_state(root: Path, subject_kind: str, subject_id: str) -> tuple[str | None, str, int]:
    result = readback(root, subject_kind, subject_id)
    if result.status == "failed":
        raise ObjectiveExecutionError(result.terminal or "OEX.JOURNAL_FAILED", "journal readback failed")
    return result.reduced_state, result.head or "absent", result.generation or 0


def _command_envelope(command: Mapping[str, Any], verified: Mapping[str, Any], source_state: str | None) -> dict[str, Any]:
    envelope = {
        "schema_version": 2,
        "subject_kind": command["subject_kind"], "subject_id": command["subject_id"],
        "source_state": source_state, "target_state": command["target_state"],
        "authority_receipt_ref": command["authority_receipt_ref"],
        "expected_scope": command["expected_scope"],
        "expected_evidence_fingerprint": command["expected_evidence_fingerprint"],
        "expected_decision_kind": command["expected_decision_kind"], "action": command["action"],
        "effect_id": command["effect_id"], "effect_idempotency_key": command["effect_idempotency_key"],
        "occurred_at": command["occurred_at"], "payload": command["payload"],
        "authority_provider_kind": verified["provider_kind"],
        "authority_provider_receipt_ref": verified["provider_receipt_ref"],
        "authority_claims_digest": payload_digest(verified["claims"]),
        "authority_winner_idempotency_key": verified["claims"]["winner_idempotency_key"],
        "authority_winner_command_digest": verified["claims"]["winner_command_digest"],
        "authority_winner_previous_generation": verified["claims"]["receipt_previous_generation"],
        "authority_winner_generation": verified["claims"]["receipt_generation"],
        "authority_chain_commit": verified["claims"]["chain_commit"],
    }
    validate_command_envelope(envelope)
    return envelope


def _zero_effect(result: dict[str, Any]) -> dict[str, Any]:
    result.update(effect_invoked=False, mutation_performed=False)
    return result


def _pending_conflict(detail: str) -> dict[str, Any]:
    return _zero_effect(typed_result("OEX.PENDING_COMMAND_CONFLICT", detail=detail))


def _pending_effect(code: str, *, detail: str, effect_invoked: bool, effect_readback: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = typed_result(code, detail=detail)
    result.update(effect_invoked=effect_invoked, retry_effect=False)
    if effect_readback is not None:
        result["readback"] = dict(effect_readback)
    return result


def _consume_command_digest(command: Mapping[str, Any]) -> str:
    return payload_digest({
        "subject_kind": command["subject_kind"], "subject_id": command["subject_id"],
        "target_state": command["target_state"], "authority_receipt_ref": command["authority_receipt_ref"],
        "expected_scope": command["expected_scope"], "expected_evidence_fingerprint": command["expected_evidence_fingerprint"],
        "expected_decision_kind": command["expected_decision_kind"], "action": command["action"],
        "effect_id": command["effect_id"], "effect_idempotency_key": command["effect_idempotency_key"],
        "occurred_at": command["occurred_at"], "payload": command["payload"],
    })


def _verified_consume_response(command: Mapping[str, Any], deps: ExecutorDependencies, provider: Any, response: Any) -> dict[str, Any]:
    provider._responses_by_provider_ref[response.envelope.provider_receipt_ref] = response
    if deps.authority_verifier is None:
        raise ValueError("authority verifier is not configured")
    claims = dict(deps.authority_verifier.verify(response.exact_body, response.envelope.provider_receipt_ref))
    if set(claims) != set(schema_fields("authority_receipt_claims")):
        raise ValueError("consume winner claims shape drifted")
    validate_authority_receipt_claims(claims)
    return {
        "result": "verified", "provider_kind": provider.provider_kind,
        "authenticated": True, "exact_bytes_verified": True, "claims": claims,
        "release_evidence_eligible": provider.release_evidence_eligible is True,
        "provider_receipt_ref": response.envelope.provider_receipt_ref,
    }


def _consume_hosted_authority(command: Mapping[str, Any], deps: ExecutorDependencies, verified: Mapping[str, Any]) -> dict[str, Any]:
    if deps.authority_provider.provider_kind == "test":
        claims = dict(verified["claims"])
        claims.update(receipt_state="consumed", receipt_previous_generation=1, receipt_generation=2, receipt_etag='"test-consumed"', chain_commit="sha256:" + "0" * 64, winner_idempotency_key=str(command["effect_idempotency_key"]), winner_command_digest=_consume_command_digest(command), provider_version="test", provider_commit="sha256:" + "0" * 64, contract_version="test", issuer="test")
        result = dict(verified); result["claims"] = claims
        return result
    provider = deps.authority_provider
    if not hasattr(provider, "consume"):
        return typed_result("OEX.AUTHORITY_PROVIDER_UNAVAILABLE", detail="authority provider does not support hosted consume")
    consume_digest = _consume_command_digest(command)
    current = verified["claims"]
    if current["receipt_state"] == "revoked":
        return _zero_effect(typed_result("OEX.AUTHORITY_CONSUME_CONFLICT", detail="authority receipt was revoked before effect"))
    if current["receipt_state"] == "consumed":
        if current["winner_idempotency_key"] == command["effect_idempotency_key"] and current["winner_command_digest"] == consume_digest:
            return dict(verified)
        return _zero_effect(typed_result("OEX.AUTHORITY_CONSUME_CONFLICT", detail="another hosted consume command won"))
    try:
        response = provider.consume(
            str(command["authority_receipt_ref"]), expected_version=str(verified["claims"]["receipt_etag"]),
            idempotency_key=str(command["effect_idempotency_key"]), fingerprint=str(command["expected_evidence_fingerprint"]),
            scope=command["expected_scope"], action=str(command["action"]), command_digest=consume_digest,
        )
        consume_verified = _verified_consume_response(command, deps, provider, response)
    except Exception as error:
        code = getattr(error, "code", "")
        if "COMMAND_OUTCOME_UNKNOWN" in code:
            try:
                reconciled = provider.client.reconcile(str(command["authority_receipt_ref"]), idempotency_key=str(command["effect_idempotency_key"]))
                consume_verified = _verified_consume_response(command, deps, provider, reconciled)
            except Exception as reconcile_error:
                return _zero_effect(typed_result("OEX.AUTHORITY_CONSUME_UNKNOWN", detail=str(reconcile_error)))
        elif code.endswith("CAS_CONFLICT"):
            return _zero_effect(typed_result("OEX.AUTHORITY_CONSUME_CONFLICT", detail=str(error)))
        else:
            return _zero_effect(typed_result("OEX.AUTHORITY_WINNER_UNPROVEN", detail=str(error)))
    if consume_verified.get("result") != "verified":
        return _zero_effect(typed_result("OEX.AUTHORITY_WINNER_UNPROVEN", detail=str(consume_verified.get("detail") or consume_verified)))
    claims = consume_verified["claims"]
    initial = verified["claims"]
    winner_proven = (
        claims["receipt_state"] == "consumed"
        and claims["receipt_previous_generation"] == initial["receipt_generation"]
        and claims["receipt_generation"] == claims["receipt_previous_generation"] + 1
        and claims["receipt_id"] == initial["receipt_id"]
        and claims["decision_id"] == initial["decision_id"]
        and claims["decision_unit_id"] == initial["decision_unit_id"]
        and all(claims[field] == initial[field] for field in ("provider_kind", "provider_version", "provider_commit", "contract_version", "issuer"))
        and claims["winner_idempotency_key"] == command["effect_idempotency_key"]
        and claims["winner_command_digest"] == consume_digest
    )
    if not winner_proven:
        code = "OEX.AUTHORITY_CONSUME_UNKNOWN" if 'code' in locals() and "COMMAND_OUTCOME_UNKNOWN" in code else "OEX.AUTHORITY_WINNER_UNPROVEN"
        return _zero_effect(typed_result(code, detail="signed consume winner identity mismatch"))
    return consume_verified


def execute_authorized_effect(
    root: Path,
    command: Mapping[str, Any],
    *,
    dependencies: ExecutorDependencies | None = None,
    projection_authority: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_exact_fields(command, "execute_effect_command")
    if projection_authority is not None:
        blocked = reject_projection_authority(projection_authority)
        if blocked is not None:
            return blocked
    deps = dependencies or ExecutorDependencies()
    verified = verify_authority(
        provider=deps.authority_provider,
        verifier=deps.authority_verifier,
        receipt_ref=str(command["authority_receipt_ref"]),
        expected_scope=command["expected_scope"],
        expected_evidence_fingerprint=str(command["expected_evidence_fingerprint"]),
        expected_decision_kind=str(command["expected_decision_kind"]),
        action=str(command["action"]),
        now=now,
    )
    if verified.get("result") != "verified":
        return verified
    if deps.effect_adapter is None:
        return typed_result("OEX.AUTHORITY_PROVIDER_UNAVAILABLE", detail="effect adapter is not configured")
    subject_kind = str(command["subject_kind"])
    subject_id = str(command["subject_id"])
    expected_scope = command["expected_scope"]
    if not isinstance(expected_scope, Mapping) or expected_scope.get(subject_kind) != subject_id:
        result = typed_result("OEX.AUTHORITY_INVALID", detail="command scope does not bind subject kind/id")
        result["effect_invoked"] = False
        return result
    idempotency_key = str(command["effect_idempotency_key"])
    effect_id = str(command["effect_id"])
    if not effect_id:
        return _pending_effect("OEX.EFFECT_IDENTITY_CONFLICT", detail="command effect_id must be non-empty", effect_invoked=False)
    try:
        preconsumed_verified: dict[str, Any] | None = None
        # Validate current local transition and pending identity before authority mutation.
        with writer_lease(root, subject_kind, subject_id) as lease:
            _recover_under_lease(lease)
            initial_events = _read_events_under_lease(lease)
            initial_state = reduce_events(subject_kind, initial_events)["reduced_state"] if initial_events else None
            bound = next((event for event in initial_events if event["event_kind"] == "human_decision_recorded" and event["effect_idempotency_key"] == idempotency_key), None)
            if bound is None:
                require_transition(subject_kind, str(command["action"]), initial_state, command["target_state"])
            else:
                persisted = bound.get("payload", {}).get("command_envelope")
                if not isinstance(persisted, Mapping):
                    raise ObjectiveExecutionError("OEX.JOURNAL_TAMPERED", "persisted command envelope is missing")
                preconsumed_verified = _consume_hosted_authority(command, deps, verified)
                if preconsumed_verified.get("result") != "verified":
                    return _pending_conflict("pending command does not own the hosted consume winner")
                candidate = _command_envelope(command, preconsumed_verified, persisted.get("source_state"))
                if bound.get("command_envelope_digest") != payload_digest(candidate) or persisted != candidate:
                    return _pending_conflict("pending command envelope identity does not exactly match before hosted consume")
        verified = preconsumed_verified or _consume_hosted_authority(command, deps, verified)
        if verified.get("result") != "verified":
            return verified
        if deps.after_consume_verified is not None:
            deps.after_consume_verified()
        with writer_lease(root, subject_kind, subject_id) as lease:
            # Recovery is an explicit mutation and is legal only under this lease.
            _recover_under_lease(lease)
            existing = _read_events_under_lease(lease)
            if existing:
                state = reduce_events(subject_kind, existing)["reduced_state"]
                head = str(existing[-1]["event_digest"])
                generation = int(existing[-1]["generation"])
            else:
                state, head, generation = None, "absent", 0
            decision = next((event for event in existing if event["event_kind"] == "human_decision_recorded" and event["effect_idempotency_key"] == idempotency_key), None)
            transition = next((event for event in existing if event["event_kind"] == "state_transition_committed" and event["effect_idempotency_key"] == idempotency_key), None)
            if transition is not None:
                persisted_envelope = decision.get("payload", {}).get("command_envelope") if decision is not None else None
                if not isinstance(persisted_envelope, Mapping):
                    raise ObjectiveExecutionError("OEX.JOURNAL_TAMPERED", "committed transition has no persisted command envelope")
                candidate = _command_envelope(command, verified, persisted_envelope.get("source_state"))
                if decision.get("command_envelope_digest") != payload_digest(candidate) or decision.get("effect_id") != effect_id or persisted_envelope != candidate:
                    return _pending_conflict("idempotency key is already bound to a different completed command envelope")
                return {"result": "duplicate", "effect_invoked": False, "release_evidence_eligible": verified["release_evidence_eligible"], "readback": readback(root, subject_kind, subject_id).as_dict()}
            source_state = state
            if decision is not None:
                persisted_envelope = decision.get("payload", {}).get("command_envelope")
                if not isinstance(persisted_envelope, Mapping):
                    raise ObjectiveExecutionError("OEX.JOURNAL_TAMPERED", "persisted command envelope is missing")
                source_state = persisted_envelope.get("source_state")
            envelope = _command_envelope(command, verified, source_state)
            envelope_digest = payload_digest(envelope)
            if decision is not None and (decision.get("command_envelope_digest") != envelope_digest or decision.get("effect_id") != effect_id or decision.get("payload", {}).get("command_envelope") != envelope):
                return _pending_conflict("pending command envelope identity does not exactly match the persisted decision")
            require_transition(subject_kind, str(command["action"]), source_state, command["target_state"])
            effect_invoked = False
            if decision is None:
                recorded = _append_event_under_lease(
                    lease,
                    {
                        "subject_kind": subject_kind, "subject_id": subject_id,
                        "event_kind": "human_decision_recorded", "reducer_version": reducer_version(),
                        "action": command["action"], "from_state": state, "to_state": state,
                        "expected_head": head, "expected_generation": generation,
                        "authority_receipt_ref": command["authority_receipt_ref"],
                        "effect_idempotency_key": idempotency_key,
                        "command_envelope_digest": envelope_digest, "effect_id": effect_id,
                        "effect_readback": None, "occurred_at": command["occurred_at"],
                        "payload": {
                            "command_envelope": envelope, "command_envelope_digest": envelope_digest,
                            "authority_claims": verified["claims"],
                            "release_evidence_eligible": verified["release_evidence_eligible"],
                            "provider_receipt_ref": verified["provider_receipt_ref"],
                        },
                    },
                )
                head = str(recorded["readback"]["head"])
                generation = int(recorded["readback"]["generation"])
                deps.effect_adapter.invoke(action=str(command["action"]), effect_id=effect_id, idempotency_key=idempotency_key, payload=command["payload"])
                effect_invoked = True
            persisted_effect_id = str((decision or {"effect_id": effect_id})["effect_id"])
            if not persisted_effect_id:
                return _pending_effect("OEX.EFFECT_IDENTITY_CONFLICT", detail="persisted decision effect_id is empty", effect_invoked=effect_invoked)
            effect_readback = dict(deps.effect_adapter.readback(effect_id=persisted_effect_id, idempotency_key=idempotency_key))
            validate_effect_readback(effect_readback)
            if effect_readback["effect_id"] != persisted_effect_id or effect_readback["idempotency_key"] != idempotency_key:
                return _pending_effect("OEX.EFFECT_IDENTITY_CONFLICT", detail="effect readback identity does not match persisted effect id/key", effect_invoked=effect_invoked, effect_readback=effect_readback)
            if effect_readback["status"] != "applied" or effect_readback["exact_match"] is not True:
                return _pending_effect("OEX.EFFECT_OUTCOME_UNKNOWN", detail="effect is not exact applied", effect_invoked=effect_invoked, effect_readback=effect_readback)
            current_events = _read_events_under_lease(lease)
            state = reduce_events(subject_kind, current_events)["reduced_state"]
            head = str(current_events[-1]["event_digest"])
            generation = int(current_events[-1]["generation"])
            committed = _append_event_under_lease(
                lease,
                {
                    "subject_kind": subject_kind, "subject_id": subject_id,
                    "event_kind": "state_transition_committed", "reducer_version": reducer_version(),
                    "action": command["action"], "from_state": state, "to_state": command["target_state"],
                    "expected_head": head, "expected_generation": generation,
                    "authority_receipt_ref": command["authority_receipt_ref"],
                    "effect_idempotency_key": idempotency_key,
                    "command_envelope_digest": envelope_digest, "effect_id": persisted_effect_id,
                    "effect_readback": effect_readback, "occurred_at": command["occurred_at"],
                    "payload": command["payload"],
                },
            )
            return {"result": "committed", "effect_invoked": effect_invoked, "release_evidence_eligible": verified["release_evidence_eligible"], "readback": committed["readback"]}
    except WriterLeaseConflict as error:
        result = typed_result(error.code, detail=error.detail)
        result["effect_invoked"] = False
        return result
    except CASConflict as error:
        result = typed_result(error.code, detail=error.detail)
        result["effect_invoked"] = False
        return result
    except ObjectiveExecutionError as error:
        result = typed_result(error.code, detail=error.detail)
        result["effect_invoked"] = False
        return result

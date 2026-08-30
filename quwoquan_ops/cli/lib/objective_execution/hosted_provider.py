"""Adapters from hosted authority transport to Objective execution protocols."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

try:
    from lib.hosted_authority import (
        PROVIDER_KIND,
        AuthorityAbsent,
        HostedAuthorityError,
        HostedAuthorityHttpClient,
        HostedAuthorityResponse,
        verify_ed25519,
    )
except ImportError:  # repository package import path
    from quwoquan_ops.cli.lib.hosted_authority import (
        PROVIDER_KIND,
        AuthorityAbsent,
        HostedAuthorityError,
        HostedAuthorityHttpClient,
        HostedAuthorityResponse,
        verify_ed25519,
    )

from .authority import AuthorityReadback

_TEST_KEY_MARKERS = ("test", "fixture", "dev", "local")
_TEST_ISSUER_SUFFIXES = (".test", ".invalid", ".localhost")
_ALLOWED_OBSERVE_ACTIONS = frozenset(
    {
        "create_objective", "create_increment", "observe_objective", "observe_increment", "read_authority_receipt",
        "read_owner_manifest", "read_readiness", "read_review_result", "read_handoff",
    }
)


def _release_eligible(
    response: HostedAuthorityResponse, *, explicit_policy: bool, claims: Mapping[str, Any]
) -> bool:
    test_key = claims.get("testKey")
    release_claim = claims.get("releaseEligible")
    return (
        response.envelope.transport_tls
        and explicit_policy
        and test_key is False
        and release_claim is True
        and not response.envelope.issuer.lower().rstrip("/").endswith(_TEST_ISSUER_SUFFIXES)
        and not any(marker in response.envelope.key_id.lower() for marker in _TEST_KEY_MARKERS)
    )


class HostedAuthorityProvider:
    """AuthorityProvider query adapter. Fresh receipts are never cached."""

    provider_kind = PROVIDER_KIND

    def __init__(self, client: HostedAuthorityHttpClient) -> None:
        self.client = client
        self.release_evidence_eligible = False
        self._responses_by_provider_ref: dict[str, HostedAuthorityResponse] = {}

    def readback(self, receipt_ref: str) -> AuthorityReadback:
        self.release_evidence_eligible = False
        self._responses_by_provider_ref.clear()
        try:
            response = self.client.query(receipt_ref)
        except AuthorityAbsent as error:
            return AuthorityReadback("absent", detail=error.detail)
        except HostedAuthorityError as error:
            return AuthorityReadback("failed", detail=f"{error.code}: {error.detail}")
        provider_ref = response.envelope.provider_receipt_ref
        self._responses_by_provider_ref[provider_ref] = response
        return AuthorityReadback(
            "present",
            exact_bytes=response.exact_body,
            provider_receipt_ref=provider_ref,
        )

    def response_for_verification(self, provider_receipt_ref: str) -> HostedAuthorityResponse:
        response = self._responses_by_provider_ref.pop(provider_receipt_ref, None)
        if response is None:
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.RESPONSE_STALE",
                "verification has no fresh matching hosted readback",
            )
        return response

    def consume(
        self, decision_id: str, *, expected_version: str, idempotency_key: str,
        fingerprint: str, scope: Mapping[str, str], action: str, command_digest: str,
    ) -> HostedAuthorityResponse:
        return self.client.consume(
            decision_id, expected_version=expected_version, idempotency_key=idempotency_key,
            fingerprint=fingerprint, scope=scope, action=action, command_digest=command_digest,
        )

    def revoke(
        self,
        decision_id: str,
        *,
        expected_version: str,
        idempotency_key: str,
        reason: str,
    ) -> HostedAuthorityResponse:
        return self.client.revoke(
            decision_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            reason=reason,
        )


class HostedAuthorityVerifier:
    """Decode one verifiable wrapper, then verify exact claim and state bytes."""

    def __init__(self, provider: HostedAuthorityProvider, trusted_public_keys: Mapping[str, bytes]) -> None:
        self.provider = provider
        self.trusted_public_keys = dict(trusted_public_keys)

    def verify(self, exact_bytes: bytes, provider_receipt_ref: str) -> Mapping[str, Any]:
        try:
            response = self.provider.response_for_verification(provider_receipt_ref)
            if response.exact_body != exact_bytes:
                raise ValueError("hosted authority exact response bytes mismatch")
            wrapper = _strict_object(exact_bytes, "hosted authority wrapper")
            _require_fields(wrapper, _WRAPPER_FIELDS, "hosted authority wrapper")
            canonical_bytes = _decode_raw_base64(wrapper["canonicalBytes"], "canonicalBytes")
            attestation_bytes = _decode_raw_base64(wrapper["attestationCanonicalBytes"], "attestationCanonicalBytes")
            claims = _strict_object(canonical_bytes, "authority claims")
            attestation = _strict_object(attestation_bytes, "authority state attestation")
            _require_fields(claims, _CLAIM_FIELDS, "authority claims")
            _require_fields(attestation, _ATTESTATION_FIELDS, "authority state attestation")
            if response.envelope.issuer != self.provider.client.config.expected_issuer:
                raise ValueError("hosted authority issuer does not equal expected issuer")
            _verify_detached(canonical_bytes, str(wrapper["signature"]), response.envelope, self.trusted_public_keys)
            _verify_detached(attestation_bytes, str(wrapper["attestationSignature"]), response.envelope, self.trusted_public_keys)
            _verify_digest(canonical_bytes, wrapper["payloadDigest"], "payload")
            _verify_digest(attestation_bytes, wrapper["attestationDigest"], "attestation")
            _verify_wrapper_bindings(wrapper, claims, attestation, response)
        except (HostedAuthorityError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
            raise ValueError(str(error)) from error
        eligible = _release_eligible(response, explicit_policy=self.provider.client.config.explicit_release_policy, claims=claims)
        self.provider.release_evidence_eligible = eligible
        return {
            "receipt_id": claims["receiptId"], "decision_id": claims["decisionId"],
            "decision_unit_id": claims["decisionUnitId"], "actor_id": claims["actorId"],
            "actor_authenticated": claims["actorAuthenticated"], "role": claims["role"],
            "scope": claims["scope"], "expires_at": claims["expiresAt"],
            "evidence_fingerprint": claims["evidenceFingerprint"],
            "decision_kind": claims["decisionKind"], "actions": claims["actions"],
            "provider_kind": claims["providerKind"], "provider_version": claims["providerVersion"], "provider_commit": claims["providerCommit"],
            "contract_version": claims["contractVersion"], "issuer": claims["issuer"],
            "receipt_state": attestation["state"], "receipt_previous_generation": attestation["previousGeneration"],
            "receipt_generation": attestation["generation"],
            "receipt_etag": attestation["etag"], "chain_commit": attestation["chainCommit"],
            "winner_idempotency_key": attestation["winnerIdempotencyKey"],
            "winner_command_digest": attestation["winnerCommandDigest"],
        }


_GENERATED_BINDING = Path(__file__).resolve().parents[4] / "quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model/human_contract_generated.go"

def _generated_fields(constant: str) -> tuple[str, ...]:
    raw = _GENERATED_BINDING.read_text(encoding="utf-8")
    match = re.search(rf'^const {re.escape(constant)} = "(.*)"$', raw, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"generated authority field binding missing: {constant}")
    decoded = json.loads('"' + match.group(1) + '"')
    values = json.loads(decoded)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise RuntimeError(f"generated authority field binding invalid: {constant}")
    return tuple(values)

_CLAIM_FIELDS = _generated_fields("GeneratedAuthorityReceiptClaimFieldsJSON")
_ATTESTATION_FIELDS = _generated_fields("GeneratedAuthorityStateAttestationFieldsJSON")
_WRAPPER_FIELDS = _generated_fields("GeneratedAuthorizationReceiptWrapperFieldsJSON")

def _strict_object(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict): raise ValueError(f"{label} must be an object")
    return value

def _require_fields(value: Mapping[str, Any], expected: tuple[str, ...], label: str) -> None:
    if set(value) != set(expected): raise ValueError(f"{label} fields drifted")

def _decode_raw_base64(value: object, label: str) -> bytes:
    if not isinstance(value, str) or "=" in value: raise ValueError(f"{label} is not canonical raw base64")
    import base64
    try: decoded = base64.b64decode(value + "=" * (-len(value) % 4), validate=True)
    except ValueError as error: raise ValueError(f"{label} is invalid") from error
    if base64.b64encode(decoded).decode().rstrip("=") != value: raise ValueError(f"{label} is not canonical raw base64")
    return decoded

def _verify_digest(raw: bytes, expected: object, label: str) -> None:
    import hashlib
    if expected != "sha256:" + hashlib.sha256(raw).hexdigest(): raise ValueError(f"{label} digest mismatch")

def _verify_detached(raw: bytes, signature: str, envelope: Any, keyring: Mapping[str, bytes]) -> None:
    derived = type(envelope)(algorithm=envelope.algorithm, key_id=envelope.key_id, signature_b64=signature, issuer=envelope.issuer, decision_id=envelope.decision_id, version=envelope.version, provider_version=envelope.provider_version, provider_commit=envelope.provider_commit, contract_version=envelope.contract_version, chain_commit=envelope.chain_commit, transport_tls=envelope.transport_tls)
    verify_ed25519(raw, derived, keyring)

def _verify_wrapper_bindings(wrapper: Mapping[str, Any], claims: Mapping[str, Any], state: Mapping[str, Any], response: HostedAuthorityResponse) -> None:
    for field in ("receiptId", "decisionId", "decisionUnitId", "providerKind", "providerVersion", "providerCommit", "contractVersion", "issuer"):
        if wrapper[field] != claims[field] or wrapper[field] != state[field]: raise ValueError(f"{field} binding mismatch")
    for field in ("state", "previousGeneration", "generation", "etag", "winnerIdempotencyKey", "winnerCommandDigest", "stateActorId", "stateAt", "chainCommit"):
        if wrapper[field] != state[field]: raise ValueError(f"{field} state binding mismatch")
    if state["payloadDigest"] != wrapper["payloadDigest"] or wrapper["keyId"] != response.envelope.key_id or wrapper["signatureAlgorithm"] != response.envelope.algorithm: raise ValueError("signature envelope binding mismatch")
    if wrapper["etag"] != response.envelope.version or wrapper["providerVersion"] != response.envelope.provider_version or wrapper["providerCommit"] != response.envelope.provider_commit or wrapper["contractVersion"] != response.envelope.contract_version or wrapper["chainCommit"] != response.envelope.chain_commit: raise ValueError("HTTP envelope identity mismatch")
    if claims["schemaVersion"] != 1 or state["schemaVersion"] != 1 or wrapper["schemaVersion"] != 1: raise ValueError("authority protocol version mismatch")
    if claims["providerKind"] != PROVIDER_KIND or not claims["actorId"] or claims["actorAuthenticated"] is not True or not claims["role"]: raise ValueError("authenticated claim identity mismatch")
    scope = claims["scope"]
    if not isinstance(scope, dict) or len(scope) != 1 or next(iter(scope)) not in {"objective", "increment"} or not all(isinstance(value, str) and value and value == value.strip() for value in scope.values()): raise ValueError("canonical scope is invalid")
    actions = claims["actions"]
    if not isinstance(actions, list) or not actions or not all(isinstance(action, str) and action and action == action.strip() for action in actions) or actions != sorted(set(actions)): raise ValueError("canonical actions are invalid")
    if state["state"] == "available" and (state["previousGeneration"] != 0 or state["generation"] != 1 or state["winnerIdempotencyKey"] or state["winnerCommandDigest"] or state["stateActorId"] or state["stateAt"]): raise ValueError("available state carries winner identity")
    if state["state"] in {"consumed", "revoked"} and (state["generation"] <= state["previousGeneration"] or not state["winnerIdempotencyKey"] or not state["winnerCommandDigest"] or not state["stateActorId"] or not state["stateAt"]): raise ValueError("terminal state winner identity is incomplete")


class ObserveOnlyEffectAdapter:
    """Zero-mutation effect adapter for governed, reversible, non-production reads."""

    write_concurrency = 1
    mutation_allowed = False
    production_allowed = False

    def __init__(self, *, allowed_actions: frozenset[str] = _ALLOWED_OBSERVE_ACTIONS) -> None:
        self.allowed_actions = allowed_actions
        self._observations: dict[str, dict[str, Any]] = {}

    def invoke(self, *, action: str, effect_id: str, idempotency_key: str, payload: Mapping[str, Any]) -> None:
        if action not in self.allowed_actions:
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.EFFECT_NOT_ALLOWED",
                f"action={action} is outside the observe-only allowlist",
            )
        environment = str(payload.get("environment") or "")
        if environment == "prod" or payload.get("mutation") is not False:
            raise HostedAuthorityError(
                "HOSTED_AUTHORITY.EFFECT_NOT_ALLOWED",
                "observe-only effects require explicit mutation=false and non-production scope",
            )
        if not effect_id:
            raise HostedAuthorityError("HOSTED_AUTHORITY.EFFECT_NOT_ALLOWED", "executor effect_id is required")
        self._observations.setdefault(
            idempotency_key,
            {
                "status": "applied",
                "effect_id": effect_id,
                "idempotency_key": idempotency_key,
                "exact_match": True,
                "provider_receipt_ref": effect_id,
            },
        )
        return None

    def readback(self, *, effect_id: str, idempotency_key: str) -> Mapping[str, Any]:
        observed = self._observations.get(idempotency_key)
        if observed is None or (effect_id and effect_id != observed["effect_id"]):
            return {
                "status": "unknown",
                "effect_id": effect_id,
                "idempotency_key": idempotency_key,
                "exact_match": False,
                "provider_receipt_ref": "observe:unknown",
            }
        return dict(observed)

"""Injected authority readback and exact-byte claim verification port."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from .contract import schema_fields, typed_result

try:
    from lib.human_agent_delivery.contract import namespace_values
except ImportError:  # repository package import path
    from quwoquan_ops.cli.lib.human_agent_delivery.contract import namespace_values


@dataclass(frozen=True, slots=True)
class AuthorityReadback:
    status: str
    exact_bytes: bytes | None = None
    provider_receipt_ref: str | None = None
    detail: str = ""


class AuthorityProvider(Protocol):
    provider_kind: str
    release_evidence_eligible: bool

    def readback(self, receipt_ref: str) -> AuthorityReadback: ...


class AuthorityVerifier(Protocol):
    def verify(self, exact_bytes: bytes, provider_receipt_ref: str) -> Mapping[str, Any]: ...


class UnavailableAuthorityProvider:
    provider_kind = "unavailable"
    release_evidence_eligible = False

    def readback(self, receipt_ref: str) -> AuthorityReadback:
        return AuthorityReadback("failed", detail=f"no authenticated provider for {receipt_ref}")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("expiry is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("expiry must include timezone")
    return parsed.astimezone(timezone.utc)


def verify_authority(
    *, provider: AuthorityProvider, verifier: AuthorityVerifier | None, receipt_ref: str,
    expected_scope: Mapping[str, Any], expected_evidence_fingerprint: str,
    expected_decision_kind: str, action: str, now: datetime | None = None,
) -> dict[str, Any]:
    readback = provider.readback(receipt_ref)
    if readback.status == "absent":
        return typed_result("OEX.AUTHORITY_ABSENT", detail=receipt_ref)
    if readback.status != "present" or readback.exact_bytes is None or not readback.provider_receipt_ref:
        return typed_result("OEX.AUTHORITY_PROVIDER_UNAVAILABLE", detail=readback.detail or receipt_ref)
    if verifier is None:
        return typed_result("OEX.AUTHORITY_PROVIDER_UNAVAILABLE", detail="authority verifier is not configured")
    try:
        claims = dict(verifier.verify(readback.exact_bytes, readback.provider_receipt_ref))
        expected_fields = set(schema_fields("authority_receipt_claims"))
        if set(claims) != expected_fields:
            raise ValueError("authority claims shape drifted")
        current = now or datetime.now(timezone.utc)
        if claims["actor_authenticated"] is not True or not claims["actor_id"]:
            raise ValueError("actor is not authenticated")
        if claims["role"] not in namespace_values("human_authority_role"):
            raise ValueError("role is not a declared Human Authority role")
        if claims["scope"] != dict(expected_scope):
            raise ValueError("scope mismatch")
        if _parse_timestamp(claims["expires_at"]) <= current:
            raise ValueError("authority expired")
        if claims["evidence_fingerprint"] != expected_evidence_fingerprint:
            raise ValueError("evidence fingerprint mismatch")
        if claims["decision_kind"] != expected_decision_kind:
            raise ValueError("decision kind mismatch")
        if not isinstance(claims["actions"], list) or action not in claims["actions"]:
            raise ValueError("action is not authorized")
        if claims["receipt_id"] != claims["decision_id"] or not claims["decision_unit_id"]:
            raise ValueError("receipt/decision/unit identity mismatch")
        if claims["provider_kind"] != provider.provider_kind:
            raise ValueError("provider kind mismatch")
        if claims["receipt_state"] not in {"available", "consumed", "revoked"}:
            raise ValueError("authority receipt state is invalid")
        if not isinstance(claims["receipt_previous_generation"], int) or claims["receipt_previous_generation"] < 0:
            raise ValueError("authority receipt previous generation is invalid")
        if not isinstance(claims["receipt_generation"], int) or claims["receipt_generation"] <= claims["receipt_previous_generation"]:
            raise ValueError("authority receipt generation is invalid")
        if not all(isinstance(claims[field], str) and claims[field] for field in ("provider_version", "provider_commit", "contract_version", "issuer", "chain_commit", "receipt_etag")):
            raise ValueError("provider/contract/chain identity missing")
        if provider.provider_kind != "test" and claims["issuer"] != provider.client.config.expected_issuer:
            raise ValueError("issuer mismatch")
        return {
            "result": "verified", "provider_kind": provider.provider_kind,
            "authenticated": True, "exact_bytes_verified": True, "claims": claims,
            "release_evidence_eligible": provider.release_evidence_eligible is True,
            "provider_receipt_ref": readback.provider_receipt_ref,
        }
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        return typed_result("OEX.AUTHORITY_INVALID", detail=str(error))


def reject_projection_authority(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if payload.get("projection_only_until_authority_provider") is True or payload.get("authenticated_authority") is False or payload.get("executable") is False:
        return typed_result("OEX.AUTHORITY_PROJECTION_ONLY", detail="AuthorizationGrant projection is non-executable")
    return None

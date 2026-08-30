"""Hosted authority adapter local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#gwt-004.t3
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.hosted_authority import (  # noqa: E402
    CANONICAL_OPERATIONS_RELATIVE_PATH,
    EXTERNAL_BLOCKER_CODE,
    PROTOCOL_BLOCKER_CODE,
    UNKNOWN_OUTCOME_CODE,
    CommandOutcomeUnknown,
    HostedAuthorityConfig,
    HostedAuthorityError,
    HostedAuthorityHttpClient,
    HostedAuthorityResponse,
    HostedAuthorityWireError,
    ProtocolUnavailableBlocker,
    SignatureEnvelope,
    load_hosted_authority_wire,
    signature_message,
)
from lib.hosted_authority.runtime import runtime_from_env  # noqa: E402
from lib.objective_execution.hosted_provider import (  # noqa: E402
    HostedAuthorityProvider,
    HostedAuthorityVerifier,
)
from lib.openssl3_resolver import resolve_openssl3  # noqa: E402

ISSUER = "https://authority.example.com"
DECISION_ID = "decision/1"
KEY_ID = "authority-ed25519-2026-08"
VERSION = '"receipt-v3"'


def claims(*, release_eligible: bool, test_key: bool) -> dict[str, object]:
    return {
        "schemaVersion": 1, "receiptId": DECISION_ID, "decisionId": DECISION_ID,
        "decisionUnitId": "unit-1", "actorId": "actor-1", "actorAuthenticated": True,
        "role": "engineering_delivery_owner", "scope": {"objective": "objective-1"},
        "evidenceFingerprint": "sha256:evidence", "decisionKind": "delivery_authorization",
        "actions": ["observe_objective"], "issuedAt": "2026-08-30T00:00:00Z",
        "expiresAt": "2099-08-30T00:00:00Z", "providerKind": "hosted-human-authority",
        "providerVersion": "provider-v1", "providerCommit": "sha256:" + "1" * 64,
        "contractVersion": "human-authority-wire-v1", "issuer": ISSUER,
        "nativeProtection": False, "releaseEligible": release_eligible, "testKey": test_key,
    }


def wrapper_fixture(private: Path, *, release_eligible: bool, test_key: bool, state: str = "available", generation: int = 1, winner_key: str = "", winner_digest: str = "") -> tuple[bytes, dict[str, str]]:
    claim = claims(release_eligible=release_eligible, test_key=test_key)
    canonical = exact(claim)
    previous = generation - 1
    state_at = "" if state == "available" else "2026-08-30T00:01:00Z"
    state_actor = "" if state == "available" else "executor-1"
    attestation = {
        "schemaVersion": 1, "receiptId": DECISION_ID, "decisionId": DECISION_ID,
        "decisionUnitId": "unit-1", "payloadDigest": "sha256:" + __import__("hashlib").sha256(canonical).hexdigest(),
        "state": state, "previousGeneration": previous, "generation": generation,
        "etag": f'"receipt:{DECISION_ID}:generation:{generation}"',
        "winnerIdempotencyKey": winner_key, "winnerCommandDigest": winner_digest,
        "stateActorId": state_actor, "stateAt": state_at, "chainCommit": "sha256:" + "2" * 64,
        "providerKind": "hosted-human-authority", "providerVersion": "provider-v1",
        "providerCommit": "sha256:" + "1" * 64, "contractVersion": "human-authority-wire-v1", "issuer": ISSUER,
    }
    attestation_bytes = exact(attestation)
    value = {
        "schemaVersion": 1, "canonicalBytes": base64.b64encode(canonical).decode().rstrip("="),
        "payloadDigest": attestation["payloadDigest"], "signatureAlgorithm": "ed25519", "keyId": KEY_ID,
        "signature": sign(private, canonical), "attestationCanonicalBytes": base64.b64encode(attestation_bytes).decode().rstrip("="),
        "attestationDigest": "sha256:" + __import__("hashlib").sha256(attestation_bytes).hexdigest(),
        "attestationSignature": sign(private, attestation_bytes), **{key: attestation[key] for key in (
            "receiptId", "decisionId", "decisionUnitId", "state", "previousGeneration", "generation", "etag",
            "winnerIdempotencyKey", "winnerCommandDigest", "stateActorId", "stateAt", "chainCommit", "providerKind",
            "providerVersion", "providerCommit", "contractVersion", "issuer")},
        "releaseEligible": release_eligible, "testKey": test_key,
    }
    headers = {
        "X-QWQ-Authority-Signature-Algorithm": "ed25519", "X-QWQ-Authority-Key-Id": KEY_ID,
        "X-QWQ-Authority-Signature": value["signature"], "X-QWQ-Authority-Issuer": ISSUER,
        "X-QWQ-Authority-Provider-Version": "provider-v1", "X-QWQ-Authority-Provider-Commit": "sha256:" + "1" * 64,
        "X-QWQ-Authority-Contract-Version": "human-authority-wire-v1", "X-QWQ-Authority-Chain-Commit": "sha256:" + "2" * 64,
        "ETag": attestation["etag"],
    }
    return exact(value), headers


def exact(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def keypair() -> tuple[tempfile.TemporaryDirectory[str], Path, bytes]:
    temporary = tempfile.TemporaryDirectory(prefix="qwq-hosted-authority-fixture-")
    root = Path(temporary.name)
    private = root / "private.pem"
    public_der = root / "public.der"
    openssl = resolve_openssl3().executable
    subprocess.run([str(openssl), "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True, capture_output=True)
    subprocess.run([str(openssl), "pkey", "-in", str(private), "-pubout", "-outform", "DER", "-out", str(public_der)], check=True, capture_output=True)
    return temporary, private, public_der.read_bytes()[-32:]


def sign(private: Path, payload: bytes) -> str:
    root = private.parent
    payload_path = root / "payload.bin"
    signature_path = root / "signature.bin"
    payload_path.write_bytes(payload)
    subprocess.run(
        [str(resolve_openssl3().executable), "pkeyutl", "-sign", "-rawin", "-inkey", str(private), "-in", str(payload_path), "-out", str(signature_path)],
        check=True, capture_output=True,
    )
    return base64.b64encode(signature_path.read_bytes()).decode().rstrip("=")


def wire_config(*, opener, allow_http: bool = False) -> HostedAuthorityHttpClient:
    wire = load_hosted_authority_wire(ROOT)
    return HostedAuthorityHttpClient(
        HostedAuthorityConfig(
            base_url="http://127.0.0.1:9" if allow_http else "https://authority.example.com",
            expected_issuer=ISSUER,
            wire=wire,
            explicit_release_policy=True,
            allow_insecure_http_for_tests=allow_http,
        ),
        token_provider=lambda: "token", opener=opener,
    )


class Response:
    status = 200

    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        self._body = body
        self.headers = headers

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._body


class HostedAuthorityAdapterTest(unittest.TestCase):
    def test_wire_routes_are_loaded_from_canonical_operations_contract(self) -> None:
        wire = load_hosted_authority_wire(ROOT)
        self.assertEqual(wire.source_path, (ROOT / CANONICAL_OPERATIONS_RELATIVE_PATH).resolve())
        self.assertEqual(wire.query_path_template, "/control-plane/platform/human-authority/receipts/{decisionId}")
        self.assertEqual(wire.consume_path_template, "/control-plane/platform/human-authority/receipts/{decisionId}:consume")
        self.assertEqual(wire.revoke_path_template, "/control-plane/platform/human-authority/receipts/{decisionId}:revoke")
        self.assertTrue(wire.source_sha256.startswith("sha256:"))

    def _wire_fixture_root(self, content: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="qwq-hosted-authority-wire-")
        root = Path(temporary.name)
        source = root / CANONICAL_OPERATIONS_RELATIVE_PATH
        source.parent.mkdir(parents=True)
        source.write_text(content, encoding="utf-8")
        self.addCleanup(temporary.cleanup)
        return temporary, root

    @staticmethod
    def _block_wire_fixture() -> str:
        return """description: Hosted authority fixture
api_routes:
- method: GET
  path: /control-plane/platform/human-authority/receipts/{decisionId}
  operation: ReadHumanAuthorizationReceipt
  actor: account
  security: {auth_mode: required}
  authorization: {principal: operator}
  reliability: {timeout_ms: 1000}
  error_codes: []
  privacy: {log_policy: redacted}
  telemetry: {metric: fixture}
  slo: {latency_p95_ms: 1000}
  commercial: {status: blocked}
  application: {kind: query}
- method: POST
  path: /control-plane/platform/human-authority/receipts/{decisionId}:consume
  operation: ConsumeHumanAuthorizationReceipt
  actor: account
  security: {auth_mode: required}
  authorization: {principal: operator}
  reliability: {timeout_ms: 1000}
  error_codes: []
  privacy: {log_policy: redacted}
  telemetry: {metric: fixture}
  slo: {latency_p95_ms: 1000}
  commercial: {status: blocked}
  application: {kind: command}
- method: POST
  path: /control-plane/platform/human-authority/receipts/{decisionId}:revoke
  operation: RevokeHumanAuthorizationReceipt
  actor: account
  security: {auth_mode: required}
  authorization: {principal: operator}
  reliability: {timeout_ms: 1000}
  error_codes: []
  privacy: {log_policy: redacted}
  telemetry: {metric: fixture}
  slo: {latency_p95_ms: 1000}
  commercial: {status: blocked}
  application: {kind: command}
contract_test:
  coverage_requirements: []
"""

    def test_block_style_fixture_loads_routes_from_source(self) -> None:
        _temporary, root = self._wire_fixture_root(self._block_wire_fixture())
        wire = load_hosted_authority_wire(root)
        self.assertEqual(
            wire.consume_path_template,
            "/control-plane/platform/human-authority/receipts/{decisionId}:consume",
        )
        self.assertEqual(
            wire.revoke_path_template,
            "/control-plane/platform/human-authority/receipts/{decisionId}:revoke",
        )

    def test_wire_rejects_malformed_non_object_unknown_and_alias_yaml(self) -> None:
        cases = {
            "malformed": "description: [unterminated\n",
            "non-object": "- description\n- api_routes\n",
            "unknown": self._block_wire_fixture().replace(
                "description: Hosted authority fixture",
                "description: Hosted authority fixture\nunknown: rejected",
            ),
            "alias": self._block_wire_fixture().replace(
                "security: {auth_mode: required}",
                "security: &security {auth_mode: required}",
                1,
            ).replace(
                "security: {auth_mode: required}",
                "security: *security",
                1,
            ),
        }
        route_non_object = """description: Hosted authority fixture
api_routes:
- not-an-object
contract_test:
  coverage_requirements: []
"""
        cases["route-non-object"] = route_non_object
        for name, content in cases.items():
            with self.subTest(name=name):
                _temporary, root = self._wire_fixture_root(content)
                with self.assertRaises(HostedAuthorityWireError):
                    load_hosted_authority_wire(root)

    def test_wire_rejects_duplicate_keys_and_duplicate_or_unknown_operations(self) -> None:
        cases = {
            "duplicate-key": self._block_wire_fixture().replace(
                "  operation: ReadHumanAuthorizationReceipt",
                "  operation: ReadHumanAuthorizationReceipt\n  operation: ReadHumanAuthorizationReceipt",
                1,
            ),
            "duplicate-operation": self._block_wire_fixture().replace(
                "  operation: RevokeHumanAuthorizationReceipt",
                "  operation: ConsumeHumanAuthorizationReceipt",
                1,
            ),
            "unknown-route-key": self._block_wire_fixture().replace(
                "  actor: account",
                "  actor: account\n  copied_wire: rejected",
                1,
            ),
            "missing-required-key": self._block_wire_fixture().replace(
                "  actor: account\n",
                "",
                1,
            ),
            "missing-operation-no-fallback": self._block_wire_fixture().replace(
                "  operation: RevokeHumanAuthorizationReceipt",
                "  operation: UnknownHumanAuthorizationReceipt",
                1,
            ),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                _temporary, root = self._wire_fixture_root(content)
                with self.assertRaises(HostedAuthorityWireError):
                    load_hosted_authority_wire(root)

    def test_wire_preserves_exact_path_and_method_validation(self) -> None:
        cases = {
            "method": self._block_wire_fixture().replace("- method: GET", "- method: POST", 1),
            "path": self._block_wire_fixture().replace(
                "/control-plane/platform/human-authority/receipts/{decisionId}",
                "/control-plane/platform/human-authority/receipts/prefix-{decisionId}",
                1,
            ),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                _temporary, root = self._wire_fixture_root(content)
                with self.assertRaises(HostedAuthorityWireError):
                    load_hosted_authority_wire(root)

    def test_wire_rejects_symlink_source_and_path_replacement(self) -> None:
        content = self._block_wire_fixture()
        temporary = tempfile.TemporaryDirectory(prefix="qwq-hosted-authority-wire-link-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / CANONICAL_OPERATIONS_RELATIVE_PATH
        source.parent.mkdir(parents=True)
        external = root / "operations-target.yaml"
        external.write_text(content, encoding="utf-8")
        source.symlink_to(external)
        with self.assertRaises(HostedAuthorityWireError):
            load_hosted_authority_wire(root)

        source.unlink()
        source.write_text(content, encoding="utf-8")
        original_open = os.open
        replaced = False

        def replace_after_open(path_value, flags, *args, **kwargs):
            nonlocal replaced
            descriptor = original_open(path_value, flags, *args, **kwargs)
            if not replaced and Path(path_value) == source:
                source.unlink()
                source.symlink_to(external)
                replaced = True
            return descriptor

        with mock.patch("lib.hosted_authority.wire.os.open", side_effect=replace_after_open):
            with self.assertRaisesRegex(HostedAuthorityWireError, "changed while being read"):
                load_hosted_authority_wire(root)

    def test_plain_authorization_receipt_json_is_protocol_unavailable(self) -> None:
        envelope_client = wire_config(
            opener=lambda *_args, **_kwargs: Response(
                json.dumps({
                    "decisionId": DECISION_ID, "canonicalBytes": "opaque", "signature": "ordinary-json",
                    "keyId": KEY_ID, "releaseEligible": True,
                }).encode(),
                {"Content-Type": "application/json"},
            )
        )
        with self.assertRaises(ProtocolUnavailableBlocker) as blocked:
            envelope_client.query(DECISION_ID)
        self.assertEqual(blocked.exception.code, PROTOCOL_BLOCKER_CODE)
        self.assertIn("ordinary JSON is unauthenticated", blocked.exception.detail)
        readback = HostedAuthorityProvider(envelope_client).readback(DECISION_ID)
        self.assertEqual(readback.status, "failed")
        self.assertIn(PROTOCOL_BLOCKER_CODE, readback.detail)


    def test_command_path_headers_body_and_timeout_unknown_outcome(self) -> None:
        captured: list[object] = []
        def timeout(request, **_kwargs):
            captured.append(request)
            raise URLError(socket.timeout("late response"))
        authority = wire_config(opener=timeout)
        with self.assertRaises(CommandOutcomeUnknown) as unknown:
            authority.consume(
                DECISION_ID, expected_version=VERSION, idempotency_key="consume-1",
                fingerprint="sha256:evidence", scope={"objective": "objective-1"},
                action="observe_objective", command_digest="sha256:" + "3" * 64,
            )
        self.assertEqual(unknown.exception.code, UNKNOWN_OUTCOME_CODE)
        self.assertFalse(unknown.exception.retry_allowed)
        request = captured[0]
        self.assertEqual(request.get_header("If-match"), VERSION)
        self.assertEqual(json.loads(request.data)["scope"], {"objective": "objective-1"})
        self.assertEqual(json.loads(request.data)["commandDigest"], "sha256:" + "3" * 64)

    def test_verifiable_wrapper_exact_bytes_and_tamper_fail_closed(self) -> None:
        temporary, private, public = keypair()
        self.addCleanup(temporary.cleanup)
        body, headers = wrapper_fixture(private, release_eligible=True, test_key=False)
        response = HostedAuthorityResponse(body, wire_config(opener=lambda *_args, **_kwargs: None)._envelope(headers, tls=True, expected_decision_id=DECISION_ID), 200)
        provider = HostedAuthorityProvider(wire_config(opener=lambda *_args, **_kwargs: None))
        provider._responses_by_provider_ref[DECISION_ID] = response  # noqa: SLF001
        verified = HostedAuthorityVerifier(provider, {KEY_ID: public}).verify(body, DECISION_ID)
        self.assertEqual(verified["scope"], {"objective": "objective-1"})
        self.assertEqual(verified["receipt_state"], "available")
        self.assertTrue(provider.release_evidence_eligible)
        for field in ("canonicalBytes", "attestationCanonicalBytes", "etag", "providerVersion", "chainCommit"):
            value = json.loads(body)
            value[field] = (value[field] + "x") if isinstance(value[field], str) else value[field]
            tampered = exact(value)
            provider._responses_by_provider_ref[DECISION_ID] = HostedAuthorityResponse(tampered, response.envelope, 200)  # noqa: SLF001
            with self.subTest(field=field), self.assertRaises(ValueError):
                HostedAuthorityVerifier(provider, {KEY_ID: public}).verify(tampered, DECISION_ID)

    def test_noncanonical_scope_and_actions_fail_closed(self) -> None:
        temporary, private, public = keypair()
        self.addCleanup(temporary.cleanup)
        for label, mutate in (
            ("ambiguous-scope", lambda value: value.update(scope={"objective": "objective-1", "increment": "increment-1"})),
            ("unknown-scope", lambda value: value.update(scope={"target": "objective-1"})),
            ("unsorted-actions", lambda value: value.update(actions=["observe_objective", "create_objective"])),
            ("duplicate-actions", lambda value: value.update(actions=["observe_objective", "observe_objective"])),
        ):
            with self.subTest(label=label):
                claim = claims(release_eligible=True, test_key=False)
                mutate(claim)
                body, headers = wrapper_fixture(private, release_eligible=True, test_key=False)
                wrapper = json.loads(body)
                canonical = exact(claim)
                wrapper["canonicalBytes"] = base64.b64encode(canonical).decode().rstrip("=")
                wrapper["payloadDigest"] = "sha256:" + __import__("hashlib").sha256(canonical).hexdigest()
                wrapper["signature"] = sign(private, canonical)
                attestation = json.loads(base64.b64decode(wrapper["attestationCanonicalBytes"] + "=" * (-len(wrapper["attestationCanonicalBytes"]) % 4)))
                attestation["payloadDigest"] = wrapper["payloadDigest"]
                attestation_bytes = exact(attestation)
                wrapper["attestationCanonicalBytes"] = base64.b64encode(attestation_bytes).decode().rstrip("=")
                wrapper["attestationDigest"] = "sha256:" + __import__("hashlib").sha256(attestation_bytes).hexdigest()
                wrapper["attestationSignature"] = sign(private, attestation_bytes)
                headers["X-QWQ-Authority-Signature"] = wrapper["signature"]
                tampered = exact(wrapper)
                response = HostedAuthorityResponse(tampered, wire_config(opener=lambda *_args, **_kwargs: None)._envelope(headers, tls=True, expected_decision_id=DECISION_ID), 200)
                provider = HostedAuthorityProvider(wire_config(opener=lambda *_args, **_kwargs: None))
                provider._responses_by_provider_ref[DECISION_ID] = response  # noqa: SLF001
                with self.assertRaisesRegex(ValueError, "canonical"):
                    HostedAuthorityVerifier(provider, {KEY_ID: public}).verify(tampered, DECISION_ID)

    def test_consumed_winner_is_authenticated_and_http_fixture_not_release_evidence(self) -> None:
        temporary, private, public = keypair()
        self.addCleanup(temporary.cleanup)
        body, headers = wrapper_fixture(private, release_eligible=True, test_key=False, state="consumed", generation=2, winner_key="consume-1", winner_digest="sha256:" + "3" * 64)
        envelope = wire_config(opener=lambda *_args, **_kwargs: None, allow_http=True)._envelope(headers, tls=False, expected_decision_id=DECISION_ID)
        provider = HostedAuthorityProvider(wire_config(opener=lambda *_args, **_kwargs: None, allow_http=True))
        provider._responses_by_provider_ref[DECISION_ID] = HostedAuthorityResponse(body, envelope, 200)  # noqa: SLF001
        verified = HostedAuthorityVerifier(provider, {KEY_ID: public}).verify(body, DECISION_ID)
        self.assertEqual(verified["winner_idempotency_key"], "consume-1")
        self.assertEqual(verified["receipt_generation"], 2)
        self.assertFalse(provider.release_evidence_eligible)

    def test_missing_real_configuration_is_one_external_blocker(self) -> None:
        with self.assertRaises(HostedAuthorityError) as captured:
            runtime_from_env(ROOT, token_provider=lambda: "", getenv=lambda _name: None)
        self.assertEqual(captured.exception.code, EXTERNAL_BLOCKER_CODE)
        self.assertFalse(captured.exception.retry_allowed)


if __name__ == "__main__":
    unittest.main()

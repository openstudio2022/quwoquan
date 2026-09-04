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
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
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
    AuthorityAbsent,
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
from hosted_authority_smoke import (  # noqa: E402
    OWNER_MANIFEST_ROOT,
    READINESS_BUNDLE_ROOT,
    SmokeFailure,
    _fresh_readiness,
    _normalize_owner_manifest_path,
    _read_canonical_input,
    _read_canonical_repo_ref,
    _verify_owner_manifest,
    build_parser as build_smoke_parser,
    main as smoke_main,
    run_observe_only_smoke,
)
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    validate_feature_context_manifest,
)
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.feature_context_fingerprint import build_feature_context_fingerprint  # noqa: E402
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
CANDIDATE = "sha256:" + "a" * 64
MANIFEST_SHA256 = "b" * 64
EXPECTED_SCOPE = {"objective": CANDIDATE}
EXPECTED_ENVIRONMENT = "gamma"
EXPECTED_DECISION_KIND = "delivery_authorization"
EXPECTED_ACTION = "observe_objective"
READINESS_REF = (READINESS_BUNDLE_ROOT / "fixture.json").as_posix()


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


def wrapper_fixture(
    private: Path, *, release_eligible: bool, test_key: bool,
    state: str = "available", generation: int = 1,
    winner_key: str = "", winner_digest: str = "",
    claim_overrides: dict[str, object] | None = None,
) -> tuple[bytes, dict[str, str]]:
    claim = claims(release_eligible=release_eligible, test_key=test_key)
    claim.update(claim_overrides or {})
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
            expected_issuer=ISSUER, wire=wire, explicit_release_policy=True,
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


class StaticHostedAuthorityClient:
    def __init__(self, response: HostedAuthorityResponse) -> None:
        self.response = response
        self.config = type(
            "SmokeHostedAuthorityConfig", (),
            {"expected_issuer": ISSUER, "explicit_release_policy": True},
        )()

    def query(self, receipt_ref: str) -> HostedAuthorityResponse:
        if receipt_ref != DECISION_ID:
            raise AssertionError(receipt_ref)
        return self.response


class FailedHostedAuthorityClient(StaticHostedAuthorityClient):
    def query(self, receipt_ref: str) -> HostedAuthorityResponse:
        raise HostedAuthorityError("HOSTED_AUTHORITY.UNAVAILABLE", receipt_ref)


class AbsentHostedAuthorityClient(StaticHostedAuthorityClient):
    def query(self, receipt_ref: str) -> HostedAuthorityResponse:
        raise AuthorityAbsent(receipt_ref)


def readiness_result(
    *, candidate: str = CANDIDATE, environment: str = EXPECTED_ENVIRONMENT,
    manifest_sha256: str = MANIFEST_SHA256, status: str = "passed",
) -> dict[str, object]:
    result: dict[str, object] = {
        "objectId": "platform-ops.hosted-authority", "specRef": "spec#gwt-004",
        "caseId": "hosted_authority_observe_only", "producer": "ops",
        "layer": "environment_acceptance", "status": status,
        "target": {"kind": "object", "id": "hosted-authority"},
        "commitSha": "1" * 40, "contractGraphSourceHash": "2" * 64,
        "deploymentTarget": "gamma-local", "baselineId": "baseline-1",
        "packageDigest": "sha256:" + "3" * 64,
        "configurationDigest": "sha256:" + "4" * 64,
        "candidateManifestSha256": manifest_sha256, "candidateDigest": candidate,
        "environment": environment, "platform": "ops", "deviceClass": "hosted",
        "provider": "hosted-human-authority", "startedAt": "2026-09-01T00:00:00Z",
        "completedAt": "2026-09-01T00:00:01Z", "runnerIdentity": "hosted-authority-smoke",
        "artifactSha256": "5" * 64, "artifactPath": "env/repo/runs/authority.json",
    }
    if status != "passed":
        result["reasonCode"] = "HOSTED_AUTHORITY.not_ready"
    return result


def readiness_bytes(
    *, generated_at: str, results: list[dict[str, object]] | None = None,
) -> bytes:
    return exact({"generatedAt": generated_at, "results": results if results is not None else [readiness_result()]})


def manifest_fixture(*, target: str = "AGENTS.md") -> tuple[str, bytes]:
    payload = {
        "schema_version": contract_schema_version("feature_context_manifest"), "target": target,
        "resolved_owner": "specs/feature-tree/spec.md",
        "owner_chain": [{"level": 0, "node_id": "app-root", "path": "specs/feature-tree/spec.md"}],
        "canonical_contexts": [{"path": "specs/feature-tree/spec.md", "anchor": None, "kind": "spec"}],
        "applicable_agents": ["AGENTS.md"], "open_items": [],
    }
    receipt = build_feature_context_fingerprint(payload, repo_root=ROOT)
    payload["evidence_fingerprint"] = {
        "mode": "embedded", "ref": receipt["ref"], "digest": receipt["digest"],
        "receipt": receipt, "receipt_ref": None,
    }
    validate_feature_context_manifest(payload)
    raw = canonical_json_bytes(payload)
    digest = __import__("hashlib").sha256(raw).hexdigest()
    ref = (OWNER_MANIFEST_ROOT / f"{digest}.json").as_posix()
    path = ROOT / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return ref, raw


class HostedAuthorityAdapterTest(unittest.TestCase):

    def _authority_client(
        self, private: Path, *, fingerprint: str, public: bytes,
        claim_overrides: dict[str, object] | None = None,
        state: str = "available",
    ) -> StaticHostedAuthorityClient:
        overrides = {
            "evidenceFingerprint": fingerprint, "scope": EXPECTED_SCOPE,
            "decisionKind": EXPECTED_DECISION_KIND, "actions": [EXPECTED_ACTION],
            **(claim_overrides or {}),
        }
        terminal = state != "available"
        body, headers = wrapper_fixture(
            private, release_eligible=True, test_key=False, state=state,
            generation=2 if terminal else 1,
            winner_key="winner-1" if terminal else "",
            winner_digest="sha256:" + "6" * 64 if terminal else "",
            claim_overrides=overrides,
        )
        envelope = wire_config(opener=lambda *_args, **_kwargs: None)._envelope(
            headers, tls=True, expected_decision_id=DECISION_ID
        )
        return StaticHostedAuthorityClient(HostedAuthorityResponse(body, envelope, 200))

    def _smoke_fixture(self):
        temporary, private, public = keypair()
        self.addCleanup(temporary.cleanup)
        owner_ref, owner_bytes = manifest_fixture()
        self.addCleanup((ROOT / owner_ref).unlink, missing_ok=True)
        fingerprint = str(json.loads(owner_bytes)["evidence_fingerprint"]["digest"])
        readiness = readiness_bytes(generated_at="2026-09-01T00:00:00+00:00")
        client = self._authority_client(private, fingerprint=fingerprint, public=public)
        return temporary, private, owner_ref, owner_bytes, readiness, client, public

    def _arguments(self, owner_ref, owner_bytes, readiness, client, public, **overrides):
        readiness_ref = (
            READINESS_BUNDLE_ROOT
            / (__import__("hashlib").sha256(readiness).hexdigest() + ".json")
        ).as_posix()
        readiness_path = ROOT / readiness_ref
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        if readiness_path.exists():
            self.assertEqual(readiness_path.read_bytes(), readiness)
        else:
            readiness_path.write_bytes(readiness)
        self.addCleanup(readiness_path.unlink, missing_ok=True)
        arguments = {
            "owner_manifest_ref": owner_ref, "owner_manifest_bytes": owner_bytes,
            "readiness_bundle_ref": readiness_ref, "readiness_bundle_bytes": readiness,
            "receipt_ref": DECISION_ID, "client": client,
            "trusted_public_keys": {KEY_ID: public}, "expected_scope": EXPECTED_SCOPE,
            "expected_environment": EXPECTED_ENVIRONMENT,
            "expected_manifest_sha256": MANIFEST_SHA256,
            "expected_decision_kind": EXPECTED_DECISION_KIND, "action": EXPECTED_ACTION,
            "now": datetime(2026, 9, 1, 0, 1, tzinfo=timezone.utc),
        }
        arguments.update(overrides)
        return arguments

    def test_hosted_smoke_cli_requires_explicit_expected_identity(self) -> None:
        parser = build_smoke_parser()
        parsed = parser.parse_args([
            "--owner-manifest", "owner.json", "--readiness-bundle", "readiness.json",
            "--authority-receipt-ref", DECISION_ID, "--expected-scope-kind", "objective",
            "--expected-scope-id", CANDIDATE, "--expected-environment", "gamma",
            "--expected-manifest-sha256", MANIFEST_SHA256,
            "--expected-decision-kind", EXPECTED_DECISION_KIND, "--action", EXPECTED_ACTION,
        ])
        self.assertEqual(parsed.authority_receipt_ref, DECISION_ID)
        self.assertEqual(parsed.expected_scope_id, CANDIDATE)
        self.assertNotIn("resolver_receipt", vars(parsed))

    def test_hosted_smoke_normalizes_repository_relative_and_absolute_manifest_paths(self) -> None:
        owner_ref, _owner_bytes = manifest_fixture()
        owner_path = ROOT / owner_ref
        self.addCleanup(owner_path.unlink, missing_ok=True)
        relative_path, relative_ref = _normalize_owner_manifest_path(Path(owner_ref))
        absolute_path, absolute_ref = _normalize_owner_manifest_path(owner_path)
        self.assertEqual(relative_path, owner_path.absolute())
        self.assertEqual(absolute_path, relative_path)
        self.assertEqual(relative_ref, owner_ref)
        self.assertEqual(absolute_ref, relative_ref)

    def test_hosted_smoke_rejects_owner_manifest_outside_repository(self) -> None:
        with tempfile.NamedTemporaryFile() as external:
            with self.assertRaises(SmokeFailure) as captured:
                _normalize_owner_manifest_path(Path(external.name))
        self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH")

    def test_hosted_smoke_same_exact_inputs_are_idempotent_and_observe_only(self) -> None:
        _, _, owner_ref, owner_bytes, readiness, client, public = self._smoke_fixture()
        arguments = self._arguments(owner_ref, owner_bytes, readiness, client, public)
        first = run_observe_only_smoke(**arguments)
        second = run_observe_only_smoke(**arguments)
        self.assertEqual(first["observation_identity"], second["observation_identity"])
        self.assertEqual(first["owner_manifest_ref"], owner_ref)
        self.assertEqual(first["readiness_candidate_digest"], CANDIDATE)
        self.assertTrue(first["signature_verified"])
        self.assertFalse(first["mutation_performed"])
        self.assertEqual(first["objective_effect"], "observe-only-test")
        self.assertNotIn("resolver_mode", first)
        self.assertNotIn("workflow", first)

    def test_hosted_smoke_identity_changes_for_each_exact_input(self) -> None:
        _, private, owner_ref, owner_bytes, readiness, client, public = self._smoke_fixture()
        baseline = run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, readiness, client, public))["observation_identity"]
        changed_readiness = readiness_bytes(generated_at="2026-09-01T00:00:01+00:00")
        changed = run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, changed_readiness, client, public))["observation_identity"]
        self.assertNotEqual(changed, baseline)
        second_ref, second_bytes = manifest_fixture(target="quwoquan_ops/AGENTS.md")
        self.addCleanup((ROOT / second_ref).unlink, missing_ok=True)
        second_fingerprint = str(json.loads(second_bytes)["evidence_fingerprint"]["digest"])
        second_client = self._authority_client(private, fingerprint=second_fingerprint, public=public)
        self.assertNotEqual(
            run_observe_only_smoke(**self._arguments(second_ref, second_bytes, readiness, second_client, public))["observation_identity"], baseline,
        )
        authority_changed = self._authority_client(
            private, fingerprint=str(json.loads(owner_bytes)["evidence_fingerprint"]["digest"]),
            public=public, claim_overrides={"actorId": "actor-2"},
        )
        self.assertNotEqual(
            run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, readiness, authority_changed, public))["observation_identity"], baseline,
        )

    def test_hosted_smoke_rejects_noncanonical_manifest_ref_filename_and_json(self) -> None:
        _, _, owner_ref, owner_bytes, readiness, client, public = self._smoke_fixture()
        arguments = self._arguments(owner_ref, owner_bytes, readiness, client, public)
        for noncanonical_ref in (".qwq_output/owner.json", f"./{owner_ref}", owner_ref.replace("/", "//", 1), str(ROOT / owner_ref)):
            with self.subTest(ref=noncanonical_ref), self.assertRaises(SmokeFailure) as captured:
                run_observe_only_smoke(**{**arguments, "owner_manifest_ref": noncanonical_ref})
            self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH")
        wrong = (Path(owner_ref).parent / ("0" * 64 + ".json")).as_posix()
        (ROOT / wrong).write_bytes(owner_bytes)
        self.addCleanup((ROOT / wrong).unlink, missing_ok=True)
        with self.assertRaises(SmokeFailure) as captured:
            run_observe_only_smoke(**{**arguments, "owner_manifest_ref": wrong})
        self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_STALE_INPUT")
        noncanonical = json.dumps(json.loads(owner_bytes), ensure_ascii=False, indent=2).encode()
        noncanonical_ref = (OWNER_MANIFEST_ROOT / (__import__("hashlib").sha256(noncanonical).hexdigest() + ".json")).as_posix()
        (ROOT / noncanonical_ref).write_bytes(noncanonical)
        self.addCleanup((ROOT / noncanonical_ref).unlink, missing_ok=True)
        with self.assertRaises(SmokeFailure) as captured:
            run_observe_only_smoke(**{**arguments, "owner_manifest_ref": noncanonical_ref, "owner_manifest_bytes": noncanonical})
        self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID")

    def test_hosted_smoke_rejects_owner_manifest_symlink_and_hardlink_nodes(self) -> None:
        owner_bytes = b"{}"
        filename = __import__("hashlib").sha256(owner_bytes).hexdigest() + ".json"
        owner_ref = (OWNER_MANIFEST_ROOT / filename).as_posix()
        for node_kind in ("ancestor-symlink", "final-symlink", "hardlink"):
            with self.subTest(node_kind=node_kind), tempfile.TemporaryDirectory(prefix="qwq-owner-node-") as temporary:
                fixture_root = Path(temporary)
                repository = fixture_root / "repo"
                canonical_root = repository / OWNER_MANIFEST_ROOT
                external = fixture_root / "external"
                external.mkdir()
                external_file = external / filename
                external_file.write_bytes(owner_bytes)
                if node_kind == "ancestor-symlink":
                    repository.mkdir()
                    (repository / OWNER_MANIFEST_ROOT.parts[0]).symlink_to(external, target_is_directory=True)
                else:
                    canonical_root.mkdir(parents=True)
                    final_path = canonical_root / filename
                    if node_kind == "final-symlink":
                        final_path.symlink_to(external_file)
                    else:
                        os.link(external_file, final_path)
                with mock.patch("hosted_authority_smoke.REPO_ROOT", repository), self.assertRaises(SmokeFailure) as captured:
                    _verify_owner_manifest(owner_manifest_ref=owner_ref, owner_manifest_bytes=owner_bytes)
                self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH")

    def test_readiness_descriptor_reader_rejects_unsafe_nodes_and_replacement(self) -> None:
        for node_kind in ("ancestor-symlink", "final-symlink", "hardlink", "replacement"):
            with self.subTest(node_kind=node_kind), tempfile.TemporaryDirectory(prefix="qwq-readiness-node-") as temporary:
                fixture_root = Path(temporary)
                repository = fixture_root / "repo"
                canonical_root = repository / READINESS_BUNDLE_ROOT
                external = fixture_root / "external"
                external.mkdir()
                external_file = external / "bundle.json"
                external_file.write_bytes(b"external")
                relative = (READINESS_BUNDLE_ROOT / "bundle.json").as_posix()
                if node_kind == "ancestor-symlink":
                    repository.mkdir()
                    (repository / READINESS_BUNDLE_ROOT.parts[0]).symlink_to(external, target_is_directory=True)
                else:
                    canonical_root.mkdir(parents=True)
                    path = canonical_root / "bundle.json"
                    if node_kind == "final-symlink":
                        path.symlink_to(external_file)
                    elif node_kind == "hardlink":
                        os.link(external_file, path)
                    else:
                        path.write_bytes(b"original")
                        original_read = os.read
                        replaced = False
                        def replace_after_open(fd, size):
                            nonlocal replaced
                            chunk = original_read(fd, size)
                            if not replaced:
                                path.unlink()
                                path.write_bytes(b"replacement")
                                replaced = True
                            return chunk
                patches = [mock.patch("hosted_authority_smoke.REPO_ROOT", repository)]
                if node_kind == "replacement":
                    patches.append(mock.patch("hosted_authority_smoke.os.read", side_effect=replace_after_open))
                with patches[0]:
                    context = patches[1] if len(patches) == 2 else mock.patch("hosted_authority_smoke.os.read", wraps=os.read)
                    with context, self.assertRaises(SmokeFailure) as captured:
                        _read_canonical_repo_ref(relative, allowed_root=READINESS_BUNDLE_ROOT, label="readiness bundle")
                self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH")

    def test_hosted_smoke_rejects_empty_or_mismatched_readiness(self) -> None:
        _, _, owner_ref, owner_bytes, _readiness, client, public = self._smoke_fixture()
        cases = {
            "empty": [],
            "candidate": [readiness_result(candidate="sha256:" + "c" * 64)],
            "environment": [readiness_result(environment="prod")],
            "manifest": [readiness_result(manifest_sha256="d" * 64)],
            "failed": [readiness_result(status="failed")],
        }
        for label, results in cases.items():
            readiness = readiness_bytes(generated_at="2026-09-01T00:00:00Z", results=results)
            with self.subTest(label=label), self.assertRaises(SmokeFailure) as captured:
                run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, readiness, client, public))
            self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_READINESS_NOT_QUALIFYING")

    def test_hosted_smoke_rejects_wrong_or_terminal_authority_claims(self) -> None:
        _, private, owner_ref, owner_bytes, readiness, _client, public = self._smoke_fixture()
        fingerprint = str(json.loads(owner_bytes)["evidence_fingerprint"]["digest"])
        cases = {
            "fingerprint": ({"evidenceFingerprint": "sha256:" + "f" * 64}, "available"),
            "scope": ({"scope": {"objective": "sha256:" + "e" * 64}}, "available"),
            "decision": ({"decisionKind": "routine_execution"}, "available"),
            "action": ({"actions": ["read_authority_receipt"]}, "available"),
            "expired": ({"expiresAt": "2026-08-31T23:59:59Z"}, "available"),
            "consumed": ({}, "consumed"), "revoked": ({}, "revoked"),
        }
        for label, (overrides, state) in cases.items():
            client = self._authority_client(private, fingerprint=fingerprint, public=public, claim_overrides=overrides, state=state)
            with self.subTest(label=label), self.assertRaises(SmokeFailure) as captured:
                run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, readiness, client, public))
            self.assertEqual(captured.exception.code, "HOSTED_AUTHORITY.SMOKE_AUTHORITY_INVALID")

    def test_hosted_smoke_distinguishes_stale_schema_unavailable_and_readback(self) -> None:
        with self.assertRaises(SmokeFailure) as stale:
            _fresh_readiness(json.loads(readiness_bytes(generated_at="2026-08-31T00:00:00Z")), now=datetime(2026, 9, 1, tzinfo=timezone.utc), max_age_seconds=300)
        self.assertEqual(stale.exception.code, "HOSTED_AUTHORITY.SMOKE_STALE_INPUT")
        with self.assertRaises(SmokeFailure) as schema:
            _fresh_readiness({"generatedAt": "bad", "results": []}, now=datetime(2026, 9, 1, tzinfo=timezone.utc), max_age_seconds=300)
        self.assertEqual(schema.exception.code, "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID")
        _, _, owner_ref, owner_bytes, readiness, client, public = self._smoke_fixture()
        failed = FailedHostedAuthorityClient(client.response)
        with self.assertRaises(SmokeFailure) as unavailable:
            run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, readiness, failed, public))
        self.assertEqual(unavailable.exception.code, "HOSTED_AUTHORITY.SMOKE_AUTHORITY_UNAVAILABLE")
        absent = AbsentHostedAuthorityClient(client.response)
        with self.assertRaises(SmokeFailure) as readback:
            run_observe_only_smoke(**self._arguments(owner_ref, owner_bytes, readiness, absent, public))
        self.assertEqual(readback.exception.code, "HOSTED_AUTHORITY.SMOKE_READBACK_FAILED")

    def test_hosted_smoke_cli_typed_terminals_have_unique_recovery_and_exit_two(self) -> None:
        codes = (
            "HOSTED_AUTHORITY.SMOKE_UNSAFE_PATH", "HOSTED_AUTHORITY.SMOKE_STALE_INPUT",
            "HOSTED_AUTHORITY.SMOKE_SCHEMA_INVALID", "HOSTED_AUTHORITY.SMOKE_AUTHORITY_UNAVAILABLE",
            "HOSTED_AUTHORITY.SMOKE_READBACK_FAILED",
        )
        argv = [
            "--owner-manifest", str(OWNER_MANIFEST_ROOT / "owner.json"),
            "--readiness-bundle", str(READINESS_BUNDLE_ROOT / "readiness.json"),
            "--authority-receipt-ref", DECISION_ID, "--expected-scope-kind", "objective",
            "--expected-scope-id", CANDIDATE, "--expected-environment", "gamma",
            "--expected-manifest-sha256", MANIFEST_SHA256,
            "--expected-decision-kind", EXPECTED_DECISION_KIND, "--action", EXPECTED_ACTION,
        ]
        recoveries = set()
        runtime = type("Runtime", (), {"config": object(), "token_provider": lambda: "token", "trusted_public_keys": {}})()
        for code in codes:
            output = io.StringIO()
            with self.subTest(code=code), mock.patch("hosted_authority_smoke._read_canonical_input", return_value=("fixture.json", b"{}")), mock.patch("hosted_authority_smoke.runtime_from_env", return_value=runtime), mock.patch("hosted_authority_smoke.HostedAuthorityHttpClient", return_value=object()), mock.patch("hosted_authority_smoke.run_observe_only_smoke", side_effect=SmokeFailure(code, "blocked")), redirect_stdout(output):
                self.assertEqual(smoke_main(argv), 2)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["code"], code)
            self.assertEqual(payload["terminal"], "blocked")
            self.assertFalse(payload["retry_allowed"])
            self.assertEqual(set(payload), {"result", "code", "terminal", "retry_allowed", "recovery", "detail"})
            recoveries.add(payload["recovery"])
        self.assertEqual(len(recoveries), len(codes))

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

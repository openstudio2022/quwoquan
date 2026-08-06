"""Research isolation runtime-proof contracts for multi-carrier release.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/
multi-carrier-release/spec.md#gwt-002
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.environment import (
    research_isolation_verification as isolation,
)
from content.release.environment.research_isolation_proof import (
    ResearchIsolationProofError,
    validate_research_isolation_pass_proof,
)
from content.release.environment.research_isolation_verification import (
    ResearchIsolationVerificationError,
    load_research_isolation_verification,
    write_research_isolation_verification,
)
from core.io import read_json, write_json
from core.release_layout import payload_digest
from core.schema import load_schema
from core.source_digest import SourceDigest, content_source_revision

RELEASE_ID = "research-isolation-a"
VERIFY_RUN_ID = "verify-research-a"
ENVIRONMENT = "alpha"
SOURCE_DIGEST = "sha256:" + "2" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "5" * 64
SOURCE_REVISION = content_source_revision(
    source_digest=SOURCE_DIGEST,
    entity_catalog_digest=ENTITY_CATALOG_DIGEST,
)
SOURCE_DIGEST_DOCUMENT = SourceDigest(SOURCE_DIGEST).to_document()


def _checksum(value: dict[str, object]) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )


def _operation(index: int, *, status: int = 200) -> dict[str, object]:
    return {
        "path": f"/research/probe/{index}",
        "pageId": f"research.probe.{index}",
        "status": status,
        "requestId": f"request-{index}",
        "traceId": f"trace-{index}",
        "startedAt": "2026-08-05T00:00:00Z",
        "endedAt": "2026-08-05T00:00:01Z",
        "durationMs": 1000,
    }


def _positive_proof(
    repository_root: Path,
    identity_contract: Path,
) -> dict[str, object]:
    contract_ref = identity_contract.relative_to(repository_root).as_posix()
    contract_digest = (
        "sha256:" + hashlib.sha256(identity_contract.read_bytes()).hexdigest()
    )
    subject_hash = "sha256:" + "3" * 64
    manifest_digest = "sha256:" + "6" * 64
    attestation_id_hash = "sha256:" + "7" * 64
    identity = {
        "subjectHash": subject_hash,
        "attestationIdHash": attestation_id_hash,
        "contractRef": contract_ref,
        "contractSha256": contract_digest,
    }
    return {
        "releaseId": RELEASE_ID,
        "manifestDigest": manifest_digest,
        "subjectHash": subject_hash,
        "identityIssuance": {**identity, "operation": _operation(1)},
        "identityAttestation": {**identity, "operation": _operation(2)},
        "internalAppReadback": {
            "releaseId": RELEASE_ID,
            "manifestDigest": manifest_digest,
            "subjectHash": subject_hash,
            "attestationIdHash": attestation_id_hash,
            "signatureVerified": True,
            "researchBadgeVisible": True,
            "operation": _operation(3),
        },
        "anonymousContentProbe": {
            "decision": "denied",
            "operation": _operation(4, status=401),
        },
        "anonymousMediaProbe": {
            "decision": "denied",
            "operation": _operation(5, status=403),
        },
        "networkExposureReadback": {
            "publicCdnDetected": False,
            "anonymousMediaUrlDetected": False,
            "operation": _operation(6),
        },
        "deniedCapabilities": {
            "share": {"decision": "denied", "operation": _operation(7, status=403)},
            "export": {"decision": "denied", "operation": _operation(8, status=403)},
            "indexing": {"decision": "denied", "operation": _operation(9, status=403)},
        },
        "signedMedia": {
            "assetId": "asset-a",
            "signedUrlHash": "sha256:" + "4" * 64,
            "ttlSeconds": 300,
            "auditEventId": "audit-a",
            "issuanceOperation": _operation(10),
            "accessOperation": _operation(11, status=206),
            "auditReadbackOperation": _operation(12),
        },
        "positiveReadback": {
            "releaseId": RELEASE_ID,
            "manifestDigest": manifest_digest,
            "subjectHash": subject_hash,
            "entityRefs": ["entity-a"],
            "postIds": ["post-a"],
            "mediaAssetIds": ["asset-a"],
            "operation": _operation(13),
        },
    }


def _release(output_root: Path) -> Path:
    release = output_root / "data/releases" / RELEASE_ID
    write_json(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": RELEASE_ID,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "sourceRevision": SOURCE_REVISION,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": True,
            "rightsStatusCounts": {
                "verified": 1,
                "unverified": 1,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": ["asset-unverified-a"],
            "researchAcceptedCount": 2,
            "commercialAcceptedCount": 1,
            "canonicalMerkle": "sha256:" + "1" * 64,
            "executionIds": ["20260805--travel-image--research--scale-001"],
            "sourceDigests": [SOURCE_DIGEST_DOCUMENT],
        },
    )
    return release


def _output_path(
    output_root: Path,
    environment: str = ENVIRONMENT,
) -> Path:
    return (
        output_root
        / "env"
        / environment
        / "runs/data-release"
        / RELEASE_ID
        / VERIFY_RUN_ID
        / "research-isolation-verification.json"
    )


def _runtime_proof_path(
    output_root: Path,
    environment: str = ENVIRONMENT,
) -> Path:
    return _output_path(output_root, environment).with_name(
        "research-isolation-runtime-proof.json"
    )


def _runtime_proof_document(
    release: Path,
    *,
    environment: str = ENVIRONMENT,
) -> dict[str, object]:
    identity_contract = (
        ROOT / "quwoquan_service/services/user-service/contracts/account/"
        "account_session/operations.yaml"
    )
    proof = _positive_proof(ROOT, identity_contract)
    manifest_digest = payload_digest(release)
    proof["manifestDigest"] = manifest_digest
    proof["internalAppReadback"]["manifestDigest"] = manifest_digest
    proof["positiveReadback"]["manifestDigest"] = manifest_digest
    policy_path = ROOT / f"quwoquan_ops/environments/{environment}/runtime.yaml"
    document: dict[str, object] = {
        "schema": "quwoquan_data.research_isolation_verification",
        "environment": environment,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "verifyRunId": VERIFY_RUN_ID,
        "policyRef": (f"quwoquan_ops/environments/{environment}/runtime.yaml"),
        "policySha256": "sha256:"
        + hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "outcome": "PASS",
        "verifiedAt": "2026-08-05T00:00:01Z",
        **proof,
    }
    document["verificationChecksum"] = _checksum(document)
    return document


@pytest.mark.parametrize("environment", ["alpha", "beta", "gamma", "prod"])
def test_writer_freezes_typed_identity_adapter_blocker_without_secrets(
    tmp_path: Path,
    environment: str,
) -> None:
    release = _release(tmp_path)
    path = write_research_isolation_verification(
        environment=environment,
        release_id=RELEASE_ID,
        verify_run_id=VERIFY_RUN_ID,
        release_root=release,
        output_root=tmp_path,
        output_path=_output_path(tmp_path, environment),
    )

    receipt = read_json(path)
    assert receipt["outcome"] == "GATE_BLOCK"
    assert receipt["blocker"]["code"] == "DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE"
    assert receipt["manifestDigest"] == payload_digest(release)
    assert receipt["policyRef"] == (
        f"quwoquan_ops/environments/{environment}/runtime.yaml"
    )
    assert "token" not in json.dumps(receipt).casefold()
    assert (
        load_research_isolation_verification(
            path,
            environment=environment,
            release_id=RELEASE_ID,
            verify_run_id=VERIFY_RUN_ID,
            manifest_digest=payload_digest(release),
            require_pass=False,
        )
        == receipt
    )
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="DATA.RESEARCH.IDENTITY_ADAPTER_UNAVAILABLE",
    ):
        load_research_isolation_verification(
            path,
            environment=environment,
            release_id=RELEASE_ID,
            verify_run_id=VERIFY_RUN_ID,
            manifest_digest=payload_digest(release),
            require_pass=True,
        )


def test_writer_is_create_once_and_requires_canonical_run_path(tmp_path: Path) -> None:
    release = _release(tmp_path)
    path = _output_path(tmp_path)
    write_research_isolation_verification(
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        verify_run_id=VERIFY_RUN_ID,
        release_root=release,
        output_root=tmp_path,
        output_path=path,
    )
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="already exists",
    ):
        write_research_isolation_verification(
            environment=ENVIRONMENT,
            release_id=RELEASE_ID,
            verify_run_id=VERIFY_RUN_ID,
            release_root=release,
            output_root=tmp_path,
            output_path=path,
        )
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="canonical verify run path",
    ):
        write_research_isolation_verification(
            environment=ENVIRONMENT,
            release_id=RELEASE_ID,
            verify_run_id="verify-other",
            release_root=release,
            output_root=tmp_path,
            output_path=tmp_path / "self-reported.json",
        )
    rogue_release = _release(tmp_path / "rogue-output")
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="canonical immutable release root",
    ):
        write_research_isolation_verification(
            environment=ENVIRONMENT,
            release_id=RELEASE_ID,
            verify_run_id="verify-rogue-release",
            release_root=rogue_release,
            output_root=tmp_path,
            output_path=(
                tmp_path
                / "env/alpha/runs/data-release"
                / RELEASE_ID
                / "verify-rogue-release/research-isolation-verification.json"
            ),
        )


def test_writer_freezes_only_an_explicit_complete_runtime_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    release = _release(tmp_path)
    runtime_proof_path = _runtime_proof_path(tmp_path)
    runtime_proof = _runtime_proof_document(release)
    write_json(runtime_proof_path, runtime_proof)
    proof_bytes = runtime_proof_path.read_bytes()
    monkeypatch.setattr(isolation, "_identity_contract_available", lambda: True)
    monkeypatch.setattr(isolation, "_signed_media_contract_available", lambda: True)

    path = write_research_isolation_verification(
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        verify_run_id=VERIFY_RUN_ID,
        release_root=release,
        output_root=tmp_path,
        output_path=_output_path(tmp_path),
        runtime_proof_path=runtime_proof_path,
    )

    assert path.read_bytes() == proof_bytes
    receipt = load_research_isolation_verification(
        path,
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        verify_run_id=VERIFY_RUN_ID,
        manifest_digest=payload_digest(release),
        require_pass=True,
    )
    assert receipt == runtime_proof
    assert receipt["outcome"] == "PASS"
    assert (
        receipt["internalAppReadback"]["attestationIdHash"]
        == (receipt["identityIssuance"]["attestationIdHash"])
    )
    assert (
        len(
            {
                row["traceId"]
                for row in (
                    receipt["identityIssuance"]["operation"],
                    receipt["identityAttestation"]["operation"],
                    receipt["internalAppReadback"]["operation"],
                    receipt["anonymousContentProbe"]["operation"],
                    receipt["anonymousMediaProbe"]["operation"],
                    receipt["networkExposureReadback"]["operation"],
                    receipt["deniedCapabilities"]["share"]["operation"],
                    receipt["deniedCapabilities"]["export"]["operation"],
                    receipt["deniedCapabilities"]["indexing"]["operation"],
                    receipt["signedMedia"]["issuanceOperation"],
                    receipt["signedMedia"]["accessOperation"],
                    receipt["signedMedia"]["auditReadbackOperation"],
                    receipt["positiveReadback"]["operation"],
                )
            }
        )
        == 13
    )


def test_writer_rejects_noncanonical_drifted_or_secret_runtime_proof(
    tmp_path: Path,
) -> None:
    release = _release(tmp_path)
    proof = _runtime_proof_document(release)
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="canonical create-once verify run path",
    ):
        write_research_isolation_verification(
            environment=ENVIRONMENT,
            release_id=RELEASE_ID,
            verify_run_id=VERIFY_RUN_ID,
            release_root=release,
            output_root=tmp_path,
            output_path=_output_path(tmp_path),
            runtime_proof_path=tmp_path / "handwritten-proof.json",
        )

    runtime_proof_path = _runtime_proof_path(tmp_path)
    drifted = copy.deepcopy(proof)
    drifted["manifestDigest"] = "sha256:" + "9" * 64
    drifted["verificationChecksum"] = _checksum(
        {key: value for key, value in drifted.items() if key != "verificationChecksum"}
    )
    write_json(runtime_proof_path, drifted)
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="release/environment identity drift",
    ):
        write_research_isolation_verification(
            environment=ENVIRONMENT,
            release_id=RELEASE_ID,
            verify_run_id=VERIFY_RUN_ID,
            release_root=release,
            output_root=tmp_path,
            output_path=_output_path(tmp_path),
            runtime_proof_path=runtime_proof_path,
        )
    assert not _output_path(tmp_path).exists()

    leaked = copy.deepcopy(proof)
    leaked["accessToken"] = "must-never-be-retained"
    leaked["verificationChecksum"] = _checksum(
        {key: value for key, value in leaked.items() if key != "verificationChecksum"}
    )
    write_json(runtime_proof_path, leaked)
    with pytest.raises(
        ResearchIsolationVerificationError,
        match="forbidden secret field",
    ):
        write_research_isolation_verification(
            environment=ENVIRONMENT,
            release_id=RELEASE_ID,
            verify_run_id=VERIFY_RUN_ID,
            release_root=release,
            output_root=tmp_path,
            output_path=_output_path(tmp_path),
            runtime_proof_path=runtime_proof_path,
        )
    assert not _output_path(tmp_path).exists()


def test_schema_rejects_success_claim_without_runtime_proofs_or_with_token(
    tmp_path: Path,
) -> None:
    release = _release(tmp_path)
    path = write_research_isolation_verification(
        environment=ENVIRONMENT,
        release_id=RELEASE_ID,
        verify_run_id=VERIFY_RUN_ID,
        release_root=release,
        output_root=tmp_path,
        output_path=_output_path(tmp_path),
    )
    receipt = read_json(path)
    validator = Draft202012Validator(
        load_schema("release", "research_isolation_verification")
    )
    missing_proof = dict(receipt)
    missing_proof["outcome"] = "PASS"
    missing_proof.pop("blocker")
    with pytest.raises(ValidationError):
        validator.validate(missing_proof)
    leaked = dict(receipt)
    leaked["accessToken"] = "must-never-be-retained"
    with pytest.raises(ValidationError):
        validator.validate(leaked)


def test_positive_proof_validator_requires_all_thirteen_unique_live_operations(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    identity_contract = (
        repository_root / "quwoquan_service/contracts/account-session.yaml"
    )
    identity_contract.parent.mkdir(parents=True)
    identity_contract.write_text("api_routes: []\n", encoding="utf-8")
    proof = _positive_proof(repository_root, identity_contract)

    Draft202012Validator(
        load_schema("release", "research_isolation_verification")
    ).validate(
        {
            "schema": "quwoquan_data.research_isolation_verification",
            "environment": ENVIRONMENT,
            "releaseClass": "research",
            "productLifecycleState": "research",
            "verifyRunId": VERIFY_RUN_ID,
            "policyRef": "quwoquan_ops/environments/alpha/runtime.yaml",
            "policySha256": "sha256:" + "8" * 64,
            "outcome": "PASS",
            "verifiedAt": "2026-08-05T00:00:01Z",
            "verificationChecksum": "sha256:" + "9" * 64,
            **proof,
        }
    )

    validate_research_isolation_pass_proof(
        proof,
        policy_ttl=900,
        repository_root=repository_root,
        identity_contract=identity_contract,
    )

    wrong_status = copy.deepcopy(proof)
    wrong_status["anonymousContentProbe"]["operation"]["status"] = 200
    with pytest.raises(ResearchIsolationProofError, match="anonymous content"):
        validate_research_isolation_pass_proof(
            wrong_status,
            policy_ttl=900,
            repository_root=repository_root,
            identity_contract=identity_contract,
        )

    reused = copy.deepcopy(proof)
    reused["positiveReadback"]["operation"]["traceId"] = "trace-1"
    with pytest.raises(ResearchIsolationProofError, match="reused"):
        validate_research_isolation_pass_proof(
            reused,
            policy_ttl=900,
            repository_root=repository_root,
            identity_contract=identity_contract,
        )

    operation_with_unowned_field = copy.deepcopy(proof)
    operation_with_unowned_field["positiveReadback"]["operation"]["rawHeaders"] = {}
    with pytest.raises(ResearchIsolationProofError, match="operation fields"):
        validate_research_isolation_pass_proof(
            operation_with_unowned_field,
            policy_ttl=900,
            repository_root=repository_root,
            identity_contract=identity_contract,
        )

    expired_media_grant = copy.deepcopy(proof)
    expired_media_grant["signedMedia"]["ttlSeconds"] = 901
    with pytest.raises(ResearchIsolationProofError, match="TTL/audit"):
        validate_research_isolation_pass_proof(
            expired_media_grant,
            policy_ttl=900,
            repository_root=repository_root,
            identity_contract=identity_contract,
        )

    for field in ("manifestDigest", "subjectHash", "attestationIdHash"):
        unbound = copy.deepcopy(proof)
        unbound["internalAppReadback"][field] = "sha256:" + "8" * 64
        with pytest.raises(ResearchIsolationProofError, match="release-bound"):
            validate_research_isolation_pass_proof(
                unbound,
                policy_ttl=900,
                repository_root=repository_root,
                identity_contract=identity_contract,
            )

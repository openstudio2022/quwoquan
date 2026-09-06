# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-001
from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.ci.environment_scheduler import (
    append_task_state,
    canonical_digest,
    canonical_json_bytes,
    create_execution_request,
    dsse_pae,
    exact_file_digest,
    issue_environment_acceptance_fact,
    request_exact_ref,
    write_create_once,
)
from quwoquan_ops.ci.integration_qualification import (
    IntegrationQualificationError,
    issue_integration_qualification,
    validate_integration_qualification,
)
from quwoquan_ops.cli.lib.evidence_signing import (
    ENVIRONMENT_OPS_IDENTITY,
    INTEGRATION_SCHEDULER_IDENTITY,
)
from quwoquan_ops.tests.support.evidence_signing_test_support import (
    create_temporary_signing,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = (
    ROOT
    / "quwoquan_ops/environments/evidence/integration_qualification_fact.schema.json"
)
IMPACT = "sha256:" + "9" * 64
NOW = datetime.now(timezone.utc)
ENVIRONMENT_SIGNER = ENVIRONMENT_OPS_IDENTITY
QUALIFICATION_SIGNER = INTEGRATION_SCHEDULER_IDENTITY
EXPECTED_ENVIRONMENT_SIGNERS = {
    environment: ENVIRONMENT_SIGNER for environment in ("alpha", "beta", "gamma")
}
# 模块级临时 Ed25519 信任根：签名/验签都走真实 openssl，与生产同一编码 `ed25519:<base64>`。
_SIGNING = create_temporary_signing(Path(tempfile.mkdtemp(prefix="qwq-iqf-signing-")))
# 第二套互不相识的 key，用于“错误 key 验签必失败”用例。
_WRONG_SIGNING = create_temporary_signing(Path(tempfile.mkdtemp(prefix="qwq-iqf-wrong-signing-")))
environment_sign = _SIGNING.signer(ENVIRONMENT_SIGNER)
qualification_sign = _SIGNING.signer(QUALIFICATION_SIGNER)
environment_verify = _SIGNING.environment_verifier((ENVIRONMENT_SIGNER,))
qualification_verify = _SIGNING.verifier(QUALIFICATION_SIGNER)
wrong_environment_verify = _WRONG_SIGNING.environment_verifier((ENVIRONMENT_SIGNER,))
wrong_qualification_verify = _WRONG_SIGNING.verifier(QUALIFICATION_SIGNER)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()


def write(root: Path, ref: str, value: dict[str, object]) -> dict[str, str]:
    path = root / ref
    write_create_once(path, value)
    return {"ref": ref, "digest": exact_file_digest(path)}


def fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str], dict[str, str]]:
    repo = tmp_path / "repo"
    store = repo / ".qwq_output/env/repo/runs/qualification-test"
    repo.mkdir()
    git(repo, "init", "-b", "dev1.0")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "owned.txt").write_text("before\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    parent = git(repo, "rev-parse", "HEAD")
    (repo / "owned.txt").write_text("after\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "candidate")
    commit = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "show", "-s", "--format=%T", commit)
    candidate_body: dict[str, object] = {
        "schema": "quwoquan_ops.exact_integration_candidate.v1",
        "commit": commit,
        "tree": tree,
        "expectedParent": parent,
        "impactPlanDigest": IMPACT,
    }
    candidate_body["candidateId"] = canonical_digest(candidate_body)
    candidate = write(store, "candidate.json", candidate_body)

    def request(environment: str) -> dict[str, str]:
        path = create_execution_request(
            store_root=store,
            candidate_ref=candidate,
            environment=environment,
            impact_plan_digest=IMPACT,
            priority=1,
            created_at=NOW.isoformat(),
        )
        exact = request_exact_ref(store, path)
        append_task_state(
            store_root=store,
            request_ref=exact,
            state="queued",
            occurred_at=NOW.isoformat(),
        )
        if environment != "beta":
            append_task_state(
                store_root=store,
                request_ref=exact,
                state="mutation_started",
                occurred_at=NOW.isoformat(),
            )
        return exact

    def candidate_identity(environment: str) -> dict[str, str]:
        return {
            "candidateId": str(candidate_body["candidateId"]),
            "commit": commit,
            "tree": tree,
        }

    def evidence(environment: str, kind: str) -> dict[str, str]:
        status = {
            "runtime-identity": "ready",
            "data-lifecycle": "closed",
            "provider-readiness": "ready",
            "observability-readiness": "ready",
            "inspect": "passed",
            "doctor": "passed",
            "cleanup": "closed",
            "lease-closure": "released",
        }[kind]
        return write(
            store,
            f"evidence/{environment}-{kind}.json",
            {
                "schema": f"quwoquan_ops.environment_{kind}.v1",
                "role": kind,
                "status": status,
                "environment": environment,
                "profile": "integration",
                **candidate_identity(environment),
                "impactPlanDigest": IMPACT,
            },
        )

    def case_result(environment: str) -> dict[str, str]:
        value: dict[str, object] = {
            "objectId": f"{environment}-case",
            "specRef": "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-001",
            "caseId": f"{environment}-case",
            "producer": "ops",
            "layer": "environment_acceptance",
            "status": "passed",
            "target": {"kind": "operation", "id": f"{environment}-case"},
            "commitSha": commit,
            "contractGraphSourceHash": "4" * 64,
            "deploymentTarget": f"{environment}-local",
            "baselineId": "integration-qualification-v2",
            "packageDigest": "sha256:" + "5" * 64,
            "configurationDigest": "sha256:" + "6" * 64,
            "candidateManifestSha256": "7" * 64,
            "candidateDigest": candidate_body["candidateId"],
            "environment": environment,
            "provider": "first-party-https",
            "startedAt": NOW.isoformat(),
            "completedAt": (NOW + timedelta(minutes=1)).isoformat(),
            "runnerIdentity": "environment-scheduler",
            "artifactSha256": "8" * 64,
            "receiptRef": f"environment/{environment}/case.json",
        }
        return write(store, f"evidence/{environment}-case.json", value)

    def evidence_arguments(environment: str) -> dict[str, object]:
        return {
            "profile": "integration",
            "case_result_refs": [case_result(environment)],
            "runtime_identity": evidence(environment, "runtime-identity"),
            "data_lifecycle": evidence(environment, "data-lifecycle"),
            "provider_readiness": evidence(environment, "provider-readiness"),
            "observability_readiness": evidence(environment, "observability-readiness"),
            "inspect_evidence": evidence(environment, "inspect"),
            "doctor_evidence": evidence(environment, "doctor"),
            "cleanup_evidence": evidence(environment, "cleanup"),
            "lease_closure_evidence": evidence(environment, "lease-closure"),
        }

    alpha_request = request("alpha")
    alpha_path = issue_environment_acceptance_fact(
        store_root=store,
        request_ref=alpha_request,
        status="passed",
        predecessor=None,
        **evidence_arguments("alpha"),
        signer_identity=ENVIRONMENT_SIGNER,
        signer=environment_sign,
        expires_at=(NOW + timedelta(hours=2)).isoformat(),
        non_promotable=True,
        issued_at=NOW.isoformat(),
    )
    alpha = {
        "ref": alpha_path.relative_to(store).as_posix(),
        "digest": exact_file_digest(alpha_path),
    }
    beta_request = request("beta")
    beta_path = issue_environment_acceptance_fact(
        store_root=store,
        request_ref=beta_request,
        status="not_required",
        predecessor=alpha,
        **evidence_arguments("beta"),
        signer_identity=ENVIRONMENT_SIGNER,
        signer=environment_sign,
        expires_at=(NOW + timedelta(hours=2)).isoformat(),
        non_promotable=True,
        reason_code="IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED",
        issued_at=NOW.isoformat(),
    )
    beta = {
        "ref": beta_path.relative_to(store).as_posix(),
        "digest": exact_file_digest(beta_path),
    }
    gamma_request = request("gamma")
    gamma_path = issue_environment_acceptance_fact(
        store_root=store,
        request_ref=gamma_request,
        status="passed",
        predecessor=beta,
        **evidence_arguments("gamma"),
        signer_identity=ENVIRONMENT_SIGNER,
        signer=environment_sign,
        expires_at=(NOW + timedelta(hours=2)).isoformat(),
        non_promotable=True,
        issued_at=NOW.isoformat(),
    )
    gamma = {
        "ref": gamma_path.relative_to(store).as_posix(),
        "digest": exact_file_digest(gamma_path),
    }
    admission_body: dict[str, object] = {
        "schema": "quwoquan_ops.integration_publish_admission.v1",
        "decision": "admitted",
        "candidateId": candidate_body["candidateId"],
        "commit": commit,
        "tree": tree,
        "environmentFacts": {"alpha": alpha, "beta": beta},
    }
    admission = write(store, "admission.json", admission_body)
    result_body = {
        "schema": "quwoquan_ops.integration_publish_result.v1",
        "terminal": "published",
        "targetRef": "refs/heads/dev1.0",
        "afterOid": commit,
        "readbackOid": commit,
        "admission": admission,
    }
    publish_result = write(store, "publish-result.json", result_body)
    return repo, store, publish_result, gamma


def test_qualification_binds_current_dev_head_abg_and_dsse(tmp_path: Path) -> None:
    repo, store, publish_result, gamma = fixture(tmp_path)
    path = issue_integration_qualification(
        repository=repo,
        store_root=store,
        publish_result_ref=publish_result,
        gamma_acceptance_ref=gamma,
        signer_identity=QUALIFICATION_SIGNER,
        signer=qualification_sign,
        environment_signature_verifier=environment_verify,
        expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        issued_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
    )
    fact = json.loads(path.read_text())
    Draft202012Validator(
        json.loads(SCHEMA.read_text()), format_checker=FormatChecker()
    ).validate(fact)
    assert fact["devHead"] == git(repo, "rev-parse", "dev1.0")
    assert fact["environmentChain"]["gamma"] == gamma
    payload = base64.b64decode(fact["signer"]["payload"])
    assert fact["signer"]["signature"] == qualification_sign(
        dsse_pae(fact["signer"]["payloadType"], payload)
    )


@pytest.mark.parametrize("environment", ["alpha", "beta", "gamma"])
def test_issue_rejects_any_environment_signature_tamper(
    tmp_path: Path, environment: str
) -> None:
    repo, store, publish_result, gamma = fixture(tmp_path)
    publish_payload = json.loads((store / publish_result["ref"]).read_text())
    admission_ref = publish_payload["admission"]
    admission_path = store / admission_ref["ref"]
    admission = json.loads(admission_path.read_text())
    exact = (
        gamma if environment == "gamma" else admission["environmentFacts"][environment]
    )
    fact_path = store / exact["ref"]
    fact = json.loads(fact_path.read_text())
    fact["signer"]["signature"] = "ed25519:" + base64.b64encode(b"\0" * 64).decode("ascii")
    fact_path.write_bytes(canonical_json_bytes(fact) + b"\n")
    tampered = {
        "ref": exact["ref"],
        "digest": exact_file_digest(fact_path),
    }
    if environment == "gamma":
        gamma = tampered
    else:
        admission["environmentFacts"][environment] = tampered
        admission_path.write_bytes(canonical_json_bytes(admission) + b"\n")
        publish_payload["admission"]["digest"] = exact_file_digest(admission_path)
        publish_path = store / publish_result["ref"]
        publish_path.write_bytes(canonical_json_bytes(publish_payload) + b"\n")
        publish_result = {
            "ref": publish_result["ref"],
            "digest": exact_file_digest(publish_path),
        }
    with pytest.raises(IntegrationQualificationError, match="ENVIRONMENT_INVALID"):
        issue_integration_qualification(
            repository=repo,
            store_root=store,
            publish_result_ref=publish_result,
            gamma_acceptance_ref=gamma,
            signer_identity=QUALIFICATION_SIGNER,
            signer=qualification_sign,
            environment_signature_verifier=environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
            issued_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=1)).isoformat(),
        )


def test_issue_rejects_wrong_environment_signer_and_key(tmp_path: Path) -> None:
    repo, store, publish_result, gamma = fixture(tmp_path)
    gamma_path = store / gamma["ref"]
    unknown_signer_gamma = json.loads(gamma_path.read_text())
    unknown_signer_gamma["signer"]["identity"] = "spiffe://unknown"
    unknown_signer_gamma.pop("factId")
    unknown_signer_gamma["factId"] = canonical_digest(unknown_signer_gamma)
    gamma_path.write_bytes(canonical_json_bytes(unknown_signer_gamma) + b"\n")
    unknown_signer_ref = {
        "ref": gamma["ref"],
        "digest": exact_file_digest(gamma_path),
    }
    with pytest.raises(IntegrationQualificationError, match="ENVIRONMENT_INVALID"):
        issue_integration_qualification(
            repository=repo,
            store_root=store,
            publish_result_ref=publish_result,
            gamma_acceptance_ref=unknown_signer_ref,
            signer_identity=QUALIFICATION_SIGNER,
            signer=qualification_sign,
            environment_signature_verifier=environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
            issued_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=1)).isoformat(),
        )

    wrong_key_root = tmp_path / "wrong-key"
    wrong_key_root.mkdir()
    repo, store, publish_result, gamma = fixture(wrong_key_root)

    with pytest.raises(IntegrationQualificationError, match="ENVIRONMENT_INVALID"):
        issue_integration_qualification(
            repository=repo,
            store_root=store,
            publish_result_ref=publish_result,
            gamma_acceptance_ref=gamma,
            signer_identity=QUALIFICATION_SIGNER,
            signer=qualification_sign,
            environment_signature_verifier=wrong_environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
            issued_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=1)).isoformat(),
        )


def test_qualification_rejects_stale_dev_head_and_gamma(tmp_path: Path) -> None:
    repo, store, publish_result, gamma = fixture(tmp_path)
    (repo / "next.txt").write_text("next\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "next")
    with pytest.raises(IntegrationQualificationError, match="DEV_HEAD_DRIFT"):
        issue_integration_qualification(
            repository=repo,
            store_root=store,
            publish_result_ref=publish_result,
            gamma_acceptance_ref=gamma,
            signer_identity=QUALIFICATION_SIGNER,
            signer=qualification_sign,
            environment_signature_verifier=environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
            issued_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=1)).isoformat(),
        )


def test_validate_qualification_verifies_identity_payload_signature_and_expiry(
    tmp_path: Path,
) -> None:
    repo, store, publish_result, gamma = fixture(tmp_path)
    path = issue_integration_qualification(
        repository=repo,
        store_root=store,
        publish_result_ref=publish_result,
        gamma_acceptance_ref=gamma,
        signer_identity=QUALIFICATION_SIGNER,
        signer=qualification_sign,
        environment_signature_verifier=environment_verify,
        expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        issued_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
    )
    exact = {
        "ref": path.relative_to(store).as_posix(),
        "digest": exact_file_digest(path),
    }
    fact, normalized = validate_integration_qualification(
        repository=repo,
        store_root=store,
        qualification_ref=exact,
        expected_dev_head=git(repo, "rev-parse", "dev1.0"),
        expected_dev_tree=git(repo, "show", "-s", "--format=%T", "dev1.0"),
        verified_at=NOW.isoformat(),
        signature_verifier=qualification_verify,
        expected_signer_identity=QUALIFICATION_SIGNER,
        environment_signature_verifier=environment_verify,
        expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
    )
    assert fact["qualificationId"] == path.stem
    assert normalized == exact

    tampered = json.loads(path.read_text())
    tampered["signer"]["payload"] = base64.b64encode(b"{}").decode("ascii")
    tampered_ref = write(store, "tampered-qualification.json", tampered)
    with pytest.raises(IntegrationQualificationError, match="SIGNATURE_INVALID"):
        validate_integration_qualification(
            repository=repo,
            store_root=store,
            qualification_ref=tampered_ref,
            expected_dev_head=git(repo, "rev-parse", "dev1.0"),
            expected_dev_tree=git(repo, "show", "-s", "--format=%T", "dev1.0"),
            verified_at=NOW.isoformat(),
            signature_verifier=qualification_verify,
            expected_signer_identity=QUALIFICATION_SIGNER,
            environment_signature_verifier=environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        )

    with pytest.raises(IntegrationQualificationError, match="EXPIRED"):
        validate_integration_qualification(
            repository=repo,
            store_root=store,
            qualification_ref=exact,
            expected_dev_head=git(repo, "rev-parse", "dev1.0"),
            expected_dev_tree=git(repo, "show", "-s", "--format=%T", "dev1.0"),
            verified_at=(NOW + timedelta(hours=2)).isoformat(),
            signature_verifier=qualification_verify,
            expected_signer_identity=QUALIFICATION_SIGNER,
            environment_signature_verifier=environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        )


def test_validate_rejects_wrong_qualification_key_and_missing_environment_trust(
    tmp_path: Path,
) -> None:
    repo, store, publish_result, gamma = fixture(tmp_path)
    path = issue_integration_qualification(
        repository=repo,
        store_root=store,
        publish_result_ref=publish_result,
        gamma_acceptance_ref=gamma,
        signer_identity=QUALIFICATION_SIGNER,
        signer=qualification_sign,
        environment_signature_verifier=environment_verify,
        expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        issued_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
    )
    exact = {
        "ref": path.relative_to(store).as_posix(),
        "digest": exact_file_digest(path),
    }
    common = {
        "repository": repo,
        "store_root": store,
        "qualification_ref": exact,
        "expected_dev_head": git(repo, "rev-parse", "dev1.0"),
        "expected_dev_tree": git(repo, "show", "-s", "--format=%T", "dev1.0"),
        "verified_at": NOW.isoformat(),
        "expected_signer_identity": QUALIFICATION_SIGNER,
    }

    with pytest.raises(IntegrationQualificationError, match="SIGNATURE_INVALID"):
        validate_integration_qualification(
            **common,
            signature_verifier=wrong_qualification_verify,
            environment_signature_verifier=environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        )

    with pytest.raises(
        IntegrationQualificationError, match="ENVIRONMENT_VERIFIER_UNAVAILABLE"
    ):
        validate_integration_qualification(
            **common, signature_verifier=qualification_verify
        )

    with pytest.raises(IntegrationQualificationError, match="ENVIRONMENT_INVALID"):
        validate_integration_qualification(
            **common,
            signature_verifier=qualification_verify,
            environment_signature_verifier=wrong_environment_verify,
            expected_environment_signer_identities=EXPECTED_ENVIRONMENT_SIGNERS,
        )

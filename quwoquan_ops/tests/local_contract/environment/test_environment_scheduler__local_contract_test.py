# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md#gwt-001
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from datetime import datetime

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.ci.environment_scheduler import (
    NO_LIVE_ENVIRONMENT_REQUIRED,
    EnvironmentSchedulerError,
    append_task_state,
    canonical_digest,
    canonical_json_bytes,
    create_execution_request,
    current_task_state,
    dsse_pae,
    exact_file_digest,
    issue_environment_acceptance_fact,
    request_exact_ref,
    select_next_request,
    supersede_request,
    validate_environment_acceptance_fact,
    write_create_once,
)

ROOT = Path(__file__).resolve().parents[4]
REQUEST_SCHEMA = ROOT / "quwoquan_ops/environments/evidence/environment_execution_request.schema.json"
ACCEPTANCE_SCHEMA = ROOT / "quwoquan_ops/environments/evidence/environment_acceptance_fact.schema.json"
IMPACT = "sha256:" + "9" * 64
NOW = "2026-09-05T10:00:00Z"
EXPIRY = "2026-09-05T11:00:00Z"


def _write(root: Path, ref: str, value: dict[str, object]) -> dict[str, str]:
    path = root / ref
    write_create_once(path, value)
    return {"ref": ref, "digest": exact_file_digest(path)}


def _candidate(root: Path, *, suffix: str = "a") -> dict[str, str]:
    body: dict[str, object] = {
        "schema": "quwoquan_ops.exact_integration_candidate.v1",
        "claimRef": f"claims/{suffix}.json",
        "claimDigest": "sha256:" + "1" * 64,
        "ownerIdentityRef": "evidence-fingerprint-v1:sha256:" + "2" * 64,
        "expectedParent": suffix * 40,
        "commit": suffix * 40,
        "tree": ("b" if suffix != "b" else "c") * 40,
        "paths": ["owned.txt"],
        "pathsDigest": "sha256:" + "3" * 64,
        "impactPlanDigest": IMPACT,
        "createdAt": NOW,
    }
    body["candidateId"] = canonical_digest(body)
    return _write(root, f"candidates/{suffix}.json", body)


def _request(
    root: Path,
    *,
    environment: str,
    candidate: dict[str, str],
    priority: int = 1,
) -> tuple[Path, dict[str, str]]:
    path = create_execution_request(
        store_root=root,
        candidate_ref=candidate,
        environment=environment,
        impact_plan_digest=IMPACT,
        priority=priority,
        created_at=NOW,
    )
    return path, request_exact_ref(root, path)


def _queue(root: Path, request: dict[str, str]) -> None:
    append_task_state(store_root=root, request_ref=request, state="queued", occurred_at=NOW)


def _mutate(root: Path, request: dict[str, str]) -> None:
    _queue(root, request)
    append_task_state(
        store_root=root,
        request_ref=request,
        state="mutation_started",
        occurred_at=NOW,
    )


def _candidate_identity(root: Path, request: dict[str, str]) -> dict[str, str]:
    payload = json.loads((root / request["ref"]).read_text(encoding="utf-8"))
    return {
        key: payload["candidate"][key] for key in ("candidateId", "commit", "tree")
    }


def _case_result(
    root: Path,
    request: dict[str, str],
    *,
    profile: str,
    name: str,
    status: str = "passed",
) -> dict[str, str]:
    candidate = _candidate_identity(root, request)
    request_payload = json.loads((root / request["ref"]).read_text(encoding="utf-8"))
    environment = request_payload["environment"]
    value: dict[str, object] = {
        "objectId": name,
        "specRef": "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md#gwt-001",
        "caseId": name,
        "producer": "app" if profile == "release" else "ops",
        "layer": "user_acceptance" if profile == "release" else "environment_acceptance",
        "status": status,
        "target": {"kind": "operation", "id": name},
        "commitSha": candidate["commit"],
        "contractGraphSourceHash": "4" * 64,
        "deploymentTarget": f"{environment}-local",
        "baselineId": "environment-v2",
        "packageDigest": "sha256:" + "5" * 64,
        "configurationDigest": "sha256:" + "6" * 64,
        "candidateManifestSha256": "7" * 64,
        "candidateDigest": candidate["candidateId"],
        "environment": environment,
        "provider": "first-party-https",
        "startedAt": NOW,
        "completedAt": "2026-09-05T10:01:00Z",
        "runnerIdentity": "environment-scheduler",
        "artifactSha256": "8" * 64,
        "receiptRef": f"environment/{environment}/{name}",
    }
    if profile == "release":
        value.update(
            {
                "releaseDigest": "sha256:" + "a" * 64,
                "releaseId": "release-a",
                "targetUatBindingDigest": "sha256:" + "b" * 64,
                "entrySurface": "feed",
                "carrier": "article",
                "platform": "android",
                "deviceClass": "physical",
                "deviceIdentity": "android-device",
                "deviceRegistered": True,
                "uatProfile": "promotable",
                "nonPromotable": False,
                "artifactClass": "production_behavior",
                "physicalDevice": True,
            }
        )
    if status != "passed":
        value["reasonCode"] = "ENVIRONMENT.CASE_FAILED"
    return _write(root, f"evidence/{name}.json", value)


def _closure(
    root: Path,
    request: dict[str, str],
    *,
    profile: str,
    role: str,
    status: str = "passed",
) -> dict[str, str]:
    candidate = _candidate_identity(root, request)
    request_payload = json.loads((root / request["ref"]).read_text(encoding="utf-8"))
    return _write(
        root,
        f"evidence/{request_payload['environment']}-{role}.json",
        {
            "schema": f"quwoquan_ops.environment_{role}.v1",
            "role": role,
            "status": status,
            "environment": request_payload["environment"],
            "profile": profile,
            **candidate,
            "impactPlanDigest": IMPACT,
        },
    )


def _sign(pae: bytes) -> str:
    return "dsse-test:" + hashlib.sha256(pae).hexdigest()


def _issue(
    root: Path,
    request: dict[str, str],
    *,
    profile: str = "integration",
    status: str = "passed",
    predecessor: dict[str, str] | None = None,
    reason_code: str | None = None,
    case_status: str = "passed",
    role_status: dict[str, str] | None = None,
) -> Path:
    role_status = role_status or {}
    return issue_environment_acceptance_fact(
        store_root=root,
        request_ref=request,
        profile=profile,
        status=status,
        case_result_refs=[
            _case_result(
                root,
                request,
                profile=profile,
                name=f"{status}-{exact_file_digest(root / request['ref'])[-8:]}",
                status=case_status,
            )
        ],
        runtime_identity=_closure(
            root, request, profile=profile, role="runtime-identity",
            status=role_status.get("runtimeIdentity", "ready"),
        ),
        data_lifecycle=_closure(
            root, request, profile=profile, role="data-lifecycle",
            status=role_status.get("dataLifecycle", "closed"),
        ),
        provider_readiness=_closure(
            root, request, profile=profile, role="provider-readiness",
            status=role_status.get("providerReadiness", "ready"),
        ),
        observability_readiness=_closure(
            root, request, profile=profile, role="observability-readiness",
            status=role_status.get("observabilityReadiness", "ready"),
        ),
        inspect_evidence=_closure(
            root, request, profile=profile, role="inspect",
            status=role_status.get("inspectEvidence", "passed"),
        ),
        doctor_evidence=_closure(
            root, request, profile=profile, role="doctor",
            status=role_status.get("doctorEvidence", "passed"),
        ),
        cleanup_evidence=_closure(
            root, request, profile=profile, role="cleanup",
            status=role_status.get("cleanupEvidence", "closed"),
        ),
        lease_closure_evidence=_closure(
            root, request, profile=profile, role="lease-closure",
            status=role_status.get("leaseClosureEvidence", "released"),
        ),
        predecessor=predecessor,
        signer_identity="spiffe://quwoquan.local/environment-ops",
        signer=_sign,
        expires_at=EXPIRY,
        non_promotable=profile != "release",
        reason_code=reason_code,
        issued_at=NOW,
    )


def _exact(root: Path, path: Path) -> dict[str, str]:
    return {"ref": path.relative_to(root).as_posix(), "digest": exact_file_digest(path)}


def test_gamma_has_absolute_priority_and_candidate_environment_is_deduplicated(
    tmp_path: Path,
) -> None:
    candidate = _candidate(tmp_path)
    alpha_path, alpha = _request(tmp_path, environment="alpha", candidate=candidate, priority=999)
    gamma_path, gamma = _request(tmp_path, environment="gamma", candidate=candidate, priority=0)
    duplicate_path = create_execution_request(
        store_root=tmp_path,
        candidate_ref=candidate,
        environment="gamma",
        impact_plan_digest=IMPACT,
        priority=500,
        created_at="2026-09-05T10:30:00Z",
    )

    assert duplicate_path == gamma_path
    assert json.loads(gamma_path.read_text())["priority"] == 0
    validator = Draft202012Validator(
        json.loads(REQUEST_SCHEMA.read_text()), format_checker=FormatChecker()
    )
    validator.validate(json.loads(alpha_path.read_text()))
    validator.validate(json.loads(gamma_path.read_text()))
    assert select_next_request(store_root=tmp_path, request_refs=[alpha, gamma, gamma])[
        "environment"
    ] == "gamma"


def test_superseded_before_mutation_cancels_without_acceptance(tmp_path: Path) -> None:
    _, request = _request(tmp_path, environment="alpha", candidate=_candidate(tmp_path))
    _queue(tmp_path, request)

    supersede_request(store_root=tmp_path, request_ref=request, reason="new candidate", occurred_at=NOW)

    request_id = json.loads((tmp_path / request["ref"]).read_text())["requestId"]
    assert current_task_state(store_root=tmp_path, request_id=request_id) == "cancelled"
    with pytest.raises(EnvironmentSchedulerError, match="ACCEPTANCE_FORBIDDEN"):
        _issue(tmp_path, request)


def test_superseded_after_mutation_requires_safe_teardown_and_cannot_accept(
    tmp_path: Path,
) -> None:
    _, request = _request(tmp_path, environment="alpha", candidate=_candidate(tmp_path))
    _mutate(tmp_path, request)

    supersede_request(store_root=tmp_path, request_ref=request, reason="new dev head", occurred_at=NOW)

    request_id = json.loads((tmp_path / request["ref"]).read_text())["requestId"]
    assert current_task_state(store_root=tmp_path, request_id=request_id) == "safe_teardown_required"
    with pytest.raises(EnvironmentSchedulerError, match="ACCEPTANCE_FORBIDDEN"):
        _issue(tmp_path, request)


def test_pass_fact_binds_cleanup_lease_signature_and_exact_predecessor(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    _, alpha = _request(tmp_path, environment="alpha", candidate=candidate)
    _mutate(tmp_path, alpha)
    alpha_path = _issue(tmp_path, alpha)
    alpha_exact = _exact(tmp_path, alpha_path)

    _, beta = _request(tmp_path, environment="beta", candidate=candidate)
    _mutate(tmp_path, beta)
    beta_path = _issue(tmp_path, beta, predecessor=alpha_exact)
    beta_exact = _exact(tmp_path, beta_path)
    beta_fact = json.loads(beta_path.read_text())
    payload_bytes = __import__("base64").b64decode(beta_fact["signer"]["payload"])
    payload = json.loads(payload_bytes)

    _, gamma = _request(tmp_path, environment="gamma", candidate=candidate)
    _mutate(tmp_path, gamma)
    gamma_path = _issue(tmp_path, gamma, predecessor=beta_exact)
    gamma_fact = json.loads(gamma_path.read_text())

    assert json.loads(alpha_path.read_text())["predecessor"] is None
    assert beta_fact["schema"] == "quwoquan_ops.environment_acceptance_fact.v2"
    assert set(beta_fact["cleanupEvidence"]) == {"ref", "digest"}
    assert set(beta_fact["leaseClosureEvidence"]) == {"ref", "digest"}
    assert beta_fact["nonPromotable"] is True
    assert beta_fact["predecessor"] == alpha_exact
    assert gamma_fact["predecessor"] == beta_exact
    assert beta_fact["signer"]["signature"] == _sign(
        dsse_pae(beta_fact["signer"]["payloadType"], payload_bytes)
    )
    assert payload["candidate"] == beta_fact["candidate"]
    assert payload["impactPlanDigest"] == IMPACT
    assert "signer" not in payload and "factId" not in payload


def test_v2_environment_acceptance_schema_validates_scheduler_output(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    _, alpha = _request(tmp_path, environment="alpha", candidate=candidate)
    _mutate(tmp_path, alpha)
    alpha_path = _issue(tmp_path, alpha)
    validator = Draft202012Validator(
        json.loads(ACCEPTANCE_SCHEMA.read_text()), format_checker=FormatChecker()
    )
    validator.validate(json.loads(alpha_path.read_text()))

    _, beta = _request(tmp_path, environment="beta", candidate=candidate)
    _queue(tmp_path, beta)
    beta_path = _issue(
        tmp_path, beta, status="not_required", predecessor=_exact(tmp_path, alpha_path),
        reason_code=NO_LIVE_ENVIRONMENT_REQUIRED,
    )
    validator.validate(json.loads(beta_path.read_text()))


def test_not_required_is_restricted_to_typed_beta_reason(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    _, alpha = _request(tmp_path, environment="alpha", candidate=candidate)
    _mutate(tmp_path, alpha)
    alpha_path = _issue(tmp_path, alpha)
    alpha_exact = _exact(tmp_path, alpha_path)

    _, beta = _request(tmp_path, environment="beta", candidate=candidate)
    _queue(tmp_path, beta)
    with pytest.raises(EnvironmentSchedulerError, match="NOT_REQUIRED_INVALID"):
        _issue(tmp_path, beta, status="not_required", predecessor=alpha_exact, reason_code="SKIPPED")

    beta_path = _issue(
        tmp_path,
        beta,
        status="not_required",
        predecessor=alpha_exact,
        reason_code=NO_LIVE_ENVIRONMENT_REQUIRED,
    )
    assert json.loads(beta_path.read_text())["reasonCode"] == NO_LIVE_ENVIRONMENT_REQUIRED

    other_candidate = _candidate(tmp_path, suffix="c")
    _, gamma = _request(tmp_path, environment="gamma", candidate=other_candidate)
    _queue(tmp_path, gamma)
    with pytest.raises(EnvironmentSchedulerError, match="NOT_REQUIRED_INVALID"):
        _issue(
            tmp_path,
            gamma,
            status="not_required",
            predecessor=None,
            reason_code=NO_LIVE_ENVIRONMENT_REQUIRED,
        )


def test_create_once_conflict_rejects_different_bytes(tmp_path: Path) -> None:
    path = tmp_path / "facts" / "one.json"
    write_create_once(path, {"value": 1})
    write_create_once(path, {"value": 1})

    with pytest.raises(EnvironmentSchedulerError, match="CREATE_CONFLICT"):
        write_create_once(path, {"value": 2})
    assert path.read_bytes() == canonical_json_bytes({"value": 1}) + b"\n"


def test_v2_validator_rejects_expired_and_dsse_drift(tmp_path: Path) -> None:
    _, request = _request(tmp_path, environment="alpha", candidate=_candidate(tmp_path))
    _mutate(tmp_path, request)
    fact_path = _issue(tmp_path, request)
    fact = json.loads(fact_path.read_text())

    validated = validate_environment_acceptance_fact(
        fact, store_root=tmp_path, verify_references=True,
        accepted_at=datetime.fromisoformat("2026-09-05T10:30:00+00:00"),
    )
    assert validated["factId"] == fact["factId"]

    with pytest.raises(EnvironmentSchedulerError, match="ACCEPTANCE_EXPIRED"):
        validate_environment_acceptance_fact(
            fact, accepted_at=datetime.fromisoformat("2026-09-05T11:00:00+00:00")
        )

    drifted = dict(fact)
    drifted["cleanupEvidence"] = dict(drifted["cleanupEvidence"])
    drifted["cleanupEvidence"]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(EnvironmentSchedulerError, match="ACCEPTANCE_INVALID"):
        validate_environment_acceptance_fact(drifted)


def test_v2_rejects_failed_case_and_named_closure_evidence(tmp_path: Path) -> None:
    _, failed_case_request = _request(
        tmp_path, environment="alpha", candidate=_candidate(tmp_path)
    )
    _mutate(tmp_path, failed_case_request)
    with pytest.raises(
        EnvironmentSchedulerError,
        match="caseResultRefs.*status must be passed",
    ):
        _issue(tmp_path, failed_case_request, case_status="failed")

    other_root = tmp_path / "named-closure"
    _, open_cleanup_request = _request(
        other_root, environment="alpha", candidate=_candidate(other_root)
    )
    _mutate(other_root, open_cleanup_request)
    with pytest.raises(
        EnvironmentSchedulerError,
        match="cleanupEvidence does not prove closure",
    ):
        _issue(
            other_root,
            open_cleanup_request,
            role_status={"cleanupEvidence": "open"},
        )


def test_v2_rejects_profile_and_predecessor_identity_drift(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    _, alpha = _request(tmp_path, environment="alpha", candidate=candidate)
    _mutate(tmp_path, alpha)
    alpha_path = _issue(tmp_path, alpha, profile="smoke")

    _, beta = _request(tmp_path, environment="beta", candidate=candidate)
    _mutate(tmp_path, beta)
    with pytest.raises(
        EnvironmentSchedulerError,
        match="predecessor fact identity drifted",
    ):
        _issue(
            tmp_path,
            beta,
            profile="integration",
            predecessor=_exact(tmp_path, alpha_path),
        )

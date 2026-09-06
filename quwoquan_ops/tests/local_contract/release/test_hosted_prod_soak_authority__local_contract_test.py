# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import pytest
import yaml

from quwoquan_ops.ci import release_evidence_reader as lifecycle
from quwoquan_ops.cli.lib.environment_stability_final_acceptance import (
    REQUIRED_SOAK_CLAIMS,
)
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.ci.release_evidence_reader import sha256_file
from quwoquan_ops.tests.support.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)

ROOT = Path(__file__).resolve().parents[4]
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
SOURCE_SHA = "e" * 40
TREE_DIGEST = "sha1:" + "f" * 40


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _timestamp(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_hosted_soak_readback(
    path: Path,
    rollout_receipt: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    receipt = lifecycle._validate_soak_readback(payload, service="prod-stack")
    source = manifest["source"]
    configuration_packages = manifest["environmentArtifacts"]["prod"][
        "configurationPackages"
    ]
    expected_bindings = {
        "fullRolloutReceiptId": rollout_receipt["receiptId"],
        "candidateId": manifest["candidateId"],
        "candidateMaterialId": rollout_receipt["candidateMaterialId"],
        "prodActivationAdmissionRef": rollout_receipt["prodActivationAdmissionRef"],
        "prodActivationAdmissionOciDigest": rollout_receipt[
            "prodActivationAdmissionOciDigest"
        ],
        "prodActivationAdmissionPayloadDigest": rollout_receipt[
            "prodActivationAdmissionPayloadDigest"
        ],
        "prodActivationAdmissionId": rollout_receipt["prodActivationAdmissionId"],
        "candidateMaterialManifestRef": rollout_receipt[
            "candidateMaterialManifestRef"
        ],
        "candidateMaterialManifestOciDigest": rollout_receipt[
            "candidateMaterialManifestOciDigest"
        ],
        "candidateMaterialManifestPayloadDigest": rollout_receipt[
            "candidateMaterialManifestPayloadDigest"
        ],
        "serviceFactoryOciDigest": rollout_receipt["toServiceFactoryOciDigest"],
        "appFactoryOciDigest": rollout_receipt["toAppFactoryOciDigest"],
        "sourceGitSha": source["gitSha"],
        "sourceTreeDigest": source["treeDigest"],
        "rolloutConfigDigest": rollout_receipt["configDigest"],
        "configGraphDigest": _canonical_digest(configuration_packages),
        "contractGraphDigest": manifest["contractGraphDigest"],
    }
    for field, expected in expected_bindings.items():
        if receipt.get(field) != expected:
            raise ValueError(f"hosted prod soak {field} binding drifted")
    ended_at = dt.datetime.fromisoformat(
        str(receipt["soakEndedAt"]).replace("Z", "+00:00")
    )
    policy = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml").read_text(
            encoding="utf-8"
        )
    )
    maximum_age = int(policy["readback"]["authority_max_age_seconds"])
    if (dt.datetime.now(dt.timezone.utc) - ended_at).total_seconds() > maximum_age:
        raise ValueError("hosted prod soak receipt is stale")
    approval = receipt["approval"]
    if (
        approval.get("kind") != "github-production-environment"
        or approval.get("environment") != "production"
        or approval.get("sourceGitSha") != source["gitSha"]
        or approval.get("candidateMaterialId") != receipt["candidateMaterialId"]
        or approval.get("prodActivationAdmissionId")
        != receipt["prodActivationAdmissionId"]
    ):
        raise ValueError("hosted prod approval is not candidate-bound")
    return receipt


def verify_canonical_hosted_prod_soak(
    path: Path,
    rollout_receipt: dict[str, Any],
    manifest: dict[str, Any],
) -> Any:
    receipt = _validate_hosted_soak_readback(path, rollout_receipt, manifest)
    receipt_id = receipt["receiptId"]
    with __import__("tempfile").TemporaryDirectory() as temporary:
        remote_path = Path(temporary) / "soak-readback.json"
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh"),
                "--plane",
                "service",
                "--operation",
                "release-ledger-soak-receipt",
                "--service",
                "prod-stack",
                "--receipt-id",
                receipt_id,
                "--output-path",
                str(remote_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not remote_path.is_file():
            raise RuntimeError(result.stderr or result.stdout or "hosted receipt missing")
        if remote_path.read_bytes() != path.read_bytes():
            raise ValueError("hosted prod soak receipt identity drifted")
    return __import__(
        "quwoquan_ops.cli.lib.environment_stability_final_acceptance.model",
        fromlist=["VerifiedAuthority"],
    ).VerifiedAuthority(
        authority=lifecycle.HOSTED_AUTHORITY,
        subject_digest=sha256_file(path),
        verification_digest=_canonical_digest({"receiptId": receipt_id}),
        claims=REQUIRED_SOAK_CLAIMS,
    )


def _full_request(*, verified_at: str) -> dict[str, Any]:
    promotion = promotion_evidence(
        candidate_id=DIGEST_B,
        artifact_digest=DIGEST_C,
        stage="100",
    )
    promotion["candidateMaterialId"] = promotion.pop("artifactDigest")
    unsigned = dict(promotion)
    unsigned.pop("evidenceDigest")
    promotion["evidenceDigest"] = _canonical_digest(unsigned)
    return {
        "schema": hosted_release_ledger.REQUEST_SCHEMA,
        "service": "prod-stack",
        "fromCandidateDigest": DIGEST_A,
        "toCandidateDigest": DIGEST_B,
        "step": "100",
        "stage": "100",
        "triggerStage": "100",
        "fromServiceFactoryOciDigest": DIGEST_A,
        "toServiceFactoryOciDigest": DIGEST_B,
        "fromAppFactoryOciDigest": DIGEST_A,
        "toAppFactoryOciDigest": DIGEST_B,
        "decision": "continue",
        "rollbackOutcome": "not_triggered",
        "rollbackEvidence": {"triggered": False},
        "candidateMaterialId": DIGEST_C,
        "prodActivationAdmissionRef": (
            "ghcr.io/owner/quwoquan/prod-admission@" + DIGEST_A
        ),
        "prodActivationAdmissionOciDigest": DIGEST_A,
        "prodActivationAdmissionPayloadDigest": DIGEST_A,
        "prodActivationAdmissionId": DIGEST_A,
        "candidateMaterialManifestRef": (
            "ghcr.io/owner/quwoquan/candidate-material@" + DIGEST_B
        ),
        "candidateMaterialManifestOciDigest": DIGEST_B,
        "candidateMaterialManifestPayloadDigest": DIGEST_B,
        "previousReleasedRef": "ghcr.io/owner/quwoquan/released-prod@" + DIGEST_D,
        "previousReleasedOciDigest": DIGEST_D,
        "previousReleasedPayloadDigest": DIGEST_D,
        "previousReleasedId": DIGEST_D,
        "imageDigest": DIGEST_D,
        "configDigest": DIGEST_A,
        "contractGraphDigest": DIGEST_D,
        "adapterDigest": DIGEST_C,
        "expectedGeneration": 0,
        "sloReadback": {
            "sampleCount": 100,
            "promotionEvidence": promotion,
        },
        "postChecks": [
            {
                "name": "health",
                "status": "passed",
                "receiptDigest": DIGEST_D,
            }
        ],
        "lastGoodCandidateDigest": DIGEST_B,
        "verifiedAt": verified_at,
    }


def _expected_credentials(verified_at: str, expires_at: str) -> list[dict[str, str]]:
    policy = yaml.safe_load(
        (
            ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
        ).read_text(encoding="utf-8")
    )
    result: list[dict[str, str]] = []
    for plane in policy["planes"]:
        if (
            plane.get("access") != "read-write"
            or "100" not in (plane.get("appliesToStages") or [])
        ):
            continue
        governed = plane.get("rootlessGovernedComposeServices") or []
        support = plane.get("rootlessSupportComposeServices") or []
        if (
            "rootlessGovernedComposeServices" in plane
            or "rootlessSupportComposeServices" in plane
        ) and not (governed or support):
            continue
        result.append(
            {
                "plane": plane["plane"],
                "account": plane["account"],
                "reference": f"github-secret://{plane['sshKeySecret']}",
                "publicDigest": DIGEST_A,
                "issuer": "github-actions-production-environment",
                "expiresAt": expires_at,
                "verifiedAt": verified_at,
            }
        )
    return result


def _fixture(
    temporary: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    ledger_root = temporary / "hosted-ledger"
    full_readback = hosted_release_ledger.commit(
        ledger_root,
        _full_request(
            verified_at=_timestamp(now - dt.timedelta(days=1, seconds=400))
        ),
    )
    full_receipt = full_readback["receipt"]
    manifest = {
        "candidateId": DIGEST_B,
        "artifactDigest": DIGEST_D,
        "source": {
            "gitSha": SOURCE_SHA,
            "treeDigest": TREE_DIGEST,
        },
        "environmentArtifacts": {
            "prod": {
                "configurationPackages": {
                    "content-service": {
                        "path": "packages/prod/content.yaml",
                        "digest": DIGEST_A,
                    }
                }
            }
        },
        "contractGraphDigest": DIGEST_D,
    }
    observed_at = _timestamp(now - dt.timedelta(seconds=1))
    expires_at = _timestamp(now + dt.timedelta(days=30))
    policy_path = (
        ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    )
    credential_policy_path = (
        ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    soak_request = {
        "schema": hosted_release_ledger.SOAK_REQUEST_SCHEMA,
        "service": "prod-stack",
        "environment": "prod",
        "target": "prod-hosted",
        "fullRolloutReceiptId": full_receipt["receiptId"],
        "candidateId": DIGEST_B,
        "candidateMaterialId": full_receipt["candidateMaterialId"],
        "prodActivationAdmissionRef": full_receipt["prodActivationAdmissionRef"],
        "prodActivationAdmissionOciDigest": full_receipt[
            "prodActivationAdmissionOciDigest"
        ],
        "prodActivationAdmissionPayloadDigest": full_receipt[
            "prodActivationAdmissionPayloadDigest"
        ],
        "prodActivationAdmissionId": full_receipt["prodActivationAdmissionId"],
        "candidateMaterialManifestRef": full_receipt[
            "candidateMaterialManifestRef"
        ],
        "candidateMaterialManifestOciDigest": full_receipt[
            "candidateMaterialManifestOciDigest"
        ],
        "candidateMaterialManifestPayloadDigest": full_receipt[
            "candidateMaterialManifestPayloadDigest"
        ],
        "serviceFactoryOciDigest": full_receipt["toServiceFactoryOciDigest"],
        "appFactoryOciDigest": full_receipt["toAppFactoryOciDigest"],
        "releasedRef": "ghcr.io/owner/quwoquan/released-prod@" + DIGEST_D,
        "releasedOciDigest": DIGEST_D,
        "releasedPayloadDigest": DIGEST_D,
        "releasedId": DIGEST_D,
        "sourceGitSha": SOURCE_SHA,
        "sourceTreeDigest": TREE_DIGEST,
        "rolloutConfigDigest": DIGEST_A,
        "configGraphDigest": _canonical_digest(
            manifest["environmentArtifacts"]["prod"]["configurationPackages"]
        ),
        "contractGraphDigest": DIGEST_D,
        "requiredSoakSeconds": 86400,
        "soakPolicyDigest": sha256_file(policy_path),
        "credentialPolicyDigest": sha256_file(credential_policy_path),
        "slo": {
            "source": "prometheus",
            "observedAt": observed_at,
            "windowSeconds": 86400,
            "minimumSamples": 100,
            "sampleCount": 200,
            "status": "passed",
            "decision": "continue",
            "values": {
                "errorRate": 0.001,
                "p95Ms": 100.0,
                "redisErrorRate": 0.001,
            },
            "receiptDigest": DIGEST_A,
        },
        "alerts": {
            "source": "alertmanager",
            "observedAt": observed_at,
            "status": "passed",
            "activeFiring": 0,
            "receiptDigest": DIGEST_B,
        },
        "health": {
            "source": "stackctl",
            "observedAt": observed_at,
            "target": "prod-hosted",
            "scope": "full",
            "status": "passed",
            "receiptDigest": DIGEST_C,
        },
        "credentials": _expected_credentials(observed_at, expires_at),
        "approval": {
            "kind": "github-production-environment",
            "repository": "owner/quwoquan",
            "sourceGitSha": SOURCE_SHA,
            "candidateMaterialId": full_receipt["candidateMaterialId"],
            "prodActivationAdmissionId": full_receipt["prodActivationAdmissionId"],
            "environment": "production",
            "workflowRunId": "42",
            "workflowRunAttempt": "1",
            "actor": "deployer",
            "receiptDigest": DIGEST_D,
            "verifiedAt": observed_at,
        },
    }
    soak_readback = hosted_release_ledger.commit_soak(ledger_root, soak_request)
    path = temporary / "prod-soak-readback.json"
    path.write_text(
        json.dumps(
            soak_readback,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path, full_receipt, manifest


def _remote_readback(path: Path) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        output = Path(argv[argv.index("--output-path") + 1])
        output.write_bytes(path.read_bytes())
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


def _rewrite(
    path: Path,
    change: Callable[[dict[str, Any]], None],
    *,
    rehash: bool,
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    receipt = payload["receipt"]
    change(receipt)
    if rehash:
        receipt["receiptId"] = lifecycle._receipt_id(receipt)
        payload["receiptRef"] = f"receipt:hosted-soak:{receipt['receiptId']}"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def test_trusted_hosted_soak_readback_returns_derived_claims(tmp_path: Path) -> None:
    path, rollout, manifest = _fixture(tmp_path)
    with patch(
        "quwoquan_ops.cli.lib.environment_stability_final_acceptance.subprocess.run",
        _remote_readback(path),
    ):
        verified = verify_canonical_hosted_prod_soak(path, rollout, manifest)

    assert verified.authority == lifecycle.HOSTED_AUTHORITY
    assert verified.subject_digest == sha256_file(path)
    assert verified.claims == REQUIRED_SOAK_CLAIMS


def test_producer_projects_raw_observations_without_secret_material(
    tmp_path: Path,
) -> None:
    # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-002.t2
    soak_path, _, _ = _fixture(tmp_path)
    soak = json.loads(soak_path.read_text(encoding="utf-8"))["receipt"]
    projected = {
        field: soak[field]
        for field in hosted_release_ledger.SOAK_REQUEST_FIELDS
        if field != "schema"
    }
    projected["schema"] = hosted_release_ledger.SOAK_REQUEST_SCHEMA
    request = hosted_release_ledger._canonical_bytes(projected)

    assert json.loads(request)["schema"] == hosted_release_ledger.SOAK_REQUEST_SCHEMA
    assert json.loads(request)["fullRolloutReceiptId"] == soak[
        "fullRolloutReceiptId"
    ]
    assert json.loads(request)["requiredSoakSeconds"] == 86400
    assert json.loads(request)["slo"]["windowSeconds"] == 86400
    assert json.loads(request)["credentials"] == soak["credentials"]
    assert json.loads(request)["candidateMaterialId"] == soak["candidateMaterialId"]
    assert json.loads(request)["prodActivationAdmissionId"] == soak[
        "prodActivationAdmissionId"
    ]
    assert json.loads(request)["releasedId"] == soak["releasedId"]
    assert "baseUrl" not in json.loads(request)["slo"]
    assert "PRIVATE KEY" not in request.decode("utf-8")

def test_collector_uses_canonical_post_100_soak_window_for_prometheus(
    tmp_path: Path,
) -> None:
    # stackctl import currently has an out-of-scope wiring blocker in this shared tree;
    # import the collector against the exact minimal surface it consumes.
    import importlib
    import sys
    import types

    fake_stackctl = types.ModuleType("quwoquan_ops.cli.stackctl")
    fake_stackctl._read_prometheus_slo = lambda *args, **kwargs: {}
    with patch.dict(sys.modules, {"quwoquan_ops.cli.stackctl": fake_stackctl}):
        collector = importlib.import_module(
            "quwoquan_ops.ci.collect_prod_soak_observations"
        )

    policy_path = ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    assert policy["readback"]["window"] == "5m"
    assert policy["readback"]["post_100_soak_window"] == "24h"

    readback_path = tmp_path / "100-readback.json"
    readback_path.write_text("{}\n", encoding="utf-8")
    observed_slo = {
        "source": "prometheus",
        "queriedAt": _timestamp(dt.datetime.now(dt.timezone.utc)),
        "window": "24h",
        "minimumSamples": 100,
        "values": {
            "errorRate": 0.001,
            "p95Ms": 100.0,
            "redisErrorRate": 0.001,
            "sampleCount": 200,
        },
    }
    completed_health = subprocess.CompletedProcess([], 0, "", "")
    with patch.object(collector, "_wait_for_authoritative_window") as wait_window, patch.object(
        collector.subprocess, "run", return_value=completed_health
    ), patch.object(
        collector.stackctl, "_read_prometheus_slo", return_value=observed_slo
    ) as read_slo, patch.object(
        collector, "_read_alertmanager", return_value={
            "schema": "prod-alertmanager-soak-observation",
            "source": "alertmanager",
            "queriedAt": observed_slo["queriedAt"],
            "status": "passed",
            "activeFiring": 0,
        }
    ):
        collector.collect(
            full_readback_path=readback_path,
            service="prod-stack",
            prometheus_service="prod-stack",
            prometheus_url="https://prometheus.invalid",
            alertmanager_url="https://alertmanager.invalid",
            soak_policy_path=policy_path,
            health_report_dir=tmp_path / "health",
            slo_output=tmp_path / "slo.json",
            alerts_output=tmp_path / "alerts.json",
        )

    wait_window.assert_called_once_with(
        {}, service="prod-stack", required_seconds=86400
    )
    assert read_slo.call_args.kwargs["window_override"] == "24h"


def test_collector_treats_error_rate_as_failure_ratio_and_fails_closed() -> None:
    import importlib
    import sys
    import types

    fake_stackctl = types.ModuleType("quwoquan_ops.cli.stackctl")
    fake_stackctl._read_prometheus_slo = lambda *args, **kwargs: {}
    with patch.dict(sys.modules, {"quwoquan_ops.cli.stackctl": fake_stackctl}):
        collector = importlib.reload(
            importlib.import_module("quwoquan_ops.ci.collect_prod_soak_observations")
        )
    policy = {
        "readback": {"minimum_samples": 100},
        "thresholds": {
            "error_rate": {"warn": 0.01},
            "p95_ms": {"warn": 300},
            "redis_error_rate": {"warn": 0.01},
        },
    }
    evidence = {
        "source": "prometheus",
        "queriedAt": "2026-09-06T00:00:00Z",
        "window": "24h",
        "minimumSamples": 100,
        "values": {
            "errorRate": 0.02,
            "p95Ms": 100.0,
            "redisErrorRate": 0.001,
            "sampleCount": 200,
        },
    }
    with pytest.raises(RuntimeError, match="errorRate.*threshold"):
        collector._validate_slo_observation(
            evidence, soak_window="24h", required_seconds=86400, policy=policy
        )
    evidence["values"]["errorRate"] = float("nan")
    with pytest.raises(RuntimeError, match="failure ratio"):
        collector._validate_slo_observation(
            evidence, soak_window="24h", required_seconds=86400, policy=policy
        )


def test_forged_self_hash_is_rejected(tmp_path: Path) -> None:
    path, rollout, manifest = _fixture(tmp_path)
    _rewrite(
        path,
        lambda receipt: receipt.__setitem__("soakDurationSeconds", 999),
        rehash=False,
    )
    with pytest.raises(ValueError, match="identity"):
        verify_canonical_hosted_prod_soak(path, rollout, manifest)


def test_stale_soak_is_rejected(tmp_path: Path) -> None:
    path, rollout, manifest = _fixture(tmp_path)

    def stale(receipt: dict[str, Any]) -> None:
        end = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
        start = end - dt.timedelta(seconds=receipt["soakDurationSeconds"])
        receipt["soakStartedAt"] = _timestamp(start)
        receipt["soakEndedAt"] = _timestamp(end)
        receipt["verifiedAt"] = _timestamp(end)
        for name in ("slo", "alerts", "health"):
            receipt[name]["observedAt"] = _timestamp(end)
        for credential in receipt["credentials"]:
            credential["verifiedAt"] = _timestamp(end)

    _rewrite(path, stale, rehash=True)
    with patch(
        "quwoquan_ops.cli.lib.environment_stability_final_acceptance.subprocess.run",
        _remote_readback(path),
    ), pytest.raises(ValueError, match="stale"):
        verify_canonical_hosted_prod_soak(path, rollout, manifest)


def test_missing_credential_is_rejected(tmp_path: Path) -> None:
    path, rollout, manifest = _fixture(tmp_path)
    _rewrite(
        path,
        lambda receipt: receipt.__setitem__("credentials", []),
        rehash=True,
    )
    with pytest.raises(ValueError, match="credentials"):
        verify_canonical_hosted_prod_soak(path, rollout, manifest)


def test_unapproved_soak_is_rejected(tmp_path: Path) -> None:
    path, rollout, manifest = _fixture(tmp_path)

    def unapproved(receipt: dict[str, Any]) -> None:
        receipt["approval"]["candidateMaterialId"] = DIGEST_A

    _rewrite(path, unapproved, rehash=True)
    with pytest.raises(ValueError, match="approval"):
        verify_canonical_hosted_prod_soak(path, rollout, manifest)


def test_candidate_drift_is_rejected(tmp_path: Path) -> None:
    path, rollout, manifest = _fixture(tmp_path)
    _rewrite(
        path,
        lambda receipt: receipt.__setitem__("candidateId", DIGEST_A),
        rehash=True,
    )
    with patch(
        "quwoquan_ops.cli.lib.environment_stability_final_acceptance.subprocess.run",
        _remote_readback(path),
    ), pytest.raises(ValueError, match="candidateId"):
        verify_canonical_hosted_prod_soak(path, rollout, manifest)


def test_local_synthetic_receipt_without_hosted_readback_is_rejected(
    tmp_path: Path,
) -> None:
    path, rollout, manifest = _fixture(tmp_path)

    def unavailable(
        argv: list[str], **_: Any
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, "", "hosted receipt missing")

    with patch(
        "quwoquan_ops.cli.lib.environment_stability_final_acceptance.subprocess.run",
        unavailable,
    ), pytest.raises(RuntimeError, match="hosted receipt missing"):
        verify_canonical_hosted_prod_soak(path, rollout, manifest)

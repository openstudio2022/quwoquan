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

from quwoquan_ops.ci import render_release_lifecycle_receipts as lifecycle
from quwoquan_ops.cli.lib.environment_stability_final_acceptance import (
    REQUIRED_SOAK_CLAIMS,
    verify_canonical_hosted_prod_soak,
)
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import sha256_file

ROOT = Path(__file__).resolve().parents[3]
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


def _full_request(*, verified_at: str) -> dict[str, Any]:
    return {
        "schema": hosted_release_ledger.REQUEST_SCHEMA,
        "service": "prod-stack",
        "fromCandidateDigest": DIGEST_A,
        "toCandidateDigest": DIGEST_B,
        "step": "100",
        "stage": "full",
        "triggerStage": "full",
        "fromReleaseEvidenceRef": (
            "ghcr.io/owner/quwoquan/release-artifact@" + DIGEST_A
        ),
        "toReleaseEvidenceRef": (
            "ghcr.io/owner/quwoquan/release-artifact@" + DIGEST_B
        ),
        "fromImageTransportTag": "sha-before",
        "toImageTransportTag": "sha-release",
        "decision": "continue",
        "rollbackOutcome": "not_triggered",
        "rollbackEvidence": {"triggered": False},
        "artifactDigest": DIGEST_C,
        "imageDigest": DIGEST_D,
        "configDigest": DIGEST_A,
        "contractGraphDigest": DIGEST_D,
        "adapterDigest": DIGEST_C,
        "expectedGeneration": 0,
        "sloReadback": {"sampleCount": 100},
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
            or "full" not in (plane.get("appliesToStages") or [])
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
        _full_request(verified_at=_timestamp(now - dt.timedelta(seconds=400))),
    )
    full_receipt = full_readback["receipt"]
    manifest = {
        "candidateId": DIGEST_B,
        "artifactDigest": DIGEST_D,
        "source": {
            "gitSha": SOURCE_SHA,
            "treeDigest": TREE_DIGEST,
        },
        "configurationPackages": {
            "prod": {
                "content-service": {
                    "path": "packages/prod/content.yaml",
                    "digest": DIGEST_A,
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
        "rolloutArtifactDigest": DIGEST_C,
        "artifactDigest": DIGEST_D,
        "sourceGitSha": SOURCE_SHA,
        "sourceTreeDigest": TREE_DIGEST,
        "rolloutConfigDigest": DIGEST_A,
        "configGraphDigest": _canonical_digest(
            manifest["configurationPackages"]
        ),
        "contractGraphDigest": DIGEST_D,
        "requiredSoakSeconds": 300,
        "soakPolicyDigest": sha256_file(policy_path),
        "credentialPolicyDigest": sha256_file(credential_policy_path),
        "slo": {
            "source": "prometheus",
            "observedAt": observed_at,
            "windowSeconds": 300,
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
            "kind": "github-reviewed-mainline",
            "repository": "owner/quwoquan",
            "sourceGitSha": SOURCE_SHA,
            "artifactDigest": DIGEST_D,
            "pullRequest": 42,
            "approvers": ["reviewer"],
            "distinctPrincipals": 2,
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
    soak_path, rollout, manifest = _fixture(tmp_path)
    soak = json.loads(soak_path.read_text(encoding="utf-8"))["receipt"]

    def write(name: str, payload: dict[str, Any]) -> Path:
        path = tmp_path / name
        path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    full_readback = {
        "schema": lifecycle.HOSTED_RECEIPT_READBACK_SCHEMA,
        "authority": lifecycle.HOSTED_AUTHORITY,
        "receipt": rollout,
        "receiptRef": f"receipt:hosted:{rollout['receiptId']}",
    }
    slo_path = write(
        "slo.json",
        {
            "source": "prometheus",
            "baseUrl": "https://prometheus.invalid",
            "queriedAt": soak["slo"]["observedAt"],
            "window": "5m",
            "minimumSamples": 100,
            "queries": {"errorRate": "query"},
            "values": {
                **soak["slo"]["values"],
                "sampleCount": soak["slo"]["sampleCount"],
            },
        },
    )
    alerts_path = write(
        "alerts.json",
        {
            "schema": "prod-alertmanager-soak-observation",
            "source": "alertmanager",
            "queriedAt": soak["alerts"]["observedAt"],
            "status": "passed",
            "activeFiring": 0,
        },
    )
    health_path = write(
        "health.json",
        {
            "command": "health",
            "target": "prod-hosted",
            "scope": "full",
            "readOnly": False,
            "findings": [],
            "checks": [{"name": "service", "ok": True}],
            "timestamp": soak["health"]["observedAt"],
        },
    )
    credentials_path = write(
        "credentials.json",
        {
            "schema": "prod-plane-credential-evidence",
            "stage": "full",
            "verifiedAt": soak["credentials"][0]["verifiedAt"],
            "credentials": soak["credentials"],
        },
    )
    governance_path = write(
        "governance.json",
        {
            "schema": "prod-release-governance-receipt",
            "repository": "owner/quwoquan",
            "gitSha": SOURCE_SHA,
            "artifactDigest": DIGEST_D,
            "pullRequest": 42,
            "author": "author",
            "mergedBy": "merger",
            "approvers": ["reviewer"],
            "distinctPrincipals": ["author", "merger", "reviewer"],
            "verifiedAt": soak["approval"]["verifiedAt"],
        },
    )
    credential_policy_path = (
        ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    soak_policy_path = (
        ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    )
    with patch.object(lifecycle, "validate_manifest"):
        request = lifecycle.render_prod_soak_request(
            manifest=manifest,
            service="prod-stack",
            full_readback=full_readback,
            slo=json.loads(slo_path.read_text()),
            slo_path=slo_path,
            alerts=json.loads(alerts_path.read_text()),
            alerts_path=alerts_path,
            health=json.loads(health_path.read_text()),
            health_path=health_path,
            credential_evidence=json.loads(credentials_path.read_text()),
            credential_policy=yaml.safe_load(
                credential_policy_path.read_text(encoding="utf-8")
            ),
            credential_policy_path=credential_policy_path,
            governance=json.loads(governance_path.read_text()),
            governance_path=governance_path,
            soak_policy=yaml.safe_load(
                soak_policy_path.read_text(encoding="utf-8")
            ),
            soak_policy_path=soak_policy_path,
        )

    assert request["schema"] == hosted_release_ledger.SOAK_REQUEST_SCHEMA
    assert request["fullRolloutReceiptId"] == rollout["receiptId"]
    assert request["credentials"] == soak["credentials"]
    assert "baseUrl" not in request["slo"]
    assert "PRIVATE KEY" not in json.dumps(request)


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
        receipt["approval"]["approvers"] = []
        receipt["approval"]["distinctPrincipals"] = 1

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

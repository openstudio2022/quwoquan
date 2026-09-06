"""prod hosted ledger readback 与 hosted soak authority 校验（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from quwoquan_ops.ci import release_evidence_reader as lifecycle
from quwoquan_ops.ci.release_evidence_reader import (
    DIGEST_PATTERN,
    sha256_file,
)

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    LoadedReceipt,
    MAX_FUTURE_SKEW_SECONDS,
    REQUIRED_SOAK_CLAIMS,
    SoakAuthorityVerifier,
    VerifiedAuthority,
    _Evaluation,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (
    _canonical_digest,
    _sha256,
    _timestamp,
    _walk,
)


def _service_from_readback(payload: Mapping[str, Any]) -> str:
    receipt = payload.get("receipt")
    if not isinstance(receipt, Mapping):
        return ""
    return str(receipt.get("service") or "")


def _manifest_contains_receipt_id(
    descriptor: Mapping[str, Any] | None,
    receipt_id: str,
) -> bool:
    if not isinstance(descriptor, Mapping):
        return False
    return any(
        key == "receiptId" and value == receipt_id
        for key, value in _walk(descriptor.get("evidence"))
    )


def _bound_stage_readback(
    artifact_root: Path,
    descriptor: Mapping[str, Any],
    receipt_id: str,
) -> tuple[Path, str] | None:
    for _, value in _walk(descriptor.get("evidence")):
        if not isinstance(value, Mapping) or value.get("receiptId") != receipt_id:
            continue
        readback = value.get("readback")
        if (
            isinstance(readback, Mapping)
            and isinstance(readback.get("path"), str)
            and isinstance(readback.get("digest"), str)
        ):
            return artifact_root / readback["path"], str(readback["digest"])
    return None


def _validate_hosted_readbacks(
    evaluation: _Evaluation,
    *,
    rollout: LoadedReceipt | None,
    rollback: LoadedReceipt | None,
    artifact_root: Path | None,
    manifest: Mapping[str, Any] | None,
    now: datetime,
    max_age_seconds: int,
) -> Mapping[str, Any] | None:
    if rollout is None or rollback is None or artifact_root is None or manifest is None:
        return None
    rollout_service = _service_from_readback(rollout.payload)
    rollback_service = _service_from_readback(rollback.payload)
    if not rollout_service or rollback_service != rollout_service:
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            "prod.hosted",
            "hosted readbacks lack one consistent service identity",
        )
        return None
    try:
        rollout_receipt = lifecycle._validate_receipt_readback(
            rollout.payload,
            service=rollout_service,
        )
        ledger_receipt = lifecycle._validate_ledger_readback(
            rollback.payload,
            service=rollout_service,
        )
    except ValueError as exc:
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            "prod.hosted",
            f"canonical hosted ledger validation failed: {exc}",
        )
        return None
    receipt_id = str(rollout_receipt["receiptId"])
    if (
        ledger_receipt["receiptId"] != receipt_id
        or rollout_receipt.get("stage") != "100"
        or rollout_receipt.get("triggerStage") != "100"
        or rollout_receipt.get("decision") != "continue"
        or rollout_receipt.get("rollbackOutcome") != "not_triggered"
        or rollout_receipt.get("toCandidateDigest") != manifest["releaseCompositionId"]
        or rollout_receipt.get("lastGoodCandidateDigest") != manifest["releaseCompositionId"]
        or not _manifest_contains_receipt_id(manifest["rolloutReceipt"], receipt_id)
        or not _manifest_contains_receipt_id(manifest["rollbackReceipt"], receipt_id)
    ):
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            "prod.hosted",
            "hosted readbacks do not match the released manifest outcome",
        )
        return None
    bound = _bound_stage_readback(
        artifact_root,
        manifest["rolloutReceipt"],
        receipt_id,
    )
    if (
        bound is None
        or rollout.path != bound[0]
        or rollout.digest != bound[1]
    ):
        evaluation.block(
            "HOSTED_READBACK_INVALID",
            rollout.label,
            "rollout readback bytes are not the manifest-bound 100-stage readback",
        )
        return None
    for receipt, hosted in (
        (rollout, rollout_receipt),
        (rollback, ledger_receipt),
    ):
        timestamp_receipt = LoadedReceipt(
            receipt.label,
            receipt.path,
            dict(hosted),
            receipt.digest,
        )
        _timestamp(
            evaluation,
            timestamp_receipt,
            ("verifiedAt",),
            now=now,
            max_age_seconds=max_age_seconds,
        )
        evaluation.authority[receipt.label] = VerifiedAuthority(
            authority=lifecycle.HOSTED_AUTHORITY,
            subject_digest=receipt.digest,
            verification_digest=_canonical_digest(receipt.payload),
            claims=frozenset({"hosted_readback", receipt_id}),
        )
    return rollout_receipt


def verify_canonical_hosted_prod_soak(
    path: Path,
    rollout_receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> VerifiedAuthority:
    """Verify exact hosted soak bytes and derive all final soak claims."""

    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("hosted prod soak readback is invalid JSON") from error
    if not isinstance(payload, dict):
        raise TypeError("hosted prod soak readback must be an object")
    service = str(rollout_receipt.get("service") or "")
    receipt = lifecycle._validate_soak_readback(payload, service=service)
    receipt_id = str(receipt["receiptId"])

    # 原文件位于 lib/ 下用 parents[3]；本模块深一层，用 parents[4] 指向仓库根。
    root = Path(__file__).resolve().parents[4]
    sync_script = root / "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh"
    with tempfile.TemporaryDirectory(prefix="qwq-prod-soak-readback-") as temporary:
        remote_path = Path(temporary) / "soak-readback.json"
        result = subprocess.run(
            [
                "bash",
                str(sync_script),
                "--plane",
                "service",
                "--operation",
                "release-ledger-soak-receipt",
                "--service",
                service,
                "--receipt-id",
                receipt_id,
                "--output-path",
                str(remote_path),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not remote_path.is_file():
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or "canonical hosted prod soak readback failed"
            )
        remote_raw = remote_path.read_bytes()
    if remote_raw != raw:
        raise ValueError("supplied prod soak bytes differ from canonical remote readback")
    remote_payload = json.loads(remote_raw)
    remote_receipt = lifecycle._validate_soak_readback(
        remote_payload, service=service
    )
    if remote_receipt != receipt:
        raise ValueError("canonical remote prod soak receipt identity drifted")

    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise TypeError("released manifest source is missing")
    artifacts = manifest.get("environmentArtifacts")
    prod_artifact = artifacts.get("prod") if isinstance(artifacts, Mapping) else None
    configuration_packages = (
        prod_artifact.get("configurationPackages")
        if isinstance(prod_artifact, Mapping)
        else None
    )
    config_graph_digest = _canonical_digest(configuration_packages)
    expected_bindings = {
        "fullRolloutReceiptId": rollout_receipt.get("receiptId"),
        "releaseCompositionId": manifest.get("releaseCompositionId"),
        "rolloutArtifactDigest": rollout_receipt.get("artifactDigest"),
        "artifactDigest": manifest.get("artifactDigest"),
        "sourceGitSha": source.get("gitSha"),
        "sourceTreeDigest": source.get("treeDigest"),
        "rolloutConfigDigest": rollout_receipt.get("configDigest"),
        "configGraphDigest": config_graph_digest,
        "contractGraphDigest": manifest.get("contractGraphDigest"),
    }
    for field, expected in expected_bindings.items():
        if receipt.get(field) != expected:
            raise ValueError(f"hosted prod soak {field} binding drifted")

    policy_path = (
        root / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    )
    credential_policy_path = (
        root / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    if (
        receipt.get("soakPolicyDigest") != sha256_file(policy_path)
        or receipt.get("credentialPolicyDigest")
        != sha256_file(credential_policy_path)
    ):
        raise ValueError("hosted prod soak policy digest drifted")
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    credential_policy = yaml.safe_load(
        credential_policy_path.read_text(encoding="utf-8")
    )
    if not isinstance(policy, dict) or not isinstance(policy.get("readback"), dict):
        raise TypeError("canonical prod soak policy is invalid")
    readback_policy = policy["readback"]
    required_seconds = lifecycle._window_seconds(
        readback_policy.get("post_100_soak_window")
    )
    maximum_age = int(readback_policy.get("authority_max_age_seconds") or 0)
    minimum_samples = int(readback_policy.get("minimum_samples") or 0)
    if (
        receipt.get("requiredSoakSeconds") != required_seconds
        or receipt.get("soakDurationSeconds", 0) < required_seconds
        or maximum_age <= 0
        or minimum_samples <= 0
    ):
        raise ValueError("hosted prod soak duration policy is not satisfied")

    started_at = datetime.fromisoformat(
        str(receipt["soakStartedAt"]).replace("Z", "+00:00")
    )
    ended_at = datetime.fromisoformat(
        str(receipt["soakEndedAt"]).replace("Z", "+00:00")
    )
    now = datetime.now(timezone.utc)
    age = (now - ended_at).total_seconds()
    if age < -MAX_FUTURE_SKEW_SECONDS or age > maximum_age:
        raise ValueError("hosted prod soak receipt is stale")
    for name in ("slo", "alerts", "health"):
        observed_at = datetime.fromisoformat(
            str(receipt[name]["observedAt"]).replace("Z", "+00:00")
        )
        if observed_at < started_at or observed_at > ended_at:
            raise ValueError(f"hosted prod soak {name} observation is out of window")

    slo = receipt["slo"]
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, Mapping):
        raise TypeError("canonical prod soak thresholds are invalid")
    threshold_bindings = {
        "errorRate": "error_rate",
        "p95Ms": "p95_ms",
        "redisErrorRate": "redis_error_rate",
    }
    if (
        slo.get("minimumSamples") != minimum_samples
        or slo.get("sampleCount", 0) < minimum_samples
        or slo.get("windowSeconds") != required_seconds
    ):
        raise ValueError("hosted prod soak SLO sample policy is not satisfied")
    for field, policy_field in threshold_bindings.items():
        policy_threshold = thresholds.get(policy_field)
        if not isinstance(policy_threshold, Mapping) or not isinstance(
            policy_threshold.get("warn"), (int, float)
        ):
            raise TypeError(f"canonical prod soak {policy_field} policy is invalid")
        if float(slo["values"][field]) >= float(policy_threshold["warn"]):
            raise ValueError(f"hosted prod soak SLO breached {policy_field}")

    if not isinstance(credential_policy, dict):
        raise TypeError("canonical prod credential policy is invalid")
    expected_credentials: set[tuple[str, str]] = set()
    for plane in credential_policy.get("planes") or []:
        if (
            not isinstance(plane, dict)
            or plane.get("access") != "read-write"
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
        expected_credentials.add(
            (str(plane.get("plane") or ""), str(plane.get("account") or ""))
        )
    actual_credentials = {
        (str(item["plane"]), str(item["account"]))
        for item in receipt["credentials"]
    }
    if actual_credentials != expected_credentials:
        raise ValueError("hosted prod soak credentials do not cover canonical planes")
    for credential in receipt["credentials"]:
        expires_at = datetime.fromisoformat(
            str(credential["expiresAt"]).replace("Z", "+00:00")
        )
        verified_at = datetime.fromisoformat(
            str(credential["verifiedAt"]).replace("Z", "+00:00")
        )
        if expires_at <= now or verified_at < started_at or verified_at > ended_at:
            raise ValueError("hosted prod credential is expired or out of soak window")

    approval = receipt["approval"]
    if (
        approval.get("kind") != "github-reviewed-mainline"
        or approval.get("sourceGitSha") != source.get("gitSha")
        or approval.get("artifactDigest") != manifest.get("artifactDigest")
        or int(approval.get("distinctPrincipals") or 0) < 2
        or not approval.get("approvers")
    ):
        raise ValueError("hosted prod approval is not canonical or candidate-bound")
    return VerifiedAuthority(
        authority=lifecycle.HOSTED_AUTHORITY,
        subject_digest=_sha256(raw),
        verification_digest=_canonical_digest(
            {
                "receiptId": receipt_id,
                "remoteBytesDigest": _sha256(remote_raw),
                "bindings": expected_bindings,
                "soakStartedAt": receipt["soakStartedAt"],
                "soakEndedAt": receipt["soakEndedAt"],
            }
        ),
        claims=REQUIRED_SOAK_CLAIMS,
    )


def _validate_soak_authority(
    evaluation: _Evaluation,
    *,
    soak: LoadedReceipt | None,
    rollout_receipt: Mapping[str, Any] | None,
    manifest: Mapping[str, Any] | None,
    verifier: SoakAuthorityVerifier,
) -> None:
    if soak is None or rollout_receipt is None or manifest is None:
        return
    try:
        verified = verifier(soak.path, rollout_receipt, manifest)
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            soak.label,
            f"hosted soak authority verification failed: {exc}",
        )
        return
    if (
        verified.authority != lifecycle.HOSTED_AUTHORITY
        or verified.subject_digest != soak.digest
        or DIGEST_PATTERN.fullmatch(verified.verification_digest) is None
        or not REQUIRED_SOAK_CLAIMS.issubset(verified.claims)
    ):
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            soak.label,
            "soak verifier lacks exact bytes, freshness, credentials, approval, or soak claims",
        )
        return
    evaluation.authority[soak.label] = verified

"""pilot 内容发布身份与内容生命周期 / Green Matrix 校验（自原单文件逐字搬移）。"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_release_attestations,
)
from quwoquan_ops.ci.release_evidence_reader import DIGEST_PATTERN

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    LoadedReceipt,
    _Evaluation,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (
    _canonical_digest,
    _schema,
    _timestamp,
)


def _pilot_identity(
    evaluation: _Evaluation,
    release: LoadedReceipt | None,
    rollback: LoadedReceipt | None,
    *,
    now: datetime,
) -> dict[str, str] | None:
    if release is None or rollback is None:
        return None
    if not _schema(evaluation, release, "quwoquan_data.release_attestation"):
        return None
    if not _schema(evaluation, rollback, "quwoquan_data.release_attestation"):
        return None
    release_id_raw = str(release.payload.get("releaseId") or "").strip()
    rollback_id_raw = str(rollback.payload.get("releaseId") or "").strip()
    release_digest_raw = str(release.payload.get("payloadSha256") or "").strip()
    rollback_digest_raw = str(rollback.payload.get("payloadSha256") or "").strip()
    identical_identity = False
    if release_id_raw and release_id_raw == rollback_id_raw:
        identical_identity = True
        evaluation.block(
            "IDENTITY_MISMATCH",
            "pilot",
            "candidate and rollback content releases must use distinct releaseId values",
        )
    if release_digest_raw and release_digest_raw == rollback_digest_raw:
        identical_identity = True
        evaluation.block(
            "DIGEST_MISMATCH",
            "pilot",
            "candidate and rollback content releases must use distinct release digests",
        )
    if identical_identity:
        return None
    try:
        bindings = validate_release_attestations(str(release.path), str(rollback.path))
    except ValueError as exc:
        evaluation.block("SCHEMA_MISMATCH", "pilot", str(exc))
        return None
    candidate = bindings["candidate"]
    previous = bindings["rollback"]
    release_id = candidate["releaseId"]
    if release_id != "pilot-003" and not release_id.endswith("--pilot-003"):
        evaluation.block(
            "IDENTITY_MISMATCH",
            release.label,
            "candidate content release must be pilot-003",
        )
    if (
        release.payload.get("releaseClass") != "commercial"
        or release.payload.get("productLifecycleState") != "commercial"
        or release.payload.get("containsUnverifiedAssets") is not False
        or release.payload.get("authorizationRequiredAssetIds") != []
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            release.label,
            "pilot-003 is not a commercially admissible release attestation",
        )
    if release_id == previous["releaseId"] or candidate["releaseDigest"] == previous["releaseDigest"]:
        evaluation.block(
            "DIGEST_MISMATCH",
            "pilot",
            "candidate and rollback content releases must be distinct",
        )
    for receipt in (release, rollback):
        _timestamp(
            evaluation,
            receipt,
            ("recordedAt",),
            now=now,
            max_age_seconds=None,
        )
    return {
        "releaseId": release_id,
        "releaseDigest": candidate["releaseDigest"],
        "rollbackReleaseId": previous["releaseId"],
        "rollbackDigest": previous["releaseDigest"],
    }


def _verify_checksum(evaluation: _Evaluation, receipt: LoadedReceipt) -> None:
    unsigned = dict(receipt.payload)
    declared = unsigned.pop("verificationChecksum", None)
    if declared != _canonical_digest(unsigned):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "verificationChecksum does not bind the receipt payload",
        )


def _validate_content_lifecycle(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    environment: str,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(
        evaluation,
        receipt,
        "quwoquan_data.environment_release_lifecycle_exit",
    ):
        return
    payload = receipt.payload
    if payload.get("passed") is not True or payload.get("sourceOwner") != "qwq_data":
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "content lifecycle Exit receipt is not passed",
        )
    if payload.get("environment") != environment:
        evaluation.block(
            "IDENTITY_MISMATCH",
            receipt.label,
            f"content lifecycle environment must be {environment}",
        )
    _verify_checksum(evaluation, receipt)
    if pilot is not None:
        expected = {
            "originalReleaseId": pilot["releaseId"],
            "originalManifestDigest": pilot["releaseDigest"],
            "replayManifestDigest": pilot["releaseDigest"],
            "rollbackToReleaseId": pilot["rollbackReleaseId"],
            "rollbackToManifestDigest": pilot["rollbackDigest"],
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                evaluation.block(
                    "DIGEST_MISMATCH",
                    receipt.label,
                    f"{field} differs from pilot-003 release binding",
                )
    _timestamp(
        evaluation,
        receipt,
        ("recordedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )


def _validate_green_matrix(
    evaluation: _Evaluation,
    receipt: LoadedReceipt | None,
    *,
    pilot: Mapping[str, str] | None,
    now: datetime,
    max_age_seconds: int,
) -> None:
    if receipt is None:
        return
    if not _schema(evaluation, receipt, "quwoquan.test.case-result"):
        return
    payload = receipt.payload
    if not (
        payload.get("caseId") == "stackctl.local-env-gate.alpha-beta-gamma"
        and payload.get("status") == "passed"
        and payload.get("claim") == "ALPHA_BETA_GAMMA_LOCAL_GREEN"
        and payload.get("executionClass") == "live"
        and payload.get("targets") == ["alpha-local", "beta-local", "gamma-local"]
        and isinstance(payload.get("executed"), int)
        and payload["executed"] > 0
        and payload.get("skipped") == 0
        and payload.get("failureCategory") in {"", None}
        and DIGEST_PATTERN.fullmatch(str(payload.get("baselineId") or "")) is not None
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "local-env receipt is not the live Alpha/Beta/Gamma Green Matrix",
        )
    if pilot is not None and (
        payload.get("releaseId") != pilot["releaseId"]
        or payload.get("releaseDigest") != pilot["releaseDigest"]
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            receipt.label,
            "Green Matrix content release differs from pilot-003",
        )
    phases = payload.get("phases")
    if not isinstance(phases, list) or not phases or any(
        not isinstance(item, dict) or item.get("status") != "passed" for item in phases
    ):
        evaluation.block(
            "STATUS_NOT_PASSED",
            receipt.label,
            "Green Matrix contains a missing or non-passed phase",
        )
    _timestamp(
        evaluation,
        receipt,
        ("generatedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )

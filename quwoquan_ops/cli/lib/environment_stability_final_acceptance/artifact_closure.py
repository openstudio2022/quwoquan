"""ReleaseEvidenceManifest artifact 闭包与 manifest 绑定输入校验（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    canonical_release_composition_id,
    canonical_manifest_digest,
    sha256_file,
    validate_manifest,
)

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    ArtifactClosureVerifier,
    ENVIRONMENTS,
    LoadedReceipt,
    ProviderReadinessVerifier,
    _Evaluation,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.provider_readiness import (
    _provider_layers,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (
    _timestamp,
    _walk,
)


def _artifact_closure(
    evaluation: _Evaluation,
    *,
    artifact_root: Path | None,
    manifest_receipt: LoadedReceipt | None,
    verifier: ArtifactClosureVerifier,
    provider_verifier: ProviderReadinessVerifier,
    now: datetime,
    max_age_seconds: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if artifact_root is None or manifest_receipt is None:
        return None, None
    if manifest_receipt.path != artifact_root / "manifest.json":
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            "candidate manifest must be artifact_root/manifest.json",
        )
        return None, None
    try:
        manifest = validate_manifest(
            manifest_receipt.payload,
            allowed_statuses={"released"},
        )
        verifier(artifact_root, manifest)
    except (OSError, RuntimeError, ValueError) as exc:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            f"ReleaseEvidenceManifest artifact closure is invalid: {exc}",
        )
        return None, None
    if (
        manifest.get("releaseCompositionId") != canonical_release_composition_id(manifest)
        or manifest.get("artifactDigest") != canonical_manifest_digest(manifest)
    ):
        evaluation.block(
            "DIGEST_MISMATCH",
            "candidate",
            "manifest canonical candidate or artifact digest drifted",
        )
        return None, None
    if set(manifest["environmentReceipts"]) != {"alpha", "beta", "gamma", "prod"}:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            "released artifact lacks the four canonical environment receipts",
        )
    if manifest.get("rolloutReceipt") is None or manifest.get("rollbackReceipt") is None:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "candidate",
            "released artifact lacks rollout or rollback receipt closure",
        )
    _timestamp(
        evaluation,
        manifest_receipt,
        ("generatedAt",),
        now=now,
        max_age_seconds=max_age_seconds,
    )
    _provider_layers(
        evaluation,
        artifact_root=artifact_root,
        manifest=manifest,
        now=now,
        max_age_seconds=max_age_seconds,
        verifier=provider_verifier,
    )
    closure = {
        "root": artifact_root.as_posix(),
        "manifest": {
            "path": manifest_receipt.path.as_posix(),
            "digest": manifest_receipt.digest,
        },
        "releaseCompositionId": manifest["releaseCompositionId"],
        "artifactDigest": manifest["artifactDigest"],
        "providerEvidence": _bound_descriptor(artifact_root, manifest["providerEvidence"]),
        "testEvidence": _bound_descriptor(artifact_root, manifest["testEvidence"]),
        "environmentReceipts": {
            environment: _bound_descriptor(artifact_root, descriptor)
            for environment, descriptor in sorted(
                manifest["environmentReceipts"].items()
            )
        },
        "rolloutReceipt": _bound_descriptor(artifact_root, manifest["rolloutReceipt"]),
        "rollbackReceipt": _bound_descriptor(
            artifact_root,
            manifest["rollbackReceipt"],
        ),
    }
    return manifest, closure


def _bound_descriptor(
    artifact_root: Path,
    descriptor: Mapping[str, Any],
) -> dict[str, str]:
    return {
        "path": (artifact_root / str(descriptor["path"])).as_posix(),
        "digest": str(descriptor["digest"]),
    }


def _artifact_binding_matches(
    *,
    artifact_root: Path,
    receipt: LoadedReceipt,
    evidence: Any,
) -> bool:
    try:
        receipt.path.relative_to(artifact_root)
    except ValueError:
        return False
    for _, value in _walk(evidence):
        if not isinstance(value, Mapping):
            continue
        relative = value.get("path")
        digest = value.get("digest")
        if not isinstance(relative, str) or not isinstance(digest, str):
            continue
        path = artifact_root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(artifact_root)
        except (OSError, ValueError):
            continue
        if (
            not path.is_symlink()
            and resolved == receipt.path
            and digest == receipt.digest
            and sha256_file(resolved) == digest
        ):
            return True
    return False


def _validate_manifest_bound_acceptance_inputs(
    evaluation: _Evaluation,
    *,
    artifact_root: Path | None,
    manifest: Mapping[str, Any] | None,
    loaded: Mapping[str, LoadedReceipt | None],
) -> None:
    if artifact_root is None or manifest is None:
        return
    environment_receipts = manifest["environmentReceipts"]
    for environment in ENVIRONMENTS:
        receipt = loaded[f"content.{environment}"]
        descriptor = environment_receipts.get(environment)
        if receipt is not None and (
            not isinstance(descriptor, Mapping)
            or not _artifact_binding_matches(
                artifact_root=artifact_root,
                receipt=receipt,
                evidence=descriptor.get("evidence"),
            )
        ):
            evaluation.block(
                "UNVERIFIABLE_AUTHORITY",
                receipt.label,
                "content lifecycle bytes are not bound by the matching environment receipt",
            )
    for label in ("pilot.release", "pilot.rollback"):
        receipt = loaded[label]
        if receipt is None:
            continue
        bound_environments = {
            environment
            for environment in ENVIRONMENTS
            if _artifact_binding_matches(
                artifact_root=artifact_root,
                receipt=receipt,
                evidence=environment_receipts[environment].get("evidence"),
            )
        }
        if bound_environments != set(ENVIRONMENTS):
            evaluation.block(
                "UNVERIFIABLE_AUTHORITY",
                label,
                "pilot attestation bytes are not bound by all preprod environment receipts",
            )
    matrix = loaded["local_env.green_matrix"]
    if matrix is not None:
        try:
            test_path = artifact_root / str(manifest["testEvidence"]["path"])
            test_payload = json.loads(test_path.read_text(encoding="utf-8"))
        except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
            evaluation.block(
                "ARTIFACT_CLOSURE_INVALID",
                matrix.label,
                f"manifest test evidence is unreadable: {exc}",
            )
        else:
            if not _artifact_binding_matches(
                artifact_root=artifact_root,
                receipt=matrix,
                evidence=test_payload,
            ):
                evaluation.block(
                    "UNVERIFIABLE_AUTHORITY",
                    matrix.label,
                    "Green Matrix bytes are not bound by manifest test evidence",
                )

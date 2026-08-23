"""finalize CLI 参数解析、收据落盘与生命周期推进主流程（逐字搬移自入口）。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    ENVIRONMENTS,
    PRE_PROD_ENVIRONMENTS,
    RECEIPT_SOURCE_FIELDS,
    TEST_LAYERS,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.canonical_digests import (
    load_json,
    seal_manifest,
    sha256_file,
    utc_now,
    write_summary,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.evidence_files import (
    load_image_descriptors,
    load_release_evidence,
    validate_descriptor,
    validate_manifest_files,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact_lib.manifest_validation import (
    _derive_status,
    _expected_gaps,
    _validate_receipt_descriptor,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--image-descriptors-dir", type=Path)
    parser.add_argument("--artifact-descriptors-dir", type=Path)
    parser.add_argument("--environment-receipts-dir", type=Path)
    parser.add_argument("--rollout-receipt", type=Path)
    parser.add_argument("--rollback-receipt", type=Path)
    return parser.parse_args()


def _receipt_descriptor(
    *,
    artifact_dir: Path,
    source_path: Path,
    manifest: dict[str, Any],
    kind: str,
    expected_environment: str,
) -> dict[str, Any]:
    payload = load_json(source_path)
    if set(payload) != RECEIPT_SOURCE_FIELDS:
        raise ValueError(f"{kind} receipt source fields are not canonical")
    suffix = (
        expected_environment
        if kind == "environment"
        else str(payload.get("status") or "missing")
    )
    relative = Path("evidence/receipts") / kind / f"{suffix}.json"
    descriptor = {
        **payload,
        "path": relative.as_posix(),
        "digest": sha256_file(source_path),
    }
    _validate_receipt_descriptor(
        descriptor,
        manifest=manifest,
        kind=kind,
        expected_environment=expected_environment,
    )
    destination = artifact_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != source_path.read_bytes():
            raise ValueError(f"immutable {kind} receipt already differs: {suffix}")
    else:
        shutil.copyfile(source_path, destination)
    return descriptor


def _load_environment_receipts(
    *,
    artifact_dir: Path,
    receipts_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(receipts_dir.glob("*.json")):
        payload = load_json(path)
        environment = str(payload.get("environment") or "")
        if environment not in ENVIRONMENTS:
            raise ValueError(f"environment receipt has invalid environment: {environment!r}")
        if environment in result:
            raise ValueError(f"duplicate environment receipt: {environment}")
        result[environment] = _receipt_descriptor(
            artifact_dir=artifact_dir,
            source_path=path,
            manifest=manifest,
            kind="environment",
            expected_environment=environment,
        )
    if not result:
        raise ValueError("environment receipt directory contains no canonical receipts")
    return result


def _apply_candidate_evidence(
    manifest: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> None:
    manifest["applicationPackages"] = evidence["applicationPackages"]
    manifest["opsPortal"] = evidence["opsPortal"]
    manifest["contractGraphDigest"] = evidence["contractGraph"]["digest"]
    provider = evidence["providerEvidence"]
    provider_payload = provider["payload"]
    manifest["providerEvidence"] = {
        "path": provider["path"],
        "digest": provider["digest"],
        "status": "passed",
        "evidenceCount": int(provider_payload.get("evidenceCount") or 0),
    }
    test = evidence["testEvidence"]
    test_evidence_files = test["payload"].get("evidence")
    if not isinstance(test_evidence_files, dict) or not test_evidence_files:
        raise ValueError("testEvidence must bind replayable raw evidence files")
    manifest["testEvidence"] = {
        "path": test["path"],
        "digest": test["digest"],
        "status": "passed",
        "layers": {
            layer: {
                "status": test["payload"]["layers"][layer]["status"],
                "artifactDigest": test["payload"]["layers"][layer][
                    "artifactDigest"
                ],
            }
            for layer in TEST_LAYERS
        },
        "evidence": test_evidence_files,
    }


def finalize(
    artifact_dir: Path,
    descriptors_dir: Path | None,
    artifact_descriptors_dir: Path | None = None,
    environment_receipts_dir: Path | None = None,
    rollout_receipt_path: Path | None = None,
    rollback_receipt_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = artifact_dir / "manifest.json"
    manifest = load_json(manifest_path)
    validate_manifest_files(artifact_dir, manifest)
    original_status = manifest["status"]

    operations = sum(
        value is not None
        for value in (
            descriptors_dir,
            artifact_descriptors_dir,
            environment_receipts_dir,
            rollout_receipt_path,
            rollback_receipt_path,
        )
    )
    if operations == 0:
        raise ValueError("one concrete evidence input is required")

    if descriptors_dir is not None:
        if original_status != "build-input" or operations != 1:
            raise ValueError("image evidence is only accepted from build-input")
        descriptors = load_image_descriptors(descriptors_dir)
        required = manifest["requiredEvidence"]["environmentArtifacts"]
        trust_domain_digests: dict[tuple[str, str], str] = {}
        for environment in ENVIRONMENTS:
            if set(descriptors[environment]) != set(required[environment]):
                missing = sorted(
                    set(required[environment]) - set(descriptors[environment])
                )
                extra = sorted(
                    set(descriptors[environment]) - set(required[environment])
                )
                raise ValueError(
                    "image descriptor set mismatch: "
                    f"environment={environment}, missing={missing}, extra={extra}"
                )
            images: dict[str, dict[str, Any]] = {}
            for owner in required[environment]:
                current = manifest["environmentArtifacts"][environment]["images"][owner]
                descriptor = validate_descriptor(
                    environment,
                    owner,
                    descriptors[environment][owner],
                    expected_repository=str(current["repository"]),
                    expected_transport_ref=str(current["transportRef"]),
                )
                digest = str(descriptor["digest"])
                trust_domain = "prod" if environment == "prod" else "nonprod"
                previous = trust_domain_digests.setdefault(
                    (trust_domain, str(owner)), digest
                )
                if previous != digest:
                    raise ValueError(
                        "nonprod image descriptors must share one digest per owner: "
                        f"{owner} diverges at {environment}"
                    )
                images[owner] = descriptor
            manifest["environmentArtifacts"][environment]["images"] = images
        for owner in required["prod"]:
            if trust_domain_digests[("prod", owner)] == trust_domain_digests.get(
                ("nonprod", owner)
            ):
                raise ValueError(
                    "prod image descriptor must fork from the nonprod trust domain: "
                    f"{owner}"
                )
    elif artifact_descriptors_dir is not None:
        if original_status != "component-ready" or operations != 1:
            raise ValueError("candidate material is only accepted from component-ready")
        _apply_candidate_evidence(
            manifest,
            load_release_evidence(artifact_dir, artifact_descriptors_dir),
        )
    else:
        if original_status not in {"candidate-ready", "deployable"}:
            raise ValueError("release receipts require a sealed candidate")
        if original_status == "deployable":
            if set(manifest["environmentReceipts"]) != set(PRE_PROD_ENVIRONMENTS):
                raise ValueError("deployable input is missing pre-prod receipts")
            if not isinstance(manifest["rollbackReceipt"], dict) or manifest[
                "rollbackReceipt"
            ].get("status") != "ready":
                raise ValueError("deployable input is missing rollback readiness")
        if environment_receipts_dir is not None:
            incoming_environments = {
                str(load_json(path).get("environment") or "")
                for path in sorted(environment_receipts_dir.glob("*.json"))
            }
            if "prod" in incoming_environments and original_status != "deployable":
                raise ValueError("prod receipt requires a previously deployable snapshot")
            incoming = _load_environment_receipts(
                artifact_dir=artifact_dir,
                receipts_dir=environment_receipts_dir,
                manifest=manifest,
            )
            for environment, descriptor in incoming.items():
                existing = manifest["environmentReceipts"].get(environment)
                if existing is not None and existing != descriptor:
                    raise ValueError(
                        f"immutable environment receipt already differs: {environment}"
                    )
                manifest["environmentReceipts"][environment] = descriptor
        if rollout_receipt_path is not None:
            if original_status != "deployable":
                raise ValueError("rollout receipt requires a previously deployable snapshot")
            manifest["rolloutReceipt"] = _receipt_descriptor(
                artifact_dir=artifact_dir,
                source_path=rollout_receipt_path,
                manifest=manifest,
                kind="rollout",
                expected_environment="prod",
            )
        if rollback_receipt_path is not None:
            rollback_payload = load_json(rollback_receipt_path)
            rollback_status = rollback_payload.get("status")
            if rollback_status in {
                "not_triggered",
                "rolled_back",
                "rollback_failed",
            } and original_status != "deployable":
                raise ValueError(
                    "completed rollback receipt requires a previously deployable snapshot"
                )
            if rollback_status == "ready" and original_status != "candidate-ready":
                raise ValueError("rollback readiness requires a candidate-ready snapshot")
            manifest["rollbackReceipt"] = _receipt_descriptor(
                artifact_dir=artifact_dir,
                source_path=rollback_receipt_path,
                manifest=manifest,
                kind="rollback",
                expected_environment="prod",
            )

    manifest["generatedAt"] = utc_now()
    manifest = seal_manifest(manifest)
    status = _derive_status(manifest)
    manifest["status"] = status
    manifest["blockers"], manifest["missingEvidence"] = _expected_gaps(
        manifest, status
    )
    manifest = seal_manifest(manifest)
    validate_manifest_files(artifact_dir, manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_summary(artifact_dir / "summary.md", manifest)
    return manifest


def main() -> int:
    args = parse_args()
    try:
        manifest = finalize(
            args.artifact_dir.resolve(),
            (
                args.image_descriptors_dir.resolve()
                if args.image_descriptors_dir is not None
                else None
            ),
            (
                args.artifact_descriptors_dir.resolve()
                if args.artifact_descriptors_dir is not None
                else None
            ),
            (
                args.environment_receipts_dir.resolve()
                if args.environment_receipts_dir is not None
                else None
            ),
            args.rollout_receipt.resolve() if args.rollout_receipt is not None else None,
            (
                args.rollback_receipt.resolve()
                if args.rollback_receipt is not None
                else None
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}")
        return 1
    image_count = sum(
        len(artifact["images"])
        for artifact in manifest["environmentArtifacts"].values()
    )
    print(
        f"OK: {manifest['status']} release evidence "
        f"{manifest['artifactDigest']} includes {image_count} immutable images"
    )
    return 0

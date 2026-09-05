#!/usr/bin/env python3
"""Bind successful stackctl/device evidence to one canonical environment receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    DIGEST_PATTERN,
    ENVIRONMENTS,
    RELEASE_CLOSURE_PATHS,
    TEST_RELEASE_CLOSURE_LABELS,
    validate_manifest,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_release_attestations,
)


TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
PREPROD_RUNTIME_EVIDENCE = frozenset({"package", "up", "health", "verify"})
PREPROD_RELEASE_EVIDENCE = frozenset(
    {"pilot-release", "pilot-rollback", "content-lifecycle"}
)
_EVIDENCE_LABEL = re.compile(r"[a-z0-9][a-z0-9-]*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--environment", required=True, choices=ENVIRONMENTS)
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence binding NAME=JSON_PATH. Repeatable.",
    )
    parser.add_argument("--require-evidence", action="append", default=[])
    parser.add_argument(
        "--archive-prefix",
        required=True,
        help=(
            "ReleaseEvidenceManifest OCI 内保存原始证据的相对目录；"
            "receipt 用它保证 runner 输出删除后仍可重放"
        ),
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"environment evidence is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _parse_evidence(items: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in items:
        name, separator, path = item.partition("=")
        name = name.strip()
        if not separator or not name or not path.strip():
            raise ValueError(f"expected NAME=JSON_PATH, got {item!r}")
        if _EVIDENCE_LABEL.fullmatch(name) is None:
            raise ValueError(f"environment evidence label is unsafe: {name!r}")
        if name in result:
            raise ValueError(f"duplicate environment evidence: {name}")
        result[name] = Path(path).expanduser().resolve()
    return result


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} evidence must be a JSON object")
    return payload


def _passed(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status in {"ok", "passed", "success"}
    command = payload.get("command")
    if command == "health":
        checks = payload.get("checks")
        findings = payload.get("findings")
        return (
            isinstance(checks, list)
            and bool(checks)
            and all(isinstance(item, dict) and item.get("ok") is True for item in checks)
            and (findings is None or findings == [])
        )
    if command == "up":
        steps = payload.get("steps")
        return (
            isinstance(steps, list)
            and bool(steps)
            and all(
                isinstance(item, dict) and item.get("exitCode") == 0
                for item in steps
            )
        )
    if command == "deploy" and payload.get("target") == "prod-hosted":
        release_state = payload.get("releaseState")
        rollback = payload.get("rollback")
        return (
            payload.get("exitCode") == 0
            and payload.get("dryRun") is False
            and payload.get("rolloutDecision") == "continue"
            and bool(payload.get("releaseReceiptId"))
            and bool(payload.get("releaseReceiptRef"))
            and isinstance(release_state, dict)
            and bool(release_state)
            and payload.get("postDeployFailures") in (None, [])
            and isinstance(rollback, dict)
            and rollback.get("triggered") is False
        )
    return False


def _timestamp(payload: dict[str, Any], label: str) -> tuple[datetime, str]:
    value = payload.get("endedAt") or payload.get("verifiedAt") or payload.get(
        "generatedAt"
    ) or payload.get("recordedAt")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} evidence has no authoritative completion timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} completion timestamp is invalid") from error
    return parsed, value


def _validate_immutable_runtime(
    payload: dict[str, Any],
    *,
    manifest: dict[str, Any],
    environment: str,
) -> None:
    artifacts = manifest.get("environmentArtifacts")
    artifact = artifacts.get(environment) if isinstance(artifacts, dict) else None
    images = artifact.get("images") if isinstance(artifact, dict) else None
    if not isinstance(images, dict) or not images:
        raise ValueError(
            f"{environment} runtime requires its immutable environment artifact images"
        )
    expected: dict[str, dict[str, str]] = {}
    for service, descriptor in sorted(images.items()):
        if not isinstance(service, str) or not isinstance(descriptor, dict):
            raise ValueError(f"{environment} manifest image descriptor is invalid")
        ref = str(descriptor.get("ref") or "")
        digest = str(descriptor.get("digest") or "")
        if DIGEST_PATTERN.fullmatch(digest) is None or not ref.endswith("@" + digest):
            raise ValueError(f"{environment} manifest image is not exact: {service}")
        expected[service] = {"ref": ref, "digest": digest}

    runtime = payload.get("runtimeImages")
    if not isinstance(runtime, dict) or set(runtime) != set(expected):
        raise ValueError(f"{environment} up evidence runtime image set is incomplete")
    for service, expected_descriptor in expected.items():
        actual = runtime.get(service)
        if not isinstance(actual, dict) or any(
            actual.get(field) != value
            for field, value in expected_descriptor.items()
        ):
            raise ValueError(
                f"{environment} up evidence runtime image differs from candidate: {service}"
            )
    if (
        payload.get("formalRelease") is not True
        or payload.get("releaseInputClassification") != "commercial_inputs"
        or payload.get("runtimeMode") != "immutable-oci"
        or payload.get("runtimeCandidateDigest") != manifest.get("releaseCompositionId")
        or payload.get("environmentArtifactDigest")
        != artifact.get("environmentArtifactDigest")
        or payload.get("destructiveRepairPerformed") is not False
        or payload.get("destructiveActions") != []
    ):
        raise ValueError(
            f"{environment} up evidence is not an immutable candidate runtime with "
            "commercial release inputs and without destructive repair"
        )
    if payload.get("contractGraphDigest") != manifest.get("contractGraphDigest"):
        raise ValueError(
            f"{environment} up evidence ContractGraph differs from the manifest"
        )


def _canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_lifecycle_exit(
    payload: dict[str, Any],
    *,
    environment: str,
    candidate: dict[str, str],
    rollback: dict[str, str],
) -> None:
    if (
        payload.get("schema")
        != "quwoquan_data.environment_release_lifecycle_exit"
        or payload.get("passed") is not True
        or payload.get("sourceOwner") != "qwq_data"
    ):
        raise ValueError(f"{environment} content lifecycle Exit is not passed")
    if payload.get("environment") != environment:
        raise ValueError(f"{environment} content lifecycle environment mismatch")
    expected = {
        "originalReleaseId": candidate["releaseId"],
        "originalManifestDigest": candidate["releaseDigest"],
        "replayManifestDigest": candidate["releaseDigest"],
        "rollbackToReleaseId": rollback["releaseId"],
        "rollbackToManifestDigest": rollback["releaseDigest"],
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(
                f"{environment} content lifecycle {field} release binding mismatch"
            )
    unsigned = dict(payload)
    declared_checksum = unsigned.pop("verificationChecksum", None)
    if declared_checksum != _canonical_digest(unsigned):
        raise ValueError(f"{environment} content lifecycle checksum mismatch")


def validate_release_closure_sources(
    *,
    pilot_release_attestation: Path,
    pilot_rollback_attestation: Path,
    lifecycle_exits: dict[str, Path],
    green_matrix: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate the exact producer files before any receipt can reference them."""

    for label, path in {
        "pilot release": pilot_release_attestation,
        "pilot rollback": pilot_rollback_attestation,
        **{
            f"{environment} content lifecycle": path
            for environment, path in lifecycle_exits.items()
        },
        **({"Green Matrix": green_matrix} if green_matrix is not None else {}),
    }.items():
        if path is None or path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} evidence is not a regular file")
    bindings = validate_release_attestations(
        str(pilot_release_attestation),
        str(pilot_rollback_attestation),
    )
    candidate = bindings["candidate"]
    rollback = bindings["rollback"]
    if (
        candidate["releaseId"] == rollback["releaseId"]
        or candidate["releaseDigest"] == rollback["releaseDigest"]
    ):
        raise ValueError("pilot release and rollback identities must be distinct")

    payloads = {
        "pilot-release": _load_json(
            pilot_release_attestation, "pilot release attestation"
        ),
        "pilot-rollback": _load_json(
            pilot_rollback_attestation, "pilot rollback attestation"
        ),
    }
    if set(lifecycle_exits) - {"alpha", "beta", "gamma"}:
        raise ValueError("content lifecycle environment set is not canonical")
    for environment, path in sorted(lifecycle_exits.items()):
        payload = _load_json(path, f"{environment} content lifecycle")
        _validate_lifecycle_exit(
            payload,
            environment=environment,
            candidate=candidate,
            rollback=rollback,
        )
        payloads[f"content-lifecycle-{environment}"] = payload

    if green_matrix is not None:
        if set(lifecycle_exits) != {"alpha", "beta", "gamma"}:
            raise ValueError(
                "Green Matrix closure requires all three lifecycle Exit receipts"
            )
        matrix = _load_json(green_matrix, "Green Matrix")
        phases = matrix.get("phases")
        if not (
            matrix.get("schema") == "quwoquan.test.case-result"
            and matrix.get("caseId")
            == "stackctl.local-env-gate.alpha-beta-gamma"
            and matrix.get("status") == "passed"
            and matrix.get("claim") == "ALPHA_BETA_GAMMA_LOCAL_GREEN"
            and matrix.get("executionClass") == "live"
            and matrix.get("targets")
            == ["alpha-local", "beta-local", "gamma-local"]
            and isinstance(matrix.get("executed"), int)
            and matrix["executed"] > 0
            and matrix.get("skipped") == 0
            and matrix.get("failureCategory") in {"", None}
            and DIGEST_PATTERN.fullmatch(str(matrix.get("baselineId") or ""))
            is not None
            and matrix.get("releaseId") == candidate["releaseId"]
            and matrix.get("releaseDigest") == candidate["releaseDigest"]
            and isinstance(phases, list)
            and bool(phases)
            and all(
                isinstance(phase, dict) and phase.get("status") == "passed"
                for phase in phases
            )
        ):
            raise ValueError("Green Matrix is not the live pilot release result")
        environments = matrix.get("environments")
        expected_environments = {
            TARGETS[environment] for environment in ("alpha", "beta", "gamma")
        }
        if (
            not isinstance(environments, dict)
            or set(environments) != expected_environments
        ):
            raise ValueError("Green Matrix environment set is not canonical")
        for environment in ("alpha", "beta", "gamma"):
            target = TARGETS[environment]
            block = environments[target]
            release = block.get("release") if isinstance(block, dict) else None
            rollback_release = (
                block.get("rollbackRelease") if isinstance(block, dict) else None
            )
            if (
                not isinstance(block, dict)
                or block.get("environment") != environment
                or block.get("target") != target
                or not isinstance(release, dict)
                or release.get("releaseId") != candidate["releaseId"]
                or release.get("releaseDigest") != candidate["releaseDigest"]
                or not isinstance(rollback_release, dict)
                or rollback_release.get("releaseId") != rollback["releaseId"]
                or rollback_release.get("releaseDigest")
                != rollback["releaseDigest"]
            ):
                raise ValueError(
                    f"Green Matrix {environment} release binding mismatch"
                )
        payloads["green-matrix"] = matrix
    return payloads


def _safe_relative_path(value: str, label: str) -> Path:
    relative = Path(value)
    if (
        not value
        or relative.is_absolute()
        or "." in relative.parts
        or ".." in relative.parts
    ):
        raise ValueError(f"{label} artifact-relative path is unsafe")
    return relative


def archive_exact_files(
    *,
    archive_root: Path,
    files: dict[str, tuple[Path, str]],
) -> dict[str, dict[str, str]]:
    """Copy exact bytes to fixed artifact-relative paths without overwrite drift."""

    if archive_root.is_symlink():
        raise ValueError("evidence archive root cannot be a symbolic link")
    archive_root.mkdir(parents=True, exist_ok=True)
    resolved_root = archive_root.resolve(strict=True)
    descriptors: dict[str, dict[str, str]] = {}
    destinations: set[Path] = set()
    for label, (source_value, relative_value) in sorted(files.items()):
        source = source_value.expanduser()
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"{label} evidence is not a regular file")
        source = source.resolve(strict=True)
        relative = _safe_relative_path(relative_value, label)
        destination = resolved_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = destination.parent.resolve(strict=True)
        try:
            resolved_parent.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError(f"{label} evidence archive escapes its root") from error
        if destination in destinations:
            raise ValueError(f"duplicate evidence archive destination: {relative}")
        destinations.add(destination)
        if destination.is_symlink():
            raise ValueError(f"{label} evidence archive is a symbolic link")
        if source != destination:
            if destination.exists():
                if destination.read_bytes() != source.read_bytes():
                    raise ValueError(
                        f"immutable evidence archive already differs: {relative}"
                    )
            else:
                shutil.copyfile(source, destination)
        digest = _sha256(destination)
        source_digest = _sha256(source)
        if digest != source_digest:
            raise ValueError(f"{label} evidence archive digest mismatch")
        descriptors[label] = {"path": relative.as_posix(), "digest": digest}
    return descriptors


def archive_environment_evidence(
    *,
    artifact_root: Path,
    staging_root: Path,
    environment: str,
    evidence_paths: dict[str, Path],
    descriptors: dict[str, dict[str, str]],
) -> None:
    """Stage receipt-owned bytes and verify shared release bytes in the artifact."""

    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise ValueError("ReleaseEvidenceManifest artifact root is unsafe")
    resolved_artifact_root = artifact_root.resolve(strict=True)
    environment_base = Path("evidence/raw/environments") / environment
    staged: dict[str, tuple[Path, str]] = {}
    for label, source in sorted(evidence_paths.items()):
        descriptor = descriptors.get(label)
        if not isinstance(descriptor, dict):
            raise ValueError(f"{label} evidence descriptor is missing")
        relative = _safe_relative_path(str(descriptor.get("path") or ""), label)
        if label in PREPROD_RELEASE_EVIDENCE:
            expected = (resolved_artifact_root / relative).resolve(strict=True)
            try:
                expected.relative_to(resolved_artifact_root)
            except ValueError as error:
                raise ValueError(
                    f"{label} release evidence escapes the artifact root"
                ) from error
            if (
                source.is_symlink()
                or source.resolve(strict=True) != expected
                or _sha256(expected) != descriptor["digest"]
            ):
                raise ValueError(
                    f"{label} release evidence is not the manifest-bound exact file"
                )
            continue
        try:
            local_relative = relative.relative_to(environment_base)
        except ValueError as error:
            raise ValueError(
                f"{label} evidence is outside the environment archive"
            ) from error
        staged[label] = (source, local_relative.as_posix())
    staged_descriptors = archive_exact_files(archive_root=staging_root, files=staged)
    for label, descriptor in staged_descriptors.items():
        expected = descriptors[label]
        if descriptor["digest"] != expected["digest"]:
            raise ValueError(f"{label} staged evidence digest mismatch")


def render(
    *,
    manifest: dict[str, Any],
    environment: str,
    evidence: dict[str, tuple[Path, dict[str, Any]]],
    required_evidence: list[str],
    archive_prefix: str,
) -> dict[str, Any]:
    validate_manifest(manifest, allowed_statuses={"qualified", "main-admitted"})
    candidate = str(manifest.get("releaseCompositionId") or "")
    if DIGEST_PATTERN.fullmatch(candidate) is None:
        raise ValueError("environment receipt requires a sealed releaseCompositionId")
    if environment not in TARGETS:
        raise ValueError(f"unsupported environment: {environment}")
    canonical_required = set(required_evidence)
    if environment in {"alpha", "beta", "gamma"}:
        canonical_required.update(PREPROD_RUNTIME_EVIDENCE)
        canonical_required.update(PREPROD_RELEASE_EVIDENCE)
    if environment == "beta":
        canonical_required.add("devices")
    missing = sorted(canonical_required - set(evidence))
    if missing:
        raise ValueError(f"environment evidence is missing: {missing}")
    if not evidence:
        raise ValueError("environment receipt has no evidence")
    if "package" not in evidence:
        raise ValueError("environment receipt requires candidate-bound package evidence")

    normalized_prefix = archive_prefix.strip().strip("/")
    expected_prefix = f"evidence/raw/environments/{environment}/raw"
    if (
        normalized_prefix != expected_prefix
        or ".." in Path(normalized_prefix).parts
    ):
        raise ValueError("environment evidence archive prefix is not canonical")
    if environment in {"alpha", "beta", "gamma"}:
        validate_release_closure_sources(
            pilot_release_attestation=evidence["pilot-release"][0],
            pilot_rollback_attestation=evidence["pilot-rollback"][0],
            lifecycle_exits={environment: evidence["content-lifecycle"][0]},
        )
    evidence_files: dict[str, dict[str, str]] = {}
    timestamps: list[tuple[datetime, str]] = []
    expected_target = TARGETS[environment]
    for label, (path, payload) in sorted(evidence.items()):
        if payload.get("schema") == "candidate-bound-environment-evidence":
            raise ValueError(
                f"{label} evidence is a rewrapped compatibility envelope"
            )
        if label not in PREPROD_RELEASE_EVIDENCE and not _passed(payload):
            raise ValueError(f"{label} evidence is not passed")
        declared_environment = payload.get("environment", payload.get("env"))
        if declared_environment not in {None, environment}:
            raise ValueError(f"{label} evidence environment mismatch")
        declared_target = payload.get("target")
        if declared_target not in {None, expected_target}:
            raise ValueError(f"{label} evidence target mismatch")
        require_direct_binding = label in {"package", "devices"}
        declared_candidate = payload.get("releaseCompositionId")
        if require_direct_binding and declared_candidate is None:
            raise ValueError(f"{label} evidence has no direct releaseCompositionId binding")
        if declared_candidate is not None and declared_candidate != candidate:
            raise ValueError(f"{label} evidence releaseCompositionId mismatch")
        declared_artifact = payload.get("artifactDigest")
        if label == "package" and declared_artifact is None:
            raise ValueError("package evidence has no direct artifactDigest binding")
        if label == "package":
            if "formalRelease" in payload:
                raise ValueError("package evidence must not claim formalRelease")
            if payload.get("releaseInputClassification") is None:
                raise ValueError(
                    "package evidence release input classification is missing"
                )
            if payload.get("releaseInputClassification") != "commercial_inputs":
                raise ValueError(
                    "package evidence requires commercial release inputs"
                )
            if payload.get("contractGraphDigest") != manifest.get(
                "contractGraphDigest"
            ):
                raise ValueError(
                    "package evidence ContractGraph differs from the manifest"
                )
        if (
            declared_artifact is not None
            and declared_artifact != manifest["artifactDigest"]
        ):
            raise ValueError(f"{label} evidence artifactDigest mismatch")
        declared_source_sha = payload.get("sourceGitSha")
        if require_direct_binding and declared_source_sha is None:
            raise ValueError(f"{label} evidence has no direct source Git SHA binding")
        if (
            declared_source_sha is not None
            and declared_source_sha != manifest["source"]["gitSha"]
        ):
            raise ValueError(f"{label} evidence source Git SHA mismatch")
        declared_tree = payload.get("sourceTreeDigest")
        if require_direct_binding and declared_tree is None:
            raise ValueError(f"{label} evidence has no direct source tree binding")
        if (
            declared_tree is not None
            and declared_tree != manifest["source"]["treeDigest"]
        ):
            raise ValueError(f"{label} evidence source tree mismatch")
        if label == "devices":
            platforms = payload.get("platforms")
            if (
                payload.get("schema") != "release-device-matrix-evidence"
                or not isinstance(platforms, dict)
                or set(platforms) != {"android", "ios"}
                or not all(isinstance(items, dict) and items for items in platforms.values())
            ):
                raise ValueError(
                    "devices evidence must contain non-empty Android and iOS matrices"
                )
            for platform, items in platforms.items():
                if not all(
                    isinstance(path_name, str)
                    and path_name
                    and DIGEST_PATTERN.fullmatch(str(item_digest or "")) is not None
                    for path_name, item_digest in items.items()
                ):
                    raise ValueError(
                        f"devices evidence {platform} matrix digests are invalid"
                    )
        if label == "up" and environment in {"alpha", "beta", "gamma"}:
            _validate_immutable_runtime(
                payload,
                manifest=manifest,
                environment=environment,
            )
        relative_path = (
            RELEASE_CLOSURE_PATHS[
                f"content-lifecycle-{environment}"
                if label == "content-lifecycle"
                else label
            ]
            if label in PREPROD_RELEASE_EVIDENCE
            else f"{normalized_prefix}/{label}.json"
        )
        if any(
            item["path"] == relative_path for item in evidence_files.values()
        ):
            raise ValueError(f"{label} evidence archive path is duplicated")
        evidence_files[label] = {
            "path": relative_path,
            "digest": _sha256(path),
        }
        timestamps.append(_timestamp(payload, label))

    source = manifest["source"]
    evidence_projection = {
        "releaseCompositionId": candidate,
        "environment": environment,
        "sourceGitSha": source["gitSha"],
        "sourceTreeDigest": source["treeDigest"],
        "files": evidence_files,
    }
    encoded = json.dumps(
        evidence_projection,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "schema": "release-environment-receipt",
        "environment": environment,
        "status": "passed",
        "releaseCompositionId": candidate,
        "sourceGitSha": source["gitSha"],
        "sourceTreeDigest": source["treeDigest"],
        "evidenceDigest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "evidence": evidence_projection,
        "verifiedAt": max(timestamps, key=lambda item: item[0])[1],
    }


def main() -> int:
    args = parse_args()
    try:
        manifest = _load_json(args.manifest, "ReleaseEvidenceManifest")
        paths = _parse_evidence(args.evidence)
        payload = render(
            manifest=manifest,
            environment=args.environment,
            evidence={
                label: (path, _load_json(path, label))
                for label, path in paths.items()
            },
            required_evidence=args.require_evidence,
            archive_prefix=args.archive_prefix,
        )
        artifact_root = args.manifest.expanduser().resolve(strict=True).parent
        archive_environment_evidence(
            artifact_root=artifact_root,
            staging_root=args.output.parent,
            environment=args.environment,
            evidence_paths=paths,
            descriptors=payload["evidence"]["files"],
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.is_symlink():
            raise ValueError("environment receipt output cannot be a symbolic link")
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_environment_release_receipt: FAIL: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

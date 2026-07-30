#!/usr/bin/env python3
"""Bind successful stackctl/device evidence to one canonical environment receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    DIGEST_PATTERN,
    ENVIRONMENTS,
    validate_manifest,
)


TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
PREPROD_RUNTIME_EVIDENCE = frozenset({"package", "up", "health", "verify"})


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
    )
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
    images = manifest.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError(f"{environment} runtime requires immutable manifest images")
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
        or payload.get("runtimeMode") != "immutable-oci"
        or payload.get("runtimeCandidateDigest") != manifest.get("candidateId")
        or payload.get("destructiveRepairPerformed") is not False
        or payload.get("destructiveActions") != []
    ):
        raise ValueError(
            f"{environment} up evidence is not an immutable candidate runtime without destructive repair"
        )


def render(
    *,
    manifest: dict[str, Any],
    environment: str,
    evidence: dict[str, tuple[Path, dict[str, Any]]],
    required_evidence: list[str],
    archive_prefix: str,
) -> dict[str, Any]:
    validate_manifest(manifest, allowed_statuses={"candidate-ready", "deployable"})
    candidate = str(manifest.get("candidateId") or "")
    if DIGEST_PATTERN.fullmatch(candidate) is None:
        raise ValueError("environment receipt requires a sealed candidateId")
    if environment not in TARGETS:
        raise ValueError(f"unsupported environment: {environment}")
    canonical_required = set(required_evidence)
    if environment in {"alpha", "beta", "gamma"}:
        canonical_required.update(PREPROD_RUNTIME_EVIDENCE)
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
    if (
        not normalized_prefix
        or normalized_prefix.startswith(".")
        or ".." in Path(normalized_prefix).parts
        or Path(normalized_prefix).is_absolute()
    ):
        raise ValueError("environment evidence archive prefix is unsafe")
    evidence_files: dict[str, dict[str, str]] = {}
    timestamps: list[tuple[datetime, str]] = []
    expected_target = TARGETS[environment]
    for label, (path, payload) in sorted(evidence.items()):
        if payload.get("schema") == "candidate-bound-environment-evidence":
            raise ValueError(
                f"{label} evidence is a rewrapped compatibility envelope"
            )
        if not _passed(payload):
            raise ValueError(f"{label} evidence is not passed")
        declared_environment = payload.get("environment", payload.get("env"))
        if declared_environment not in {None, environment}:
            raise ValueError(f"{label} evidence environment mismatch")
        declared_target = payload.get("target")
        if declared_target not in {None, expected_target}:
            raise ValueError(f"{label} evidence target mismatch")
        require_direct_binding = label in {"package", "devices"}
        declared_candidate = payload.get("candidateId")
        if require_direct_binding and declared_candidate is None:
            raise ValueError(f"{label} evidence has no direct candidateId binding")
        if declared_candidate is not None and declared_candidate != candidate:
            raise ValueError(f"{label} evidence candidateId mismatch")
        declared_artifact = payload.get("artifactDigest")
        if label == "package" and declared_artifact is None:
            raise ValueError("package evidence has no direct artifactDigest binding")
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
        evidence_files[label] = {
            "path": f"{normalized_prefix}/{path.name}",
            "digest": _sha256(path),
        }
        timestamps.append(_timestamp(payload, label))

    source = manifest["source"]
    evidence_projection = {
        "candidateId": candidate,
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
        "candidateId": candidate,
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
        args.output.parent.mkdir(parents=True, exist_ok=True)
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

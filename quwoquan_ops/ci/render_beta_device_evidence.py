#!/usr/bin/env python3
"""Seal and merge candidate-bound Beta Android/iOS device evidence."""

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

from quwoquan_ops.ci.release_evidence_reader import (
    DIGEST_PATTERN,
    _passed,
    _timestamp,
    validate_historical_release_snapshot,
)


PLATFORMS = ("android", "ios")
STACK_LABELS = ("package", "up", "health", "verify")
IMMUTABLE_REF = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    stack = subparsers.add_parser("stack")
    stack.add_argument("--manifest", required=True, type=Path)
    stack.add_argument("--host-digest", required=True)
    stack.add_argument(
        "--stack-evidence",
        action="append",
        default=[],
        help="Native stack evidence NAME=JSON_PATH. Repeatable.",
    )
    stack.add_argument("--bundle-dir", required=True, type=Path)

    platform = subparsers.add_parser("platform")
    platform.add_argument("--manifest", required=True, type=Path)
    platform.add_argument("--platform", required=True, choices=PLATFORMS)
    platform.add_argument("--lease-evidence", required=True, type=Path)
    platform.add_argument("--execution-started-at", required=True)
    platform.add_argument("--execution-ended-at", required=True)
    platform.add_argument("--device-report-root", required=True, type=Path)
    platform.add_argument("--bundle-dir", required=True, type=Path)

    merge = subparsers.add_parser("merge")
    merge.add_argument("--manifest", required=True, type=Path)
    merge.add_argument("--expected-host-digest", required=True)
    merge.add_argument("--stack-bundle", required=True, type=Path)
    merge.add_argument("--stack-ref", required=True)
    merge.add_argument("--stack-digest", required=True)
    for name in PLATFORMS:
        merge.add_argument(f"--{name}-bundle", required=True, type=Path)
        merge.add_argument(f"--{name}-ref", required=True)
        merge.add_argument(f"--{name}-digest", required=True)
    merge.add_argument("--output", required=True, type=Path)
    return parser


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _parse_named_paths(items: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in items:
        name, separator, raw_path = item.partition("=")
        name = name.strip()
        if not separator or not name or not raw_path.strip():
            raise ValueError(f"expected NAME=JSON_PATH, got {item!r}")
        if name in result:
            raise ValueError(f"duplicate stack evidence: {name}")
        result[name] = Path(raw_path).expanduser().resolve()
    if set(result) != set(STACK_LABELS):
        raise ValueError(
            "Beta stack evidence requires exactly: " + ", ".join(STACK_LABELS)
        )
    return result


def _validate_manifest_identity(
    manifest: dict[str, Any],
) -> tuple[str, str, str, str]:
    validate_historical_release_snapshot(manifest, allowed_statuses={"candidate-ready", "deployable"})
    candidate = str(manifest.get("candidateId") or "")
    source = manifest.get("source")
    if DIGEST_PATTERN.fullmatch(candidate) is None or not isinstance(source, dict):
        raise ValueError("Beta device evidence requires one sealed candidate")
    git_sha = str(source.get("gitSha") or "")
    tree_digest = str(source.get("treeDigest") or "")
    artifact_digest = str(manifest.get("artifactDigest") or "")
    if re.fullmatch(r"[0-9a-f]{40}", git_sha) is None:
        raise ValueError("Beta device evidence source Git SHA is invalid")
    if not tree_digest:
        raise ValueError("Beta device evidence source tree digest is missing")
    if DIGEST_PATTERN.fullmatch(artifact_digest) is None:
        raise ValueError("Beta device evidence manifest artifactDigest is invalid")
    return candidate, git_sha, tree_digest, artifact_digest


def _require_direct_binding(
    payload: dict[str, Any],
    *,
    label: str,
    candidate: str,
    git_sha: str,
    tree_digest: str,
) -> None:
    expected = {
        "candidateId": candidate,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"{label} {field} is not directly bound to the candidate")


def _copy_regular_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"evidence file is missing or unsafe: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _empty_bundle(bundle_dir: Path, label: str) -> None:
    if bundle_dir.is_symlink() or (bundle_dir.exists() and any(bundle_dir.iterdir())):
        raise ValueError(f"{label} bundle destination must start empty")
    bundle_dir.mkdir(parents=True, exist_ok=True)


def render_stack_bundle(
    *,
    manifest: dict[str, Any],
    host_digest: str,
    stack_paths: dict[str, Path],
    bundle_dir: Path,
) -> dict[str, Any]:
    candidate, git_sha, tree_digest, artifact_digest = _validate_manifest_identity(
        manifest
    )
    if DIGEST_PATTERN.fullmatch(host_digest) is None:
        raise ValueError("Beta stack host digest is invalid")
    _empty_bundle(bundle_dir, "Beta stack")
    artifacts = manifest.get("environmentArtifacts")
    beta_artifact = artifacts.get("beta") if isinstance(artifacts, dict) else None
    manifest_images = (
        beta_artifact.get("images") if isinstance(beta_artifact, dict) else None
    )
    if not isinstance(manifest_images, dict) or not manifest_images:
        raise ValueError("Beta stack requires immutable Beta artifact images")
    expected_runtime_images: dict[str, dict[str, str]] = {}
    for service, descriptor in manifest_images.items():
        if not isinstance(service, str) or not isinstance(descriptor, dict):
            raise ValueError("Beta stack manifest image descriptor is invalid")
        ref = str(descriptor.get("ref") or "")
        digest = str(descriptor.get("digest") or "")
        if (
            IMMUTABLE_REF.fullmatch(ref) is None
            or DIGEST_PATTERN.fullmatch(digest) is None
            or ref.rsplit("@", 1)[1] != digest
        ):
            raise ValueError(f"Beta stack manifest image is not immutable: {service}")
        expected_runtime_images[service] = {"ref": ref, "digest": digest}
    stack_evidence: dict[str, dict[str, str]] = {}
    timestamps: list[tuple[datetime, str]] = []
    for label in STACK_LABELS:
        source_path = stack_paths[label]
        evidence = _load_json(source_path, label)
        if not _passed(evidence):
            raise ValueError(f"{label} evidence is not passed")
        declared_environment = evidence.get("environment", evidence.get("env"))
        if declared_environment not in {None, "beta"}:
            raise ValueError(f"{label} evidence environment mismatch")
        if evidence.get("target") not in {None, "beta-local"}:
            raise ValueError(f"{label} evidence target mismatch")
        if label == "package":
            _require_direct_binding(
                evidence,
                label=label,
                candidate=candidate,
                git_sha=git_sha,
                tree_digest=tree_digest,
            )
            if evidence.get("artifactDigest") != artifact_digest:
                raise ValueError("package artifactDigest is not bound to the manifest")
            if "formalRelease" in evidence:
                raise ValueError("package evidence must not claim formalRelease")
            if evidence.get("releaseInputClassification") != "commercial_inputs":
                raise ValueError(
                    "package evidence requires commercial release inputs"
                )
            if evidence.get("contractGraphDigest") != manifest.get(
                "contractGraphDigest"
            ):
                raise ValueError(
                    "package evidence ContractGraph differs from the manifest"
                )
        if label == "up":
            runtime_images = evidence.get("runtimeImages")
            runtime_images_valid = (
                isinstance(runtime_images, dict)
                and set(runtime_images) == set(expected_runtime_images)
            )
            if runtime_images_valid:
                for service, expected in expected_runtime_images.items():
                    runtime = runtime_images.get(service)
                    if (
                        not isinstance(runtime, dict)
                        or runtime.get("ref") != expected["ref"]
                        or runtime.get("digest") != expected["digest"]
                        or DIGEST_PATTERN.fullmatch(
                            str(runtime.get("runtimeImageId") or "")
                        )
                        is None
                        or not str(runtime.get("containerId") or "").strip()
                        or runtime.get("status") != "running"
                        or runtime.get("health") not in {"healthy", "not-declared"}
                    ):
                        runtime_images_valid = False
                        break
            if (
                evidence.get("runtimeMode") != "immutable-oci"
                or evidence.get("runtimeCandidateDigest") != candidate
                or evidence.get("formalRelease") is not True
                or evidence.get("releaseInputClassification")
                != "commercial_inputs"
                or not runtime_images_valid
                or evidence.get("destructiveRepairPerformed") is not False
                or evidence.get("destructiveActions") != []
            ):
                raise ValueError(
                    "Beta up evidence is not an immutable candidate runtime "
                    "with commercial release inputs and without destructive repair"
                )
            if evidence.get("contractGraphDigest") != manifest.get(
                "contractGraphDigest"
            ):
                raise ValueError(
                    "Beta up evidence ContractGraph differs from the manifest"
                )
        destination = bundle_dir / "raw" / f"{label}.json"
        _copy_regular_file(source_path, destination)
        relative = destination.relative_to(bundle_dir).as_posix()
        stack_evidence[label] = {"path": relative, "digest": _sha256(destination)}
        timestamps.append(_timestamp(evidence, label))
    payload = {
        "environment": "beta",
        "target": "beta-local",
        "status": "passed",
        "candidateId": candidate,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "artifactDigest": artifact_digest,
        "hostDigest": host_digest,
        "stackEvidence": stack_evidence,
        "endedAt": max(timestamps, key=lambda item: item[0])[1],
    }
    (bundle_dir / "stack.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _parse_instant(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is not an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def render_platform_bundle(
    *,
    manifest: dict[str, Any],
    platform: str,
    lease_evidence_path: Path,
    execution_started_at: str,
    execution_ended_at: str,
    device_report_root: Path,
    bundle_dir: Path,
) -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise ValueError(f"unsupported platform: {platform}")
    candidate, git_sha, tree_digest, artifact_digest = _validate_manifest_identity(
        manifest
    )
    _empty_bundle(bundle_dir, f"Beta {platform}")
    lease = _load_json(lease_evidence_path, f"Beta {platform} device lease")
    if "schema" in lease or lease.get("status") != "held":
        raise ValueError(f"Beta {platform} device lease is not canonical and held")
    if lease.get("platform") != platform:
        raise ValueError(f"Beta {platform} device lease platform mismatch")
    for field in ("hostDigest", "deviceIdDigest", "leaseId"):
        if DIGEST_PATTERN.fullmatch(str(lease.get(field) or "")) is None:
            raise ValueError(f"Beta {platform} device lease {field} is invalid")
    expected_runner_label = f"mobile-{platform}"
    if lease.get("runnerLabel") != expected_runner_label:
        raise ValueError(f"Beta {platform} runner label mismatch")
    acquired = _parse_instant(str(lease.get("acquiredAt") or ""), "lease acquiredAt")
    execution_start = _parse_instant(execution_started_at, "execution startedAt")
    execution_end = _parse_instant(execution_ended_at, "execution endedAt")
    if not acquired <= execution_start < execution_end:
        raise ValueError(f"Beta {platform} device lease does not cover execution")
    lease_destination = bundle_dir / "raw" / "device-lease.json"
    _copy_regular_file(lease_evidence_path, lease_destination)
    lease_claim = {
        "path": lease_destination.relative_to(bundle_dir).as_posix(),
        "digest": _sha256(lease_destination),
    }

    report_root = device_report_root.expanduser().resolve()
    if device_report_root.is_symlink() or not report_root.is_dir():
        raise ValueError("Beta device report root is missing or unsafe")
    entries = sorted(report_root.rglob("*"))
    unsafe = next((path for path in entries if path.is_symlink()), None)
    if unsafe is not None:
        raise ValueError(f"Beta device evidence contains a symlink: {unsafe}")
    files = [path for path in entries if path.is_file()]
    reports = [path for path in files if path.name.endswith(f"-{platform}.json")]
    if not reports:
        raise ValueError(f"Beta {platform} device reports are missing")
    copied_reports: dict[str, str] = {}
    for source_path in files:
        relative_source = source_path.relative_to(report_root)
        destination = bundle_dir / "raw" / "device-matrix" / relative_source
        _copy_regular_file(source_path, destination)
        if source_path in reports:
            report_payload = _load_json(source_path, source_path.name)
            if not _passed(report_payload):
                raise ValueError(
                    f"Beta {platform} device report is not passed: {source_path.name}"
                )
            report_time, _ = _timestamp(report_payload, source_path.name)
            if report_time < execution_start or report_time > execution_end:
                raise ValueError(
                    f"Beta {platform} report is outside the bound execution interval"
                )
            relative = destination.relative_to(bundle_dir).as_posix()
            copied_reports[relative] = _sha256(destination)

    payload = {
        "environment": "beta",
        "target": "beta-local",
        "platform": platform,
        "status": "passed",
        "candidateId": candidate,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "artifactDigest": artifact_digest,
        "deviceLease": {
            "hostDigest": lease["hostDigest"],
            "deviceIdDigest": lease["deviceIdDigest"],
            "leaseId": lease["leaseId"],
            "runnerLabel": lease["runnerLabel"],
            "acquiredAt": lease["acquiredAt"],
        },
        "deviceLeaseEvidence": lease_claim,
        "execution": {
            "startedAt": execution_started_at,
            "endedAt": execution_ended_at,
        },
        "reports": copied_reports,
        "endedAt": execution_ended_at,
    }
    (bundle_dir / "platform.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _validate_exact_ref(ref: str, digest: str, label: str) -> None:
    if IMMUTABLE_REF.fullmatch(ref) is None:
        raise ValueError(f"Beta {label} evidence ref is not an immutable GHCR ref")
    if DIGEST_PATTERN.fullmatch(digest) is None or ref.rsplit("@", 1)[1] != digest:
        raise ValueError(f"Beta {label} evidence ref/digest mismatch")


def _validate_claim(
    bundle: Path,
    *,
    label: str,
    claim: Any,
) -> None:
    if not isinstance(claim, dict):
        raise ValueError(f"Beta {label} claim is invalid")
    relative = str(claim.get("path") or "")
    digest = str(claim.get("digest") or "")
    path = bundle / relative
    try:
        path.resolve().relative_to(bundle.resolve())
    except ValueError as error:
        raise ValueError(f"Beta {label} path escapes its bundle") from error
    if path.is_symlink() or not path.is_file() or _sha256(path) != digest:
        raise ValueError(f"Beta {label} digest mismatch")


def _validate_stack_bundle_claims(bundle: Path, payload: dict[str, Any]) -> None:
    stack = payload.get("stackEvidence")
    if not isinstance(stack, dict) or set(stack) != set(STACK_LABELS):
        raise ValueError("Beta stack evidence is incomplete")
    for label in STACK_LABELS:
        _validate_claim(
            bundle,
            label=f"stackEvidence.{label}",
            claim=stack[label],
        )


def _validate_platform_bundle_claims(
    bundle: Path,
    payload: dict[str, Any],
    platform: str,
) -> None:
    _validate_claim(
        bundle,
        label=f"{platform}.deviceLeaseEvidence",
        claim=payload.get("deviceLeaseEvidence"),
    )
    reports = payload.get("reports")
    if not isinstance(reports, dict) or not reports:
        raise ValueError(f"Beta {platform} device reports are incomplete")
    for relative, digest in reports.items():
        _validate_claim(
            bundle,
            label=f"{platform}.reports.{relative}",
            claim={"path": relative, "digest": digest},
        )


def merge_platform_bundles(
    *,
    manifest: dict[str, Any],
    expected_host_digest: str,
    stack_bundle: Path,
    stack_ref: str,
    stack_digest: str,
    bundles: dict[str, Path],
    refs: dict[str, str],
    digests: dict[str, str],
) -> dict[str, Any]:
    candidate, git_sha, tree_digest, expected_artifact_digest = (
        _validate_manifest_identity(manifest)
    )
    if DIGEST_PATTERN.fullmatch(expected_host_digest) is None:
        raise ValueError("Beta expected host digest is invalid")
    stack_bundle = stack_bundle.expanduser().resolve()
    _validate_exact_ref(stack_ref, stack_digest, "stack")
    stack_payload_path = stack_bundle / "stack.json"
    stack_payload = _load_json(stack_payload_path, "Beta stack evidence")
    if "schema" in stack_payload:
        raise ValueError("Beta stack evidence must not create a second schema identity")
    if (
        stack_payload.get("environment") != "beta"
        or stack_payload.get("target") != "beta-local"
        or stack_payload.get("status") != "passed"
    ):
        raise ValueError("Beta stack environment evidence is not passed")
    _require_direct_binding(
        stack_payload,
        label="Beta stack",
        candidate=candidate,
        git_sha=git_sha,
        tree_digest=tree_digest,
    )
    if stack_payload.get("artifactDigest") != expected_artifact_digest:
        raise ValueError("Beta stack artifactDigest is not bound to the manifest")
    if stack_payload.get("hostDigest") != expected_host_digest:
        raise ValueError("Beta stack ran on an unexpected host")
    _validate_stack_bundle_claims(stack_bundle, stack_payload)

    all_refs = {stack_ref, refs["android"], refs["ios"]}
    all_digests = {stack_digest, digests["android"], digests["ios"]}
    if len(all_refs) != 3 or len(all_digests) != 3:
        raise ValueError("Beta Android/iOS evidence OCI identities must be distinct")
    platforms: dict[str, dict[str, str]] = {}
    platform_evidence: dict[str, dict[str, Any]] = {}
    timestamps: list[tuple[datetime, str]] = []
    artifact_digests: set[str] = set()
    host_digests: set[str] = {str(stack_payload.get("hostDigest") or "")}
    device_digests: set[str] = set()
    lease_ids: set[str] = set()
    execution_intervals: dict[str, tuple[datetime, datetime]] = {}
    for platform in PLATFORMS:
        bundle = bundles[platform].expanduser().resolve()
        _validate_exact_ref(refs[platform], digests[platform], platform)
        payload_path = bundle / "platform.json"
        payload = _load_json(payload_path, f"Beta {platform} platform evidence")
        if "schema" in payload:
            raise ValueError(
                f"Beta {platform} platform evidence must not create a second schema identity"
            )
        if payload.get("platform") != platform:
            raise ValueError(f"Beta {platform} platform identity mismatch")
        if payload.get("environment") != "beta" or payload.get("target") != "beta-local":
            raise ValueError(f"Beta {platform} environment identity mismatch")
        if payload.get("status") != "passed":
            raise ValueError(f"Beta {platform} platform evidence is not passed")
        _require_direct_binding(
            payload,
            label=f"Beta {platform}",
            candidate=candidate,
            git_sha=git_sha,
            tree_digest=tree_digest,
        )
        artifact_digest = str(payload.get("artifactDigest") or "")
        if DIGEST_PATTERN.fullmatch(artifact_digest) is None:
            raise ValueError(f"Beta {platform} artifactDigest is invalid")
        artifact_digests.add(artifact_digest)
        lease = payload.get("deviceLease")
        execution = payload.get("execution")
        if not isinstance(lease, dict) or not isinstance(execution, dict):
            raise ValueError(f"Beta {platform} lease/execution evidence is missing")
        if lease.get("runnerLabel") != f"mobile-{platform}":
            raise ValueError(f"Beta {platform} runner label mismatch")
        host_digest = str(lease.get("hostDigest") or "")
        device_digest = str(lease.get("deviceIdDigest") or "")
        lease_id = str(lease.get("leaseId") or "")
        for field, value in (
            ("hostDigest", host_digest),
            ("deviceIdDigest", device_digest),
            ("leaseId", lease_id),
        ):
            if DIGEST_PATTERN.fullmatch(value) is None:
                raise ValueError(f"Beta {platform} {field} is invalid")
        host_digests.add(host_digest)
        device_digests.add(device_digest)
        lease_ids.add(lease_id)
        execution_start = _parse_instant(
            str(execution.get("startedAt") or ""),
            f"Beta {platform} execution startedAt",
        )
        execution_end = _parse_instant(
            str(execution.get("endedAt") or ""),
            f"Beta {platform} execution endedAt",
        )
        if execution_start >= execution_end:
            raise ValueError(f"Beta {platform} execution interval is invalid")
        execution_intervals[platform] = (execution_start, execution_end)
        _validate_platform_bundle_claims(bundle, payload, platform)
        timestamps.append(_timestamp(payload, platform))
        platforms[platform] = {
            f"platforms/{platform}/{relative}": digest
            for relative, digest in payload["reports"].items()
        }
        platform_evidence[platform] = {
            "evidenceRef": refs[platform],
            "evidenceDigest": digests[platform],
            "payloadDigest": _sha256(payload_path),
            "hostDigest": host_digest,
            "deviceIdDigest": device_digest,
            "leaseId": lease_id,
            "runnerLabel": lease["runnerLabel"],
            "execution": execution,
        }
    if len(artifact_digests) != 1:
        raise ValueError("Beta Android/iOS package artifactDigest mismatch")
    if artifact_digests != {expected_artifact_digest}:
        raise ValueError("Beta platform artifactDigest is not bound to the manifest")
    if host_digests != {expected_host_digest}:
        raise ValueError("Beta stack and platform evidence did not run on one host")
    if len(device_digests) != 2 or len(lease_ids) != 2:
        raise ValueError("Beta Android/iOS require distinct device leases")
    latest_start = max(interval[0] for interval in execution_intervals.values())
    earliest_end = min(interval[1] for interval in execution_intervals.values())
    if latest_start >= earliest_end:
        raise ValueError("Beta Android/iOS executions did not overlap")
    return {
        "schema": "release-device-matrix-evidence",
        "environment": "beta",
        "target": "beta-local",
        "status": "passed",
        "candidateId": candidate,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "artifactDigest": artifact_digests.pop(),
        "stackEvidence": {
            "evidenceRef": stack_ref,
            "evidenceDigest": stack_digest,
            "payloadDigest": _sha256(stack_payload_path),
            "hostDigest": expected_host_digest,
        },
        "platforms": platforms,
        "platformEvidence": platform_evidence,
        "endedAt": max(timestamps, key=lambda item: item[0])[1],
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = _load_json(args.manifest, "ReleaseEvidenceManifest")
        if args.command == "stack":
            payload = render_stack_bundle(
                manifest=manifest,
                host_digest=args.host_digest,
                stack_paths=_parse_named_paths(args.stack_evidence),
                bundle_dir=args.bundle_dir.expanduser().resolve(),
            )
        elif args.command == "platform":
            payload = render_platform_bundle(
                manifest=manifest,
                platform=args.platform,
                lease_evidence_path=args.lease_evidence,
                execution_started_at=args.execution_started_at,
                execution_ended_at=args.execution_ended_at,
                device_report_root=args.device_report_root,
                bundle_dir=args.bundle_dir.expanduser().resolve(),
            )
        else:
            payload = merge_platform_bundles(
                manifest=manifest,
                expected_host_digest=args.expected_host_digest,
                stack_bundle=args.stack_bundle,
                stack_ref=args.stack_ref,
                stack_digest=args.stack_digest,
                bundles={name: getattr(args, f"{name}_bundle") for name in PLATFORMS},
                refs={name: getattr(args, f"{name}_ref") for name in PLATFORMS},
                digests={name: getattr(args, f"{name}_digest") for name in PLATFORMS},
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_beta_device_evidence: FAIL: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

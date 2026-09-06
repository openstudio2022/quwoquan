#!/usr/bin/env python3
"""Render and verify exact-byte GitHub-attested stability receipts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import sys

sys.dont_write_bytecode = True

from quwoquan_ops.ci.release_evidence_reader import (
    canonical_candidate_digest,
    canonical_manifest_digest,
    validate_historical_release_snapshot,
)

DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
CASE_IDS = {
    "recovery.ios": "environment-stability.recovery.ios",
    "recovery.android": "environment-stability.recovery.android",
    "nightly": "environment-stability.nightly_full",
}
CASE_FIELDS = frozenset(
    {
        "schema",
        "caseId",
        "status",
        "candidateId",
        "commit",
        "releaseId",
        "releaseDigest",
        "artifactDigest",
        "executed",
        "skipped",
        "executedAt",
    }
)
RUNTIME_RECOVERY_FIELDS = frozenset(
    {
        "authenticatedBefore",
        "authenticatedAfter",
        "sameOwner",
        "samePersona",
        "homeRestored",
        "secondFaultNoReentry",
    }
)


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _read_canonical_object(path: Path, *, label: str) -> dict[str, Any]:
    value = _read_object(path, label=label)
    if path.read_bytes() != _canonical_bytes(value):
        raise ValueError(f"{label} bytes are not canonical JSON")
    return value


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include timezone")
    return normalized


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _reject_local_authority(value: Mapping[str, Any], *, label: str) -> None:
    for key, child in _walk(value):
        normalized_key = key.replace("_", "").lower()
        normalized_value = (
            str(child or "").strip().lower() if isinstance(child, str) else ""
        )
        if normalized_value.startswith(("hmac-sha256:", "local-sha256:")):
            raise ValueError(f"{label} contains local attestation material")
        if (
            normalized_key in {"attestationauthority", "authority"}
            and normalized_value in {"local", "local-hmac", "developer", "workstation"}
        ):
            raise ValueError(f"{label} contains self-described local authority")


def _manifest(path: Path) -> tuple[Path, dict[str, Any]]:
    root = path.resolve().parent
    manifest = validate_historical_release_snapshot(
        _read_object(path, label="ReleaseEvidenceManifest"),
        allowed_statuses={"candidate-ready", "deployable", "released"},
    )
    if (
        manifest.get("candidateId") != canonical_candidate_digest(manifest)
        or manifest.get("artifactDigest") != canonical_manifest_digest(manifest)
    ):
        raise ValueError("ReleaseEvidenceManifest canonical identity drifted")
    return root, manifest


def _descriptor_files(descriptor: Mapping[str, Any]) -> set[tuple[str, str]]:
    bindings: set[tuple[str, str]] = set()
    for _, value in _walk(descriptor.get("evidence")):
        if not isinstance(value, Mapping):
            continue
        path = value.get("path")
        digest = value.get("digest")
        if (
            isinstance(path, str)
            and path.strip()
            and isinstance(digest, str)
            and DIGEST_PATTERN.fullmatch(digest) is not None
        ):
            bindings.add((path, digest))
    return bindings


def _bound_commercial_release(
    artifact_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    receipts = manifest.get("environmentReceipts")
    if not isinstance(receipts, Mapping) or set(receipts) != {
        "alpha",
        "beta",
        "gamma",
        "prod",
    }:
        raise ValueError("manifest lacks four environment receipt bindings")
    binding_sets = [
        _descriptor_files(receipts[environment])
        for environment in ("alpha", "beta", "gamma", "prod")
        if isinstance(receipts[environment], Mapping)
    ]
    if len(binding_sets) != 4:
        raise ValueError("manifest environment receipt descriptors are invalid")
    common = set.intersection(*binding_sets)
    candidates: list[dict[str, str]] = []
    for relative, expected_digest in sorted(common):
        path = (artifact_root / relative).resolve()
        try:
            path.relative_to(artifact_root)
        except ValueError:
            continue
        if not path.is_file() or path.is_symlink() or _sha256_file(path) != expected_digest:
            continue
        try:
            payload = _read_object(path, label="bound release attestation")
        except (TypeError, ValueError):
            continue
        release_id = str(payload.get("releaseId") or "").strip()
        release_digest = str(payload.get("payloadSha256") or "").strip()
        if (
            payload.get("schema") == "quwoquan_data.release_attestation"
            and (release_id == "pilot-003" or release_id.endswith("--pilot-003"))
            and payload.get("releaseClass") == "commercial"
            and payload.get("productLifecycleState") == "commercial"
            and payload.get("containsUnverifiedAssets") is False
            and payload.get("authorizationRequiredAssetIds") == []
            and DIGEST_PATTERN.fullmatch(release_digest) is not None
        ):
            candidates.append(
                {
                    "releaseId": release_id,
                    "releaseDigest": release_digest,
                    "attestationDigest": expected_digest,
                }
            )
    identities = {
        (item["releaseId"], item["releaseDigest"]): item for item in candidates
    }
    if len(identities) != 1:
        raise ValueError(
            "manifest must bind exactly one commercial pilot-003 release in all environments"
        )
    return next(iter(identities.values()))


def _identity(
    manifest_path: Path,
    *,
    expected_candidate: str,
    expected_artifact_digest: str,
    expected_source_sha: str,
) -> dict[str, str]:
    root, manifest = _manifest(manifest_path)
    candidate = str(manifest.get("candidateId") or "")
    artifact = str(manifest.get("artifactDigest") or "")
    commit = str((manifest.get("source") or {}).get("gitSha") or "")
    expected = {
        "candidateId": expected_candidate,
        "artifactDigest": expected_artifact_digest,
        "commit": expected_source_sha,
    }
    actual = {
        "candidateId": candidate,
        "artifactDigest": artifact,
        "commit": commit,
    }
    if actual != expected:
        raise ValueError("candidate, commit, or artifact binding differs from workflow input")
    release = _bound_commercial_release(root, manifest)
    return {**actual, **release}


def _verify_release_binding(manifest_path: Path, release_attestation: Path) -> None:
    root, manifest = _manifest(manifest_path)
    expected = _bound_commercial_release(root, manifest)
    supplied = _read_object(
        release_attestation,
        label="runtime commercial release attestation",
    )
    actual = {
        "releaseId": str(supplied.get("releaseId") or "").strip(),
        "releaseDigest": str(supplied.get("payloadSha256") or "").strip(),
        "attestationDigest": _sha256_file(release_attestation),
    }
    if supplied.get("schema") != "quwoquan_data.release_attestation" or actual != expected:
        raise ValueError(
            "runtime commercial release bytes differ from manifest-bound pilot-003"
        )


def _recovery_execution(path: Path, *, platform: str) -> tuple[int, str]:
    report = _read_object(path, label=f"{platform} runtime recovery report")
    _reject_local_authority(report, label=f"{platform} runtime recovery report")
    cases = report.get("caseResults")
    if (
        report.get("status") != "passed"
        or report.get("platform") != platform
        or not str(report.get("target") or "").endswith(
            "runtime_recovery_journey__user_acceptance_test.dart"
        )
        or not isinstance(cases, list)
        or not cases
    ):
        raise ValueError(f"{platform} runtime recovery report is not a passed canonical run")
    executed = 0
    for item in cases:
        if not isinstance(item, Mapping) or item.get("status") != "passed":
            raise ValueError(f"{platform} runtime recovery contains a failed case")
        execution = item.get("testExecution")
        evidence = item.get("evidence")
        recovery = evidence.get("runtimeRecovery") if isinstance(evidence, Mapping) else None
        count = execution.get("executed") if isinstance(execution, Mapping) else None
        failed = execution.get("failed") if isinstance(execution, Mapping) else None
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
            or failed != 0
            or not isinstance(recovery, Mapping)
            or set(recovery) != RUNTIME_RECOVERY_FIELDS
            or not all(value is True for value in recovery.values())
        ):
            raise ValueError(
                f"{platform} runtime recovery lacks executed, zero-failure recovery evidence"
            )
        executed += count
    return executed, _timestamp(report.get("endedAt"), label="recovery endedAt")


def _case_payload(
    kind: str,
    *,
    identity: Mapping[str, str],
    executed: int,
    executed_at: str,
) -> dict[str, Any]:
    if kind not in CASE_IDS:
        raise ValueError(f"unsupported stability receipt kind: {kind}")
    payload = {
        "schema": "quwoquan.test.case-result",
        "caseId": CASE_IDS[kind],
        "status": "passed",
        "candidateId": identity["candidateId"],
        "commit": identity["commit"],
        "releaseId": identity["releaseId"],
        "releaseDigest": identity["releaseDigest"],
        "artifactDigest": identity["artifactDigest"],
        "executed": executed,
        "skipped": 0,
        "executedAt": executed_at,
    }
    _validate_case(payload, kind=kind)
    return payload


def _validate_case(payload: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    if kind not in CASE_IDS:
        raise ValueError(f"unsupported stability receipt kind: {kind}")
    if (
        set(payload) != CASE_FIELDS
        or payload.get("schema") != "quwoquan.test.case-result"
        or payload.get("caseId") != CASE_IDS[kind]
        or payload.get("status") != "passed"
        or DIGEST_PATTERN.fullmatch(str(payload.get("candidateId") or "")) is None
        or DIGEST_PATTERN.fullmatch(str(payload.get("releaseDigest") or "")) is None
        or DIGEST_PATTERN.fullmatch(str(payload.get("artifactDigest") or "")) is None
        or GIT_SHA_PATTERN.fullmatch(str(payload.get("commit") or "")) is None
        or not str(payload.get("releaseId") or "").strip()
        or not isinstance(payload.get("executed"), int)
        or isinstance(payload.get("executed"), bool)
        or int(payload["executed"]) <= 0
        or payload.get("skipped") != 0
    ):
        raise ValueError(f"{kind} is not a complete passed canonical case result")
    _timestamp(payload.get("executedAt"), label=f"{kind}.executedAt")
    _reject_local_authority(payload, label=kind)
    return dict(payload)


def _validate_prod_sim(payload: Mapping[str, Any]) -> dict[str, Any]:
    eligibility = payload.get("releaseEligibility")
    release = payload.get("releaseEvidence")
    if not (
        payload.get("schema") == "prod-hosted-first-party-prevalidation-report"
        and payload.get("target") == "prod-hosted"
        and payload.get("mode") == "prevalidate"
        and payload.get("dataMode") == "isolated"
        and payload.get("scope") == "first-party"
        and payload.get("dryRun") is False
        and (payload.get("containerDeployment") or {}).get("status") == "passed"
        and isinstance(eligibility, Mapping)
        and eligibility.get("status") == "GATE_BLOCK"
        and eligibility.get("promotable") is False
        and eligibility.get("ledgerWritten") is False
        and eligibility.get("receiptWritten") is False
        and payload.get("issues") == []
        and isinstance(release, Mapping)
        and DIGEST_PATTERN.fullmatch(str(release.get("candidateId") or "")) is not None
        and DIGEST_PATTERN.fullmatch(str(release.get("artifactDigest") or "")) is not None
        and GIT_SHA_PATTERN.fullmatch(
            str((release.get("source") or {}).get("gitSha") or "")
        )
        is not None
        and str(payload.get("releaseId") or "").strip()
        and DIGEST_PATTERN.fullmatch(str(payload.get("releaseDigest") or "")) is not None
    ):
        raise ValueError("prod-sim report is not the canonical passed non-promotable rehearsal")
    _timestamp(payload.get("endedAt"), label="prod-sim.endedAt")
    _reject_local_authority(payload, label="prod-sim report")
    return dict(payload)


def _write_github_output(path: str, name: str, value: str) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _encode_receipt(path: Path, github_output: str) -> None:
    _write_github_output(
        github_output,
        "receipt_base64",
        base64.b64encode(path.read_bytes()).decode("ascii"),
    )


def _render_recovery(args: argparse.Namespace) -> None:
    identity = _identity(
        args.manifest,
        expected_candidate=args.expected_candidate,
        expected_artifact_digest=args.expected_artifact_digest,
        expected_source_sha=args.expected_source_sha,
    )
    executed, ended_at = _recovery_execution(args.evidence, platform=args.platform)
    kind = f"recovery.{args.platform}"
    _write_object(
        args.output,
        _case_payload(
            kind,
            identity=identity,
            executed=executed,
            executed_at=ended_at,
        ),
    )
    _encode_receipt(args.output, args.github_output)


def _aggregate_nightly(args: argparse.Namespace) -> None:
    ios = _validate_case(
        _read_canonical_object(args.ios_receipt, label="iOS recovery receipt"),
        kind="recovery.ios",
    )
    android = _validate_case(
        _read_canonical_object(args.android_receipt, label="Android recovery receipt"),
        kind="recovery.android",
    )
    identity_fields = (
        "candidateId",
        "commit",
        "releaseId",
        "releaseDigest",
        "artifactDigest",
    )
    if any(ios[field] != android[field] for field in identity_fields):
        raise ValueError("iOS and Android recovery receipts have different identities")
    identity = {field: str(ios[field]) for field in identity_fields}
    executed_at = max(
        (
            _timestamp(ios["executedAt"], label="iOS recovery executedAt"),
            _timestamp(android["executedAt"], label="Android recovery executedAt"),
        ),
        key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    _write_object(
        args.output,
        _case_payload(
            "nightly",
            identity=identity,
            executed=int(ios["executed"]) + int(android["executed"]),
            executed_at=executed_at,
        ),
    )


def _bind_prod_sim(args: argparse.Namespace) -> None:
    identity = _identity(
        args.manifest,
        expected_candidate=args.expected_candidate,
        expected_artifact_digest=args.expected_artifact_digest,
        expected_source_sha=args.expected_source_sha,
    )
    report = _read_object(args.report, label="prod-sim report")
    release = report.get("releaseEvidence")
    if (
        not isinstance(release, Mapping)
        or release.get("candidateId") != identity["candidateId"]
        or release.get("artifactDigest") != identity["artifactDigest"]
        or (release.get("source") or {}).get("gitSha") != identity["commit"]
    ):
        raise ValueError("prod-sim report differs from candidate, commit, or artifact")
    report["releaseId"] = identity["releaseId"]
    report["releaseDigest"] = identity["releaseDigest"]
    _validate_prod_sim(report)
    _write_object(args.report, report)
    _encode_receipt(args.report, args.github_output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    recovery = subparsers.add_parser("render-recovery")
    recovery.add_argument("--platform", choices=("ios", "android"), required=True)
    recovery.add_argument("--manifest", type=Path, required=True)
    recovery.add_argument("--evidence", type=Path, required=True)
    recovery.add_argument("--expected-candidate", required=True)
    recovery.add_argument("--expected-artifact-digest", required=True)
    recovery.add_argument("--expected-source-sha", required=True)
    recovery.add_argument("--output", type=Path, required=True)
    recovery.add_argument("--github-output", default="")

    verify_case = subparsers.add_parser("verify-case")
    verify_case.add_argument("--kind", choices=tuple(CASE_IDS), required=True)
    verify_case.add_argument("--receipt", type=Path, required=True)

    nightly = subparsers.add_parser("aggregate-nightly")
    nightly.add_argument("--ios-receipt", type=Path, required=True)
    nightly.add_argument("--android-receipt", type=Path, required=True)
    nightly.add_argument("--output", type=Path, required=True)

    bind_prod_sim = subparsers.add_parser("bind-prod-sim")
    bind_prod_sim.add_argument("--report", type=Path, required=True)
    bind_prod_sim.add_argument("--manifest", type=Path, required=True)
    bind_prod_sim.add_argument("--expected-candidate", required=True)
    bind_prod_sim.add_argument("--expected-artifact-digest", required=True)
    bind_prod_sim.add_argument("--expected-source-sha", required=True)
    bind_prod_sim.add_argument("--github-output", default="")

    verify_prod_sim = subparsers.add_parser("verify-prod-sim")
    verify_prod_sim.add_argument("--receipt", type=Path, required=True)

    verify_release = subparsers.add_parser("verify-release-binding")
    verify_release.add_argument("--manifest", type=Path, required=True)
    verify_release.add_argument("--release-attestation", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "render-recovery":
        _render_recovery(args)
    elif args.command == "verify-case":
        _validate_case(
            _read_canonical_object(args.receipt, label=args.kind),
            kind=args.kind,
        )
    elif args.command == "aggregate-nightly":
        _aggregate_nightly(args)
    elif args.command == "bind-prod-sim":
        _bind_prod_sim(args)
    elif args.command == "verify-prod-sim":
        _validate_prod_sim(
            _read_canonical_object(args.receipt, label="prod-sim report")
        )
    elif args.command == "verify-release-binding":
        _verify_release_binding(args.manifest, args.release_attestation)
    else:  # pragma: no cover - argparse owns command enumeration.
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

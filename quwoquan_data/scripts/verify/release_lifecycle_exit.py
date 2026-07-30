"""Validate one environment's original -> rollback -> replay Exit receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root
from verify.release_lifecycle_attestation import read_object, validate_document
from verify.verify_release_lifecycle import environment_lifecycle_issues

ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
SCHEMA = "quwoquan_data.environment_release_lifecycle_exit"
FILENAME = "lifecycle-exit.json"


def checksum(document: Mapping[str, Any]) -> str:
    unsigned = dict(document)
    unsigned.pop("verificationChecksum", None)
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def receipt_path(
    *,
    output_root: Path,
    environment: str,
    original_release_id: str,
    exit_run_id: str,
) -> Path:
    return (
        output_root
        / "env"
        / environment
        / "runs"
        / "release-lifecycle-exit"
        / original_release_id
        / exit_run_id
        / FILENAME
    )


def _attestation(
    release_root: Path,
    release_id: str,
    *,
    issues: list[str],
) -> dict[str, Any]:
    path = attestation_root(release_root / release_id) / "release.json"
    document = read_object(path, label="release attestation", issues=issues)
    if document:
        validate_document(
            document,
            path=path,
            schema_name="release_attestation",
            issues=issues,
        )
    return document


def _run_file_ref(
    *,
    environment: str,
    release_id: str,
    run_id: str,
    filename: str,
) -> str:
    return (
        Path("env")
        / environment
        / "runs"
        / "data-release"
        / release_id
        / run_id
        / filename
    ).as_posix()


def _run_kind(
    *,
    output_root: Path,
    environment: str,
    release_id: str,
    run_id: str,
    expected: str,
    issues: list[str],
) -> None:
    path = (
        output_root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / run_id
        / "run.json"
    )
    document = read_object(path, label="environment release run", issues=issues)
    if document and document.get("kind") != expected:
        issues.append(f"{path}: run kind must be {expected}")


def lifecycle_exit_issues(
    document: Mapping[str, Any],
    *,
    path: Path,
    release_root: Path = RELEASE_ROOT,
    output_root: Path = OUTPUT_ROOT,
) -> list[str]:
    """Recompute every binding; a self-consistent receipt alone is insufficient."""

    receipt = dict(document)
    issues: list[str] = []
    if not validate_document(
        receipt,
        path=path,
        schema_name="environment_release_lifecycle_exit",
        issues=issues,
    ):
        return issues
    environment = str(receipt["environment"])
    original = str(receipt["originalReleaseId"])
    rollback_to = str(receipt["rollbackToReleaseId"])
    exit_run_id = str(receipt["exitRunId"])
    expected_path = receipt_path(
        output_root=output_root,
        environment=environment,
        original_release_id=original,
        exit_run_id=exit_run_id,
    )
    if path.resolve() != expected_path.resolve():
        issues.append(f"{path}: receipt path is not bound to environment/release/exitRunId")
    if environment not in ENVIRONMENTS:
        issues.append(f"{path}: environment is invalid")
    if original == rollback_to:
        issues.append(f"{path}: rollbackToReleaseId must differ from originalReleaseId")

    run_ids = [
        str(receipt[field])
        for field in (
            "originalImportRunId",
            "originalVerifyRunId",
            "rollbackRunId",
            "rollbackVerifyRunId",
            "replayImportRunId",
            "replayVerifyRunId",
        )
    ]
    if len(run_ids) != len(set(run_ids)):
        issues.append(f"{path}: lifecycle run IDs must be distinct")

    original_attestation = _attestation(release_root, original, issues=issues)
    rollback_attestation = _attestation(release_root, rollback_to, issues=issues)
    original_digest = str(original_attestation.get("payloadSha256") or "")
    rollback_digest = str(rollback_attestation.get("payloadSha256") or "")
    if original_attestation.get("sourceOwner") != "qwq_data":
        issues.append(f"{path}: original release sourceOwner must be qwq_data")
    if original_attestation.get("releaseKind") != "content":
        issues.append(f"{path}: original release must be a content release")
    if rollback_attestation.get("sourceOwner") != "qwq_data":
        issues.append(f"{path}: rollback release sourceOwner must be qwq_data")
    if receipt.get("sourceOwner") != "qwq_data":
        issues.append(f"{path}: receipt sourceOwner must be qwq_data")
    if receipt.get("originalManifestDigest") != original_digest:
        issues.append(f"{path}: originalManifestDigest drift")
    if receipt.get("rollbackToManifestDigest") != rollback_digest:
        issues.append(f"{path}: rollbackToManifestDigest drift")
    if receipt.get("replayManifestDigest") != original_digest:
        issues.append(f"{path}: replayManifestDigest must equal original payload digest")

    phases = (
        (
            original,
            str(receipt["originalImportRunId"]),
            str(receipt["originalVerifyRunId"]),
            None,
            "apply",
        ),
        (
            rollback_to,
            str(receipt["rollbackRunId"]),
            str(receipt["rollbackVerifyRunId"]),
            original,
            "rollback",
        ),
        (
            original,
            str(receipt["replayImportRunId"]),
            str(receipt["replayVerifyRunId"]),
            None,
            "apply",
        ),
    )
    for release_id, import_run_id, verify_run_id, rollback_from, expected_kind in phases:
        issues.extend(
            environment_lifecycle_issues(
                release_id,
                environment=environment,
                import_run_id=import_run_id,
                verify_run_id=verify_run_id,
                rollback_from_release_id=rollback_from,
                release_root=release_root,
                output_root=output_root,
            )
        )
        _run_kind(
            output_root=output_root,
            environment=environment,
            release_id=release_id,
            run_id=import_run_id,
            expected=expected_kind,
            issues=issues,
        )

    expected_refs = {
        "originalImportResultRef": _run_file_ref(
            environment=environment,
            release_id=original,
            run_id=str(receipt["originalImportRunId"]),
            filename="result.json",
        ),
        "originalVerifyResultRef": _run_file_ref(
            environment=environment,
            release_id=original,
            run_id=str(receipt["originalVerifyRunId"]),
            filename="result.json",
        ),
        "rollbackResultRef": _run_file_ref(
            environment=environment,
            release_id=rollback_to,
            run_id=str(receipt["rollbackRunId"]),
            filename="result.json",
        ),
        "rollbackVerifyResultRef": _run_file_ref(
            environment=environment,
            release_id=rollback_to,
            run_id=str(receipt["rollbackVerifyRunId"]),
            filename="result.json",
        ),
        "replayImportResultRef": _run_file_ref(
            environment=environment,
            release_id=original,
            run_id=str(receipt["replayImportRunId"]),
            filename="result.json",
        ),
        "replayVerifyResultRef": _run_file_ref(
            environment=environment,
            release_id=original,
            run_id=str(receipt["replayVerifyRunId"]),
            filename="result.json",
        ),
    }
    for field, expected in expected_refs.items():
        if receipt.get(field) != expected:
            issues.append(f"{path}: {field} does not bind canonical run evidence")
        elif not (output_root / expected).is_file():
            issues.append(f"{path}: {field} evidence is missing")
    if receipt.get("passed") is not True:
        issues.append(f"{path}: passed must be true")
    if receipt.get("verificationChecksum") != checksum(receipt):
        issues.append(f"{path}: verificationChecksum drift")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="重算验证一个环境的 original→rollback→replay Exit receipt"
    )
    parser.add_argument("--environment", required=True, choices=sorted(ENVIRONMENTS))
    parser.add_argument("--original-release", required=True)
    parser.add_argument("--exit-run", required=True)
    args = parser.parse_args(argv)
    path = receipt_path(
        output_root=OUTPUT_ROOT,
        environment=args.environment,
        original_release_id=args.original_release,
        exit_run_id=args.exit_run,
    )
    issues: list[str] = []
    document = read_object(path, label="release lifecycle Exit receipt", issues=issues)
    if document:
        issues.extend(
            lifecycle_exit_issues(
                document,
                path=path,
                release_root=RELEASE_ROOT,
                output_root=OUTPUT_ROOT,
            )
        )
    if issues:
        print("[verify_release_lifecycle_exit] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(
        "[verify_release_lifecycle_exit] OK "
        f"environment={args.environment} originalRelease={args.original_release} "
        f"exitRun={args.exit_run}"
    )
    return 0


__all__ = ["FILENAME", "checksum", "lifecycle_exit_issues", "main", "receipt_path"]


if __name__ == "__main__":
    raise SystemExit(main())

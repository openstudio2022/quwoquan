#!/usr/bin/env python3
"""Verify data runtime evidence is bound to repository-owned source inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution.execution_terminal import load_terminal_execution_evidence
from content.execution.identity import validate_execution_id
from core.paths import DATA_EXECUTIONS_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_file
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDigest,
    SourceDigestError,
    SourceDefinitionSnapshot,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
    parse_source_digest_document,
)


def _read_object(path: Path, *, issues: list[str]) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"{path}: unreadable JSON: {exc}")
        return None
    if not isinstance(value, dict):
        issues.append(f"{path}: top-level document must be an object")
        return None
    return value


def _document_digests(
    document: dict[str, object], *, path: Path, issues: list[str]
) -> tuple[SourceDigest, ...] | None:
    raw_value = document.get("sourceDigests")
    if not isinstance(raw_value, list):
        issues.append(f"{path}: sourceDigests must be an array")
        return None
    raw_identities = document.get("sourceIdentities") or []
    if not isinstance(raw_identities, list):
        issues.append(f"{path}: sourceIdentities must be an array")
        return None
    try:
        source_digests = tuple(
            parse_source_digest_document(item) for item in raw_value
        )
    except SourceDigestError as exc:
        issues.append(f"{path}: {exc}")
        return None
    values = tuple(item.digest for item in source_digests)
    if not values or values != tuple(sorted(set(values))):
        issues.append(f"{path}: sourceDigests must be sorted and contain no duplicates")
        return None
    return source_digests


def source_digest_issues(
    *,
    executions_root: Path = DATA_EXECUTIONS_ROOT,
    release_root: Path = RELEASE_ROOT,
    candidate_execution_id: str | None = None,
) -> list[str]:
    """Return drift/errors without treating output as a persistent source."""
    issues: list[str] = []
    manifest_paths: tuple[Path, ...] = ()
    if candidate_execution_id is not None:
        try:
            normalized = validate_execution_id(candidate_execution_id)
        except ValueError as exc:
            return [
                "GATE_BLOCK DATA.EXECUTION.CANDIDATE_ID_INVALID: " + str(exc)
            ]
        manifest_path = executions_root / normalized / "execution_manifest.json"
        if not manifest_path.is_file():
            return [
                "GATE_BLOCK DATA.EXECUTION.CANDIDATE_NOT_FOUND: "
                f"execution manifest does not exist: {manifest_path}"
            ]
        manifest_paths = (manifest_path,)
    elif executions_root.is_dir():
        manifest_paths = tuple(
            sorted(executions_root.glob("*/execution_manifest.json"))
        )
    current_snapshot = current_source_definition_snapshot()
    current_bundle = current_execution_bundle_identity()
    if executions_root.is_dir():
        for manifest_path in manifest_paths:
            try:
                terminal = load_terminal_execution_evidence(manifest_path.parent)
            except (OSError, TypeError, ValueError) as exc:
                issues.append(
                    f"{manifest_path.parent}: invalid terminal execution evidence: {exc}"
                )
                terminal = None
            if terminal is not None:
                continue
            manifest = _read_object(manifest_path, issues=issues)
            if manifest is None:
                continue
            if "executionBundle" not in manifest:
                issues.append(
                    f"{manifest_path}: GATE_BLOCK "
                    "DATA.EXECUTION.SOURCE_IDENTITY_MIGRATION_REQUIRED: "
                    "pre-bundle nonterminal execution cannot resume"
                )
                continue
            try:
                digest = SourceDefinitionSnapshot.from_document(
                    manifest.get("sourceDigest")
                )
                bundle = ExecutionBundleIdentity.from_document(
                    manifest.get("executionBundle")
                )
            except SourceDigestError as exc:
                issues.append(f"{manifest_path}: {exc}")
                continue
            if digest != current_snapshot or bundle != current_bundle:
                issues.append(
                    f"{manifest_path}: candidate source snapshot/execution bundle drift; "
                    "create a new execution sequence with retryOf"
                )
    if candidate_execution_id is None and release_root.is_dir():
        for release_dir in sorted(path for path in release_root.iterdir() if path.is_dir()):
            header_path = payload_file(release_dir, "release.json")
            aggregate_path = attestation_root(release_dir) / "release.json"
            if not header_path.is_file() and not aggregate_path.is_file():
                continue
            header = _read_object(header_path, issues=issues)
            aggregate = _read_object(aggregate_path, issues=issues)
            if header is None or aggregate is None:
                continue
            digests = _document_digests(header, path=header_path, issues=issues)
            aggregate_digests = _document_digests(
                aggregate,
                path=aggregate_path,
                issues=issues,
            )
            if (
                digests is not None
                and aggregate_digests is not None
                and digests != aggregate_digests
            ):
                issues.append(f"{aggregate_path}: sourceDigests drift from release header")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证 data execution/release source digest")
    parser.add_argument("--execution-id")
    args = parser.parse_args(argv)
    issues = source_digest_issues(candidate_execution_id=args.execution_id)
    if issues:
        print("[verify_source_digest] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_source_digest] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

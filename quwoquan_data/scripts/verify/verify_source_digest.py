#!/usr/bin/env python3
"""Verify data runtime evidence is bound to repository-owned source inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.paths import DATA_EXECUTIONS_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_file
from core.source_digest import SourceDigest, SourceDigestError, current_source_digest


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


def _document_digest(
    document: dict[str, object], *, path: Path, issues: list[str]
) -> SourceDigest | None:
    try:
        return SourceDigest.from_document(document.get("sourceDigest"))
    except SourceDigestError as exc:
        issues.append(f"{path}: {exc}")
        return None


def source_digest_issues(
    *,
    executions_root: Path = DATA_EXECUTIONS_ROOT,
    release_root: Path = RELEASE_ROOT,
) -> list[str]:
    """Return drift/errors without treating output as a persistent source."""
    issues: list[str] = []
    current = current_source_digest()
    if executions_root.is_dir():
        for manifest_path in sorted(executions_root.glob("*/execution_manifest.json")):
            manifest = _read_object(manifest_path, issues=issues)
            if manifest is None:
                continue
            digest = _document_digest(manifest, path=manifest_path, issues=issues)
            if digest is not None and digest != current:
                issues.append(
                    f"{manifest_path}: sourceDigest drift; resume requires a new execution sequence"
                )
    if release_root.is_dir():
        for release_dir in sorted(path for path in release_root.iterdir() if path.is_dir()):
            header_path = payload_file(release_dir, "release.json")
            aggregate_path = attestation_root(release_dir) / "aggregate.json"
            if not header_path.is_file() and not aggregate_path.is_file():
                continue
            header = _read_object(header_path, issues=issues)
            aggregate = _read_object(aggregate_path, issues=issues)
            if header is None or aggregate is None:
                continue
            digest = _document_digest(header, path=header_path, issues=issues)
            aggregate_digest = _document_digest(aggregate, path=aggregate_path, issues=issues)
            if digest is not None and aggregate_digest is not None and digest != aggregate_digest:
                issues.append(f"{aggregate_path}: sourceDigest drift from release header")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证 data execution/release source digest")
    parser.parse_args(argv)
    issues = source_digest_issues()
    if issues:
        print("[verify_source_digest] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_source_digest] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

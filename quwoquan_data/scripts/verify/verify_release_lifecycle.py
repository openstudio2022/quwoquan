#!/usr/bin/env python3
"""Verify one immutable data release has the minimum lifecycle evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid


AGGREGATE_ATTESTATION = "aggregate.json"


def _read_object(path: Path, *, label: str, issues: list[str]) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"{path}: invalid {label}: {exc}")
        return {}
    if not isinstance(payload, dict):
        issues.append(f"{path}: {label} must be an object")
        return {}
    return payload


def release_lifecycle_issues(release_id: str, *, release_root: Path | None = None) -> list[str]:
    root = (release_root or RELEASE_ROOT) / release_id
    required = (
        payload_file(root, "release.json"),
        payload_file(root, "desired_state.json"),
        attestation_root(root) / AGGREGATE_ATTESTATION,
    )
    issues = [f"{path}: missing immutable release evidence" for path in required if not path.is_file()]
    release_file = payload_file(root, "release.json")
    desired_file = payload_file(root, "desired_state.json")
    aggregate_file = attestation_root(root) / AGGREGATE_ATTESTATION
    if not release_file.is_file() or not desired_file.is_file() or not aggregate_file.is_file():
        return issues

    header = _read_object(release_file, label="release header", issues=issues)
    desired = _read_object(desired_file, label="desired state", issues=issues)
    aggregate = _read_object(aggregate_file, label="aggregate attestation", issues=issues)
    if not header or not desired or not aggregate:
        return issues
    try:
        assert_valid(
            aggregate,
            "release",
            "aggregate_release_attestation",
            label=f"aggregate_release_attestation:{release_id}",
        )
    except (FileNotFoundError, ValueError) as exc:
        issues.append(str(exc))
        return issues

    if header.get("releaseId") != release_id:
        issues.append(f"{release_file}: releaseId does not match directory")
    release_kind = header.get("releaseKind")
    if release_kind not in {"content", "empty_baseline"}:
        issues.append(f"{release_file}: releaseKind is invalid")
    header_execution_ids = header.get("executionIds")
    if not isinstance(header_execution_ids, list):
        issues.append(f"{release_file}: executionIds must be an array")
        header_execution_ids = []
    desired_refs = desired.get("desiredRefs")
    if not isinstance(desired_refs, dict):
        issues.append(f"{desired_file}: desiredRefs must be an object")
        desired_refs = {}
    entity_refs = desired_refs.get("entities")
    tag_refs = desired_refs.get("tags")
    if not isinstance(entity_refs, list) or not isinstance(tag_refs, list):
        issues.append(f"{desired_file}: desiredRefs.entities/tags must be arrays")
        return issues
    if aggregate.get("releaseId") != release_id:
        issues.append(f"{aggregate_file}: releaseId does not match directory")
    if aggregate.get("releaseKind") != release_kind:
        issues.append(f"{aggregate_file}: releaseKind drift from release header")
    if sorted(aggregate.get("executionIds") or []) != sorted(header_execution_ids):
        issues.append(f"{aggregate_file}: executionIds drift from release header")
    if aggregate.get("canonicalMerkle") != header.get("canonicalMerkle"):
        issues.append(f"{aggregate_file}: canonicalMerkle drift from release header")
    if aggregate.get("entityCount") != len(entity_refs):
        issues.append(f"{aggregate_file}: entityCount drift from desired state")
    if aggregate.get("tagCount") != len(tag_refs):
        issues.append(f"{aggregate_file}: tagCount drift from desired state")
    if release_kind == "content" and (not header_execution_ids or not entity_refs):
        issues.append(f"{release_file}: content release requires executionIds and entity refs")
    if release_kind == "empty_baseline" and (header_execution_ids or entity_refs or tag_refs):
        issues.append(f"{release_file}: empty baseline must have no executions, entities, or tags")
    try:
        actual_payload_digest = payload_digest(root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        issues.append(f"{root}: cannot compute payload digest: {exc}")
    else:
        if aggregate.get("payloadSha256") != actual_payload_digest:
            issues.append(f"{aggregate_file}: payloadSha256 drift from immutable payload")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证不可变 release 生命周期证据")
    parser.add_argument("--release", required=True)
    args = parser.parse_args(argv)
    issues = release_lifecycle_issues(args.release)
    if issues:
        print("[verify_release_lifecycle] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print(f"[verify_release_lifecycle] OK release={args.release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

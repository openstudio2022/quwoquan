#!/usr/bin/env python3
"""Fail closed unless materialized release evidence matches workflow identity."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import validate_manifest


DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA = re.compile(r"[0-9a-f]{40}")
IMMUTABLE_RELEASE_REF = re.compile(
    r"ghcr\.io/[a-z0-9._/-]+/release-artifact@sha256:[0-9a-f]{64}"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--expected-candidate", default="")
    parser.add_argument("--expected-artifact-digest", required=True)
    parser.add_argument("--expected-workflow-run-id", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-release-ref", default="")
    parser.add_argument("--discovered-release-ref", default="")
    parser.add_argument("--require-deployable", action="store_true")
    parser.add_argument("--expect-component-ready", action="store_true")
    return parser.parse_args()


def validate(args: argparse.Namespace) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != "release-evidence-manifest":
        raise ValueError("canonical ReleaseEvidenceManifest is required")
    allowed_statuses = (
        {"component-ready"}
        if args.expect_component_ready
        else (
            {"main-admitted"}
            if args.require_deployable
            else {"qualified", "main-admitted"}
        )
    )
    validate_manifest(manifest, allowed_statuses=allowed_statuses)
    artifact_digest = str(manifest.get("artifactDigest") or "")
    if DIGEST.fullmatch(artifact_digest) is None:
        raise ValueError("artifactDigest is not an immutable digest")
    if artifact_digest != args.expected_artifact_digest:
        raise ValueError("artifact digest does not match Service Pipeline output")
    if args.expect_component_ready:
        if (
            manifest.get("status") != "component-ready"
            or manifest.get("releaseCompositionId") is not None
        ):
            raise ValueError("Service Pipeline evidence must be component-ready without releaseCompositionId")
        if args.expected_candidate:
            raise ValueError("component-ready verification must not expect a releaseCompositionId")
    else:
        candidate = str(manifest.get("releaseCompositionId") or "")
        if DIGEST.fullmatch(candidate) is None:
            raise ValueError("releaseCompositionId is not an immutable digest")
        if candidate != args.expected_candidate:
            raise ValueError("candidate digest does not match sealed candidate output")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError("release source is missing")
    if source.get("workflowRunId") != args.expected_workflow_run_id:
        raise ValueError("workflowRunId does not match Service Pipeline output")
    if GIT_SHA.fullmatch(args.expected_source_sha) is None or source.get(
        "gitSha"
    ) != args.expected_source_sha:
        raise ValueError("source git SHA does not match Service Pipeline output")
    if source.get("repository") != args.expected_repository:
        raise ValueError("source repository does not match the current repository")
    expected_ref = args.expected_release_ref.strip()
    discovered_ref = args.discovered_release_ref.strip()
    for label, value in (
        ("expected release ref", expected_ref),
        ("discovered release ref", discovered_ref),
    ):
        if value and IMMUTABLE_RELEASE_REF.fullmatch(value) is None:
            raise ValueError(f"{label} is not an immutable GHCR release ref")
    if expected_ref and discovered_ref and expected_ref != discovered_ref:
        raise ValueError("source-SHA discovery did not resolve the Service Pipeline OCI ref")
    if args.require_deployable:
        if manifest.get("status") != "main-admitted":
            raise ValueError("GATE_BLOCK: real Prod apply requires deployable evidence")
        receipts = manifest.get("environmentReceipts")
        missing_envs = sorted(
            {"alpha", "beta", "gamma"}
            - (set(receipts) if isinstance(receipts, dict) else set())
        )
        if missing_envs:
            raise ValueError(
                "GATE_BLOCK: environment receipts are missing: " + ", ".join(missing_envs)
            )
        if not manifest.get("providerEvidence"):
            raise ValueError("GATE_BLOCK: provider evidence is missing")


def main() -> int:
    args = parse_args()
    try:
        validate(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"verify_workflow_release_candidate: FAIL: {error}", file=sys.stderr)
        return 2
    print(
        "verify_workflow_release_candidate: OK: canonical candidate, workflow, "
        "source and OCI evidence are bound"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

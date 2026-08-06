#!/usr/bin/env python3
"""Consume one immutable released ReleaseEvidenceManifest as workflow truth."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod.fetch_mainline_release_artifact import fetch
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    RELEASE_CLOSURE_PATHS,
    validate_manifest,
    validate_manifest_files,
)
from quwoquan_ops.cli.prod.oci_supply_chain import verify_oci_supply_chain

IMMUTABLE_RELEASE_REF = re.compile(
    r"ghcr\.io/[a-z0-9._/-]+/release-artifact@sha256:[0-9a-f]{64}"
)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
CONSUMABLE_STATUSES = ("candidate-ready", "deployable", "released")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be a JSON object")
    return payload


def _descriptor(
    files: Mapping[str, object],
    label: str,
    *,
    artifact_root: Path,
) -> tuple[str, str]:
    descriptor = files.get(label)
    if not isinstance(descriptor, Mapping):
        raise TypeError(f"release closure descriptor is missing: {label}")
    path = str(descriptor.get("path") or "")
    digest = str(descriptor.get("digest") or "")
    if path != RELEASE_CLOSURE_PATHS[label] or DIGEST.fullmatch(digest) is None:
        raise ValueError(f"release closure descriptor is invalid: {label}")
    resolved_root = artifact_root.resolve(strict=True)
    candidate_path = resolved_root / path
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ValueError(f"release closure file is missing or unsafe: {label}")
    resolved_path = candidate_path.resolve(strict=True)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(
            f"release closure path escapes artifact root: {label}"
        ) from error
    return str(resolved_path), digest


def derive(
    *,
    artifact_root: Path,
    release_evidence_ref: str,
    repository: str,
    require_status: str,
    expected_candidate: str = "",
    expected_artifact_digest: str = "",
    expected_source_sha: str = "",
) -> dict[str, str]:
    """Validate and derive every workflow identity from one materialized manifest."""

    if IMMUTABLE_RELEASE_REF.fullmatch(release_evidence_ref) is None:
        raise ValueError(
            "release evidence ref must be one immutable GHCR release-artifact digest"
        )
    if REPOSITORY.fullmatch(repository) is None:
        raise ValueError("repository must be owner/name")
    if require_status not in CONSUMABLE_STATUSES:
        raise ValueError("required release status is not consumable")

    manifest_path = artifact_root / "manifest.json"
    manifest = _load_json(manifest_path, "ReleaseEvidenceManifest")
    validate_manifest(manifest, allowed_statuses={require_status})
    validate_manifest_files(artifact_root, manifest)

    candidate = str(manifest.get("candidateId") or "")
    artifact_digest = str(manifest.get("artifactDigest") or "")
    source = manifest.get("source")
    if (
        DIGEST.fullmatch(candidate) is None
        or DIGEST.fullmatch(artifact_digest) is None
        or not isinstance(source, Mapping)
    ):
        raise ValueError("released manifest identity is incomplete")
    source_sha = str(source.get("gitSha") or "")
    producer_workflow_run_id = str(source.get("workflowRunId") or "")
    if (
        GIT_SHA.fullmatch(source_sha) is None
        or source.get("repository") != repository
        or not producer_workflow_run_id
    ):
        raise ValueError("released manifest producer identity is invalid")

    for label, expected, actual in (
        ("candidateId", expected_candidate, candidate),
        ("artifactDigest", expected_artifact_digest, artifact_digest),
        ("source.gitSha", expected_source_sha, source_sha),
    ):
        if expected and expected != actual:
            raise ValueError(f"derived {label} does not match the caller expectation")

    test_evidence = manifest.get("testEvidence")
    evidence = (
        test_evidence.get("evidence") if isinstance(test_evidence, Mapping) else None
    )
    files = evidence.get("files") if isinstance(evidence, Mapping) else None
    if not isinstance(files, Mapping) or set(files) != set(RELEASE_CLOSURE_PATHS):
        raise ValueError("released manifest closure is incomplete")

    closure: dict[str, tuple[str, str]] = {
        label: _descriptor(files, label, artifact_root=artifact_root)
        for label in RELEASE_CLOSURE_PATHS
    }
    provider_descriptor = manifest.get("providerEvidence")
    if not isinstance(provider_descriptor, Mapping):
        raise TypeError("released manifest provider evidence is missing")
    provider_path = str(provider_descriptor.get("path") or "")
    provider_digest = str(provider_descriptor.get("digest") or "")
    if DIGEST.fullmatch(provider_digest) is None:
        raise ValueError("released manifest provider evidence digest is invalid")
    provider = _load_json(artifact_root / provider_path, "provider evidence")
    source_evidence = provider.get("sourceEvidence")
    if not isinstance(source_evidence, Mapping):
        raise TypeError("provider source evidence is missing")
    provider_ref = str(source_evidence.get("ref") or "")
    provider_source_digest = str(source_evidence.get("digest") or "")
    if (
        not provider_ref.startswith("oci://ghcr.io/")
        or not provider_ref.endswith("@" + provider_source_digest)
        or DIGEST.fullmatch(provider_source_digest) is None
    ):
        raise ValueError("provider source evidence is not immutable")

    outputs = {
        "release_evidence_ref": release_evidence_ref,
        "release_status": str(manifest["status"]),
        "manifest_path": str(manifest_path.resolve(strict=True)),
        "candidate_digest": candidate,
        "artifact_digest": artifact_digest,
        "source_git_sha": source_sha,
        "source_tree_digest": str(source.get("treeDigest") or ""),
        "producer_repository": str(source["repository"]),
        "producer_workflow_run_id": producer_workflow_run_id,
        "provider_evidence_path": str(
            (artifact_root.resolve(strict=True) / provider_path).resolve(strict=True)
        ),
        "provider_evidence_digest": provider_digest,
        "provider_source_ref": provider_ref,
        "provider_source_digest": provider_source_digest,
    }
    for label, (path, digest) in closure.items():
        key = label.replace("-", "_")
        outputs[f"{key}_path"] = path
        outputs[f"{key}_digest"] = digest
    return outputs


def consume(
    *,
    release_evidence_ref: str,
    repository: str,
    artifact_root: Path,
    require_status: str,
    expected_candidate: str = "",
    expected_artifact_digest: str = "",
    expected_source_sha: str = "",
) -> dict[str, str]:
    if IMMUTABLE_RELEASE_REF.fullmatch(release_evidence_ref) is None:
        raise ValueError(
            "release evidence ref must be one immutable GHCR release-artifact digest"
        )
    fetch(release_evidence_ref, artifact_root)
    outputs = derive(
        artifact_root=artifact_root,
        release_evidence_ref=release_evidence_ref,
        repository=repository,
        require_status=require_status,
        expected_candidate=expected_candidate,
        expected_artifact_digest=expected_artifact_digest,
        expected_source_sha=expected_source_sha,
    )
    verify_oci_supply_chain(
        release_evidence_ref,
        repository=repository,
        signer_workflow=f"{repository}/.github/workflows/deploy-prod-auto.yml",
        source_digest=outputs["source_git_sha"],
    )
    return outputs


def _write_github_output(path: Path, outputs: Mapping[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            if "\n" in value or "\r" in value:
                raise ValueError(f"derived output contains a newline: {key}")
            handle.write(f"{key}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--require-status",
        required=True,
        choices=CONSUMABLE_STATUSES,
    )
    parser.add_argument("--expected-candidate", default="")
    parser.add_argument("--expected-artifact-digest", default="")
    parser.add_argument("--expected-source-sha", default="")
    parser.add_argument("--github-output", default="", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        outputs = consume(
            release_evidence_ref=args.ref.strip(),
            repository=args.repository.strip(),
            artifact_root=args.output_dir.resolve(),
            require_status=args.require_status,
            expected_candidate=args.expected_candidate.strip(),
            expected_artifact_digest=args.expected_artifact_digest.strip(),
            expected_source_sha=args.expected_source_sha.strip(),
        )
        if args.github_output:
            _write_github_output(args.github_output, outputs)
    except (
        OSError,
        TypeError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"consume_released_release_evidence: GATE_BLOCK: {error}", file=sys.stderr
        )
        return 2
    print(
        json.dumps({"status": "passed", **outputs}, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

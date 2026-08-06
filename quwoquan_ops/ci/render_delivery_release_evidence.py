#!/usr/bin/env python3
"""Render immutable three-layer Delivery evidence from real job conclusions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.render_environment_release_receipt import (
    RELEASE_CLOSURE_PATHS,
    TEST_RELEASE_CLOSURE_LABELS,
    archive_exact_files,
    validate_release_closure_sources,
)


GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
TREE_DIGEST_PATTERN = re.compile(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
LAYERS = ("local_contract", "api_integration", "user_acceptance")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-git-sha", required=True)
    parser.add_argument("--source-tree-digest", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--job-result", action="append", default=[])
    parser.add_argument("--local-required", action="append", default=[])
    parser.add_argument("--api-required", action="append", default=[])
    parser.add_argument(
        "--user-acceptance-source",
        type=Path,
        help=(
            "Immutable prior three-layer evidence whose real user_acceptance layer "
            "is bound to the same source tree"
        ),
    )
    parser.add_argument(
        "--user-acceptance-transport-digest",
        help="Exact OCI digest carrying --user-acceptance-source",
    )
    parser.add_argument("--generated-at")
    parser.add_argument("--pilot-release-attestation", required=True, type=Path)
    parser.add_argument("--pilot-rollback-attestation", required=True, type=Path)
    parser.add_argument("--content-lifecycle-alpha", required=True, type=Path)
    parser.add_argument("--content-lifecycle-beta", required=True, type=Path)
    parser.add_argument("--content-lifecycle-gamma", required=True, type=Path)
    parser.add_argument("--local-env-green-matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def canonical_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def parse_job_results(items: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for item in items:
        name, separator, result = item.partition("=")
        name = name.strip()
        result = result.strip()
        if not separator or not name or not result:
            raise ValueError(f"expected NAME=RESULT, got {item!r}")
        if name in results:
            raise ValueError(f"duplicate Delivery job result: {name}")
        results[name] = result
    return results


def _validated_user_acceptance_layer(
    payload: dict[str, Any],
    *,
    expected_source: dict[str, str],
    transport_digest: str,
) -> dict[str, Any]:
    if DIGEST_PATTERN.fullmatch(transport_digest) is None:
        raise ValueError("user_acceptance evidence transport digest is not immutable")
    if payload.get("schema") != "qwq.three-layer-case-results":
        raise ValueError("user_acceptance source schema is not canonical")
    if payload.get("status") != "passed":
        raise ValueError("user_acceptance source is not passed")
    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("user_acceptance source identity is missing")
    for field in ("gitSha", "treeDigest", "repository"):
        if source.get(field) != expected_source[field]:
            raise ValueError(f"user_acceptance source {field} differs")
    if not str(source.get("workflowRunId") or "").strip():
        raise ValueError("user_acceptance source workflowRunId is missing")
    layers = payload.get("layers")
    layer = layers.get("user_acceptance") if isinstance(layers, dict) else None
    if not isinstance(layer, dict) or layer.get("status") != "passed":
        raise ValueError("user_acceptance source layer is not passed")
    jobs = layer.get("jobs")
    if not isinstance(jobs, dict) or not jobs or any(
        not isinstance(name, str) or not name or result != "success"
        for name, result in jobs.items()
    ):
        raise ValueError("user_acceptance source has no real successful jobs")
    generated_at = layer.get("generatedAt")
    layer_source = layer.get("source")
    candidate_material = layer.get("candidateMaterial")
    if not isinstance(candidate_material, dict) or set(candidate_material) != {
        "images",
        "configurationPackages",
        "applicationPackages",
        "contractGraphDigest",
    }:
        raise ValueError(
            "user_acceptance source is not bound to canonical candidate material"
        )
    imported_observation = {
        "source": layer_source,
        "generatedAt": generated_at,
        "jobs": jobs,
        "candidateMaterial": candidate_material,
    }
    imported_digest = layer.get("artifactDigest")
    if (
        not isinstance(layer_source, dict)
        or layer_source != source
        or not isinstance(generated_at, str)
        or canonical_digest(imported_observation) != imported_digest
    ):
        raise ValueError("user_acceptance source layer digest is invalid")
    observation = {
        **imported_observation,
        "sourceEvidence": {
            "transportDigest": transport_digest,
            "artifactDigest": imported_digest,
        },
    }
    return {
        "status": "passed",
        "artifactDigest": canonical_digest(observation),
        **observation,
    }


def render(
    *,
    source_git_sha: str,
    source_tree_digest: str,
    repository: str,
    workflow_run_id: str,
    job_results: dict[str, str],
    requirements: dict[str, list[str]],
    generated_at: str,
    user_acceptance_source: dict[str, Any] | None = None,
    user_acceptance_transport_digest: str = "",
    evidence_files: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    if GIT_SHA_PATTERN.fullmatch(source_git_sha) is None:
        raise ValueError("source Git SHA must be exact")
    if TREE_DIGEST_PATTERN.fullmatch(source_tree_digest) is None:
        raise ValueError("source tree digest must be immutable")
    if not repository.strip() or not workflow_run_id.strip():
        raise ValueError("repository and workflow run id are required")
    if set(requirements) != set(LAYERS):
        raise ValueError("test evidence must use exactly the three canonical layers")
    if not isinstance(evidence_files, dict) or set(evidence_files) != set(
        TEST_RELEASE_CLOSURE_LABELS
    ):
        raise ValueError("test evidence release closure file set is incomplete")
    for label, descriptor in evidence_files.items():
        expected_path = RELEASE_CLOSURE_PATHS[label]
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("path") != expected_path
            or DIGEST_PATTERN.fullmatch(str(descriptor.get("digest") or "")) is None
        ):
            raise ValueError(f"test evidence release closure is invalid: {label}")

    source = {
        "gitSha": source_git_sha,
        "treeDigest": source_tree_digest,
        "repository": repository,
        "workflowRunId": workflow_run_id,
    }
    layers: dict[str, Any] = {}
    for layer in LAYERS:
        if layer == "user_acceptance":
            if user_acceptance_source is None:
                raise ValueError(
                    "user_acceptance requires immutable real Remote evidence"
                )
            if requirements[layer]:
                raise ValueError(
                    "user_acceptance cannot combine imported evidence with job aliases"
                )
            layers[layer] = _validated_user_acceptance_layer(
                user_acceptance_source,
                expected_source=source,
                transport_digest=user_acceptance_transport_digest,
            )
            continue
        required = requirements[layer]
        if not required:
            raise ValueError(f"{layer} has no real required job evidence")
        missing = sorted(set(required) - set(job_results))
        if missing:
            raise ValueError(f"{layer} job results are missing: {missing}")
        failed = {
            name: job_results[name]
            for name in required
            if job_results[name] != "success"
        }
        if failed:
            raise ValueError(f"{layer} is not passed: {failed}")
        observation = {
            "source": source,
            "generatedAt": generated_at,
            "jobs": {name: job_results[name] for name in sorted(set(required))},
        }
        layers[layer] = {
            "status": "passed",
            "artifactDigest": canonical_digest(observation),
            **observation,
        }
    return {
        "schema": "qwq.three-layer-case-results",
        "status": "passed",
        "generatedAt": generated_at,
        "source": source,
        "layers": layers,
        "evidence": {"files": evidence_files},
    }


def main() -> int:
    args = parse_args()
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    try:
        if (args.user_acceptance_source is None) != (
            args.user_acceptance_transport_digest is None
        ):
            raise ValueError(
                "user_acceptance source and transport digest must be provided together"
            )
        user_acceptance_source: dict[str, Any] | None = None
        if args.user_acceptance_source is not None:
            loaded = json.loads(
                args.user_acceptance_source.read_text(encoding="utf-8")
            )
            if not isinstance(loaded, dict):
                raise ValueError("user_acceptance source must contain an object")
            user_acceptance_source = loaded
        closure_sources = {
            "pilot-release": args.pilot_release_attestation,
            "pilot-rollback": args.pilot_rollback_attestation,
            "content-lifecycle-alpha": args.content_lifecycle_alpha,
            "content-lifecycle-beta": args.content_lifecycle_beta,
            "content-lifecycle-gamma": args.content_lifecycle_gamma,
            "green-matrix": args.local_env_green_matrix,
        }
        validate_release_closure_sources(
            pilot_release_attestation=args.pilot_release_attestation,
            pilot_rollback_attestation=args.pilot_rollback_attestation,
            lifecycle_exits={
                "alpha": args.content_lifecycle_alpha,
                "beta": args.content_lifecycle_beta,
                "gamma": args.content_lifecycle_gamma,
            },
            green_matrix=args.local_env_green_matrix,
        )
        evidence_files = archive_exact_files(
            archive_root=args.output.parent,
            files={
                label: (path, RELEASE_CLOSURE_PATHS[label])
                for label, path in closure_sources.items()
            },
        )
        payload = render(
            source_git_sha=args.source_git_sha,
            source_tree_digest=args.source_tree_digest,
            repository=args.repository,
            workflow_run_id=args.workflow_run_id,
            job_results=parse_job_results(args.job_result),
            requirements={
                "local_contract": args.local_required,
                "api_integration": args.api_required,
                "user_acceptance": [],
            },
            generated_at=generated_at,
            user_acceptance_source=user_acceptance_source,
            user_acceptance_transport_digest=(
                args.user_acceptance_transport_digest or ""
            ),
            evidence_files=evidence_files,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_delivery_release_evidence: FAIL: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

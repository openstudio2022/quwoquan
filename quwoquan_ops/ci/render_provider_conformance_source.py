#!/usr/bin/env python3
"""Project repository Provider checks into the versionless release source contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.provider_conformance import (
    evidence_files,
    load_validate_and_derive,
    readiness_issues,
)
from quwoquan_ops.cli.lib.output_paths import output_root


SCHEMA = "provider-conformance-source"
FIELDS = frozenset(
    {
        "schema",
        "evidenceCount",
        "sourceEvidence",
        "sourceCoverageIssues",
        "readiness",
        "issues",
    }
)
IMMUTABLE_REF = re.compile(r"oci://ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REPORT_FIELDS = frozenset(
    {
        "schema",
        "evidenceCount",
        "executableSourceCount",
        "sourceCoverageIssues",
        "readiness",
        "issues",
    }
)
READINESS_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
CAPABILITY_READINESS_FIELDS = frozenset(
    {
        "state",
        "required",
        "adapter_id",
        "local_substitute",
        "adapter_preflight_ready",
        "adapter_ready",
        "evidence_ready",
        "matrix_selected_adapters_ready",
        "capability_ready",
    }
)
PROD_CAPABILITY_READINESS_FIELDS = (
    CAPABILITY_READINESS_FIELDS | {"prod_remote_release_ready"}
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-environment", default="prod", choices=("prod",))
    parser.add_argument("--source-evidence-ref", required=True)
    parser.add_argument("--source-evidence-digest", required=True)
    parser.add_argument("--archive-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _validate_readiness(value: object) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(value, Mapping) or set(value) != READINESS_ENVIRONMENTS:
        raise ValueError("Provider readiness must contain exactly alpha, beta, gamma and prod")
    canonical: dict[str, dict[str, dict[str, Any]]] = {}
    for environment in sorted(READINESS_ENVIRONMENTS):
        capabilities = value.get(environment)
        if not isinstance(capabilities, Mapping) or not capabilities:
            raise ValueError(f"Provider readiness.{environment} must be non-empty")
        expected_fields = (
            PROD_CAPABILITY_READINESS_FIELDS
            if environment == "prod"
            else CAPABILITY_READINESS_FIELDS
        )
        environment_result: dict[str, dict[str, Any]] = {}
        for capability_id, item in capabilities.items():
            if (
                not isinstance(capability_id, str)
                or not capability_id
                or not isinstance(item, Mapping)
                or set(item) != expected_fields
            ):
                raise ValueError(
                    f"Provider readiness.{environment} capability shape is not canonical"
                )
            if (
                item.get("state") != "enabled"
                or not isinstance(item.get("adapter_id"), str)
                or not item["adapter_id"]
                or not all(
                    isinstance(item.get(field), bool)
                    for field in expected_fields - {"state", "adapter_id"}
                )
            ):
                raise ValueError(
                    f"Provider readiness.{environment}.{capability_id} is malformed"
                )
            environment_result[capability_id] = dict(item)
        canonical[environment] = environment_result
    return canonical


def validate_source(payload: Mapping[str, Any]) -> None:
    """Reject every non-canonical or historical Provider source shape."""
    if set(payload) != FIELDS or payload.get("schema") != SCHEMA:
        raise ValueError("Provider conformance source fields are not canonical")
    if not isinstance(payload.get("evidenceCount"), int) or payload["evidenceCount"] <= 0:
        raise ValueError("real Provider conformance evidenceCount must be positive")
    source = payload.get("sourceEvidence")
    if not isinstance(source, Mapping) or set(source) != {"ref", "digest", "files"}:
        raise ValueError("Provider sourceEvidence shape is not canonical")
    ref = str(source.get("ref") or "")
    digest = str(source.get("digest") or "")
    files = source.get("files")
    if (
        IMMUTABLE_REF.fullmatch(ref) is None
        or DIGEST.fullmatch(digest) is None
        or not ref.endswith("@" + digest)
        or not isinstance(files, Mapping)
        or len(files) != payload["evidenceCount"]
        or not files
        or any(
            not isinstance(path, str)
            or not path.startswith("evidence/raw/provider/")
            or DIGEST.fullmatch(str(file_digest or "")) is None
            for path, file_digest in files.items()
        )
    ):
        raise ValueError("Provider sourceEvidence is not exact and digest-bound")
    for field in ("issues", "sourceCoverageIssues"):
        issues = payload.get(field)
        if not isinstance(issues, list) or issues:
            raise ValueError(f"Provider conformance {field} is not empty")
    _validate_readiness(payload.get("readiness"))


def render(
    report: Mapping[str, Any],
    *,
    validation_issues: list[str],
    environment: str,
    source_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the only source shape accepted by release candidate sealing."""
    if set(report) != REPORT_FIELDS or report.get("schema") != "provider-conformance-readiness":
        raise ValueError("Provider readiness report fields are not canonical")
    evidence_count = report.get("evidenceCount")
    source_coverage = report.get("sourceCoverageIssues")
    readiness = _validate_readiness(report.get("readiness"))
    report_issues = report.get("issues")
    if not isinstance(report_issues, list):
        raise ValueError("Provider readiness issues must be a list")
    issues = [
        *validation_issues,
        *(str(issue) for issue in report_issues),
        *readiness_issues(report, environment=environment),
    ]
    if not isinstance(evidence_count, int) or evidence_count <= 0:
        raise ValueError("real Provider conformance evidenceCount must be positive")
    if not isinstance(source_coverage, list):
        raise ValueError("Provider sourceCoverageIssues must be a list")
    if issues:
        raise ValueError(
            "real Provider conformance evidence is incomplete: " + "; ".join(issues)
        )
    payload = {
        "schema": SCHEMA,
        "evidenceCount": evidence_count,
        "sourceEvidence": dict(source_evidence or {}),
        "sourceCoverageIssues": list(source_coverage),
        "readiness": dict(readiness),
        "issues": [],
    }
    validate_source(payload)
    return payload


def _archive_raw_evidence(
    *,
    source_root: Path,
    paths: list[Path],
    archive_dir: Path,
) -> dict[str, str]:
    archive_root = archive_dir.expanduser().resolve()
    source_paths: list[Path] = []
    for path in paths:
        try:
            path.resolve().relative_to(archive_root)
        except ValueError:
            source_paths.append(path)
        else:
            # A retried CI job may already contain its previous disposable
            # archive. It is never a Provider source and must not recursively
            # attest itself.
            continue
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(parents=True)
    files: dict[str, str] = {}
    resolved_root = source_root.resolve()
    for path in sorted(source_paths):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Provider raw evidence is not a regular file: {path}")
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError("Provider raw evidence escapes the output root") from error
        destination = archive_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, destination)
        files[f"evidence/raw/provider/{relative.as_posix()}"] = (
            "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
        )
    return files


def main() -> int:
    args = parse_args()
    try:
        evidence_root = output_root()
        report, issues = load_validate_and_derive(root=evidence_root)
        raw_files = _archive_raw_evidence(
            source_root=evidence_root,
            paths=evidence_files(evidence_root),
            archive_dir=args.archive_dir,
        )
        source_ref = str(args.source_evidence_ref).strip()
        if source_ref.startswith("ghcr.io/"):
            source_ref = "oci://" + source_ref
        payload = render(
            report,
            validation_issues=list(issues),
            environment=args.require_environment,
            source_evidence={
                "ref": source_ref,
                "digest": args.source_evidence_digest,
                "files": raw_files,
            },
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_provider_conformance_source: GATE_BLOCK: {error}")
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

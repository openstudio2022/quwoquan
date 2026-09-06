"""Provider readiness 的 canonical 重推导与 manifest 绑定校验（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib import external_provider_governance, provider_conformance
from quwoquan_ops.ci.release_evidence_reader import (
    DIGEST_PATTERN,
    sha256_file,
)

from quwoquan_ops.cli.lib.environment_stability_final_acceptance.model import (
    LoadedReceipt,
    PROVIDER_NONPROD_ENVIRONMENTS,
    ProviderReadinessVerifier,
    VerifiedAuthority,
    _Evaluation,
)
from quwoquan_ops.cli.lib.environment_stability_final_acceptance.receipt_io import (
    _canonical_digest,
    _timestamp,
)


def verify_canonical_provider_readiness(
    artifact_root: Path,
    payload: Mapping[str, Any],
    evidence: list[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> VerifiedAuthority:
    """Re-derive manifest-bound Provider readiness from canonical governance."""

    compiled, governance_issues = external_provider_governance.load_and_compile()
    if governance_issues:
        raise ValueError(
            "Provider governance is invalid: "
            + "; ".join(issue.render() for issue in governance_issues)
        )
    source_catalog, source_issues = provider_conformance.discover_test_sources()
    if source_issues:
        raise ValueError("Provider source discovery is invalid: " + "; ".join(source_issues))
    validation_issues = provider_conformance.validate_evidence(
        evidence,
        registry=external_provider_governance.load_registry(),
        root=artifact_root / "evidence/raw/provider",
        current_commit=str(manifest["source"]["gitSha"]),
        compiled=compiled,
        source_catalog=source_catalog,
    )
    if validation_issues:
        raise ValueError(
            "Provider raw evidence is invalid: " + "; ".join(validation_issues)
        )
    coverage_issues = provider_conformance.source_coverage_issues(
        compiled=compiled,
        sources=source_catalog,
    )
    if coverage_issues:
        raise ValueError(
            "Provider source coverage is incomplete: " + "; ".join(coverage_issues)
        )
    derived = provider_conformance.derive_readiness(
        compiled=compiled,
        evidence=evidence,
    )
    derived_report = {
        "schema": "provider-conformance-readiness",
        "evidenceCount": len(evidence),
        "sourceCoverageIssues": coverage_issues,
        "readiness": derived,
        "issues": [],
    }
    readiness_errors = [
        issue
        for environment in (*PROVIDER_NONPROD_ENVIRONMENTS, "prod")
        for issue in provider_conformance.readiness_issues(
            derived_report,
            environment=environment,
        )
    ]
    if readiness_errors:
        raise ValueError(
            "Provider derived readiness is not promotable: "
            + "; ".join(readiness_errors)
        )
    declared = payload.get("readiness")
    if not isinstance(declared, Mapping):
        raise TypeError("Provider readiness payload is missing")
    for environment in (*PROVIDER_NONPROD_ENVIRONMENTS, "prod"):
        expected = derived.get(environment)
        actual = declared.get(environment)
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            raise TypeError(f"Provider readiness.{environment} is missing")
        for capability_id, expected_item in expected.items():
            if not expected_item.get("required"):
                continue
            actual_item = actual.get(capability_id)
            if (
                not isinstance(actual_item, Mapping)
                or actual_item.get("required") is not True
                or actual_item.get("capability_ready")
                != expected_item.get("capability_ready")
                or actual_item.get("capability_ready") is not True
            ):
                raise ValueError(
                    f"Provider readiness.{environment}.{capability_id} drifted"
                )
    provider_path = artifact_root / str(manifest["providerEvidence"]["path"])
    return VerifiedAuthority(
        authority="canonical-provider-conformance",
        subject_digest=sha256_file(provider_path),
        verification_digest=_canonical_digest(
            {
                "compiled": compiled,
                "readiness": derived,
                "evidenceDigests": sorted(
                    sha256_file(Path(str(item["_source"]))) for item in evidence
                ),
            }
        ),
        claims=frozenset({"provider_readiness", "all_required_cells"}),
    )


def _provider_layers(
    evaluation: _Evaluation,
    *,
    artifact_root: Path,
    manifest: Mapping[str, Any],
    now: datetime,
    max_age_seconds: int,
    verifier: ProviderReadinessVerifier,
) -> None:
    provider = manifest.get("providerEvidence")
    if not isinstance(provider, Mapping):
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "artifact.provider",
            "manifest provider evidence descriptor is missing",
        )
        return
    try:
        provider_path = artifact_root / str(provider["path"])
        payload = json.loads(provider_path.read_text(encoding="utf-8"))
        files = payload["sourceEvidence"]["files"]
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        evaluation.block(
            "ARTIFACT_CLOSURE_INVALID",
            "artifact.provider",
            f"provider evidence closure is unreadable: {exc}",
        )
        return
    if not isinstance(payload, dict) or not isinstance(files, Mapping):
        evaluation.block(
            "SCHEMA_MISMATCH",
            "artifact.provider",
            "Provider readiness payload or sourceEvidence.files is not canonical",
        )
        return
    compiled, governance_issues = external_provider_governance.load_and_compile()
    capability_ids = frozenset(
        provider_conformance.provider_conformance_capability_ids(compiled)
    )
    if governance_issues or not capability_ids:
        evaluation.block(
            "STATUS_NOT_PASSED",
            "artifact.provider",
            "canonical Provider governance must define a non-empty required capability set",
        )
        return
    expected_cells = set(
        provider_conformance.expected_required_cell_keys(compiled)
    )
    expected_cell_count = len(expected_cells)
    evidence: list[Mapping[str, Any]] = []
    observed_cells: list[tuple[str, str, str]] = []
    for relative in files:
        try:
            raw_path = artifact_root / str(relative)
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            evaluation.block(
                "ARTIFACT_CLOSURE_INVALID",
                "artifact.provider",
                f"provider raw evidence is unreadable: {exc}",
            )
            continue
        if not isinstance(raw, dict):
            evaluation.block(
                "SCHEMA_MISMATCH",
                "artifact.provider",
                "provider raw evidence root must be an object",
            )
            continue
        layer = str(raw.get("testLayer") or "")
        environment = str(raw.get("environment") or "")
        capability_id = str(raw.get("capabilityId") or "")
        cell = (capability_id, environment, layer)
        if (
            raw.get("schema") != "provider-conformance-evidence"
            or raw.get("status") != "passed"
            or raw.get("nonPromotable") is not False
            or raw.get("sourceTreeState") != "clean"
            or raw.get("commitReview") != "reviewed"
            or raw.get("candidateStatus") != "active_immutable"
            or raw.get("attestationAuthority") != "ci"
            or raw.get("commit") != manifest["source"]["gitSha"]
            or raw.get("contractGraphDigest") != manifest["contractGraphDigest"]
            or cell not in expected_cells
        ):
            evaluation.block(
                "STATUS_NOT_PASSED",
                "artifact.provider",
                f"provider raw evidence is not promotable: {relative}",
            )
            continue
        raw["_source"] = raw_path
        evidence.append(raw)
        observed_cells.append(cell)
        raw_receipt = LoadedReceipt(
            "artifact.provider",
            raw_path,
            raw,
            sha256_file(raw_path),
        )
        _timestamp(
            evaluation,
            raw_receipt,
            ("executedAt",),
            now=now,
            max_age_seconds=max_age_seconds,
        )
    duplicate_cells = len(observed_cells) != len(set(observed_cells))
    if duplicate_cells or set(observed_cells) != expected_cells:
        evaluation.block(
            "STATUS_NOT_PASSED",
            "artifact.provider",
            "manifest-bound Provider evidence must contain exactly the compiled "
            f"{expected_cell_count} unique required cells",
        )
    readiness = payload.get("readiness")
    readiness_valid = (
        payload.get("issues") == []
        and payload.get("sourceCoverageIssues") == []
        and payload.get("evidenceCount") == expected_cell_count
        and len(files) == expected_cell_count
        and isinstance(readiness, Mapping)
        and set(readiness) == {"alpha", "beta", "gamma", "prod"}
    )
    if readiness_valid:
        for environment in (*PROVIDER_NONPROD_ENVIRONMENTS, "prod"):
            environment_readiness = readiness.get(environment)
            if (
                not isinstance(environment_readiness, Mapping)
                or set(environment_readiness) != capability_ids
                or any(
                    not isinstance(item, Mapping)
                    or item.get("required") is not True
                    or item.get("capability_ready") is not True
                    for item in environment_readiness.values()
                )
            ):
                readiness_valid = False
                break
    if not readiness_valid:
        evaluation.block(
            "STATUS_NOT_PASSED",
            "artifact.provider",
            "manifest-bound Provider readiness is incomplete or reports issues",
        )
    if duplicate_cells or set(observed_cells) != expected_cells or not readiness_valid:
        return
    try:
        verified = verifier(artifact_root, payload, evidence, manifest)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            "artifact.provider",
            f"canonical Provider readiness verification failed: {exc}",
        )
        return
    provider_digest = sha256_file(provider_path)
    if (
        verified.authority != "canonical-provider-conformance"
        or verified.subject_digest != provider_digest
        or DIGEST_PATTERN.fullmatch(verified.verification_digest) is None
        or not {"provider_readiness", "all_required_cells"}.issubset(
            verified.claims
        )
    ):
        evaluation.block(
            "UNVERIFIABLE_AUTHORITY",
            "artifact.provider",
            "Provider verifier did not bind canonical readiness and all compiled cells",
        )
        return
    evaluation.authority["artifact.provider"] = verified

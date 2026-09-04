"""Owner and review evidence admission for local readiness."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import evidence_runner
from lib.agent_governance_contract import (
    contract_schema_version,
    validate_declared_fields,
    validate_feature_context_manifest,
    validate_required_fields,
)
from lib.candidate_evidence import CandidateEvidenceError, validate_candidate_ref
from lib.evidence_fingerprint import (
    EvidenceFingerprintError,
    normalize_repo_relative_path,
    validate_evidence_fingerprint,
)
from lib.feature_context_fingerprint import (
    validate_content_addressed_ref,
    validate_current_feature_context_fingerprint,
)

from . import core as _core


def owner_manifest_assets(owner_manifest: Path | None, *, repo_root: Path, candidate_evidence: Path | None = None) -> tuple[list[str], dict[str, Any] | None]:
    assets = [] if repo_root.resolve() != _core.ROOT.resolve() else [
        "quwoquan_ops/policies/local_readiness_contract.yaml",
        "quwoquan_ops/cli/lib/evidence_fingerprint.py",
        "quwoquan_ops/cli/lib/local_readiness/core.py",
        "quwoquan_ops/cli/lib/local_readiness/admission.py",
        "quwoquan_ops/cli/lib/local_readiness/source_inputs.py",
        "quwoquan_ops/ci/local_readiness_planner.py",
        "quwoquan_ops/ci/detect_ci_impacted_scopes.py",
    ]
    manifest_value: dict[str, Any] | None = None
    if owner_manifest is not None:
        resolved = owner_manifest.resolve()
        try:
            relative = str(resolved.relative_to(repo_root.resolve()))
        except ValueError as exc:
            raise _core.LocalReadinessError("owner manifest 必须位于仓库内") from exc
        try:
            raw_bytes = resolved.read_bytes()
            validate_content_addressed_ref(
                relative, raw_bytes=raw_bytes, repo_root=repo_root
            )
            value = json.loads(raw_bytes.decode("utf-8"))
            if not isinstance(value, dict):
                raise TypeError("manifest 必须为 object")
            validate_feature_context_manifest(value)
            validate_current_feature_context_fingerprint(value, repo_root=repo_root)
        except (OSError, TypeError, ValueError, EvidenceFingerprintError, json.JSONDecodeError) as exc:
            raise _core.LocalReadinessError(f"owner manifest 非 current canonical manifest: {exc}") from exc
        manifest_value = value
        assets.append(relative)
        if candidate_evidence is not None:
            try:
                candidate_relative = normalize_repo_relative_path(candidate_evidence.as_posix(), repo_root)
                validate_candidate_ref(candidate_relative, repo_root=repo_root, expected_owner_identity_ref=relative)
            except (CandidateEvidenceError, ValueError) as exc:
                raise _core.LocalReadinessError(f"candidate evidence 非 current canonical candidate: {exc}") from exc
            assets.append(candidate_relative)
    elif candidate_evidence is not None:
        raise _core.LocalReadinessError("candidate evidence 要求 owner identity predecessor")
    existing = [item for item in assets if (repo_root / item).exists()]
    return existing, manifest_value


def load_review_inputs(
    review_consolidation: Path | None,
    required_evidence: list[Path] | None,
    *,
    repo_root: Path,
    required: bool,
    allow_missing: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    evidence_paths = list(required_evidence or [])
    if required and (review_consolidation is None or not evidence_paths):
        if allow_missing:
            return [], {"required": True, "consolidation": None, "evidence": []}
        raise _core.LocalReadinessError("scope/release readiness 要求 Review consolidation PASS 与 required evidence receipts")
    if review_consolidation is None and not evidence_paths:
        return [], {"required": required, "consolidation": None, "evidence": []}
    if review_consolidation is None:
        raise _core.LocalReadinessError("required evidence 缺 Review consolidation")
    paths = [review_consolidation, *evidence_paths]
    relatives: list[str] = []
    exact_bytes: list[bytes] = []
    repo_absolute = _core._canonical_absolute(repo_root)
    for item in paths:
        absolute = _core._canonical_absolute(
            item if item.is_absolute() else repo_root / item
        )
        try:
            relatives.append(absolute.relative_to(repo_absolute).as_posix())
        except ValueError as exc:
            raise _core.LocalReadinessError("Review/evidence receipt 必须位于仓库或 .qwq_output 内") from exc
        exact_bytes.append(_core._read_regular_bytes(absolute, label="Review/evidence receipt"))
    try:
        consolidation = json.loads(exact_bytes[0].decode("utf-8"))
        validate_required_fields(consolidation, "review_consolidation")
        validate_declared_fields(consolidation, "review_consolidation", "required_fields")
        if consolidation.get("schema_version") != contract_schema_version("review_consolidation"):
            raise ValueError("Review consolidation schema_version 非法")
        if consolidation.get("terminal", {}).get("status") != "PASS":
            raise ValueError("Review consolidation terminal 非 PASS")
        if any(item.get("severity") == "GATE_BLOCK" for item in consolidation.get("findings", [])):
            raise ValueError("Review consolidation 含 GATE_BLOCK finding")
        receipts = [json.loads(raw.decode("utf-8")) for raw in exact_bytes[1:]]
        for receipt in receipts:
            validate_declared_fields(receipt, "named_evidence_receipt", "required_fields")
            evidence_runner.validate_named_evidence_receipt(receipt)
            if receipt.get("schema_version") != contract_schema_version("named_evidence_receipt"):
                raise ValueError("required named evidence schema_version 非法")
            if receipt.get("terminal") != {"status": "PASS", "code": "EVIDENCE.PASSED", "failed_evidence": None}:
                raise ValueError("required named evidence 非 PASS")
            required_results = [item for item in receipt.get("evidence", []) if item.get("required")]
            if not required_results:
                raise ValueError("required named evidence receipt 未包含 required check")
            if any(item.get("exit_code") != 0 for item in required_results):
                raise ValueError("required named evidence check 非零退出")
        consolidation_evidence = consolidation.get("evidence_identities") or []
        if len(consolidation_evidence) != len(receipts):
            raise ValueError("Review consolidation evidence identities 与 supplied receipts 数量不一致")
        supplied_identities: list[dict[str, Any]] = []
        for relative, raw, receipt in zip(relatives[1:], exact_bytes[1:], receipts):
            execution = validate_evidence_fingerprint(receipt["execution_fingerprint"])
            result = validate_evidence_fingerprint(receipt["result_fingerprint"])
            supplied_identities.append(
                {
                    "receipt_ref": relative,
                    "canonical_bytes_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "run_id": receipt["run_id"],
                    "generation_id": receipt["generation_id"],
                    "evidence_class": receipt["evidence_class"],
                    "admission_eligible": receipt["admission_eligible"],
                    "plan_fingerprint_ref": receipt["plan_fingerprint_ref"],
                    "plan_fingerprint_digest": receipt["plan_fingerprint_digest"],
                    "execution_fingerprint_ref": execution["ref"],
                    "execution_fingerprint_digest": execution["digest"],
                    "result_fingerprint_ref": result["ref"],
                    "result_fingerprint_digest": result["digest"],
                    "finished_at": receipt["finished_at"],
                }
            )
        if consolidation_evidence != supplied_identities:
            raise ValueError("Review consolidation 未绑定提供的 required evidence exact identities")
        if any(
            identity["plan_fingerprint_ref"] != consolidation.get("plan_fingerprint_ref")
            or identity["plan_fingerprint_digest"] != consolidation.get("plan_fingerprint_digest")
            for identity in supplied_identities
        ):
            raise ValueError("Review consolidation 与 evidence plan identity 不一致")
        if required:
            for receipt in receipts:
                try:
                    evidence_runner.require_admission_eligible(
                        receipt, label="scope/release required named evidence"
                    )
                except evidence_runner.EvidenceRunnerError as exc:
                    raise ValueError(str(exc)) from exc
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise _core.LocalReadinessError(f"Review admission receipt 非法: {exc}") from exc
    return relatives, {
        "required": required,
        "consolidation": "sha256:" + hashlib.sha256(exact_bytes[0]).hexdigest(),
        "evidence": [
            "sha256:" + hashlib.sha256(raw).hexdigest()
            for raw in exact_bytes[1:]
        ],
    }

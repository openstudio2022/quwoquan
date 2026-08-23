"""WorkRequest normalization and typed preview contract."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.carrier_execution_policy import (
    POLICY_PATH as CARRIER_POLICY_PATH,
    carrier_policy_digest,
)
from content.execution.campaign.external_inputs import bind_external_input_refs
from content.execution.campaign.lane import CAMPAIGN_CARRIERS, normalize_workloads
from content.execution.campaign.scale import campaign_workload_targets
from content.execution.workspace import entity_catalog_digest
from content.source.research.scale_source_pool import (
    validate_scale_source_pool_evidence,
)
from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import (
    content_source_revision,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from governance.coverage.distribution import (
    POLICY_PATH as DISTRIBUTION_POLICY_PATH,
    load_content_distribution_policy,
)

_RESULT_SCHEMA = "quwoquan_data.work_request_compile_result"
_MAX_DOCUMENT_BYTES = 256 * 1024
# Demand facts (vertical, scope, topic refs, lifecycle, workloads) are owned by
# the confirmed pre-acquisition handoff; independent caller inputs for them are
# rejected as unknown keys instead of silently merged.
_ALLOWED_INPUTS = frozenset(
    {
        "intentText",
        "mode",
        "targetNames",
        "sourceProviders",
        "semanticSelectionId",
        "semanticPreflightReceiptRef",
        "capacityCalibrationReceiptRef",
        "preAcquisitionHandoffRef",
        "scaleSourcePoolPlanRef",
        "sourcePoolEvidenceRootRef",
        "externalInputRefsByCarrier",
        "acquisitionRootRef",
        "predecessorExecutionIdsByCarrier",
        "predecessorReconciliationReceiptRef",
        "promotionReceiptRef",
    }
)
_REQUIRED_INPUTS = (
    "mode",
    "preAcquisitionHandoffRef",
    "scaleSourcePoolPlanRef",
    "sourcePoolEvidenceRootRef",
)


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise FileNotFoundError(f"dependency directory is missing: {root}")
    rows: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append(
            {
                "ref": path.relative_to(root).as_posix(),
                "digest": _file_digest(path),
            }
        )
    if not rows:
        raise ValueError(f"dependency directory is empty: {root}")
    return _digest(rows)


def _document_size(document: Mapping[str, Any]) -> int:
    return len(
        (
            json.dumps(document, ensure_ascii=False, indent=2)
            + "\n"
        ).encode("utf-8")
    )


def _validated_result(document: dict[str, Any]) -> dict[str, Any]:
    assert_valid(document, "execution", "work_request_compile_result")
    if _document_size(document) > _MAX_DOCUMENT_BYTES:
        raise ValueError("DATA.WORK_REQUEST.DOCUMENT_TOO_LARGE: compile result")
    return document


def _raw_digest(intent: Mapping[str, Any]) -> str:
    return _digest(
        {
            str(key): value
            for key, value in intent.items()
            if str(key) != "intentText"
        }
    )


def _needs_input(
    intent: Mapping[str, Any], fields: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    return _validated_result(
        {
            "schema": _RESULT_SCHEMA,
            "outcome": "needs_input",
            "requestDigest": _raw_digest(intent),
            "missingFields": sorted(set(fields)),
        }
    )


def _blocked(
    request_digest: str,
    *,
    code: str,
    message: str,
    attributes: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    return _validated_result(
        {
            "schema": _RESULT_SCHEMA,
            "outcome": "blocked",
            "requestDigest": request_digest,
            "error": {
                "code": code,
                "message": message,
                "attributes": {
                    str(key): str(value)
                    for key, value in (attributes or {}).items()
                },
            },
        }
    )


def _path(value: object) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError("dependency ref is empty")
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.parts and candidate.parts[0] == "data":
        return (paths.OUTPUT_ROOT / candidate).resolve()
    if candidate.parts and candidate.parts[0] in {
        "quwoquan_data",
        ".qwq_output",
    }:
        return (paths.REPO_ROOT / candidate).resolve()
    return candidate.resolve()


def _canonical_ref(path: Path) -> str:
    resolved = path.resolve()
    for root in (paths.OUTPUT_ROOT.resolve(), paths.REPO_ROOT.resolve()):
        if resolved == root:
            return "."
        if root in resolved.parents:
            return resolved.relative_to(root).as_posix()
    raise ValueError(f"dependency is outside governed roots: {resolved}")


def _normalized_workload(
    raw_workloads: Mapping[str, int],
) -> tuple[str, str, dict[str, int]]:
    if not isinstance(raw_workloads, Mapping) or not raw_workloads:
        raise ValueError("handoff workloadTargets must be a non-empty carrier mapping")
    workloads = normalize_workloads(raw_workloads)
    policy = load_content_distribution_policy()
    for milestone in policy.governed_scales():
        if tuple(workloads) == CAMPAIGN_CARRIERS and workloads == campaign_workload_targets(
            milestone
        ):
            return milestone, "milestone_preset", workloads
    return f"M{max(workloads.values())}", "explicit", workloads


def _dependency_bindings(
    intent: Mapping[str, Any],
    *,
    scale: str,
    workload_mode: str,
    workloads: Mapping[str, int],
    vertical: str,
    region_ref: str,
) -> dict[str, Any]:
    repo_root = paths.REPO_ROOT.resolve()
    source = current_source_definition_snapshot(repo_root=repo_root).to_document()
    execution_bundle = current_execution_bundle_identity(
        repo_root=repo_root
    ).to_document()
    entity_root = (
        repo_root / "quwoquan_data" / "reference" / vertical / "entities" / region_ref
    )
    if not entity_root.is_dir():
        raise ValueError(f"unknown region reference: {region_ref}")
    entity_digest = entity_catalog_digest(
        entity_root.relative_to(repo_root).as_posix()
    )
    source_revision = content_source_revision(
        source_digest=str(source["digest"]),
        entity_catalog_digest=entity_digest,
    )
    plan_path = _path(intent["scaleSourcePoolPlanRef"])
    evidence_root = _path(intent["sourcePoolEvidenceRootRef"])
    plan = read_json(plan_path)
    if not isinstance(plan, Mapping):
        raise TypeError("SourcePool plan must be an object")
    validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)
    expected_target = "WORKLOAD" if workload_mode == "explicit" else scale
    expected_identity = (
        str(source["digest"]),
        entity_digest,
    )
    if (
        plan.get("targetScale") != expected_target
        or plan.get("workloadMode") != workload_mode
        or plan.get("activeCarriers") != list(workloads)
        or plan.get("workloadTargets") != dict(workloads)
        or plan.get("sourceRevision") != source_revision
        or (
            str(plan.get("sourceDigest") or ""),
            str(plan.get("entityCatalogDigest") or ""),
        )
        != expected_identity
    ):
        raise ValueError("SourcePool identity or workload binding drift")
    file_refs = {
        "preAcquisitionHandoffRef": _path(intent["preAcquisitionHandoffRef"]),
        "scaleSourcePoolPlanRef": plan_path,
    }
    # bounded M1–M10 请求不携带 calibration receipt，授权由 envelope builder
    # 的互斥 executionAuthority 判定；governed 请求仍逐字节绑定 receipt。
    calibration_ref = str(intent.get("capacityCalibrationReceiptRef") or "").strip()
    if calibration_ref:
        file_refs["capacityCalibrationReceiptRef"] = _path(calibration_ref)
    semantic_ref = str(intent.get("semanticPreflightReceiptRef") or "").strip()
    if semantic_ref:
        file_refs["semanticPreflightReceiptRef"] = _path(semantic_ref)
    reconciliation_ref = str(
        intent.get("predecessorReconciliationReceiptRef") or ""
    ).strip()
    if reconciliation_ref:
        file_refs["predecessorReconciliationReceiptRef"] = _path(
            reconciliation_ref
        )
    promotion_ref = str(intent.get("promotionReceiptRef") or "").strip()
    if promotion_ref:
        file_refs["promotionReceiptRef"] = _path(promotion_ref)
    for label, path in file_refs.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label} is missing: {path}")
    dependency_rows = {
        label: {"ref": _canonical_ref(path), "digest": _file_digest(path)}
        for label, path in file_refs.items()
    }
    dependency_rows["sourceDefinition"] = {
        "ref": "quwoquan_data/source-definition",
        "digest": str(source["digest"]),
    }
    dependency_rows["executionBundle"] = {
        "ref": "quwoquan_data/execution-bundle",
        "digest": str(execution_bundle["digest"]),
    }
    dependency_rows["sourcePoolEvidenceRootRef"] = {
        "ref": _canonical_ref(evidence_root),
        "digest": _tree_digest(evidence_root),
    }
    dependency_rows["carrierExecutionPolicy"] = {
        "ref": CARRIER_POLICY_PATH.relative_to(repo_root).as_posix(),
        "digest": carrier_policy_digest(),
    }
    dependency_rows["contentDistributionPolicy"] = {
        "ref": DISTRIBUTION_POLICY_PATH.relative_to(repo_root).as_posix(),
        "digest": _file_digest(DISTRIBUTION_POLICY_PATH),
    }
    acquisition_root_text = str(intent.get("acquisitionRootRef") or "").strip()
    acquisition_root = (
        _path(acquisition_root_text)
        if acquisition_root_text
        else paths.SOURCE_ACQUISITION_ROOT.resolve()
    )
    external_inputs = intent.get("externalInputRefsByCarrier") or {}
    if not isinstance(external_inputs, Mapping):
        raise TypeError("externalInputRefsByCarrier must be a carrier mapping")
    for carrier in workloads:
        declarations = external_inputs.get(carrier) or []
        if not isinstance(declarations, list):
            raise TypeError(
                f"externalInputRefsByCarrier.{carrier} must be a list"
            )
        frozen = bind_external_input_refs(
            carrier,
            declarations,
            acquisition_root=acquisition_root,
            source_revision=source_revision,
            source_digest=str(source["digest"]),
            entity_catalog_digest=entity_digest,
        )
        if frozen:
            dependency_rows[f"externalInputs:{carrier}"] = {
                "ref": f"external-inputs/{carrier}",
                "digest": _digest(frozen),
            }
    return {
        "source": source,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": entity_digest,
        "sourcePool": dict(plan),
        "dependencies": dependency_rows,
        "dependencySetDigest": _digest(dependency_rows),
    }


def _normalize(intent: Mapping[str, Any]) -> dict[str, Any]:
    from content.execution.controller.execute.pre_acquisition_handoff import (
        PreAcquisitionHandoffError,
        load_pre_acquisition_handoff,
    )
    from governance.provider_policy import load_provider_policy

    handoff_path = _path(intent["preAcquisitionHandoffRef"])
    try:
        handoff = load_pre_acquisition_handoff(handoff_path)
    except PreAcquisitionHandoffError as exc:
        raise ValueError(str(exc)) from exc
    vertical = str(handoff["vertical"])
    region_ref = str(handoff.get("regionRef") or "").strip()
    lifecycle = str(handoff["lifecycle"])
    execution_mode = str(intent["mode"]).strip()
    scale, workload_mode, workloads = _normalized_workload(handoff["workloadTargets"])
    if scale != str(handoff["scale"]):
        raise ValueError(
            "handoff scale conflicts with its own workloadTargets: "
            f"{handoff['scale']} vs {scale}"
        )
    if not region_ref:
        # Envelope execution is region-addressed today; region-less scopes stay
        # typed at the input boundary instead of collapsing to a default region.
        raise LookupError(f"regionScopedExecutionRequired:{handoff['scopeType']}")
    entity_root = (
        paths.REPO_ROOT
        / "quwoquan_data"
        / "reference"
        / vertical
        / "entities"
        / region_ref
    )
    if not entity_root.is_dir():
        raise LookupError(f"unknownRegionRef:{region_ref}")
    distribution = load_content_distribution_policy()
    if lifecycle != distribution.product_lifecycle_state.value:
        raise LookupError(
            "lifecycle conflicts with current content distribution policy"
        )
    providers = sorted(
        {
            str(item).strip()
            for item in intent.get("sourceProviders") or []
            if str(item).strip()
        }
    )
    try:
        load_provider_policy(vertical).require_declared(tuple(providers))
    except ValueError as exc:
        raise LookupError(f"undeclaredSourceProvider:{exc}") from exc
    predecessors = dict(intent.get("predecessorExecutionIdsByCarrier") or {})
    if execution_mode == "retry" and set(predecessors) != set(workloads):
        raise LookupError("predecessorExecutionIdsByCarrier")
    external_inputs = intent.get("externalInputRefsByCarrier") or {}
    if isinstance(external_inputs, Mapping):
        inactive = sorted(set(external_inputs) - set(workloads))
        if inactive:
            raise LookupError(
                "externalInputInactiveCarrier:" + ",".join(inactive)
            )
    dependencies = _dependency_bindings(
        intent,
        scale=scale,
        workload_mode=workload_mode,
        workloads=workloads,
        vertical=vertical,
        region_ref=region_ref,
    )
    normalized = {
        "vertical": vertical,
        "regionRef": region_ref,
        "scopeType": str(handoff["scopeType"]),
        "scope": str(handoff["scope"]),
        "primaryTopicRef": handoff.get("primaryTopicRef"),
        "relatedTopicRefs": list(handoff.get("relatedTopicRefs") or []),
        "lifecycle": lifecycle,
        "executionMode": execution_mode,
        "scale": scale,
        "workloadMode": workload_mode,
        "activeCarriers": list(workloads),
        "workloads": workloads,
        "targetNames": sorted(
            {str(item).strip() for item in intent.get("targetNames") or [] if str(item).strip()}
        ),
        "sourceProviders": sorted(
            {str(item).strip() for item in intent.get("sourceProviders") or [] if str(item).strip()}
        ),
        "semanticSelectionId": str(
            intent.get("semanticSelectionId") or "default"
        ).strip(),
        "semanticPreflightReceiptRef": (
            _canonical_ref(_path(intent["semanticPreflightReceiptRef"]))
            if str(intent.get("semanticPreflightReceiptRef") or "").strip()
            else ""
        ),
        "capacityCalibrationReceiptRef": (
            _canonical_ref(_path(intent["capacityCalibrationReceiptRef"]))
            if str(intent.get("capacityCalibrationReceiptRef") or "").strip()
            else ""
        ),
        "preAcquisitionHandoffRef": _canonical_ref(
            _path(intent["preAcquisitionHandoffRef"])
        ),
        "scaleSourcePoolPlanRef": _canonical_ref(
            _path(intent["scaleSourcePoolPlanRef"])
        ),
        "sourcePoolEvidenceRootRef": _canonical_ref(
            _path(intent["sourcePoolEvidenceRootRef"])
        ),
        "externalInputRefsByCarrier": {
            carrier: list((intent.get("externalInputRefsByCarrier") or {}).get(carrier) or [])
            for carrier in workloads
        },
        "acquisitionRootRef": (
            _canonical_ref(_path(intent["acquisitionRootRef"]))
            if str(intent.get("acquisitionRootRef") or "").strip()
            else ""
        ),
        "predecessorExecutionIdsByCarrier": dict(
            intent.get("predecessorExecutionIdsByCarrier") or {}
        ),
        "predecessorReconciliationReceiptRef": (
            _canonical_ref(_path(intent["predecessorReconciliationReceiptRef"]))
            if str(
                intent.get("predecessorReconciliationReceiptRef") or ""
            ).strip()
            else ""
        ),
        "promotionReceiptRef": (
            _canonical_ref(_path(intent["promotionReceiptRef"]))
            if str(intent.get("promotionReceiptRef") or "").strip()
            else ""
        ),
        "sourceIdentity": {
            "sourceRevision": str(dependencies["sourcePool"]["sourceRevision"]),
            "sourceDigest": str(dependencies["source"]["digest"]),
            "executionBundleDigest": str(dependencies["executionBundle"]["digest"]),
            "entityCatalogDigest": str(dependencies["entityCatalogDigest"]),
        },
        "sourcePool": {
            key: dependencies["sourcePool"][key]
            for key in (
                "poolId",
                "targetScale",
                "workloadMode",
                "activeCarriers",
                "workloadTargets",
                "planDigest",
            )
        },
        "dependencies": dependencies["dependencies"],
        "dependencySetDigest": dependencies["dependencySetDigest"],
        "carrierPolicyDigest": carrier_policy_digest(),
    }
    return normalized


def _input_issues(intent: Mapping[str, Any]) -> list[str]:
    issues = [key for key in _REQUIRED_INPUTS if intent.get(key) in (None, "", {})]
    issues.extend(f"unknown:{key}" for key in intent if key not in _ALLOWED_INPUTS)
    for field in ("targetNames", "sourceProviders"):
        value = intent.get(field, [])
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            issues.append(field)
    external_inputs = intent.get("externalInputRefsByCarrier") or {}
    if not isinstance(external_inputs, Mapping):
        issues.append("externalInputRefsByCarrier")
    else:
        issues.extend(
            f"unknownCarrier:{carrier}"
            for carrier in external_inputs
            if carrier not in CAMPAIGN_CARRIERS
        )
        issues.extend(
            f"externalInputRefsByCarrier:{carrier}"
            for carrier, declarations in external_inputs.items()
            if not isinstance(declarations, list)
        )
    mode = str(intent.get("mode") or "")
    if mode and mode not in {"fresh", "retry"}:
        issues.append("mode")
    semantic = str(intent.get("semanticSelectionId") or "default")
    if semantic not in {"default", "cursor_grok", "cursor_auto"}:
        issues.append("semanticSelectionId")
    if semantic in {"cursor_grok", "cursor_auto"} and not intent.get(
        "semanticPreflightReceiptRef"
    ):
        issues.append("semanticPreflightReceiptRef")
    if semantic == "cursor_auto" and mode != "retry":
        issues.append("cursorAutoRetryRequired")
    predecessors = intent.get("predecessorExecutionIdsByCarrier") or {}
    reconciliation = intent.get("predecessorReconciliationReceiptRef")
    if mode == "fresh" and (predecessors or reconciliation):
        issues.append("freshRetryConflict")
    if mode == "retry":
        if not isinstance(predecessors, Mapping) or not predecessors or any(
            not isinstance(value, str) or not value.strip()
            for value in predecessors.values()
        ):
            issues.append("predecessorExecutionIdsByCarrier")
        if not reconciliation:
            issues.append("predecessorReconciliationReceiptRef")
    return issues


class WorkRequestPreviewQuery:
    def preview(self, intent: Mapping[str, Any]) -> dict[str, Any]:
        issues = _input_issues(intent)
        if issues:
            return _needs_input(intent, issues)
        try:
            normalized = _normalize(intent)
        except LookupError as exc:
            return _needs_input(intent, [str(exc)])
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            return _blocked(
                _raw_digest(intent),
                code="DATA.WORK_REQUEST.DEPENDENCY_UNAVAILABLE",
                message=str(exc),
                attributes={"exceptionType": type(exc).__name__},
            )
        request_digest = _digest(normalized)
        return _validated_result(
            {
                "schema": _RESULT_SCHEMA,
                "outcome": "preview",
                "requestDigest": request_digest,
                "normalizedRequest": normalized,
            }
        )


__all__ = ["WorkRequestPreviewQuery"]

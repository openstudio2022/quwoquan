"""WorkRequest normalization and typed preview contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from content.execution.campaign.carrier_execution_policy import carrier_policy_digest
from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.planning.work_request_dependencies import (
    canonical_dependency_ref,
    canonical_digest,
    dependency_bindings,
    normalized_workload,
    resolve_dependency_path,
)
from core import paths
from core.control_types import RecoveryNextAction
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy

_RESULT_SCHEMA = "quwoquan_data.work_request_compile_result"
_MAX_DOCUMENT_BYTES = 256 * 1024
# Demand facts (vertical, scope, topic refs, lifecycle, workloads) are owned by
# the confirmed pre-acquisition handoff; independent caller inputs for them are
# rejected as unknown keys instead of silently merged.
# `sourceProviders` is deliberately absent: per-carrier provider intent is owned
# by `handoff.sourceSelection` and only projected, so a caller-supplied list is
# rejected as an unknown key instead of becoming a second truth source.
_ALLOWED_INPUTS = frozenset(
    {
        "intentText",
        "mode",
        "targetNames",
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
    return canonical_digest(
        {
            str(key): value
            for key, value in intent.items()
            if str(key) != "intentText"
        }
    )


def declared_handoff_ref(intent: Mapping[str, Any]) -> str | None:
    """Read the handoff the caller declared, or `None` when none was declared.

    A needs-input result exists precisely because the intent may be incomplete,
    so an undeclared handoff is a legitimate absence here rather than a failure;
    it must stay distinguishable from a declared-but-empty ref, which is why the
    blank string collapses to absence instead of travelling into the reentry.
    """

    text = str(intent.get("preAcquisitionHandoffRef") or "").strip()
    return text or None


def _reentry_ref(request_digest: str, handoff_ref: str | None) -> dict[str, Any]:
    return {
        "requestDigest": request_digest,
        "preAcquisitionHandoffRef": handoff_ref,
    }


def _needs_input(
    intent: Mapping[str, Any], fields: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    request_digest = _raw_digest(intent)
    return _validated_result(
        {
            "schema": _RESULT_SCHEMA,
            "outcome": "needs_input",
            "requestDigest": request_digest,
            "missingFields": sorted(set(fields)),
            "nextAction": RecoveryNextAction.SUPPLY_INPUT.value,
            "reentryRef": _reentry_ref(
                request_digest, declared_handoff_ref(intent)
            ),
        }
    )


def _blocked(
    request_digest: str,
    *,
    code: str,
    message: str,
    next_action: RecoveryNextAction,
    handoff_ref: str | None,
    attributes: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Project one blocked compile result whose recovery action is declared.

    `next_action` is a required argument rather than a lookup keyed by `code`:
    deriving the action from the error code would put the recovery contract in a
    table that drifts silently every time a new code appears, and the caller is
    the only party that knows which of two callers sharing a code is recoverable
    by re-compiling versus by repairing evidence.
    """

    if next_action is RecoveryNextAction.NONE:
        raise ValueError(
            "DATA.WORK_REQUEST.RECOVERY_ACTION_INVALID: "
            "blocked compile result must declare a recovery action"
        )
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
            "nextAction": next_action.value,
            "reentryRef": _reentry_ref(request_digest, handoff_ref),
        }
    )


def _normalize(intent: Mapping[str, Any]) -> dict[str, Any]:
    from content.source.pre_acquisition_handoff import (
        PreAcquisitionHandoffError,
        carrier_source_providers,
        load_pre_acquisition_handoff,
    )

    handoff_path = resolve_dependency_path(intent["preAcquisitionHandoffRef"])
    try:
        handoff = load_pre_acquisition_handoff(handoff_path)
    except PreAcquisitionHandoffError as exc:
        raise ValueError(str(exc)) from exc
    vertical = str(handoff["vertical"])
    region_ref = str(handoff.get("regionRef") or "").strip()
    lifecycle = str(handoff["lifecycle"])
    execution_mode = str(intent["mode"]).strip()
    scale, workload_mode, workloads = normalized_workload(handoff["workloadTargets"])
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
    try:
        source_selection = {
            carrier: {
                "mode": str(handoff["sourceSelection"][carrier]["mode"]),
                "providers": carrier_source_providers(handoff, carrier),
            }
            for carrier in workloads
        }
    except PreAcquisitionHandoffError as exc:
        raise ValueError(str(exc)) from exc
    except (KeyError, TypeError) as exc:
        raise LookupError(f"sourceSelectionUnavailable:{exc}") from exc
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
    dependencies = dependency_bindings(
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
        "sourceSelection": source_selection,
        "semanticSelectionId": str(
            intent.get("semanticSelectionId") or "default"
        ).strip(),
        "semanticPreflightReceiptRef": (
            canonical_dependency_ref(
                resolve_dependency_path(intent["semanticPreflightReceiptRef"])
            )
            if str(intent.get("semanticPreflightReceiptRef") or "").strip()
            else ""
        ),
        "capacityCalibrationReceiptRef": (
            canonical_dependency_ref(
                resolve_dependency_path(intent["capacityCalibrationReceiptRef"])
            )
            if str(intent.get("capacityCalibrationReceiptRef") or "").strip()
            else ""
        ),
        "preAcquisitionHandoffRef": canonical_dependency_ref(
            resolve_dependency_path(intent["preAcquisitionHandoffRef"])
        ),
        "scaleSourcePoolPlanRef": canonical_dependency_ref(
            resolve_dependency_path(intent["scaleSourcePoolPlanRef"])
        ),
        "sourcePoolEvidenceRootRef": canonical_dependency_ref(
            resolve_dependency_path(intent["sourcePoolEvidenceRootRef"])
        ),
        "externalInputRefsByCarrier": {
            carrier: list((intent.get("externalInputRefsByCarrier") or {}).get(carrier) or [])
            for carrier in workloads
        },
        "acquisitionRootRef": (
            canonical_dependency_ref(
                resolve_dependency_path(intent["acquisitionRootRef"])
            )
            if str(intent.get("acquisitionRootRef") or "").strip()
            else ""
        ),
        "predecessorExecutionIdsByCarrier": dict(
            intent.get("predecessorExecutionIdsByCarrier") or {}
        ),
        "predecessorReconciliationReceiptRef": (
            canonical_dependency_ref(
                resolve_dependency_path(
                    intent["predecessorReconciliationReceiptRef"]
                )
            )
            if str(
                intent.get("predecessorReconciliationReceiptRef") or ""
            ).strip()
            else ""
        ),
        "promotionReceiptRef": (
            canonical_dependency_ref(
                resolve_dependency_path(intent["promotionReceiptRef"])
            )
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
    value = intent.get("targetNames", [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        issues.append("targetNames")
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
                # 依赖不可读时意图本身没问题，恢复动作是修证据而不是改意图。
                next_action=RecoveryNextAction.REPAIR_EVIDENCE,
                handoff_ref=declared_handoff_ref(intent),
                attributes={"exceptionType": type(exc).__name__},
            )
        request_digest = canonical_digest(normalized)
        return _validated_result(
            {
                "schema": _RESULT_SCHEMA,
                "outcome": "preview",
                "requestDigest": request_digest,
                "normalizedRequest": normalized,
                "nextAction": RecoveryNextAction.NONE.value,
                "reentryRef": None,
            }
        )


__all__ = ["WorkRequestPreviewQuery", "declared_handoff_ref"]

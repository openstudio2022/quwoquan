"""把一份 WorkRequest 意图里声明的依赖引用冻结成逐字节绑定。

本模块只做「声明 → 解析 → 校验 → 摘要」这一段：解析出的每个依赖都要落在受治理的
根下、要真实存在、要与 SourcePool 计划声明的身份一致，任何一条不成立立即判否，不为
缺失依赖挑一个默认值。编译截面的判定与结果文档构造留在 `work_request_contract`。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.dependency_ref import canonical_dependency_ref, resolve_dependency_path
from core.io import read_json
from core.source_digest import (
    content_source_revision,
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from governance.coverage.distribution import (
    POLICY_PATH as DISTRIBUTION_POLICY_PATH,
)
from governance.coverage.distribution import (
    load_content_distribution_policy,
)

from content.execution.planning.carrier_policy import (
    POLICY_PATH as CARRIER_POLICY_PATH,
)
from content.execution.planning.carrier_policy import (
    carrier_policy_digest,
)
from content.execution.execution_terminal import load_terminal_execution_evidence
from content.execution.source_pool.external_inputs import bind_external_input_refs
from content.execution.planning.carrier_demand import CAMPAIGN_CARRIERS, normalize_workloads
from content.execution.planning.scale import campaign_workload_targets
from content.execution.identity import parse_execution_id
from content.execution.stage_authority_validation import (
    validate_stage_receipt_authority,
)
from content.execution.stage_receipt import RECEIPT_STAGES, list_receipt_files
from content.execution.workspace import entity_catalog_digest
from content.source.research.scale_source_pool import (
    validate_scale_source_pool_evidence,
)
from core.schema import assert_valid

__all__ = [
    "canonical_dependency_ref",
    "canonical_digest",
    "dependency_bindings",
    "file_digest",
    "normalized_workload",
    "resolve_dependency_path",
    "tree_digest",
]


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise FileNotFoundError(f"dependency directory is missing: {root}")
    rows: list[dict[str, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append(
            {
                "ref": path.relative_to(root).as_posix(),
                "digest": file_digest(path),
            }
        )
    if not rows:
        raise ValueError(f"dependency directory is empty: {root}")
    return canonical_digest(rows)


def normalized_workload(
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


def _portable_output_ref(path: Path) -> str:
    resolved = path.resolve(strict=True)
    output_root = paths.OUTPUT_ROOT.resolve(strict=True)
    try:
        return resolved.relative_to(output_root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"predecessor evidence is outside the governed output root: {path}"
        ) from exc


def _receipt_projection(
    execution_id: str,
    receipt: Mapping[str, Any],
    *,
    receipt_path: Path,
    receipt_digest: str,
    completed: list[str],
    status: str,
) -> dict[str, Any]:
    return {
        "executionId": execution_id,
        "completed": completed,
        "status": status,
        "latestStage": str(receipt.get("stage") or ""),
        "next": str(receipt.get("next") or ""),
        "latestReceiptRef": receipt_path.relative_to(
            receipt_path.parents[2]
        ).as_posix(),
        "latestReceiptDigest": receipt_digest,
        "updatedAt": str(receipt.get("recordedAt") or ""),
    }


def _predecessor_terminal_dependency_rows(
    intent: Mapping[str, Any],
    workloads: Mapping[str, int],
) -> dict[str, dict[str, str]]:
    raw_predecessors = intent.get("predecessorExecutionIdsByCarrier") or {}
    if not raw_predecessors:
        return {}
    if not isinstance(raw_predecessors, Mapping):
        raise TypeError("predecessorExecutionIdsByCarrier must be a carrier mapping")
    if set(raw_predecessors) != set(workloads):
        raise ValueError(
            "predecessorExecutionIdsByCarrier must exactly match active carriers"
        )

    rows: dict[str, dict[str, str]] = {}
    for carrier in workloads:
        execution_id = str(raw_predecessors[carrier]).strip()
        identity = parse_execution_id(execution_id)
        if identity.content_type.value != carrier:
            raise ValueError(
                "predecessor execution carrier differs from mapping key: "
                f"{carrier} != {identity.content_type.value}"
            )
        execution_root = paths.DATA_EXECUTIONS_ROOT / execution_id
        if not execution_root.is_dir() or execution_root.is_symlink():
            raise FileNotFoundError(
                f"predecessor execution work package is missing: {execution_root}"
            )
        receipts = list_receipt_files(execution_id)
        if not receipts:
            raise FileNotFoundError(
                f"predecessor execution has no immutable stage receipt: {execution_id}"
            )
        receipt_inventory = tuple(
            (sequence, stage, path.resolve(strict=True))
            for sequence, stage, path in receipts
        )
        _, _, latest_receipt_path = receipts[-1]
        state_path = execution_root / "_shared" / "execution_state.json"
        for label, evidence_path in (
            ("predecessor latest stage receipt", latest_receipt_path),
            ("predecessor execution state", state_path),
        ):
            if not evidence_path.is_file() or evidence_path.is_symlink():
                raise FileNotFoundError(f"{label} is missing: {evidence_path}")

        latest_receipt_digest = file_digest(latest_receipt_path)
        state_digest = file_digest(state_path)
        latest_receipt = validate_stage_receipt_authority(
            execution_id,
            latest_receipt_path,
            verify_current_workflow=False,
        )
        state = read_json(state_path)
        if not isinstance(state, dict):
            raise TypeError("predecessor execution state must be an object")
        assert_valid(
            state,
            "execution",
            "execution_state",
            label=f"predecessor execution state:{execution_id}",
        )

        terminal_path = latest_receipt_path
        terminal_digest = latest_receipt_digest
        workflow_terminal = False
        if latest_receipt.get("verdict") == "blocked":
            terminal = load_terminal_execution_evidence(execution_root)
            if terminal is not None:
                raise ValueError(
                    "blocked predecessor must not carry independent terminal evidence: "
                    f"{execution_id}"
                )
            expected_state = _receipt_projection(
                execution_id,
                latest_receipt,
                receipt_path=latest_receipt_path,
                receipt_digest=latest_receipt_digest,
                completed=list(
                    RECEIPT_STAGES[: max(int(latest_receipt.get("sequence") or 0) - 1, 0)]
                ),
                status="manual_required",
            )
        elif latest_receipt.get("verdict") == "pass":
            terminal = load_terminal_execution_evidence(execution_root)
            if (
                terminal is None
                or terminal.decision != "superseded"
                or terminal.receipt.get("reason") != "workflow_drift"
            ):
                raise ValueError(
                    "passing predecessor requires canonical workflow_drift "
                    f"supersession evidence: {execution_id}"
                )
            terminal_path = terminal.path.resolve(strict=True)
            terminal_digest = file_digest(terminal_path)
            workflow_terminal = True
            expected_state = _receipt_projection(
                execution_id,
                latest_receipt,
                receipt_path=latest_receipt_path,
                receipt_digest=latest_receipt_digest,
                completed=list(RECEIPT_STAGES[: int(latest_receipt.get("sequence") or 0)]),
                status="running",
            )
        else:
            raise ValueError(
                f"predecessor latest stage receipt verdict is invalid: {execution_id}"
            )

        drift = [
            field
            for field, expected in expected_state.items()
            if state.get(field) != expected
        ]
        if drift:
            raise ValueError(
                "predecessor execution state is not the current receipt-derived "
                f"projection: {execution_id}: {', '.join(drift)}"
            )
        current_inventory = tuple(
            (sequence, stage, path.resolve(strict=True))
            for sequence, stage, path in list_receipt_files(execution_id)
        )
        terminal_again = (
            load_terminal_execution_evidence(execution_root)
            if workflow_terminal
            else None
        )
        if (
            current_inventory != receipt_inventory
            or file_digest(latest_receipt_path) != latest_receipt_digest
            or file_digest(state_path) != state_digest
            or (
                workflow_terminal
                and (
                    terminal_again is None
                    or terminal_again.decision != "superseded"
                    or terminal_again.receipt.get("reason") != "workflow_drift"
                    or terminal_again.path.resolve(strict=True) != terminal_path
                )
            )
            or not terminal_path.is_file()
            or terminal_path.is_symlink()
            or file_digest(terminal_path) != terminal_digest
        ):
            raise ValueError(
                "predecessor terminal evidence changed during validation: "
                f"{execution_id}"
            )
        rows[f"predecessorTerminalReceipt:{carrier}"] = {
            "ref": _portable_output_ref(terminal_path),
            "digest": terminal_digest,
        }
        rows[f"predecessorExecutionState:{carrier}"] = {
            "ref": _portable_output_ref(state_path),
            "digest": state_digest,
        }
    return rows


def dependency_bindings(
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
    plan_path = resolve_dependency_path(intent["scaleSourcePoolPlanRef"])
    evidence_root = resolve_dependency_path(intent["sourcePoolEvidenceRootRef"])
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
        "preAcquisitionHandoffRef": resolve_dependency_path(
            intent["preAcquisitionHandoffRef"]
        ),
        "scaleSourcePoolPlanRef": plan_path,
    }
    # bounded M1–M10 请求不携带 calibration receipt，授权由 envelope builder
    # 的互斥 executionAuthority 判定；governed 请求仍逐字节绑定 receipt。
    calibration_ref = str(intent.get("capacityCalibrationReceiptRef") or "").strip()
    if calibration_ref:
        file_refs["capacityCalibrationReceiptRef"] = resolve_dependency_path(
            calibration_ref
        )
    semantic_ref = str(intent.get("semanticPreflightReceiptRef") or "").strip()
    if semantic_ref:
        file_refs["semanticPreflightReceiptRef"] = resolve_dependency_path(semantic_ref)
    promotion_ref = str(intent.get("promotionReceiptRef") or "").strip()
    if promotion_ref:
        file_refs["promotionReceiptRef"] = resolve_dependency_path(promotion_ref)
    for label, path in file_refs.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label} is missing: {path}")
    dependency_rows = {
        label: {
            "ref": canonical_dependency_ref(path),
            "digest": file_digest(path),
        }
        for label, path in file_refs.items()
    }
    dependency_rows.update(
        _predecessor_terminal_dependency_rows(intent, workloads)
    )
    dependency_rows["sourceDefinition"] = {
        "ref": "quwoquan_data/source-definition",
        "digest": str(source["digest"]),
    }
    dependency_rows["executionBundle"] = {
        "ref": "quwoquan_data/execution-bundle",
        "digest": str(execution_bundle["digest"]),
    }
    dependency_rows["sourcePoolEvidenceRootRef"] = {
        "ref": canonical_dependency_ref(evidence_root),
        "digest": tree_digest(evidence_root),
    }
    dependency_rows["carrierExecutionPolicy"] = {
        "ref": CARRIER_POLICY_PATH.relative_to(repo_root).as_posix(),
        "digest": carrier_policy_digest(),
    }
    dependency_rows["contentDistributionPolicy"] = {
        "ref": DISTRIBUTION_POLICY_PATH.relative_to(repo_root).as_posix(),
        "digest": file_digest(DISTRIBUTION_POLICY_PATH),
    }
    acquisition_root_text = str(intent.get("acquisitionRootRef") or "").strip()
    acquisition_root = (
        resolve_dependency_path(acquisition_root_text)
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
                "digest": canonical_digest(frozen),
            }
    return {
        "source": source,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": entity_digest,
        "sourcePool": dict(plan),
        "dependencies": dependency_rows,
        "dependencySetDigest": canonical_digest(dependency_rows),
    }

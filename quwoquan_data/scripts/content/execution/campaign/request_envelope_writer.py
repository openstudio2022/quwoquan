"""Atomic active-workload writer for immutable campaign request envelopes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.request_envelope import (
    _require_stable_source_inputs,
    _sha256,
    build_envelope,
    envelope_path,
)
from content.execution.campaign.scale import (
    CampaignScaleError,
    campaign_workload_targets,
    resolve_campaign_scale,
)
from content.execution.identity import parse_execution_id
from content.execution.model_contract import DEFAULT_SEMANTIC_SELECTION_ID
from content.execution.planning.capacity_policy import (
    derive_workload_capacity_fields,
)


def _reconciliation_inputs(
    receipt_path: Path,
    *,
    sequence: int,
    retry_predecessors: Mapping[str, str],
    target_names: Iterable[str],
    output_root: Path,
) -> tuple[dict[str, str], tuple[str, ...], dict[str, Any], Mapping[str, Any]]:
    from content.execution.campaign import request_envelope as envelope_contract

    if sequence == 1:
        raise ValueError(
            "campaign envelope sequence=1 forbids predecessor reconciliation"
        )
    receipt = envelope_contract.load_submission_reconciliation_receipt(
        receipt_path,
        output_root=output_root,
    )
    submissions = receipt.get("submissions")
    if not isinstance(submissions, Mapping) or not submissions:
        raise ValueError("campaign predecessor reconciliation is incomplete")
    active = normalize_active_carriers(receipt.get("activeCarriers") or ())
    if not set(submissions) <= set(active):
        raise ValueError("campaign predecessor reconciliation carriers are invalid")
    absence_rows = {
        str(row.get("carrier") or ""): str(row.get("executionId") or "")
        for row in (receipt.get("executionEvidence") or {}).get("lanes") or []
        if isinstance(row, Mapping)
    }
    predecessors = {
        carrier: (
            str(submissions[carrier]["executionId"])
            if carrier in submissions
            else absence_rows.get(carrier, "")
        )
        for carrier in active
    }
    if any(not execution_id for execution_id in predecessors.values()):
        raise ValueError("campaign predecessor reconciliation executionIds are incomplete")
    first_carrier = active[0]
    targets = tuple(submissions[first_carrier]["targetNames"])
    if any(
        tuple(submissions[carrier]["targetNames"]) != targets
        for carrier in active
    ):
        raise ValueError("campaign predecessor reconciliation targetNames drift")
    if tuple(sorted(set(targets))) != targets:
        raise ValueError(
            "campaign predecessor reconciliation targetNames are not canonical"
        )
    reason = receipt.get("reason")
    retry_subset_allowed = reason == "terminal_unpublished_retryable_shortfall"
    if retry_predecessors:
        supplied = dict(retry_predecessors)
        valid = (
            all(predecessors.get(carrier) == execution_id for carrier, execution_id in supplied.items())
            and (
                set(supplied) <= set(predecessors)
                if retry_subset_allowed
                else supplied == predecessors
            )
        )
        if not valid:
            raise ValueError(
                "campaign retry predecessors differ from reconciliation receipt"
            )
    requested = tuple(
        sorted({str(item).strip() for item in target_names if str(item).strip()})
    )
    if requested and requested != targets and not retry_subset_allowed:
        raise ValueError(
            "campaign retry targetNames differ from reconciliation receipt"
        )
    original = receipt.get("originalSourceIdentity")
    if not isinstance(original, Mapping):
        raise TypeError(
            "campaign predecessor reconciliation original identity is invalid"
        )
    return (
        (dict(retry_predecessors) if retry_subset_allowed else predecessors),
        (requested if retry_subset_allowed else targets),
        envelope_contract.reconciliation_reference(
            receipt_path,
            output_root=output_root,
        ),
        receipt,
    )


def _assert_one_source_identity(
    payloads: Mapping[str, Mapping[str, Any]],
    *,
    predecessor_reconciliation_receipt: Mapping[str, Any] | None,
) -> None:
    identities = {
        json.dumps(
            {
                "sourceRevision": payload["sourceRevision"],
                "sourceDigest": payload["sourceDigest"],
                "entityCatalogDigest": payload["entityCatalogDigest"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for payload in payloads.values()
    }
    if len(identities) != 1:
        raise ValueError(
            "campaign envelope source identity changed while freezing carriers"
        )
    if predecessor_reconciliation_receipt is None:
        return
    reason = predecessor_reconciliation_receipt.get("reason")
    if reason in {
        "mixed_finalized_partial_terminal",
        "terminal_unpublished_source_drift",
        "terminal_unpublished_retryable_shortfall",
    }:
        observed_identity = predecessor_reconciliation_receipt.get(
            "observedSourceIdentity"
        )
        if not isinstance(observed_identity, Mapping):
            raise TypeError(
                "campaign mixed terminal reconciliation observed identity is invalid"
            )
        execution_evidence = predecessor_reconciliation_receipt.get(
            "executionEvidence"
        )
        if not isinstance(execution_evidence, Mapping):
            raise TypeError(
                "campaign mixed terminal reconciliation execution evidence is invalid"
            )
        if (
            predecessor_reconciliation_receipt.get("retryPolicy")
            != "active_workload_execution_with_retryOf"
            or execution_evidence.get("excludedFromRetryRelease") is not True
            or execution_evidence.get("eligibleForRelease") is not False
        ):
            raise ValueError(
                "campaign mixed terminal reconciliation does not exclude predecessor objects"
            )
        current = next(iter(payloads.values()))
        current_identity = {
            "sourceRevision": current["sourceRevision"],
            "sourceDigest": current["sourceDigest"],
            "entityCatalogDigest": current["entityCatalogDigest"],
        }
        if (
            reason
            in {
                "terminal_unpublished_source_drift",
                "terminal_unpublished_retryable_shortfall",
            }
            and current_identity != observed_identity
        ):
            raise ValueError(
                "campaign terminal unpublished retry source identity drifted"
            )
        # The receipt binds the old mixed terminal boundary.  A retry is a fresh
        # active-workload execution and may intentionally use a superseding handoff
        # after a source fix; the old objects remain provenance only and are
        # never carried into the retry release.
        return
    if reason not in {
        "source_drift",
        "claimed_execution_source_drift",
    }:
        return
    original_identity = predecessor_reconciliation_receipt.get(
        "originalSourceIdentity"
    )
    if not isinstance(original_identity, Mapping):
        raise TypeError(
            "campaign predecessor reconciliation original identity is invalid"
        )
    current = next(iter(payloads.values()))
    current_identity = {
        "sourceRevision": current["sourceRevision"],
        "sourceDigest": current["sourceDigest"],
        "entityCatalogDigest": current["entityCatalogDigest"],
    }
    if current_identity == dict(original_identity):
        raise ValueError(
            "campaign retry source identity did not leave the reconciled source"
        )


def _assert_one_handoff_identity(
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    bindings = {
        json.dumps(
            payload["preAcquisitionHandoff"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for payload in payloads.values()
    }
    if len(bindings) != 1:
        raise ValueError(
            "campaign handoff identity changed while freezing carriers"
        )


def _assert_workload_plans(
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    for payload in payloads.values():
        work_unit_count = int(payload["quota"])
        expected = derive_workload_capacity_fields(
            target_scale=str(payload["scale"]),
            carrier=str(payload["carrier"]),
            work_unit_count=work_unit_count,
        )
        if any(
            payload.get(key) != value
            for key, value in expected.items()
            if key != "workerHostSetBinding"
        ) or payload.get("workerHostSetBinding") is not None:
            raise ValueError("campaign workload plan drift")


def _assert_one_scale_source_pool(
    payloads: Mapping[str, Mapping[str, Any]], *, scale: str
) -> None:
    bindings = {
        json.dumps(
            payload.get("scaleSourcePool"), sort_keys=True, separators=(",", ":")
        )
        for payload in payloads.values()
    }
    evidence_refs = {
        str(payload.get("sourcePoolEvidenceRootRef") or "")
        for payload in payloads.values()
    }
    if bindings == {"null"}:
        if evidence_refs != {""} or any(
            payload.get("sourcePoolSelection") is not None
            for payload in payloads.values()
        ):
            raise ValueError(
                "DATA.SOURCE.POOL_SHORTFALL: incomplete campaign pool binding"
            )
        return
    if scale in {"M100", "M1000", "M10000"}:
        if len(bindings) != 1 or len(evidence_refs) != 1 or "" in evidence_refs:
            raise ValueError("DATA.SOURCE.POOL_SHORTFALL: campaign pool binding drift")
        carriers = {
            str((payload.get("sourcePoolSelection") or {}).get("carrier") or "")
            for payload in payloads.values()
        }
        if carriers != set(payloads):
            raise ValueError("DATA.SOURCE.POOL_SHORTFALL: lane pool selections incomplete")
        first = next(iter(payloads.values()))
        binding = first.get("scaleSourcePool") or {}
        if (
            binding.get("workloadMode") == "explicit"
            and (
                binding.get("activeCarriers") != list(payloads)
                or binding.get("workloadTargets") != first.get("workloads")
            )
        ):
            raise ValueError(
                "DATA.SOURCE.POOL_SHORTFALL: pool workloadTargets drift"
            )
    elif bindings != {"null"} or evidence_refs != {""}:
        raise ValueError(
            "DATA.SOURCE.POOL_SHORTFALL: below-M100 forbids source pool binding"
        )


def write_scale_envelopes(
    scale: str | None = None,
    *,
    quota: int | None = None,
    region_ref: str = "china",
    vertical: str = "travel",
    topic: str | None = None,
    target_names: Iterable[str] | None = None,
    source_providers: Iterable[str] | None = None,
    family_ref: str | None = None,
    carriers: Iterable[str] | None = None,
    workloads: Mapping[str, int] | None = None,
    repo_root: Path | None = None,
    output_root: Path | None = None,
    day: str | None = None,
    sequence: int = 1,
    semantic_selection_id: str = DEFAULT_SEMANTIC_SELECTION_ID,
    semantic_preflight_receipt: Path | None = None,
    semantic_preflight_output_root: Path | None = None,
    predecessor_execution_ids_by_carrier: Mapping[str, str] | None = None,
    predecessor_reconciliation_receipt: Path | None = None,
    reconciliation_output_root: Path | None = None,
    promotion_receipt: Path | None = None,
    promotion_output_root: Path | None = None,
    pre_acquisition_handoff: Path | None = None,
    pre_acquisition_handoff_output_root: Path | None = None,
    external_input_refs_by_carrier: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    acquisition_root: Path | None = None,
    scale_source_pool: Path | None = None,
    source_pool_evidence_root: Path | None = None,
    retry_evidence_output_root: Path | None = None,
) -> dict[str, Path]:
    """Write immutable envelopes for selected carriers at one resolved scale."""

    requested_workloads = dict(workloads or {})
    resolved = resolve_campaign_scale(
        scale=scale,
        quota=(
            quota
            if quota is not None
            else (max(requested_workloads.values()) if scale is None and requested_workloads else None)
        ),
    )
    if requested_workloads:
        selected = normalize_active_carriers(
            carriers if carriers is not None else requested_workloads
        )
        exact_workloads = normalize_workloads(
            requested_workloads,
            active_carriers=selected,
        )
        workload_mode = "explicit"
    else:
        selected = normalize_active_carriers(carriers or CAMPAIGN_CARRIERS)
        is_milestone_preset = (
            selected == CAMPAIGN_CARRIERS
            and resolved.scale in {"M100", "M1000", "M10000"}
        )
        workload_mode = "milestone_preset" if is_milestone_preset else "explicit"
        exact_workloads = (
            campaign_workload_targets(resolved.scale)
            if is_milestone_preset
            else {carrier: resolved.quota for carrier in selected}
        )
    retry_predecessors = dict(predecessor_execution_ids_by_carrier or {})
    target_input = tuple(target_names or ())
    predecessor_reconciliation: dict[str, Any] | None = None
    reconciliation_receipt: Mapping[str, Any] | None = None
    if predecessor_reconciliation_receipt is not None:
        reconciliation_root = (
            reconciliation_output_root or paths.OUTPUT_ROOT
        ).resolve()
        (
            retry_predecessors,
            target_input,
            predecessor_reconciliation,
            reconciliation_receipt,
        ) = _reconciliation_inputs(
            predecessor_reconciliation_receipt,
            sequence=sequence,
            retry_predecessors=retry_predecessors,
            target_names=target_input,
            output_root=reconciliation_root,
        )
    if sequence == 1 and retry_predecessors:
        raise ValueError("campaign envelope sequence=1 forbids retry predecessors")
    required = set(selected)
    if retry_predecessors and set(retry_predecessors) != required:
        raise ValueError(
            "campaign retry predecessors must exactly match active carriers"
        )
    payloads: dict[str, dict[str, Any]] = {}
    for carrier in selected:
        payload = build_envelope(
            scale=resolved.scale,
            quota=None,
            carrier=carrier,
            region_ref=region_ref,
            vertical=vertical,
            topic=topic,
            target_names=target_input,
            source_providers=source_providers,
            family_ref=family_ref,
            repo_root=repo_root,
            day=day,
            sequence=sequence,
            predecessor_execution_id=retry_predecessors.get(carrier),
            allow_retry_intent_change=(
                reconciliation_receipt is not None
                and reconciliation_receipt.get("reason")
                == "terminal_unpublished_retryable_shortfall"
            ),
            semantic_selection_id=semantic_selection_id,
            semantic_preflight_receipt=semantic_preflight_receipt,
            semantic_preflight_output_root=semantic_preflight_output_root,
            predecessor_reconciliation=predecessor_reconciliation,
            promotion_receipt=promotion_receipt,
            promotion_output_root=(promotion_output_root or output_root or paths.OUTPUT_ROOT),
            pre_acquisition_handoff=pre_acquisition_handoff,
            pre_acquisition_handoff_output_root=pre_acquisition_handoff_output_root,
            external_input_refs=(external_input_refs_by_carrier or {}).get(carrier, ()),
            acquisition_root=acquisition_root,
            scale_source_pool=scale_source_pool,
            source_pool_evidence_root=source_pool_evidence_root,
            source_pool_output_root=(output_root or paths.OUTPUT_ROOT),
            retry_evidence_output_root=retry_evidence_output_root,
            active_carriers=selected,
            workloads=exact_workloads,
            workload_mode=workload_mode,
        )
        payloads[carrier] = payload
    actual_workloads = {
        carrier: int(payloads[carrier]["quota"])
        for carrier in selected
    }
    root_execution_id = str(payloads[selected[0]]["executionId"])
    for payload in payloads.values():
        payload["activeCarriers"] = list(selected)
        payload["workloads"] = dict(actual_workloads)
        payload["rootExecutionId"] = root_execution_id
        stable = {
            key: value
            for key, value in payload.items()
            if key not in {"requestDigest", "frozenAt"}
        }
        payload["requestDigest"] = _sha256(stable)
        assert_valid(
            payload,
            "execution",
            "content_campaign_request_envelope",
            label=f"campaign envelope:{resolved.scale}:{payload['carrier']}",
        )
    _assert_one_source_identity(
        payloads,
        predecessor_reconciliation_receipt=reconciliation_receipt,
    )
    _assert_one_handoff_identity(payloads)
    _assert_workload_plans(payloads)
    _assert_one_scale_source_pool(payloads, scale=resolved.scale)
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    frozen_source = next(iter(payloads.values()))["sourceDigest"]
    frozen_bundle = next(iter(payloads.values()))["executionBundle"]
    if not isinstance(frozen_source, dict):
        raise TypeError("campaign envelope sourceDigest document is invalid")
    if not isinstance(frozen_bundle, dict):
        raise TypeError("campaign envelope executionBundle document is invalid")
    _require_stable_source_inputs(
        frozen_source,
        execution_bundle=frozen_bundle,
        repo_root=source_repo,
    )

    written: dict[str, Path] = {}
    for carrier, payload in payloads.items():
        identity = parse_execution_id(str(payload["executionId"]))
        path = envelope_path(
            resolved.scale,
            carrier,
            scope=identity.scope,
            vertical=vertical,
            root=output_root,
            sequence=identity.sequence,
        )
        if path.is_file():
            existing = read_json(path)
            if existing != payload and (
                str(existing.get("requestDigest") or "")
                != str(payload.get("requestDigest") or "")
            ):
                raise ValueError(
                    f"campaign envelope already frozen with different digest: {path}"
                )
            written[carrier] = path
            continue
        write_json(path, payload)
        written[carrier] = path
    return written


def write_campaign_envelopes(
    *,
    scales: Iterable[str] | None = None,
    quota: int | None = None,
    **kwargs: Any,
) -> dict[str, dict[str, Path]]:
    """Write one or more named/custom scales through the atomic writer."""
    scale_list = [str(item).strip() for item in (scales or []) if str(item).strip()]
    if scale_list and quota is not None and len(scale_list) != 1:
        raise CampaignScaleError(
            "GATE_BLOCK write_campaign_envelopes cannot combine quota= with multiple scales"
        )
    if not scale_list:
        if quota is None:
            raise CampaignScaleError(
                "GATE_BLOCK write_campaign_envelopes requires scales= or quota="
            )
        scale_list = [resolve_campaign_scale(quota=quota).scale]
    written: dict[str, dict[str, Path]] = {}
    for scale in scale_list:
        resolved = resolve_campaign_scale(
            scale=scale,
            quota=quota if len(scale_list) == 1 else None,
        )
        written[resolved.scale] = write_scale_envelopes(
            resolved.scale,
            quota=resolved.quota,
            **kwargs,
        )
    return written


__all__ = ["write_campaign_envelopes", "write_scale_envelopes"]

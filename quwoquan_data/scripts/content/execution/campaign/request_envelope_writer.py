"""Atomic active-workload writer for immutable campaign request envelopes."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable, Mapping
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
from content.execution.campaign.request_envelope_identity import (
    assert_one_handoff_identity as _assert_one_handoff_identity,
    assert_one_source_identity as _assert_one_source_identity,
)
from content.execution.campaign.scale import campaign_workload_targets, resolve_campaign_scale
from content.execution.controller.execute.pre_acquisition_handoff import (
    load_pre_acquisition_handoff,
)
from content.execution.identity import parse_execution_id
from content.execution.model_contract import DEFAULT_SEMANTIC_SELECTION_ID
from content.execution.planning.execution_authority import (
    assert_execution_authority,
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


def _assert_workload_plans(
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    """Hold every carrier of one campaign on a single execution authority.

    `DEC-002` moved partition count and `capacityPlanDigest` to the execution
    freeze, so the envelope no longer carries them. What the envelope must still
    guarantee is that all carriers were admitted against the same mutually
    exclusive authority and that no host slice was pre-bound here.
    """
    authorities = set()
    for payload in payloads.values():
        authority = payload.get("executionAuthority")
        if not isinstance(authority, Mapping):
            raise ValueError("campaign envelope execution authority is missing")
        assert_execution_authority(authority)
        authorities.add(
            json.dumps(dict(authority), sort_keys=True, separators=(",", ":"))
        )
        if payload.get("workerHostSetBinding") is not None:
            raise ValueError("campaign envelope must not pre-bind a worker host set")
    if len(authorities) > 1:
        raise ValueError("campaign carriers disagree on the execution authority")


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
    workload_mode = str(first.get("workloadMode") or "")
    expected_target_scale = "WORKLOAD" if workload_mode == "explicit" else scale
    if (
        binding.get("targetScale") != expected_target_scale
        or binding.get("workloadMode") != workload_mode
        or binding.get("activeCarriers") != list(payloads)
        or binding.get("workloadTargets") != first.get("workloads")
    ):
        raise ValueError("DATA.SOURCE.POOL_SHORTFALL: pool workload binding drift")


def write_scale_envelopes(
    scale: str | None = None,
    *,
    quota: int | None = None,
    target_names: Iterable[str] | None = None,
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
    capacity_calibration_receipt: Path | None = None,
    capacity_calibration_output_root: Path | None = None,
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
    batch_documents_factory: Callable[
        [Mapping[str, Mapping[str, Any]], Mapping[str, Path]],
        Mapping[str, Mapping[str, Any]],
    ]
    | None = None,
) -> dict[str, Path]:
    """Write immutable envelopes for selected carriers at one resolved scale."""

    if pre_acquisition_handoff is None:
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.HANDOFF_REQUIRED: campaign envelopes "
            "require a confirmed pre-acquisition handoff"
        )
    handoff_document = load_pre_acquisition_handoff(
        pre_acquisition_handoff.expanduser().resolve()
    )
    vertical = str(handoff_document["vertical"])
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
            target_names=target_input,
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
            capacity_calibration_receipt=capacity_calibration_receipt,
            capacity_calibration_output_root=capacity_calibration_output_root,
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
    first_identity = parse_execution_id(str(payloads[selected[0]]["executionId"]))
    replay_target_root = envelope_path(
        resolved.scale,
        selected[0],
        scope=first_identity.scope,
        vertical=vertical,
        root=output_root,
        sequence=first_identity.sequence,
    ).parent
    replay_first = replay_target_root / f"{selected[0]}.json"
    if replay_first.is_file():
        existing_first = read_json(replay_first)
        if not isinstance(existing_first, Mapping):
            raise TypeError("existing campaign envelope must be an object")
        batch_frozen_at = str(existing_first.get("frozenAt") or "")
    else:
        batch_frozen_at = str(payloads[selected[0]]["frozenAt"])
    for payload in payloads.values():
        payload["frozenAt"] = batch_frozen_at
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
            if key != "requestDigest"
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
        written[carrier] = path
    target_roots = {path.parent for path in written.values()}
    if len(target_roots) != 1:
        raise ValueError("campaign envelope batch resolved multiple commit roots")
    target_root = next(iter(target_roots))
    extra_documents = (
        dict(batch_documents_factory(payloads, written))
        if batch_documents_factory is not None
        else {}
    )
    documents: dict[str, Mapping[str, Any]] = {
        f"{carrier}.json": payload for carrier, payload in payloads.items()
    }
    for filename, document in extra_documents.items():
        if (
            not filename.endswith(".json")
            or Path(filename).name != filename
            or filename in documents
            or not isinstance(document, Mapping)
        ):
            raise ValueError(f"campaign envelope batch document is invalid: {filename}")
        documents[filename] = document
    if target_root.exists():
        observed_entries = {path.name: path for path in target_root.iterdir()}
        if set(observed_entries) != set(documents) or any(
            not path.is_file() for path in observed_entries.values()
        ):
            raise ValueError(
                f"campaign envelope batch is partial or has foreign files: {target_root}"
            )
        for filename, document in documents.items():
            existing = read_json(target_root / filename)
            if filename in {f"{carrier}.json" for carrier in payloads}:
                assert_valid(
                    existing,
                    "execution",
                    "content_campaign_request_envelope",
                    label=f"existing campaign envelope:{filename}",
                )
                existing_stable = {
                    key: value
                    for key, value in existing.items()
                    if key != "requestDigest"
                }
                candidate_stable = {
                    key: value
                    for key, value in document.items()
                    if key != "requestDigest"
                }
                if (
                    existing.get("requestDigest") != _sha256(existing_stable)
                    or document.get("requestDigest") != _sha256(candidate_stable)
                    or existing_stable != candidate_stable
                ):
                    raise ValueError(
                        "campaign envelope already frozen with different digest: "
                        f"{target_root / filename}"
                    )
            elif existing != document:
                raise ValueError(
                    f"campaign envelope batch document collision: {target_root / filename}"
                )
        return written
    target_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{target_root.name}.", dir=target_root.parent)
    )
    try:
        for filename, document in documents.items():
            write_json(staging_root / filename, document)
        directory_fd = os.open(staging_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(staging_root, target_root)
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise
    return written


__all__ = ["write_scale_envelopes"]

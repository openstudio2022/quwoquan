"""Atomic four-lane writer for immutable campaign request envelopes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.process import CAMPAIGN_CARRIERS
from content.execution.campaign.request_envelope import (
    _OPERATIONS,
    _require_stable_source_inputs,
    build_envelope,
    envelope_path,
)
from content.execution.model_contract import DEFAULT_SEMANTIC_SELECTION_ID
from content.execution.campaign.scale import CampaignScaleError, resolve_campaign_scale


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
    if not isinstance(submissions, Mapping) or set(submissions) != set(
        CAMPAIGN_CARRIERS
    ):
        raise ValueError("campaign predecessor reconciliation is incomplete")
    predecessors = {
        carrier: str(submissions[carrier]["executionId"])
        for carrier in CAMPAIGN_CARRIERS
    }
    targets = tuple(submissions["homepage"]["targetNames"])
    if any(
        tuple(submissions[carrier]["targetNames"]) != targets
        for carrier in CAMPAIGN_CARRIERS
    ):
        raise ValueError("campaign predecessor reconciliation targetNames drift")
    if tuple(sorted(set(targets))) != targets:
        raise ValueError(
            "campaign predecessor reconciliation targetNames are not canonical"
        )
    if retry_predecessors and dict(retry_predecessors) != predecessors:
        raise ValueError(
            "campaign retry predecessors differ from reconciliation receipt"
        )
    requested = tuple(
        sorted({str(item).strip() for item in target_names if str(item).strip()})
    )
    if requested and requested != targets:
        raise ValueError(
            "campaign retry targetNames differ from reconciliation receipt"
        )
    original = receipt.get("originalSourceIdentity")
    if not isinstance(original, Mapping):
        raise TypeError(
            "campaign predecessor reconciliation original identity is invalid"
        )
    return (
        predecessors,
        targets,
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
    if predecessor_reconciliation_receipt.get("reason") != "source_drift":
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
    carriers: Iterable[str] = CAMPAIGN_CARRIERS,
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
    pre_acquisition_handoff: Path | None = None,
    pre_acquisition_handoff_output_root: Path | None = None,
    external_input_refs_by_carrier: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    acquisition_root: Path | None = None,
) -> dict[str, Path]:
    """Write immutable envelopes for selected carriers at one resolved scale."""

    resolved = resolve_campaign_scale(scale=scale, quota=quota)
    selected = tuple(carriers) or CAMPAIGN_CARRIERS
    unknown = [carrier for carrier in selected if carrier not in _OPERATIONS]
    if unknown:
        raise ValueError(f"unsupported carriers: {unknown}")
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
    required = set(CAMPAIGN_CARRIERS)
    if sequence > 1 and (
        len(selected) != len(required)
        or set(selected) != required
        or set(retry_predecessors) != required
    ):
        raise ValueError(
            "campaign envelope sequence>1 requires complete four-carrier retry predecessors"
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
            semantic_selection_id=semantic_selection_id,
            semantic_preflight_receipt=semantic_preflight_receipt,
            semantic_preflight_output_root=semantic_preflight_output_root,
            predecessor_reconciliation=predecessor_reconciliation,
            promotion_receipt=promotion_receipt,
            pre_acquisition_handoff=pre_acquisition_handoff,
            pre_acquisition_handoff_output_root=pre_acquisition_handoff_output_root,
            external_input_refs=(external_input_refs_by_carrier or {}).get(carrier, ()),
            acquisition_root=acquisition_root,
        )
        assert_valid(
            payload,
            "execution",
            "content_campaign_request_envelope",
            label=f"campaign envelope:{resolved.scale}:{carrier}",
        )
        payloads[carrier] = payload
    _assert_one_source_identity(
        payloads,
        predecessor_reconciliation_receipt=reconciliation_receipt,
    )
    _assert_one_handoff_identity(payloads)
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    frozen_source = next(iter(payloads.values()))["sourceDigest"]
    if not isinstance(frozen_source, dict):
        raise TypeError("campaign envelope sourceDigest document is invalid")
    _require_stable_source_inputs(frozen_source, repo_root=source_repo)

    written: dict[str, Path] = {}
    for carrier, payload in payloads.items():
        path = envelope_path(
            resolved.scale,
            carrier,
            vertical=vertical,
            root=output_root,
            sequence=sequence,
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

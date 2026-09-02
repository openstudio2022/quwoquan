"""Immutable carrier request envelopes for copy-session operators."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

from content.execution.planning.carrier_demand import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.planning.scale import (
    resolve_campaign_scale,
)
from content.execution.identity import build_execution_id
from content.execution.model_contract import (
    DEFAULT_SEMANTIC_SELECTION_ID,
)
from content.release.canonical.research_scale_predecessor import (
    ResearchScalePredecessorError,
    load_predecessor_promotion,
)

ENVELOPE_SCHEMA = "quwoquan_data.content_campaign_request_envelope"

_SCOPE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VERTICAL_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def envelopes_root(*, root: Path | None = None) -> Path:
    return (root or paths.DATA_LOCAL_ROOT) / "workspace" / "content-campaign-envelopes"


def scale_root(
    scale: str,
    *,
    scope: str,
    vertical: str = "travel",
    root: Path | None = None,
    sequence: int = 1,
) -> Path:
    resolved = resolve_campaign_scale(scale=scale)
    vertical_id = _normalize_vertical(vertical)
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("campaign envelope sequence must be a positive integer")
    scope_id = str(scope).strip()
    if not _SCOPE_TOKEN_RE.fullmatch(scope_id):
        raise ValueError("campaign envelope scope token is invalid")
    return (
        envelopes_root(root=root)
        / vertical_id
        / resolved.scale
        / scope_id
        / f"sequence-{sequence:03d}"
    )


def envelope_path(
    scale: str,
    carrier: str,
    *,
    scope: str,
    vertical: str = "travel",
    root: Path | None = None,
    sequence: int = 1,
) -> Path:
    if carrier not in CAMPAIGN_CARRIERS:
        raise ValueError(f"unsupported carrier: {carrier}")
    parent = scale_root(
        scale,
        scope=scope,
        vertical=vertical,
        root=root,
        sequence=sequence,
    )
    return parent / f"{carrier}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _git_commit(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_branch(repo_root: Path) -> str:
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not branch:
        raise ValueError("campaign envelope requires a named frozen main branch")
    return branch


def _require_stable_source_inputs(
    source_document: dict[str, object],
    *,
    execution_bundle: dict[str, object],
    repo_root: Path,
) -> None:
    """Reject content drift, without requiring a shared worktree to be clean."""
    observed = current_source_definition_snapshot(repo_root=repo_root).to_document()
    observed_bundle = current_execution_bundle_identity(
        repo_root=repo_root
    ).to_document()
    if observed != source_document or observed_bundle != execution_bundle:
        raise ValueError(
            "campaign envelope source snapshot/execution bundle changed during freeze"
        )


def _normalize_vertical(vertical: str) -> str:
    value = str(vertical or "").strip().lower()
    if not _VERTICAL_RE.fullmatch(value):
        raise ValueError(f"GATE_BLOCK unsupported campaign vertical: {vertical}")
    return value


def _slug_token(value: str, *, label: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not token or not _SCOPE_TOKEN_RE.fullmatch(token):
        raise ValueError(f"GATE_BLOCK campaign {label} is not a valid scope token: {value}")
    return token


def normalize_execution_scope(
    region_ref: str,
    topic: str | None = None,
) -> str:
    parts = [part for part in str(region_ref or "").strip().strip("/").split("/") if part]
    if not parts:
        raise ValueError("GATE_BLOCK regionRef must be non-empty")
    base = None
    for part in parts:
        candidate = part.strip().lower()
        if _SCOPE_TOKEN_RE.fullmatch(candidate):
            base = candidate
            break
    if base is None:
        base = _slug_token(parts[0], label="regionRef")
    if topic is None or not str(topic).strip():
        return base
    return f"{base}-{_slug_token(str(topic), label='topic')}"


def default_family_ref(*, vertical: str, carrier: str) -> str:
    if carrier not in CAMPAIGN_CARRIERS:
        raise ValueError(f"unsupported carrier: {carrier}")
    return f"content/{vertical}/{carrier}/{carrier}"


def _execution_ids(
    *,
    intent: str,
    vertical: str,
    scope: str,
    day: str,
    carriers: Iterable[str],
    sequence: int = 1,
) -> dict[str, str]:
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("campaign envelope sequence must be a positive integer")
    return {
        carrier: build_execution_id(
            run_date=day,
            vertical=vertical,
            content_type=carrier,
            intent=intent,
            scope=scope,
            phase="scale",
            sequence=sequence,
        )
        for carrier in normalize_active_carriers(carriers)
    }


def workload_intent(
    *,
    scale: str,
    workload_mode: str,
    workloads: Mapping[str, int],
) -> str:
    """Keep explicit workload identities distinct from milestone promotions."""

    active = normalize_workloads(workloads)
    if workload_mode == "milestone_preset":
        if tuple(active) != CAMPAIGN_CARRIERS:
            raise ValueError("milestone preset must expand all campaign carriers")
        return scale.lower()
    if workload_mode != "explicit":
        raise ValueError(f"unsupported campaign workload mode: {workload_mode}")
    return "workload-" + "-".join(
        f"{carrier}-{active[carrier]}" for carrier in active
    )


def _research_scale_promotion_ref(
    receipt_path: Path | None,
    *,
    next_scale: str,
    source_digest: dict[str, Any],
    entity_catalog_digest: str,
    source_revision: str,
    output_root: Path,
) -> dict[str, Any]:
    try:
        reference, carried = load_predecessor_promotion(
            receipt_path,
            target_scale=next_scale,
            source_revision=source_revision,
            source_digest=str(source_digest.get("digest") or ""),
            entity_catalog_digest=entity_catalog_digest,
            output_root=output_root,
        )
    except ResearchScalePredecessorError as exc:
        raise ValueError(str(exc)) from exc
    if reference is None:
        raise ValueError(f"{next_scale} requires a predecessor promotion")
    return {
        **reference,
        "carrierCounts": [
            {"carrier": carrier, "totalUniqueFinalizedCount": carried[carrier]}
            for carrier in CAMPAIGN_CARRIERS
        ],
    }


from content.execution.planning.request_envelope_build import build_envelope


def load_campaign_envelope(
    path: Path,
    *,
    semantic_preflight_output_root: Path | None = None,
) -> dict[str, Any]:
    from content.execution.planning.request_envelope_io import (
        load_campaign_envelope as load_envelope,
    )

    return load_envelope(
        path,
        semantic_preflight_output_root=semantic_preflight_output_root,
    )


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
    from content.execution.planning.request_envelope_writer import (
        write_scale_envelopes as write_atomic_scale_envelopes,
    )

    return write_atomic_scale_envelopes(
        scale,
        quota=quota,
        target_names=target_names,
        family_ref=family_ref,
        carriers=carriers,
        workloads=workloads,
        repo_root=repo_root,
        output_root=output_root,
        day=day,
        sequence=sequence,
        semantic_selection_id=semantic_selection_id,
        semantic_preflight_receipt=semantic_preflight_receipt,
        semantic_preflight_output_root=semantic_preflight_output_root,
        capacity_calibration_receipt=capacity_calibration_receipt,
        capacity_calibration_output_root=capacity_calibration_output_root,
        predecessor_execution_ids_by_carrier=predecessor_execution_ids_by_carrier,
        predecessor_reconciliation_receipt=predecessor_reconciliation_receipt,
        reconciliation_output_root=reconciliation_output_root,
        promotion_receipt=promotion_receipt,
        promotion_output_root=promotion_output_root,
        pre_acquisition_handoff=pre_acquisition_handoff,
        pre_acquisition_handoff_output_root=pre_acquisition_handoff_output_root,
        external_input_refs_by_carrier=external_input_refs_by_carrier,
        acquisition_root=acquisition_root,
        scale_source_pool=scale_source_pool,
        source_pool_evidence_root=source_pool_evidence_root,
        retry_evidence_output_root=retry_evidence_output_root,
        batch_documents_factory=batch_documents_factory,
    )


__all__ = [
    "build_envelope",
    "default_family_ref",
    "envelope_path",
    "envelopes_root",
    "load_campaign_envelope",
    "normalize_execution_scope",
    "read_json",
    "scale_root",
    "write_scale_envelopes",
]

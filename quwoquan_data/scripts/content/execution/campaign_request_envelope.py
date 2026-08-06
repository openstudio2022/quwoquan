"""Immutable carrier request envelopes for copy-session operators."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import current_source_digest
from governance.coverage.distribution import load_content_distribution_policy

from content.execution.campaign_external_inputs import (
    bind_external_input_refs,
    content_source_revision,
    external_inputs_digest,
)
from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_scale import (
    CampaignScaleError,
    resolve_campaign_scale,
)
from content.execution.campaign_submission_reconciliation import (
    load_submission_reconciliation_receipt,
    reconciliation_reference,
)
from content.execution.identity import build_execution_id, parse_execution_id
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    normalize_semantic_selection_id,
)
from content.execution.request import resolve_candidate_pool
from content.execution.runtime_contract import file_sha256
from content.execution.semantic_preflight_admission import bind_semantic_preflight_receipt
from content.execution.workspace import entity_catalog_digest

ENVELOPE_SCHEMA = "quwoquan_data.content_campaign_request_envelope"

_OPERATIONS = {
    "homepage": "homepage.generate",
    "article": "article.generate",
    "image": "image.generate",
    "video": "video.generate",
}
_SELECTORS = {
    "homepage": "source-ready-priority",
    "article": "priority",
    "image": "priority",
    "video": "source-ready-priority",
}
_OPERATOR_PROMPTS = {
    "homepage": "执行实体内容生成",
    "article": "执行文章内容生成",
    "image": "执行图片内容生成",
    "video": "执行视频内容生成",
}
_SCOPE_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VERTICAL_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def envelopes_root(*, root: Path | None = None) -> Path:
    return (root or paths.DATA_LOCAL_ROOT) / "workspace" / "content-campaign-envelopes"


def scale_root(
    scale: str,
    *,
    vertical: str = "travel",
    root: Path | None = None,
    sequence: int = 1,
) -> Path:
    resolved = resolve_campaign_scale(scale=scale)
    vertical_id = _normalize_vertical(vertical)
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("campaign envelope sequence must be a positive integer")
    scale_path = envelopes_root(root=root) / vertical_id / resolved.scale
    return scale_path if sequence == 1 else scale_path / f"retry-{sequence:03d}"


def envelope_path(
    scale: str,
    carrier: str,
    *,
    vertical: str = "travel",
    root: Path | None = None,
    sequence: int = 1,
) -> Path:
    if carrier not in _OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    parent = scale_root(scale, vertical=vertical, root=root, sequence=sequence)
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
    repo_root: Path,
) -> None:
    """Reject content drift, without requiring a shared worktree to be clean."""
    observed = current_source_digest(repo_root=repo_root).to_document()
    if observed != source_document:
        raise ValueError(
            "campaign envelope sourceDigest inputs changed during freeze"
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
    if carrier not in _OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    return f"content/{vertical}/{carrier}/{carrier}"


def _execution_ids(
    *,
    scale: str,
    vertical: str,
    scope: str,
    day: str,
    sequence: int = 1,
) -> dict[str, str]:
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("campaign envelope sequence must be a positive integer")
    intent = scale.lower()
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
        for carrier in CAMPAIGN_CARRIERS
    }


def _research_m100_promotion_ref(
    receipt_path: Path | None,
    *,
    source_digest: dict[str, Any],
    entity_catalog_digest: str,
    source_revision: str,
) -> dict[str, Any]:
    if receipt_path is None:
        raise ValueError("M1000 requires one canonical four-carrier M100 receipt")
    path = receipt_path.resolve()
    promotion = read_json(path)
    assert_valid(
        promotion,
        "release",
        "research_scale_promotion",
        label=f"research M100 promotion:{path}",
    )
    if (
        promotion.get("targetScale") != "M100"
        or promotion.get("releaseClass") != "research"
        or promotion.get("productLifecycleState") != "research"
        or promotion.get("m1000Eligible") is not True
    ):
        raise ValueError("M1000 requires an eligible research M100 receipt")
    if (
        promotion.get("sourceDigest") != source_digest.get("digest")
        or promotion.get("entityCatalogDigest") != entity_catalog_digest
        or promotion.get("sourceRevision") != source_revision
    ):
        raise ValueError("M1000 M100 receipt source/catalog identity drift")
    return {
        "promotionId": str(promotion["promotionId"]),
        "releaseId": str(promotion["releaseId"]),
        "manifestDigest": str(promotion["manifestDigest"]),
        "sourceRevision": str(promotion["sourceRevision"]),
        "sourceDigest": str(promotion["sourceDigest"]),
        "entityCatalogDigest": str(promotion["entityCatalogDigest"]),
        "receiptRef": path.as_posix(),
        "receiptDigest": file_sha256(path),
    }


def build_envelope(
    *,
    scale: str | None = None,
    quota: int | None = None,
    carrier: str,
    region_ref: str,
    vertical: str = "travel",
    topic: str | None = None,
    target_names: Iterable[str] | None = None,
    source_providers: Iterable[str] | None = None,
    family_ref: str | None = None,
    repo_root: Path | None = None,
    day: str | None = None,
    sequence: int = 1,
    predecessor_execution_id: str | None = None,
    semantic_selection_id: str = DEFAULT_SEMANTIC_SELECTION_ID,
    semantic_preflight_receipt: Path | None = None,
    semantic_preflight_output_root: Path | None = None,
    predecessor_reconciliation: Mapping[str, Any] | None = None,
    promotion_receipt: Path | None = None,
    external_input_refs: Iterable[Mapping[str, Any]] = (),
    acquisition_root: Path | None = None,
) -> dict[str, Any]:
    if carrier not in _OPERATIONS:
        raise ValueError(f"unsupported carrier: {carrier}")
    resolved = resolve_campaign_scale(scale=scale, quota=quota)
    vertical_id = _normalize_vertical(vertical)
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    policy = load_content_distribution_policy()
    governed_quota = (
        policy.scale_target(resolved.scale, carrier)
        if resolved.scale in {"M100", "M1000"}
        else resolved.quota
    )
    try:
        quota_value, count = resolve_candidate_pool(quota=governed_quota, count=None)
    except SystemExit as exc:
        raise CampaignScaleError(str(exc)) from exc
    source = current_source_digest(repo_root=source_repo).to_document()
    _require_stable_source_inputs(source, repo_root=source_repo)
    discovery = (
        source_repo
        / "quwoquan_data"
        / "reference"
        / vertical_id
        / "entities"
        / region_ref
    )
    if not discovery.is_dir():
        raise ValueError(f"region reference does not exist: {region_ref}")
    catalog_digest = entity_catalog_digest(
        discovery.relative_to(source_repo).as_posix()
    )
    source_revision = content_source_revision(
        source_digest=str(source["digest"]),
        entity_catalog_digest=catalog_digest,
    )
    frozen_external_refs = bind_external_input_refs(
        carrier,
        external_input_refs,
        acquisition_root=(
            acquisition_root or paths.SOURCE_ACQUISITION_ROOT
        ).resolve(),
        source_revision=source_revision,
        source_digest=str(source["digest"]),
        entity_catalog_digest=catalog_digest,
    )
    stamp = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    scope = normalize_execution_scope(region_ref, topic)
    ids = _execution_ids(
        scale=resolved.scale,
        vertical=vertical_id,
        scope=scope,
        day=stamp,
        sequence=sequence,
    )
    retry_of = str(predecessor_execution_id or "").strip() or None
    if sequence == 1 and retry_of is not None:
        raise ValueError("campaign envelope sequence=1 forbids a retry predecessor")
    if sequence > 1 and retry_of is None:
        raise ValueError("campaign envelope sequence>1 requires a retry predecessor")
    if retry_of is not None:
        current, predecessor = map(parse_execution_id, (ids[carrier], retry_of))
        comparable = ("vertical", "content_type", "intent", "scope", "phase")
        if any(getattr(current, key) != getattr(predecessor, key) for key in comparable):
            raise ValueError("campaign envelope retry predecessor must preserve execution scope")
        if predecessor.sequence >= current.sequence:
            raise ValueError("campaign envelope retry predecessor must use an earlier sequence")
    frozen_semantic_selection_id = normalize_semantic_selection_id(
        semantic_selection_id
    )
    semantic_preflight_binding = (
        bind_semantic_preflight_receipt(
            semantic_preflight_receipt,
            semantic_selection_id=frozen_semantic_selection_id,
            output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
        )
        if semantic_preflight_receipt is not None
        else None
    )
    if frozen_semantic_selection_id == CURSOR_AUTO_SEMANTIC_SELECTION_ID:
        from core.runtime_policy import active_runtime_policy

        explicit = active_runtime_policy().explicit_semantic_selection(
            frozen_semantic_selection_id
        )
        if explicit.requires_new_retry_of and retry_of is None:
            raise ValueError(
                "campaign cursor_auto selection requires a new execution with retryOf"
            )
        if semantic_preflight_binding is None:
            raise ValueError(
                "campaign cursor_auto selection requires a fresh semantic preflight receipt"
            )
    reconciliation = (
        dict(predecessor_reconciliation)
        if predecessor_reconciliation is not None
        else None
    )
    if reconciliation is not None:
        if retry_of is None:
            raise ValueError(
                "campaign envelope predecessor reconciliation requires retryOf"
            )
        assert_valid(
            reconciliation,
            "execution",
            "campaign_submission_reconciliation_ref",
            label=f"campaign predecessor reconciliation:{carrier}",
        )
    names = sorted({str(item).strip() for item in (target_names or []) if str(item).strip()})
    providers = sorted(
        {str(item).strip() for item in (source_providers or []) if str(item).strip()}
    )
    topic_value = str(topic).strip() if topic is not None and str(topic).strip() else None
    git_branch = _git_branch(source_repo)
    git_commit_sha = _git_commit(source_repo)
    promotion_reference = (
        _research_m100_promotion_ref(
            promotion_receipt,
            source_digest=source,
            entity_catalog_digest=catalog_digest,
            source_revision=source_revision,
        )
        if resolved.scale == "M1000"
        else None
    )
    stable: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "scale": resolved.scale,
        "carrier": carrier,
        "operation": _OPERATIONS[carrier],
        "vertical": vertical_id,
        "familyRef": family_ref or default_family_ref(
            vertical=vertical_id,
            carrier=carrier,
        ),
        "regionRef": region_ref,
        "selector": _SELECTORS[carrier],
        "quota": quota_value,
        "count": count,
        "topic": topic_value,
        "targetNames": names,
        "sourceProviders": providers,
        "semanticSelectionId": frozen_semantic_selection_id,
        "retryOf": retry_of,
        "rootExecutionId": ids["homepage"],
        "executionId": ids[carrier],
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source,
        "entityCatalogDigest": catalog_digest,
        "externalInputRefs": frozen_external_refs,
        "externalInputsDigest": external_inputs_digest(frozen_external_refs),
        "allowedStage": "submit-only",
        "operatorPrompt": _OPERATOR_PROMPTS[carrier],
    }
    if promotion_reference is not None:
        stable["researchScalePromotion"] = promotion_reference
    if semantic_preflight_binding is not None:
        stable["semanticPreflightReceipt"] = semantic_preflight_binding
    if reconciliation is not None:
        stable["predecessorReconciliation"] = reconciliation
    envelope = {
        **stable,
        "requestDigest": _sha256(stable),
        "frozenAt": _utc_now(),
    }
    _require_stable_source_inputs(source, repo_root=source_repo)
    return envelope


def load_campaign_envelope(
    path: Path,
    *,
    semantic_preflight_output_root: Path | None = None,
) -> dict[str, Any]:
    from content.execution.campaign_request_envelope_io import (
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
    external_input_refs_by_carrier: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    acquisition_root: Path | None = None,
) -> dict[str, Path]:
    """Write immutable envelopes for selected carriers at one resolved scale."""
    from content.execution.campaign_request_envelope_writer import (
        write_scale_envelopes as write_atomic_scale_envelopes,
    )

    return write_atomic_scale_envelopes(
        scale,
        quota=quota,
        region_ref=region_ref,
        vertical=vertical,
        topic=topic,
        target_names=target_names,
        source_providers=source_providers,
        family_ref=family_ref,
        carriers=carriers,
        repo_root=repo_root,
        output_root=output_root,
        day=day,
        sequence=sequence,
        semantic_selection_id=semantic_selection_id,
        semantic_preflight_receipt=semantic_preflight_receipt,
        semantic_preflight_output_root=semantic_preflight_output_root,
        predecessor_execution_ids_by_carrier=predecessor_execution_ids_by_carrier,
        predecessor_reconciliation_receipt=predecessor_reconciliation_receipt,
        reconciliation_output_root=reconciliation_output_root,
        promotion_receipt=promotion_receipt,
        external_input_refs_by_carrier=external_input_refs_by_carrier,
        acquisition_root=acquisition_root,
    )


def write_campaign_envelopes(
    *,
    scales: Iterable[str] | None = None,
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
    external_input_refs_by_carrier: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    acquisition_root: Path | None = None,
) -> dict[str, dict[str, Path]]:
    from content.execution.campaign_request_envelope_writer import (
        write_campaign_envelopes as write_atomic_campaign_envelopes,
    )

    return write_atomic_campaign_envelopes(
        scales=scales,
        quota=quota,
        region_ref=region_ref,
        vertical=vertical,
        topic=topic,
        target_names=target_names,
        source_providers=source_providers,
        family_ref=family_ref,
        carriers=carriers,
        repo_root=repo_root,
        output_root=output_root,
        day=day,
        sequence=sequence,
        semantic_selection_id=semantic_selection_id,
        semantic_preflight_receipt=semantic_preflight_receipt,
        semantic_preflight_output_root=semantic_preflight_output_root,
        predecessor_execution_ids_by_carrier=predecessor_execution_ids_by_carrier,
        predecessor_reconciliation_receipt=predecessor_reconciliation_receipt,
        reconciliation_output_root=reconciliation_output_root,
        promotion_receipt=promotion_receipt,
        external_input_refs_by_carrier=external_input_refs_by_carrier,
        acquisition_root=acquisition_root,
    )


__all__ = [
    "build_envelope",
    "default_family_ref",
    "envelope_path",
    "envelopes_root",
    "load_campaign_envelope",
    "load_submission_reconciliation_receipt",
    "normalize_execution_scope",
    "scale_root",
    "reconciliation_reference",
    "write_campaign_envelopes",
    "write_scale_envelopes",
]

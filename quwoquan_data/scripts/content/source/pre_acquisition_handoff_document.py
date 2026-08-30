"""Canonical pre-acquisition handoff document creation and binding."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    content_source_revision,
)
from content.execution.carrier_contract import normalize_workloads
from content.source.pre_acquisition_handoff_validation import (
    validate_document_carrier_alignment,
    validated_scope_fields,
    validated_source_selection,
)

HANDOFF_SCHEMA = "quwoquan_data.content_pre_acquisition_handoff"
HANDOFFS_RELATIVE_ROOT = Path("data/local/workspace/content-pre-acquisition-handoffs")
LIFECYCLES = ("research", "commercial")
_CARRIER_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "homepage": {
        "externalInputMode": "external_acquisition",
        "requiredExternalInputKinds": ["professional_image_acquisition"],
        "operatorPrompt": "先取得并冻结主页专业图片，再准备 homepage envelope。",
    },
    "article": {
        "externalInputMode": "execution_source_unit_freeze",
        "requiredExternalInputKinds": [],
        "operatorPrompt": (
            "article 预获取不接受外部 acquisition；由 execution 内 sourceUnit "
            "create-once freeze 派生 READY。"
        ),
    },
    "image": {
        "externalInputMode": "external_acquisition",
        "requiredExternalInputKinds": ["professional_image_acquisition"],
        "operatorPrompt": "先取得并冻结图片作品专业图片，再准备 image envelope。",
    },
    "video": {
        "externalInputMode": "external_acquisition",
        "requiredExternalInputKinds": ["professional_video_acquisition"],
        "operatorPrompt": "先取得并冻结可播放专业视频，再准备 video envelope。",
    },
}


class PreAcquisitionHandoffError(ValueError):
    """Typed fail-closed handoff or acquisition identity error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"GATE_BLOCK {code}: {detail}")
        self.code = code


def _typed(code: str, detail: str) -> PreAcquisitionHandoffError:
    return PreAcquisitionHandoffError(f"DATA.CAMPAIGN.PRE_ACQUISITION_{code}", detail)


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_handoff_id(value: object) -> str:
    handoff_id = str(value or "").strip()
    if (
        not handoff_id
        or not handoff_id[0].isalnum()
        or any(
            not (character.islower() or character.isdigit() or character in "._-")
            for character in handoff_id
        )
    ):
        raise _typed("IDENTITY_INVALID", f"invalid handoffId: {value}")
    return handoff_id


def _portable_ref(path: Path, *, output_root: Path) -> str:
    root = output_root.expanduser().resolve()
    resolved = path.expanduser().resolve()
    if resolved == root or root not in resolved.parents:
        raise _typed(
            "PATH_ESCAPE",
            f"handoff evidence must remain under output root: {resolved}",
        )
    return resolved.relative_to(root).as_posix()


def pre_acquisition_handoff_path(
    handoff_id: str,
    handoff_revision: int,
    *,
    output_root: Path | None = None,
) -> Path:
    if (
        isinstance(handoff_revision, bool)
        or not isinstance(handoff_revision, int)
        or handoff_revision < 1
    ):
        raise _typed(
            "REVISION_INVALID",
            "handoffRevision must be a positive integer",
        )
    root = (output_root or paths.OUTPUT_ROOT).expanduser().resolve()
    return (
        root
        / HANDOFFS_RELATIVE_ROOT
        / _safe_handoff_id(handoff_id)
        / f"revision-{handoff_revision:03d}.json"
    )


def _require_canonical_handoff_location(
    path: Path,
    handoff: Mapping[str, Any],
    *,
    output_root: Path | None = None,
) -> None:
    resolved = path.expanduser().resolve()
    handoff_id = _safe_handoff_id(handoff.get("handoffId"))
    revision = handoff.get("handoffRevision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise _typed("LOCATION_INVALID", "handoffRevision cannot resolve canonical path")
    if output_root is not None:
        expected = pre_acquisition_handoff_path(
            handoff_id,
            revision,
            output_root=output_root,
        )
        if resolved != expected:
            raise _typed(
                "LOCATION_INVALID",
                f"handoff must use canonical create-once path: {expected}",
            )
        return
    suffix = (
        HANDOFFS_RELATIVE_ROOT
        / handoff_id
        / f"revision-{revision:03d}.json"
    )
    if tuple(resolved.parts[-len(suffix.parts) :]) != suffix.parts:
        raise _typed(
            "LOCATION_INVALID",
            f"handoff is outside canonical create-once layout: {resolved}",
        )


def _load_superseded_handoff_identity(path: Path) -> dict[str, Any]:
    """Load a retired revision by identity + digest integrity only.

    Superseded revisions are immutable evidence frozen under the schema of
    their own creation time; they are referenced by downstream create-once
    receipts and must never be rewritten.  The supersession chain only needs
    the prior identity triple and its self-consistent handoffDigest, so a
    contract rename in the active schema must not invalidate the chain.
    Active handoffs keep going through the fully validating loader.
    """
    handoff = read_json(path.expanduser().resolve())
    if not isinstance(handoff, dict):
        raise _typed("INVALID", "superseded handoff must be an object")
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise _typed("INVALID", f"superseded handoff schema mismatch: {path}")
    stable = {
        key: value
        for key, value in handoff.items()
        if key not in {"handoffDigest", "createdAt"}
    }
    if handoff.get("handoffDigest") != _digest(stable):
        raise _typed("DIGEST_DRIFT", f"superseded handoffDigest drift: {path}")
    return handoff


def _supersedes_reference(
    *,
    handoff_id: str,
    handoff_revision: int,
    supersedes_handoff: Path | None,
    output_root: Path,
) -> dict[str, Any] | None:
    if handoff_revision == 1:
        if supersedes_handoff is not None:
            raise _typed(
                "SUPERSEDES_INVALID",
                "handoffRevision=1 forbids supersedes evidence",
            )
        return None
    if supersedes_handoff is None:
        raise _typed(
            "SUPERSEDES_REQUIRED",
            "handoffRevision>1 requires explicit supersedes evidence",
        )
    path = supersedes_handoff.expanduser().resolve()
    prior = _load_superseded_handoff_identity(path)
    _require_canonical_handoff_location(
        path,
        prior,
        output_root=output_root,
    )
    prior_id = str(prior.get("handoffId") or "").strip()
    prior_revision = prior.get("handoffRevision")
    if prior_id != handoff_id or prior_revision != handoff_revision - 1:
        raise _typed(
            "SUPERSEDES_INVALID",
            "superseded handoff must be the immediately previous revision "
            f"of {handoff_id}",
        )
    return {
        "handoffId": prior_id,
        "handoffRevision": int(prior_revision),
        "handoffRef": _portable_ref(path, output_root=output_root),
        "handoffFileDigest": _file_digest(path),
    }


def build_pre_acquisition_handoff(
    *,
    handoff_id: str,
    handoff_revision: int,
    supersedes_handoff: Path | None,
    scale: str,
    vertical: str,
    lifecycle: str,
    scope_type: str,
    region_ref: str | None,
    primary_topic_ref: str | None,
    related_topic_refs: Sequence[str] = (),
    source_selection: Mapping[str, Any],
    run_date: str,
    campaign_sequence: int,
    campaign_retry_of: str | None,
    source_digest: Mapping[str, Any],
    execution_bundle: Mapping[str, Any],
    entity_catalog_digest: str,
    workload_targets: Mapping[str, int],
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Build one canonical handoff without writing execution or campaign state."""
    resolved_output = (output_root or paths.OUTPUT_ROOT).expanduser().resolve()
    handoff_id_value = _safe_handoff_id(handoff_id)
    vertical_value = str(vertical or "").strip().lower()
    if not vertical_value:
        raise _typed(
            "VERTICAL_REQUIRED",
            "vertical is an explicit demand input; silent defaults are forbidden",
        )
    lifecycle_value = str(lifecycle or "").strip()
    if lifecycle_value not in LIFECYCLES:
        raise _typed("LIFECYCLE_INVALID", f"lifecycle must be one of {LIFECYCLES}")
    scope_fields = validated_scope_fields(
        scope_type=str(scope_type or "").strip(),
        vertical=vertical_value,
        region_ref=region_ref,
        primary_topic_ref=primary_topic_ref,
        related_topic_refs=related_topic_refs,
        error_factory=_typed,
    )
    source = SourceDefinitionSnapshot.from_document(source_digest)
    bundle = ExecutionBundleIdentity.from_document(execution_bundle)
    catalog_digest = str(entity_catalog_digest or "").strip()
    revision = content_source_revision(
        source_digest=source.digest,
        entity_catalog_digest=catalog_digest,
    )
    try:
        targets = normalize_workloads(workload_targets)
    except ValueError as exc:
        raise _typed("WORKLOAD_INVALID", str(exc)) from exc
    active_carriers = list(targets)
    selection = validated_source_selection(
        source_selection,
        vertical=vertical_value,
        active_carriers=active_carriers,
        error_factory=_typed,
    )
    retry_of = str(campaign_retry_of or "").strip() or None
    if campaign_sequence == 1 and retry_of is not None:
        raise _typed(
            "LINEAGE_INVALID",
            "campaignSequence=1 requires campaignRetryOf=null",
        )
    if campaign_sequence > 1 and retry_of is None:
        raise _typed(
            "LINEAGE_INVALID",
            "campaignSequence>1 requires campaignRetryOf",
        )
    stable: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "handoffId": handoff_id_value,
        "handoffRevision": handoff_revision,
        "supersedes": _supersedes_reference(
            handoff_id=handoff_id_value,
            handoff_revision=handoff_revision,
            supersedes_handoff=supersedes_handoff,
            output_root=resolved_output,
        ),
        "scale": str(scale),
        "vertical": vertical_value,
        "lifecycle": lifecycle_value,
        **scope_fields,
        "runDate": str(run_date),
        "campaignSequence": campaign_sequence,
        "campaignRetryOf": retry_of,
        "sourceRevision": revision,
        "sourceDigest": source.to_document(),
        "executionBundle": bundle.to_document(),
        "entityCatalogDigest": catalog_digest,
        "activeCarriers": active_carriers,
        "workloadTargets": targets,
        "sourceSelection": selection,
        "sourceMutationPolicy": {
            "mode": "immutable_after_handoff",
            "driftAction": "GATE_BLOCK",
            "nextRevisionAction": "create_superseding_handoff",
        },
        "carrierRequirements": {
            carrier: dict(_CARRIER_REQUIREMENTS[carrier])
            for carrier in active_carriers
        },
    }
    handoff = {
        **stable,
        "handoffDigest": _digest(stable),
        "createdAt": _utc_now(),
    }
    assert_valid(
        handoff,
        "execution",
        "content_pre_acquisition_handoff",
        label=f"pre-acquisition handoff:{handoff_id_value}:{handoff_revision}",
    )
    return handoff


def load_pre_acquisition_handoff(path: Path) -> dict[str, Any]:
    handoff = read_json(path.expanduser().resolve())
    if not isinstance(handoff, dict):
        raise _typed("INVALID", "pre-acquisition handoff must be an object")
    try:
        assert_valid(
            handoff,
            "execution",
            "content_pre_acquisition_handoff",
            label=f"pre-acquisition handoff:{path}",
        )
    except ValueError as exc:
        raise _typed("INVALID", str(exc)) from exc
    stable = {
        key: value
        for key, value in handoff.items()
        if key not in {"handoffDigest", "createdAt"}
    }
    if handoff.get("handoffDigest") != _digest(stable):
        raise _typed("DIGEST_DRIFT", f"handoffDigest drift: {path}")
    try:
        targets = normalize_workloads(
            handoff.get("workloadTargets", {}),
            active_carriers=handoff.get("activeCarriers", ()),
        )
    except (TypeError, ValueError) as exc:
        raise _typed("WORKLOAD_INVALID", str(exc)) from exc
    validate_document_carrier_alignment(
        handoff,
        targets,
        error_factory=_typed,
    )
    _require_canonical_handoff_location(path, handoff)
    return handoff


def carrier_source_providers(
    handoff: Mapping[str, Any],
    carrier: str,
) -> list[str]:
    """Project one carrier's declared source providers out of the handoff.

    `sourceSelection` is the only owner of per-carrier provider intent, so this
    projection is the single path from demand to envelope; callers never pass an
    independent provider list.
    """
    selection = handoff.get("sourceSelection")
    if not isinstance(selection, Mapping):
        raise _typed(
            "SOURCE_SELECTION_INVALID",
            "handoff sourceSelection must be a carrier mapping",
        )
    row = selection.get(carrier)
    if not isinstance(row, Mapping):
        raise _typed(
            "SOURCE_SELECTION_INVALID",
            f"handoff sourceSelection has no entry for carrier {carrier}",
        )
    providers = [str(item or "").strip() for item in (row.get("providers") or [])]
    if not providers or any(not item for item in providers):
        raise _typed(
            "SOURCE_SELECTION_INVALID",
            f"handoff sourceSelection.{carrier}.providers must be non-empty",
        )
    return sorted(set(providers))


def write_pre_acquisition_handoff(
    *,
    output_root: Path | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], Path]:
    """Atomically create one revision; idempotent replay never rewrites evidence."""
    resolved_output = (output_root or paths.OUTPUT_ROOT).expanduser().resolve()
    handoff = build_pre_acquisition_handoff(
        output_root=resolved_output,
        **kwargs,
    )
    path = pre_acquisition_handoff_path(
        str(handoff["handoffId"]),
        int(handoff["handoffRevision"]),
        output_root=resolved_output,
    )
    if path.is_file():
        existing = load_pre_acquisition_handoff(path)
        if existing["handoffDigest"] != handoff["handoffDigest"]:
            raise _typed(
                "COLLISION",
                f"handoff revision already exists with another digest: {path}",
            )
        return existing, path
    body = json.dumps(handoff, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = load_pre_acquisition_handoff(path)
        if existing["handoffDigest"] != handoff["handoffDigest"]:
            raise _typed(
                "COLLISION",
                f"handoff revision concurrently created with another digest: {path}",
            )
        return existing, path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return handoff, path


def _identity_drift(
    document: Mapping[str, Any],
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> list[str]:
    expected = {
        "sourceRevision": source_revision,
        "entityCatalogDigest": entity_catalog_digest,
    }
    observed_source = document.get("sourceDigest")
    expected["sourceDigest"] = (
        observed_source.get("digest")
        if isinstance(observed_source, Mapping)
        else observed_source
    )
    values = {
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    return [key for key, value in values.items() if expected[key] != value]


def bind_pre_acquisition_handoff(
    handoff_ref: Path | None,
    *,
    scale: str,
    run_date: str,
    campaign_sequence: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bind one confirmed handoff by identity only.

    Demand facts (vertical, lifecycle, scope, topic refs, sourceSelection)
    are owned by the handoff itself and must be read from the returned
    document; callers cannot supply independent expectations for them.
    """
    if handoff_ref is None:
        raise _typed("HANDOFF_REQUIRED", "explicit handoffRef is required")
    resolved_output = (output_root or paths.OUTPUT_ROOT).expanduser().resolve()
    path = handoff_ref.expanduser().resolve()
    handoff = load_pre_acquisition_handoff(path)
    _require_canonical_handoff_location(
        path,
        handoff,
        output_root=resolved_output,
    )
    expected = {
        "scale": scale,
        "runDate": run_date,
        "campaignSequence": campaign_sequence,
    }
    drift = [key for key, value in expected.items() if handoff.get(key) != value]
    drift.extend(
        _identity_drift(
            handoff,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    )
    if drift:
        raise _typed(
            "IDENTITY_DRIFT",
            "handoff does not match envelope inputs: "
            + ", ".join(sorted(set(drift))),
        )
    binding = {
        "handoffId": str(handoff["handoffId"]),
        "handoffRevision": int(handoff["handoffRevision"]),
        "handoffRef": _portable_ref(path, output_root=resolved_output),
        "handoffDigest": str(handoff["handoffDigest"]),
        "handoffFileDigest": _file_digest(path),
    }
    return handoff, binding

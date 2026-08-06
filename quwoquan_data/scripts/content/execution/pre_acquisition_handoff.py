"""Create-once pre-acquisition identity handoff and shared drift guard."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid
from core.source_digest import (
    SourceDigest,
    content_source_revision,
    current_source_digest,
)

HANDOFF_SCHEMA = "quwoquan_data.content_pre_acquisition_handoff"
HANDOFFS_RELATIVE_ROOT = Path("data/local/workspace/content-pre-acquisition-handoffs")
_CARRIERS = ("homepage", "article", "image", "video")
_CARRIER_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "homepage": {
        "phase1Mode": "external_acquisition",
        "requiredExternalInputKinds": ["professional_image_acquisition"],
        "operatorPrompt": "先取得并冻结主页专业图片，再准备 homepage envelope。",
    },
    "article": {
        "phase1Mode": "execution_source_unit_freeze",
        "requiredExternalInputKinds": [],
        "operatorPrompt": (
            "article phase1 不接受外部 acquisition；由 execution 内 sourceUnit "
            "create-once freeze 派生 READY。"
        ),
    },
    "image": {
        "phase1Mode": "external_acquisition",
        "requiredExternalInputKinds": ["professional_image_acquisition"],
        "operatorPrompt": "先取得并冻结图片作品专业图片，再准备 image envelope。",
    },
    "video": {
        "phase1Mode": "external_acquisition",
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
    prior = load_pre_acquisition_handoff(path)
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
    scope: str,
    region_ref: str,
    topic: str | None,
    run_date: str,
    campaign_sequence: int,
    campaign_retry_of: str | None,
    source_digest: Mapping[str, Any],
    entity_catalog_digest: str,
    workload_targets: Mapping[str, int],
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Build one canonical handoff without writing execution or campaign state."""
    resolved_output = (output_root or paths.OUTPUT_ROOT).expanduser().resolve()
    handoff_id_value = _safe_handoff_id(handoff_id)
    source = SourceDigest.from_document(source_digest)
    catalog_digest = str(entity_catalog_digest or "").strip()
    revision = content_source_revision(
        source_digest=source.digest,
        entity_catalog_digest=catalog_digest,
    )
    if set(workload_targets) != set(_CARRIERS) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in workload_targets.values()
    ):
        raise _typed(
            "WORKLOAD_INVALID",
            "workloadTargets must contain four positive carrier targets",
        )
    targets = {
        carrier: int(workload_targets[carrier])
        for carrier in _CARRIERS
    }
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
        "vertical": str(vertical),
        "scope": str(scope),
        "regionRef": str(region_ref),
        "topic": str(topic).strip() if topic is not None and str(topic).strip() else None,
        "runDate": str(run_date),
        "campaignSequence": campaign_sequence,
        "campaignRetryOf": retry_of,
        "sourceRevision": revision,
        "sourceDigest": source.to_document(),
        "entityCatalogDigest": catalog_digest,
        "workloadTargets": targets,
        "sourceMutationPolicy": {
            "mode": "immutable_after_handoff",
            "driftAction": "GATE_BLOCK",
            "nextRevisionAction": "create_superseding_handoff",
        },
        "carrierRequirements": {
            carrier: dict(_CARRIER_REQUIREMENTS[carrier])
            for carrier in _CARRIERS
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
    _require_canonical_handoff_location(path, handoff)
    return handoff


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
    vertical: str,
    scope: str,
    region_ref: str,
    topic: str | None,
    run_date: str,
    campaign_sequence: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
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
        "vertical": vertical,
        "scope": scope,
        "regionRef": region_ref,
        "topic": str(topic).strip() if topic is not None and str(topic).strip() else None,
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


def validate_carrier_phase1_requirements(
    handoff: Mapping[str, Any],
    *,
    carrier: str,
    external_input_refs: Iterable[Mapping[str, Any]],
) -> None:
    requirements = handoff.get("carrierRequirements")
    if not isinstance(requirements, Mapping) or carrier not in requirements:
        raise _typed("INVALID", f"missing carrier requirement: {carrier}")
    requirement = requirements[carrier]
    if not isinstance(requirement, Mapping):
        raise _typed("INVALID", f"invalid carrier requirement: {carrier}")
    required = tuple(requirement.get("requiredExternalInputKinds") or ())
    observed = tuple(
        str(row.get("kind") or "")
        for row in external_input_refs
        if isinstance(row, Mapping)
    )
    if not required:
        if observed:
            raise _typed(
                "ARTICLE_EXTERNAL_INPUT_FORBIDDEN",
                "article READY must derive from governed sourceUnit freeze",
            )
        return
    if not observed or any(kind not in required for kind in observed):
        raise _typed(
            "EXTERNAL_INPUT_REQUIRED",
            f"{carrier} requires phase1 inputs of kind {', '.join(required)}",
        )


def freeze_carrier_pre_acquisition_inputs(
    carrier: str,
    declarations: Iterable[Mapping[str, Any]],
    *,
    acquisition_root: Path,
    handoff_ref: Path | None,
    scale: str,
    vertical: str,
    scope: str,
    region_ref: str,
    topic: str | None,
    run_date: str,
    campaign_sequence: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    handoff_output_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze external refs only while their governed handoff identity matches."""
    from content.execution.campaign_external_inputs import bind_external_input_refs

    frozen = bind_external_input_refs(
        carrier,
        declarations,
        acquisition_root=acquisition_root,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    handoff, binding = bind_pre_acquisition_handoff(
        handoff_ref,
        scale=scale,
        vertical=vertical,
        scope=scope,
        region_ref=region_ref,
        topic=topic,
        run_date=run_date,
        campaign_sequence=campaign_sequence,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        output_root=handoff_output_root,
    )
    validate_carrier_phase1_requirements(
        handoff,
        carrier=carrier,
        external_input_refs=frozen,
    )
    return frozen, binding


def guard_acquisition_source_identity(
    manifest: Mapping[str, Any],
    *,
    handoff_ref: Path | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Reject stale manifest/handoff identity before any receipt or CAS write."""
    if handoff_ref is None:
        raise _typed("HANDOFF_REQUIRED", "acquisition requires explicit handoffRef")
    source = current_source_digest(
        repo_root=(repo_root or paths.REPO_ROOT).expanduser().resolve()
    )
    manifest_source = str(manifest.get("sourceDigest") or "")
    catalog_digest = str(manifest.get("entityCatalogDigest") or "")
    manifest_revision = str(manifest.get("sourceRevision") or "")
    if manifest_source != source.digest:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest sourceDigest differs from current_source_digest",
        )
    expected_revision = content_source_revision(
        source_digest=source.digest,
        entity_catalog_digest=catalog_digest,
    )
    if manifest_revision != expected_revision:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest sourceRevision does not match sourceDigest + "
            "entityCatalogDigest",
        )
    handoff = load_pre_acquisition_handoff(handoff_ref.expanduser().resolve())
    drift = _identity_drift(
        handoff,
        source_revision=manifest_revision,
        source_digest=manifest_source,
        entity_catalog_digest=catalog_digest,
    )
    if drift:
        raise _typed(
            "SOURCE_IDENTITY_DRIFT",
            "manifest differs from handoff identity: " + ", ".join(drift),
        )
    return handoff


__all__ = [
    "HANDOFF_SCHEMA",
    "PreAcquisitionHandoffError",
    "bind_pre_acquisition_handoff",
    "build_pre_acquisition_handoff",
    "freeze_carrier_pre_acquisition_inputs",
    "guard_acquisition_source_identity",
    "load_pre_acquisition_handoff",
    "pre_acquisition_handoff_path",
    "validate_carrier_phase1_requirements",
    "write_pre_acquisition_handoff",
]

"""Resolve frozen scale source-pool selections for one execution lane.

The campaign capsule is the only runtime authority.  M100+ planning may not
re-run region discovery or reconstruct candidate inputs from a mutable local
mirror after the campaign has frozen its selected-only snapshot.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.entity_object import parse_entity_ref
from core.carrier_contract import research_plan_files
from core.io import read_json, write_json
from core.paths import STAGE_DOWNLOAD
from core.schema import assert_valid

from content.execution.campaign.external_input_runtime import (
    bound_runtime_external_input_context,
)
from content.execution.campaign.source_pool_binding import load_capsule_source_pool
from content.source.research.homepage_article_source_ready_batch import (
    CAPSULE_SCHEMA as SOURCE_READY_CAPSULE_SCHEMA,
    validate_source_ready_candidate_capsule,
)
from content.source.source_unit import resolve_entity_object_dir
from content.source.source_unit_writer import write_source_unit


RUNTIME_INPUT_UNBOUND = "DATA.SOURCE.POOL.RUNTIME_INPUT_UNBOUND"


class ScaleSourcePoolRuntimeError(ValueError):
    """Typed missing, drifted, or cross-lane runtime source-pool input."""

    code = RUNTIME_INPUT_UNBOUND

    def __init__(self, issue: object) -> None:
        message = str(issue).strip()
        if not message:
            raise ValueError("source-pool runtime blocker requires an issue")
        self.issue = message
        super().__init__(f"{self.code}: {message}")


def _fail(issue: object) -> ScaleSourcePoolRuntimeError:
    return ScaleSourcePoolRuntimeError(issue)


def _execution_uses_scale_source_pool(execution_id: str) -> bool:
    from content.execution import store

    spec = store.load_spec(execution_id)
    policy = spec.get("executionPolicy") if isinstance(spec, Mapping) else None
    return isinstance(policy, Mapping) and isinstance(
        policy.get("scaleSourcePool"), Mapping
    )


def _manifest(capsule_root: Path) -> dict[str, Any]:
    try:
        value = read_json(capsule_root / ".qwq_campaign_capsule.json")
        if not isinstance(value, dict):
            raise TypeError("campaign capsule manifest must be one object")
        assert_valid(value, "execution", "content_source_capsule")
        return value
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(f"campaign capsule manifest is unavailable: {exc}") from exc


def _selected_rows(
    *, execution_id: str, carrier: str
) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    context = bound_runtime_external_input_context(execution_id, carrier)
    if context is None or context.capsule_root is None:
        raise _fail("campaign capsule runtime context is not bound")
    capsule_root = context.capsule_root.expanduser().resolve()
    try:
        manifest = _manifest(capsule_root)
        binding, selections, root_ref = load_capsule_source_pool(
            manifest, capsule_path=capsule_root
        )
        if binding is None or selections is None or root_ref is None:
            raise _fail("campaign capsule has no frozen scale source pool")
        selection = selections[carrier]
        snapshot_root = (capsule_root / root_ref).resolve()
        snapshot_root.relative_to(capsule_root)
        snapshot = read_json(snapshot_root / "selected.json")
        if not isinstance(snapshot, Mapping):
            raise TypeError("selected source-pool snapshot must be one object")
        selected_ids = tuple(str(value) for value in selection["candidateIds"])
        rows = [
            dict(row)
            for row in snapshot.get("selectedCandidates") or []
            if isinstance(row, Mapping)
            and row.get("carrier") == carrier
            and str(row.get("candidateId") or "") in selected_ids
        ]
        by_id = {str(row["candidateId"]): row for row in rows}
        if len(by_id) != len(selected_ids) or set(by_id) != set(selected_ids):
            raise ValueError("selected lane candidates drift from frozen selection")
        return capsule_root, snapshot_root, binding, [by_id[value] for value in selected_ids]
    except ScaleSourcePoolRuntimeError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen source-pool selection is invalid: {exc}") from exc


def _source_ready_capsule(
    row: Mapping[str, Any], *, snapshot_root: Path
) -> dict[str, Any]:
    evidence_root = snapshot_root / "evidence"
    relative = Path(str(row.get("sourceUnitRef") or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise _fail("selected source-ready candidate ref is unsafe")
    path = evidence_root / relative
    try:
        value = read_json(path)
        if not isinstance(value, Mapping) or value.get("schema") != SOURCE_READY_CAPSULE_SCHEMA:
            raise TypeError("selected candidate is not a source-ready capsule")
        capsule = validate_source_ready_candidate_capsule(
            value, evidence_root=evidence_root
        )
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(f"selected source-ready candidate is invalid: {exc}") from exc
    candidate = capsule["candidate"]
    checks = {
        "carrier": (capsule.get("carrier"), row.get("carrier")),
        "candidateId": (candidate.get("candidateId"), row.get("candidateId")),
        "entityRef": (candidate.get("entityRef"), row.get("entityRef")),
        "observedEntityRef": (
            candidate.get("observedEntityRef"), row.get("observedEntityRef")
        ),
        **{
            field: (candidate.get(field), row.get(field))
            for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
        },
    }
    drift = sorted(field for field, values in checks.items() if values[0] != values[1])
    if drift:
        raise _fail(
            "selected candidate row drifts from its source-ready capsule: "
            + ", ".join(drift)
        )
    return capsule


def frozen_scale_source_pool_candidates(
    execution_id: str, carrier: str
) -> tuple[dict[str, Any], ...]:
    """Return exact lane candidates after physical selected-snapshot validation."""

    _, snapshot_root, binding, rows = _selected_rows(
        execution_id=execution_id, carrier=carrier
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        value = dict(row)
        if carrier in {"homepage", "article"}:
            value["sourceReadyCapsule"] = _source_ready_capsule(
                row, snapshot_root=snapshot_root
            )
            value["sourceReadyEvidenceRoot"] = snapshot_root / "evidence"
        if any(
            value.get(field) != binding.get(field)
            for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
        ):
            raise _fail("selected candidate source identity drift")
        result.append(value)
    return tuple(result)


def frozen_scale_source_pool_targets(
    execution_id: str, carrier: str
) -> tuple[dict[str, Any], ...]:
    """Project exact candidate entity identities into execution coverage targets."""

    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in frozen_scale_source_pool_candidates(execution_id, carrier):
        parsed = parse_entity_ref(str(row.get("entityRef") or ""))
        if parsed is None:
            raise _fail(f"invalid candidate entityRef: {row.get('entityRef')!r}")
        domain, entity_type, name = parsed
        identity = (f"{domain}/{entity_type}", name)
        if identity in seen:
            raise _fail(f"duplicate selected entity target: {identity[0]}/{name}")
        seen.add(identity)
        target: dict[str, Any] = {"entityType": identity[0], "name": name}
        if carrier == "homepage":
            capsule = row.get("sourceReadyCapsule")
            candidate = capsule.get("candidate") if isinstance(capsule, Mapping) else None
            primary = candidate.get("primarySource") if isinstance(candidate, Mapping) else None
            if not isinstance(primary, Mapping):
                raise _fail("homepage source-ready primarySource is missing")
            target["qualifiedHomepageSource"] = {
                "provider": primary["sourceKind"],
                "title": primary["platform"],
                "url": primary["sourceUrl"],
            }
        targets.append(target)
    return tuple(targets)


def select_frozen_source_pool_targets(
    *,
    targets: tuple[dict[str, Any], ...],
    requested_limit: int,
    approved_quota: int,
    target_names: tuple[str, ...],
    discovery_path: Path,
    pool_binding: Mapping[str, Any],
    lane_selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate request cardinality and emit the immutable selection receipt."""

    rows = [dict(row) for row in targets]
    selected_names = tuple(sorted(str(row.get("name") or "") for row in rows))
    requested_names = tuple(sorted(target_names))
    expected_count = int(lane_selection.get("candidateCount") or 0)
    if (
        len(rows) != requested_limit
        or len(rows) != expected_count
        or approved_quota > len(rows)
        or (requested_names and requested_names != selected_names)
    ):
        raise _fail(
            "frozen source-pool targets do not match count/quota/requested target names"
        )
    return rows, {
        "discoveryPath": str(discovery_path),
        "selectionAuthority": "frozen_scale_source_pool",
        "sourcePoolPlanDigest": pool_binding["planDigest"],
        "sourcePoolSelectionDigest": lane_selection["selectionDigest"],
        "selectedCount": len(rows),
        "quota": approved_quota,
    }


def _candidate_source(candidate: Mapping[str, Any], carrier: str) -> dict[str, Any]:
    source = (
        candidate["primarySource"] if carrier == "homepage" else candidate
    )
    assert isinstance(source, Mapping)
    return {
        "source_id": str(source["sourceUnitId"]),
        "platform": str(source["platform"]),
        "url": str(source["sourceUrl"]),
        "canonicalUrl": str(source["sourceUrl"]),
        "finalUrl": str(source["sourceUrl"]),
        "sourceKind": str(source["sourceKind"]),
        "sourceTitle": str(source["platform"]),
        "qualifiedAuthorityTitle": str(source["platform"]),
        "extractor": str(source["extractor"]),
        "policyRevision": str(source["policyRevision"]),
        "sourceUseMode": "factual_reference_only",
        "publishMediaMode": "illustrated",
        "category": str(source["sourceKind"]),
        "discoveryProvider": "frozen_scale_source_pool",
        "matchConfidence": 1.0,
        "evidenceReason": "immutable source-ready candidate capsule",
        "sourceRole": "base",
        "imageEvidenceMode": "same_source",
        "entityMatch": "accepted",
        "researchLane": carrier,
        "articleCommercialAdmission": (
            "commercial_release" if carrier == "article" else ""
        ),
        "articleSiteId": str(source.get("articleSiteId") or ""),
        "sourceDiscoveryProfileDigest": str(
            source.get("sourceDiscoveryProfileDigest") or ""
        ),
        "runtimeInputMode": "frozen_scale_source_pool",
        "sourcePoolCandidateId": str(candidate["candidateId"]),
    }


def write_frozen_scale_source_pool_plans(
    execution_id: str,
    entity_ids: list[str],
    *,
    carrier: str,
) -> dict[str, Any] | None:
    """Write offline homepage/article plans from selected candidate capsules."""

    if carrier not in {"homepage", "article"}:
        return None
    if not _execution_uses_scale_source_pool(execution_id):
        return None
    rows = frozen_scale_source_pool_candidates(execution_id, carrier)
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        parsed = parse_entity_ref(str(row["entityRef"]))
        if parsed is None:
            raise _fail("selected source-ready entityRef is invalid")
        name = parsed[2]
        if name in by_name:
            raise _fail(f"selected source-ready entity is duplicated: {name}")
        by_name[name] = row
    if set(by_name) != set(entity_ids):
        raise _fail("execution entity ids drift from frozen source-pool selection")
    plan_file = research_plan_files()[carrier]
    updated: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        row = by_name[entity_id]
        parsed = parse_entity_ref(str(row["entityRef"]))
        assert parsed is not None
        object_dir = resolve_entity_object_dir(
            execution_id, entity_id, etype_hint=f"{parsed[0]}/{parsed[1]}"
        )
        path = object_dir / STAGE_DOWNLOAD / plan_file
        plan = read_json(path)
        if not isinstance(plan, dict) or not isinstance(plan.get("payload"), dict):
            raise _fail(f"{carrier} source plan envelope is unavailable: {entity_id}")
        source = _candidate_source(row["sourceReadyCapsule"]["candidate"], carrier)
        payload = dict(plan["payload"])
        payload["sources"] = [source]
        payload["runtimeInputAuthority"] = "frozen_scale_source_pool"
        write_json(path, {**plan, "payload": payload})
        updated.append(
            {
                "entityId": entity_id,
                "lane": carrier,
                "candidateId": row["candidateId"],
                "planRef": path.as_posix(),
            }
        )
    return {
        "schema": "quwoquan.content.source.auto_research_plan",
        "executionId": execution_id,
        "selectedLanes": [carrier],
        "selectionAuthority": "frozen_scale_source_pool",
        "updated": updated,
        "issues": [],
        "candidates": [
            {"candidateId": row["candidateId"], "entityRef": row["entityRef"]}
            for row in rows
        ],
        "imageCollections": [],
        "homepageMediaCollections": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }


def _image_rows(candidate: Mapping[str, Any], carrier: str) -> list[Mapping[str, Any]]:
    if carrier == "homepage":
        hero = candidate.get("hero")
        return [hero] if isinstance(hero, Mapping) else []
    return [row for row in candidate.get("assets") or [] if isinstance(row, Mapping)]


def _existing_source_unit(
    execution_id: str,
    source_unit_id: str,
    *,
    body_sha256: str,
    media_sha256: list[str],
    carrier: str,
    source_url: str,
) -> dict[str, Any] | None:
    from content.source import source_unit_writer

    unit = source_unit_writer.execution_source_unit_dir(execution_id, source_unit_id)
    if not unit.exists():
        return None
    try:
        meta = read_json(unit / "meta.json")
        index = read_json(unit / "assets/index.json")
        source_path = unit / "source.md"
        actual_body = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
        actual_media = sorted(
            str(row["sha256"])
            for row in index["assets"]
            if isinstance(row, Mapping)
        )
        if (
            not isinstance(meta, dict)
            or meta.get("sourceUnitId") != source_unit_id
            or meta.get("researchLane") != carrier
            or meta.get("url") != source_url
            or actual_body != body_sha256
            or actual_media != sorted(media_sha256)
        ):
            raise ValueError("existing source unit bytes differ from frozen candidate")
        return meta
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"existing frozen source unit is not replayable: {exc}") from exc


def materialize_frozen_scale_source_pool_entity(
    execution_id: str,
    carrier: str,
    entity_id: str,
    entity_type: str,
) -> dict[str, Any] | None:
    """Materialize selected body/media bytes without any network discovery."""

    if carrier not in {"homepage", "article"}:
        return None
    matches: list[dict[str, Any]] = []
    for row in frozen_scale_source_pool_candidates(execution_id, carrier):
        parsed = parse_entity_ref(str(row["entityRef"]))
        if parsed is not None and parsed[2] == entity_id:
            matches.append(row)
    if len(matches) != 1:
        raise _fail(f"{carrier} entity must bind exactly one selected candidate: {entity_id}")
    row = matches[0]
    capsule = row["sourceReadyCapsule"]
    candidate = capsule["candidate"]
    materialization = capsule["materialization"]
    evidence_root = row["sourceReadyEvidenceRoot"]
    assert isinstance(evidence_root, Path)
    body = (evidence_root / str(materialization["body"]["ref"])).read_text(
        encoding="utf-8"
    )
    source = _candidate_source(candidate, carrier)
    media_by_id = {
        str(binding["assetId"]): binding for binding in materialization["media"]
    }
    images: list[dict[str, Any]] = []
    for index, asset in enumerate(_image_rows(candidate, carrier), start=1):
        binding = media_by_id.get(str(asset["assetId"]))
        if binding is None:
            raise _fail(f"selected media binding is missing: {asset['assetId']}")
        images.append(
            {
                **dict(asset),
                "sourcePath": evidence_root / str(binding["ref"]),
                "url": str(asset["originalAssetUrl"]),
                "sourceUrl": str(asset["sourcePageUrl"]),
                "credit": str(asset["creator"]),
                "caption": str(asset["assetId"]),
                "relevance": f"{entity_id} frozen {asset.get('role') or 'hero'} media",
                "role": str(asset.get("role") or "hero"),
                "coverCandidateRank": 1 if asset.get("role") in {"hero", "cover"} else index + 1,
            }
        )
    object_dir = resolve_entity_object_dir(
        execution_id, entity_id, etype_hint=entity_type
    )
    source_unit = candidate["primarySource"] if carrier == "homepage" else candidate
    assert isinstance(source_unit, Mapping)
    existing = _existing_source_unit(
        execution_id,
        str(source_unit["sourceUnitId"]),
        body_sha256=str(materialization["body"]["contentSha256"]),
        media_sha256=[str(row["contentSha256"]) for row in materialization["media"]],
        carrier=carrier,
        source_url=str(source_unit["sourceUrl"]),
    )
    if existing is not None:
        return existing
    return write_source_unit(
        object_dir,
        ordinal=1,
        source_id=str(source_unit["sourceUnitId"]),
        source_md=body,
        clean_md=body,
        quality={
            "sourceId": str(source_unit["sourceUnitId"]),
            "entity": entity_id,
            "quality": "High",
            "score": 100,
            "reasons": ["frozen_scale_source_pool"],
            "url": str(source_unit["sourceUrl"]),
            "statusCode": 200,
            "fetchSucceeded": True,
            "taskProvidedBodyPresent": False,
        },
        platform=str(source_unit["platform"]),
        source_category=str(source_unit["sourceKind"]),
        source_kind=str(source_unit["sourceKind"]),
        extractor=str(source_unit["extractor"]),
        policy_revision=str(source_unit["policyRevision"]),
        source_use_mode="factual_reference_only",
        publish_media_mode="illustrated",
        source_role="base",
        image_evidence_mode="same_source",
        research_lane=carrier,
        url=str(source_unit["sourceUrl"]),
        title=str(source_unit["platform"]),
        target_ref=str(candidate["entityRef"]),
        relevance=f"frozen source-ready evidence for {entity_id}",
        images=images,
        execution_id=execution_id,
        build_variants=False,
        source={
            **source,
            "fetchedAt": str(source_unit.get("capturedAt") or ""),
        },
        frozen_source_unit_id=str(source_unit["sourceUnitId"]),
    )


def frozen_scale_source_pool_fetch_result(
    execution_id: str,
    *,
    selected_lanes: set[str] | None,
    entity_id: str,
    entity_type: str,
    entity_index: int,
) -> dict[str, Any] | None:
    """Return the download-stage result for an offline selected source unit."""

    if not selected_lanes or len(selected_lanes) != 1:
        return None
    if not _execution_uses_scale_source_pool(execution_id):
        return None
    carrier = next(iter(selected_lanes))
    manifest = materialize_frozen_scale_source_pool_entity(
        execution_id, carrier, entity_id, entity_type
    )
    if manifest is None:
        return None
    return {
        "entityId": entity_id,
        "entityIndex": entity_index,
        "sourceCount": 1,
        "imageCount": int(manifest.get("assetCount") or 0),
        "fetchedSources": [
            {
                "sourceId": manifest["sourceId"],
                "url": manifest["url"],
                "quality": "High",
                "score": 100,
                "entityId": entity_id,
                "retainedFromCache": False,
                "runtimeInputAuthority": "frozen_scale_source_pool",
            }
        ],
        "qualityRows": [
            {
                "sourceId": manifest["sourceId"],
                "quality": "High",
                "score": 100,
                "url": manifest["url"],
                "statusCode": 200,
                "retainedFromCache": False,
            }
        ],
        "failedImage": False,
        "sourcedVideoFailure": None,
    }


__all__ = [
    "RUNTIME_INPUT_UNBOUND",
    "ScaleSourcePoolRuntimeError",
    "frozen_scale_source_pool_candidates",
    "frozen_scale_source_pool_fetch_result",
    "frozen_scale_source_pool_targets",
    "materialize_frozen_scale_source_pool_entity",
    "select_frozen_source_pool_targets",
    "write_frozen_scale_source_pool_plans",
]

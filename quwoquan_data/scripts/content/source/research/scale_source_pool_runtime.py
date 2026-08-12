"""Resolve frozen scale source-pool selections for one execution lane.

The campaign capsule is the only runtime authority.  M100+ planning may not
re-run region discovery or reconstruct candidate inputs from a mutable local
mirror after the campaign has frozen its selected-only snapshot.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from core.carrier_contract import research_plan_files
from core.entity_object import parse_entity_ref
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, STAGE_DOWNLOAD
from core.schema import assert_valid

from content.execution.campaign.external_input_runtime import (
    bound_runtime_external_input_context,
)
from content.execution.campaign.source_pool_binding import load_capsule_source_pool
from content.source.research.scale_source_pool_runtime_inputs import (
    direct_selected_rows,
    source_ready_capsule,
)
from content.source.research.scale_source_pool_evidence_path import (
    compute_evidence_file_sha256,
    resolve_evidence_file,
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
    *,
    execution_id: str,
    carrier: str,
    direct_selection: Mapping[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    context = bound_runtime_external_input_context(execution_id, carrier)
    if context is None or context.capsule_root is None:
        try:
            return direct_selected_rows(
                execution_id=execution_id,
                carrier=carrier,
                direct_selection=direct_selection,
                output_root=OUTPUT_ROOT,
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise _fail(f"standalone source-pool binding is invalid: {exc}") from exc
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
        return (
            capsule_root,
            snapshot_root / "evidence",
            binding,
            [by_id[value] for value in selected_ids],
        )
    except ScaleSourcePoolRuntimeError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen source-pool selection is invalid: {exc}") from exc

def frozen_scale_source_pool_candidates(
    execution_id: str,
    carrier: str,
    *,
    direct_selection: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return exact lane candidates after physical selected-snapshot validation."""

    _, evidence_root, binding, rows = _selected_rows(
        execution_id=execution_id,
        carrier=carrier,
        direct_selection=direct_selection,
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        value = dict(row)
        value["sourcePoolEvidenceRoot"] = evidence_root
        if carrier in {"homepage", "article"}:
            try:
                capsule, candidate_root = source_ready_capsule(
                    row, evidence_root=evidence_root
                )
            except (OSError, TypeError, ValueError) as exc:
                raise _fail(f"selected source-ready candidate is invalid: {exc}") from exc
            value["sourceReadyCapsule"] = capsule
            value["sourceReadyEvidenceRoot"] = candidate_root
        if any(
            value.get(field) != binding.get(field)
            for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
        ):
            raise _fail("selected candidate source identity drift")
        result.append(value)
    return tuple(result)


def frozen_scale_source_pool_targets(
    execution_id: str,
    carrier: str,
    *,
    direct_selection: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Project exact candidate entity identities into execution coverage targets."""

    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in frozen_scale_source_pool_candidates(
        execution_id,
        carrier,
        direct_selection=direct_selection,
    ):
        parsed = parse_entity_ref(str(row.get("entityRef") or ""))
        if parsed is None:
            raise _fail(f"invalid candidate entityRef: {row.get('entityRef')!r}")
        domain, entity_type, name = parsed
        identity = (f"{domain}/{entity_type}", name)
        if identity in seen:
            raise _fail(f"duplicate selected entity target: {identity[0]}/{name}")
        seen.add(identity)
        target: dict[str, Any] = {"entityType": identity[0], "name": name}
        if identity[0] == "地点/城市":
            # 行政实体的完整 canonical ref 来自冻结 source-pool；runtime join
            # 必须逐字节消费它，不能仅凭同名城市重新构造或模糊匹配。
            target["canonicalEntityRef"] = str(row["entityRef"])
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

    rows = _enrich_frozen_targets_from_discovery(
        targets,
        discovery_path=discovery_path,
    )
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


def _enrich_frozen_targets_from_discovery(
    targets: tuple[dict[str, Any], ...],
    *,
    discovery_path: Path,
) -> list[dict[str, Any]]:
    """Join exact source-pool identities back to governed geography metadata.

    Source-pool candidates deliberately carry the canonical entity identity and
    source evidence, while the execution spec owns ``geoTagRef`` and taxonomy
    fields needed by qualification/materialization.  The join is exact on
    canonical name + entity type and fails closed on missing or ambiguous rows;
    it never performs network discovery or changes the frozen candidate order.
    """

    from governance.coverage.admin_entity_catalog import admin_entity_partitions

    from content.execution.planning.selection_discovery import (
        apply_master_list_fields,
        leaf_selection_name,
        load_partitions,
    )

    def exact_text(value: object) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).strip()

    by_identity: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    if any(str(row.get("entityType") or "").strip() != "地点/城市" for row in targets):
        for partition in load_partitions(discovery_path):
            for leaf in partition.get("leaves") or []:
                if not isinstance(leaf, Mapping):
                    continue
                name = exact_text(leaf_selection_name(leaf))
                entity_type = exact_text(leaf.get("entityType"))
                if name and entity_type:
                    by_identity.setdefault((entity_type, name), []).append(leaf)

    admin_by_identity: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    if any(str(row.get("entityType") or "").strip() == "地点/城市" for row in targets):
        for partition in admin_entity_partitions():
            for leaf in partition.get("leaves") or []:
                if not isinstance(leaf, Mapping):
                    continue
                identity = (
                    exact_text(leaf.get("entityType")),
                    exact_text(leaf_selection_name(leaf)),
                    exact_text(leaf.get("canonicalEntityRef")),
                )
                if all(identity):
                    admin_by_identity.setdefault(identity, []).append(leaf)

    enriched: list[dict[str, Any]] = []
    for target in targets:
        row = dict(target)
        identity = (
            exact_text(row.get("entityType")),
            exact_text(row.get("name")),
        )
        if identity[0] == "地点/城市":
            canonical_ref = exact_text(row.get("canonicalEntityRef"))
            matches = admin_by_identity.get((*identity, canonical_ref), [])
            authority = "admin"
        else:
            matches = by_identity.get(identity, [])
            authority = "discovery"
        if len(matches) != 1:
            reason = "missing" if not matches else "ambiguous"
            raise _fail(
                f"{reason} governed {authority} target for "
                f"{identity[0]}/{identity[1]}"
            )
        enriched.append(apply_master_list_fields(row, matches[0]))
    return enriched


def _candidate_source(candidate: Mapping[str, Any], carrier: str) -> dict[str, Any]:
    source = (
        candidate["primarySource"] if carrier == "homepage" else candidate
    )
    assert isinstance(source, Mapping)
    result = {
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
        "publishMediaMode": str(
            candidate.get("publishMediaMode") or "illustrated"
        ),
        "category": str(source["sourceKind"]),
        "discoveryProvider": "frozen_scale_source_pool",
        "matchConfidence": 1.0,
        "evidenceReason": "immutable source-ready candidate capsule",
        "sourceRole": "base",
        "imageEvidenceMode": (
            "" if candidate.get("publishMediaMode") == "text_only" else "same_source"
        ),
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
        "sourceAttribution": dict(candidate["sourceAttribution"]),
    }
    if carrier == "article" and candidate.get("articleCategory"):
        result.update(
            {
                "articleCategory": str(candidate["articleCategory"]),
                "writingIntent": str(candidate["writingIntent"]),
                "topicTagRefs": list(candidate["topicTagRefs"]),
                "sourceClassification": dict(candidate["sourceClassification"]),
            }
        )
    return result


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


def _wiki_file_key(value: object) -> str:
    text = unquote(str(value or "")).strip()
    match = re.search(r"(?:File|文件):([^/?#]+)", text, re.IGNORECASE)
    if match:
        text = match.group(1)
    elif ":" in text and text.split(":", 1)[0] in {"File", "文件"}:
        text = text.split(":", 1)[1]
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip().casefold()


def _frozen_homepage_media_inputs(
    *,
    capsule: Mapping[str, Any],
    evidence_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    """Restore exact selected-hero placement from immutable acquisition bytes.

    Homepage source-ready capsules intentionally bind a small carrier-selective
    media set, while their acquisition evidence retains the exact MediaWiki raw
    response.  Runtime materialization must project the selected hero's real
    placement from those frozen bytes; inventing a generic lead placement would
    hide locator maps and break the page-media enumeration contract.
    """

    from core.wiki_wikitext import parse_wikitext_layout, placements_from_layout

    from content.source.mediawiki_page import _revision_wikitext
    from content.source.research.homepage_article_source_ready_evidence import (
        assert_source_ready_evidence_matches_capsule,
        file_sha256,
        validate_source_ready_acquisition_evidence,
    )

    candidate = capsule.get("candidate")
    provenance = capsule.get("provenance")
    if not isinstance(candidate, Mapping) or not isinstance(provenance, Mapping):
        raise _fail("frozen homepage capsule lacks candidate/provenance")
    evidence_ref = Path(str(provenance.get("discoveryEvidenceRef") or ""))
    if not str(evidence_ref) or evidence_ref.is_absolute() or ".." in evidence_ref.parts:
        raise _fail("frozen homepage acquisition evidence ref is unsafe")
    try:
        evidence = read_json(evidence_root / evidence_ref)
        if not isinstance(evidence, Mapping):
            raise TypeError("acquisition evidence must be one object")
        validated = validate_source_ready_acquisition_evidence(evidence)
        assert_source_ready_evidence_matches_capsule(validated, capsule)
    except (OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen homepage acquisition evidence is invalid: {exc}") from exc
    if validated.get("carrier") != "homepage":
        raise _fail("frozen homepage acquisition evidence carrier drift")
    source = validated.get("sourceUnit")
    if not isinstance(source, Mapping) or source.get("sourceKind") != "wikipedia":
        raise _fail("frozen homepage source does not bind MediaWiki placement evidence")
    raw_ref = Path(str(source.get("rawEvidenceRef") or ""))
    if not str(raw_ref) or raw_ref.is_absolute() or ".." in raw_ref.parts:
        raise _fail("frozen homepage raw evidence ref is unsafe")
    raw_path = evidence_root / raw_ref
    try:
        if file_sha256(raw_path) != source.get("rawEvidenceFileSha256"):
            raise ValueError("rawEvidenceFileSha256 drift")
        raw_document = read_json(raw_path)
        if not isinstance(raw_document, Mapping):
            raise TypeError("raw MediaWiki evidence must be one object")
        mediawiki_raw = raw_document.get("mediawikiRaw")
        if mediawiki_raw is not None:
            if not isinstance(mediawiki_raw, str):
                raise TypeError("mediawikiRaw must be serialized JSON")
            raw_document = json.loads(mediawiki_raw)
        responses = raw_document.get("responses")
        if not isinstance(responses, list) or not responses:
            raise ValueError("MediaWiki raw evidence lacks responses")
        first = responses[0]
        query = first.get("query") if isinstance(first, Mapping) else None
        pages = query.get("pages") if isinstance(query, Mapping) else None
        page_rows = [row for row in (pages or {}).values() if isinstance(row, Mapping)]
        if len(page_rows) != 1:
            raise ValueError("MediaWiki raw evidence page identity is not exact")
        page = page_rows[0]
        revisions = page.get("revisions")
        revision_rows = [
            row for row in (revisions or []) if isinstance(row, Mapping)
        ]
        if len(revision_rows) != 1:
            raise ValueError("MediaWiki raw evidence revision identity is not exact")
        revision = revision_rows[0]
        if (
            int(page.get("pageid") or 0) != int(source.get("pageId") or 0)
            or str(page.get("title") or "") != str(source.get("resolvedTitle") or "")
            or int(revision.get("revid") or page.get("lastrevid") or 0)
            != int(source.get("revisionId") or 0)
        ):
            raise ValueError("MediaWiki raw evidence identity drift")
        wikitext = _revision_wikitext(revision).strip()
        if not wikitext:
            raise ValueError("MediaWiki raw evidence lacks revision wikitext")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _fail(f"frozen homepage raw evidence is invalid: {exc}") from exc

    layout = parse_wikitext_layout(
        wikitext,
        source_kind="wikipedia",
        title=str(source["resolvedTitle"]),
    )
    hero = candidate.get("hero")
    if not isinstance(hero, Mapping):
        raise _fail("frozen homepage candidate lacks hero")
    hero_key = _wiki_file_key(hero.get("sourcePageUrl"))
    matching_figures = [
        dict(block)
        for block in layout.get("blocks") or []
        if isinstance(block, Mapping)
        and block.get("type") == "figure"
        and _wiki_file_key(block.get("fileTitle")) == hero_key
    ]
    if not hero_key or not matching_figures:
        raise _fail("frozen homepage hero is absent from exact MediaWiki placements")
    selected_layout = {
        **layout,
        "blocks": matching_figures,
        "figureCount": len(matching_figures),
        "tables": [],
    }
    placements = placements_from_layout(selected_layout)
    if not placements:
        raise _fail("frozen homepage hero placement projection is empty")
    # The same source asset may appear more than once on a page.  Preserve all
    # exact occurrences in imagePlacements, while the assets index carries the
    # earliest occurrence only as its deterministic summary.
    placement = min(placements, key=lambda row: int(row.get("sourceOrder") or 0))
    asset_metadata = {
        str(hero["assetId"]): {
            "fileName": str(placement.get("fileName") or ""),
            "caption": str(placement.get("caption") or ""),
            "placeholderId": str(placement.get("placeholderId") or ""),
            "placementType": str(placement.get("placementType") or "inline"),
            "groupId": str(placement.get("groupId") or ""),
            "sectionSlug": str(placement.get("sectionSlug") or ""),
            "sourceOrder": int(placement.get("sourceOrder") or 0),
            "coverCandidateRank": int(placement.get("coverCandidateRank") or 0),
            "subjectKey": str(placement.get("subjectKey") or ""),
            "isMapLike": bool(placement.get("isMapLike")),
            "pageResolvedTitle": str(source["resolvedTitle"]),
            "pageId": int(source["pageId"]),
            "pageRevisionId": int(source["revisionId"]),
        }
    }
    funnel = {
        "candidateCount": 1,
        "keptCount": 1,
        "droppedCount": 0,
        "dedupeRemoved": 0,
        "drops": [],
        "fetchFailures": [],
    }
    return selected_layout, asset_metadata, funnel


def _existing_source_unit(
    execution_id: str,
    source_unit_id: str,
    *,
    body_sha256: str,
    media_sha256: list[str],
    carrier: str,
    source_url: str,
    source_attribution: Mapping[str, Any],
    publish_media_mode: str,
    image_placements: list[dict[str, Any]] | None,
    asset_funnel: Mapping[str, Any] | None,
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
            or meta.get("sourceAttribution") != dict(source_attribution)
            or meta.get("publishMediaMode") != publish_media_mode
            or (
                image_placements is not None
                and meta.get("imagePlacements") != image_placements
            )
            or (
                asset_funnel is not None
                and meta.get("assetFunnel") != dict(asset_funnel)
            )
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

    if carrier not in {"homepage", "article", "image"}:
        return None
    matches: list[dict[str, Any]] = []
    for row in frozen_scale_source_pool_candidates(execution_id, carrier):
        parsed = parse_entity_ref(str(row["entityRef"]))
        if parsed is not None and parsed[2] == entity_id:
            matches.append(row)
    if len(matches) != 1:
        raise _fail(f"{carrier} entity must bind exactly one selected candidate: {entity_id}")
    row = matches[0]
    if carrier == "image":
        return _materialize_frozen_image_source_unit(
            execution_id=execution_id,
            entity_id=entity_id,
            entity_type=entity_type,
            row=row,
        )
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
    layout: dict[str, Any] | None = None
    asset_metadata: dict[str, dict[str, Any]] = {}
    asset_funnel: dict[str, Any] | None = None
    image_placements: list[dict[str, Any]] | None = None
    if carrier == "homepage":
        layout, asset_metadata, asset_funnel = _frozen_homepage_media_inputs(
            capsule=capsule,
            evidence_root=evidence_root,
        )
        from core.wiki_wikitext import placements_from_layout

        image_placements = placements_from_layout(layout)
    images: list[dict[str, Any]] = []
    for index, asset in enumerate(_image_rows(candidate, carrier), start=1):
        binding = media_by_id.get(str(asset["assetId"]))
        if binding is None:
            raise _fail(f"selected media binding is missing: {asset['assetId']}")
        placement = asset_metadata.get(str(asset["assetId"]), {})
        images.append(
            {
                **dict(asset),
                **placement,
                "sourcePath": evidence_root / str(binding["ref"]),
                "url": str(asset["originalAssetUrl"]),
                "sourceUrl": str(asset["sourcePageUrl"]),
                "credit": str(asset["creator"]),
                "caption": str(placement.get("caption") or asset["assetId"]),
                "relevance": f"{entity_id} frozen {asset.get('role') or 'hero'} media",
                "role": str(asset.get("role") or "hero"),
                "coverCandidateRank": int(
                    placement.get("coverCandidateRank")
                    if "coverCandidateRank" in placement
                    else 1 if asset.get("role") in {"hero", "cover"} else index + 1
                ),
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
        source_attribution=candidate["sourceAttribution"],
        publish_media_mode=str(candidate.get("publishMediaMode") or "illustrated"),
        image_placements=image_placements,
        asset_funnel=asset_funnel,
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
        publish_media_mode=str(candidate.get("publishMediaMode") or "illustrated"),
        source_role="base",
        image_evidence_mode=(
            "" if candidate.get("publishMediaMode") == "text_only" else "same_source"
        ),
        research_lane=carrier,
        url=str(source_unit["sourceUrl"]),
        title=str(
            source_unit.get("resolvedTitle")
            if carrier == "article"
            else source_unit["platform"]
        ),
        target_ref=str(candidate["entityRef"]),
        relevance=f"frozen source-ready evidence for {entity_id}",
        images=images,
        asset_funnel=asset_funnel,
        layout=layout,
        execution_id=execution_id,
        build_variants=False,
        source={
            **source,
            "fetchedAt": str(source_unit.get("capturedAt") or ""),
        },
        frozen_source_unit_id=str(source_unit["sourceUnitId"]),
    )


def _materialize_frozen_image_source_unit(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Project one reviewed professional image without provider rediscovery."""

    evidence_root = row.get("sourcePoolEvidenceRoot")
    if not isinstance(evidence_root, Path):
        raise _fail("selected image candidate lacks frozen evidence root")
    try:
        receipt_path = resolve_evidence_file(
            evidence_root,
            row["acquisitionRef"],
            label="image acquisition receipt",
        )
        if compute_evidence_file_sha256(receipt_path) != row["acquisitionFileSha256"]:
            raise ValueError("image acquisition receipt file SHA drift")
        receipt = read_json(receipt_path)
        if not isinstance(receipt, Mapping):
            raise TypeError("image acquisition receipt must be one object")
        assert_valid(
            receipt,
            "source",
            "professional_image_acquisition_receipt",
            label="frozen image acquisition receipt",
        )
        if receipt.get("receiptDigest") != row.get("acquisitionDigest"):
            raise ValueError("image acquisition receipt digest drift")
        asset_id = str(row["objectRef"]).removeprefix("posts/image/")
        assets = [
            asset
            for asset in receipt.get("assets") or []
            if isinstance(asset, Mapping) and asset.get("assetId") == asset_id
        ]
        if len(assets) != 1:
            raise ValueError("image candidate must bind exactly one acquisition asset")
        asset = assets[0]
        if (
            asset.get("entityId") != entity_id
            or asset.get("contentSha256") != row.get("contentSha256")
            or asset.get("sourceAttribution") != row.get("sourceAttribution")
            or asset.get("acquisitionStatus") != "acquired"
            or asset.get("distributionDecision") not in {
                "research_allowed",
                "commercial_allowed",
            }
        ):
            raise ValueError("image candidate acquisition binding drift")
        asset_path = resolve_evidence_file(
            receipt_path.parent.parent,
            asset["assetRef"],
            label="image acquisition CAS asset",
        )
        if compute_evidence_file_sha256(asset_path) != asset["contentSha256"]:
            raise ValueError("image acquisition CAS bytes drift")
        plan_spec = asset.get("planImageSpec")
        if not isinstance(plan_spec, Mapping):
            raise TypeError("image acquisition asset lacks planImageSpec")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise _fail(f"frozen image acquisition is invalid: {exc}") from exc

    collection_id = f"acquisition:{receipt['manifestId']}:{asset_id}"
    acquisition_ref = Path(str(row["acquisitionRef"]))
    acquisition_prefix = ("local", "workspace", "source-acquisition")
    if acquisition_ref.parts[: len(acquisition_prefix)] == acquisition_prefix:
        acquisition_ref = Path(*acquisition_ref.parts[len(acquisition_prefix) :])
    if (
        acquisition_ref.is_absolute()
        or ".." in acquisition_ref.parts
        or len(acquisition_ref.parts) < 2
        or acquisition_ref.parts[-2] != "receipts"
        or acquisition_ref.suffix != ".json"
    ):
        raise _fail("frozen image acquisition receiptRef is non-canonical")
    image = {
        **dict(plan_spec),
        "sourcePath": asset_path,
        "sourceCollectionId": collection_id,
        "acquisitionReceiptRef": acquisition_ref.as_posix(),
        "professionalAssetId": asset_id,
        "professionalContentSha256": str(asset["contentSha256"]),
        "researchLane": "image",
    }
    source_attribution = dict(asset["sourceAttribution"])
    source_body = (
        "---\n"
        "researchLane: image\n"
        f"sourceCollectionId: {collection_id}\n"
        f"creator: {asset['creator']}\n"
        f"url: {asset['sourceUrl']}\n"
        f"license: {asset['license']}\n"
        "---\n\n"
        f"{entity_id} 专业图片来源集合，仅供结构化资产与授权链使用。\n"
    )
    object_dir = resolve_entity_object_dir(
        execution_id,
        entity_id,
        etype_hint=entity_type,
    )
    return write_source_unit(
        object_dir,
        ordinal=1,
        source_id=str(asset.get("provider") or "professional_image"),
        source_md=source_body,
        clean_md=source_body,
        quality={
            "sourceId": str(asset.get("provider") or "professional_image"),
            "entity": entity_id,
            "quality": "High",
            "score": 100,
            "reasons": ["frozen_scale_source_pool", "independent_asset_review"],
            "url": str(asset["sourceUrl"]),
            "statusCode": 200,
            "fetchSucceeded": True,
        },
        platform=str(asset["platform"]),
        source_category="image_collection",
        source_kind="image_collection",
        extractor="frozen_professional_image_acquisition",
        policy_revision="scale-source-pool-image-v1",
        source_use_mode=(
            "licensed_adaptation"
            if asset.get("rightsStatus") == "verified"
            else "rights_audit_only"
        ),
        research_lane="image",
        license_value=str(asset["license"]),
        url=str(asset["sourceUrl"]),
        title=str(asset["displayName"]),
        target_ref=str(row["entityRef"]),
        relevance=str(asset["relevance"]),
        images=[image],
        execution_id=execution_id,
        build_variants=False,
        source={"sourceAttribution": source_attribution},
        frozen_source_unit_id="image-pool-" + str(row["candidateId"]).split("-", 1)[-1],
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

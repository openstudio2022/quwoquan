"""data download — multi-platform source acquisition."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.paths import ensure_batch_layout, batch_root, source_unit_dir  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.batch_manifest import write_batch_manifest, write_source_catalog  # noqa: E402
from _common.content_evidence import anonymize_source_markdown, score_source_markdown  # noqa: E402
from _common.entity_extract import entity_ref as build_entity_ref, require_domain_etype  # noqa: E402
from _common.source_catalog import (  # noqa: E402
    coverage_issues,
    source_category_coverage,
    source_unit_category_issues,
    vertical_from_task_id,
)
from _common.source_unit import resolve_entity_object_dir, slugify, write_source_unit  # noqa: E402
from _common.image_rules import (  # noqa: E402
    MIN_ENTITY_IMAGES,
    min_count_issue,
    pixel_size_issue,
    relevance_issue,
)
from _common.image_safety import assess_image  # noqa: E402
from _common.image_variants import image_dimensions  # noqa: E402
from _common.image_safety import dedupe_image_payloads  # noqa: E402
from _common.stage_reports import write_gate_report, write_stage_result  # noqa: E402
from download.gate import download_requirements, gate_download  # noqa: E402
from download.source_inputs import (
    curated_sources_for_entity,
    curated_images_for_entity,
    manual_body_note,
    source_plan_rights_issues,
    source_frontmatter,
)  # noqa: E402
from download.fetch import fetch_image_payload, fetch_source_payload  # noqa: E402
from download.prepare import prepare_source_plan, prepare_source_screen  # noqa: E402
from vertical.license import normalize_rights_payload, validate_image_rights  # noqa: E402

SOURCE_UNIT_MAX_IMAGES_PER_SOURCE = max(1, int(os.environ.get("QWQ_SOURCE_UNIT_MAX_IMAGES_PER_SOURCE", "1")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_download_progress(
    task_id: str,
    batch_id: str,
    *,
    status: str,
    entity_id: str = "",
    entity_index: int = 0,
    entity_count: int = 0,
    sources: int = 0,
    images: int = 0,
    message: str = "",
) -> None:
    shared = batch_root(task_id, batch_id) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    write_json(
        shared / "download_progress.json",
        {
            "schemaVersion": "quwoquan.download.progress",
            "updatedAt": _now_iso(),
            "status": status,
            "entityId": entity_id,
            "entityIndex": entity_index,
            "entityCount": entity_count,
            "sources": sources,
            "images": images,
            "message": message,
        },
    )


def _stable_source_image_collection_id(
    *,
    entity_id: str,
    source_id: str,
    spec: Mapping[str, Any],
) -> str:
    """Current-contract collection id for an article/homepage source image.

    Source-unit images are not independent gallery collections, but they still
    need a globally stable identity for cross-work reuse gates. Local ids such
    as ``article_qunar_base_1`` collide across entities, so derive the identity
    from the actual image landing/proof URL and the target entity.
    """

    existing = str(spec.get("sourceCollectionId") or "").strip()
    local_default = f"article:{source_id}"
    if existing and existing != local_default:
        return existing
    key = str(
        spec.get("authorizationProof")
        or spec.get("sourceUrl")
        or spec.get("url")
        or spec.get("collectionPageUrl")
        or source_id
    ).strip()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    entity_key = slugify(entity_id)[:48]
    return f"source_image:{entity_key}:{digest}"


def _source_image_requires_ocr(spec: Mapping[str, Any]) -> bool:
    platform = str(spec.get("platform") or "").casefold()
    proof = str(spec.get("authorizationProof") or spec.get("sourceUrl") or spec.get("url") or "").casefold()
    license_value = str(spec.get("license") or "").casefold()
    trusted_open_license = (
        "wikimedia commons" in platform
        or "openverse" in platform
        or "commons.wikimedia.org" in proof
    )
    has_open_license = any(token in license_value for token in ("cc by", "cc-by", "cc0", "public domain"))
    return not (trusted_open_license and has_open_license and proof)


def _assess_source_image(path: Path, spec: Mapping[str, Any]):
    try:
        return assess_image(path, require_ocr=_source_image_requires_ocr(spec))
    except TypeError:
        return assess_image(path)


def _cached_source_image_payload(
    object_dir: Path,
    *,
    ordinal: int,
    source_id: str,
    spec: Mapping[str, Any],
) -> dict[str, Any] | None:
    unit = source_unit_dir(object_dir, ordinal, source_id)
    index_path = unit / "assets" / "index.json"
    if not index_path.is_file():
        return None
    try:
        rows = read_json(index_path).get("assets") or []
    except (OSError, ValueError, TypeError):
        return None
    wanted = {
        str(spec.get("url") or "").strip(),
        str(spec.get("sourceUrl") or "").strip(),
        str(spec.get("authorizationProof") or "").strip(),
    }
    wanted.discard("")
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_keys = {
            str(row.get("url") or "").strip(),
            str(row.get("requestedUrl") or "").strip(),
            str(row.get("sourceUrl") or "").strip(),
            str(row.get("authorizationProof") or "").strip(),
        }
        row_keys.discard("")
        if wanted and not (wanted & row_keys):
            continue
        file_name = str(row.get("fileName") or "").strip()
        if not file_name:
            continue
        path = unit / "assets" / file_name
        if not path.is_file():
            continue
        try:
            body = path.read_bytes()
        except OSError:
            continue
        if not body:
            continue
        return {
            "url": str(row.get("url") or spec.get("url") or ""),
            "requestedUrl": str(row.get("requestedUrl") or spec.get("url") or ""),
            "normalizedFromUrl": str(row.get("normalizedFromUrl") or ""),
            "sourceUrl": str(row.get("sourceUrl") or spec.get("sourceUrl") or ""),
            "contentType": str(row.get("contentType") or ""),
            "sha256": str(row.get("sha256") or "").removeprefix("sha256:") or hashlib.sha256(body).hexdigest(),
            "ext": Path(file_name).suffix or ".jpg",
            "bytes": body,
            "fromCache": True,
        }
    return None


def _image_lane_source_unit_dirs(object_dir: Path) -> set[Path]:
    """Return existing image/homepage-image source units for monotonic repair.

    Download retries should be allowed to fail without deleting the last
    usable visual evidence. Successful retries still prune through the normal
    source-plan commit path.
    """

    sources_root = object_dir / "1.download" / "sources"
    if not sources_root.is_dir():
        return set()
    out: set[Path] = set()
    for child in sources_root.iterdir():
        if not child.is_dir():
            continue
        try:
            meta = read_json(child / "meta.json")
        except (OSError, ValueError, TypeError):
            meta = {}
        lane = str(meta.get("researchLane") or "")
        if lane in {"image", "homepage_image"}:
            out.add(child)
    return out


def _cached_image_lane_payload(object_dir: Path, spec: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reuse a previously retained image-lane asset before hitting the network.

    Independent image works are written as image/homepage_image source units.
    Repeated repair runs often ask for the same URL/proof again; using the
    already audited bytes avoids transient CDN/network failures turning into
    destructive evidence churn.
    """

    wanted = {
        str(spec.get("url") or "").strip(),
        str(spec.get("sourceUrl") or "").strip(),
        str(spec.get("authorizationProof") or "").strip(),
    }
    wanted.discard("")
    if not wanted:
        return None
    for unit in sorted(_image_lane_source_unit_dirs(object_dir), key=lambda path: path.name):
        index_path = unit / "assets" / "index.json"
        if not index_path.is_file():
            continue
        try:
            rows = read_json(index_path).get("assets") or []
        except (OSError, ValueError, TypeError):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            row_keys = {
                str(row.get("url") or "").strip(),
                str(row.get("requestedUrl") or "").strip(),
                str(row.get("normalizedFromUrl") or "").strip(),
                str(row.get("sourceUrl") or "").strip(),
                str(row.get("authorizationProof") or "").strip(),
            }
            row_keys.discard("")
            if not (wanted & row_keys):
                continue
            file_name = str(row.get("fileName") or "").strip()
            if not file_name:
                continue
            path = unit / "assets" / file_name
            if not path.is_file():
                continue
            try:
                body = path.read_bytes()
            except OSError:
                continue
            if not body:
                continue
            return {
                "url": str(row.get("url") or spec.get("url") or ""),
                "requestedUrl": str(row.get("requestedUrl") or spec.get("url") or ""),
                "normalizedFromUrl": str(row.get("normalizedFromUrl") or ""),
                "sourceUrl": str(row.get("sourceUrl") or spec.get("sourceUrl") or ""),
                "contentType": str(row.get("contentType") or ""),
                "sha256": str(row.get("sha256") or "").removeprefix("sha256:") or hashlib.sha256(body).hexdigest(),
                "ext": Path(file_name).suffix or ".jpg",
                "bytes": body,
                "fromCache": True,
            }
    return None


def _cached_source_quality_if_better(
    object_dir: Path,
    *,
    ordinal: int,
    source_id: str,
    url: str,
    candidate_quality: dict,
) -> dict | None:
    """Return a same-URL cached quality row when the new fetch is worse.

    Repeated runs must be monotonic: a transient block/probe page cannot replace
    a previously retained source unit with Reject or a lower-quality result.
    """
    unit = source_unit_dir(object_dir, ordinal, source_id)
    meta_path = unit / "meta.json"
    quality_path = unit / "source.quality.json"
    source_path = unit / "source.md"
    if not (meta_path.is_file() and quality_path.is_file() and source_path.is_file()):
        return None
    try:
        meta = read_json(meta_path)
        cached = read_json(quality_path)
    except (OSError, ValueError, TypeError):
        return None
    if str(meta.get("url") or "") != str(url or ""):
        return None

    rank = {"Reject": 0, "C-context": 1, "B-fact": 2, "A-story": 3}
    cached_key = (rank.get(str(cached.get("quality") or ""), 0), int(cached.get("score") or 0))
    candidate_key = (
        rank.get(str(candidate_quality.get("quality") or ""), 0),
        int(candidate_quality.get("score") or 0),
    )
    return cached if cached_key > candidate_key else None


def _prune_stale_source_units(object_dir: Path, written_dirs: set[Path]) -> list[str]:
    """Remove source units that are no longer present in the current plan.

    A repair run may replace an image collection or text source. Keeping old
    source-unit directories makes later gates see evidence that the current
    source plan did not authorize, so each entity fetch commits exactly the
    source units written in this run.
    """

    sources_root = object_dir / "1.download" / "sources"
    if not sources_root.is_dir():
        return []
    keep = {path.resolve() for path in written_dirs}
    pruned: list[str] = []
    for child in sorted(sources_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if child.resolve() in keep:
            continue
        shutil.rmtree(child)
        pruned.append(child.name)
    return pruned


def _move_rejected_source_unit(object_dir: Path, unit_dir: Path) -> Path:
    """Keep rejected fetches for audit, outside the consumable source bundle."""

    rejected_root = object_dir / "1.download" / "rejected_sources"
    rejected_root.mkdir(parents=True, exist_ok=True)
    dest = rejected_root / unit_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(unit_dir), str(dest))
    return dest


def _prune_stale_rejected_source_units(object_dir: Path, written_dirs: set[Path]) -> list[str]:
    rejected_root = object_dir / "1.download" / "rejected_sources"
    if not rejected_root.is_dir():
        return []
    keep = {path.resolve() for path in written_dirs}
    pruned: list[str] = []
    for child in sorted(rejected_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if child.resolve() in keep:
            continue
        shutil.rmtree(child)
        pruned.append(child.name)
    return pruned


def _download_source_unit_images(
    source: Mapping[str, Any],
    *,
    task_id: str,
    batch_id: str,
    entity_id: str,
    object_dir: Path,
    ordinal: int,
    vertical: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Download and gate images that belong to the same text source unit.

    Article/homepage source images are part of that source's draft evidence.
    They must stay attached to the source unit instead of being mixed into the
    independent image-work collection lane.
    """
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    raw_images = source.get("imageUrls") or []
    if not isinstance(raw_images, list):
        return images, [f"{source.get('source_id') or '?'} imageUrls must be a list"]
    source_id = str(source.get("source_id") or "")
    for idx_img, raw in enumerate(raw_images, start=1):
        if len(images) >= SOURCE_UNIT_MAX_IMAGES_PER_SOURCE:
            break
        if not isinstance(raw, Mapping):
            issues.append(f"{source_id} image[{idx_img}] invalid payload")
            continue
        spec = {
            **{
                "license": source.get("license") or "",
                "credit": source.get("credit") or "",
                "termsUrl": source.get("termsUrl") or "",
                "licenseSnapshot": source.get("licenseSnapshot") or "",
                "authorizationProof": source.get("authorizationProof") or "",
                "usageScope": source.get("usageScope") or "",
                "sourceUrl": source.get("url") or "",
                "platform": source.get("platform") or "",
                "sourceCollectionId": "",
                "creator": source.get("credit") or "",
                "collectionPageUrl": source.get("url") or "",
            },
            **{k: v for k, v in raw.items() if v not in ("", None)},
        }
        spec["sourceCollectionId"] = _stable_source_image_collection_id(
            entity_id=entity_id,
            source_id=source_id,
            spec=spec,
        )
        label = f"{entity_id}/{source_id}#{idx_img}"
        rights_issues = validate_image_rights(spec, vertical=vertical)
        if rights_issues:
            issues.extend(f"{label}: {issue}" for issue in rights_issues)
            continue
        payload = _cached_source_image_payload(
            object_dir,
            ordinal=ordinal,
            source_id=source_id,
            spec=spec,
        )
        if payload is None:
            payload = fetch_image_payload(str(spec.get("url") or ""))
        if payload is None:
            issues.append(f"{label}: imageFetch failed/non-image/too small ({spec.get('url')})")
            continue
        dims = image_dimensions(payload["bytes"]) or (0, 0)
        width, height = dims
        px_issue = pixel_size_issue(width, height, asset_id=label)
        if px_issue:
            issues.append(px_issue)
            continue
        # assess_image operates on a path; keep source-unit image checks in the
        # batch temp tree next to the existing image lane checks.
        temp_dir = batch_root(task_id, batch_id) / "_shared" / "tmp_source_unit_image_checks"
        temp_dir.mkdir(parents=True, exist_ok=True)
        safe_slug = slugify(f"{entity_id}_{source_id}_{idx_img}")
        temp_file = temp_dir / f"{safe_slug}{payload['ext']}"
        temp_file.write_bytes(payload["bytes"])
        verdict = _assess_source_image(temp_file, spec)
        if verdict.blocks_image_publish:
            issues.append(f"{label}: imageSafety blocked ({verdict.status}) reasons={list(verdict.reasons)}")
            continue
        relevance = str(spec.get("relevance") or spec.get("caption") or "")
        rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=label)
        if rel_issue:
            issues.append(rel_issue)
            continue
        rights = normalize_rights_payload(spec)
        images.append(
            {
                "bytes": payload["bytes"],
                "ext": payload["ext"],
                "url": payload.get("url") or spec.get("url") or "",
                "requestedUrl": payload.get("requestedUrl") or spec.get("url") or "",
                "normalizedFromUrl": payload.get("normalizedFromUrl") or "",
                "sourceUrl": spec.get("sourceUrl") or spec.get("url") or "",
                "contentType": payload.get("contentType") or "",
                "width": width,
                "height": height,
                "license": rights.get("license") or spec.get("license") or "",
                "credit": rights.get("credit") or spec.get("credit") or "",
                "termsUrl": rights.get("termsUrl") or spec.get("termsUrl") or "",
                "licenseSnapshot": rights.get("licenseSnapshot") or spec.get("licenseSnapshot") or "",
                "usageScope": rights.get("usageScope") or spec.get("usageScope") or "",
                "generationModel": rights.get("generationModel") or "",
                "generationPromptHash": rights.get("generationPromptHash") or "",
                "generatedAt": rights.get("generatedAt") or "",
                "syntheticDisclosure": rights.get("syntheticDisclosure") or "",
                "sourceCollectionId": spec.get("sourceCollectionId") or "",
                "creator": spec.get("creator") or spec.get("credit") or "",
                "collectionPageUrl": spec.get("collectionPageUrl") or spec.get("sourceUrl") or "",
                "authorizationProof": spec.get("authorizationProof") or "",
                "caption": str(spec.get("caption") or relevance),
                "relevance": relevance,
                "slug": f"{source_id}_{idx_img}",
            }
        )
    images, duplicates = dedupe_image_payloads(images)
    if duplicates:
        issues.append(f"{source_id}: source image dedupe removed {len(duplicates)} near-duplicate image(s)")
    if images:
        return images, []
    return images, issues


def handle_download(args: argparse.Namespace) -> None:
    """Orchestrate download: source_plan → fetch → source_screen.

    Steps:
    1. source_plan: Agent plans multi-platform download strategy per entity
    2. fetch: Script executes HTTP fetches + text extraction
    3. source_screen: Agent screens quality/relevance/copyright

    Output: batches/{batch_id}/entities/{domain}/{type}/{entity}/1.download/sources/{NN}.{source_id}/source.md
    """
    task_id = args.task
    batch_id = args.batch
    entity_ids = args.entity_ids.split(",") if args.entity_ids else []

    ensure_batch_layout(task_id, batch_id, "download")
    dl_root = batch_root(task_id, batch_id) / "entities"
    # 批次级公共信息上提（规格 §4/§14）：定义快照 + 受控来源类目，不在对象目录重复。
    write_batch_manifest(task_id, batch_id, command="download")
    write_source_catalog(task_id, batch_id)

    print(f"[download] Task: {task_id}, Batch: {batch_id}", flush=True)
    print(f"[download] Target entities: {entity_ids}", flush=True)
    print(f"[download] Work dir: {dl_root}", flush=True)
    print(f"[download] Steps: source_plan → fetch → source_screen", flush=True)

    entity_type = getattr(args, "entity_type", "") or ""
    vertical = vertical_from_task_id(task_id)
    entities = [{"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type} for entity_id in entity_ids]
    prepare_source_plan(task_id, batch_id, entities)
    for entity in entities:
        planned_sources = [
            {
                "source_id": source.get("source_id") or "",
                "platform": source["platform"],
                "url": source["url"],
                "category": source.get("category") or "",
                "sourceRole": source.get("sourceRole") or "",
                "researchLane": source.get("researchLane") or "",
                "expectedContentType": "article",
                "priority": index + 1,
            }
            for index, source in enumerate(curated_sources_for_entity(task_id, batch_id, entity["entityId"], entity_type))
        ]
        write_stage_result(
            task_id,
            batch_id,
            "download",
            "source_plan",
            entity["entityId"],
            {
                "entityId": entity["entityId"],
                "sources": planned_sources,
            },
        )
        # 源类别覆盖门（「全」硬约束）：≥2 源 + 覆盖 ≥N 类（含核心类），杜绝同质单一来源。
        coverage = source_category_coverage(planned_sources, vertical=vertical)
        plan_issues: list[str] = []
        if len(planned_sources) < 2:
            plan_issues.append("sourcePlan: fewer than 2 planned sources")
        plan_issues.extend(
            source_plan_rights_issues(
                task_id,
                batch_id,
                entity["entityId"],
                entity_type,
                require_explicit=download_requirements(task_id)["minSources"] >= 4,
            )
        )
        plan_issues.extend(coverage_issues(planned_sources, vertical=vertical, entity_id=entity["entityId"]))
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="source_plan",
            ref=entity["entityId"],
            passed=not plan_issues,
            issues=plan_issues,
            evidence_summary={
                "plannedSourceCount": len(planned_sources),
                "coveredCategories": coverage["coveredCategories"],
                "coveredCount": coverage["coveredCount"],
                "minCategories": coverage["minCategories"],
                "missingCore": coverage["missingCore"],
                "unknownPlatforms": coverage["unknownPlatforms"],
            },
            next_step="fetch",
            fallback_stage="source_plan" if plan_issues else None,
        )

    domain, etype = require_domain_etype(
        entity_type,
        context=f"download entity_type for task={task_id} batch={batch_id}",
    )
    fetched_sources: list[dict] = []
    quality_by_entity: dict[str, list[dict]] = defaultdict(list)
    failed_image_entities: list[str] = []
    _write_download_progress(
        task_id,
        batch_id,
        status="running",
        entity_count=len(entity_ids),
        message="download_fetch started",
    )
    for entity_index, entity_id in enumerate(entity_ids, start=1):
        print(f"[download] Fetch entity {entity_index}/{len(entity_ids)}: {entity_id}", flush=True)
        _write_download_progress(
            task_id,
            batch_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=len(entity_ids),
            message="entity fetch started",
        )
        # 对象同构目录：来源写成来源单元（编号 + 类目 + assets/），禁对象级散 images/。
        object_dir = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
        target_ref = build_entity_ref(domain, etype, entity_id)
        sources = curated_sources_for_entity(task_id, batch_id, entity_id, entity_type)
        existing_image_source_dirs = _image_lane_source_unit_dirs(object_dir)
        written_source_dirs: set[Path] = set()
        written_rejected_source_dirs: set[Path] = set()
        # 实体级 imageUrls 全部归属首个（概览类）来源单元，并标注相关性，避免无归属散图。
        image_specs = curated_images_for_entity(task_id, batch_id, entity_id, entity_type)
        image_manifest: list[dict] = []
        image_rights_issues: list[str] = []
        image_quality_issues: list[str] = []
        pending_images: list[dict] = []
        required_images = download_requirements(task_id)["minImages"]
        image_fetch_target = max(
            required_images,
            int(os.environ.get("QWQ_DOWNLOAD_IMAGE_FETCH_TARGET_PER_ENTITY", str(required_images + 2))),
        )
        image_candidate_limit = max(
            image_fetch_target,
            int(os.environ.get("QWQ_DOWNLOAD_IMAGE_CANDIDATE_LIMIT_PER_ENTITY", str(image_fetch_target + 4))),
        )
        for idx_img, spec in enumerate(image_specs, start=1):
            if len(pending_images) >= image_fetch_target:
                break
            if idx_img > image_candidate_limit:
                image_quality_issues.append(
                    f"imageFetch: {entity_id} stopped after {image_candidate_limit} image candidate(s)"
                )
                break
            asset_label = f"{entity_id}#{idx_img}"
            issues = validate_image_rights(spec, vertical=vertical)
            if issues:
                image_rights_issues.extend([f"{idx_img}: {issue}" for issue in issues])
                continue
            payload = _cached_image_lane_payload(object_dir, spec)
            if payload is None:
                payload = fetch_image_payload(spec["url"])
            if payload is None:
                image_quality_issues.append(
                    f"imageFetch: {asset_label} 下载失败/非图片/过小 ({spec.get('url')})"
                )
                continue
            # 最小像素尺寸门：糊图/缩略图不进内容页。
            dims = image_dimensions(payload["bytes"]) or (0, 0)
            width, height = dims
            px_issue = pixel_size_issue(width, height, asset_id=asset_label)
            if px_issue:
                image_quality_issues.append(px_issue)
                continue
            temp_path = batch_root(task_id, batch_id) / "_shared" / "tmp_image_checks" / f"{entity_id}_{idx_img}{payload['ext']}"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_bytes(payload["bytes"])
            verdict = _assess_source_image(temp_path, spec)
            if verdict.blocks_image_publish:
                image_quality_issues.append(
                    f"imageSafety: {asset_label} blocked ({verdict.status}) reasons={list(verdict.reasons)}"
                )
                continue
            # 相关性门：必须有与检索对象的真实相关性说明（来自 source_plan，禁通用模板串）。
            relevance = str(spec.get("relevance") or spec.get("caption") or "")
            rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=asset_label)
            if rel_issue:
                image_quality_issues.append(rel_issue)
                continue
            rights = normalize_rights_payload(spec)
            pending_images.append(
                {
                    "bytes": payload["bytes"],
                    "ext": payload["ext"],
                    "url": payload.get("url") or spec["url"],
                    "requestedUrl": payload.get("requestedUrl") or spec["url"],
                    "normalizedFromUrl": payload.get("normalizedFromUrl") or "",
                    "sourceUrl": spec.get("sourceUrl") or spec["url"],
                    "contentType": payload.get("contentType") or "",
                    "width": width,
                    "height": height,
                    "license": rights.get("license") or spec.get("license") or "",
                    "credit": rights.get("credit") or spec.get("credit") or "",
                    "termsUrl": rights.get("termsUrl") or spec.get("termsUrl") or "",
                    "licenseSnapshot": rights.get("licenseSnapshot") or spec.get("licenseSnapshot") or "",
                    "usageScope": rights.get("usageScope") or spec.get("usageScope") or "",
                    "generationModel": rights.get("generationModel") or "",
                    "generationPromptHash": rights.get("generationPromptHash") or "",
                    "generatedAt": rights.get("generatedAt") or "",
                    "syntheticDisclosure": rights.get("syntheticDisclosure") or "",
                    "sourceCollectionId": spec.get("sourceCollectionId") or "",
                    "creator": spec.get("creator") or spec.get("credit") or "",
                    "collectionPageUrl": spec.get("collectionPageUrl") or spec.get("sourceUrl") or "",
                    "authorizationProof": spec.get("authorizationProof") or "",
                    "researchLane": spec.get("researchLane") or "image",
                    "sourceId": spec.get("sourceId") or "",
                    "caption": str(spec.get("caption") or relevance),
                    "relevance": relevance,
                    "slug": f"{entity_id}_{idx_img}",
                    "sha256": payload.get("sha256"),
                }
            )
            image_manifest.append({**payload, "url": spec["url"], **rights})
        # 感知哈希去重（落盘前）：剔除同实体近重复图，避免画报/详情页重复观感。
        pending_images, dup_idx = dedupe_image_payloads(pending_images)
        if dup_idx:
            image_quality_issues.append(
                f"imageDedupe: {entity_id} 剔除 {len(dup_idx)} 张近重复图"
            )
            image_manifest = [
                m for i, m in enumerate(image_manifest) if i not in set(dup_idx)
            ]

        for ordinal, source in enumerate(sources, start=1):
            html_bytes: bytes | None = None
            status_code = 0
            fetched_text = ""
            try:
                fetched = fetch_source_payload(source["url"])
                html_bytes = fetched["htmlBytes"]
                status_code = fetched["statusCode"]
                fetched_text = str(fetched.get("text") or "").strip()
                source_md = source_frontmatter(source, entity_id)
                if fetched_text:
                    source_md += fetched_text
            except Exception:
                source_md = source_frontmatter(source, entity_id)
            note = manual_body_note(source)
            if note:
                source_md = source_md.rstrip() + f"\n\n{note}\n"
            clean_md = anonymize_source_markdown(source_md)
            assessment = score_source_markdown(source["source_id"], source_md, entity_name=entity_id)
            quality = {
                "sourceId": source["source_id"],
                "entity": entity_id,
                "quality": assessment.quality,
                "score": assessment.score,
                "reasons": list(assessment.reasons),
                "excerpt": assessment.excerpt,
                "url": source["url"],
                "statusCode": status_code,
                "fetchSucceeded": bool(fetched_text),
                "taskProvidedBodyPresent": bool(str(source.get("body") or "").strip()),
            }
            cached_quality = _cached_source_quality_if_better(
                object_dir,
                ordinal=ordinal,
                source_id=source["source_id"],
                url=source["url"],
                candidate_quality=quality,
            )
            if cached_quality is not None:
                print(
                    "[download] Preserve better cached source "
                    f"{entity_id}/{source['source_id']}: "
                    f"{cached_quality.get('quality')}({cached_quality.get('score')}) > "
                    f"{quality.get('quality')}({quality.get('score')})",
                    flush=True,
                )
                unit = source_unit_dir(object_dir, ordinal, source["source_id"])
                source_md = (unit / "source.md").read_text(encoding="utf-8")
                clean_path = unit / "source.clean.md"
                clean_md = clean_path.read_text(encoding="utf-8") if clean_path.is_file() else ""
                page_path = unit / "page.html"
                html_bytes = page_path.read_bytes() if page_path.is_file() else None
                quality = {**cached_quality, "retainedFromCache": True}
            source_images, source_image_issues = _download_source_unit_images(
                source,
                task_id=task_id,
                batch_id=batch_id,
                entity_id=entity_id,
                object_dir=object_dir,
                ordinal=ordinal,
                vertical=vertical,
            )
            if source_image_issues:
                image_quality_issues.extend(
                    f"sourceImage:{source['source_id']}: {issue}"
                    for issue in source_image_issues
                )
            write_source_unit(
                object_dir,
                ordinal=ordinal,
                source_id=source["source_id"],
                source_md=source_md,
                clean_md=clean_md,
                html_bytes=html_bytes,
                quality=quality,
                platform=source.get("platform") or "web",
                source_category=source.get("category") or source.get("platform") or "web",
                source_use_mode=source.get("sourceUseMode") or "",
                source_role=source.get("sourceRole") or "",
                image_evidence_mode=source.get("imageEvidenceMode") or "",
                research_lane=source.get("researchLane") or "",
                license_value=source.get("license") or "",
                url=source["url"],
                title=source.get("title") or source["source_id"],
                target_ref=target_ref,
                relevance=f"覆盖 {entity_id} 的基础事实/交通/季节等",
                images=source_images,
                task_id=task_id,
                batch_id=batch_id,
            )
            unit_dir = source_unit_dir(object_dir, ordinal, source["source_id"])
            if str(quality.get("quality") or "") == "Reject":
                rejected_dir = _move_rejected_source_unit(object_dir, unit_dir)
                written_rejected_source_dirs.add(rejected_dir)
                print(
                    f"[download] Rejected source isolated {entity_id}/{source['source_id']}",
                    flush=True,
                )
                continue
            written_source_dirs.add(unit_dir)
            quality_by_entity[entity_id].append(
                {
                    "sourceId": source["source_id"],
                    "quality": quality.get("quality"),
                    "score": quality.get("score"),
                    "url": source["url"],
                    "statusCode": quality.get("statusCode", status_code),
                    "retainedFromCache": bool(quality.get("retainedFromCache")),
                }
            )
            fetched_sources.append(
                {
                    "sourceId": source["source_id"],
                    "url": source["url"],
                    "quality": quality.get("quality"),
                    "score": quality.get("score"),
                    "entityId": entity_id,
                    "retainedFromCache": bool(quality.get("retainedFromCache")),
                }
            )
        image_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for image in pending_images:
            lane = str(image.get("researchLane") or "image")
            collection_id = str(image.get("sourceCollectionId") or "").strip()
            if not collection_id:
                image_quality_issues.append(
                    f"imageCollection: {image.get('url') or '?'} missing sourceCollectionId"
                )
                continue
            image_groups[(lane, collection_id)].append(image)
        for offset, ((lane, collection_id), group) in enumerate(
            sorted(image_groups.items()),
            start=1,
        ):
            first = group[0]
            source_id = (
                str(first.get("sourceId") or "").strip()
                or f"{lane}_{slugify(collection_id)}"
            )
            unit_lane = "homepage_image" if lane == "homepage" else "image"
            collection_page = str(first.get("collectionPageUrl") or first.get("sourceUrl") or "")
            collection_md = (
                "---\n"
                f"researchLane: {unit_lane}\n"
                f"sourceCollectionId: {collection_id}\n"
                f"creator: {first.get('creator') or first.get('credit') or ''}\n"
                f"url: {collection_page}\n"
                f"license: {first.get('license') or ''}\n"
                "---\n\n"
                f"{entity_id} 图片来源集合，仅供结构化资产与授权链使用。\n"
            )
            write_source_unit(
                object_dir,
                ordinal=len(sources) + offset,
                source_id=source_id,
                source_md=collection_md,
                quality={
                    "sourceId": source_id,
                    "entity": entity_id,
                    "quality": "B-fact",
                    "score": 1,
                    "reasons": ["structured image collection"],
                    "url": collection_page,
                    "fetchSucceeded": True,
                },
                platform=str(first.get("platform") or "image_collection"),
                source_category="image_collection",
                source_use_mode="licensed_adaptation",
                research_lane=unit_lane,
                license_value=str(first.get("license") or ""),
                url=collection_page,
                title=f"{entity_id} image collection {collection_id}",
                target_ref=target_ref,
                relevance=f"{entity_id} 同一来源图片集合",
                images=group,
                task_id=task_id,
                batch_id=batch_id,
            )
            written_source_dirs.add(source_unit_dir(object_dir, len(sources) + offset, source_id))
        kept_images = len(pending_images)
        count_issue = (
            min_count_issue(kept_images, entity_id=entity_id)
            if required_images <= MIN_ENTITY_IMAGES
            else (
                f"imageCount: {entity_id} 仅下到 {kept_images} 张合格去重图"
                f"（规模化任务要求 ≥{required_images}）"
                if kept_images < required_images
                else None
            )
        )
        fetch_issues = list(image_rights_issues)
        if count_issue:
            fetch_issues.append(count_issue)
        if kept_images == 0 and not image_rights_issues:
            fetch_issues.append(
                "imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"
            )
        preserved_image_dirs: set[Path] = set()
        if fetch_issues:
            preserved_image_dirs = existing_image_source_dirs - written_source_dirs
            written_source_dirs.update(preserved_image_dirs)
        pruned_units = _prune_stale_source_units(object_dir, written_source_dirs)
        pruned_rejected_units = _prune_stale_rejected_source_units(
            object_dir,
            written_rejected_source_dirs,
        )
        if preserved_image_dirs:
            print(
                f"[download] Preserved {len(preserved_image_dirs)} previous image source unit(s) "
                f"for failed repair of {entity_id}",
                flush=True,
            )
        if pruned_units:
            print(
                f"[download] Pruned {len(pruned_units)} stale source unit(s) for {entity_id}: "
                + ", ".join(pruned_units),
                flush=True,
            )
        if pruned_rejected_units:
            print(
                f"[download] Pruned {len(pruned_rejected_units)} stale rejected source unit(s) for {entity_id}: "
                + ", ".join(pruned_rejected_units),
                flush=True,
            )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="image_rights",
            ref=entity_id,
            passed=not image_rights_issues,
            issues=image_rights_issues,
            evidence_summary={"plannedImages": len(image_specs), "blockedImages": len(image_rights_issues)},
            next_step="image_fetch",
            fallback_stage="source_plan" if image_rights_issues else None,
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="image_fetch",
            ref=entity_id,
            passed=not fetch_issues,
            issues=fetch_issues,
            evidence_summary={
                "plannedImages": len(image_specs),
                "downloadedImages": kept_images,
                "minRequired": required_images,
                "rejectedForQuality": image_quality_issues,
            },
            next_step="quality_analysis",
            fallback_stage="source_plan" if fetch_issues else None,
        )
        if fetch_issues:
            failed_image_entities.append(entity_id)
        print(
            f"[download] Entity done {entity_index}/{len(entity_ids)}: {entity_id} "
            f"sources={len(sources)} images={kept_images}",
            flush=True,
        )
        _write_download_progress(
            task_id,
            batch_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=len(entity_ids),
            sources=len(sources),
            images=kept_images,
            message="entity fetch done",
        )

    prepare_source_screen(task_id, batch_id, fetched_sources)
    for source in fetched_sources:
        issues: list[str] = []
        if source["quality"] == "Reject":
            issues.append("sourceScreen: source scored Reject")
        write_stage_result(
            task_id,
            batch_id,
            "download",
            "source_screen",
            source["sourceId"],
            {
                "sourceId": source["sourceId"],
                "decision": "retain" if source["quality"] != "Reject" else "reject",
                "qualityScore": source["score"],
                "relevanceScore": source["score"],
                "copyrightStatus": "internal_reference",
                "reason": "quality gate auto-screen",
                "entityId": source["entityId"],
            },
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="source_screen",
            ref=source["sourceId"],
            passed=not issues,
            issues=issues,
            evidence_summary={
                "entityId": source["entityId"],
                "quality": source["quality"],
                "score": source["score"],
            },
            next_step="quality_analysis",
            fallback_stage="fetch" if issues else None,
        )
    for entity_id, rows in quality_by_entity.items():
        retained = [row for row in rows if row["quality"] != "Reject"]
        issues: list[str] = []
        if len(retained) < 1:
            issues.append("sourceScreen: no retained source for entity")
        # 受控类目门：阻断无类别的 weather_* 散来源（天气应作为百科/官方/攻略来源内事实）。
        for source in curated_sources_for_entity(task_id, batch_id, entity_id, entity_type):
            issues.extend(source_unit_category_issues(source["source_id"], source.get("platform") or ""))
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="entity_source_bundle",
            ref=entity_id,
            passed=not issues,
            issues=issues,
            evidence_summary={
                "sourceCount": len(rows),
                "retainedCount": len(retained),
                "qualities": [row["quality"] for row in rows],
            },
            next_step="quality_analysis",
            fallback_stage="source_plan" if issues else None,
        )
    print(
        f"[download] Planned {len(entities)} entity/entities and fetched {len(fetched_sources)} source bundle(s)",
        flush=True,
    )
    gate_issues = gate_download(task_id, batch_id)
    gate_issues.extend(
        f"{entity_id}: image gates failed (rights/fetch/safety/min-count); unsafe or unauthorized images must not enter assets"
        for entity_id in failed_image_entities
    )
    if gate_issues:
        print(f"[download] Gate FAILED ({len(gate_issues)} issue(s)):", file=sys.stderr, flush=True)
        for issue in gate_issues:
            print(f"  - {issue}", file=sys.stderr, flush=True)
        _write_download_progress(
            task_id,
            batch_id,
            status="failed",
            entity_count=len(entity_ids),
            sources=len(fetched_sources),
            message="; ".join(gate_issues[:5]),
        )
        raise SystemExit(1)
    _write_download_progress(
        task_id,
        batch_id,
        status="done",
        entity_count=len(entity_ids),
        sources=len(fetched_sources),
        message="download gate passed",
    )
    print("[download] Gate PASSED", flush=True)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("download", help="Multi-platform source acquisition")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--entity-ids", required=True, help="Comma-separated entity IDs")
    p.add_argument("--entity-type", default="", help="实体类型(可选，仅记录到 source_plan)")
    p.set_defaults(handler=handle_download)

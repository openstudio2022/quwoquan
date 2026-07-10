"""Download image, source-unit cache and rejection helpers."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Lock
from typing import Any, Mapping, Sequence

from _common.paths import ensure_batch_layout, batch_root
from _common.io import read_json, write_json
from _common.batch_manifest import write_batch_manifest, write_source_catalog
from _common.content_evidence import clean_source_markdown, score_source_markdown
from _common.entity_extract import entity_ref as build_entity_ref, require_domain_etype
from _common.source_catalog import (
    coverage_issues,
    platform_category,
    source_category_coverage,
    source_unit_category_issues,
    vertical_from_task_id,
)
from _common.source_unit import (
    find_source_unit_raw_snapshot,
    iter_source_units,
    resolve_entity_object_dir,
    slugify,
    write_source_unit,
)
from _common.image_rules import MIN_ENTITY_IMAGES, pixel_size_issue, relevance_issue
from _common.image_safety import assess_image, assess_image_cached, dedupe_image_payloads
from _common.image_variants import image_dimensions
from _common.stage_reports import write_gate_report, write_stage_result
from download.gate import download_requirements, gate_download
from download.source_inputs import (
    curated_sources_for_entity,
    curated_images_for_entity,
    manual_body_note,
    source_plan_rights_issues,
    source_frontmatter,
)
from download.fetch import fetch_image_payload, fetch_source_payload
from download.prepare import prepare_source_plan, prepare_source_screen
from vertical.license import normalize_rights_payload, validate_image_rights

from download.handler_plan import *  # noqa: F403
from download import handler_bridge

def _source_screen_report_ref(entity_id: str, source_id: str) -> str:
    """Stable flat report ref for per-entity source screen evidence.

    Source ids such as ``article_qunar_base_1`` repeat across entities in large
    batches. A source-screen report keyed only by source id is overwritten by
    later entities and corrupts audit evidence. Keep the true ids in the
    payload, and use a flat entity+source key on disk so stage report iteration
    remains top-level ``*.json``.
    """
    raw = f"{entity_id}__{source_id}"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    safe = safe.strip("._-") or digest
    return f"{safe[:120]}_{digest}"

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

def _image_safety_cache_dir(task_id: str, batch_id: str) -> Path:
    return batch_root(task_id, batch_id) / "_shared" / "image_safety_cache"

def _write_image_check_temp_file(
    task_id: str,
    batch_id: str,
    *,
    subdir: str,
    payload: Mapping[str, Any],
) -> Path:
    body = payload.get("bytes") or b""
    digest = str(payload.get("sha256") or "").removeprefix("sha256:")
    if not digest and isinstance(body, (bytes, bytearray)):
        digest = hashlib.sha256(bytes(body)).hexdigest()
    ext = str(payload.get("ext") or ".jpg")
    if not ext.startswith("."):
        ext = "." + ext
    temp_dir = batch_root(task_id, batch_id) / "_shared" / subdir
    temp_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{(digest or 'unknown')[:16]}_"
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=ext, dir=temp_dir, delete=False) as handle:
        if isinstance(body, (bytes, bytearray)):
            handle.write(bytes(body))
        return Path(handle.name)

def _cleanup_image_check_temp_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return

def _assess_source_image(
    path: Path,
    spec: Mapping[str, Any],
    *,
    task_id: str = "",
    batch_id: str = "",
):
    if handler_bridge.patched("assess_image", assess_image):
        return handler_bridge.call("assess_image", assess_image, path)
    try:
        cache_dir = _image_safety_cache_dir(task_id, batch_id) if task_id and batch_id else None
        return handler_bridge.call(
            "assess_image_cached",
            assess_image_cached,
            path,
            cache_dir=cache_dir,
            require_ocr=_source_image_requires_ocr(spec),
        )
    except TypeError:
        return handler_bridge.call("assess_image", assess_image, path)

def _cached_source_image_payload(
    object_dir: Path,
    *,
    ordinal: int,
    source_id: str,
    spec: Mapping[str, Any],
) -> dict[str, Any] | None:
    unit = _find_source_unit_by_plan_key(
        object_dir,
        ordinal=ordinal,
        source_id=source_id,
    )
    if unit is None:
        return None
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

    out: set[Path] = set()
    for child in iter_source_units(object_dir):
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

def _find_source_unit_by_plan_key(
    object_dir: Path,
    *,
    ordinal: int,
    source_id: str,
    url: str = "",
) -> Path | None:
    for unit in iter_source_units(object_dir):
        try:
            meta = read_json(unit / "meta.json")
        except (OSError, ValueError, TypeError):
            meta = {}
        if int(meta.get("ordinal") or 0) != int(ordinal):
            continue
        if str(meta.get("sourceId") or "") != str(source_id or ""):
            continue
        if url and str(meta.get("url") or "") != str(url or ""):
            continue
        return unit
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
    unit = _find_source_unit_by_plan_key(
        object_dir,
        ordinal=ordinal,
        source_id=source_id,
        url=url,
    )
    if unit is None:
        return None
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

def _prune_stale_source_units(
    object_dir: Path,
    written_dirs: set[Path],
    *,
    selected_lanes: set[str] | None = None,
) -> list[str]:
    """Remove source units that are no longer present in the current plan.

    A repair run may replace an image collection or text source. Keeping old
    source-unit directories makes later gates see evidence that the current
    source plan did not authorize, so each entity fetch commits exactly the
    source units written in this run.
    """

    keep = {path.resolve() for path in written_dirs}
    pruned: list[str] = []
    for child in sorted(iter_source_units(object_dir), key=lambda path: path.name):
        if child.resolve() in keep:
            continue
        try:
            meta = read_json(child / "meta.json")
        except (OSError, ValueError, TypeError):
            meta = {}
        if not _source_unit_lane_in_scope(str(meta.get("researchLane") or ""), selected_lanes):
            continue
        shutil.rmtree(child)
        pruned.append(child.name)
    return pruned

def _describe_rejection_reason(quality: Mapping[str, Any]) -> str:
    """把质量门裁决翻译成人可读的「为什么被拒」一句话，便于人工复查。"""
    fetched = bool(quality.get("fetchSucceeded"))
    status = int(quality.get("statusCode") or 0)
    score = int(quality.get("score") or 0)
    reasons = [str(r) for r in (quality.get("reasons") or []) if r]
    if not fetched:
        if status == 0:
            return "抓取失败：站点反爬 / 超时 / 无响应，未取到正文（statusCode=0），并非内容质量问题"
        return f"抓取失败：HTTP {status}，未取到可用正文"
    positive = {"length_ok", "detail_rich", "multi_paragraph", "scene_rich", "fact_dense", "entity_grounded"}
    noise = {"platform_visible", "meta_visible", "url_visible"}
    has_positive = any(r in positive for r in reasons)
    has_noise = any(r in noise for r in reasons)
    if has_positive and has_noise:
        return (
            f"正文已抓到且内容达标（{'、'.join(r for r in reasons if r in positive)}），"
            f"但因页眉页脚/导航/外链等噪声（{'、'.join(r for r in reasons if r in noise)}）惩罚后评分 {score} 跌入 Reject，"
            "建议加强 source.clean.md 清洗或放宽噪声惩罚后再评估"
        )
    if reasons:
        return f"质量门评分 {score} 判为 Reject；命中信号：{'、'.join(reasons)}"
    return f"质量门评分 {score} 判为 Reject（正文过短或与实体相关性不足）"

def _move_rejected_source_unit(
    object_dir: Path,
    unit_dir: Path,
    *,
    quality: Mapping[str, Any] | None = None,
) -> Path:
    """Keep rejected fetches for audit, outside the consumable source bundle.

    把人可读的「被拒原因」写进 meta.json 的 ``rejection`` 字段，避免人工复查时
    打开 rejected_sources/<unit>/meta.json 看不到为什么被拒。
    """

    rejected_root = object_dir / "1.download" / "rejected_sources"
    rejected_root.mkdir(parents=True, exist_ok=True)
    dest = rejected_root / unit_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(unit_dir), str(dest))
    if quality is not None:
        meta_path = dest / "meta.json"
        try:
            meta = read_json(meta_path) if meta_path.is_file() else {}
        except (OSError, ValueError, TypeError):
            meta = {}
        if isinstance(meta, dict):
            meta["rejection"] = {
                "decision": "reject",
                "reason": _describe_rejection_reason(quality),
                "quality": quality.get("quality"),
                "score": quality.get("score"),
                "fetchSucceeded": bool(quality.get("fetchSucceeded")),
                "statusCode": quality.get("statusCode"),
                "qualityReasons": [str(r) for r in (quality.get("reasons") or []) if r],
            }
            write_json(meta_path, meta)
    return dest

def _prune_stale_rejected_source_units(
    object_dir: Path,
    written_dirs: set[Path],
    *,
    selected_lanes: set[str] | None = None,
) -> list[str]:
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
        try:
            meta = read_json(child / "meta.json")
        except (OSError, ValueError, TypeError):
            meta = {}
        if not _source_unit_lane_in_scope(str(meta.get("researchLane") or ""), selected_lanes):
            continue
        if _preserve_rejected_source_memory(child, meta):
            continue
        shutil.rmtree(child)
        pruned.append(child.name)
    return pruned

def _preserve_rejected_source_memory(unit_dir: Path, meta: dict[str, object]) -> bool:
    """Keep high-value homepage rejects so planning does not loop on them.

    Rejected units are outside the consumable source bundle, so retaining a
    failed encyclopedia URL cannot pollute downstream evidence. It does,
    however, give source planning a stable memory that a Baidu/Sogou homepage
    URL has already failed fetch/screen gates, even after later scoped repair
    runs prune current sources.
    """
    if str(meta.get("researchLane") or "") != "homepage":
        return False
    source_text = " ".join(
        str(meta.get(field) or "")
        for field in ("sourceKind", "category", "platform", "sourceId", "url")
    )
    if not any(token in source_text for token in ("百科", "baike", "wikipedia", "维基")):
        return False
    quality_path = unit_dir / "source.quality.json"
    try:
        quality = read_json(quality_path) if quality_path.is_file() else {}
    except (OSError, ValueError, TypeError):
        quality = {}
    if str(quality.get("quality") or "") == "Reject":
        return True
    if not bool(quality.get("fetchSucceeded")) and int(quality.get("statusCode") or 0) == 0:
        return True
    return False

def build_inline_image_candidates(
    inline_images: Sequence[Mapping[str, Any]] | None,
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    """RC3：把 fetch 抽出的同源内联 <img> 清单映射成来源单元图片候选规格。

    每项携带 placeholderId（用于 write_source_unit 把 source.md 占位绑定到真实
    sourceAssetId）、url、caption、relevance；许可/出处等字段不在此伪造，统一由
    `_download_source_unit_images` 从来源 spec 继承，再走 权利→抓取→像素→安全→相关性
    五道硬门（同源不绕许可：来源无可发布许可的内联图会被权利门如实丢弃）。
    """
    candidates: list[dict[str, Any]] = []
    for row in inline_images or []:
        if not isinstance(row, Mapping):
            continue
        src = str(row.get("src") or "").strip()
        placeholder_id = str(row.get("placeholderId") or "").strip()
        if not src or not placeholder_id:
            continue
        caption = str(row.get("caption") or "").strip()
        candidates.append(
            {
                "url": src,
                "placeholderId": placeholder_id,
                "caption": caption,
                # 同源内联图相关性以真实 alt/caption 表达；为空则交由相关性门判定，
                # 不用实体名拼接伪造相关性。
                "relevance": caption,
            }
        )
    _ = entity_id  # 保留签名以便后续按实体调相关性默认（当前不伪造）。
    return candidates


def _download_source_unit_images(
    source: Mapping[str, Any],
    *,
    task_id: str,
    batch_id: str,
    entity_id: str,
    object_dir: Path,
    ordinal: int,
    vertical: str,
    extra_candidates: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Download and gate images that belong to the same text source unit.

    Article/homepage source images are part of that source's draft evidence.
    They must stay attached to the source unit instead of being mixed into the
    independent image-work collection lane.

    下载该来源 imageUrls 中所有与底稿相符、且通过 权利→抓取→像素→安全→相关性 五道门、
    再经感知去重的真实图（广告/图标/占位/视频在这些门里被排除），而不是只留 1 张。
    返回 (images, issues, funnel)：funnel 记录候选数、保留数、按原因聚合的丢弃明细与去重数，
    用于写入 assets/index.json 做候选/丢弃可审计。
    """
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    drops: list[dict[str, str]] = []

    def _funnel(candidate_count: int, dedupe_removed: int) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        for drop in drops:
            key = str(drop.get("reason") or "unknown").split(":", 1)[0]
            reason_counts[key] = reason_counts.get(key, 0) + 1
        return {
            "candidateCount": candidate_count,
            "keptCount": len(images),
            "droppedCount": len(drops),
            "dedupeRemoved": dedupe_removed,
            # 组感知配额：散图按源级上限；宫格/表格行图成组保完整（只受总保险丝）。
            "maxKeptPerSource": SOURCE_UNIT_MAX_IMAGES_PER_SOURCE,
            "quotaMode": "group_aware",
            "dropReasonCounts": reason_counts,
            "drops": drops,
        }

    raw_images = source.get("imageUrls") or []
    if not isinstance(raw_images, list):
        msg = f"{source.get('source_id') or '?'} imageUrls must be a list"
        return images, [msg], _funnel(0, 0)
    # RC3：同源内联 <img> 候选与计划 imageUrls 合并，走同一套五道硬门（不绕许可），
    # 经 placeholderId 把通过门的内联图回连 source.md 段落占位。
    all_candidates = list(raw_images) + list(extra_candidates or [])
    source_id = str(source.get("source_id") or "")
    candidate_count = len(all_candidates)
    # 组感知配额：宫格/表格行图（groupId 非空）成组保完整，不占散图配额，
    # 只受总保险丝约束；散图仍按源级上限截断（修复图库整组被硬截断丢图）。
    loose_kept = 0
    total_ceiling = max(SOURCE_UNIT_MAX_IMAGES_PER_SOURCE * 6, 48)
    for idx_img, raw in enumerate(all_candidates, start=1):
        candidate_group = str(raw.get("groupId") or "") if isinstance(raw, Mapping) else ""
        if len(images) >= total_ceiling:
            drops.append({"slug": f"{source_id}#{idx_img}", "reason": "capReached: 已达单源总保险丝"})
            continue
        if not candidate_group and loose_kept >= SOURCE_UNIT_MAX_IMAGES_PER_SOURCE:
            drops.append({"slug": f"{source_id}#{idx_img}", "reason": "capReached: 已达单源散图保留上限"})
            continue
        if not isinstance(raw, Mapping):
            issues.append(f"{source_id} image[{idx_img}] invalid payload")
            drops.append({"slug": f"{source_id}#{idx_img}", "reason": "invalidPayload"})
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
        spec_url = str(spec.get("url") or "")
        rights_issues = validate_image_rights(spec, vertical=vertical)
        if rights_issues:
            issues.extend(f"{label}: {issue}" for issue in rights_issues)
            drops.append({"slug": label, "url": spec_url, "reason": f"rights: {rights_issues[0]}"})
            continue
        payload = _cached_source_image_payload(
            object_dir,
            ordinal=ordinal,
            source_id=source_id,
            spec=spec,
        )
        if payload is None:
            payload = handler_bridge.call(
                "fetch_image_payload",
                fetch_image_payload,
                str(spec.get("url") or ""),
                max_bytes=SOURCE_UNIT_MAX_IMAGE_BYTES,
            )
        if payload is None:
            size_note = (
                f"/too large >{SOURCE_UNIT_MAX_IMAGE_BYTES} bytes"
                if SOURCE_UNIT_MAX_IMAGE_BYTES
                else ""
            )
            issues.append(f"{label}: imageFetch failed/non-image/too small{size_note} ({spec.get('url')})")
            drops.append({"slug": label, "url": spec_url, "reason": "fetch: 抓取失败/非图片/视频/过小或过大"})
            continue
        dims = image_dimensions(payload["bytes"]) or (0, 0)
        width, height = dims
        px_issue = pixel_size_issue(width, height, asset_id=label)
        if px_issue:
            issues.append(px_issue)
            drops.append({"slug": label, "url": spec_url, "reason": f"pixel: {px_issue}"})
            continue
        temp_file = _write_image_check_temp_file(
            task_id,
            batch_id,
            subdir="tmp_source_unit_image_checks",
            payload=payload,
        )
        try:
            verdict = _assess_source_image(temp_file, spec, task_id=task_id, batch_id=batch_id)
        finally:
            _cleanup_image_check_temp_file(temp_file)
        if verdict.blocks_image_publish:
            issues.append(f"{label}: imageSafety blocked ({verdict.status}) reasons={list(verdict.reasons)}")
            drops.append({"slug": label, "url": spec_url, "reason": f"safety: {verdict.status} {list(verdict.reasons)}"})
            continue
        relevance = str(spec.get("relevance") or spec.get("caption") or "")
        rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=label)
        if rel_issue:
            issues.append(rel_issue)
            drops.append({"slug": label, "url": spec_url, "reason": f"relevance: {rel_issue}"})
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
                # RC3：内联同源图回连 source.md 段落占位（非内联候选为空字符串）。
                "placeholderId": str(spec.get("placeholderId") or ""),
                # 布局/封面候选语义透传（source.layout.json figure 同源；无结构源为默认值）。
                "placementType": str(spec.get("placementType") or ""),
                "groupId": candidate_group,
                "sectionSlug": str(spec.get("sectionSlug") or ""),
                "sourceOrder": int(spec.get("sourceOrder") or 0),
                "coverCandidateRank": int(spec.get("coverCandidateRank") or 0),
                "isMapLike": bool(spec.get("isMapLike")),
                "fileTitle": str(spec.get("fileTitle") or ""),
            }
        )
        if not candidate_group:
            loose_kept += 1
    images, duplicates = dedupe_image_payloads(images)
    if duplicates:
        issues.append(f"{source_id}: source image dedupe removed {len(duplicates)} near-duplicate image(s)")
    funnel = _funnel(candidate_count, len(duplicates))
    # 保留了真实图就不把丢弃明细当作阻断 issue 上抛（funnel 已留痕），否则把所有原因回传给调用方。
    if images:
        return images, [], funnel
    return images, issues, funnel

__all__ = [name for name in globals() if not name.startswith("__")]

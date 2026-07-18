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

from core.paths import ensure_execution_command_layout, execution_root
from core.io import read_json, write_json
from content.execution.runtime_state import write_execution_runtime_state, write_source_catalog
from content.post.article.evidence_text import clean_source_markdown, score_source_markdown
from governance.coverage.entity_extract import entity_ref as build_entity_ref, require_domain_etype
from core.source_catalog import (
    coverage_issues,
    platform_category,
    source_category_coverage,
    source_unit_category_issues,
    vertical_from_task_id,
)
from content.source.source_unit import (
    find_source_unit_raw_snapshot,
    iter_source_units,
    remove_object_source_ref,
    resolve_entity_object_dir,
    write_source_unit,
)
from core.image_rules import MIN_ENTITY_IMAGES, pixel_size_issue, relevance_issue
from core.image_safety import assess_image, assess_image_cached, dedupe_image_payloads
from core.image_variants import image_dimensions
from core.page_media import DownloadedPageAsset, PageImagePlacement, PageImagePlacementType
from content.execution.stage_reports import write_gate_report, write_stage_result
from content.source.gate import download_requirements, gate_download
from content.source.source_inputs import (
    curated_sources_for_entity,
    curated_images_for_entity,
    manual_body_note,
    source_plan_rights_issues,
    source_frontmatter,
)
from content.source.fetch_payload import fetch_source_payload
from content.source.fetch_images import fetch_image_payload, fetch_page_image_payload
from content.source.prepare import prepare_source_plan, prepare_source_screen
from governance.coverage.license import normalize_rights_payload, validate_image_rights

from content.source.handler_plan import SOURCE_UNIT_MAX_IMAGE_BYTES, _source_unit_lane_in_scope
from content.source.source_asset_identity import (
    source_screen_report_ref as _source_screen_report_ref,
    stable_source_image_collection_id,
)

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

def _image_safety_cache_dir(execution_id: str) -> Path:
    return execution_root(execution_id) / "_shared" / "image_safety_cache"

def _write_image_check_temp_file(
    execution_id: str,
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
    temp_dir = execution_root(execution_id) / "_shared" / subdir
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
    execution_id: str = "",
):
    try:
        cache_dir = _image_safety_cache_dir(execution_id) if execution_id else None
        return assess_image_cached(
            path,
            cache_dir=cache_dir,
            require_ocr=_source_image_requires_ocr(spec),
        )
    except TypeError:
        return assess_image(path)

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
    """Return existing visual source units for monotonic repair.

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
        if lane in {"image", "homepage_image", "video"}:
            out.add(child)
    return out

def _cached_image_lane_payload(object_dir: Path, spec: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reuse a previously retained image-lane asset before hitting the network.

    Visual works are written as image/homepage_image/video source units.
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
    """Remove source units that are no longer present in the current content.execution.planning.

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

    meta_path = unit_dir / "meta.json"
    try:
        source_meta = read_json(meta_path) if meta_path.is_file() else {}
    except (OSError, ValueError, TypeError):
        source_meta = {}
    source_unit_id = str(
        source_meta.get("sourceUnitId") if isinstance(source_meta, Mapping) else ""
    ).strip()
    source_ref = str(
        source_meta.get("sourceRef") if isinstance(source_meta, Mapping) else ""
    ).strip()
    remove_object_source_ref(
        object_dir,
        source_unit_id=source_unit_id,
        source_ref=source_ref,
    )
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


__all__ = [name for name in globals() if not name.startswith("__")]

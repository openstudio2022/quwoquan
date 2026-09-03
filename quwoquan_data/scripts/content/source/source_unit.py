"""来源单元 + 对象证据链统一读写（真相源：object-homepage-coverage-scaling/design.md）。

替代「对象级散落 images/ + 实体目录承载来源」的旧布局。每个来源是一个自包含、
稳定 ID、带类目与相关性说明的单元；实体/作品对象只保存 `1.download/source_refs.json`
软引用索引：

    sources/{sourceUnitId}/
        meta.json            # url/title/sourceKind/relevance（与对象相关性）
        source.md            # 原文
        source.clean.md      # 清洗正文
        page.html / page.raw.json  # 原始抓取快照（HTML 存 page.html，MediaWiki API JSON 存 page.raw.json）
        source.quality.json  # 来源质量
        assets/{NNN}_{slug}.{ext}   # 该来源自带图片
        assets/index.json    # 每图 sourceAssetId/fileName/url/sha256/license/relevance/variants

证据链：source -> source asset -> writing pack asset -> article asset:// ->
post assets/{assetId} -> manifest.sourceAssetRef（相对 batch 根）。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.io import read_json, write_json
from content.execution.runtime_contract import stage_execution_context
from core.image_variants import build_local_variants, image_dimensions
from core.paths import (
    STAGE_DOWNLOAD,
    execution_entity_object_dir,
    execution_root,
    execution_source_unit_dir,
    executions_root,
    relative_execution_ref,
    object_source_unit_dir,
)
from governance.coverage.entity_type_taxonomy import require_domain_etype, resolve_domain_etype

SOURCE_UNIT_MANIFEST = "meta.json"
SOURCE_UNIT_ASSET_INDEX = "assets/index.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_UNIT_RE = re.compile(r"^(\d{2})\.(.+)$")
OBJECT_SOURCE_REFS = "1.download/source_refs.json"


def slugify(value: str) -> str:
    """可读 slug：保留中文/字母数字，连续非法折叠为 _。"""
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", str(value or "")).strip("_")
    return s or "asset"


# RC3：source.md 内联图占位 :::figure 块（未绑定到真实资产的悬空占位需整块剥离）。
# 图注行可选：无原图注的占位块只有图行（禁止人为补注），剥离时同样整块移除。
_INLINE_FIGURE_BLOCK_RE = re.compile(
    r"\n?:::figure\n!\[[^\]]*\]\(asset://source-inline-\d+\)\n(?:(?!:::)[^\n]*\n)?:::\n?"
)


def bind_inline_source_placeholders(text: str, placeholder_to_asset: Mapping[str, str]) -> str:
    """把 source.md 内联占位 asset://source-inline-NNN 绑定到真实 sourceAssetId。

    成功就地同源下载的内联图：占位 → asset://{ordinal_kkk}（段落锚定位置不变，
    保留图文交错）。未成功下载的 source-inline 占位：删除其整个 :::figure 块，
    杜绝悬空占位（这是九寨沟"图片对不上/缺失"的直接表征）。
    """
    from core.figure_groups import prune_unbound_group_images

    bound = str(text or "")
    for placeholder, asset_id in placeholder_to_asset.items():
        placeholder = str(placeholder or "").strip()
        asset_id = str(asset_id or "").strip()
        if not placeholder or not asset_id:
            continue
        bound = bound.replace(f"asset://{placeholder}", f"asset://{asset_id}")
    # figuregroup（连续图组）：剔除组内未绑定图行 + 重算 count + 删空组（P2）。
    bound = prune_unbound_group_images(bound)
    # 单图内联块：未绑定的悬空 :::figure 占位整块剥离（RC3）。
    bound = _INLINE_FIGURE_BLOCK_RE.sub("\n", bound)
    return re.sub(r"\n{3,}", "\n\n", bound)


_SOURCE_RAW_SNAPSHOT_NAMES = ("page.raw.json", "page.html")


def source_unit_raw_snapshot_name(raw_format: str = "") -> str:
    """原始抓取快照文件名：MediaWiki API JSON 存 page.raw.json，其它（HTML）存 page.html。"""
    return "page.raw.json" if str(raw_format or "").strip() == "mediawiki_api_json" else "page.html"


def find_source_unit_raw_snapshot(unit: Path) -> Path | None:
    """返回来源单元已有的原始快照文件（兼容 page.raw.json 与 page.html）。"""
    for name in _SOURCE_RAW_SNAPSHOT_NAMES:
        candidate = unit / name
        if candidate.is_file():
            return candidate
    return None


def resolve_entity_object_dir(
    execution_id: str,
    ref_or_name: str,
    *,
    etype_hint: str = "",
) -> Path:
    """从 entityRef（/entity/{domain}/{type}/{name} 或 {domain}/{type}/{name}）
    或裸名 + etype_hint 解析实体对象目录（与 publish DataRoot 同构）。"""
    raw = str(ref_or_name or "").strip().strip("/")
    parts = [p for p in raw.split("/") if p]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        domain, etype, name = parts[0], parts[1], parts[-1]
    else:
        name = parts[-1] if parts else raw
        if etype_hint:
            domain, etype = require_domain_etype(etype_hint, context=f"entity object path for {name}")
        else:
            domain, etype = resolve_domain_etype(etype_hint)
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    _raise_if_scenic_location_type_conflict(execution_id, domain, etype, name, current=obj)
    return obj


def _raise_if_scenic_location_type_conflict(
    execution_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    current: Path,
) -> None:
    if domain != "地点" or etype not in {"景区", "打卡地"}:
        return
    sibling_type = "打卡地" if etype == "景区" else "景区"
    sibling = execution_entity_object_dir(execution_id, domain, sibling_type, name)
    if sibling == current or not sibling.exists():
        return
    markers = ("_entity.json", "page.md", "1.download")
    if not any((sibling / marker).exists() for marker in markers):
        return
    # 「same batch contains both」要求两类型目录都真实物化：读路径以默认/空
    # hint 解析出的 current 并不在磁盘上时，只是类型提示缺失（上游应做
    # canonical 校正），不构成漂移共存；否则 canonical 产物存在时任何空 hint
    # 读操作都会假阳性炸穿 audit/completion gate（WP5 舟山实测）。
    if not current.exists() or not any((current / marker).exists() for marker in markers):
        return
    raise ValueError(
        "entity type drift detected: same batch contains both "
        f"{domain}/{etype}/{name} and {domain}/{sibling_type}/{name}; "
        "must fail or explicitly correct, silent coexistence is forbidden"
    )


# ─── 写：来源单元 ──────────────────────────────────────────────────
def _execution_root_for_object_dir(object_dir: Path) -> Path | None:
    root = executions_root().resolve()
    path = object_dir.resolve()
    for parent in (path, *path.parents):
        try:
            if parent.parent.resolve() == root:
                return parent
        except OSError:
            continue
    return None


def _object_source_refs_path(object_dir: Path) -> Path:
    return object_dir / OBJECT_SOURCE_REFS


def _relative_ref_for_execution_root(target: Path, execution_root_path: Path) -> str:
    return os.path.relpath(Path(target).resolve(), Path(execution_root_path).resolve()).replace(os.sep, "/")


def _record_object_source_ref(
    object_dir: Path,
    *,
    execution_id: str = "",
    execution_root_path: Path | None = None,
    source_ref: str,
    meta_ref: str,
    manifest: Mapping[str, Any],
) -> None:
    path = _object_source_refs_path(object_dir)
    payload = read_json(path) if path.is_file() else {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("schema", "quwoquan_data.object_source_refs")
    try:
        if execution_id:
            payload["objectRef"] = relative_execution_ref(object_dir, execution_id)
        elif execution_root_path is not None:
            payload["objectRef"] = _relative_ref_for_execution_root(object_dir, execution_root_path)
        else:
            payload["objectRef"] = ""
    except Exception:  # noqa: BLE001
        payload["objectRef"] = ""
    rows = [row for row in (payload.get("sources") or []) if isinstance(row, dict)]
    row = {
        "sourceUnitId": str(manifest.get("sourceUnitId") or ""),
        "sourceRef": source_ref,
        "metaRef": meta_ref,
        "sourceId": str(manifest.get("sourceId") or ""),
        "sourceKind": str(manifest.get("sourceKind") or ""),
        "ordinal": int(manifest.get("ordinal") or 0),
        "researchLane": str(manifest.get("researchLane") or ""),
        "sourceUseMode": str(manifest.get("sourceUseMode") or ""),
        "publishMediaMode": str(manifest.get("publishMediaMode") or ""),
        "targetRefs": list((manifest.get("relevance") or {}).get("targetRefs") or []),
    }
    rows = [existing for existing in rows if str(existing.get("sourceRef") or "") != source_ref]
    rows.append(row)
    payload["sources"] = sorted(rows, key=lambda item: (int(item.get("ordinal") or 0), str(item.get("sourceRef") or "")))
    write_json(path, payload)


def remove_object_source_ref(
    object_dir: Path,
    *,
    source_unit_id: str = "",
    source_ref: str = "",
) -> int:
    """Remove a source-unit reference when that unit leaves the consumable bundle.

    Rejected fetches remain under the object-local audit directory, but they are
    no longer valid ``sources/**`` inputs. Keeping their former ref would let a
    later consumer follow a dangling path and mistake rejected evidence for an
    accepted source.
    """
    path = _object_source_refs_path(object_dir)
    if not path.is_file():
        return 0
    payload = read_json(path)
    if not isinstance(payload, dict):
        return 0
    normalized_unit_id = str(source_unit_id or "").strip()
    normalized_source_ref = str(source_ref or "").strip()

    def matches(row: Mapping[str, Any]) -> bool:
        if normalized_unit_id and str(row.get("sourceUnitId") or "").strip() == normalized_unit_id:
            return True
        if normalized_source_ref and str(row.get("sourceRef") or "").strip() == normalized_source_ref:
            return True
        return False

    rows = [row for row in (payload.get("sources") or []) if isinstance(row, dict)]
    retained = [row for row in rows if not matches(row)]
    removed = len(rows) - len(retained)
    if not removed:
        return 0
    payload["sources"] = retained
    write_json(path, payload)
    return removed




def _ext_from_name(name: str) -> str:
    suffix = Path(str(name).split("?")[0]).suffix.lower()
    return suffix if suffix in _IMAGE_EXTS else ""


# ─── 读：来源单元与候选图（含证据链相对引用）────────────────────────
def iter_source_units(object_dir: Path) -> list[Path]:
    refs_path = _object_source_refs_path(object_dir)
    if not refs_path.is_file():
        return []
    execution_dir = _execution_root_for_object_dir(object_dir)
    if execution_dir is None:
        return []
    payload = read_json(refs_path)
    if not isinstance(payload, Mapping):
        # agent 产物是外部输入：顶层写成数组/标量时视为无可回查来源单元，
        # 契约违规由 verify 证据链负责报 issue，读路径不得崩溃。
        return []
    units: list[Path] = []
    for row in payload.get("sources") or []:
        if not isinstance(row, Mapping):
            continue
        ref = str(row.get("sourceRef") or "").strip()
        if not ref:
            continue
        source_md = execution_dir / ref
        unit = source_md.parent
        if source_md.is_file() and (unit / SOURCE_UNIT_MANIFEST).is_file():
            units.append(unit)
    return sorted(set(units), key=lambda d: d.name)


def find_entity_object_dirs(
    execution_id: str,
    name: str,
    *,
    etype_hint: str = "",
) -> list[Path]:
    """按实体名在批次 entities/** 下定位对象目录（含 1.download 来源单元者）。

    新布局来源单元在对象目录下，post/quality 读取时无需 domain/type，
    用名字定位即可（同名跨类目极少；命中多个时全部返回，调用方合并）。
    """
    from core.paths import execution_root

    entities_root = execution_root(execution_id) / "entities"
    if not entities_root.is_dir():
        return []
    raw = str(name or "").strip().strip("/")
    parts = [p for p in raw.split("/") if p]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        return [resolve_entity_object_dir(execution_id, raw)]
    if etype_hint:
        return [resolve_entity_object_dir(execution_id, raw, etype_hint=etype_hint)]
    out: list[Path] = []
    for refs_path in entities_root.rglob("source_refs.json"):
        obj = refs_path.parent.parent
        if obj.name == raw:
            out.append(obj)
    unique = sorted(set(out))
    scenic_pairs = {
        path.relative_to(entities_root).parts[1]
        for path in unique
        if len(path.relative_to(entities_root).parts) >= 3
        and path.relative_to(entities_root).parts[0] == "地点"
        and path.relative_to(entities_root).parts[1] in {"景区", "打卡地"}
    }
    if len(scenic_pairs) > 1:
        rels = sorted(path.relative_to(execution_root(execution_id)).as_posix() for path in unique)
        raise ValueError(
            f"entity type drift detected for '{raw}': dual scenic-location trees coexist -> {rels}"
        )
    return unique


from content.source.source_unit_writer import write_source_unit


__all__ = [
    "SOURCE_UNIT_MANIFEST",
    "SOURCE_UNIT_ASSET_INDEX",
    "slugify",
    "resolve_entity_object_dir",
    "write_source_unit",
    "remove_object_source_ref",
    "iter_source_units",
    "find_entity_object_dirs",
]

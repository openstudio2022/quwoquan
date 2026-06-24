"""Entity-service introduction seed mapping for homepage triplets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _common.io import read_json

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_INTRODUCTION_KIND_BY_TITLE = (
    ("timeline", ("时间线", "大事记", "节点")),
    ("history", ("历史", "沿革", "背景")),
    ("keyFacts", ("核心信息", "基础信息", "关键事实", "实用信息")),
    ("relatedObjects", ("相关地点", "相关对象", "周边", "关联")),
    ("gallery", ("图片", "图集", "相册")),
    ("map", ("位置", "交通", "地图")),
)


def _safe_ref(domain: str, etype: str, name: str) -> str:
    return f"{domain}__{etype}__{name}".replace("/", "_")


def homepage_introduction_seed_from_triplet(entity_dir: Path) -> dict[str, Any]:
    """Map entity homepage triplets into an entity-service introduction seed."""
    page_path = entity_dir / "page.md"
    entity_path = entity_dir / "_entity.json"
    manifest_path = entity_dir / "manifest.json"
    if not page_path.is_file() or not entity_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"missing homepage triplet under {entity_dir}")
    page_text = page_path.read_text(encoding="utf-8")
    entity_payload = read_json(entity_path)
    manifest_payload = read_json(manifest_path)
    label = str(entity_payload.get("label") or entity_payload.get("name") or entity_dir.name).strip()
    domain = str(entity_payload.get("domain") or "").strip()
    etype = str(entity_payload.get("type") or entity_payload.get("etype") or "").strip()
    homepage_id = str(
        entity_payload.get("homepageId")
        or manifest_payload.get("homepageId")
        or entity_payload.get("id")
        or _safe_ref(domain or "entity", etype or "object", label or entity_dir.name),
    ).strip()
    sections = _introduction_sections_from_markdown(page_text, manifest_payload)
    source_refs = _introduction_source_refs(entity_payload, manifest_payload, entity_dir)
    return {
        "homepageId": homepage_id,
        "displayName": label,
        "homepageType": etype,
        "coverUrl": _manifest_cover_url(manifest_payload),
        "summary": _introduction_summary(page_text, label),
        "sections": sections,
        "relatedObjects": _introduction_related_objects(entity_payload, manifest_payload),
        "sourceRefs": source_refs,
        "updatedAt": str(manifest_payload.get("updatedAt") or manifest_payload.get("generatedAt") or ""),
        "seedSource": {
            "pageMd": str(page_path),
            "entityJson": str(entity_path),
            "manifestJson": str(manifest_path),
        },
    }


def _introduction_sections_from_markdown(page_text: str, manifest_payload: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(page_text))
    if not matches:
        body = page_text.strip()
        if body:
            chunks.append(("概况", body))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_text)
        title = match.group(2).strip()
        body = page_text[start:end].strip()
        if title and body:
            chunks.append((title, body))
    if not chunks and page_text.strip():
        chunks.append(("概况", page_text.strip()))
    assets = _introduction_assets(manifest_payload)
    out: list[dict[str, Any]] = []
    for index, (title, body) in enumerate(chunks):
        kind = _section_kind_for_title(title, index)
        out.append(
            {
                "kind": kind,
                "title": title,
                "bodyMarkdown": body,
                "assets": assets if index == 0 else [],
                "timelineItems": _timeline_items_from_body(body) if kind == "timeline" else [],
            }
        )
    return out


def _section_kind_for_title(title: str, index: int) -> str:
    if index == 0:
        return "overview"
    for kind, tokens in _INTRODUCTION_KIND_BY_TITLE:
        if any(token in title for token in tokens):
            return kind
    return "overview"


def _timeline_items_from_body(body: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in body.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if not line:
            continue
        if "：" in line:
            date_label, text = line.split("：", 1)
        elif ":" in line:
            date_label, text = line.split(":", 1)
        else:
            continue
        items.append({"dateLabel": date_label.strip(), "text": text.strip()})
    return items


def _introduction_assets(manifest_payload: dict[str, Any]) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for raw in manifest_payload.get("assets") or []:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        url = str(raw.get("url") or raw.get("imageUrl") or raw.get("sourceUrl") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        if not url and file_name:
            url = f"asset://{asset_id or file_name}"
        if not asset_id or not url:
            continue
        assets.append(
            {
                "assetId": asset_id,
                "url": url,
                "caption": str(raw.get("caption") or raw.get("title") or "").strip(),
                "sourceRef": str(raw.get("sourceRef") or raw.get("license") or "").strip(),
            }
        )
    return assets


def _source_ref_from_asset_ref(source_asset_ref: str) -> str:
    normalized = str(source_asset_ref or "").replace("\\", "/").strip()
    if not normalized or "/assets/" not in normalized:
        return ""
    return normalized.split("/assets/", 1)[0].rstrip("/") + "/source.md"


def _normalize_homepage_manifest_assets(manifest_payload: dict[str, Any]) -> bool:
    assets = manifest_payload.get("assets")
    if not isinstance(assets, list):
        return False
    changed = False
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        source_ref = str(raw.get("sourceRef") or "").strip()
        source_asset_ref = str(raw.get("sourceAssetRef") or "").strip()
        if source_ref and "/assets/" in source_ref:
            if not source_asset_ref:
                raw["sourceAssetRef"] = source_ref
                source_asset_ref = source_ref
            raw["sourceRef"] = ""
            source_ref = ""
            changed = True
        if not source_ref and source_asset_ref:
            inferred = _source_ref_from_asset_ref(source_asset_ref)
            if inferred:
                raw["sourceRef"] = inferred
                changed = True
    return changed


def _manifest_cover_url(manifest_payload: dict[str, Any]) -> str:
    cover = str(manifest_payload.get("coverUrl") or "").strip()
    if cover:
        return cover
    assets = _introduction_assets(manifest_payload)
    return assets[0]["url"] if assets else ""


def _introduction_summary(page_text: str, fallback: str) -> str:
    lines = [
        line.strip()
        for line in page_text.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("asset://")
    ]
    if not lines:
        return f"{fallback} 的完整介绍正在整理中。"
    summary = lines[0]
    return summary[:180]


def _introduction_related_objects(entity_payload: dict[str, Any], manifest_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = entity_payload.get("relatedObjects") or manifest_payload.get("relatedObjects") or []
    return [item for item in raw_items if isinstance(item, dict)]


def _introduction_source_refs(entity_payload: dict[str, Any], manifest_payload: dict[str, Any], entity_dir: Path) -> list[str]:
    refs: list[str] = []
    for raw in entity_payload.get("sourceRefs") or manifest_payload.get("sourceRefs") or []:
        value = str(raw).strip()
        if value:
            refs.append(value)
    for name in ("page.md", "_entity.json", "manifest.json"):
        refs.append(str(entity_dir / name))
    return sorted(set(refs))

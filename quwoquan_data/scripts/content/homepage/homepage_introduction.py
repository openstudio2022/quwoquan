"""Entity-service introduction seed mapping for homepage triplets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.io import read_json

_ASSET_REF_LINE_RE = re.compile(r"^asset://(\S+)\s*$", re.MULTILINE)
_GALLERY_IDS_ATTR_RE = re.compile(r'^:::gallery\b[^\n]*\bids="([^"]*)"', re.MULTILINE)
_RELATED_IMAGES_HEADING = "相关图片"
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
    return {
        "homepageId": homepage_id,
        "displayName": label,
        "homepageType": etype,
        "coverUrl": _manifest_cover_url(manifest_payload),
        "summary": _introduction_summary(page_text, label),
        "sections": sections,
        "relatedObjects": _introduction_related_objects(entity_payload, manifest_payload),
        "primarySource": entity_payload.get("primarySource"),
        "sourceUrls": entity_payload.get("sourceUrls") or [],
        "updatedAt": str(manifest_payload.get("updatedAt") or manifest_payload.get("generatedAt") or ""),
        "seedSource": {
            "pageMd": str(page_path),
            "entityJson": str(entity_path),
            "manifestJson": str(manifest_path),
        },
    }


def _introduction_sections_from_markdown(page_text: str, manifest_payload: dict[str, Any]) -> list[dict[str, Any]]:
    _frontmatter, body = _split_frontmatter(page_text)
    lead, chapters = _split_chapters(body)
    assets = _introduction_assets(manifest_payload)
    asset_by_id = {asset["assetId"]: asset for asset in assets}
    out: list[dict[str, Any]] = []
    if lead:
        out.append(
            {
                "kind": "overview",
                "title": "概况",
                "bodyMarkdown": lead,
                "assets": _section_assets(lead, asset_by_id, role="inline"),
                "timelineItems": [],
            }
        )
    for index, (title, chapter_body) in enumerate(chapters, start=1):
        if title == _RELATED_IMAGES_HEADING:
            related = _section_assets(chapter_body, asset_by_id, role="related")
            if related:
                out.append(
                    {
                        "kind": "relatedImages",
                        "title": _RELATED_IMAGES_HEADING,
                        "bodyMarkdown": "",
                        "assets": related,
                        "timelineItems": [],
                    }
                )
            continue
        kind = _section_kind_for_title(title, index)
        out.append(
            {
                "kind": kind,
                "title": title,
                "bodyMarkdown": chapter_body.strip(),
                "assets": _section_assets(chapter_body, asset_by_id, role="inline"),
                "timelineItems": _timeline_items_from_body(chapter_body) if kind == "timeline" else [],
            }
        )
    return out


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    cut = end + len("\n---\n")
    return text[:cut], text[cut:]


def _split_chapters(body: str) -> tuple[str, list[tuple[str, str]]]:
    lead_lines: list[str] = []
    chapters: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("## "):
            chapters.append((trimmed[3:].strip(), []))
        elif chapters:
            chapters[-1][1].append(line)
        elif not trimmed.startswith("# "):
            lead_lines.append(line)
    return (
        "\n".join(lead_lines).strip(),
        [(title, "\n".join(lines).strip()) for title, lines in chapters],
    )


def _section_assets(
    section_body: str,
    asset_by_id: dict[str, dict[str, str]],
    *,
    role: str,
) -> list[dict[str, str]]:
    ordered: list[tuple[int, list[str]]] = []
    ordered.extend((match.start(), [match.group(1)]) for match in _ASSET_REF_LINE_RE.finditer(section_body))
    ordered.extend(
        (match.start(), match.group(1).split(","))
        for match in _GALLERY_IDS_ATTR_RE.finditer(section_body)
    )
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _position, refs in sorted(ordered, key=lambda item: item[0]):
        for raw_ref in refs:
            asset_id = raw_ref.strip()
            asset = asset_by_id.get(asset_id)
            if not asset or asset_id in seen or asset.get("role") == "cover":
                continue
            seen.add(asset_id)
            out.append({**asset, "role": role})
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
                "role": str(raw.get("role") or "related").strip(),
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
    for asset in assets:
        if asset.get("role") == "cover":
            return asset["url"]
    return ""


def _introduction_summary(page_text: str, fallback: str) -> str:
    _frontmatter, body = _split_frontmatter(page_text)
    lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip()
        and not line.strip().startswith(("#", "asset://", ":::"))
    ]
    if not lines:
        return f"{fallback} 的完整介绍正在整理中。"
    summary = lines[0]
    return summary[:180]


def _introduction_related_objects(
    entity_payload: dict[str, Any],
    manifest_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_items = entity_payload.get("relatedObjects") or manifest_payload.get("relatedObjects") or []
    return [item for item in raw_items if isinstance(item, dict)]


__all__ = ["homepage_introduction_seed_from_triplet"]

"""发布门：账本发布态 + 实体主页存在性，对单个 post 做过滤裁决。

- 文章不可发布 / 仍有 fix 项 → 整 post 跳过（不静默 BLOCK 全量）。
- discard 图片 → 从 manifest.assets / article.md 引用一并剔除。
- entityRefs 中"无主页"的实体 → 过滤掉（页面不存在即不可关联查看）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from _common.io import read_json, write_json
from _common.review_ledger import (
    ReviewLedger,
    STATE_DISCARD,
    post_publishability,
)


def _parse_entity_ref(raw: str) -> tuple[str, str, str]:
    parts = (raw or "").strip().strip("/").split("/")
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        return parts[0], parts[1], "/".join(parts[2:])
    return "", "", raw


def entity_homepage_exists(homepage_root: Path, ref: str, sidecar_homepages: set[str]) -> bool:
    if ref in sidecar_homepages:
        return True
    domain, etype, name = _parse_entity_ref(ref)
    if not (domain and etype and name):
        return False
    return (homepage_root / domain / etype / name / "page.md").is_file()


def _normalized_runtime_entity_ref(ref: str) -> str:
    domain, etype, name = _parse_entity_ref(ref)
    if not (domain and etype and name):
        return ""
    etype_slug = etype.strip().replace(" ", "_")
    name_slug = name.strip().replace(" ", "_")
    if not etype_slug or not name_slug:
        return ""
    return f"entity:{etype_slug}:{name_slug}"


def _normalized_runtime_entity_refs(entity_refs: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for ref in entity_refs:
        normalized = _normalized_runtime_entity_ref(ref)
        if not normalized or normalized in seen:
            continue
        out.append(normalized)
        seen.add(normalized)
    return out


def _sync_publish_ref_projections(manifest: dict[str, Any]) -> None:
    normalized = _normalized_runtime_entity_refs([str(ref) for ref in manifest.get("entityRefs") or []])
    if "normalizedEntityRefs" in manifest:
        manifest["normalizedEntityRefs"] = normalized
    allowed = set(normalized)
    hints = manifest.get("intersectionHints")
    if isinstance(hints, list):
        kept_hints: list[Any] = []
        for hint in hints:
            if not isinstance(hint, dict):
                kept_hints.append(hint)
                continue
            if str(hint.get("source") or "") == "entityRef" and str(hint.get("actionTargetId") or "") not in allowed:
                continue
            kept_hints.append(hint)
        manifest["intersectionHints"] = kept_hints
    if manifest.get("semanticMentions") == []:
        manifest.pop("semanticMentions", None)


@dataclass
class PublishFilterVerdict:
    publishable: bool
    reasons: list[str]
    manifest: dict[str, Any]
    article_md: str
    filtered_entities: list[str] = field(default_factory=list)
    discarded_assets: list[str] = field(default_factory=list)
    asset_filenames_to_remove: list[str] = field(default_factory=list)

    def write_into(self, dst: Path) -> None:
        """把过滤后的 manifest / article.md 写入已复制好的发布目录，并删除 discard 图片文件。"""
        write_json(dst / "manifest.json", self.manifest)
        if self.article_md:
            (dst / "article.md").write_text(self.article_md, encoding="utf-8")
        for fname in self.asset_filenames_to_remove:
            f = dst / "assets" / fname
            if f.is_file():
                f.unlink()


def _strip_asset_from_markdown(article_md: str, asset_ids: set[str]) -> str:
    if not asset_ids or not article_md:
        return article_md
    lines = article_md.splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        if any(aid in line and "asset://" in line for aid in asset_ids):
            continue
        kept.append(line)
    text = "".join(kept)
    # 清理可能残留的空 :::figure 块
    text = re.sub(r"(?ms)^:::figure\s*\n(?:\s*\n)*:::\s*\n?", "", text)
    return text


def apply_publish_filter(
    topic_dir: Path,
    publish_root: Path,
    *,
    entity_homepage_root: Path | None = None,
) -> PublishFilterVerdict:
    manifest = read_json(topic_dir / "manifest.json")
    article_path = topic_dir / "article.md"
    article_md = article_path.read_text(encoding="utf-8") if article_path.is_file() else ""

    # 账本/实体边车在内容对象 5.review/（对象优先）。
    ledger_file = topic_dir / "5.review" / "review_ledger.json"
    entities_file = topic_dir / "5.review" / "review_entities.json"

    reasons: list[str] = []
    discard_targets: list[str] = []
    publishable = True

    if ledger_file.is_file():
        ledger = ReviewLedger.from_dict(read_json(ledger_file))
        publishable, reasons, discard_targets = post_publishability(ledger)

    # 实体主页存在性：sidecar hasHomepage + publish 主线 page.md / release entity_pages.
    sidecar_homepages: set[str] = set()
    if entities_file.is_file():
        for ent in read_json(entities_file).get("entities", []):
            if ent.get("hasHomepage") and ent.get("ref"):
                sidecar_homepages.add(ent["ref"])
    homepage_root = entity_homepage_root or (publish_root / "entities")

    filtered_entities: list[str] = []
    kept_refs: list[str] = []
    for ref in manifest.get("entityRefs", []):
        if entity_homepage_exists(homepage_root, ref, sidecar_homepages):
            kept_refs.append(ref)
        else:
            filtered_entities.append(ref)
    manifest["entityRefs"] = kept_refs
    _sync_publish_ref_projections(manifest)

    # discard 图片：从顶层 assets 剔除并记录文件名
    discard_set = set(discard_targets)
    fnames_to_remove: list[str] = []
    if discard_set:
        new_assets = []
        for a in manifest.get("assets", []):
            if a.get("assetId") in discard_set:
                if a.get("fileName"):
                    fnames_to_remove.append(a["fileName"])
                continue
            new_assets.append(a)
        manifest["assets"] = new_assets

        article_md = _strip_asset_from_markdown(article_md, discard_set)

    return PublishFilterVerdict(
        publishable=publishable,
        reasons=reasons,
        manifest=manifest,
        article_md=article_md,
        filtered_entities=filtered_entities,
        discarded_assets=list(discard_set),
        asset_filenames_to_remove=fnames_to_remove,
    )

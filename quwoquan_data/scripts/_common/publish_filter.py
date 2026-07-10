"""发布门：账本发布态 + 实体主页存在性，对单个 post 做过滤裁决。

- 文章不可发布 / 仍有 fix 项 → 整 post 跳过（不静默 BLOCK 全量）。
- discard 图片 → 从 manifest.assets / article.md 引用一并剔除。
- entityRefs 中"无主页"的实体 → 过滤掉（页面不存在即不可关联查看）。
"""
from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from _common.article_package import compute_asset_manifest_sha256, compute_document_sha256
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


def entity_homepage_exists(homepage_root: Path, ref: str, sidecar_homepages: set[str] | None = None) -> bool:
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


def _normalized_entity_link_ref(ref: str) -> str:
    domain, etype, name = _parse_entity_ref(ref)
    if not (domain and etype and name):
        return ""
    return f"/entity/{domain}/{etype}/{name}"


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


def _pending_entity_candidate_id(ref: str) -> str:
    digest = hashlib.sha256(str(ref or "").encode("utf-8")).hexdigest()[:16]
    return f"entity_candidate_{digest}"


def _pending_entity_mentions(refs: list[str], article_md: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep site-supply entity gaps auditable without projecting active entity refs."""
    topic_id = str(manifest.get("topicId") or manifest.get("ref") or "").strip()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        domain, etype, name = _parse_entity_ref(ref)
        surface = name.strip()
        if not surface or ref in seen:
            continue
        seen.add(ref)
        start = article_md.find(surface) if article_md else -1
        row: dict[str, Any] = {
            "candidateId": _pending_entity_candidate_id(ref),
            "kind": "entity",
            "status": "pending_review",
            "surface": surface,
            "sourceEntityRef": ref,
            "source": "publish_filter.filtered_entity_without_homepage",
        }
        if topic_id:
            row["sourceRef"] = topic_id
        if domain or etype:
            row["entityType"] = "/".join(part for part in (domain, etype) if part)
        if start >= 0:
            row["location"] = "body"
            row["rangeStart"] = start
            row["rangeEnd"] = start + len(surface)
        else:
            row["location"] = "manifest"
        rows.append(row)
    return rows


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
        _sync_release_final_provenance(dst, self.manifest, self.article_md)
        write_json(dst / "manifest.json", self.manifest)
        if self.article_md:
            (dst / "article.md").write_text(self.article_md, encoding="utf-8")
        for fname in self.asset_filenames_to_remove:
            f = dst / "assets" / fname
            if f.is_file():
                f.unlink()


def _sync_release_final_provenance(topic_dir: Path, manifest: dict[str, Any], article_md: str) -> None:
    """发布过滤会改正文/资产，release 面 provenance 必须指向过滤后的最终交付物。"""
    review_dir = topic_dir / "5.review"
    provenance_path = review_dir / "provenance.json"
    is_image = str(manifest.get("contentType") or "") == "image" or str(
        manifest.get("carrier") or ""
    ) in ("image", "gallery")
    final_digest = (
        compute_asset_manifest_sha256(list(manifest.get("assets") or []))
        if is_image
        else compute_document_sha256(str(article_md or ""))
    )
    if is_image:
        manifest.pop("articleMarkdownDigest", None)
        manifest.pop("documentSha256", None)
    else:
        manifest["articleMarkdownDigest"] = final_digest
        manifest["documentSha256"] = final_digest
    if not provenance_path.is_file():
        return
    data = read_json(provenance_path)
    if not isinstance(data, dict):
        return
    final = data.get("final")
    if not isinstance(final, dict):
        final = {}
        data["final"] = final
    if is_image:
        final["assetDigest"] = final_digest
    else:
        final["articleDigest"] = final_digest
    write_json(provenance_path, data)


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


def _strip_filtered_entity_links(article_md: str, entity_refs: set[str]) -> str:
    if not article_md or not entity_refs or "/entity/" not in article_md:
        return article_md
    normalized = {_normalized_entity_link_ref(ref) for ref in entity_refs if _normalized_entity_link_ref(ref)}
    if not normalized:
        return article_md
    pattern = re.compile(r"\[([^\]\n]+)\]\((/entity/[^)\s]+)\)")

    def replace(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2)
        if _normalized_entity_link_ref(href) in normalized:
            return label
        return match.group(0)

    return pattern.sub(replace, article_md)


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

    # 实体主页存在性必须以发布面 page.md 为准；review sidecar 只作审计输入，
    # 不能让 release 产生悬挂主页链接。
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
    if filtered_entities:
        article_md = _strip_filtered_entity_links(article_md, set(filtered_entities))
        existing_pending = [
            item for item in (manifest.get("pendingEntityMentions") or [])
            if isinstance(item, dict)
        ]
        existing_keys = {
            str(item.get("sourceEntityRef") or item.get("candidateId") or "")
            for item in existing_pending
        }
        for item in _pending_entity_mentions(filtered_entities, article_md, manifest):
            key = str(item.get("sourceEntityRef") or item.get("candidateId") or "")
            if key and key in existing_keys:
                continue
            existing_pending.append(item)
            existing_keys.add(key)
        manifest["pendingEntityMentions"] = existing_pending
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

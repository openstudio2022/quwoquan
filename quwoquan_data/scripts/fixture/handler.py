"""qwq-data fixture — 把 publish 真实实体转换为 App contract fixture。

`fixture entity-introduction` 消费 publish/entities 的 page.md 三件套
（_entity.json / page.md / manifest.json），按与 entity-service
`buildIntroductionFromPageMarkdown`（homepage_introduction.go）同构的三段结构
投影生成 `entity_scenarios.json` 的 introduction fixture 节，替换手工
unsplash 占位，让 alpha mock 与 beta/gamma 真实通道共享同一份真实主页语料。

投影同构契约（与服务侧逐点对齐，任何一侧变更必须同步另一侧 + 测试）：
- frontmatter `coverImage: asset://<id>` → coverUrl；
- 首个 `## ` 前导语（剥 H1）→ kind=overview「概况」；
- `## X` 章节 → kind=body（bodyMarkdown 保留 :::figure 指令，asset:// 行绑定 inline 资产）；
- `## 相关图片` → kind=relatedImages（`:::gallery ids="a,b"` 属性绑定 related 资产，指令不下发）；
- 资产 URL：objectKey + media base 优先，其次 manifest cdnUrl；未物化资产记 issue。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from _common.io import read_json, write_json
from _common.paths import PUBLISH_ROOT, REPO_ROOT

DEFAULT_SCENARIOS_PATH = (
    REPO_ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "entity"
    / "test_fixtures"
    / "scenarios"
    / "entity_scenarios.json"
)

# 与 entity-service cmd/homepage-import/loader.go 的映射同源。
ENTITY_TYPE_TO_HOMEPAGE_TYPE = {
    "景区": "sight",
    "机位": "travel_photo",
    "住宿": "hotel",
    "餐饮": "restaurant",
    "学校": "university",
}
ASSET_ROLE_TO_INTRODUCTION_ROLE = {
    "cover": "cover",
    "detail": "inline",
    "node": "inline",
    "closing": "related",
    "related": "related",
}

RELATED_IMAGES_HEADING = "相关图片"

_ASSET_REF_LINE_RE = re.compile(r"^asset://(\S+)\s*$", re.M)
_GALLERY_IDS_ATTR_RE = re.compile(r'^:::gallery\b[^\n]*\bids="([^"]*)"', re.M)
_SEED_SET = "entity_homepage_core"


def canonical_slug(value: str) -> str:
    """与 entity-service homepage_lookup.go canonicalSlug 同构。"""
    out: list[str] = []
    last_underscore = False
    for ch in value.strip():
        if ch.isalnum():
            out.append(ch.lower())
            last_underscore = False
        elif ch == "_" or ch.isspace() or ch in "-/":
            if not last_underscore:
                out.append("_")
                last_underscore = True
    return "".join(out).strip("_")


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end < 0:
        return "", text
    cut = end + len("\n---\n")
    return text[:cut], text[cut:]


def _frontmatter_cover_asset_id(frontmatter: str) -> str:
    for line in frontmatter.splitlines():
        trimmed = line.strip()
        if not trimmed.startswith("coverImage:"):
            continue
        value = trimmed[len("coverImage:"):].strip().strip("\"'")
        return value.removeprefix("asset://")
    return ""


def _split_chapters(body: str) -> tuple[str, list[tuple[str, str]]]:
    lead_lines: list[str] = []
    chapters: list[tuple[str, list[str]]] = []
    for line in body.split("\n"):
        trimmed = line.strip()
        if trimmed.startswith("## "):
            chapters.append((trimmed[3:].strip(), []))
            continue
        if chapters:
            chapters[-1][1].append(line)
            continue
        if trimmed.startswith("# "):
            continue
        lead_lines.append(line)
    return (
        "\n".join(lead_lines).strip(),
        [(title, "\n".join(lines)) for title, lines in chapters],
    )


def _section_assets(
    section_body: str,
    asset_by_id: Mapping[str, dict[str, Any]],
    role: str,
) -> list[dict[str, Any]]:
    groups: list[tuple[int, list[str]]] = []
    for match in _ASSET_REF_LINE_RE.finditer(section_body):
        groups.append((match.start(), [match.group(1)]))
    for match in _GALLERY_IDS_ATTR_RE.finditer(section_body):
        groups.append((match.start(), match.group(1).split(",")))
    groups.sort(key=lambda item: item[0])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, ids in groups:
        for raw_id in ids:
            asset_id = raw_id.strip()
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            asset = asset_by_id.get(asset_id)
            if not asset or not str(asset.get("url") or "").strip():
                continue
            bound = dict(asset)
            bound["role"] = role
            out.append(bound)
    return out


def _first_paragraph_summary(lead: str) -> str:
    for paragraph in lead.split("\n\n"):
        text = paragraph.strip()
        if not text or text.startswith(":::") or text.startswith("asset://"):
            continue
        return text[:120]
    return ""


def _asset_url(asset: Mapping[str, Any], media_base_url: str) -> str:
    object_key = str(asset.get("objectKey") or "").strip()
    base = media_base_url.strip().rstrip("/")
    if base and object_key:
        return f"{base}/{object_key.lstrip('/')}"
    return str(asset.get("cdnUrl") or "").strip()


def project_entity_introduction(
    entity_dir: Path,
    entity_ref: str,
    *,
    media_base_url: str = "",
) -> tuple[dict[str, Any] | None, list[str]]:
    """把单个 publish 实体投影为 fixture homepage 条目；返回 (条目, issues)。"""
    issues: list[str] = []
    header = read_json(entity_dir / "_entity.json") if (entity_dir / "_entity.json").is_file() else {}
    page_path = entity_dir / "page.md"
    if not page_path.is_file():
        issues.append(f"{entity_ref}: page.md 缺失，无 introduction 可投影")
        return None, issues
    page = page_path.read_text(encoding="utf-8")
    manifest = read_json(entity_dir / "manifest.json") if (entity_dir / "manifest.json").is_file() else {}

    etype = str(header.get("type") or "").strip() or (entity_ref.split("/")[1] if entity_ref.count("/") >= 1 else "")
    homepage_type = ENTITY_TYPE_TO_HOMEPAGE_TYPE.get(etype)
    if not homepage_type:
        issues.append(f"{entity_ref}: 实体类型 {etype!r} 未登记主页类型映射，跳过")
        return None, issues
    title = str(header.get("label") or "").strip() or entity_ref.split("/")[-1]
    slug = canonical_slug(title)
    if not slug:
        issues.append(f"{entity_ref}: 标题无法生成 canonical slug，跳过")
        return None, issues

    asset_by_id: dict[str, dict[str, Any]] = {}
    for raw in manifest.get("assets") or []:
        if not isinstance(raw, Mapping):
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        if not asset_id:
            continue
        url = _asset_url(raw, media_base_url)
        if not url:
            issues.append(
                f"{entity_ref}: 资产 {asset_id} 无 objectKey/cdnUrl 可映射 URL（publish 树未 materialize？）"
            )
            continue
        role = ASSET_ROLE_TO_INTRODUCTION_ROLE.get(str(raw.get("role") or "").strip(), "related")
        asset_by_id[asset_id] = {
            "assetId": asset_id,
            "url": url,
            "caption": str(raw.get("caption") or "").strip(),
            "role": role,
            "sourceRef": str(raw.get("sourceRef") or "").strip(),
        }

    frontmatter, body = _split_frontmatter(page)
    cover_url = ""
    cover_asset_id = _frontmatter_cover_asset_id(frontmatter)
    if cover_asset_id and cover_asset_id in asset_by_id:
        cover_url = asset_by_id[cover_asset_id]["url"]
    if not cover_url:
        for asset in asset_by_id.values():
            if asset["role"] == "cover":
                cover_url = asset["url"]
                break

    lead, chapters = _split_chapters(body)
    sections: list[dict[str, Any]] = []
    if lead:
        sections.append(
            {
                "kind": "overview",
                "title": "概况",
                "bodyMarkdown": lead,
                "assets": _section_assets(lead, asset_by_id, "inline"),
            }
        )
    for chapter_title, chapter_body in chapters:
        if chapter_title == RELATED_IMAGES_HEADING:
            related_assets = _section_assets(chapter_body, asset_by_id, "related")
            if not related_assets:
                continue
            sections.append(
                {
                    "kind": "relatedImages",
                    "title": RELATED_IMAGES_HEADING,
                    "assets": related_assets,
                }
            )
            continue
        sections.append(
            {
                "kind": "body",
                "title": chapter_title,
                "bodyMarkdown": chapter_body.strip(),
                "assets": _section_assets(chapter_body, asset_by_id, "inline"),
            }
        )

    summary = _first_paragraph_summary(lead) or str(header.get("summary") or "").strip()[:120]
    homepage_id = f"homepage_{homepage_type}_{slug}"
    canonical_entity_id = f"entity:{homepage_type}:{slug}"
    entry = {
        "homepageId": homepage_id,
        "type": homepage_type,
        "canonicalEntityId": canonical_entity_id,
        "title": title,
        "summary": summary,
        "city": str(header.get("city") or "").strip(),
        "status": "published",
        "coverUrl": cover_url,
        "seedSource": {
            "channel": "qwq-data fixture entity-introduction",
            "entityRef": entity_ref,
            "sourceTaskId": str(header.get("sourceTaskId") or manifest.get("sourceTaskId") or "").strip(),
        },
        "introduction": {
            "homepageId": homepage_id,
            "displayName": title,
            "homepageType": homepage_type,
            "coverUrl": cover_url,
            "summary": summary,
            "sections": sections,
            "sourceRefs": [f"entity-service/homepage/{homepage_id}", canonical_entity_id],
        },
    }
    return entry, issues


# fixture 手工运营字段：已有条目更新 introduction 时保留，不被生成器覆盖。
_PRESERVED_KEYS = (
    "subtitle",
    "categoryTags",
    "verified",
    "establishedYear",
    "followerCount",
    "contentPreview",
    "questionPreview",
    "relatedCircleIds",
    "relatedGroups",
    "relatedPostIds",
    "ownerId",
    "geo",
    "createdAt",
    "publishedAt",
    "updatedAt",
)


def merge_into_scenarios(
    scenarios: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """把生成条目并入 seedSets.entity_homepage_core.homepages（按 homepageId 幂等 upsert）。"""
    seed_sets = scenarios.setdefault("seedSets", {})
    core = seed_sets.setdefault(_SEED_SET, {"description": "", "homepages": []})
    homepages: list[dict[str, Any]] = core.setdefault("homepages", [])
    by_id = {str(h.get("homepageId") or ""): i for i, h in enumerate(homepages) if isinstance(h, Mapping)}
    for entry in entries:
        idx = by_id.get(entry["homepageId"])
        if idx is None:
            homepages.append(entry)
            by_id[entry["homepageId"]] = len(homepages) - 1
            continue
        existing = dict(homepages[idx])
        merged = dict(entry)
        for key in _PRESERVED_KEYS:
            if key in existing:
                merged[key] = existing[key]
        homepages[idx] = merged
    return scenarios


def handle_entity_introduction(args: argparse.Namespace) -> None:
    entities_root = Path(args.entities_root) if args.entities_root else (PUBLISH_ROOT / "entities")
    scenarios_path = Path(args.scenarios) if args.scenarios else DEFAULT_SCENARIOS_PATH
    if not entities_root.is_dir():
        print(f"[fixture] ERROR: entities root 不存在: {entities_root}", file=sys.stderr)
        raise SystemExit(2)
    if not scenarios_path.is_file():
        print(f"[fixture] ERROR: scenarios fixture 不存在: {scenarios_path}", file=sys.stderr)
        raise SystemExit(2)

    wanted = [ref.strip().strip("/") for ref in (args.entity or "").split(",") if ref.strip()]
    refs: list[str] = []
    if wanted:
        refs = wanted
    else:
        for header_path in sorted(entities_root.rglob("_entity.json")):
            refs.append(str(header_path.parent.relative_to(entities_root)).replace("\\", "/"))

    entries: list[dict[str, Any]] = []
    all_issues: list[str] = []
    for ref in refs:
        entry, issues = project_entity_introduction(
            entities_root / ref,
            ref,
            media_base_url=args.media_base_url or "",
        )
        all_issues.extend(issues)
        if entry is not None:
            entries.append(entry)

    for issue in all_issues:
        print(f"[fixture] ISSUE: {issue}", file=sys.stderr)
    if not entries:
        print("[fixture] ERROR: 没有可转换的实体（全部缺 page.md/类型未登记/资产未物化）", file=sys.stderr)
        raise SystemExit(1)
    if args.strict and all_issues:
        print(f"[fixture] ERROR: --strict 下存在 {len(all_issues)} 个 issue，拒绝写入", file=sys.stderr)
        raise SystemExit(1)

    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    merge_into_scenarios(scenarios, entries)
    if args.dry_run:
        print(f"[fixture] dry-run: 将写入 {len(entries)} 个主页条目到 {scenarios_path}")
        for entry in entries:
            print(f"  - {entry['homepageId']} ({entry['title']}) sections={len(entry['introduction']['sections'])}")
        return
    write_json(scenarios_path, scenarios)
    print(f"[fixture] 写入 {len(entries)} 个主页条目 -> {scenarios_path}")
    for entry in entries:
        print(f"  - {entry['homepageId']} ({entry['title']}) sections={len(entry['introduction']['sections'])}")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("fixture", help="publish 真实实体 → App contract fixture 转换")
    sub = p.add_subparsers(dest="fixture_command")

    pe = sub.add_parser(
        "entity-introduction",
        help="把 publish 实体 page.md+manifest 投影为 entity_scenarios.json introduction fixture",
    )
    pe.add_argument("--entity", help="实体相对路径（如 地点/景区/乐山大佛），逗号分隔；缺省转换全部")
    pe.add_argument("--entities-root", help="实体根目录（默认 publish/entities）")
    pe.add_argument("--scenarios", help=f"目标 scenarios fixture（默认 {DEFAULT_SCENARIOS_PATH}）")
    pe.add_argument("--media-base-url", default="", help="资产 objectKey → URL 的 media base（缺省用 manifest cdnUrl）")
    pe.add_argument("--strict", action="store_true", help="任何资产/类型 issue 都拒绝写入")
    pe.add_argument("--dry-run", action="store_true", help="只打印将写入的条目，不改 fixture")
    pe.set_defaults(handler=handle_entity_introduction)

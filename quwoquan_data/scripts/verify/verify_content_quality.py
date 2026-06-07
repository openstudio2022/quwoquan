#!/usr/bin/env python3
"""Content quality gate for materialized article packages."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import re
import sys
from pathlib import Path

from _common.article_package import sha256_file
from _common.entity_annotation import annotation_publish_issues
from _common.intersection_signal import intersection_hint_issues
from _common.provenance import provenance_issues
from template.condition import REGION_LOCKED_TERMS

# asset:// 引用 token：允许中文实体名（assetId 可读化后含中文）。
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")


FORBIDDEN = ["冷启动", "批次", "角色：", "占位", "contract_fixture", "isSystemBuiltin", "routingReason"]


def _default_posts_root(task: str | None, batch: str | None) -> Path | None:
    if task and batch:
        from _common.paths import batch_posts_root
        return batch_posts_root(task, batch)
    return None


def verify_posts(posts_root: Path) -> list[str]:
    issues: list[str] = []
    if not posts_root.exists():
        return issues
    for article_path in sorted(posts_root.rglob("article.md")):
        post_dir = article_path.parent
        manifest_path = post_dir / "manifest.json"
        article = article_path.read_text(encoding="utf-8")
        manifest = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            issues.append(f"{post_dir}: missing manifest.json")

        for word in FORBIDDEN:
            if word in article:
                issues.append(f"{article_path}: forbidden phrase found: {word}")
        if len(re.sub(r"\s+", "", article)) < 600:
            issues.append(f"{article_path}: article body shorter than 600 non-space chars")
        if re.search(r"(?m)^标签[:：]", article):
            issues.append(f"{article_path}: standalone tag section is not allowed")

        tag_refs = manifest.get("tagRefs", [])
        entity_refs = manifest.get("entityRefs", [])
        if not isinstance(tag_refs, list) or len(tag_refs) < 2:
            issues.append(f"{manifest_path}: tagRefs must contain at least 2 refs")
        if not isinstance(entity_refs, list):
            issues.append(f"{manifest_path}: entityRefs must be an array")
        if not manifest.get("sourceTaskId"):
            issues.append(f"{manifest_path}: missing sourceTaskId provenance (task trace/hydrate 必需)")

        found_region_terms = sorted({term for term in REGION_LOCKED_TERMS if term in article})
        if found_region_terms and not _authorized_region(manifest):
            issues.append(
                f"{article_path}: region-locked terms {found_region_terms} require "
                "conditionContext.region in manifest (地域专有现象必须由 region 条件授权)"
            )

        issues.extend(asset_closure_issues(post_dir, manifest))
        # 出处强制门：交付 post 必须有完整且一致的 provenance.json。
        issues.extend(provenance_issues(post_dir, manifest))
        # 实体标注强制门：manifest.entityRefs 每个实体必须在正文 inline 标注并登记闭环。
        issues.extend(annotation_publish_issues(article, entity_refs if isinstance(entity_refs, list) else []))
        # 「明」交集信号强制门：每个 post 必须有完备的 intersectionHints（对齐 IntersectionReason 闭集）。
        issues.extend(intersection_hint_issues(manifest.get("intersectionHints"), manifest))
    return issues


def _asset_index(manifest: dict) -> tuple[dict[str, str], dict[str, str]]:
    """返回 (assetId→fileName, assetId→sha256)。fileName/sha256 取顶层 assets。"""

    id_to_file: dict[str, str] = {}
    for asset in manifest.get("assets") or []:
        if isinstance(asset, dict) and asset.get("assetId"):
            id_to_file[str(asset["assetId"])] = str(asset.get("fileName") or "")
    id_to_sha: dict[str, str] = {}
    for asset in manifest.get("assets") or []:
        if isinstance(asset, dict) and asset.get("assetId"):
            id_to_sha[str(asset["assetId"])] = str(asset.get("sha256") or "")
    return id_to_file, id_to_sha


def _referenced_asset_ids(post_dir: Path) -> set[str]:
    """收集 article.md + gallery.md 内的全部 asset:// 引用 id（含 frontmatter coverImage）。"""
    refs: set[str] = set()
    for md_name in ("article.md", "gallery.md"):
        md_path = post_dir / md_name
        if not md_path.is_file():
            continue
        for ref in _ASSET_REF_RE.findall(md_path.read_text(encoding="utf-8")):
            refs.add(ref.split("/")[-1])
    return refs


def asset_closure_issues(post_dir: Path, manifest: dict) -> list[str]:
    """asset:// 引用闭环：引用 → manifest.assets → fileName → 物理文件 → sha256 全链可追。

    评审痛点「图片找不到对应资源文件」的硬门：
    1. 正向——article/gallery 的每个 asset:// 引用都能在 manifest 命中（assetId 或 fileName）；
    2. 物理——每个声明 asset 的 assets/<fileName> 真实存在于盘上；
    3. 一致——若 manifest.assets 记录了 sha256，则物理文件摘要必须与之一致。
    """
    issues: list[str] = []
    id_to_file, id_to_sha = _asset_index(manifest)
    known_ids = set(id_to_file) | set(id_to_sha)
    file_names = {name for name in id_to_file.values() if name}
    assets_dir = post_dir / "assets"

    for ref in sorted(_referenced_asset_ids(post_dir)):
        if ref not in known_ids and ref not in file_names:
            issues.append(f"{post_dir}: asset ref not in manifest: {ref}")

    for asset_id, file_name in id_to_file.items():
        if not file_name:
            issues.append(f"{post_dir}: asset {asset_id} missing fileName in manifest")
            continue
        physical = assets_dir / file_name
        if not physical.is_file():
            issues.append(f"{post_dir}: asset file missing on disk: assets/{file_name} (assetId={asset_id})")
            continue
        expected = id_to_sha.get(asset_id)
        if expected:
            actual = sha256_file(physical)
            if actual != expected:
                issues.append(
                    f"{post_dir}: asset sha256 mismatch for {file_name}: manifest={expected} disk={actual}"
                )
    return issues


def _authorized_region(manifest: dict) -> bool:
    context = manifest.get("conditionContext")
    if not isinstance(context, dict) or not context:
        recommendation = manifest.get("recommendation")
        context = recommendation.get("conditionContext", {}) if isinstance(recommendation, dict) else {}
    if not isinstance(context, dict):
        return False
    return bool(context.get("region"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify materialized content quality")
    parser.add_argument("--task")
    parser.add_argument("--batch")
    parser.add_argument("--posts-root")
    args = parser.parse_args()

    posts_root = Path(args.posts_root) if args.posts_root else _default_posts_root(args.task, args.batch)
    if posts_root is None:
        print("[content-quality] No posts root specified; template-only gate skipped")
        return
    issues = verify_posts(posts_root)
    if issues:
        print(f"[content-quality] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    print(f"[content-quality] PASSED: {posts_root}")


if __name__ == "__main__":
    main()

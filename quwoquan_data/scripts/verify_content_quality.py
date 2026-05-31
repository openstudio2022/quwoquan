#!/usr/bin/env python3
"""Content quality gate for materialized article packages."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _common.paths import batch_command_root
from template.condition import REGION_LOCKED_TERMS


FORBIDDEN = ["冷启动", "批次", "角色：", "占位", "contract_fixture", "isSystemBuiltin", "routingReason"]


def _default_posts_root(task: str | None, batch: str | None) -> Path | None:
    if task and batch:
        return batch_command_root(task, batch, "produce") / "posts"
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

        found_region_terms = sorted({term for term in REGION_LOCKED_TERMS if term in article})
        if found_region_terms and not _authorized_region(manifest):
            issues.append(
                f"{article_path}: region-locked terms {found_region_terms} require "
                "conditionContext.region in manifest (地域专有现象必须由 region 条件授权)"
            )

        asset_ids = _asset_ids(manifest)
        for asset_ref in re.findall(r"asset://([A-Za-z0-9_./-]+)", article):
            normalized = asset_ref.split("/")[-1]
            if normalized not in asset_ids and asset_ref not in asset_ids:
                issues.append(f"{article_path}: asset ref not in manifest: {asset_ref}")
    return issues


def _authorized_region(manifest: dict) -> bool:
    context = manifest.get("conditionContext")
    if not isinstance(context, dict) or not context:
        recommendation = manifest.get("recommendation")
        context = recommendation.get("conditionContext", {}) if isinstance(recommendation, dict) else {}
    if not isinstance(context, dict):
        return False
    return bool(context.get("region"))


def _asset_ids(manifest: dict) -> set[str]:
    assets = manifest.get("articleAssetManifest", {}).get("assets")
    if not isinstance(assets, list):
        assets = manifest.get("assets", [])
    ids: set[str] = set()
    for asset in assets or []:
        if isinstance(asset, dict):
            for key in ("assetId", "fileName"):
                value = asset.get(key)
                if isinstance(value, str):
                    ids.add(value)
    return ids


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

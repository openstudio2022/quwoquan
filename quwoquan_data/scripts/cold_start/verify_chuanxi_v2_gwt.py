#!/usr/bin/env python3
"""川西 v2 acceptance GWT 样例校验（plan 第七节 6 条）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.paths import batch_command_root, release_root  # noqa: E402
from cold_start.chuanxi_catalog_v2 import CHUANXI_V2_RELEASE_ID, CHUANXI_V2_TASK_ID  # noqa: E402
from verify_content_quality import verify_posts  # noqa: E402

GWT_SAMPLES: list[tuple[str, str, str]] = [
    ("entity_intro", "article", "九寨沟_攻略"),
    ("weekend_chengdu", "article", "青城山都江堰_公共交通"),
    ("loop_3_5d", "article", "九寨黄龙环线_跟团_夏"),
    ("deep_7_14d", "article", "格聂徒步穿越_自驾_夏"),
    ("inbound_hub", "article", "北京出发_稻城亚丁经典线_散团_夏"),
    ("images_p0", "image", "四姑娘山_图文画报"),
]


def _post_dir(task_id: str, batch_id: str, content_type: str, ref: str) -> Path:
    return (
        batch_command_root(task_id, batch_id, "produce")
        / "posts"
        / content_type
        / ref
    )


def verify_gwt(task_id: str = CHUANXI_V2_TASK_ID) -> list[str]:
    issues: list[str] = []
    for batch_id, content_type, ref in GWT_SAMPLES:
        post_dir = _post_dir(task_id, batch_id, content_type, ref)
        if not post_dir.is_dir():
            issues.append(f"missing post dir: {post_dir}")
            continue
        manifest_path = post_dir / "manifest.json"
        if not manifest_path.exists():
            issues.append(f"missing manifest: {manifest_path}")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("reviewDecision") != "approved":
            issues.append(f"{ref}: reviewDecision not approved")
        if content_type == "article":
            article_path = post_dir / "article.md"
            if not article_path.exists():
                issues.append(f"{ref}: missing article.md")
            else:
                issues.extend(verify_posts(post_dir))
        else:
            assets = list((post_dir / "assets").glob("*")) if (post_dir / "assets").is_dir() else []
            if not assets and not (post_dir / "gallery.md").exists():
                issues.append(f"{ref}: image package incomplete")
    return issues


def verify_release(release_id: str = CHUANXI_V2_RELEASE_ID) -> list[str]:
    issues: list[str] = []
    root = release_root(release_id)
    if not root.exists():
        return [f"release not found: {root}"]
    posts = list((root / "posts").rglob("manifest.json"))
    if len(posts) < 115:
        issues.append(f"release posts count low: {len(posts)} (expected ~122)")
    for _, _, ref in GWT_SAMPLES:
        matches = list((root / "posts").rglob(f"{ref}/manifest.json"))
        if not matches:
            issues.append(f"release missing GWT ref: {ref}")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify 川西 v2 GWT acceptance samples")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    issues = verify_gwt()
    if args.release:
        issues.extend(verify_release())
    if issues:
        print(f"[gwt] FAILED ({len(issues)} issue(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        sys.exit(1)
    print(f"[gwt] PASSED: {len(GWT_SAMPLES)} samples")


if __name__ == "__main__":
    main()

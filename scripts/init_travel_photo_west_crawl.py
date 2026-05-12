#!/usr/bin/env python3
"""
初始化「川滇藏 + 新疆」旅行摄影 crawl runtime：
- 写入 quwoquan_data/runtime（默认 gitignore）
- 生成实体树 YAML、景点 catalog、spec

克隆 image lane 请在 pool-bootstrap 之后执行：
  python3 scripts/clone_travel_photo_west_image_pools.py

用法：
  python3 scripts/init_travel_photo_west_crawl.py [--limit N]   # 仅取前 N 个景点（调试）

默认写入全部模板景点。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "quwoquan_data"
sys.path.insert(0, str(DATA_ROOT / "tools"))

from common import (  # noqa: E402
    CRAWL_SPEC_ROOT,
    RUNTIME_ROOT,
    TREES_ROOT,
    ensure_runtime_layout,
    read_ndjson,
    write_ndjson,
    write_text,
    write_yaml,
)

TEMPLATE_ATTRACTIONS = (
    DATA_ROOT / "catalog_templates" / "travel_photo_west" / "attractions.ndjson"
)
SPEC_ID = "travel_photo_chuan_dian_zang_xinjiang_001"
TAG_REL = "trees/tags/主题/旅行摄影.yaml"
ENTITY_DIR = TREES_ROOT / "entities" / "地点"


def write_tag_yaml() -> None:
    path = RUNTIME_ROOT / TAG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(
        path,
        """tag_id: theme_travel_photography
label: 旅行摄影
summary: 川滇藏与新疆等区域的风光与人文旅行摄影选题标签。
""",
    )


def write_entity_yaml(idx: int, name: str, region: str, aliases: list[str]) -> str:
    ENTITY_DIR.mkdir(parents=True, exist_ok=True)
    rel_path = f"trees/entities/地点/tw_ent_{idx:03d}.yaml"
    path = RUNTIME_ROOT / rel_path
    lines = [
        f"entity_id: tw_ent_{idx:03d}",
        f"name: {name}",
        "kind: scenic_spot",
        f"summary: {region}旅行摄影相关地标（自动生成）。",
    ]
    if aliases:
        lines.append("aliases:")
        for a in aliases:
            lines.append(f"  - {a}")
    lines.extend(
        [
            "scene_tag_refs:",
            f"  - {TAG_REL}",
            "category_tag_refs:",
            f"  - {TAG_REL}",
            "search_terms:",
            f"  - {name}",
            f"  - {name} 摄影",
        ]
    )
    write_text(path, "\n".join(lines) + "\n")
    return rel_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅初始化前 N 个景点（0 表示全部）",
    )
    args = parser.parse_args()

    ensure_runtime_layout()
    if not TEMPLATE_ATTRACTIONS.is_file():
        print(f"缺少模板 {TEMPLATE_ATTRACTIONS}", file=sys.stderr)
        return 1

    rows = read_ndjson(TEMPLATE_ATTRACTIONS)
    if not rows:
        print("attractions 为空", file=sys.stderr)
        return 1
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    seed_dir = RUNTIME_ROOT / "seed" / "catalogs"
    seed_dir.mkdir(parents=True, exist_ok=True)
    catalog_dst = seed_dir / "travel_photo_west_attractions.ndjson"
    shutil.copyfile(TEMPLATE_ATTRACTIONS, catalog_dst)
    # 覆盖为切片后的子集，便于 --limit 调试
    write_ndjson(catalog_dst, rows)

    write_tag_yaml()

    entity_refs: list[str] = []
    image_topic_ids: list[str] = []
    for i, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        region = str(raw.get("region") or "").strip()
        aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
        aliases_s = [str(a).strip() for a in aliases if str(a).strip()]
        ref = write_entity_yaml(i, name, region, aliases_s)
        entity_refs.append(ref)
        tid = str(raw.get("topic_id") or "").strip()
        if tid.startswith("tw_art_"):
            image_topic_ids.append(tid.replace("tw_art_", "tw_img_", 1))

    entity_refs = sorted(set(entity_refs))

    catalog_rel = "seed/catalogs/travel_photo_west_attractions.ndjson"
    spec = {
        "spec_id": SPEC_ID,
        "query": "川滇藏与新疆旅行风光与人文摄影选题：权威百科与开放旅行页面聚合",
        "search_provider": "native_fetch",
        "article_topic_catalog_ref": catalog_rel,
        "entity_refs": entity_refs,
        "tag_refs": [TAG_REL],
        "target_envs": ["alpha", "gamma"],
        "creator_refs": {
            "article": ["fixture_user_travel", "fixture_user_article"],
            "image": ["fixture_user_photo"],
        },
        "publish_policy": {"visibility": "public", "assistant_use_policy": "inherit"},
        "discovery_policy": {
            "min_article_topics": len(rows),
            "min_image_topics": len(image_topic_ids),
            "min_candidate_sources_per_task": 8,
            "min_article_publish_topics": min(6, len(rows)),
            "min_image_publish_topics": min(3, len(image_topic_ids)),
        },
        "article_lane": {
            "allow_domains": [
                "you.ctrip.com",
                "www.mafengwo.cn",
                "www.qunar.com",
                "baike.baidu.com",
                "zh.wikipedia.org",
                "zh.wikivoyage.org",
                "commons.wikimedia.org",
                "upload.wikimedia.org",
            ]
        },
        "image_lane": {
            "allow_domains": [
                "you.ctrip.com",
                "www.mafengwo.cn",
                "www.qunar.com",
                "tuchong.com",
                "500px.com",
                "www.lofter.com",
                "baike.baidu.com",
                "zh.wikipedia.org",
                "commons.wikimedia.org",
                "upload.wikimedia.org",
            ]
        },
        "sample_topics": {
            "article": [],
            "image": image_topic_ids,
        },
    }
    write_yaml(CRAWL_SPEC_ROOT / f"{SPEC_ID}.yaml", spec)

    print(
        json.dumps(
            {
                "ok": True,
                "runtimeRoot": str(RUNTIME_ROOT),
                "specPath": str(CRAWL_SPEC_ROOT / f'{SPEC_ID}.yaml'),
                "entityCount": len(entity_refs),
                "articleTopicCount": len(rows),
                "imageTopicCount": len(image_topic_ids),
                "catalogRef": catalog_rel,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

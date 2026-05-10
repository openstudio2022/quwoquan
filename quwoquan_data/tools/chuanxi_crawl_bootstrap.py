#!/usr/bin/env python3
"""
川西/通用景点 pool 初始化入口（薄封装）。

推荐优先使用命令：
  python3 quwoquan_data/tools/cli.py crawl pool-bootstrap --spec ... [--catalog ...]

本脚本保留兼容，参数转发至 crawl_topic_pool.bootstrap_from_attractions_yaml。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import CRAWL_SPEC_ROOT, RUNTIME_ROOT, read_ndjson, read_yaml
from crawl_topic_pool import bootstrap_from_attractions_yaml, load_travel_url_seed_ndjson


def main() -> int:
    parser = argparse.ArgumentParser(description="（兼容）景点 source_pool 初始化，请优先使用 crawl pool-bootstrap")
    parser.add_argument("--spec", default=str(CRAWL_SPEC_ROOT / "chengdu_chuanxi_attractions_001.yaml"))
    parser.add_argument("--catalog", default=str(RUNTIME_ROOT / "seed" / "chuanxi_attractions_catalog.yaml"))
    parser.add_argument("--max-sources", type=int, default=22)
    parser.add_argument("--wiki-expand", default="filtered", choices=["none", "filtered", "full"])
    parser.add_argument("--wiki-link-budget", type=int, default=40)
    parser.add_argument("--baike-link-budget", type=int, default=24)
    parser.add_argument("--wikivoyage-limit", type=int, default=12)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--skip-baike-scrape", action="store_true")
    parser.add_argument("--merge", action="store_true", help="按 sourceUrl 去重合并到已有 source_pool")
    parser.add_argument("--topics", default="", help="逗号分隔 topic_id，仅处理指定 topic")
    parser.add_argument("--travel-seed", default="", help="travel_urls_by_topic.ndjson 路径")
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve() if Path(args.spec).is_absolute() else (Path.cwd() / args.spec).resolve()
    catalog_path = (
        Path(args.catalog).resolve()
        if Path(args.catalog).is_absolute()
        else (Path.cwd() / args.catalog).resolve()
    )
    if not spec_path.exists() or not catalog_path.exists():
        print("缺少 spec 或 catalog", file=sys.stderr)
        return 1
    spec = read_yaml(spec_path)
    if catalog_path.suffix.lower() == ".ndjson":
        catalog = {"attractions": read_ndjson(catalog_path)}
    else:
        catalog = read_yaml(catalog_path)
    travel_by = (
        load_travel_url_seed_ndjson(Path(args.travel_seed).resolve())
        if str(args.travel_seed).strip()
        else {}
    )
    topic_filter = {t.strip() for t in str(args.topics).split(",") if t.strip()} or None
    bootstrap_from_attractions_yaml(
        spec,
        catalog,
        max_sources=int(args.max_sources),
        wiki_expand=str(args.wiki_expand),
        wiki_link_budget=int(args.wiki_link_budget),
        baike_link_budget=int(args.baike_link_budget),
        wikivoyage_limit=int(args.wikivoyage_limit),
        sleep_s=float(args.sleep),
        skip_baike_scrape=bool(args.skip_baike_scrape),
        merge=bool(args.merge),
        topic_filter=topic_filter,
        travel_seed_by_topic=travel_by,
    )
    try:
        rel = str(spec_path.relative_to(Path.cwd()))
    except ValueError:
        rel = str(spec_path)
    print(json.dumps({"ok": True, "next": f"python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec {rel}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

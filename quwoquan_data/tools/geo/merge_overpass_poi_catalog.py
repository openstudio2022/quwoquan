#!/usr/bin/env python3
"""
合并多份 Overpass `out body` JSON（含 `elements`），输出与
`python3 quwoquan_data/tools/cli.py crawl export-poi-topics`
相同字段约定的景点 NDJSON catalog。

用法（在仓库根目录）：

  python3 quwoquan_data/tools/geo/merge_overpass_poi_catalog.py \\
    --inputs artifacts/a.json artifacts/b.json \\
    --output quwoquan_data/runtime/seed/sichuan_merged_pois.ndjson \\
    --topic-id-prefix poi_sichuan

分层采集建议：
1）省/州的 admin relation 拉出市县级 relation 或 bbox 切片；
2）各市/县 bbox 内跑 tourism/historic/attraction；
3）多文件经本脚本去重合并（同一 element id 只保留一次），再设为 spec.article_topic_catalog_ref。

四川省域若要在线切片并写入省/市州字段：可直接使用同目录
`build_sichuan_attractions_catalog.py`（默认按 21 个地级行政区 Overpass 切片）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root / "quwoquan_data" / "tools"))
    from common import write_ndjson  # noqa: E402

    parser = argparse.ArgumentParser(description="合并 Overpass JSON → POI NDJSON catalog")
    parser.add_argument("--inputs", nargs="+", required=True, help="Overpass 导出 JSON（含 elements）")
    parser.add_argument("--output", required=True, help="输出 NDJSON（runtime 下路径建议）")
    parser.add_argument("--topic-id-prefix", default="poi", help="topic_id 前缀（与 export-poi-topics 一致）")
    args = parser.parse_args()

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = (repo_root / out_path).resolve()
    else:
        out_path = out_path.resolve()

    merged_elements: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    prefix = str(args.topic_id_prefix or "poi").strip() or "poi"

    for raw_in in args.inputs:
        in_path = Path(raw_in)
        if not in_path.is_absolute():
            in_path = (repo_root / in_path).resolve()
        else:
            in_path = in_path.resolve()
        if not in_path.is_file():
            print(f"[merge_overpass_poi_catalog] SKIP missing {in_path}", file=sys.stderr)
            continue
        data = json.loads(in_path.read_text(encoding="utf-8"))
        for el in data.get("elements") or []:
            if not isinstance(el, dict):
                continue
            et = str(el.get("type") or "x").strip()
            el_id = el.get("id")
            if el_id is None:
                continue
            uid = f"{et}:{el_id}"
            if uid in seen_ids:
                continue
            seen_ids.add(uid)
            merged_elements.append(el)

    rows: list[dict[str, object]] = []
    for el in merged_elements:
        el_type = str(el.get("type") or "x").strip()
        el_id = el.get("id")
        tags = el.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        name = str(tags.get("name:zh") or tags.get("name") or "").strip()
        if not name:
            continue
        tourism = str(tags.get("tourism") or "").strip()
        historic = str(tags.get("historic") or "").strip()
        amenity = str(tags.get("amenity") or "").strip()
        if not (tourism or historic or amenity in {"museum", "arts_centre"}):
            continue
        topic_id = f"{prefix}_{el_type}_{el_id}"
        row: dict[str, object] = {
            "topic_id": topic_id,
            "name": name,
            "wiki_title": name,
            "baike_item": name,
        }
        province = str(
            tags.get("addr:province")
            or tags.get("is_in:province")
            or tags.get("addr:state")
            or ""
        ).strip()
        prefecture = str(
            tags.get("addr:city")
            or tags.get("is_in:city")
            or tags.get("addr:region")
            or ""
        ).strip()
        district = str(
            tags.get("addr:district")
            or tags.get("addr:county")
            or tags.get("is_in:municipality")
            or ""
        ).strip()
        if province:
            row["province"] = province
        if prefecture:
            row["prefecture"] = prefecture
        if district:
            row["district"] = district
        geo_hints: list[str] = []
        for g in (province, prefecture, district):
            if g and g not in geo_hints:
                geo_hints.append(g)
        if geo_hints:
            row["expected_region_keywords"] = geo_hints[:8]
        rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_ndjson(out_path, rows)
    print(
        f"[merge_overpass_poi_catalog] OK: elements={len(merged_elements)} rows={len(rows)} -> {out_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

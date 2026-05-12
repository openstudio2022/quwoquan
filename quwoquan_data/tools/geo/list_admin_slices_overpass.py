#!/usr/bin/env python3
"""
枚举指定省级行政区下的 boundary admin relation，输出可作为 geo_catalog_config scope.slices 的名称列表。

示例：

  python3 quwoquan_data/tools/geo/list_admin_slices_overpass.py \\
    --province 四川省 --admin-level 6 --emit-yaml

需联网访问 Overpass；CI 勿依赖本脚本输出文件为唯一真相源（可把生成结果检入 config）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _http_overpass(query: str, retries: int = 3) -> dict:
    url = "https://overpass-api.de/api/interpreter"
    data = query.encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "quwoquan-data-list-admin-slices/1.0 (+https://github.com/quwoquan/quwoquan)",
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_err = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"Overpass 请求失败: {last_err}")


def _build_query(*, province_zh: str, province_admin_level: str, child_admin_level: str, name_key: str) -> str:
    return "\n".join(
        [
            "[out:json][timeout:180];",
            f'area["{name_key}"="{province_zh}"]["admin_level"="{province_admin_level}"]->.p;',
            "(",
            f'  relation["admin_level"="{child_admin_level}"]["boundary"="administrative"](area.p);',
            ");",
            "out tags;",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Overpass 枚举省以下行政切片名称")
    parser.add_argument("--province", default="四川省", help="省级名称（与 OSM name:zh 一致）")
    parser.add_argument(
        "--province-admin-level",
        default="4",
        help="省 relation/area 的 admin_level（中国省一般为 4）",
    )
    parser.add_argument("--admin-level", default="6", dest="child_admin_level", help="下级行政区 admin_level（县/区一般为 6）")
    parser.add_argument("--name-key", default="name:zh", help="切片名称 tag")
    parser.add_argument("--emit-yaml", action="store_true", help="打印为 YAML list 片段（每行 - 名称）")
    parser.add_argument("--out", default="", help="可选：写入 UTF-8 文本（每行一个名称）")
    ns = parser.parse_args(argv)

    query = _build_query(
        province_zh=str(ns.province).strip(),
        province_admin_level=str(ns.province_admin_level).strip() or "4",
        child_admin_level=str(ns.child_admin_level).strip() or "6",
        name_key=str(ns.name_key).strip() or "name:zh",
    )
    data = _http_overpass(query)
    names: list[str] = []
    for el in data.get("elements") or []:
        if not isinstance(el, dict) or str(el.get("type")) != "relation":
            continue
        tags = el.get("tags") or {}
        if not isinstance(tags, dict):
            continue
        if str(tags.get("boundary") or "").strip() != "administrative":
            continue
        raw = str(tags.get(str(ns.name_key).strip() or "name:zh") or tags.get("name") or "").strip()
        if raw:
            names.append(raw)
    names = sorted(set(names))

    out_path = str(ns.out or "").strip()
    if out_path:
        Path(out_path).write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")

    if ns.emit_yaml:
        for n in names:
            print(f"    - {n}")
    else:
        for n in names:
            print(n)

    print(f"# total_unique_slices={len(names)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

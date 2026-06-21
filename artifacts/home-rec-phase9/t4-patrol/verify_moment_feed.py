#!/usr/bin/env python3
"""验证 gamma-local 首页推荐频道（identity=moment）多形态 + 连刷≥2 页曝光不重复。

复现：
  python3 artifacts/home-rec-phase9/t4-patrol/verify_moment_feed.py \
    --base http://localhost:19000 --out artifacts/home-rec-phase9/t4-patrol/moment_feed_pagination.json
可选 --user us_01_3278 模拟登录 viewer（应用 rec:hidden_authors / rec:negative 抑制）。
"""
from __future__ import annotations

import argparse
import json
import urllib.request


def fetch(base: str, limit: int, cursor: str, user: str) -> dict:
    url = f"{base}/v1/content/feed?identity=moment&category=micro&limit={limit}"
    if cursor:
        url += f"&cursor={cursor}"
    req = urllib.request.Request(url)
    if user:
        req.add_header("X-Client-User-Id", user)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize(items: list[dict]) -> list[dict]:
    rows = []
    for it in items:
        w, h = it.get("width"), it.get("height")
        orient = ""
        if it.get("videoUrl"):
            orient = "portrait" if (w and h and w < h) else "landscape"
        rows.append(
            {
                "id": it.get("id"),
                "type": it.get("type"),
                "contentType": it.get("contentType"),
                "imageCount": len(it.get("images") or []),
                "hasVideo": bool(it.get("videoUrl")),
                "videoOrientation": orient,
                "width": w,
                "height": h,
                "createdAt": it.get("createdAt"),
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:19000")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--user", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    p1 = fetch(args.base, args.limit, "", args.user)
    cur = p1.get("nextCursor") or p1.get("cursor") or ""
    p2 = fetch(args.base, args.limit, cur, args.user) if cur else {"items": []}

    rows1 = summarize(p1.get("items", []))
    rows2 = summarize(p2.get("items", []))
    ids1 = [r["id"] for r in rows1]
    ids2 = [r["id"] for r in rows2]
    overlap = sorted(set(ids1) & set(ids2))

    def type_dist(rows):
        d = {}
        for r in rows:
            d[r["type"]] = d.get(r["type"], 0) + 1
        return d

    def seed_count(ids):
        return sum(1 for i in ids if str(i).startswith("t4hrec_moment_"))

    p1_videos = [r for r in rows1 if r["hasVideo"]]
    report = {
        "base": args.base,
        "user": args.user or "(guest)",
        "page1": {
            "count": len(rows1),
            "seedCount": seed_count(ids1),
            "typeDist": type_dist(rows1),
            "videoOrientations": sorted({r["videoOrientation"] for r in p1_videos if r["videoOrientation"]}),
            "gridCount": sum(1 for r in rows1 if r["type"] == "moment" and r["imageCount"] >= 9),
            "multiImageCount": sum(1 for r in rows1 if r["type"] == "moment" and 1 < r["imageCount"] < 9),
            "singleImageCount": sum(1 for r in rows1 if r["type"] == "moment" and r["imageCount"] == 1),
            "ids": ids1,
            "rows": rows1,
        },
        "page2": {
            "count": len(rows2),
            "seedCount": seed_count(ids2),
            "typeDist": type_dist(rows2),
            "ids": ids2,
            "rows": rows2,
        },
        "overlapBetweenPages": overlap,
        "noOverlap": len(overlap) == 0,
        "multiFormPage1": len(type_dist(rows1)) >= 2
        or (sum(1 for r in rows1 if r["type"] == "moment" and r["imageCount"] >= 9) > 0
            and any(r["hasVideo"] for r in rows1)),
    }

    print(json.dumps({k: v for k, v in report.items() if k not in ("page1", "page2")}, ensure_ascii=False, indent=2))
    print("page1 typeDist:", report["page1"]["typeDist"],
          "seed:", report["page1"]["seedCount"],
          "videoOrient:", report["page1"]["videoOrientations"],
          "grid:", report["page1"]["gridCount"],
          "multi:", report["page1"]["multiImageCount"],
          "single:", report["page1"]["singleImageCount"])
    print("page2 typeDist:", report["page2"]["typeDist"], "seed:", report["page2"]["seedCount"])
    for r in report["page1"]["rows"]:
        print(f"  P1 {r['id']:22s} type={str(r['type']):7s} imgs={r['imageCount']} "
              f"video={int(r['hasVideo'])} {r['videoOrientation']:9s} {r['width']}x{r['height']} {r['createdAt']}")

    if args.out:
        import pathlib
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

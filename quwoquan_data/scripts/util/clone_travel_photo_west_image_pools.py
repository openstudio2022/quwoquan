#!/usr/bin/env python3
"""在 crawl pool-bootstrap（article）完成后，将各 tw_art_* source_pool 克隆为 tw_img_*（taskType=image）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "quwoquan_data"
sys.path.insert(0, str(DATA_ROOT / "tools"))

import yaml  # noqa: E402

from common import CRAWL_SPEC_ROOT, RUNTIME_ROOT, read_ndjson, write_ndjson  # noqa: E402
from crawl_topic_pool import default_enrichment_row  # noqa: E402

SPEC_ID = "travel_photo_chuan_dian_zang_xinjiang_001"
SPEC_PATH = CRAWL_SPEC_ROOT / f"{SPEC_ID}.yaml"
CATALOG_TEMPLATE = DATA_ROOT / "catalog_templates" / "travel_photo_west" / "attractions.ndjson"
CATALOG_RUNTIME = RUNTIME_ROOT / "seed" / "catalogs" / "travel_photo_west_attractions.ndjson"


def main() -> int:
    spec_path = SPEC_PATH
    if not spec_path.exists():
        print(f"缺少 spec，请先运行 quwoquan_data/scripts/util/init_travel_photo_west_crawl.py: {spec_path}", file=sys.stderr)
        return 1
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    catalog_path = CATALOG_RUNTIME if CATALOG_RUNTIME.exists() else CATALOG_TEMPLATE
    rows = read_ndjson(catalog_path)
    cloned = 0
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        tid = str(raw.get("topic_id") or "").strip()
        if not tid.startswith("tw_art_"):
            continue
        img_tid = tid.replace("tw_art_", "tw_img_", 1)
        art_dir = RUNTIME_ROOT / "runs" / SPEC_ID / "topics" / tid
        sp_art = art_dir / "source_pool.ndjson"
        if not sp_art.exists():
            continue
        img_dir = RUNTIME_ROOT / "runs" / SPEC_ID / "topics" / img_tid
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "pages").mkdir(parents=True, exist_ok=True)
        pool = read_ndjson(sp_art)
        img_pool: list[dict] = []
        for row in pool:
            r = dict(row)
            r["taskType"] = "image"
            for k in ("qualityBreakdown", "publishabilityBreakdown"):
                r.pop(k, None)
            img_pool.append(r)
        write_ndjson(img_dir / "source_pool.ndjson", img_pool)
        en = img_dir / "enrichment.ndjson"
        if not en.exists():
            title = str(raw.get("name") or img_tid).strip()
            write_ndjson(en, [default_enrichment_row(spec, img_tid, "image", title)])
        cloned += 1
    print(json.dumps({"ok": True, "clonedTopics": cloned}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
四川目录构建兼容入口。

当前推荐主入口为：

  python3 quwoquan_data/tools/geo/build_geo_poi_catalog.py \
    --config specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/config/geo_catalog_config.sichuan.yaml \
    --output quwoquan_data/runtime/seed/sichuan_chuanxi_attractions_catalog.ndjson

本脚本保留向后兼容，内部转发给通用构建器。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.getenv("QWQ_REPO_ROOT", Path(__file__).resolve().parents[3])).resolve()
DEFAULT_CONFIG = (
    REPO_ROOT
    / "specs"
    / "feature-tree"
    / "runtime"
    / "runtime-data-engineering"
    / "geo-content-trinity"
    / "config"
    / "geo_catalog_config.sichuan.yaml"
)


def main(argv: list[str] | None = None) -> int:
    from build_geo_poi_catalog import main as generic_main

    return generic_main(["--config", str(DEFAULT_CONFIG), *(argv or sys.argv[1:])])


if __name__ == "__main__":
    raise SystemExit(main())

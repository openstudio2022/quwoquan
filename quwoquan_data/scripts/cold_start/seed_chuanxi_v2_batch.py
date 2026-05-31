#!/usr/bin/env python3
"""川西 v2 入口：默认仅 bootstrap（不写正文）。

旧版模版化 smoke 见 seed_chuanxi_v2_smoke.py。
正文生产见 run_chuanxi_v2_pipeline.py。

用法:
  python3 cold_start/seed_chuanxi_v2_batch.py          # bootstrap only
  python3 cold_start/run_chuanxi_v2_pipeline.py --all-batches --release
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from cold_start.bootstrap_chuanxi_v2_task import bootstrap_chuanxi_v2  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap 川西 v2（不写正文）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="运行旧版模版化 smoke（仅 pipeline 联调，非终稿）",
    )
    args = parser.parse_args()

    if args.smoke:
        from cold_start.seed_chuanxi_v2_smoke import seed_chuanxi_v2_smoke  # noqa: E402

        count = seed_chuanxi_v2_smoke(dry_run=args.dry_run)
    else:
        count = bootstrap_chuanxi_v2(dry_run=args.dry_run)
        if not args.dry_run:
            print("[seed-v2] 正文请运行: python3 cold_start/run_chuanxi_v2_pipeline.py --all-batches --release")

    if count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

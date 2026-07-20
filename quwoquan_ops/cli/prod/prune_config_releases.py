#!/usr/bin/env python3
"""云侧服务 release 配置双版本保留（IaC 收口）。

规则：每个服务 configs/releases/ 只保留两个 release 配置版本 ——
当前灰度版本与上一个版本（回滚目标）。更旧版本随发布推进删除，
历史内容由 git 承载，不在工作树保留第三份。

用法：
  python3 quwoquan_ops/cli/prod/prune_config_releases.py --check   # 门禁校验
  python3 quwoquan_ops/cli/prod/prune_config_releases.py --apply   # 实际清理
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES_DIR = ROOT / "quwoquan_service" / "services"
RETAIN_COUNT = 2


def release_files(service_dir: Path) -> list[Path]:
    releases = service_dir / "configs" / "releases"
    if not releases.is_dir():
        return []
    return sorted(
        (entry for entry in releases.iterdir() if entry.suffix == ".yaml"),
        key=lambda entry: entry.name,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="仅校验，超限退出码 1")
    mode.add_argument("--apply", action="store_true", help="删除超限的最旧版本")
    args = parser.parse_args()

    failures: list[str] = []
    for service_dir in sorted(SERVICES_DIR.iterdir()):
        if not service_dir.is_dir():
            continue
        files = release_files(service_dir)
        if len(files) <= RETAIN_COUNT:
            continue
        stale = files[:-RETAIN_COUNT]
        keep = files[-RETAIN_COUNT:]
        if args.apply:
            for entry in stale:
                entry.unlink()
                print(f"PRUNE: {entry.relative_to(ROOT)}")
            print(
                f"KEEP:  {service_dir.name} -> "
                + ", ".join(item.stem for item in keep)
            )
        else:
            failures.append(
                f"{service_dir.name}: {len(files)} release configs, keep<= {RETAIN_COUNT} "
                f"(stale: {', '.join(item.stem for item in stale)})"
            )

    if args.check:
        if failures:
            print("FAIL: config release retention exceeded (当前灰度 + 上一版本):")
            for line in failures:
                print(f"  - {line}")
            print("修复: python3 quwoquan_ops/cli/prod/prune_config_releases.py --apply")
            return 1
        print("PASS: config release retention (<=2 versions per service)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

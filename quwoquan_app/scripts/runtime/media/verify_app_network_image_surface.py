#!/usr/bin/env python3
from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-002
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-002.t4

import argparse
from pathlib import Path
import re

import yaml


ROOT = REPO_ROOT
APP_LIB = ROOT / "quwoquan_app/lib"
ALLOWLIST = ROOT / "quwoquan_ops/policies/gates/app_network_image_policy_allowlist.yaml"
EXEMPT_PATHS = {
    "core/widgets/app_image.dart",
    "design_system/media/app_cached_network_image.dart",
}
PATTERN = re.compile(
    r"\bImage\.network\s*\(|\bNetworkImage\s*\(|\bCachedNetworkImage\s*\("
)


def _scan() -> dict[str, int]:
    current: dict[str, int] = {}
    for path in APP_LIB.rglob("*.dart"):
        relative = path.relative_to(APP_LIB).as_posix()
        if relative in EXEMPT_PATHS:
            continue
        count = len(PATTERN.findall(path.read_text(encoding="utf-8", errors="replace")))
        if count > 0:
            current[relative] = count
    return current


def _load() -> dict[str, int]:
    if not ALLOWLIST.is_file():
        return {}
    data = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    return {
        str(item["path"]): int(item.get("maxCount", 0))
        for item in data.get("allowed", [])
    }


def _write(current: dict[str, int]) -> list[str]:
    """按基线自称的「只减不增」写入，拒绝把新增违规固化成豁免。

    基线文件写着 "Counts may only decrease"，但 ``--write-baseline`` 原先无条件重写，
    等于给这句话开了一扇后门：新增一处直连图片 API 再跑一次就能转绿。这里用既有基线
    作为上限——文件已随债务清零而删除时上限为空，于是任何重建都会被挡下。

    返回超过既有上限的条目；非空表示拒绝写入。
    """
    ceiling = _load()
    regressions = [
        f"{path}: {count} > 既有基线 {ceiling.get(path, 0)}"
        for path, count in sorted(current.items())
        if count > ceiling.get(path, 0)
    ]
    if regressions:
        return regressions
    if not current:
        if ALLOWLIST.is_file():
            ALLOWLIST.unlink()
        return []
    lines = [
        "version: 1",
        "description: Transitional baseline for pre-AppImage direct image APIs. Counts may only decrease.",
        "allowed:",
    ]
    for path, count in sorted(current.items()):
        lines.extend(
            [
                f"  - path: {path}",
                f"    maxCount: {count}",
            ]
        )
    ALLOWLIST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    current = _scan()
    if args.write_baseline:
        regressions = _write(current)
        if regressions:
            print(
                "[app-network-image] BLOCK: 基线只减不增，拒绝把新增直连固化成豁免",
                file=sys.stderr,
            )
            for line in regressions:
                print(f"  {line}", file=sys.stderr)
            return 2
        print(f"[app-network-image] wrote baseline entries={len(current)}")
        return 0

    allowed = _load()
    violations: list[str] = []
    for path in sorted(set(current) | set(allowed)):
        current_count = current.get(path, 0)
        allowed_count = allowed.get(path, 0)
        if current_count > allowed_count:
            violations.append(f"{path}: {current_count} > allowlist {allowed_count}")
        elif allowed_count > current_count:
            violations.append(
                f"{path}: stale allowlist budget {allowed_count} > current {current_count}"
            )
    if violations:
        print("[app-network-image] FAIL")
        print("\n".join(violations))
        return 2
    print(f"[app-network-image] OK entries={len(current)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

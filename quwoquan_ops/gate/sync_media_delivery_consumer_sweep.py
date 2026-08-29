#!/usr/bin/env python3
"""把消费面扫描册对齐到当前扫描结果。

只做两件确定性的事：删除已消失的条目（收口或行号漂移后的旧位置），把仍然存在
但行号变了的条目按原理由重新登记。**不会**自动给新出现的未登记命中编造理由——
那正是需要人判定「是缺口还是按设计公开」的地方，脚本替它选一边就等于把判据
交给了工具。

用法：
    python3 quwoquan_ops/gate/sync_media_delivery_consumer_sweep.py [--apply]

不带 --apply 时只打印差异。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops" / "gate"))

import yaml  # noqa: E402

import media_delivery_consumer_sweep as sweep  # noqa: E402


def _section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{heading}:"))
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  ") or not lines[end].strip()):
        end += 1
    return start + 1, end


def _rewrite(section: str, entries: dict[str, str], lines: list[str]) -> list[str]:
    start, end = _section_bounds(lines, section)
    body = [f"  {site}: {entries[site]}\n" for site in sorted(entries)]
    trailing = [line for line in lines[start:end] if not line.strip()]
    return lines[:start] + body + trailing + lines[end:]


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    registry_path = sweep.REGISTRY_PATH
    lines = registry_path.read_text(encoding="utf-8").splitlines(keepends=True)
    registry = yaml.safe_load("".join(lines)) or {}
    baseline = dict(registry.get("baseline") or {})
    allowlist = dict(registry.get("allowlist") or {})

    found = sweep.scan_direct_render_sites()
    found_set = set(found)
    # 同一文件内的行号漂移：按文件分组后，把册子里已消失的条目重新落到该文件
    # 仍然命中的位置上；文件整体收口时自然没有可落的位置，条目被删除。
    by_file: dict[str, list[str]] = {}
    for site in found:
        by_file.setdefault(site.rsplit(":", 1)[0], []).append(site)

    def realign(entries: dict[str, str]) -> tuple[dict[str, str], list[str], list[str]]:
        kept: dict[str, str] = {}
        removed: list[str] = []
        moved: list[str] = []
        claimed: set[str] = set()
        for site, reason in sorted(entries.items()):
            if site in found_set:
                kept[site] = reason
                claimed.add(site)
                continue
            path = site.rsplit(":", 1)[0]
            free = [s for s in by_file.get(path, []) if s not in claimed and s not in entries]
            if free:
                kept[free[0]] = reason
                claimed.add(free[0])
                moved.append(f"{site} -> {free[0]}")
            else:
                removed.append(site)
        return kept, removed, moved

    new_baseline, removed_baseline, moved_baseline = realign(baseline)
    new_allowlist, removed_allowlist, moved_allowlist = realign(allowlist)

    print(f"命中 {len(found)}")
    print(f"baseline {len(baseline)} -> {len(new_baseline)}"
          f"（收口删除 {len(removed_baseline)}，行号重定位 {len(moved_baseline)}）")
    for site in removed_baseline:
        print("  - 收口:", site)
    for move in moved_baseline:
        print("  ~ 重定位:", move)
    print(f"allowlist {len(allowlist)} -> {len(new_allowlist)}"
          f"（删除 {len(removed_allowlist)}，重定位 {len(moved_allowlist)}）")
    for site in removed_allowlist:
        print("  - 删除:", site)

    unregistered = sorted(found_set - set(new_baseline) - set(new_allowlist))
    for site in unregistered:
        print("  ! 未登记（需人工判定缺口或豁免）:", site)

    if not apply:
        print("（未写入；加 --apply 生效）")
        return 0
    lines = _rewrite("baseline", new_baseline, lines)
    lines = _rewrite("allowlist", new_allowlist, lines)
    registry_path.write_text("".join(lines), encoding="utf-8")
    print("已写入", registry_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

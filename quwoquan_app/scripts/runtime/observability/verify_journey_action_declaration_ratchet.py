#!/usr/bin/env python3
"""埋点 journey/action 闭集棘轮门禁。

产品动作埋点收敛主线：`JourneyEventTracker.trackAction` 的 `journey`/`action`
取值必须在 `page_object_contract.yaml` 的 `product_actions` 中声明（漏斗与告警
的唯一真相源），禁止业务侧继续新增自由字符串。

- 已声明对（journey, action）：直接放行；
- 未声明的字面量对、动态插值调用点、存量 `AnalyticsService.trackEvent` /
  `AnalyticsEvent(` 裸事件：进入 `journey_action_baseline.json` 棘轮，
  只减不增；新增即 BLOCK（先补契约声明再写代码）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT
from _common.ratchet_baseline import load_counts, write_counts

import yaml

LIB_ROOT = APP_ROOT / "lib"
CONTRACT_PATH = (
    REPO_ROOT
    / "quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml"
)
BASELINE_PATH = Path(__file__).with_name("journey_action_baseline.json")

_JOURNEY_RE = re.compile(r"journey:\s*'([^']*)'")
_ACTION_RE = re.compile(r"action:\s*'([^']*)'")

# 页面级 enter/exit 停留漏斗属 lifecycle 语义：其声明真相源是页面契约的
# `telemetry_descriptor.lifecycle`（由 verify_page_object_contract.py 强制每页
# 必填），不进入 product_actions 闭集；调用点以 pageName 绑定页面。
_LIFECYCLE_ACTIONS = frozenset(
    {
        "enter",
        "exit",
        "page_enter",
        "page_exit",
        "approval_page_enter",
        "approval_page_exit",
    }
)


def _declared_pairs() -> set[tuple[str, str]]:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    declared: set[tuple[str, str]] = set()
    for page in contract["pages"]:
        descriptor = page.get("telemetry_descriptor") or {}
        for product_action in descriptor.get("product_actions") or []:
            journey = product_action.get("journey", "")
            for action in product_action.get("actions") or []:
                declared.add((journey, action))
    return declared


def _track_action_segments(text: str) -> list[str]:
    segments: list[str] = []
    idx = 0
    while True:
        idx = text.find("trackAction(", idx)
        if idx < 0:
            break
        start = idx + len("trackAction(")
        depth = 1
        j = start
        while j < len(text) and depth > 0:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
            j += 1
        segments.append(text[start : j - 1])
        idx = j
    return segments


def scan() -> dict[str, int]:
    """返回棘轮口径的债务项：未声明 (journey,action) 对、动态插值、裸 Analytics。"""
    declared = _declared_pairs()
    debts: dict[str, int] = {}

    def _bump(key: str) -> None:
        debts[key] = debts.get(key, 0) + 1

    for path in sorted(LIB_ROOT.rglob("*.dart")):
        rel = path.relative_to(APP_ROOT).as_posix()
        if "/generated/" in rel or rel.endswith(".g.dart"):
            continue
        text = path.read_text(encoding="utf-8")
        for segment in _track_action_segments(text):
            journey_match = _JOURNEY_RE.search(segment)
            action_match = _ACTION_RE.search(segment)
            journey = journey_match.group(1) if journey_match else None
            action = action_match.group(1) if action_match else None
            if journey is None or action is None or "$" in (journey + action):
                _bump(f"dynamic:{rel}")
                continue
            if action in _LIFECYCLE_ACTIONS:
                continue
            if (journey, action) not in declared:
                _bump(f"undeclared:{journey} -> {action}")
        for pattern in ("AnalyticsEvent(", ".trackEvent("):
            count = text.count(pattern)
            if count:
                _bump_key = f"legacy_analytics:{rel}"
                debts[_bump_key] = debts.get(_bump_key, 0) + count
    return debts


def main() -> int:
    update = "--update-baseline" in sys.argv
    debts = scan()
    if update:
        write_counts(BASELINE_PATH, debts)
        print(
            f"OK: journey/action 埋点债务基线已更新（{sum(debts.values())} 处 / "
            f"{len(debts)} 项）"
        )
        return 0

    if not BASELINE_PATH.is_file():
        print(
            "FAIL: 缺少 journey_action_baseline.json，先运行 --update-baseline 固化存量"
        )
        return 1
    baseline = load_counts(BASELINE_PATH)

    errors: list[str] = []
    for key, count in sorted(debts.items()):
        allowed = baseline.get(key, 0)
        if count > allowed:
            errors.append(
                f"{key}: {count} 处（基线 {allowed}）；journey/action 必须先在 "
                "page_object_contract.yaml 的 product_actions 声明"
            )
    if errors:
        print("FAIL: 埋点 journey/action 闭集棘轮未通过：")
        for error in errors:
            print(f"  - {error}")
        return 1
    total_now = sum(debts.values())
    total_baseline = sum(baseline.values())
    suffix = (
        f"（基线 {total_baseline}，已下降；可运行 --update-baseline 固化战果）"
        if total_now < total_baseline
        else ""
    )
    print(f"OK: 埋点 journey/action 债务未超出基线（{total_now} 处）{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

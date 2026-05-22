#!/usr/bin/env python3
"""
端云行为 action / referral source / signal weight 三方一致性校验。

三个真相源：
  1. behaviors.yaml  — behavior_events[*].type + signal_weight
  2. hotpath.go      — SignalWeights + ReferralSourceMultiplier
  3. behavior_repository.dart — BehaviorAction enum + ReferralSource enum

校验规则：
  A) behaviors.yaml type 集合 == Go SignalWeights keys == Dart BehaviorAction wireValues
  B) behaviors.yaml signal_weight == Go SignalWeights value（浮点容差 0.001）
  C) Go ReferralSourceMultiplier keys == Dart ReferralSource wireValues
  D) entity_page_view 在 Go SignalWeights 但不在 behaviors.yaml 时仅 warn（附加 action）

用法：
  python3 scripts/recommendation/verify_behavior_action_consistency.py
  python3 scripts/recommendation/verify_behavior_action_consistency.py --warn-only
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPO_ROOT

BEHAVIORS_YAML = (
    SERVICE_ROOT
    / "contracts"
    / "metadata"
    / "content"
    / "post"
    / "behaviors.yaml"
)
HOTPATH_GO = SERVICE_ROOT / "runtime" / "recommendation" / "hotpath.go"
BEHAVIOR_REPO_DART = (
    REPO_ROOT.parent
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "services"
    / "behavior"
    / "behavior_repository.dart"
)

_GO_MAP_ENTRY = re.compile(r'"([^"]+)":\s*([-\d.]+)')
_DART_ENUM_WIRE = re.compile(r"\w+\('([^']+)'\)")
_DART_REFERRAL_CASE = re.compile(r"case\s+ReferralSource\.\w+:\s*\n\s*return\s+'([^']+)'")


def _parse_behaviors_yaml() -> tuple[dict[str, float], list[str]]:
    """Return {action: weight} and list of errors."""
    errors: list[str] = []
    if not BEHAVIORS_YAML.is_file():
        errors.append(f"behaviors.yaml 缺失: {BEHAVIORS_YAML}")
        return {}, errors
    data = yaml.safe_load(BEHAVIORS_YAML.read_text(encoding="utf-8"))
    events = data.get("behavior_events", [])
    actions: dict[str, float] = {}
    for ev in events:
        t = ev.get("type")
        w = ev.get("signal_weight")
        if t is None:
            errors.append(f"behaviors.yaml: 事件缺 type 字段: {ev}")
            continue
        if w is None:
            errors.append(f"behaviors.yaml: 事件 '{t}' 缺 signal_weight")
            continue
        actions[t] = float(w)
    return actions, errors


def _parse_go_map(src: str, var_name: str) -> dict[str, float]:
    """Extract Go var map[string]float64{...} entries."""
    pattern = re.compile(
        rf"var\s+{var_name}\s*=\s*map\[string\]float64\{{(.*?)\}}",
        re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        return {}
    body = m.group(1)
    result: dict[str, float] = {}
    for entry in _GO_MAP_ENTRY.finditer(body):
        result[entry.group(1)] = float(entry.group(2))
    return result


def _parse_hotpath_go() -> tuple[dict[str, float], dict[str, float], list[str]]:
    """Return (SignalWeights, ReferralSourceMultiplier, errors)."""
    errors: list[str] = []
    if not HOTPATH_GO.is_file():
        errors.append(f"hotpath.go 缺失: {HOTPATH_GO}")
        return {}, {}, errors
    src = HOTPATH_GO.read_text(encoding="utf-8")
    sw = _parse_go_map(src, "SignalWeights")
    rsm = _parse_go_map(src, "ReferralSourceMultiplier")
    if not sw:
        errors.append("hotpath.go: 未找到 SignalWeights map")
    if not rsm:
        errors.append("hotpath.go: 未找到 ReferralSourceMultiplier map")
    return sw, rsm, errors


def _parse_dart_behavior_actions() -> tuple[set[str], list[str]]:
    """Extract BehaviorAction enum wire values from Dart source."""
    errors: list[str] = []
    if not BEHAVIOR_REPO_DART.is_file():
        errors.append(f"behavior_repository.dart 缺失: {BEHAVIOR_REPO_DART}")
        return set(), errors
    src = BEHAVIOR_REPO_DART.read_text(encoding="utf-8")

    enum_match = re.search(
        r"enum\s+BehaviorAction\s*\{(.*?)\}",
        src,
        re.DOTALL,
    )
    if not enum_match:
        errors.append("behavior_repository.dart: 未找到 BehaviorAction enum")
        return set(), errors

    wires = set(_DART_ENUM_WIRE.findall(enum_match.group(1)))
    if not wires:
        errors.append("behavior_repository.dart: BehaviorAction enum 无 wireValue")
    return wires, errors


def _parse_dart_referral_sources() -> tuple[set[str], list[str]]:
    """Extract ReferralSource wire values from Dart extension."""
    errors: list[str] = []
    if not BEHAVIOR_REPO_DART.is_file():
        errors.append(f"behavior_repository.dart 缺失: {BEHAVIOR_REPO_DART}")
        return set(), errors
    src = BEHAVIOR_REPO_DART.read_text(encoding="utf-8")

    wires: set[str] = set()
    for m in _DART_REFERRAL_CASE.finditer(src):
        wires.add(m.group(1))
    if not wires:
        errors.append("behavior_repository.dart: 未找到 ReferralSource wire values")
    return wires, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args()

    all_errors: list[str] = []
    warnings: list[str] = []

    yaml_actions, errs = _parse_behaviors_yaml()
    all_errors.extend(errs)

    go_sw, go_rsm, errs = _parse_hotpath_go()
    all_errors.extend(errs)

    dart_actions, errs = _parse_dart_behavior_actions()
    all_errors.extend(errs)

    dart_referrals, errs = _parse_dart_referral_sources()
    all_errors.extend(errs)

    if all_errors:
        for e in all_errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 2

    yaml_set = set(yaml_actions.keys())
    go_sw_set = set(go_sw.keys())

    # A) Action set consistency
    only_yaml = yaml_set - go_sw_set
    only_go = go_sw_set - yaml_set
    only_dart = dart_actions - go_sw_set
    missing_dart = go_sw_set - dart_actions

    for a in only_yaml:
        all_errors.append(f"action '{a}' 在 behaviors.yaml 但不在 Go SignalWeights")
    for a in only_go:
        if a == "entity_page_view":
            warnings.append(
                f"action '{a}' 在 Go SignalWeights 但不在 behaviors.yaml（附加 action，可接受）"
            )
        else:
            all_errors.append(f"action '{a}' 在 Go SignalWeights 但不在 behaviors.yaml")
    for a in only_dart:
        all_errors.append(
            f"action '{a}' 在 Dart BehaviorAction 但不在 Go SignalWeights"
        )
    for a in missing_dart:
        all_errors.append(
            f"action '{a}' 在 Go SignalWeights 但不在 Dart BehaviorAction"
        )

    # B) Signal weight value consistency
    for action, yaml_w in yaml_actions.items():
        go_w = go_sw.get(action)
        if go_w is None:
            continue
        if abs(yaml_w - go_w) > 0.001:
            all_errors.append(
                f"action '{action}' signal_weight 不一致: "
                f"yaml={yaml_w}, go={go_w}"
            )

    # C) ReferralSource consistency
    go_rsm_set = set(go_rsm.keys())
    only_go_rs = go_rsm_set - dart_referrals
    only_dart_rs = dart_referrals - go_rsm_set

    for rs in only_go_rs:
        all_errors.append(
            f"referral '{rs}' 在 Go ReferralSourceMultiplier 但不在 Dart ReferralSource"
        )
    for rs in only_dart_rs:
        all_errors.append(
            f"referral '{rs}' 在 Dart ReferralSource 但不在 Go ReferralSourceMultiplier"
        )

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}", file=sys.stderr)
        label = "[verify_behavior_action_consistency]"
        if args.warn_only:
            print(f"{label} FAIL（warn-only）", file=sys.stderr)
            return 0
        print(f"{label} FAIL", file=sys.stderr)
        return 1

    print("[verify_behavior_action_consistency] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

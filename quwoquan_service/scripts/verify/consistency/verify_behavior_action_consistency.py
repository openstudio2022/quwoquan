#!/usr/bin/env python3
"""
端云行为 action / referral source / signal weight 三方一致性校验。

三个真相源：
  1. behaviors.yaml  — behavior_events[*].type + signal_weight
                       非内容推荐信号成员 non_content_signal_events[*]
  2. hotpath.go      — SignalWeights + ReferralSourceMultiplier
  3. shared_operation_enums.g.dart — BehaviorEventType（共享枚举）
     behavior_repository.dart      — ReferralSource enum

`BehaviorEventType` 是跨对象共享枚举（content/content_behavior_fact 与
circle_management/circle_behavior_fact 同时消费），而 `SignalWeights` 是 content
推荐专用权重表。因此共享枚举成员分成两类，且必须**显式声明**属于哪一类：

  - 内容推荐信号：登记在 behaviors.yaml `behavior_events`，必须有 SignalWeights 权重。
  - 非内容推荐信号：登记在 behaviors.yaml `non_content_signal_events`，必须给出
    owner 对象，且禁止出现在 SignalWeights（否则同一语义会出现第二条推荐轨）。

校验规则：
  A) Dart BehaviorEventType 成员集合 == behavior_events ⊎ non_content_signal_events
     （严格划分：不重不漏，且两侧不得交叠）
  B) behaviors.yaml type 集合 == Go SignalWeights keys
  C) behaviors.yaml signal_weight == Go SignalWeights value（浮点容差 0.001）
  D) non_content_signal_events 每项必须声明 type / owner_service / owner_object /
     rationale；owner 对象的 fields.yaml 必须真实存在且以 enum_ref 消费
     BehaviorEventType；该成员不得出现在 Go SignalWeights
  E) Go ReferralSourceMultiplier keys == Dart ReferralSource wireValues

用法：
  python3 scripts/verify/consistency/verify_behavior_action_consistency.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    p for p in Path(__file__).resolve().parents if (p / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))
from repository_root import repository_root  # noqa: E402

REPO_ROOT = repository_root()
SERVICE_ROOT = REPO_ROOT / "quwoquan_service"

BEHAVIORS_YAML = (
    SERVICE_ROOT
    / "services"
    / "content-service"
    / "contracts"
    / "content"
    / "content_behavior_fact"
    / "behaviors.yaml"
)
HOTPATH_GO = SERVICE_ROOT / "runtime" / "recommendation" / "hotpath.go"

#: 端侧行为 action 枚举现由 ContractGraph 生成，不再是手写的 `BehaviorAction`。
#: 对象化重构把 `lib/cloud/services/behavior/behavior_repository.dart` 拆成了
#: 「生成枚举 + 对象级 repository」两处，此处跟随真相源而不是保留旧路径。
BEHAVIOR_EVENT_TYPE_DART = (
    REPO_ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "generated"
    / "shared_operation_enums.g.dart"
)
#: `ReferralSource` 仍是端侧手写枚举，随对象归属搬到了 content_behavior_fact。
BEHAVIOR_REPO_DART = (
    REPO_ROOT
    / "quwoquan_app"
    / "lib"
    / "service"
    / "content_service"
    / "content"
    / "content_behavior_fact"
    / "application"
    / "public"
    / "content_behavior_repository.dart"
)

_GO_MAP_ENTRY = re.compile(r'"([^"]+)":\s*([-\d.]+)')
_DART_ENUM_WIRE = re.compile(r"""\w+\(['"]([^'"]+)['"]\)""")
_DART_REFERRAL_CASE = re.compile(r"case\s+ReferralSource\.\w+:\s*\n\s*return\s+'([^']+)'")


_NON_CONTENT_REQUIRED_KEYS = ("type", "owner_service", "owner_object", "rationale")


def _parse_behaviors_yaml() -> tuple[dict[str, float], dict[str, dict], list[str]]:
    """Return ({action: weight}, {action: non-content declaration}, errors)."""
    errors: list[str] = []
    if not BEHAVIORS_YAML.is_file():
        errors.append(f"behaviors.yaml 缺失: {BEHAVIORS_YAML}")
        return {}, {}, errors
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

    non_content: dict[str, dict] = {}
    declared = data.get("non_content_signal_events", [])
    if not isinstance(declared, list):
        errors.append("behaviors.yaml: non_content_signal_events 必须是列表")
        declared = []
    for entry in declared:
        if not isinstance(entry, dict):
            errors.append(f"behaviors.yaml: non_content_signal_events 条目须是映射: {entry}")
            continue
        missing = [k for k in _NON_CONTENT_REQUIRED_KEYS if not str(entry.get(k) or "").strip()]
        if missing:
            errors.append(
                f"behaviors.yaml: non_content_signal_events 条目 {entry.get('type')!r} "
                f"缺必填字段 {missing}"
            )
            continue
        action = entry["type"]
        if action in non_content:
            errors.append(f"behaviors.yaml: non_content_signal_events 重复声明 '{action}'")
            continue
        non_content[action] = entry
    return actions, non_content, errors


def _verify_non_content_owner(action: str, entry: dict) -> list[str]:
    """Owner 对象必须真实存在且确实以 enum_ref 消费 BehaviorEventType。"""
    owner_service = entry["owner_service"]
    owner_object = entry["owner_object"]
    fields_yaml = (
        SERVICE_ROOT / "services" / owner_service / "contracts" / owner_object / "fields.yaml"
    )
    if not fields_yaml.is_file():
        return [
            f"non_content_signal_events '{action}': owner 契约不存在 "
            f"{fields_yaml.relative_to(REPO_ROOT)}"
        ]
    if "BehaviorEventType" not in fields_yaml.read_text(encoding="utf-8"):
        return [
            f"non_content_signal_events '{action}': owner 对象 "
            f"{owner_service}/{owner_object} 的 fields.yaml 未以 enum_ref 消费 "
            f"BehaviorEventType，该 owner 声明不可信"
        ]
    return []


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
    """Extract generated BehaviorEventType enum wire names from Dart source."""
    errors: list[str] = []
    if not BEHAVIOR_EVENT_TYPE_DART.is_file():
        errors.append(f"shared_operation_enums.g.dart 缺失: {BEHAVIOR_EVENT_TYPE_DART}")
        return set(), errors
    src = BEHAVIOR_EVENT_TYPE_DART.read_text(encoding="utf-8")

    enum_match = re.search(
        r"enum\s+BehaviorEventType\s*\{(.*?)^\}",
        src,
        re.DOTALL | re.MULTILINE,
    )
    if not enum_match:
        errors.append("shared_operation_enums.g.dart: 未找到 BehaviorEventType enum")
        return set(), errors

    # 枚举体后半段是 fromWire switch，会把同一批 wire 再写一遍；只取分号之前的常量声明。
    constants = enum_match.group(1).split(";", 1)[0]
    wires = set(_DART_ENUM_WIRE.findall(constants))
    if not wires:
        errors.append("shared_operation_enums.g.dart: BehaviorEventType enum 无 wireName")
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
    all_errors: list[str] = []

    yaml_actions, non_content, errs = _parse_behaviors_yaml()
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
    non_content_set = set(non_content.keys())

    # A) 共享枚举必须被 behaviors.yaml 严格划分成「内容推荐信号」与「非内容推荐信号」
    for a in sorted(yaml_set & non_content_set):
        all_errors.append(
            f"action '{a}' 同时出现在 behavior_events 与 non_content_signal_events；"
            f"共享枚举成员只能归属其中一类"
        )
    unclassified = dart_actions - yaml_set - non_content_set
    for a in sorted(unclassified):
        all_errors.append(
            f"action '{a}' 是 BehaviorEventType 成员但未被 behaviors.yaml 归类："
            f"若是内容推荐信号请登记 behavior_events + signal_weight，"
            f"否则登记 non_content_signal_events 并声明 owner 对象"
        )
    for a in sorted(non_content_set - dart_actions):
        all_errors.append(
            f"non_content_signal_events '{a}' 不是 BehaviorEventType 成员，声明已失效"
        )
    for a in sorted(yaml_set - dart_actions):
        all_errors.append(f"action '{a}' 在 behaviors.yaml 但不是 BehaviorEventType 成员")

    # B) 内容推荐信号必须与 Go SignalWeights 逐一对应
    for a in sorted(yaml_set - go_sw_set):
        all_errors.append(f"action '{a}' 在 behaviors.yaml 但不在 Go SignalWeights")
    for a in sorted(go_sw_set - yaml_set):
        all_errors.append(f"action '{a}' 在 Go SignalWeights 但不在 behaviors.yaml")

    # D) 非内容推荐信号：owner 必须可核实，且禁止在内容推荐权重表里出现第二条轨
    for a in sorted(non_content_set):
        all_errors.extend(_verify_non_content_owner(a, non_content[a]))
        if a in go_sw_set:
            all_errors.append(
                f"action '{a}' 已声明为非内容推荐信号，却在 Go SignalWeights 登记了权重"
                f"（同一语义的第二条推荐轨）"
            )

    # C) Signal weight value consistency
    for action, yaml_w in yaml_actions.items():
        go_w = go_sw.get(action)
        if go_w is None:
            continue
        if abs(yaml_w - go_w) > 0.001:
            all_errors.append(
                f"action '{action}' signal_weight 不一致: "
                f"yaml={yaml_w}, go={go_w}"
            )

    # E) ReferralSource consistency
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

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}", file=sys.stderr)
        print("[verify_behavior_action_consistency] FAIL", file=sys.stderr)
        return 1

    print(
        "[verify_behavior_action_consistency] OK: "
        f"content_signals={len(yaml_set)} non_content_signals={len(non_content_set)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

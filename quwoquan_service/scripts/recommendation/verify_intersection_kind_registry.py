#!/usr/bin/env python3
"""交集 kind 注册表单一真相源门禁（Phase 0 漂移收口 §20d + §23 去桥接闭集校验）。

唯一真相源:
  services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml

校验项:
  1. 顶层四闭集结构完整：dimensions / lifecycleStates / verticals / objectKinds 均非空，且包含
     §22/§23 要求的必备成员（lifecycleStates 含 archived/expired，verticals 含 travel_photography/campus，
     objectKinds 含 route/photo_spot/gear）。objectKinds 每项 roles ⊆ {object,count}，roles 含 object 必填 assetKind。
  2. 注册表每个 kind 结构完整（必填 valueTier/computability/evidenceRank/vertical 等且取值合法），
     且与顶层闭集一致：objectKind/countObjectKind ∈ objectKinds，dimensions ⊆ dimensions 闭集，vertical ∈ verticals 闭集。
  3. 服务端 Go codegen 产物 generated/intersection_kind_table.go 与注册表逐字段一致（§23 去桥接：
     evidenceRank / iconKey(by kind) / iconKeyByDimension / route(by objectKind) / asset(by objectKind) /
     actionKeys(by kind) / actionLabel(by key) 全部 == registry，取代「markdown + 手写 switch」双源）。
  4. iconKeyByDimension 末级回退闭集：键 ∈ dimensions、值 ∈ iconKeyLegend，且每个维度都有回退。
  5. actionLabelByKey 键集 == actionHintLegend 键集（终端短标签与词典描述同闭集）。
  6. 服务端消费方（intersection_service.go / intersection_hydration*.go）已改为查 generated.Intersection* 表，
     不得回归手写 kind→iconKey/route/asset/action/evidenceRank switch（防漂移再生）。

退出码: 0 通过 / 1 失败。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY = (
    REPO_ROOT
    / "quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml"
)
GENERATED_TABLE = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/generated/content/post/intersection_kind_table.go"
)
SERVICE_GO = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/internal/content/post/application/intersection/intersection_service.go"
)
HYDRATION_PACKAGE = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

VALUE_TIERS = {"T1", "T2", "T3", "T4"}
COMPUTABILITY = {"R1", "R2", "R3", "R4"}
LEVELS = {"sharedFact", "bridgeFact", "impactFact", "affinity"}
CLASSES = {"fact", "affinity"}
STATUSES = {"active", "deferred"}
OBJECT_KIND_ROLES = {"object", "count"}

# §23 去桥接：闭集必备成员（防止回归把扩展项删回旧集合）。
REQUIRED_DIMENSIONS = {"identity", "location", "content", "interest", "relationship"}
REQUIRED_LIFECYCLE_STATES = {
    "new",
    "strengthened",
    "stable",
    "weakened",
    "reactivated",
    "archived",
    "expired",
}
REQUIRED_VERTICALS = {"general", "travel_photography", "campus"}
REQUIRED_OBJECT_KINDS = {
    "person",
    "circle",
    "school",
    "place",
    "enterprise",
    "route",
    "photo_spot",
    "gear",
}

REQUIRED = [
    "kind",
    "vertical",
    "entry",
    "level",
    "intersectionClass",
    "dimensions",
    "objectKind",
    "valueTier",
    "computability",
    "evidenceRank",
    "status",
]


def fail(msg: str) -> None:
    print(f"[verify-intersection-kind-registry] FAIL: {msg}")
    sys.exit(1)


def load_closed_sets(data: dict) -> tuple[set[str], set[str], set[str], set[str]]:
    """读取并校验顶层四闭集，返回 (dimensions, lifecycleStates, verticals, objectKinds)。"""
    dimensions = data.get("dimensions")
    lifecycle = data.get("lifecycleStates")
    verticals = data.get("verticals")
    object_kinds_raw = data.get("objectKinds")
    for name, value in (
        ("dimensions", dimensions),
        ("lifecycleStates", lifecycle),
        ("verticals", verticals),
        ("objectKinds", object_kinds_raw),
    ):
        if not isinstance(value, list) or not value:
            fail(f"top-level closed set `{name}` must be a non-empty list")

    dim_set = set(dimensions)
    life_set = set(lifecycle)
    vert_set = set(verticals)

    object_kinds: set[str] = set()
    for item in object_kinds_raw:
        if not isinstance(item, dict):
            fail("objectKinds entries must be mappings (kind/roles/routeId/assetKind)")
        kind = item.get("kind")
        if not kind:
            fail("objectKinds entry missing kind")
        if kind in object_kinds:
            fail(f"duplicate objectKind {kind}")
        roles = item.get("roles") or []
        if not isinstance(roles, list) or not roles:
            fail(f"objectKind {kind} must declare non-empty roles")
        bad = set(roles) - OBJECT_KIND_ROLES
        if bad:
            fail(f"objectKind {kind} invalid roles {sorted(bad)} (allowed: {sorted(OBJECT_KIND_ROLES)})")
        if "object" in roles and not str(item.get("assetKind", "")).strip():
            fail(f"objectKind {kind} has role object but missing assetKind")
        object_kinds.add(kind)

    if not REQUIRED_DIMENSIONS <= dim_set:
        fail(f"dimensions missing required members {sorted(REQUIRED_DIMENSIONS - dim_set)}")
    if not REQUIRED_LIFECYCLE_STATES <= life_set:
        fail(f"lifecycleStates missing required members {sorted(REQUIRED_LIFECYCLE_STATES - life_set)}")
    if not REQUIRED_VERTICALS <= vert_set:
        fail(f"verticals missing required members {sorted(REQUIRED_VERTICALS - vert_set)}")
    if not REQUIRED_OBJECT_KINDS <= object_kinds:
        fail(f"objectKinds missing required members {sorted(REQUIRED_OBJECT_KINDS - object_kinds)}")

    return dim_set, life_set, vert_set, object_kinds


def validate_icon_key_by_dimension(data: dict, dim_set: set[str]) -> None:
    """dimension → iconKey 末级回退闭集：键 ∈ dimensions、值 ∈ iconKeyLegend，且每维度都有回退。

    §23 去桥接：端 IntersectionIconResolver 与 inbox 归一层共用此唯一回退表，
    未登记 kind / affinity 概率类据此降级，禁止端各写一份 dimension switch。
    """
    fallback = data.get("iconKeyByDimension")
    if not isinstance(fallback, dict) or not fallback:
        fail("iconKeyByDimension must be a non-empty mapping")
    legend = data.get("iconKeyLegend")
    if not isinstance(legend, dict) or not legend:
        fail("iconKeyLegend must be a non-empty mapping")
    legend_keys = set(legend)
    for dim, icon_key in fallback.items():
        if dim not in dim_set:
            fail(f"iconKeyByDimension key {dim!r} not in dimensions closed set")
        if icon_key not in legend_keys:
            fail(f"iconKeyByDimension[{dim!r}] value {icon_key!r} not in iconKeyLegend closed set")
    missing = dim_set - set(fallback)
    if missing:
        fail(f"dimensions missing iconKeyByDimension fallback: {sorted(missing)}")


def load_registry() -> tuple[dict[str, dict], dict]:
    if not REGISTRY.exists():
        fail(f"missing registry: {REGISTRY}")
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    dim_set, _life_set, vert_set, object_kinds = load_closed_sets(data)
    validate_icon_key_by_dimension(data, dim_set)
    validate_action_labels(data)
    kinds = data.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        fail("registry.kinds must be a non-empty list")
    by_kind: dict[str, dict] = {}
    for item in kinds:
        for field in REQUIRED:
            if field not in item or item[field] in ("", None):
                fail(f"kind {item.get('kind', '?')} missing required field {field}")
        if item["valueTier"] not in VALUE_TIERS:
            fail(f"kind {item['kind']} invalid valueTier {item['valueTier']}")
        if item["computability"] not in COMPUTABILITY:
            fail(f"kind {item['kind']} invalid computability {item['computability']}")
        if item["level"] not in LEVELS:
            fail(f"kind {item['kind']} invalid level {item['level']}")
        if item["intersectionClass"] not in CLASSES:
            fail(f"kind {item['kind']} invalid intersectionClass {item['intersectionClass']}")
        if item["objectKind"] not in object_kinds:
            fail(f"kind {item['kind']} invalid objectKind {item['objectKind']} (not in objectKinds closed set)")
        count_object_kind = item.get("countObjectKind")
        if count_object_kind not in (None, "") and count_object_kind not in object_kinds:
            fail(
                f"kind {item['kind']} invalid countObjectKind {count_object_kind} "
                "(not in objectKinds closed set)"
            )
        dims = item["dimensions"]
        if not isinstance(dims, list) or not dims:
            fail(f"kind {item['kind']} dimensions must be a non-empty list")
        bad_dims = set(dims) - dim_set
        if bad_dims:
            fail(f"kind {item['kind']} dimensions {sorted(bad_dims)} not in dimensions closed set")
        if item["vertical"] not in vert_set:
            fail(f"kind {item['kind']} invalid vertical {item['vertical']} (not in verticals closed set)")
        if item["status"] not in STATUSES:
            fail(f"kind {item['kind']} invalid status {item['status']}")
        if not isinstance(item["evidenceRank"], int):
            fail(f"kind {item['kind']} evidenceRank must be int")
        if item["kind"] in by_kind:
            fail(f"duplicate kind {item['kind']}")
        by_kind[item["kind"]] = item
    return by_kind, data


def validate_action_labels(data: dict) -> None:
    """actionLabelByKey 键集必须 == actionHintLegend 键集（终端短标签 vs 词典描述同闭集）。"""
    legend = data.get("actionHintLegend")
    labels = data.get("actionLabelByKey")
    if not isinstance(legend, dict) or not legend:
        fail("actionHintLegend must be a non-empty mapping")
    if not isinstance(labels, dict) or not labels:
        fail("actionLabelByKey must be a non-empty mapping")
    only_legend = set(legend) - set(labels)
    only_labels = set(labels) - set(legend)
    if only_legend:
        fail(f"actionLabelByKey missing keys present in actionHintLegend: {sorted(only_legend)}")
    if only_labels:
        fail(f"actionLabelByKey has keys absent from actionHintLegend: {sorted(only_labels)}")


def _table_block(src: str, var_name: str, value_type: str) -> str:
    pat = rf"var {re.escape(var_name)} = map\[string\]{re.escape(value_type)}\{{(.*?)\n\}}"
    m = re.search(pat, src, re.S)
    if not m:
        fail(f"generated table missing var {var_name} (map[string]{value_type})")
    return m.group(1)


def parse_generated_table() -> dict[str, dict]:
    """解析 Go codegen 产物 intersection_kind_table.go 的各查表（§23 单一真相源下发）。"""
    if not GENERATED_TABLE.exists():
        fail(f"missing generated table: {GENERATED_TABLE} (run `make codegen-rec-intersection`)")
    src = GENERATED_TABLE.read_text(encoding="utf-8")

    evidence: dict[str, int] = {}
    for k, v in re.findall(r'"([^"]+)":\s*(\d+),', _table_block(src, "IntersectionEvidenceRank", "int")):
        evidence[k] = int(v)

    def parse_str_map(var_name: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in re.findall(r'"([^"]+)":\s*"([^"]*)",', _table_block(src, var_name, "string")):
            out[k] = v
        return out

    icon_by_kind = parse_str_map("IntersectionIconKeyByKind")
    icon_by_dim = parse_str_map("IntersectionIconKeyByDimension")
    route_by_obj = parse_str_map("IntersectionRouteIDByObjectKind")
    asset_by_obj = parse_str_map("IntersectionAssetKindByObjectKind")
    action_label = parse_str_map("IntersectionActionLabelByKey")
    # §24 M0：意图时态 / 行动阶梯 str 表。
    moment_by_kind = parse_str_map("IntersectionMomentByKind")
    action_tier = parse_str_map("IntersectionActionTierByKey")
    target_avail = parse_str_map("IntersectionActionTargetAvailabilityByKey")
    action_dispatch = parse_str_map("IntersectionActionDispatchByKey")

    def parse_action_keys(var_name: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        body = _table_block(src, var_name, "[]string")
        for k, raw in re.findall(r'"([^"]+)":\s*\{([^}]*)\},', body):
            out[k] = re.findall(r'"([^"]+)"', raw)
        return out

    def parse_slice_var(var_name: str) -> list[str]:
        m = re.search(rf"var {re.escape(var_name)} = \[\]string\{{([^}}]*)\}}", src)
        if not m:
            fail(f"generated table missing slice var {var_name} (run `make codegen-rec-intersection`)")
        return re.findall(r'"([^"]+)"', m.group(1))

    actions = parse_action_keys("IntersectionActionKeysByKind")
    required_gates = parse_action_keys("IntersectionRequiredGatesByActionKey")
    moments = parse_slice_var("IntersectionMoments")
    gate_keys = parse_slice_var("IntersectionGateKeys")
    feedback_kinds = parse_slice_var("IntersectionFeedbackKinds")
    action_dispatch_set = parse_slice_var("IntersectionActionDispatch")

    return {
        "evidenceRank": evidence,
        "iconKeyByKind": icon_by_kind,
        "iconKeyByDimension": icon_by_dim,
        "routeByObjectKind": route_by_obj,
        "assetByObjectKind": asset_by_obj,
        "actionKeysByKind": actions,
        "actionLabelByKey": action_label,
        "momentByKind": moment_by_kind,
        "actionTierByKey": action_tier,
        "targetAvailabilityByKey": target_avail,
        "dispatchByKey": action_dispatch,
        "requiredGatesByActionKey": required_gates,
        "moments": moments,
        "gateKeys": gate_keys,
        "feedbackKinds": feedback_kinds,
        "actionDispatch": action_dispatch_set,
    }


def expected_from_registry(by_kind: dict[str, dict], data: dict) -> dict[str, dict]:
    """从注册表派生「服务端 Go 表应当生成」的期望值（与生成器口径一致）。"""
    object_kinds = data.get("objectKinds") or []
    route = {
        ok["kind"]: ok["routeId"]
        for ok in object_kinds
        if str(ok.get("routeId", "")).strip()
    }
    asset = {
        ok["kind"]: ok["assetKind"]
        for ok in object_kinds
        if str(ok.get("assetKind", "")).strip()
    }
    action_meta = data.get("actionKeyMeta") or {}
    return {
        "evidenceRank": {k: v["evidenceRank"] for k, v in by_kind.items()},
        "iconKeyByKind": {k: v["iconKey"] for k, v in by_kind.items()},
        "iconKeyByDimension": dict(data.get("iconKeyByDimension") or {}),
        "routeByObjectKind": route,
        "assetByObjectKind": asset,
        "actionKeysByKind": {k: list(v) for k, v in (data.get("actionHintsByKind") or {}).items()},
        "actionLabelByKey": dict(data.get("actionLabelByKey") or {}),
        "momentByKind": {k: (v.get("moment") or "current") for k, v in by_kind.items()},
        "actionTierByKey": {k: v.get("tier", "") for k, v in action_meta.items()},
        "targetAvailabilityByKey": {k: v.get("targetAvailability", "") for k, v in action_meta.items()},
        "dispatchByKey": {k: v.get("dispatch", "") for k, v in action_meta.items()},
        "requiredGatesByActionKey": {k: list(v.get("requiredGates") or []) for k, v in action_meta.items()},
        "moments": list(data.get("moments") or []),
        "gateKeys": list(data.get("gateKeys") or []),
        "feedbackKinds": list(data.get("feedbackKinds") or []),
        "actionDispatch": list(data.get("actionDispatch") or []),
    }


def diff_field(name: str, expected: dict, actual: dict, problems: list[str]) -> None:
    for key in sorted(set(expected) | set(actual)):
        if key not in actual:
            problems.append(f"{name}: generated table missing key '{key}' (registry={expected[key]!r})")
        elif key not in expected:
            problems.append(f"{name}: generated table has unregistered key '{key}'={actual[key]!r}")
        elif expected[key] != actual[key]:
            problems.append(
                f"{name}: key '{key}' drift registry={expected[key]!r} generated={actual[key]!r}"
            )


def check_consumers_table_driven(problems: list[str]) -> None:
    """消费方必须查 generated.Intersection* 表，不得回归手写 kind switch。"""
    hydration_files = sorted(HYDRATION_PACKAGE.glob("intersection_hydration*.go"))
    if not SERVICE_GO.exists() or not hydration_files:
        problems.append("intersection_service.go / intersection_hydration*.go missing")
        return
    service = SERVICE_GO.read_text(encoding="utf-8")
    hydration = "\n".join(path.read_text(encoding="utf-8") for path in hydration_files)
    required = [
        (service, "generated.IntersectionEvidenceRank", "intersection_service.go evidenceKindRank"),
        (hydration, "generated.IntersectionIconKeyByKind", "intersection hydration iconKeyForKind"),
        (hydration, "generated.IntersectionIconKeyByDimension", "intersection hydration dimension fallback"),
        (hydration, "generated.IntersectionRouteIDByObjectKind", "intersection hydration routeIDForObjectKind"),
        (hydration, "generated.IntersectionAssetKindByObjectKind", "intersection hydration assetKindForObjectKind"),
        (hydration, "generated.IntersectionActionKeysByKind", "intersection hydration actionKeysForKind"),
        (hydration, "generated.IntersectionActionLabelByKey", "intersection hydration actionLabelForKey"),
    ]
    for src, token, where in required:
        if token not in src:
            problems.append(f"consumer not table-driven: {where} must consume {token}")


def main() -> int:
    by_kind, data = load_registry()
    expected = expected_from_registry(by_kind, data)
    actual = parse_generated_table()

    problems: list[str] = []
    for field in (
        "evidenceRank",
        "iconKeyByKind",
        "iconKeyByDimension",
        "routeByObjectKind",
        "assetByObjectKind",
        "actionKeysByKind",
        "actionLabelByKey",
        # §24 M0：意图时态 / 行动阶梯 map 表逐字段一致。
        "momentByKind",
        "actionTierByKey",
        "targetAvailabilityByKey",
        "dispatchByKey",
        "requiredGatesByActionKey",
    ):
        diff_field(field, expected[field], actual[field], problems)
    # §24 M0：闭集 slice（保序）一致。
    for field in ("moments", "gateKeys", "feedbackKinds", "actionDispatch"):
        if expected[field] != actual[field]:
            problems.append(
                f"{field}: registry={expected[field]!r} generated={actual[field]!r} (run `make codegen-rec-intersection`)"
            )
    check_consumers_table_driven(problems)

    if problems:
        for p in problems:
            print(f"[verify-intersection-kind-registry] FAIL: {p}")
        return 1

    print(
        f"[verify-intersection-kind-registry] OK: {len(by_kind)} kinds registered; "
        f"generated Go table aligned across evidenceRank/iconKey/iconKeyByDimension/route/asset/"
        f"actionKeys/actionLabel (single source = intersection_kind_registry.yaml)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

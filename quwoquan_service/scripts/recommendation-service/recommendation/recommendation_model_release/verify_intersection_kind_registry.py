#!/usr/bin/env python3
"""交集 kind 注册表单一真相源门禁。

唯一真相源:
  services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml

校验项:
  1. 顶层四闭集结构完整：dimensions / lifecycleStates / verticals / objectKinds 均非空，且包含
     必备成员（lifecycleStates 含 archived/expired，verticals 含 travel_photography，
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
  7. §23.4 垂类扩展契约：verticals 闭集中除 general 外每个垂类都必须在 verticalExtensionContract 登记
     objectKinds（⊆ objectKinds 闭集）/ taxonomyRoots / factProducers / instantiatedKinds（⊆ 已登记 kind）
     / newKinds；forbidNewKind 为真时 newKinds 必须为空，且任何 kind 名不得带垂类前缀（禁止 travel.* 私有 kind）。
  8. objectType→objectKind 单一真相源：objectTypeBindings 逐值登记且值 ∈ objectKinds 闭集，
     objectKinds 每项必填 dimension（∈ dimensions 闭集）与 label；生成表的 objectKindByObjectType /
     dimensionByObjectKind / labelByObjectKind 与注册表逐字段一致；且
     intersection_source_object_types.go 必须查这三张表，不得回归 objectID 子串/前缀嗅探。
  9. 垂类生产者必须引用本注册表 factProducerShapes；shape 明确输入、输出 kind/object/taxonomy
     与可见性，禁止自由文本生产者与 recommendation-only 事实回流成交集句。
 10. 每个 kind 必须逐项拥有唯一 statementTemplates.byKind 模板；结论句生产代码不得在展示字段
     重新写中文字面量，Dart cloud intersection 展示字段由 App semantic gate 同步扫描。
 11. 注册表禁止 migration/alias/deferred 状态；actionKeyMeta.dispatch 全部属于当前 actionDispatch 闭集。

退出码: 0 通过 / 1 失败。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
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
OBJECT_TYPES_GO = (
    REPO_ROOT
    / "quwoquan_service/services/content-service/internal/content/post/infrastructure"
    / "recommendation/intersection_source_object_types.go"
)

VALUE_TIERS = {"T1", "T2", "T3", "T4"}
COMPUTABILITY = {"R1", "R2", "R3"}
LEVELS = {"sharedFact", "bridgeFact", "impactFact", "affinity"}
CLASSES = {"fact", "affinity"}
OBJECT_KIND_ROLES = {"object", "count"}
PRODUCER_VISIBILITIES = {"intersection", "recommendation_only", "object_derivation"}
HAN_CHARACTER = re.compile(r"[\u3400-\u9fff]")
DISPLAY_FIELD_LITERAL = re.compile(
    r"\b(?:PrimaryText|DisplayText|ReasonText|StatementText)\s*(?::|=)\s*"
    r"(?:`[^`\n]*[\u3400-\u9fff][^`\n]*`|\"[^\"\n]*[\u3400-\u9fff][^\"\n]*\")"
)

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
REQUIRED_VERTICALS = {"general", "travel_photography"}
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
        # dimension/label 决定这类对象上的共享标签算哪个维度、缺展示名时怎么称呼
        # （同校 / 同游 / 同圈 / 同好）。缺任一个，服务端就只能回到手写 switch。
        dimension = str(item.get("dimension", "")).strip()
        if not dimension:
            fail(f"objectKind {kind} missing dimension")
        if dimension not in dim_set:
            fail(f"objectKind {kind} dimension {dimension} not in dimensions closed set")
        if not str(item.get("label", "")).strip():
            fail(f"objectKind {kind} missing label")
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


def validate_object_type_bindings(data: dict, object_kinds: set[str]) -> None:
    """objectType（开放词汇）→ objectKind（闭集）必须逐值登记，且落在闭集里。

    这层翻译过去是服务端和端上各一段手写 switch，只认 user/circle/homepage，
    其余垂类主页静默落 default 被当成人物：说成「同好」、点进去跳个人主页。
    登记在注册表后，新增垂类只改这份 YAML 并重跑 codegen，不必发 Go/Dart 版本。
    HomepageType 全集是否都有登记由 verify_homepage_type_contract.py 阻断。
    """
    bindings = data.get("objectTypeBindings")
    if not isinstance(bindings, list) or not bindings:
        fail("objectTypeBindings must be a non-empty list")
    seen: set[str] = set()
    for entry in bindings:
        if not isinstance(entry, dict):
            fail("objectTypeBindings entries must be mappings (objectType/objectKind)")
        object_type = str(entry.get("objectType", "")).strip()
        object_kind = str(entry.get("objectKind", "")).strip()
        if not object_type:
            fail("objectTypeBindings entry missing objectType")
        if object_type in seen:
            fail(f"duplicate objectTypeBindings entry for objectType {object_type}")
        seen.add(object_type)
        if object_kind not in object_kinds:
            fail(
                f"objectTypeBindings[{object_type}] objectKind {object_kind!r} "
                "not in objectKinds closed set"
            )


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
    raw = REGISTRY.read_text(encoding="utf-8")
    if re.search(r"\bdeferred\b", raw, flags=re.IGNORECASE):
        fail("canonical registry retains deferred vocabulary")
    if re.search(r"^\s+status\s*:", raw, flags=re.MULTILINE):
        fail("canonical registry retains redundant status tracks")
    data = yaml.safe_load(raw)
    dim_set, _life_set, vert_set, object_kinds = load_closed_sets(data)
    validate_icon_key_by_dimension(data, dim_set)
    validate_object_type_bindings(data, object_kinds)
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
        if not isinstance(item["evidenceRank"], int):
            fail(f"kind {item['kind']} evidenceRank must be int")
        if item["kind"] in by_kind:
            fail(f"duplicate kind {item['kind']}")
        by_kind[item["kind"]] = item
    validate_vertical_extension_contract(data, vert_set, object_kinds, set(by_kind))
    validate_single_track_registry(data)
    return by_kind, data


def validate_single_track_registry(data: dict) -> None:
    """当前注册表只允许可生产、可承接的单轨名称。"""
    for retired in (
        "migrations",
        "actionKeyMigrations",
        "objectKindMigrations",
        "actionDispatchMigrations",
    ):
        if retired in data:
            fail(f"{retired} is forbidden: rename migrations must finish outside the canonical registry")

    dispatch_set = set(data.get("actionDispatch") or [])
    for key, meta in sorted((data.get("actionKeyMeta") or {}).items()):
        dispatch = (meta or {}).get("dispatch")
        if dispatch not in dispatch_set:
            fail(
                f"actionKeyMeta[{key}].dispatch {dispatch!r} not in actionDispatch closed set "
                f"{sorted(dispatch_set)}"
            )


def validate_vertical_extension_contract(
    data: dict, vert_set: set[str], object_kinds: set[str], registered_kinds: set[str]
) -> None:
    """§23.4 垂类扩展契约：垂类只能靠 vertical + objectKind + taxonomy 子树 + 事实生产者扩展。

    这条契约把「垂类差异化只体现在事实丰富度、不体现在结构分叉」变成可执行门禁：
    新增 kind / dimension / actionKey / 端侧垂类分支都在此被阻断。
    """
    contract = data.get("verticalExtensionContract")
    if not isinstance(contract, dict) or not contract:
        fail("verticalExtensionContract must be a non-empty mapping (§23.4 垂类扩展契约)")
    for flag in ("forbidNewKind", "forbidNewDimension", "forbidNewActionKey", "forbidClientVerticalBranch"):
        if contract.get(flag) is not True:
            fail(f"verticalExtensionContract.{flag} must be true (§23.4 禁止垂类结构分叉)")

    producer_shapes = validate_fact_producer_shapes(
        data,
        object_kinds=object_kinds,
        registered_kinds=registered_kinds,
    )

    declared = contract.get("verticals")
    if not isinstance(declared, dict) or not declared:
        fail("verticalExtensionContract.verticals must be a non-empty mapping")

    expected_verticals = vert_set - {"general"}
    missing = expected_verticals - set(declared)
    if missing:
        fail(f"verticalExtensionContract.verticals missing entries for {sorted(missing)}")
    extra = set(declared) - expected_verticals
    if extra:
        fail(f"verticalExtensionContract.verticals has entries absent from verticals closed set: {sorted(extra)}")

    for name, entry in sorted(declared.items()):
        if not isinstance(entry, dict):
            fail(f"verticalExtensionContract.verticals[{name}] must be a mapping")
        for field in ("objectKinds", "taxonomyRoots", "factProducers", "instantiatedKinds", "newKinds"):
            if not isinstance(entry.get(field), list):
                fail(f"verticalExtensionContract.verticals[{name}].{field} must be a list")
        bad_objects = set(entry["objectKinds"]) - object_kinds
        if bad_objects:
            fail(
                f"verticalExtensionContract.verticals[{name}].objectKinds {sorted(bad_objects)} "
                "not in objectKinds closed set (垂类 objectKind 必须映射到已有对象)"
            )
        if not entry["objectKinds"]:
            fail(f"verticalExtensionContract.verticals[{name}].objectKinds must be non-empty")
        if not entry["taxonomyRoots"]:
            fail(f"verticalExtensionContract.verticals[{name}].taxonomyRoots must be non-empty")
        unknown_producers = set(entry["factProducers"]) - set(producer_shapes)
        if unknown_producers:
            fail(
                f"verticalExtensionContract.verticals[{name}].factProducers references "
                f"unknown factProducerShapes {sorted(unknown_producers)}"
            )
        for producer_id in entry["factProducers"]:
            output_kinds = set(producer_shapes[producer_id]["outputKinds"])
            undeclared_outputs = output_kinds - set(entry["instantiatedKinds"])
            if undeclared_outputs:
                fail(
                    f"verticalExtensionContract.verticals[{name}].factProducer {producer_id!r} "
                    f"outputs kinds absent from instantiatedKinds: {sorted(undeclared_outputs)}"
                )
        bad_kinds = set(entry["instantiatedKinds"]) - registered_kinds
        if bad_kinds:
            fail(
                f"verticalExtensionContract.verticals[{name}].instantiatedKinds {sorted(bad_kinds)} "
                "not registered in kinds"
            )
        if not entry["instantiatedKinds"]:
            fail(
                f"verticalExtensionContract.verticals[{name}].instantiatedKinds must be non-empty "
                "(垂类必须复用既有通用 kind，而不是新造 kind)"
            )
        if entry["newKinds"]:
            fail(
                f"verticalExtensionContract.verticals[{name}].newKinds must be empty while "
                f"forbidNewKind=true (禁止垂类专有 kind: {sorted(entry['newKinds'])})"
            )

    # 垂类专有 kind 的另一种伪装：把垂类名写进 kind 名。
    for prefix in sorted(expected_verticals):
        head = prefix.split("_", 1)[0].lower()
        offenders = sorted(k for k in registered_kinds if k.lower().startswith(head))
        if offenders:
            fail(
                f"kind name must not carry vertical prefix {head!r}: {offenders} "
                "(§23.4 垂类扩展只改 vertical 字段，禁止独立垂类 kind)"
            )


def validate_fact_producer_shapes(
    data: dict,
    *,
    object_kinds: set[str],
    registered_kinds: set[str],
) -> dict[str, dict]:
    """生产者 shape 与交集/推荐/对象派生输出保持互斥且可静态验证。"""
    shapes = data.get("factProducerShapes")
    if not isinstance(shapes, dict) or not shapes:
        fail("factProducerShapes must be a non-empty mapping")
    required = {
        "visibility",
        "inputRefs",
        "outputKinds",
        "outputObjectKinds",
        "outputTaxonomyRoots",
    }
    for producer_id, shape in sorted(shapes.items()):
        if not isinstance(shape, dict):
            fail(f"factProducerShapes[{producer_id}] must be a mapping")
        missing = required - set(shape)
        if missing:
            fail(f"factProducerShapes[{producer_id}] missing fields {sorted(missing)}")
        visibility = shape["visibility"]
        if visibility not in PRODUCER_VISIBILITIES:
            fail(f"factProducerShapes[{producer_id}].visibility invalid: {visibility!r}")
        for field in ("inputRefs", "outputKinds", "outputObjectKinds", "outputTaxonomyRoots"):
            if not isinstance(shape[field], list):
                fail(f"factProducerShapes[{producer_id}].{field} must be a list")
        if not shape["inputRefs"]:
            fail(f"factProducerShapes[{producer_id}].inputRefs must be non-empty")
        unknown_kinds = set(shape["outputKinds"]) - registered_kinds
        if unknown_kinds:
            fail(f"factProducerShapes[{producer_id}] outputs unknown kinds {sorted(unknown_kinds)}")
        unknown_objects = set(shape["outputObjectKinds"]) - object_kinds
        if unknown_objects:
            fail(
                f"factProducerShapes[{producer_id}] outputs unknown objectKinds "
                f"{sorted(unknown_objects)}"
            )
        if visibility == "intersection" and not shape["outputKinds"]:
            fail(f"factProducerShapes[{producer_id}] intersection producer must output kinds")
        if visibility != "intersection" and shape["outputKinds"]:
            fail(
                f"factProducerShapes[{producer_id}] {visibility} producer must not output intersection kinds"
            )
        if visibility == "recommendation_only" and not shape["outputTaxonomyRoots"]:
            fail(
                f"factProducerShapes[{producer_id}] recommendation_only producer must output taxonomy roots"
            )
        if visibility == "object_derivation" and not shape["outputObjectKinds"]:
            fail(
                f"factProducerShapes[{producer_id}] object_derivation producer must output objectKinds"
            )
    return shapes


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


def _snake_case(value: str) -> str:
    result: list[str] = []
    for index, character in enumerate(value):
        if "A" <= character <= "Z":
            if index > 0:
                result.append("_")
            result.append(character.lower())
        else:
            result.append(character)
    return "".join(result)


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

    def parse_text_map(var_name: str) -> tuple[dict[str, str], dict[str, str]]:
        text_by_key: dict[str, str] = {}
        l10n_key_by_key: dict[str, str] = {}
        body = _table_block(src, var_name, "IntersectionText")
        for key, text, l10n_key in re.findall(
            r'"([^"]+)":\s*\{Text:\s*"([^"]*)",\s*L10nKey:\s*"([^"]*)"\},',
            body,
        ):
            text_by_key[key] = text
            l10n_key_by_key[key] = l10n_key
        return text_by_key, l10n_key_by_key

    icon_by_kind = parse_str_map("IntersectionIconKeyByKind")
    icon_by_dim = parse_str_map("IntersectionIconKeyByDimension")
    route_by_obj = parse_str_map("IntersectionRouteIDByObjectKind")
    asset_by_obj = parse_str_map("IntersectionAssetKindByObjectKind")
    dimension_by_obj = parse_str_map("IntersectionDimensionByObjectKind")
    label_by_obj = parse_str_map("IntersectionLabelByObjectKind")
    kind_by_object_type = parse_str_map("IntersectionObjectKindByObjectType")
    action_label, action_label_l10n_key = parse_text_map("IntersectionActionLabelByKey")
    # §24 M0：意图时态 / 行动阶梯 str 表。
    moment_by_kind = parse_str_map("IntersectionMomentByKind")
    action_tier = parse_str_map("IntersectionActionTierByKey")
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
        "dimensionByObjectKind": dimension_by_obj,
        "labelByObjectKind": label_by_obj,
        "objectKindByObjectType": kind_by_object_type,
        "actionKeysByKind": actions,
        "actionLabelByKey": action_label,
        "actionLabelL10nKeyByKey": action_label_l10n_key,
        "momentByKind": moment_by_kind,
        "actionTierByKey": action_tier,
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
    dimension = {ok["kind"]: ok.get("dimension", "") for ok in object_kinds}
    label = {ok["kind"]: ok.get("label", "") for ok in object_kinds}
    binding = {
        entry["objectType"]: entry["objectKind"]
        for entry in (data.get("objectTypeBindings") or [])
        if isinstance(entry, dict)
    }
    action_meta = data.get("actionKeyMeta") or {}
    action_labels = dict(data.get("actionLabelByKey") or {})
    action_label_prefix = str(data.get("actionLabelL10nKeyPrefix") or "").strip()
    return {
        "evidenceRank": {k: v["evidenceRank"] for k, v in by_kind.items()},
        "iconKeyByKind": {k: v["iconKey"] for k, v in by_kind.items()},
        "iconKeyByDimension": dict(data.get("iconKeyByDimension") or {}),
        "routeByObjectKind": route,
        "assetByObjectKind": asset,
        "dimensionByObjectKind": dimension,
        "labelByObjectKind": label,
        "objectKindByObjectType": binding,
        "actionKeysByKind": {k: list(v) for k, v in (data.get("actionHintsByKind") or {}).items()},
        "actionLabelByKey": action_labels,
        "actionLabelL10nKeyByKey": {
            key: f"{action_label_prefix}.{_snake_case(key)}"
            for key in action_labels
        },
        "momentByKind": {k: (v.get("moment") or "current") for k, v in by_kind.items()},
        "actionTierByKey": {k: v.get("tier", "") for k, v in action_meta.items()},
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


STATEMENT_VARIANTS = ("personPlace", "noObject", "circleTag")


def validate_statement_templates(data: dict, by_kind: dict[str, dict], problems: list[str]) -> int:
    """结论句模板必须齐备、槽位合法、l10nKey 唯一，且与生成表逐字对齐。

    模板是文案的唯一真相源：缺 l10nKey 就等于「改一句话必须改代码 + 发服务」，
    槽位越界会把 `{foo}` 原样播给用户，因此两者都按阻断处理。
    """
    st = data.get("statementTemplates")
    if not isinstance(st, dict) or not st.get("byKind"):
        problems.append("statementTemplates.byKind missing (§17.1 结论句模板真相源)")
        return 0
    slots = set(st.get("slots") or [])
    if not slots:
        problems.append("statementTemplates.slots closed set is empty")
        return 0
    src = GENERATED_TABLE.read_text(encoding="utf-8") if GENERATED_TABLE.exists() else ""
    seen_keys: dict[str, str] = {}
    count = 0
    missing_kinds = set(by_kind) - set(st["byKind"])
    if missing_kinds:
        problems.append(
            "statementTemplates.byKind missing kinds "
            f"{sorted(missing_kinds)}（canonical kind 不得依赖代码内兜底文案）"
        )

    def check_one(owner: str, template: str, l10n_key: str) -> None:
        nonlocal count
        count += 1
        if not template:
            problems.append(f"statementTemplates {owner}: empty template")
            return
        if not l10n_key:
            problems.append(f"statementTemplates {owner}: missing l10nKey（文案无法脱离发版本地化）")
        elif l10n_key in seen_keys:
            problems.append(
                f"statementTemplates {owner}: l10nKey {l10n_key!r} 与 {seen_keys[l10n_key]} 重复"
            )
        else:
            seen_keys[l10n_key] = owner
        for slot in re.findall(r"\{([^}]*)\}", template):
            if slot not in slots:
                problems.append(f"statementTemplates {owner}: slot {slot!r} 不在 slots 闭集")
        # 生成表必须逐字带上模板与 key，否则服务端渲染的还是旧文案。
        if src and (template not in src or (l10n_key and l10n_key not in src)):
            problems.append(
                f"statementTemplates {owner}: generated table 缺模板或 l10nKey"
                "（run `make codegen-rec-intersection`）"
            )

    for kind, form in sorted(st["byKind"].items()):
        if kind not in by_kind:
            problems.append(f"statementTemplates 登记了未注册 kind {kind!r}")
        if not isinstance(form, dict):
            problems.append(f"statementTemplates {kind}: entry must be a mapping")
            continue
        template = str(form.get("template") or "").strip()
        check_one(kind, template, str(form.get("l10nKey") or "").strip())
        if "{action}" in template and not str(form.get("actionFallback") or "").strip():
            problems.append(f"statementTemplates {kind}: 用了 {{action}} 却没有 actionFallback")
        counted = form.get("counted")
        if isinstance(counted, dict):
            check_one(
                f"{kind}.counted",
                str(counted.get("template") or "").strip(),
                str(counted.get("l10nKey") or "").strip(),
            )
        variants = form.get("variants") or {}
        for name, variant in sorted(variants.items()):
            if name not in STATEMENT_VARIANTS:
                problems.append(
                    f"statementTemplates {kind}: variant {name!r} 不在闭集 {list(STATEMENT_VARIANTS)}"
                )
            if isinstance(variant, dict):
                check_one(
                    f"{kind}.{name}",
                    str(variant.get("template") or "").strip(),
                    str(variant.get("l10nKey") or "").strip(),
                )
    return count


def check_statements_template_driven(problems: list[str]) -> None:
    """结论句只能由注册表模板渲染：hydration 不得再手写中文句式。

    此前谓语在 ExplainPrimaryText 与 primaryStatementSpansForReason 各写一份，
    改文案要改两处代码；这里静态阻断回归。
    """
    files = sorted(HYDRATION_PACKAGE.glob("intersection_hydration*.go")) + sorted(
        HYDRATION_PACKAGE.glob("intersection_statement_template.go")
    )
    if not files:
        problems.append("intersection hydration/statement sources missing")
        return
    sources = {path.name: path.read_text(encoding="utf-8") for path in files}
    joined = "\n".join(sources.values())
    if "generated.IntersectionStatementFormByKind" not in joined:
        problems.append(
            "consumer not table-driven: 结论句渲染必须消费 generated.IntersectionStatementFormByKind"
        )
    # 禁止在 hydration 里重新出现「按 kind 拼中文谓语」的句式片段。
    banned = ("也关注了", "都加入了", "都点赞过", "都去过", "都想去", "都讨论过", "都转发过", "也看过")
    for name, src in sources.items():
        for line in src.splitlines():
            code = line.split("//", 1)[0]
            if any(phrase in code for phrase in banned):
                problems.append(
                    f"hardcoded statement copy in {name}: {line.strip()!r}"
                    "（文案真相源是 registry.statementTemplates）"
                )

    # 所有 content-service 交集生产/投影源码都不得直接给展示字段写中文。
    # 只扫 production Go，测试与 fixture 文案仍由各自 contract fixture 管理。
    producer_roots = (
        HYDRATION_PACKAGE,
        HYDRATION_PACKAGE.parent / "authorimpact",
        HYDRATION_PACKAGE.parent.parent / "infrastructure" / "recommendation",
    )
    for root in producer_roots:
        if not root.exists():
            problems.append(f"intersection producer root missing: {root}")
            continue
        for path in sorted(root.rglob("*.go")):
            if path.name.endswith("_test.go"):
                continue
            src = path.read_text(encoding="utf-8")
            for match in DISPLAY_FIELD_LITERAL.finditer(src):
                line_no = src.count("\n", 0, match.start()) + 1
                problems.append(
                    f"hardcoded Han display literal in {path.relative_to(REPO_ROOT)}:{line_no}: "
                    f"{match.group(0)!r}（展示句必须来自 registry 模板或结构化事实）"
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
    check_object_type_translation_table_driven(problems)


def check_object_type_translation_table_driven(problems: list[str]) -> None:
    """objectType 翻译层必须查表，且不得靠 objectID 子串反推类型。

    这层原本是三段手写 switch 加一段 objectID 嗅探（`strings.Contains(id, "_university_")`、
    `strings.HasPrefix(id, "fixture_homepage_poi")`）。它把注册表之外的知识写进了服务代码：
    加一个垂类要发版，改一次 ID 命名就静默改语义，fixture 前缀还渗进了生产判定。
    """
    if not OBJECT_TYPES_GO.exists():
        problems.append(f"missing {OBJECT_TYPES_GO.name}")
        return
    src = OBJECT_TYPES_GO.read_text(encoding="utf-8")
    for token in (
        "generated.IntersectionObjectKindByObjectType",
        "generated.IntersectionDimensionByObjectKind",
        "generated.IntersectionLabelByObjectKind",
    ):
        if token not in src:
            problems.append(
                f"consumer not table-driven: {OBJECT_TYPES_GO.name} must consume {token}"
            )
    for banned, why in (
        ("strings.Contains(id", "objectID 子串嗅探"),
        ("strings.HasPrefix(id", "objectID 前缀嗅探"),
        ("fixture_", "fixture 前缀渗入生产判定"),
    ):
        if banned in src:
            problems.append(
                f"{OBJECT_TYPES_GO.name} reintroduces {why}: {banned!r}; "
                "objectType 只能来自调用方并经注册表 objectTypeBindings 查表"
            )


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
        # objectType→objectKind→dimension/label：交集侧对象语义的唯一真相源。
        "dimensionByObjectKind",
        "labelByObjectKind",
        "objectKindByObjectType",
        "actionKeysByKind",
        "actionLabelByKey",
        "actionLabelL10nKeyByKey",
        # §24 M0：意图时态 / 行动阶梯 map 表逐字段一致。
        "momentByKind",
        "actionTierByKey",
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
    statement_count = validate_statement_templates(data, by_kind, problems)
    check_statements_template_driven(problems)

    if problems:
        for p in problems:
            print(f"[verify-intersection-kind-registry] FAIL: {p}")
        return 1

    print(
        f"[verify-intersection-kind-registry] OK: {len(by_kind)} kinds registered; "
        f"generated Go table aligned across evidenceRank/iconKey/iconKeyByDimension/route/asset/"
        f"actionKeys/actionLabel; {statement_count} statement templates carry l10nKey "
        f"(single source = intersection_kind_registry.yaml)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

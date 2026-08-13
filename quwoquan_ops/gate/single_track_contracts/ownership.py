"""退役领域身份字段的对象归属判定：只认 ContractGraph 与 contracts 结构。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

from .constants import ROOT
from .heuristics import _is_external_provider_path

#: scope -> ContractGraph 对象 id。归属只认 ContractGraph 声明，不维护第二份台账；
#: 对象不存在时 `_scope_object_segments` 会直接抛错，禁止悄悄退化成永不命中。
RETIRED_DOMAIN_IDENTITY_OBJECTS = {
    "assistant_policy_release": "assistant.assistant_policy_release",
    "product_ops_experiment_assignment": "ops.experiment_assignment_fact",
    "assistant_learning_fact": "assistant.assistant_learning_fact",
}
CONTRACT_GRAPH_PATH = ROOT / "quwoquan_service/generated/contract_graph.json"
#: 对象 contracts 源目录的物理布局。`object.yaml` 的父目录是对象，祖父目录是
#: bounded context，与 ContractGraph `sourcePath` 的 `<domain>/<context>/<object>`
#: 是同一条布局不变量。这里用固定根（导入时求值），测试替换 `ROOT` 时不受影响。
CONTRACT_OBJECT_DIR_GLOBS = (
    "services/*/contracts/*/*/object.yaml",
    "control-plane/*/contracts/*/*/object.yaml",
    "contracts/metadata/*/*/object.yaml",
)
CONTRACT_OBJECT_SOURCE_ROOT = ROOT / "quwoquan_service"
#: `recommendation_content_identity` 收口后的 canonical 单轨身份字段。模型与特征
#: 身份只由 `modelReleaseId` + `featureContractDigest` 表达，`modelVersion` /
#: `featureVersion` / `featureContractVersion` 是被它们取代的第二轨。
#: 谁在自己的 contracts 里声明了 canonical 身份，谁就承载这条身份，也就落在
#: 单轨范围内——这是从 contracts 结构派生的归属事实。
RECOMMENDATION_CANONICAL_IDENTITY_FIELDS = frozenset(
    {"modelReleaseId", "featureContractDigest"}
)
#: YAML 里承载自然语言、与标识符恒不相等的键；解析后按值排除，避免把散文当声明。
CONTRACT_PROSE_KEYS = frozenset(
    {"description", "doc", "summary", "note", "notes", "rationale", "reason"}
)


@lru_cache(maxsize=1)
def _contract_graph_object_segments() -> dict[str, tuple[str, str]]:
    """对象 id -> (bounded context, 对象目录名)，来自 ContractGraph `sourcePath`。

    `sourcePath` 形如 `<domain>/<context>/<object>/object.yaml`；contracts、internal、
    tests 与端侧目标形态四种物理布局都把 `<context>/<object>` 作为连续目录段，
    这与 `object_path_map.derive_cloud_source_identity` /
    `derive_app_target_shape_identity` 编码的是同一条布局不变量。
    """
    try:
        payload = json.loads(CONTRACT_GRAPH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"[single-track] 无法读取 ContractGraph: {error}") from error
    segments: dict[str, tuple[str, str]] = {}
    for record in payload.get("objects", []):
        source_path = str(record.get("sourcePath", ""))
        parts = source_path.split("/")
        if len(parts) < 4:
            continue
        segments[str(record.get("id", ""))] = (parts[1], parts[2])
    return segments


def _scope_object_segments(scope: str) -> tuple[str, str]:
    object_id = RETIRED_DOMAIN_IDENTITY_OBJECTS[scope]
    segments = _contract_graph_object_segments().get(object_id)
    if segments is None:
        raise SystemExit(
            f"[single-track] scope {scope!r} 声明的对象 {object_id!r} 不在 ContractGraph 中；"
            "先修对象归属，不要让门禁静默失效"
        )
    return segments


def _path_owns_segments(rel: str, segments: tuple[str, str]) -> bool:
    context, object_name = segments
    parts = rel.split("/")
    return any(
        parts[index] == context and parts[index + 1] == object_name
        for index in range(len(parts) - 1)
    )


def _path_owns_object(rel: str, scope: str) -> bool:
    """文件是否落在该对象自己的领地内，由 ContractGraph 归属判定，不看上下文文本。"""
    return _path_owns_segments(rel, _scope_object_segments(scope))


@lru_cache(maxsize=1)
def _contract_object_source_dirs() -> dict[tuple[str, str], Path]:
    """(bounded context, 对象目录名) -> 该对象 contracts 源目录。"""
    dirs: dict[tuple[str, str], Path] = {}
    for pattern in CONTRACT_OBJECT_DIR_GLOBS:
        for object_yaml in CONTRACT_OBJECT_SOURCE_ROOT.glob(pattern):
            directory = object_yaml.parent
            dirs[(directory.parent.name, directory.name)] = directory
    return dirs


def _yaml_declared_identifiers(node: object) -> set[str]:
    """YAML 文档里作为「声明」出现的标识符：映射键、非散文标量、列表项标量。

    输入是 `yaml.safe_load` 的解析结果，注释在这一步已经不存在，因此注释里的
    否认句、示例和 prose 都无法冒充声明。散文键（description 等）的值按键名排除。
    """
    declared: set[str] = set()
    if isinstance(node, dict):
        for raw_key, child in node.items():
            key = str(raw_key)
            declared.add(key)
            if key in CONTRACT_PROSE_KEYS:
                continue
            declared |= _yaml_declared_identifiers(child)
    elif isinstance(node, list):
        for child in node:
            declared |= _yaml_declared_identifiers(child)
    elif isinstance(node, str):
        declared.add(node)
    return declared


def _object_declares_identifiers(directory: Path, wanted: frozenset[str]) -> bool:
    for contract_yaml in sorted(directory.rglob("*.yaml")):
        try:
            raw = contract_yaml.read_text(encoding="utf-8")
        except OSError as error:
            raise SystemExit(
                f"[single-track] 无法读取对象契约 {contract_yaml}: {error}"
            ) from error
        # 纯性能预筛：字节里根本没有该标识符时，解析后也不可能有该节点。
        # 判定本身仍由下面的解析结果给出，出现在注释里不算声明。
        if not any(name in raw for name in wanted):
            continue
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as error:
            raise SystemExit(
                f"[single-track] 无法解析对象契约 {contract_yaml}: {error}"
            ) from error
        if _yaml_declared_identifiers(document) & wanted:
            return True
    return False


@lru_cache(maxsize=1)
def _recommendation_identity_object_segments() -> tuple[tuple[str, str], ...]:
    """承载 recommendation canonical 模型身份的全部对象领地。

    归属由两个结构事实合成，都不依赖命中行附近的自由文本：

    1. ContractGraph 声明了哪些对象、以及每个对象的 `<context>/<object>` 布局；
    2. 对象自己的 `contracts/**.yaml` 是否在解析后的键/标量位置声明了
       `modelReleaseId` 或 `featureContractDigest`。

    这样一来，新对象一旦承载 canonical 身份就自动进入范围，跨服务消费者
    （如 content.feed_delivery_page）也不再依赖「附近有没有提到推荐对象名」。
    """
    dirs = _contract_object_source_dirs()
    segments: set[tuple[str, str]] = set()
    for object_segments in _contract_graph_object_segments().values():
        directory = dirs.get(object_segments)
        if directory is None:
            continue
        if _object_declares_identifiers(
            directory,
            RECOMMENDATION_CANONICAL_IDENTITY_FIELDS,
        ):
            segments.add(object_segments)
    if not segments:
        raise SystemExit(
            "[single-track] 没有任何 ContractGraph 对象声明 "
            f"{sorted(RECOMMENDATION_CANONICAL_IDENTITY_FIELDS)}；"
            "recommendation 单轨身份的归属已失真，先修契约，"
            "不要让门禁静默退化成永不命中"
        )
    return tuple(sorted(segments))


def _retired_domain_identity_applies(scope: str, rel: str) -> bool:
    """Match retired fields only inside the first-party object that retired them.

    归属只由文件位置与 contracts 结构决定；命中行附近写了什么与判定无关。
    """
    if _is_external_provider_path(rel):
        return False
    rel_lower = rel.lower()

    if scope == "assistant_policy_release":
        return (
            rel_lower.startswith(
                "quwoquan_service/services/assistant-service/"
            )
            or rel_lower.startswith(
                "specs/feature-tree/assistant-run-learning/"
            )
            or (
                rel_lower.startswith("quwoquan_app/")
                and "/assistant/" in rel_lower
            )
            or _path_owns_object(rel, scope)
        )
    if scope == "product_ops_experiment_assignment":
        return (
            rel_lower.startswith(
                "quwoquan_service/services/product-ops-service/"
            )
            or rel_lower.startswith(
                "specs/feature-tree/product-operations/"
            )
            or _path_owns_object(rel, scope)
        )
    if scope == "recommendation_content_identity":
        return (
            rel_lower.startswith(
                "quwoquan_service/services/recommendation-service/"
            )
            or rel_lower.startswith("quwoquan_service/runtime/recommendation/")
            or rel_lower.startswith("quwoquan_service/runtime/recpolicy/")
            or (
                rel_lower.startswith("quwoquan_app/")
                and "recommendation" in rel_lower
            )
            or (
                rel_lower.startswith("specs/feature-tree/")
                and "recommend" in rel_lower
            )
            or rel_lower.endswith("/l3_rec_model.json")
            # 本 scope 没有单一权威对象，但它有单一权威身份：承载 canonical
            # `modelReleaseId` / `featureContractDigest` 的对象集合。归属因此从
            # contracts 结构派生，而不是看命中行附近提到了哪个名字。
            or any(
                _path_owns_segments(rel, segments)
                for segments in _recommendation_identity_object_segments()
            )
        )
    if scope == "assistant_learning_fact":
        return (
            "assistant_learning_fact" in rel_lower
            or "/assistant/learning/" in rel_lower
            or rel_lower.startswith(
                "specs/feature-tree/assistant-run-learning/"
                "learning-event-feedback-injection/"
            )
            or _path_owns_object(rel, scope)
        )
    return False

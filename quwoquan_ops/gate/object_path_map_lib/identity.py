"""端云物理路径 → 身份/层/目标路径的派生函数族。"""
from __future__ import annotations

from typing import Sequence

from .constants import (
    APP_CROSS_CUTTING_ROOTS,
    APP_CROSS_CUTTING_SEGMENTS,
    APP_CROSS_CUTTING_STRIPPED_PREFIXES,
    APP_CROSS_OBJECT_JOURNEY_ROOT,
    APP_CROSS_OBJECT_JOURNEY_TEST_LAYERS,
    APP_COMPOSITION_ROOT_SEGMENT,
    APP_DESIGN_SYSTEM_SEGMENTS,
    APP_ENTRY_FILE_RE,
    APP_LAYERS,
    APP_LAYER_ALIASES,
    APP_LAYER_BY_SEGMENT,
    APP_LIB_ROOT,
    APP_PATROL_RUNNER_FILES,
    APP_PATROL_RUNNER_LAYER,
    APP_PATROL_RUNNER_ROOT,
    APP_ROOT,
    APP_SERVICE_ROOT_SEGMENT,
    APP_SOURCE_SUFFIX,
    APP_TARGET_SHAPE_SEGMENTS,
    APP_TEST_ROOT,
    APP_TEST_TARGET_SHAPE_SEGMENTS,
    CLOUD_LAYERS,
    CLOUD_TEST_LAYERS,
)
from .roster import ObjectRoster
# app_service_for_context 经 topology 模块属性访问：canonical_coverage 契约测试
# 会 monkeypatch 该函数，from-import 固化绑定会让 patch 打不进派生链。
from . import topology

# ---------------------------------------------------------------------------
# 云侧身份派生（物理路径可唯一反推，无启发式）
# ---------------------------------------------------------------------------


def derive_cloud_source_identity(
    relative_parts: Sequence[str],
) -> tuple[str, str, str] | None:
    """从 ``internal/<context>/<object>/<layer>/...`` 反推 ``(context, object, layer)``。

    与 verify_service_architecture.py 的 production 源扫描同形：层必须是
    ``CLOUD_LAYERS`` 之一，否则视为不可反推。
    """
    if len(relative_parts) < 4:
        return None
    context, object_name, layer = relative_parts[0], relative_parts[1], relative_parts[2]
    if layer not in CLOUD_LAYERS:
        return None
    return context, object_name, layer


def derive_cloud_test_identity(
    relative_parts: Sequence[str],
) -> tuple[str, str, str] | None:
    """从 ``tests/<layer>/<context>/<object>/...`` 反推 ``(test_layer, context, object)``。"""
    if len(relative_parts) < 3:
        return None
    test_layer, context, object_name = (
        relative_parts[0],
        relative_parts[1],
        relative_parts[2],
    )
    if test_layer not in CLOUD_TEST_LAYERS:
        return None
    return test_layer, context, object_name


# ---------------------------------------------------------------------------
# 端侧目标形态识别（精确反推，派生幂等的唯一依据）
# ---------------------------------------------------------------------------


def derive_app_target_shape_identity(
    relative_parts: Sequence[str],
    roster: ObjectRoster,
) -> tuple[str, str, str, str] | None:
    """从 ``service/<service>/<context>/<object>/<layer>/...`` 精确反推身份。

    与 ``derive_cloud_source_identity`` 同性质：service/context 必须由云侧
    ``contracts/domain.yaml`` 与 context 物理目录共同证明，对象必须命中
    ContractGraph roster，第五段必须是 ``APP_LAYERS`` 之一。层内允许可选子路径
    （``presentation/widgets/``、``adapters/remote/``），子路径不参与身份判定。

    命中即代表该文件**已经处于目标形态**，此时任何基于旧命名的启发式都必须让位：
    否则 ``post/presentation/comment/x.dart`` 会被深层段 ``comment`` 劫持成
    ``content.comment``，``presentation/providers/`` 会被改判成 application。
    """
    if len(relative_parts) <= APP_TARGET_SHAPE_SEGMENTS:
        return None
    service_root, service, context, object_name, layer = relative_parts[
        :APP_TARGET_SHAPE_SEGMENTS
    ]
    if service_root != APP_SERVICE_ROOT_SEGMENT:
        return None
    if layer not in APP_LAYERS:
        return None
    context_ids = roster.contexts_by_name.get(context) or set()
    if len(context_ids) != 1:
        return None
    domain = next(iter(context_ids)).split(".", 1)[0]
    try:
        expected_service = topology.app_service_for_context(domain, context)
    except ValueError:
        return None
    if service != expected_service:
        return None
    if (domain, context, object_name) not in roster.by_key:
        return None
    return domain, context, object_name, layer


def derive_page_physical_owner(
    repository_relative_path: str,
    roster: ObjectRoster,
) -> str | None:
    """从 canonical 页面 ``source_path`` 返回唯一 presentation owner。

    ``page_object_contract.object_ids`` 是页面参与对象集合，不能用来选物理 owner；
    只有实际位于
    ``lib/service/<service>/<context>/<object>/presentation/**`` 的页面源文件才建立
    页面层义务。runtime/design_system 页面及尚未归位的旧路径返回 ``None``，由页面
    目录门禁单独阻断，派生器不猜 owner。
    """
    prefix = f"{APP_LIB_ROOT.as_posix()}/"
    if not repository_relative_path.startswith(prefix):
        return None
    relative_parts = tuple(repository_relative_path[len(prefix) :].split("/"))
    identity = derive_app_target_shape_identity(relative_parts, roster)
    if identity is None or identity[3] != "presentation":
        return None
    return roster.by_key[identity[:3]]["objectId"]


def derive_app_test_target_shape_identity(
    test_relative_parts: Sequence[str],
    roster: ObjectRoster,
) -> tuple[str, str, str] | None:
    """从 ``service/<service>/<context>/<object>/...`` 精确反推对象身份。"""
    if len(test_relative_parts) <= APP_TEST_TARGET_SHAPE_SEGMENTS:
        return None
    service_root, service, context, object_name = test_relative_parts[
        :APP_TEST_TARGET_SHAPE_SEGMENTS
    ]
    if service_root != APP_SERVICE_ROOT_SEGMENT:
        return None
    context_ids = roster.contexts_by_name.get(context) or set()
    if len(context_ids) != 1:
        return None
    domain = next(iter(context_ids)).split(".", 1)[0]
    try:
        expected_service = topology.app_service_for_context(domain, context)
    except ValueError:
        return None
    if service != expected_service:
        return None
    if (domain, context, object_name) not in roster.by_key:
        return None
    return domain, context, object_name


def derive_app_test_non_object_identity(
    test_layer: str | None,
    test_relative_parts: Sequence[str],
) -> dict[str, str] | None:
    """派生不属于单一 business object 的 canonical 测试身份。

    测试目录本身是唯一输入：不读取 registry、spec_ref、import 或文件名来猜对象。
    这类身份只让横切/Journey/runner 测试脱离 ``unowned`` 诊断，绝不能反向填充
    ``object_view[objectId].app.tests``，因为它们不是对象级三层证据。
    """
    if not test_layer or not test_relative_parts:
        return None

    cross_cutting_root = derive_app_cross_cutting_shape_root(test_relative_parts)
    if cross_cutting_root is not None:
        return {
            "kind": "test_support_cross_cutting"
            if test_layer == "support"
            else "test_cross_cutting",
            "root": cross_cutting_root,
            "status": "canonical_test_support_cross_cutting"
            if test_layer == "support"
            else "canonical_test_cross_cutting",
        }

    if (
        test_layer in APP_CROSS_OBJECT_JOURNEY_TEST_LAYERS
        and len(test_relative_parts) >= 3
        and test_relative_parts[0] == APP_CROSS_OBJECT_JOURNEY_ROOT
    ):
        return {
            "kind": "cross_object_journey",
            "root": APP_CROSS_OBJECT_JOURNEY_ROOT,
            "status": "canonical_cross_object_journey",
        }

    if (
        test_layer == APP_PATROL_RUNNER_LAYER
        and len(test_relative_parts) == 2
        and test_relative_parts[0] == APP_PATROL_RUNNER_ROOT
        and test_relative_parts[1] in APP_PATROL_RUNNER_FILES
    ):
        return {
            "kind": "patrol_runner",
            "root": APP_PATROL_RUNNER_ROOT,
            "status": "canonical_patrol_runner",
        }
    return None


def derive_app_cross_cutting_shape_root(relative_parts: Sequence[str]) -> str | None:
    """已处于横切面目标位置时返回其根名（``runtime`` / ``design_system``），否则 None。"""
    if not relative_parts:
        return None
    return APP_CROSS_CUTTING_SEGMENTS.get(relative_parts[0])


def derive_app_is_entry_file(relative_parts: Sequence[str]) -> bool:
    """路径是否是 `lib/` 顶层的 Flutter 入口文件（``lib/main*.dart``）。"""
    return len(relative_parts) == 1 and bool(
        APP_ENTRY_FILE_RE.match(relative_parts[0])
    )


def derive_app_is_composition_root(relative_parts: Sequence[str]) -> bool:
    """路径是否落在端侧组合根（现状 ``core/di/**`` 与目标 ``runtime/di/**``）。

    组合根按定义横跨多个 domain，不承载单一对象身份，因此不参与对象反推，也
    不受横切面反向依赖禁令约束（与云侧 `cmd/` 同义，不是逃逸）。
    """
    return APP_COMPOSITION_ROOT_SEGMENT in list(relative_parts[:-1])


# ---------------------------------------------------------------------------
# 端侧层与目标路径派生
# ---------------------------------------------------------------------------


def derive_app_layer(
    relative_parts: Sequence[str],
    roster: ObjectRoster | None = None,
) -> str | None:
    """派生端侧层角色。

    传入 *roster* 且路径已处于目标形态时，层由固定的第 5 段精确决定；否则退回
    ``APP_LAYER_BY_SEGMENT`` 的最右命中段（仅适用于尚未搬迁的旧命名）。
    """
    if roster is not None:
        identity = derive_app_target_shape_identity(relative_parts, roster)
        if identity is not None:
            return identity[3]
    for segment in reversed(list(relative_parts[:-1])):
        layer = APP_LAYER_BY_SEGMENT.get(segment)
        if layer is not None:
            return APP_LAYER_ALIASES.get(layer, layer)
    return None


def derive_app_cross_cutting_root(relative_parts: Sequence[str]) -> str:
    """无主端侧文件的横切面归属：design_system 或 runtime。

    已处于横切面目标位置时以物理根为准，段名启发式不得改判（`lib/runtime/theme/`
    属于 runtime，不是 design_system）。
    """
    shaped = derive_app_cross_cutting_shape_root(relative_parts)
    if shaped is not None:
        return shaped
    if APP_DESIGN_SYSTEM_SEGMENTS & set(relative_parts):
        return "design_system"
    return "runtime"


def derive_app_target_path(
    domain: str,
    context: str,
    object_name: str,
    layer: str,
    file_name: str,
) -> str:
    """端侧目标路径：``lib/service/<service>/<context>/<object>/<layer>/<file>``。"""
    service = topology.app_service_for_context(domain, context)
    return (
        f"{APP_LIB_ROOT.as_posix()}/{APP_SERVICE_ROOT_SEGMENT}/{service}/"
        f"{context}/{object_name}/{layer}/{file_name}"
    )


def derive_app_test_target_path(
    test_layer: str,
    domain: str,
    context: str,
    object_name: str,
    file_name: str,
) -> str:
    """端侧测试目标路径，逐段镜像 production 的 service/context/object。"""
    service = topology.app_service_for_context(domain, context)
    return (
        f"{APP_TEST_ROOT.as_posix()}/{test_layer}/{APP_SERVICE_ROOT_SEGMENT}/"
        f"{service}/{context}/{object_name}/{file_name}"
    )


def derive_app_cross_cutting_target_path(
    root: str,
    relative_to_lib: Sequence[str],
) -> str:
    """横切面目标路径：剥离现状前缀与目标根自身的段后挂到唯一横切根下。

    剥离目标根自身的段是幂等的充要条件：``lib/runtime/di/x.dart`` 已经在目标位置，
    若不剥离首段 ``runtime`` 就会被推导成 ``lib/runtime/runtime/di/x.dart``，且每次
    派生再套一层，导致组合根漏判与假违规随搬迁推进不断累积。
    """
    parts = list(relative_to_lib)
    # 顶层入口已经在工具链固定的终态位置，目标路径即自身；否则会被推成
    # `lib/runtime/main.dart`，既永远 already_placed=False，也不是可执行的落点。
    if derive_app_is_entry_file(parts):
        return f"{APP_LIB_ROOT.as_posix()}/{parts[0]}"
    strippable = set(APP_CROSS_CUTTING_STRIPPED_PREFIXES) | {
        segment
        for segment, mapped_root in APP_CROSS_CUTTING_SEGMENTS.items()
        if mapped_root == root
    }
    while len(parts) > 1 and parts[0] in strippable:
        parts = parts[1:]
    return f"{APP_ROOT.as_posix()}/{APP_CROSS_CUTTING_ROOTS[root]}/{'/'.join(parts)}"

"""单元发现：名册全部从 ContractGraph 派生，本包不写任何 domain 名单。

覆盖计量单元（``app:*`` / ``cloud:*``）、采集目标折叠与 scope 描述的唯一定义处。
除 import 重组外与拆分前逐字一致；被测试 monkeypatch 的符号（``ROOT``、
``AppAttribution`` / ``CloudAttribution``、``discover_*``）经包命名空间 ``cc``
在调用期解析，保持与拆分前单文件全局查找相同的语义。
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Sequence

import quwoquan_ops.gate.canonical_coverage as cc
from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate.object_path_map_lib import topology as opm_topology
from quwoquan_ops.gate import verify_app_architecture as vaa

from .constants import (
    APP_COLLECTION_TARGET,
    APP_CROSS_CUTTING_UNIT_PREFIX,
    APP_TEST_TARGET,
    APP_UNIT_PREFIX,
    CLOUD_CROSS_CUTTING_ROOTS,
    CLOUD_CROSS_CUTTING_UNIT_PREFIX,
    CLOUD_UNIT_PREFIX,
    KIND_CLOUD_STATEMENT,
    KIND_FLUTTER_LCOV,
    PYTHON_TRACE_SOURCE_ROOTS,
    SERVICE_COVERPKG_PATTERNS,
    SERVICE_EXCLUDED_PACKAGE_MARKER,
    SERVICE_ROOT,
    SHARED_RUNTIME_COLLECTION_TARGET,
    CoverageError,
)


def _has_go_sources(directory: Path) -> bool:
    """目录里是否真的有会进入 ``-coverpkg`` 的 production Go 代码。

    并非每个带 `contracts/domain.yaml` 的 service 都是 Go 实现（推荐服务是
    Python 模型服务，`go list` 对它返回空集）。只含 ``tests/**``、``*_test.go``
    或工具样例的目录也不能成为覆盖目标；否则 test-only service 会凭测试代码制造
    一个没有 production statement 分母的假 target。
    """
    return any(
        path.is_file() and not path.is_symlink() and not path.name.endswith("_test.go")
        for root_name in SERVICE_COVERPKG_PATTERNS
        for path in (directory / root_name).rglob("*.go")
    )


def _has_python_sources(directory: Path) -> bool:
    """目录里是否有真实 production Python 代码。"""
    return any(
        path.is_file() and not path.is_symlink() and path.name != "__init__.py"
        for root_name in PYTHON_TRACE_SOURCE_ROOTS
        for path in (directory / root_name).rglob("*.py")
    )


@functools.lru_cache(maxsize=1)
def go_collection_targets() -> dict[str, str]:
    """Go 采集目标：``service 相对根 → domain``。

    真相源是 `object_path_map.service_domains()`（扫 `contracts/domain.yaml`，
    同时覆盖 `services/*` 与 `control-plane/*`），再按「有没有 Go 代码」收窄。
    """
    return {
        relative: domain
        for relative, (_owner, domain) in sorted(opm.service_domains().items())
        if _has_go_sources(cc.ROOT / relative)
    }


@functools.lru_cache(maxsize=1)
def python_collection_targets() -> dict[str, str]:
    """Python 采集目标：同样从 service domain 真相源派生。"""
    targets = {
        relative: domain
        for relative, (_owner, domain) in sorted(opm.service_domains().items())
        if _has_python_sources(cc.ROOT / relative)
    }
    mixed = sorted(set(targets) & set(go_collection_targets()))
    if mixed:
        raise CoverageError(
            "同一 Cloud service 同时含 Go/Python production source，必须先声明唯一"
            f" coverage collection owner: {mixed}"
        )
    return targets


def cloud_collection_targets() -> dict[str, str]:
    """返回全部可执行 Cloud 采集目标，不因实现语言漏掉对象。"""
    return {**go_collection_targets(), **python_collection_targets()}


def _collection_target_language(target: str) -> str:
    if target == SHARED_RUNTIME_COLLECTION_TARGET or target in go_collection_targets():
        return "go"
    if target in python_collection_targets():
        return "python"
    raise CoverageError(f"未知覆盖率采集目标 {target!r}")


def app_object_unit(domain: str, context: str, object_name: str) -> str:
    """返回 canonical App ``service/context/object`` 单元，不维护 service 清单。"""
    service = opm_topology.app_service_for_context(domain, context)
    return f"{APP_UNIT_PREFIX}{service}/{context}/{object_name}"


def app_cross_cutting_unit(root: str) -> str:
    """返回 canonical 横切根的独立计量单元。"""
    if root not in opm.APP_CROSS_CUTTING_ROOTS:
        raise CoverageError(f"未知 App canonical cross-cutting root {root!r}")
    return f"{APP_CROSS_CUTTING_UNIT_PREFIX}{root}"


def expected_app_capability_units(
    roster: opm.ObjectRoster,
    pages: Sequence[dict],
) -> tuple[str, ...]:
    """派生必须拥有 App production coverage unit 的对象。

    端侧对象义务只有两条 machine-readable 真相源：ContractGraph 中真实存在
    ``clientContract`` 的 operation，以及已经物理归位到 canonical presentation
    路径的 page owner。页面的参与对象不能冒充物理 owner；纯云对象也不能因为存在于
    ContractGraph 就被强制造一个 App 单元。
    """
    object_ids = set(roster.app_client_contract_operations)
    for page in pages:
        physical_owner = opm.derive_page_physical_owner(
            str(page.get("path") or ""), roster
        )
        if physical_owner is not None:
            object_ids.add(physical_owner)
    return tuple(
        sorted(
            app_object_unit(
                roster.objects[object_id]["domain"],
                roster.objects[object_id]["context"],
                roster.objects[object_id]["objectName"],
            )
            for object_id in object_ids
        )
    )


def app_units(roster: opm.ObjectRoster) -> list[str]:
    """从当前 production source 的唯一对象/横切归属派生 App 单元。

    ``AppAttribution`` 对任一非唯一对象或非 canonical 横切源码 fail closed，因此
    返回的每个单元都至少拥有一个真实生产文件，纯云对象不会靠空目录冒充 App 单元。
    """
    return sorted(cc.AppAttribution(roster).files_by_unit)


def cloud_object_unit(service_name: str, context: str, object_name: str) -> str:
    """返回 canonical Cloud ``service/context/object`` 单元。"""
    service = opm.app_service_segment(service_name)
    return f"{CLOUD_UNIT_PREFIX}{service}/{context}/{object_name}"


def cloud_cross_cutting_unit(root: str) -> str:
    """返回 Cloud 组合根/共享 runtime 的显式横切单元。"""
    if root not in CLOUD_CROSS_CUTTING_ROOTS:
        raise CoverageError(f"未知 Cloud cross-cutting root {root!r}")
    return f"{CLOUD_CROSS_CUTTING_UNIT_PREFIX}{root}"


@functools.lru_cache(maxsize=1)
def _roster() -> opm.ObjectRoster:
    return vaa.load_roster()


@functools.lru_cache(maxsize=1)
def discover_app_units() -> tuple[str, ...]:
    return tuple(app_units(_roster()))


@functools.lru_cache(maxsize=1)
def discover_cloud_units() -> tuple[str, ...]:
    return tuple(sorted(cc.CloudAttribution(_roster()).files_by_unit))


@functools.lru_cache(maxsize=1)
def discover_units() -> tuple[str, ...]:
    return cc.discover_app_units() + cc.discover_cloud_units()


def unit_kind(unit: str) -> str:
    if unit.startswith(APP_UNIT_PREFIX):
        return KIND_FLUTTER_LCOV
    if unit.startswith(CLOUD_UNIT_PREFIX):
        return KIND_CLOUD_STATEMENT
    raise CoverageError(f"无法识别的单元 {unit!r}")


def unit_bucket(unit: str) -> str:
    prefix = APP_UNIT_PREFIX if unit.startswith(APP_UNIT_PREFIX) else CLOUD_UNIT_PREFIX
    return unit[len(prefix) :]


def _service_target_for_segment(service_segment: str) -> str:
    matches = sorted(
        relative
        for relative in cloud_collection_targets()
        if opm.app_service_segment(Path(relative).name) == service_segment
    )
    if len(matches) != 1:
        raise CoverageError(
            f"Cloud service segment {service_segment!r} 必须唯一命中采集目标，实测 {matches}"
        )
    return matches[0]


def cloud_collection_targets_for_unit(unit: str) -> list[str]:
    """返回 Cloud 单元所依赖的真实采集产物。"""
    bucket = unit_bucket(unit)
    if bucket == "cross-cutting/cmd":
        targets = [
            relative
            for relative in cloud_collection_targets()
            if any(
                path.is_file()
                and not path.is_symlink()
                and not path.name.endswith("_test.go")
                for suffix in (
                    ("*.go",)
                    if _collection_target_language(relative) == "go"
                    else ("*.py",)
                )
                for path in (cc.ROOT / relative / "cmd").rglob(suffix)
            )
        ]
        if any(
            path.is_file()
            and not path.is_symlink()
            and not path.name.endswith("_test.go")
            for path in (SERVICE_ROOT / "cmd").rglob("*.go")
        ):
            targets.append(SHARED_RUNTIME_COLLECTION_TARGET)
        return sorted(targets)
    if bucket == "cross-cutting/shared_runtime":
        return [SHARED_RUNTIME_COLLECTION_TARGET]
    parts = bucket.split("/")
    if len(parts) != 3 or any(not part for part in parts):
        raise CoverageError(f"Cloud 对象单元不是 service/context/object: {unit!r}")
    return [_service_target_for_segment(parts[0])]


def unit_scope(unit: str) -> str:
    """人类可读且逐字段可比的采集范围描述；与实际执行的命令同源派生。

    端侧把归属规则标识 (`object_path_map.RULE_ID`) 写进 scope：反推规则一变，
    同一份 lcov 的分桶结果就不可比，必须重采而不是继续比大小。
    """
    if unit.startswith(APP_UNIT_PREFIX):
        return (
            f"quwoquan_app: flutter test --coverage --branch-coverage {APP_TEST_TARGET}"
            f"; unit={unit_bucket(unit)} attribution={opm.RULE_ID}"
        )
    targets = cloud_collection_targets_for_unit(unit)
    target_kinds = sorted({_collection_target_language(target) for target in targets})
    return (
        "quwoquan_service: canonical local_contract statement coverage; "
        f"unit={unit_bucket(unit)} targets={','.join(targets)} "
        f"collectors={','.join(target_kinds)} "
        f"attribution={opm.RULE_ID} (excluding {SERVICE_EXCLUDED_PACKAGE_MARKER})"
    )


def collection_targets(units: Sequence[str]) -> list[str]:
    """把计量单元折叠成去重后的采集目标。

    端侧对象共享同一次 `flutter test --coverage`；云侧对象只读取 owning service
    的产物，cmd/shared-runtime 横切单元读取对应的全部真实采集目标。
    """
    targets: list[str] = []
    for unit in units:
        if unit.startswith(APP_UNIT_PREFIX):
            candidates = [APP_COLLECTION_TARGET]
        else:
            candidates = cloud_collection_targets_for_unit(unit)
        for candidate in candidates:
            if candidate not in targets:
                targets.append(candidate)
    return targets

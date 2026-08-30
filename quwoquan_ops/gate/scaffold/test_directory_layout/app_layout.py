"""端侧三层测试目录的对象名册派生、残留棘轮与 verify_app 编排。"""

from __future__ import annotations

import json
from pathlib import Path

from test_directory_layout_lib import APP_PACKAGES_ROOT, APP_ROOT, LAYERS

from quwoquan_ops.gate import object_path_map as opm

from .app_support import (
    verify_app_journeys,
    verify_app_support_layout,
    verify_app_user_acceptance_support_edges,
)
from .common import (
    Failures,
    ensure_allowed_children,
    expected_suffix,
    iter_app_test_files,
    rel,
    require_layer_suffix,
    verify_support_has_no_tests,
)
from .constants import (
    APP_CROSS_OBJECT_JOURNEY_ROOT,
    APP_PATROL_RUNNER_FILES,
    APP_PATROL_RUNNER_ROOT,
    APP_TEST_ROOT_DIRS,
    APP_UNMIGRATED_LAYER_DIRS,
)


def app_object_roster() -> opm.ObjectRoster:
    """从 ContractGraph 读取端侧测试路径的唯一对象名册。

    这里返回完整 roster，后续不仅校验 domain 顶层，还必须用同一名册
    校验 ``domain/context/object`` 三段身份。
    """
    graph_path = opm.ROOT / opm.CONTRACT_GRAPH_PATH
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)


def app_object_test_dirs(roster: opm.ObjectRoster | None = None) -> set[str]:
    """端侧测试层的 canonical 顶层目录，全部由名册派生。

    目标形态
    ``test/<layer>/service/<service>/<context>/<object>/`` 的首段只能是统一
    ``service`` 容器；不归属任何业务对象的横切测试落到
    `object_path_map.APP_CROSS_CUTTING_ROOTS` 的三个根。
    """
    roster = roster or app_object_roster()
    # 强制求值 service/context 派生，避免仅因顶层字面量正确而掩盖 owner 冲突。
    for record in roster.objects.values():
        opm.app_service_for_context(record["domain"], record["context"])
    return {opm.APP_SERVICE_ROOT_SEGMENT} | set(opm.APP_CROSS_CUTTING_ROOTS)


def allowed_app_layer_dirs(layer: str, object_dirs: set[str]) -> set[str]:
    allowed = object_dirs | APP_UNMIGRATED_LAYER_DIRS.get(layer, set())
    if layer in {"local_contract", "user_acceptance"}:
        allowed.add(APP_CROSS_OBJECT_JOURNEY_ROOT)
    if layer == "user_acceptance":
        allowed.add(APP_PATROL_RUNNER_ROOT)
    return allowed


def verify_app_patrol_runner_root(failures: Failures) -> None:
    """Patrol runner shell 不是 UAT owner；只允许 pubspec 绑定的两个精确入口。"""
    runner_root = APP_ROOT / "user_acceptance" / APP_PATROL_RUNNER_ROOT
    if not runner_root.exists():
        return
    actual = {
        path.relative_to(runner_root).as_posix()
        for path in runner_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    unexpected = sorted(actual - APP_PATROL_RUNNER_FILES)
    missing = sorted(APP_PATROL_RUNNER_FILES - actual)
    for name in unexpected:
        failures.add(
            f"{rel(runner_root / name)} is not a Patrol runner entry; "
            "move runnable UAT to a canonical object or Journey owner"
        )
    for name in missing:
        failures.add(f"{rel(runner_root / name)} is required by the Patrol runner shell")
    for directory in sorted(path for path in runner_root.rglob("*") if path.is_dir()):
        failures.add(
            f"{rel(directory)} is nested below the Patrol runner shell; "
            "only patrol_test_main.dart and test_bundle.dart are allowed"
        )


def verify_app_unmigrated_residue(layer: str, failures: Failures) -> None:
    """missing / empty / remaining 残留均 BLOCK，不允许 allowance 假绿。"""
    layer_root = APP_ROOT / layer
    for name in sorted(APP_UNMIGRATED_LAYER_DIRS.get(layer, set())):
        residue_root = layer_root / name
        if not residue_root.is_dir():
            failures.add(
                f"{rel(residue_root)} no longer exists; drop it from "
                "APP_UNMIGRATED_LAYER_DIRS instead of keeping a stale allowance"
            )
            continue
        tests = sorted(iter_app_test_files(residue_root))
        if not tests:
            failures.add(
                f"{rel(residue_root)} is an empty-shell legacy allowance with no "
                "Dart/Python tests; empty directories and non-test artifacts do not count "
                "as migrated test evidence"
            )
            continue
        for path in tests:
            failures.add(
                f"{rel(path)} remains under legacy test root {rel(residue_root)}; "
                "move it to a canonical object owner and remove the allowance"
            )


def require_app_object_test_path(
    path: Path,
    layer_root: Path,
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    """对每个对象测试精确校验 ``service/service/context/object`` 四段身份。"""
    parts = path.relative_to(layer_root).parts
    top_level = parts[0]
    if top_level in APP_UNMIGRATED_LAYER_DIRS.get(layer_root.name, set()):
        return
    if top_level in opm.APP_CROSS_CUTTING_ROOTS:
        return
    if top_level == APP_CROSS_OBJECT_JOURNEY_ROOT:
        if layer_root.name == "api_integration":
            failures.add(
                f"{rel(path)} is a cross-object Journey in api_integration; "
                "use test/local_contract/journeys for typed-double/Provider/Widget "
                "contracts or test/user_acceptance/journeys for production Remote journeys"
            )
        return
    if opm.derive_app_test_target_shape_identity(parts, roster) is None:
        failures.add(
            f"{rel(path)} must live under a ContractGraph-owned "
            f"test/{layer_root.name}/service/<service>/<context>/<object>/.../file"
        )


def verify_app_object_source_files(
    layer: str,
    layer_root: Path,
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    """Object test directories contain runnable tests; reusable code belongs in support."""
    if not layer_root.exists():
        return
    for path in sorted(layer_root.rglob("*")):
        if not path.is_file() or path.suffix not in {".dart", ".py"}:
            continue
        parts = path.relative_to(layer_root).parts
        if opm.derive_app_test_target_shape_identity(parts, roster) is None:
            continue
        suffix = expected_suffix(path, layer)
        if suffix is None or not path.name.endswith(suffix):
            failures.add(
                f"{rel(path)} is non-test source inside an object test directory; "
                "move reusable helpers/barrels to the unique test/support owner"
            )


def verify_app_python_evidence_boundaries(failures: Failures) -> None:
    """Only root App local_contract Python is executed by the canonical runner."""
    for layer in ("api_integration", "user_acceptance"):
        for path in sorted((APP_ROOT / layer).rglob("*.py")):
            if path.is_file():
                failures.add(
                    f"{rel(path)} is static App Python under {layer}; only root "
                    "test/local_contract Python is executable evidence"
                )
    if APP_PACKAGES_ROOT.exists():
        for path in sorted(APP_PACKAGES_ROOT.glob("*/test/**/*.py")):
            if path.is_file():
                failures.add(
                    f"{rel(path)} is package-local App Python without a canonical runner"
                )


def verify_app(failures: Failures) -> None:
    # flutter_test_config.dart 是 Flutter SDK 约定的树级前置入口，必须位于 test
    # 根才会被 test runner 识别；它不是测试用例，因此显式列入允许文件而不是
    # 让它伪装成某一层的 suite。
    ensure_allowed_children(
        APP_ROOT,
        APP_TEST_ROOT_DIRS,
        failures,
        allow_files={"flutter_test_config.dart"},
    )
    verify_support_has_no_tests(APP_ROOT / "support", failures)
    roster = app_object_roster()
    verify_app_support_layout(roster, failures)
    object_dirs = app_object_test_dirs(roster)
    for layer in sorted(LAYERS):
        layer_root = APP_ROOT / layer
        ensure_allowed_children(
            layer_root, allowed_app_layer_dirs(layer, object_dirs), failures
        )
        verify_app_unmigrated_residue(layer, failures)
        for path in sorted(iter_app_test_files(layer_root)):
            require_layer_suffix(path, layer, failures)
            require_app_object_test_path(path, layer_root, roster, failures)
        verify_app_object_source_files(layer, layer_root, roster, failures)
        for child in (sorted(layer_root.iterdir()) if layer_root.exists() else []):
            if child.is_file():
                failures.add(f"{rel(child)} must live under a test object directory")
    for layer in sorted(LAYERS):
        verify_app_journeys(layer, failures)
    verify_app_user_acceptance_support_edges(roster, failures)
    verify_app_python_evidence_boundaries(failures)
    verify_app_patrol_runner_root(failures)

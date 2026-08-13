"""Ops 测试树 concern 分域、pytest 命名与 provider conformance 声明矩阵校验。"""

from __future__ import annotations

from pathlib import Path

from test_directory_layout_lib import OPS_ACCEPTANCE_ROOT, OPS_TEST_ROOT

from .common import (
    Failures,
    ensure_allowed_children,
    rel,
    require_layer_suffix,
    verify_support_has_no_tests,
)
from .constants import OPS_ACCEPTANCE_DIRS, OPS_TEST_ROOT_DIRS


def require_ops_pytest_prefix(path: Path, failures: Failures) -> None:
    """pytest 默认按 ``*_test.py`` 收集；缺 ``test_`` 前缀的套件会被执行却绕过
    命名门禁，因此收集面与门禁面必须对齐到同一个 ``test_*`` 前缀。"""
    if not path.name.startswith("test_"):
        failures.add(
            f"{rel(path)} must start with 'test_' so pytest collection and the "
            "layout gate govern the same suite"
        )


#: provider conformance 声明矩阵（裁决：保留在测试树内）。
#:
#: 每个声明文件是「一层 × 一个 Provider adapter」的测试声明点：头部
#: ``# provider_conformance: {...}`` JSON 携带 adapterId/testLayer/command，
#: command 路径被 conformance readiness digest 绑定，迁出测试树需以真实
#: Provider 凭据重建全部 receipt，收益不抵成本。数量随 Provider 名册增减
#: （守恒上限防无名册拷贝），每个 adapterId 必须三层成对声明。
OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING = 27

_CONFORMANCE_LAYER_ROOTS = (
    ("local_contract", Path("local_contract")),
    ("api_integration", Path("acceptance/api_integration")),
    ("user_acceptance", Path("acceptance/user_acceptance")),
)
_CONFORMANCE_HEADER_RE = __import__("re").compile(
    r"^# provider_conformance: (\{.*\})\s*$"
)


def _conformance_declaration_identity(path: Path) -> tuple[str, str] | None:
    """返回声明的 (adapterId, testLayer)；无法解析返回 None。"""
    import json

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:10]:
        match = _CONFORMANCE_HEADER_RE.match(line)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        return (
            str(payload.get("adapterId") or ""),
            str(payload.get("testLayer") or ""),
        )
    return None


def verify_ops_conformance_declaration_matrix(failures: Failures) -> None:
    """conformance 声明矩阵守恒：testLayer 与树层一致、adapterId 三层成对。"""
    adapters_by_layer: dict[str, dict[str, int]] = {}
    for layer, relative_root in _CONFORMANCE_LAYER_ROOTS:
        root = OPS_TEST_ROOT / relative_root
        adapters: dict[str, int] = {}
        for path in sorted(root.rglob("*_provider_conformance.py")):
            if "/service_ops/" not in rel(path) or "/ci/" not in rel(path):
                continue
            identity = _conformance_declaration_identity(path)
            if identity is None:
                failures.add(
                    f"{rel(path)} has no parseable '# provider_conformance:' "
                    "declaration header"
                )
                continue
            adapter_id, declared_layer = identity
            if declared_layer != layer:
                failures.add(
                    f"{rel(path)} declares testLayer={declared_layer!r} but lives "
                    f"in the {layer} tree"
                )
            if not adapter_id:
                failures.add(f"{rel(path)} declares an empty adapterId")
                continue
            adapters[adapter_id] = adapters.get(adapter_id, 0) + 1
        if len(adapters) > OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING:
            failures.add(
                f"conformance declarations in {layer} grew to {len(adapters)} "
                f"(> {OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING}); grow the "
                "provider roster and this ceiling in the same change"
            )
        for adapter_id, count in sorted(adapters.items()):
            if count > 1:
                failures.add(
                    f"adapter {adapter_id} has {count} conformance declarations "
                    f"in {layer}; each layer declares one file per adapter"
                )
        adapters_by_layer[layer] = adapters
    layer_names = [layer for layer, _ in _CONFORMANCE_LAYER_ROOTS]
    all_adapters = sorted(
        set().union(*(set(items) for items in adapters_by_layer.values()))
    )
    for adapter_id in all_adapters:
        missing = [
            layer
            for layer in layer_names
            if adapter_id not in adapters_by_layer.get(layer, {})
        ]
        if missing:
            failures.add(
                f"adapter {adapter_id} is missing conformance declarations in "
                f"{', '.join(missing)}; the declaration matrix pairs every "
                "adapter across all three layers"
            )
    print(
        "[verify] conformance declaration matrix: adapters="
        f"{len(all_adapters)} (ceiling per layer="
        f"{OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING})"
    )

#: ops local_contract 按 concern 分域；新 concern 目录必须与搬迁批次一起登记。
OPS_LOCAL_CONTRACT_CONCERN_DIRS = {
    "ci",
    "environment",
    "gate",
    "media",
    "observability",
    "provider",
    "release",
    "service_ops",
    "stackctl",
    "test_data",
}


def verify_ops_local_contract_concerns(failures: Failures) -> None:
    """终态规则：local_contract 根只允许已登记 concern 子目录，禁止任何平铺
    套件。分域搬迁已归零，历史平铺棘轮随之退役。"""
    root = OPS_TEST_ROOT / "local_contract"
    if not root.exists():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir():
            # 运行时 bytecode 缓存由缓存治理军规单独阻断，不属于 concern 名册。
            if child.name == "__pycache__":
                continue
            if child.name not in OPS_LOCAL_CONTRACT_CONCERN_DIRS:
                failures.add(
                    f"{rel(child)} is not a registered ops local_contract concern "
                    "directory; register the concern with its migration batch"
                )
            continue
        if child.name.endswith("_test.py"):
            failures.add(
                f"{rel(child)} is a flat suite at the ops local_contract root; "
                "place it in a registered concern directory"
            )


def verify_ops_local_contract_python_roles(failures: Failures) -> None:
    """local_contract 树内的 Python 只能是 pytest 套件、conftest 或 conformance
    声明；helper 归 tests/support，runner 归 canonical 脚本角色。"""
    root = OPS_TEST_ROOT / "local_contract"
    for path in sorted(root.rglob("*.py")):
        if path.name.endswith("_test.py") or path.name == "conftest.py":
            continue
        rel_parts = path.relative_to(root).parts
        if (
            len(rel_parts) == 4
            and rel_parts[0] == "service_ops"
            and rel_parts[2] == "ci"
            and path.name.endswith("_provider_conformance.py")
        ):
            # conformance 声明矩阵成员；名册守恒与三层成对由
            # verify_ops_conformance_declaration_matrix 校验。
            continue
        failures.add(
            f"{rel(path)} is not a pytest suite; move helpers to "
            "quwoquan_ops/tests/support and runners to a canonical script role"
        )


def verify_ops(failures: Failures) -> None:
    ensure_allowed_children(OPS_TEST_ROOT, OPS_TEST_ROOT_DIRS, failures)
    verify_support_has_no_tests(OPS_TEST_ROOT / "support", failures)
    if OPS_ACCEPTANCE_ROOT.exists():
        ensure_allowed_children(OPS_ACCEPTANCE_ROOT, OPS_ACCEPTANCE_DIRS, failures)
    verify_ops_local_contract_concerns(failures)
    verify_ops_local_contract_python_roles(failures)
    verify_ops_conformance_declaration_matrix(failures)
    for path in sorted((OPS_TEST_ROOT / "local_contract").rglob("*_test.py")):
        require_layer_suffix(path, "local_contract", failures)
        require_ops_pytest_prefix(path, failures)
    for layer in sorted(OPS_ACCEPTANCE_DIRS):
        layer_root = OPS_ACCEPTANCE_ROOT / layer
        if not layer_root.exists():
            failures.add(f"missing ops acceptance layer: {rel(layer_root)}")
            continue
        for path in sorted(layer_root.rglob("*_test.py")):
            require_layer_suffix(path, layer, failures)
            require_ops_pytest_prefix(path, failures)

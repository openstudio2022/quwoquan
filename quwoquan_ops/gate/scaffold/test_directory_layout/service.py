"""Service/control-plane/runtime 与横切区的 canonical 测试树校验。"""

from __future__ import annotations

from pathlib import Path

from test_directory_layout_lib import (
    CONTROL_PLANE_ROOT,
    RUNTIME_ROOT,
    RUNTIME_TEST_ROOT,
    SERVICE_DOMAIN_ROOT,
    SERVICE_ROOT,
    evidence_path_is_canonical,
    iter_canonical_files,
)

from quwoquan_ops.gate import object_path_map as opm

from .app_layout import app_object_roster
from .common import (
    Failures,
    ensure_allowed_children,
    rel,
    require_layer_suffix,
    verify_support_has_no_tests,
)
from .constants import SERVICE_TEST_DIRS, _SERVICE_DOMAIN_RE


def service_object_test_roster(
    service_dir: Path,
    roster: opm.ObjectRoster,
) -> set[tuple[str, str]]:
    """Intersect the service's physical contracts with the ContractGraph roster."""
    domain_path = service_dir / "contracts" / "domain.yaml"
    if not domain_path.is_file():
        return set()
    match = _SERVICE_DOMAIN_RE.search(
        domain_path.read_text(encoding="utf-8", errors="ignore")
    )
    if match is None:
        return set()
    domain = match.group(1)
    objects: set[tuple[str, str]] = set()
    for graph_domain, context, object_name in sorted(roster.by_key):
        if graph_domain != domain:
            continue
        contract = service_dir / "contracts" / context / object_name / "object.yaml"
        if contract.is_file():
            objects.add((context, object_name))
    return objects


def verify_service_tests_dir(
    tests_root: Path,
    roster: opm.ObjectRoster,
    failures: Failures,
) -> None:
    ensure_allowed_children(tests_root, SERVICE_TEST_DIRS, failures, allow_files={"__init__.py"})
    verify_support_has_no_tests(tests_root / "support", failures)
    if (tests_root / "ops").exists():
        failures.add(f"{rel(tests_root / 'ops')} is retired; cross-environment tests belong to quwoquan_ops/tests/acceptance")
    object_roster = service_object_test_roster(tests_root.parent, roster)
    for layer in ("local_contract", "api_integration"):
        layer_root = tests_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*_test.go")):
            require_layer_suffix(path, layer, failures)
            require_service_object_test_path(path, layer_root, object_roster, failures)
        for path in sorted(layer_root.rglob("*_test.py")):
            require_layer_suffix(path, layer, failures)
            require_service_object_test_path(path, layer_root, object_roster, failures)


def require_service_object_test_path(
    path: Path,
    layer_root: Path,
    object_roster: set[tuple[str, str]],
    failures: Failures,
) -> None:
    parts = path.relative_to(layer_root).parts
    if len(parts) < 3:
        failures.add(
            f"{rel(path)} must live under "
            "<context>/<object>/.../file"
        )
        return
    if any(part in {"internal", "cmd", "generated"} for part in parts[:2]):
        failures.add(
            f"{rel(path)} must use a business context/object owner before "
            "any optional Go package subpath"
        )
        return
    if (parts[0], parts[1]) not in object_roster:
        failures.add(
            f"{rel(path)} uses context/object {parts[0]}/{parts[1]} outside the "
            "owning service contracts and ContractGraph roster"
        )


def verify_service(failures: Failures) -> None:
    if not SERVICE_ROOT.exists():
        failures.add(f"missing service root: {rel(SERVICE_ROOT)}")
        return
    roster = app_object_roster()
    for owner_root in (SERVICE_ROOT, CONTROL_PLANE_ROOT):
        if not owner_root.exists():
            continue
        for service_dir in sorted(path for path in owner_root.iterdir() if path.is_dir()):
            tests_root = service_dir / "tests"
            if tests_root.exists():
                verify_service_tests_dir(tests_root, roster, failures)
            for path in sorted(service_dir.rglob("*_test.go")):
                rel_text = rel(path)
                if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                    continue
                try:
                    owner_relative = path.relative_to(service_dir).parts
                except ValueError:
                    owner_relative = ()
                # 服务 cmd 装配层与顶层横切区同规：允许旁路同包白盒测试，
                # 但必须携带 local_contract 层后缀；对象实现（internal）仍禁止旁路。
                if owner_relative and owner_relative[0] == "cmd":
                    require_cross_cutting_go_layer_suffix(path, failures)
                    continue
                failures.add(
                    f"{rel_text} is a service test outside canonical "
                    "tests/local_contract/<context>/<object> or "
                    "tests/api_integration/<context>/<object>"
                )
            for path in sorted(service_dir.rglob("*_test.py")):
                rel_text = rel(path)
                if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                    continue
                failures.add(
                    f"{rel_text} is a service test outside canonical "
                    "tests/local_contract/<context>/<object> or "
                    "tests/api_integration/<context>/<object>"
                )


def require_cross_cutting_go_layer_suffix(path: Path, failures: Failures) -> None:
    """横切区（runtime/internal/tools/cmd）允许旁路同包白盒测试，但必须显式
    携带 local_contract 层后缀；api_integration 依赖真实环境，禁止旁路同包。"""
    rel_text = rel(path)
    if not path.name.endswith("__local_contract_test.go"):
        failures.add(
            f"{rel_text} is a package-local cross-cutting test and must end with "
            "'__local_contract_test.go'; api_integration tests belong to a "
            "canonical tests/api_integration tree"
        )
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "//go:build api_integration" in text:
        failures.add(
            f"{rel_text} carries the api_integration build tag and must move to "
            "a canonical tests/api_integration tree"
        )


def verify_runtime(failures: Failures) -> None:
    if not RUNTIME_ROOT.exists():
        failures.add(f"missing runtime root: {rel(RUNTIME_ROOT)}")
        return
    verify_runtime_tests_dir(RUNTIME_TEST_ROOT, failures)
    for path in sorted(RUNTIME_ROOT.rglob("*_test.go")):
        rel_text = rel(path)
        if (
            "/tests/local_contract/" in rel_text
            or "/tests/api_integration/" in rel_text
        ):
            continue
        require_cross_cutting_go_layer_suffix(path, failures)


def verify_service_domain_cross_cutting(failures: Failures) -> None:
    """internal/tools/cmd 与 runtime 共用同一横切测试军规。"""
    for root_name in ("internal", "tools", "cmd"):
        root = SERVICE_DOMAIN_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*_test.go")):
            rel_text = rel(path)
            if "/tests/local_contract/" in rel_text or "/tests/api_integration/" in rel_text:
                continue
            if any(part in {"vendor", "generated", "testdata"} for part in path.parts):
                continue
            require_cross_cutting_go_layer_suffix(path, failures)


def verify_runtime_tests_dir(tests_root: Path, failures: Failures) -> None:
    ensure_allowed_children(
        tests_root,
        SERVICE_TEST_DIRS,
        failures,
        allow_files={"__init__.py"},
    )
    verify_support_has_no_tests(tests_root / "support", failures)
    for layer in ("local_contract", "api_integration"):
        layer_root = tests_root / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*_test.go")):
            require_layer_suffix(path, layer, failures)
            parts = path.relative_to(layer_root).parts
            if len(parts) != 2:
                failures.add(
                    f"{rel(path)} must live directly under <runtime-package>/file"
                )
            elif parts[0] in {"internal", "cmd", "generated"}:
                failures.add(
                    f"{rel(path)} must not recreate a production source root "
                    "inside runtime tests/"
                )


def verify_all_canonical_files_recognized(failures: Failures) -> None:
    for _, path, layer in iter_canonical_files():
        if not evidence_path_is_canonical(rel(path)):
            failures.add(f"{rel(path)} is not recognized as canonical {layer} evidence")

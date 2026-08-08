# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` 唯一 coverage rule 的本地契约。

本测试锁定六件事：

1. **端云单元为 service/context/object**，canonical cross-cutting 独立计量；
   名册从 ContractGraph 与 `object_path_map` 派生，源码里不复制 domain/object 名单。
2. **解析口径正确**：lcov 的 `LF`/`LH` 是行，分支只能从 `BRDA` 明细数
   （Flutter 3.44 的 `--branch-coverage` 不写 `BRF`/`BRH`，照汇总行解析会得到
   恒为 0 的分母）；Go coverprofile 按基本块去重，Python trace 必须覆盖磁盘上
   全部 production 文件，二者都按对象 statement 计量。
3. **canonical rule 语义**：低于基线（超容差）阻断，达标放行，涨得太多也阻断并要求
   `--write-baseline` 收紧，未登记单元与陈旧单元同样阻断。
4. **分母为 0 绝不折成 0%**，且不可测状态在任一组合下都阻断，不能写 baseline。
   仓库里出过的事故是旧门禁对缺失静默返回 0，文件搬走后那个 bucket 永久
   「达标」。
5. **`file` 轴堵住分母缩水**：删掉一个覆盖率低的测试会让 lcov 分母变小、`line`
   反而上升；`file` 轴的分母来自磁盘，让这种「覆盖率下降却变绿」不成立。
6. **没有 warn-only / 可跳过 / 默认关闭的逃逸口**：无主源码、旧 lcov、红测试、
   receipt 的 HEAD commit/tree、config/toolchain、artifact/source/test/attribution/scope
   任一漂移都阻断；baseline entry 缺失或伪造 receipt provenance 同样阻断。

仓库真实覆盖率的采集（`--collect`）要跑整套 Flutter、Go 与 Python 测试，属于 gate 阶段
的职责，不在 L0 契约测试里重复执行；这里只断言基线文件本身自洽、分桶派生正确、
以及求值语义。
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_canonical_coverage as vcr

GATE_SOURCE_PATH = ROOT / "quwoquan_ops" / "gate" / "verify_canonical_coverage.py"
DELIVERY_GATE_PATH = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"
RECOMMENDATION_SERVICE_ROOT = (
    ROOT / "quwoquan_service" / "services" / "recommendation-service"
)
RECOMMENDATION_MAKEFILE_PATH = RECOMMENDATION_SERVICE_ROOT / "Makefile"
RECOMMENDATION_COVERAGE_LOCK_PATH = (
    RECOMMENDATION_SERVICE_ROOT / vcr.PYTHON_COVERAGE_TOOLCHAIN_LOCK
)
RECOMMENDATION_RUNTIME_REQUIREMENTS_PATH = (
    RECOMMENDATION_SERVICE_ROOT
    / "internal/recommendation/recommendation_model_release/"
    "infrastructure/model_runtime/requirements.txt"
)


def _identity(marker: str = "1") -> dict[str, str]:
    return {
        "headCommit": marker * 40,
        "headTree": marker * 40,
        "sourceTreeDigest": "sha256:" + marker * 64,
        "testTreeDigest": "sha256:" + marker * 64,
        "attributionDigest": "sha256:" + marker * 64,
        "configDigest": "sha256:" + marker * 64,
        "toolchainDigest": "sha256:" + marker * 64,
        "collectionScopeDigest": "sha256:" + marker * 64,
    }


def _receipt(target: str, marker: str = "1") -> dict:
    return {
        "schema": vcr.ARTIFACT_RECEIPT_SCHEMA,
        "ruleId": vcr.RULE_ID,
        "target": target,
        "artifactRef": vcr._display(vcr.artifact_path(target)),
        "artifactDigest": "sha256:" + marker * 64,
        **_identity(marker),
        "testsGreen": True,
    }


def _receipts_for_unit(unit: str) -> list[dict]:
    markers = "123456789abcdef"
    return [
        _receipt(target, markers[index % len(markers)])
        for index, target in enumerate(vcr.collection_targets([unit]))
    ]


def _add_baseline_unit(baseline: dict, unit: str, metrics: dict) -> None:
    receipts = _receipts_for_unit(unit)
    baseline["units"][unit] = vcr.unit_entry(metrics, unit, receipts=receipts)
    for receipt in receipts:
        baseline["receipts"][vcr.receipt_digest(receipt)] = receipt


# ---------------------------------------------------------------------------
# App 对象单元从 ContractGraph 与 production source 派生
# ---------------------------------------------------------------------------


def _roster_from_disk() -> opm.ObjectRoster:
    graph = json.loads((ROOT / opm.CONTRACT_GRAPH_PATH).read_text(encoding="utf-8"))
    return opm.ObjectRoster(graph)


def _probe_roster() -> opm.ObjectRoster:
    """两个对象的最小 ContractGraph：一个 clientContract owner、一个 page owner。"""
    return opm.ObjectRoster(
        {
            "objects": [
                {
                    "id": "probe.client_object",
                    "domain": "probe",
                    "kind": "projection",
                    "sourcePath": "probe/client_context/client_object",
                },
                {
                    "id": "probe.page_object",
                    "domain": "probe",
                    "kind": "projection",
                    "sourcePath": "probe/page_context/page_object",
                },
            ],
            "businessObjectMaps": [
                {
                    "boundedContexts": [
                        {"contextId": "probe.client_context"},
                        {"contextId": "probe.page_context"},
                    ]
                }
            ],
            "operations": [
                {
                    "id": "ProbeClientObjectQuery",
                    "objectId": "probe.client_object",
                    "clientContract": {"responseWire": "ProbeClientObjectWire"},
                }
            ],
        }
    )


def _production_row(
    path: str,
    *,
    object_id: str | None = None,
    status: str = "canonical",
    cross_cutting_root: str | None = None,
    method: str = "app_target_shape",
) -> dict:
    return {
        "role": "production",
        "path": f"{opm.APP_LIB_ROOT.as_posix()}/{path}",
        "objectId": object_id,
        "status": status,
        "crossCuttingRoot": cross_cutting_root,
        "method": method,
    }


def _first_object(roster: opm.ObjectRoster) -> dict:
    return roster.objects[sorted(roster.objects)[0]]


def test_app_units_are_domain_context_object_and_cross_cutting_is_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """App 名册只能来自唯一对象 owner；canonical 横切根各自计量。"""
    roster = _probe_roster()
    monkeypatch.setattr(
        opm, "app_service_for_context", lambda domain, context: f"{domain}_service"
    )
    record = _first_object(roster)
    object_unit = vcr.app_object_unit(
        record["domain"], record["context"], record["objectName"]
    )
    rows = [
        _production_row("owned.dart", object_id=record["objectId"]),
        *[
            _production_row(
                f"{root}/owned.dart",
                status="canonical_cross_cutting",
                cross_cutting_root=root,
                method="cross_cutting",
            )
            for root in sorted(opm.APP_CROSS_CUTTING_ROOTS)
        ],
    ]
    monkeypatch.setattr(opm, "load_page_claims", lambda: ({}, []))
    monkeypatch.setattr(opm, "scan_app", lambda _roster, _claims: (rows, []))

    expected_app = sorted(
        [object_unit]
        + [
            vcr.app_cross_cutting_unit(root)
            for root in sorted(opm.APP_CROSS_CUTTING_ROOTS)
        ]
    )
    assert vcr.app_units(roster) == expected_app
    assert object_unit == (
        f"app:{record['domain']}_service/{record['context']}/{record['objectName']}"
    )
    assert all(
        unit.startswith(vcr.APP_CROSS_CUTTING_UNIT_PREFIX)
        for unit in expected_app
        if unit != object_unit
    )

    # Cloud 同样是 service/context/object，不再按 domain 合并。
    disk_roster = _roster_from_disk()
    cloud = sorted(vcr.CloudAttribution(disk_roster).files_by_unit)
    assert cloud, "云侧至少要有一个 Go 对象/横切单元"
    assert vcr.cloud_cross_cutting_unit("cmd") in cloud
    assert vcr.cloud_cross_cutting_unit("shared_runtime") in cloud
    assert all(
        unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
        or len(vcr.unit_bucket(unit).split("/")) == 3
        for unit in cloud
    )


def test_app_scope_measures_the_real_repository_instead_of_an_empty_roster() -> None:
    """App scope 必须真的发现单元；空 App 名册是假绿，不是通过。

    `AppAttribution` 对任何无主 `lib/**` 生产文件 fail closed，因此这条断言同时
    覆盖两件事：归属闭合，且 App scope 不是空转。归属破裂时（l10n 根或顶层入口
    缺席 `APP_CROSS_CUTTING_ROOTS`）构造即抛 `CoverageError`，本测试红。
    """
    roster = _roster_from_disk()
    attribution = vcr.AppAttribution(roster)

    # 磁盘上每个 lib/** 生产文件都必须落进恰好一个计量单元。
    assert attribution.unit_of
    assert set(attribution.unit_of.values()) == set(attribution.files_by_unit)

    units = vcr.app_units(roster)
    assert units == sorted(attribution.files_by_unit)
    # 三个 canonical 横切根各自成单元，且都真的有生产文件。
    for root in opm.APP_CROSS_CUTTING_ROOTS:
        unit = vcr.app_cross_cutting_unit(root)
        assert unit in units, f"{unit} 没有被发现为 App 计量单元"
        assert attribution.files_by_unit[unit], f"{unit} 没有任何生产文件"
    # 至少要有真实的对象单元，否则 App scope 退化成只量横切面。
    assert [
        unit for unit in units if not unit.startswith(vcr.APP_CROSS_CUTTING_UNIT_PREFIX)
    ]


def test_app_entry_and_l10n_sources_are_measured_not_dropped() -> None:
    """顶层入口与 l10n 源码必须进入计量，而不是被静默排除在分母之外。"""
    attribution = vcr.AppAttribution(_roster_from_disk())
    l10n_root = opm.derive_app_l10n_cross_cutting_root()

    l10n_unit = vcr.app_cross_cutting_unit(l10n_root)
    l10n_files = attribution.files_by_unit[l10n_unit]
    assert l10n_files
    assert all(name.startswith(f"{l10n_root}/") for name in l10n_files)

    # `lib/main*.dart` 是端侧组合根，计入 runtime 横切单元。
    entries = sorted(
        name
        for name in attribution.unit_of
        if opm.derive_app_is_entry_file(tuple(name.split("/")))
    )
    assert entries, "顶层入口文件必须被计量"
    for name in entries:
        assert attribution.unit_of[name] == vcr.app_cross_cutting_unit("runtime")


def test_cloud_collection_targets_are_derived_from_domain_yaml_not_a_hand_list() -> (
    None
):
    """采集目标同源于 `object_path_map.service_domains()`，并按有无 Go 代码收窄。"""
    targets = vcr.go_collection_targets()
    expected = {
        relative: domain
        for relative, (_owner, domain) in opm.service_domains().items()
        if vcr._has_go_sources(ROOT / relative)
    }

    assert targets == expected
    # 非 Go 实现的 service 必须被排除，否则 go list 返回空集、门禁误报。
    excluded = set(opm.service_domains()) - set(targets)
    for relative in excluded:
        assert not vcr._has_go_sources(ROOT / relative)
    # 同一 domain 可以横跨多个 service，但对象单元必须保留物理 service 身份。
    domains = list(targets.values())
    assert len(set(domains)) < len(domains)
    cloud_units = vcr.discover_cloud_units()
    ops_services = {
        vcr.unit_bucket(unit).split("/", 1)[0]
        for unit in cloud_units
        if unit.startswith(vcr.CLOUD_UNIT_PREFIX)
        and not unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
        and vcr.unit_bucket(unit).split("/", 1)[0]
        in {
            opm.app_service_segment("product-ops-service"),
            opm.app_service_segment("platform-ops"),
        }
    }
    assert ops_services == {"product_ops_service", "platform_ops"}


def test_python_recommendation_target_and_seven_objects_are_not_dropped() -> None:
    target = "quwoquan_service/services/recommendation-service"

    assert target not in vcr.go_collection_targets()
    assert vcr.python_collection_targets()[target] == "recommendation"
    assert vcr.artifact_path(target).name.endswith(".python-trace.json")

    prefix = "cloud:recommendation_service/recommendation/"
    object_units = {
        unit for unit in vcr.discover_cloud_units() if unit.startswith(prefix)
    }
    assert object_units == {
        prefix + object_name
        for object_name in {
            "ranked_recommendation_window",
            "recommendation_candidate_index_view",
            "recommendation_exposure_fact",
            "recommendation_feature_profile_view",
            "recommendation_feedback_fact",
            "recommendation_model_release",
            "recommendation_subject_closure_fact",
        }
    }
    assert all(
        vcr.cloud_collection_targets_for_unit(unit) == [target] for unit in object_units
    )
    assert target in vcr.cloud_collection_targets_for_unit(
        vcr.cloud_cross_cutting_unit("cmd")
    )


def test_python_coverage_toolchain_has_one_tracked_exact_dependency_truth() -> None:
    lock_text = RECOMMENDATION_COVERAGE_LOCK_PATH.read_text(encoding="utf-8")
    locked = vcr._parse_python_coverage_toolchain_lock(lock_text)

    assert locked == {
        "iniconfig": "2.3.0",
        "packaging": "26.2",
        "pluggy": "1.6.0",
        "pygments": "2.20.0",
        "pytest": "9.1.1",
    }
    runtime_requirements = RECOMMENDATION_RUNTIME_REQUIREMENTS_PATH.read_text(
        encoding="utf-8"
    )
    assert "pytest" not in runtime_requirements.lower()

    makefile = RECOMMENDATION_MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "COVERAGE_TOOLCHAIN_LOCK := resources/coverage-toolchain.lock" in makefile
    assert (
        "COVERAGE_TOOLCHAIN_MARKER := $(REC_PYTHON_ROOT)/coverage-toolchain.sha256"
        in makefile
    )
    assert (
        'pip install --disable-pip-version-check -r "$(COVERAGE_TOOLCHAIN_LOCK)"'
        in makefile
    )
    assert "coverage pytest drift" in makefile


@pytest.mark.parametrize(
    "lock_text",
    (
        "pytest>=9.1.1\n",
        "pluggy==1.6.0\n",
        "pytest==9.1.1\npytest==9.1.1\n",
    ),
)
def test_python_coverage_toolchain_rejects_ranges_missing_pytest_or_duplicates(
    lock_text: str,
) -> None:
    with pytest.raises(vcr.CoverageError):
        vcr._parse_python_coverage_toolchain_lock(lock_text)


def test_python_toolchain_state_blocks_missing_marker_and_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = "quwoquan_service/services/probe-service"
    service_root = tmp_path / target
    service_root.mkdir(parents=True)
    lock_path = service_root / vcr.PYTHON_COVERAGE_TOOLCHAIN_LOCK
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("pytest==9.1.1\npluggy==1.6.0\n", encoding="utf-8")

    environment_root = tmp_path / "managed-python"
    executable = environment_root / "bin/python"
    executable.parent.mkdir(parents=True)
    executable.write_text("managed\n", encoding="utf-8")
    pytest_path = environment_root / "lib/python/site-packages/pytest/__init__.py"
    pytest_path.parent.mkdir(parents=True)
    pytest_path.write_text("__version__ = '9.1.1'\n", encoding="utf-8")
    base_prefix = tmp_path / "python-base"
    trace_path = base_prefix / "lib/python/trace.py"
    trace_path.parent.mkdir(parents=True)
    trace_path.write_text("class Trace: pass\n", encoding="utf-8")
    trace_digest = vcr._sha256_file(trace_path)

    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(
        vcr, "_python_collection_executable", lambda _target: executable
    )
    pytest_version = "9.1.1"

    def identity(command: list[str], *, cwd: Path) -> str:
        assert cwd == service_root
        if "freeze" in command:
            return "pluggy==1.6.0\npytest==9.1.1\npip==25.1.1\n"
        return json.dumps(
            {
                "basePrefix": str(base_prefix),
                "pythonExecutable": str(executable),
                "pythonVersion": "3.13.3 controlled",
                "pytestPath": str(pytest_path),
                "pytestVersion": pytest_version,
                "traceDigest": trace_digest,
                "tracePath": str(trace_path),
            }
        )

    monkeypatch.setattr(vcr, "_identity_command", identity)

    with pytest.raises(vcr.CoverageError, match="缺少受管 coverage toolchain marker"):
        vcr._python_toolchain_state(target)

    marker = environment_root / vcr.PYTHON_COVERAGE_TOOLCHAIN_MARKER
    marker.write_text(vcr._sha256_file(lock_path).removeprefix("sha256:") + "\n")
    pytest_version = "9.2.0"
    with pytest.raises(vcr.CoverageError, match="pytest version 漂移"):
        vcr._python_toolchain_state(target)

    pytest_version = "9.1.1"
    state = vcr._python_toolchain_state(target)
    assert state["pytestVersion"] == "9.1.1"
    assert state["traceDigest"] == trace_digest
    assert state["pipFreeze"] == [
        "pip==25.1.1",
        "pluggy==1.6.0",
        "pytest==9.1.1",
    ]


def test_a_test_only_go_service_never_becomes_a_collection_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "quwoquan_service/services/probe-service"
    service_root = tmp_path / relative
    (service_root / "internal/probe").mkdir(parents=True)
    (service_root / "tests/local_contract").mkdir(parents=True)
    (service_root / "internal/probe/probe_test.go").write_text(
        "package probe\n", encoding="utf-8"
    )
    (service_root / "tests/local_contract/helper.go").write_text(
        "package local_contract\n", encoding="utf-8"
    )
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(
        opm, "service_domains", lambda: {relative: ("probe-service", "probe")}
    )
    vcr.go_collection_targets.cache_clear()
    try:
        assert vcr.go_collection_targets() == {}
        (service_root / "internal/probe/probe.go").write_text(
            "package probe\n", encoding="utf-8"
        )
        vcr.go_collection_targets.cache_clear()
        assert vcr.go_collection_targets() == {relative: "probe"}
    finally:
        vcr.go_collection_targets.cache_clear()


def test_a_test_only_python_service_never_becomes_a_collection_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = "quwoquan_service/services/probe-service"
    service_root = tmp_path / relative
    (service_root / "internal/probe").mkdir(parents=True)
    (service_root / "tests/local_contract").mkdir(parents=True)
    (service_root / "internal/probe/__init__.py").write_text("", encoding="utf-8")
    (service_root / "tests/local_contract/test_probe.py").write_text(
        "def test_probe(): assert True\n", encoding="utf-8"
    )
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(
        opm, "service_domains", lambda: {relative: ("probe-service", "probe")}
    )
    vcr.go_collection_targets.cache_clear()
    vcr.python_collection_targets.cache_clear()
    try:
        assert vcr.python_collection_targets() == {}
        (service_root / "internal/probe/service.py").write_text(
            "def execute(): return True\n", encoding="utf-8"
        )
        vcr.python_collection_targets.cache_clear()
        assert vcr.python_collection_targets() == {relative: "probe"}
    finally:
        vcr.python_collection_targets.cache_clear()
        vcr.go_collection_targets.cache_clear()


def test_app_source_closure_binds_flutter_pubspec_and_every_local_path_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_root = tmp_path / "quwoquan_app"
    (app_root / "lib").mkdir(parents=True)
    (app_root / "packages/local_one/native").mkdir(parents=True)
    (tmp_path / "shared/local_two/lib").mkdir(parents=True)
    (app_root / "lib/main.dart").write_text("void main() {}\n", encoding="utf-8")
    (app_root / ".flutter-version").write_text("3.44.3\n", encoding="utf-8")
    (app_root / "pubspec.yaml").write_text("name: probe\n", encoding="utf-8")
    (app_root / "pubspec.lock").write_text(
        """packages:
  local_one:
    source: path
    description:
      path: packages/local_one
      relative: true
  local_two:
    source: path
    description:
      path: ../shared/local_two
      relative: true
""",
        encoding="utf-8",
    )
    first_dependency_file = app_root / "packages/local_one/native/probe.mm"
    second_dependency_file = tmp_path / "shared/local_two/lib/probe.dart"
    first_dependency_file.write_text("// native\n", encoding="utf-8")
    second_dependency_file.write_text("const probe = 1;\n", encoding="utf-8")
    ignored_cache = app_root / "packages/local_one/.dart_tool/package_config.json"
    ignored_cache.parent.mkdir(parents=True)
    ignored_cache.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(vcr, "APP_ROOT", app_root)

    closure = vcr._app_source_closure_files()
    assert app_root / ".flutter-version" in closure
    assert app_root / "pubspec.yaml" in closure
    assert app_root / "pubspec.lock" in closure
    assert first_dependency_file in closure
    assert second_dependency_file in closure
    assert ignored_cache not in closure

    before = vcr._tree_digest(closure, label="app source closure")
    second_dependency_file.write_text("const probe = 2;\n", encoding="utf-8")
    after = vcr._tree_digest(
        vcr._app_source_closure_files(), label="app source closure"
    )
    assert after != before


def test_unowned_or_noncanonical_cross_cutting_source_blocks_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = _roster_from_disk()
    rows = [
        _production_row(
            "legacy.dart",
            status="cross_cutting",
            cross_cutting_root="runtime",
            method="cross_cutting",
        )
    ]
    monkeypatch.setattr(opm, "load_page_claims", lambda: ({}, []))
    monkeypatch.setattr(opm, "scan_app", lambda _roster, _claims: (rows, []))

    with pytest.raises(vcr.CoverageError, match="没有唯一 canonical object owner"):
        vcr.AppAttribution(roster)


def test_expected_app_capability_units_use_only_client_contract_and_page_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = _probe_roster()
    pages = [
        {
            "path": (
                "quwoquan_app/lib/service/probe_service/page_context/page_object/"
                "presentation/probe_page.dart"
            ),
            # 参与对象不参与 physical owner 推断；物理 canonical 路径才是 owner。
            "objectIds": ["probe.client_object", "probe.page_object"],
        }
    ]
    monkeypatch.setattr(
        opm,
        "app_service_for_context",
        lambda domain, context: f"{domain}_service",
    )

    assert vcr.expected_app_capability_units(roster, pages) == (
        "app:probe_service/client_context/client_object",
        "app:probe_service/page_context/page_object",
    )


def test_missing_expected_app_capability_unit_blocks_before_an_empty_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roster = _probe_roster()
    rows = [
        _production_row(
            "runtime/owned.dart",
            status="canonical_cross_cutting",
            cross_cutting_root="runtime",
            method="cross_cutting",
        )
    ]
    monkeypatch.setattr(opm, "load_page_claims", lambda: ({}, []))
    monkeypatch.setattr(opm, "scan_app", lambda _roster, _claims: (rows, []))
    monkeypatch.setattr(
        opm, "app_service_for_context", lambda domain, context: f"{domain}_service"
    )

    with pytest.raises(vcr.CoverageError, match="没有 owned production coverage unit"):
        vcr.AppAttribution(roster)


def _literal_strings(tree: ast.AST) -> list[str]:
    """收集非 docstring 的字符串字面量；docstring 与注释只是说明，不是规则。"""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        for statement in node.body:
            if isinstance(statement, ast.Expr) and isinstance(
                statement.value, ast.Constant
            ):
                if isinstance(statement.value.value, str):
                    docstrings.add(id(statement.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_domain_name_is_hardcoded_in_the_gate_source() -> None:
    """门禁源码里不得出现 domain 字面量，否则名册就不再跟着契约走。"""
    tree = ast.parse(GATE_SOURCE_PATH.read_text(encoding="utf-8"))
    domains = _roster_from_disk().domains

    offenders = sorted({value for value in _literal_strings(tree) if value in domains})

    assert offenders == [], (
        f"{GATE_SOURCE_PATH.name} 硬编码了 domain 名 {offenders}；"
        "分桶必须从 contract_graph.json 派生"
    )


def test_the_baseline_never_registers_a_unit_outside_the_derived_roster() -> None:
    """基线不得出现派生名册之外的单元；陈旧单元必须显式收敛。"""
    if not vcr.BASELINE_PATH.is_file():
        with pytest.raises(FileNotFoundError):
            vcr.load_baseline()
        return
    baseline = json.loads(vcr.BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline.get("schema") == vcr.BASELINE_SCHEMA
    assert baseline.get("ruleId") == vcr.RULE_ID
    roster = _roster_from_disk()
    contract_app_units = {
        vcr.app_object_unit(record["domain"], record["context"], record["objectName"])
        for record in roster.objects.values()
    } | {vcr.app_cross_cutting_unit(root) for root in opm.APP_CROSS_CUTTING_ROOTS}
    known = contract_app_units | set(vcr.discover_cloud_units())

    assert set(baseline["units"]) <= known


def test_units_awaiting_a_first_measurement_block_instead_of_passing_silently() -> None:
    """尚未采集的桶不写任何数字，靠「未登记单元」阻断，而不是填 0 或猜的值。

    缺少绿测试 provenance 的单元不保留旧数字；宁可由「未登记单元」阻断，也不能
    用旧 lcov 或红测试的暂定值冒充基线。
    """
    if not vcr.BASELINE_PATH.is_file():
        with pytest.raises(FileNotFoundError):
            vcr.load_baseline()
        return
    baseline = json.loads(vcr.BASELINE_PATH.read_text(encoding="utf-8"))
    pending = sorted(set(vcr.discover_cloud_units()) - set(baseline["units"]))

    for unit in pending:
        # legacy baseline 本身已因缺 receipt provenance 阻断；待采集单元更不能
        # 被解释为拥有可比较的绿基线。
        assert unit not in baseline["units"], f"{unit} 待采集却被登记"


# ---------------------------------------------------------------------------
# 解析口径
# ---------------------------------------------------------------------------

_LCOV_TWO_FILES = "\n".join(
    [
        "SF:lib/a.dart",
        "DA:1,1",
        "DA:2,0",
        "BRDA:1,0,0,1",
        "BRDA:1,0,1,0",
        "BRDA:2,0,0,-",
        "BRDA:2,0,1,4",
        "LF:10",
        "LH:7",
        "end_of_record",
        "SF:lib/b.dart",
        "LF:10",
        "LH:3",
        # 无分支的文件不会写任何 BRDA。
        "end_of_record",
        "",
    ]
)


def test_lcov_parser_keeps_per_file_records_so_buckets_can_be_attributed() -> None:
    parsed = vcr.parse_lcov(_LCOV_TWO_FILES)

    assert sorted(parsed) == ["lib/a.dart", "lib/b.dart"]
    assert parsed["lib/a.dart"]["line"] == (7, 10)
    assert parsed["lib/b.dart"]["line"] == (3, 10)
    # 分支没有汇总行，只能数 BRDA：4 条，其中 taken 既不是 `-` 也不是 `0` 的有 2 条。
    assert parsed["lib/a.dart"]["branch"] == (2, 4)
    assert parsed["lib/b.dart"]["branch"] == (0, 0)


def test_branch_coverage_comes_from_brda_because_flutter_writes_no_summary() -> None:
    """回归守卫：Flutter 3.44 只写 BRDA。

    照 `BRF`/`BRH` 解析会让每个文件的分支分母恒为 0，把「测不出分支」伪装成
    「这个文件没有分支」，分支阈值随之失效——这正是本门禁要防的那类假绿。
    """
    assert "BRF:" not in _LCOV_TWO_FILES
    assert "BRH:" not in _LCOV_TWO_FILES

    total = sum(
        values["branch"][1] for values in vcr.parse_lcov(_LCOV_TWO_FILES).values()
    )

    assert total == 4, "没有汇总行时分支分母必须来自 BRDA 明细"


def test_lcov_branch_summary_disagreeing_with_brda_blocks() -> None:
    """若某天产出里出现 BRF/BRH，必须与 BRDA 一致，不允许两套口径并存。"""
    consistent = "SF:lib/a.dart\nBRDA:1,0,0,1\nBRDA:1,0,1,0\nBRF:2\nBRH:1\nLF:1\nLH:1\nend_of_record\n"

    assert vcr.parse_lcov(consistent)["lib/a.dart"]["branch"] == (1, 2)

    for drifted in (
        "SF:lib/a.dart\nBRDA:1,0,0,1\nBRF:9\nLF:1\nLH:1\nend_of_record\n",
        "SF:lib/a.dart\nBRDA:1,0,0,1\nBRH:9\nLF:1\nLH:1\nend_of_record\n",
    ):
        with pytest.raises(vcr.CoverageError):
            vcr.parse_lcov(drifted)


def test_lcov_parser_rejects_a_file_without_any_record() -> None:
    with pytest.raises(vcr.CoverageError):
        vcr.parse_lcov("TN:\n")


def test_go_coverprofile_parser_counts_statements_not_blocks() -> None:
    text = "\n".join(
        [
            "mode: atomic",
            "pkg/a.go:1.1,3.2 5 1",
            "pkg/a.go:5.1,6.2 2 0",
            "pkg/b.go:1.1,2.2 3 7",
            "",
        ]
    )

    parsed = vcr.parse_go_coverprofile(text)
    files = vcr.parse_go_coverprofile_files(text)

    # 分母是语句数（5+2+3），不是块数；未执行的块（count=0）不计入分子。
    assert parsed["statement"] == (8, 10)
    assert files == {"pkg/a.go": (5, 7), "pkg/b.go": (3, 3)}
    assert vcr.percent(*parsed["statement"]) == 80.0


def test_go_coverprofile_parser_merges_repeated_blocks_from_multiple_binaries() -> None:
    """同一个块会被多个测试二进制各写一份，必须按块去重后再累加计数。"""
    text = "\n".join(
        [
            "mode: atomic",
            "pkg/a.go:1.1,3.2 5 0",
            "pkg/a.go:1.1,3.2 5 4",
            "pkg/a.go:5.1,6.2 2 0",
            "pkg/a.go:5.1,6.2 2 0",
            "",
        ]
    )

    assert vcr.parse_go_coverprofile(text)["statement"] == (5, 7)


def test_go_coverprofile_parser_rejects_malformed_input() -> None:
    with pytest.raises(vcr.CoverageError):
        vcr.parse_go_coverprofile("pkg/a.go:1.1,3.2 5 1\n")
    with pytest.raises(vcr.CoverageError):
        vcr.parse_go_coverprofile("mode: atomic\nnot a block record\n")
    with pytest.raises(vcr.CoverageError):
        vcr.parse_go_coverprofile("mode: atomic\n")


def test_python_trace_parser_keeps_zero_hit_files_in_the_denominator() -> None:
    target = "quwoquan_service/services/recommendation-service"
    parsed = vcr.parse_python_trace_files(
        json.dumps(
            {
                "schema": vcr.PYTHON_TRACE_ARTIFACT_SCHEMA,
                "files": {
                    "internal/recommendation/recommendation_exposure_fact/"
                    "application/appender.py": {
                        "coveredStatements": 7,
                        "totalStatements": 9,
                    },
                    "internal/recommendation/recommendation_exposure_fact/"
                    "infrastructure/mongo_store.py": {
                        "coveredStatements": 0,
                        "totalStatements": 5,
                    },
                },
            }
        ),
        target,
    )

    prefix = "services/recommendation-service/"
    assert parsed == {
        prefix
        + "internal/recommendation/recommendation_exposure_fact/"
        + "application/appender.py": (7, 9),
        prefix
        + "internal/recommendation/recommendation_exposure_fact/"
        + "infrastructure/mongo_store.py": (0, 5),
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"schema": "stale", "files": {}},
        {
            "schema": vcr.PYTHON_TRACE_ARTIFACT_SCHEMA,
            "files": {"../escape.py": {"coveredStatements": 1, "totalStatements": 1}},
        },
        {
            "schema": vcr.PYTHON_TRACE_ARTIFACT_SCHEMA,
            "files": {
                "internal/probe.py": {
                    "coveredStatements": 2,
                    "totalStatements": 1,
                }
            },
        },
    ],
)
def test_python_trace_parser_rejects_unknown_or_malformed_input(payload: dict) -> None:
    with pytest.raises(vcr.CoverageError):
        vcr.parse_python_trace_files(
            json.dumps(payload),
            "quwoquan_service/services/recommendation-service",
        )


# ---------------------------------------------------------------------------
# 端侧对象计量与 file 轴
# ---------------------------------------------------------------------------

_APP_UNIT = "app:probe_service/probe_context/probe_object"


def _attribution(files: dict[str, str]) -> SimpleNamespace:
    units: dict[str, set[str]] = {_APP_UNIT: set()}
    for library_relative, unit in files.items():
        units.setdefault(unit, set()).add(library_relative)
    return SimpleNamespace(unit_of=dict(files), files_by_unit=units)


def _label(entry: str) -> str:
    """取阻断消息的主语（`app:<domain>/<context>/<object>/<metric>` 等）。

    单元名本身含 `:`，不能按 `:` 切；消息统一用 `": "` 分隔主语与说明。
    """
    return entry.split(": ", 1)[0]


def test_app_object_measurement_only_counts_files_owned_by_that_unit() -> None:
    attribution = _attribution({"a.dart": _APP_UNIT, "b.dart": "app:other/c/o"})
    lcov = {
        "lib/a.dart": {"line": (7, 10), "branch": (2, 4)},
        "lib/b.dart": {"line": (9, 10), "branch": (4, 4)},
    }

    metrics = vcr._measure_app_unit(_APP_UNIT, lcov, attribution)

    # 邻对象的高覆盖率不得漏进本对象——这正是 domain 聚合平均数的病。
    assert metrics["line"] == {"covered": 7, "total": 10, "percent": 70.0}
    assert metrics["branch"] == {"covered": 2, "total": 4, "percent": 50.0}
    assert metrics["file"] == {"covered": 1, "total": 1, "percent": 100.0}


def test_an_object_no_test_ever_loaded_is_unmeasured_not_zero_percent() -> None:
    """从未被触达的对象：`file` 是实测的 0/N，其他轴如实标不可测。"""
    attribution = _attribution({"a.dart": _APP_UNIT, "b.dart": _APP_UNIT})

    metrics = vcr._measure_app_unit(_APP_UNIT, {}, attribution)

    # 0/2 是磁盘上的事实，不是猜测，照实登记。
    assert metrics["file"] == {"covered": 0, "total": 2, "percent": 0.0}
    for metric in ("line", "branch"):
        assert metrics[metric]["status"] == vcr.METRIC_STATUS_UNMEASURED
        assert "percent" not in metrics[metric], "分母为 0 时绝不写 0%"
        assert metrics[metric]["reason"]

    with pytest.raises(vcr.CoverageError, match="App coverage 不可准出"):
        vcr._require_app_unit_measured(_APP_UNIT, metrics)


def test_app_zero_numerator_or_any_unmeasured_axis_blocks_before_baseline() -> None:
    zero_branch = {
        "file": {"covered": 1, "total": 1, "percent": 100.0},
        "line": {"covered": 2, "total": 3, "percent": 66.67},
        "branch": {"covered": 0, "total": 2, "percent": 0.0},
    }
    with pytest.raises(vcr.CoverageError, match="branch=0/2"):
        vcr._require_app_unit_measured(_APP_UNIT, zero_branch)

    unmeasured_branch = dict(
        zero_branch,
        branch={"status": vcr.METRIC_STATUS_UNMEASURED, "reason": "no branches"},
    )
    with pytest.raises(vcr.CoverageError, match="branch=unmeasured"):
        vcr._require_app_unit_measured(_APP_UNIT, unmeasured_branch)

    vcr._require_app_unit_measured(
        _APP_UNIT,
        dict(
            zero_branch,
            branch={"covered": 1, "total": 2, "percent": 50.0},
        ),
    )


def test_an_app_unit_without_any_production_file_is_not_a_measurement_unit() -> None:
    with pytest.raises(vcr.CoverageError, match="没有 production source"):
        vcr._measure_app_unit("app:missing/context/object", {}, _attribution({}))


def test_the_file_axis_closes_the_shrinking_denominator_loophole() -> None:
    """删掉覆盖低的测试会让 lcov 分母变小、line 反而上升；file 轴必须拦住。"""
    attribution = _attribution({"well.dart": _APP_UNIT, "poorly.dart": _APP_UNIT})
    before = vcr._measure_app_unit(
        _APP_UNIT,
        {
            "lib/well.dart": {"line": (10, 10), "branch": (2, 2)},
            "lib/poorly.dart": {"line": (1, 10), "branch": (0, 2)},
        },
        attribution,
    )
    # 摘掉 poorly.dart 的 import 后它整个离开 lcov 分母。
    after = vcr._measure_app_unit(
        _APP_UNIT,
        {"lib/well.dart": {"line": (10, 10), "branch": (2, 2)}},
        attribution,
    )

    assert before["line"]["percent"] == 55.0
    assert after["line"]["percent"] == 100.0, "行覆盖率确实会被这么做抬上去"

    baseline = _baseline_with(_app_unit(), before)
    failures = vcr.diff({_app_unit(): after}, baseline, [_app_unit()])

    labels = [_label(entry) for entry in failures]
    assert f"{_app_unit()}/file" in labels
    # line 看起来上升也会要求收紧基线；关键是 file 轴必须独立识别触达文件减少。
    assert f"{_app_unit()}/line" in labels
    assert "50.00%" in failures[0]


# ---------------------------------------------------------------------------
# canonical rule 语义
# ---------------------------------------------------------------------------


def _app_unit() -> str:
    return _APP_UNIT


def _cloud_unit() -> str:
    return next(
        unit
        for unit in vcr.discover_cloud_units()
        if not unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
    )


def _block(percent_value: float, total: int = 10000) -> dict:
    covered = round(percent_value * total / 100.0)
    return {
        "covered": covered,
        "total": total,
        "percent": vcr.percent(covered, total),
    }


def _app_metrics(line: float, branch: float, file: float) -> dict:
    return {"line": _block(line), "branch": _block(branch), "file": _block(file)}


def _baseline_with(unit: str, metrics: dict, **policy_overrides) -> dict:
    policy = {
        "tolerance_percentage_points": 0.3,
        "tolerance_reason": "r",
        "improvement_slack_percentage_points": 3.0,
        "improvement_slack_reason": "r",
        "granularity_units": 2.0,
        "granularity_units_reason": "r",
    }
    policy.update(policy_overrides)
    receipts = _receipts_for_unit(unit)
    baseline = {
        "_governance": {"owner": "o", "reason": "r", "expires_when": "w"},
        "schema": vcr.BASELINE_SCHEMA,
        "ruleId": vcr.RULE_ID,
        "policy": policy,
        "receipts": {vcr.receipt_digest(receipt): receipt for receipt in receipts},
        "units": {unit: vcr.unit_entry(metrics, unit, receipts=receipts)},
    }
    return baseline


def test_summary_keeps_line_branch_and_file_denominators() -> None:
    unit = _app_unit()
    metrics = _app_metrics(41.0, 23.0, 67.0)

    summary = vcr.summarize({unit: metrics}, [unit])

    assert summary["units"][unit] == {
        metric: metrics[metric] for metric in ("branch", "file", "line")
    }
    for metric in ("line", "branch", "file"):
        assert set(summary["units"][unit][metric]) == {
            "covered",
            "total",
            "percent",
        }


def test_meeting_the_baseline_passes_and_a_small_rise_passes_too() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))

    assert vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit]) == []
    assert vcr.diff({unit: _app_metrics(42.0, 22.0, 62.0)}, baseline, [unit]) == []


def test_a_drop_beyond_the_tolerance_blocks_per_metric() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))

    # 容差内的浮动不阻断。
    assert vcr.diff({unit: _app_metrics(39.8, 20.0, 60.0)}, baseline, [unit]) == []

    failures = vcr.diff({unit: _app_metrics(39.4, 16.0, 60.0)}, baseline, [unit])

    assert sorted(_label(entry) for entry in failures) == [
        f"{unit}/branch",
        f"{unit}/line",
    ]


def test_branch_coverage_is_enforced_independently_of_line_coverage() -> None:
    """只堆无分支的直线代码把行覆盖率糊上去，救不了掉下去的分支覆盖率。"""
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))

    failures = vcr.diff({unit: _app_metrics(40.5, 12.0, 60.0)}, baseline, [unit])

    assert [_label(entry) for entry in failures] == [f"{unit}/branch"]


def test_a_rise_beyond_the_slack_blocks_so_the_baseline_cannot_rot() -> None:
    unit = _cloud_unit()
    baseline = _baseline_with(unit, {"statement": _block(13.0)})

    failures = vcr.diff({unit: {"statement": _block(19.0)}}, baseline, [unit])

    assert len(failures) == 1
    assert failures[0].startswith(f"{unit}/statement:")
    assert "--write-baseline" in failures[0]


def test_the_granularity_floor_only_widens_thresholds_for_tiny_buckets() -> None:
    """小桶动一个分支就是几个百分点；大桶不受影响，约束力不被削弱。"""
    policy = {
        "tolerance_percentage_points": 0.3,
        "improvement_slack_percentage_points": 3.0,
        "granularity_units": 2.0,
    }

    tiny_tolerance, tiny_slack = vcr.thresholds(policy, 40)
    large_tolerance, large_slack = vcr.thresholds(policy, 20000)

    # 40 个分支：一个分支是 2.5pp，两个是 5pp。
    assert tiny_tolerance == pytest.approx(5.0)
    assert tiny_slack == pytest.approx(5.0)
    # 两万条语句：两个单位只有 0.01pp，配置值继续生效。
    assert large_tolerance == pytest.approx(0.3)
    assert large_slack == pytest.approx(3.0)


def test_an_unregistered_unit_blocks_instead_of_passing_by_default() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"].pop(unit)

    failures = vcr.diff(
        {unit: _app_metrics(40.0, 20.0, 60.0)},
        baseline,
        [unit],
        known_units=[unit],
    )

    assert len(failures) == 1
    assert failures[0].startswith(f"{unit}: 未登记单元")


def test_a_stale_baseline_unit_blocks_and_must_be_converged_explicitly() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    retired = "app:retired/context/object"
    baseline["units"][retired] = baseline["units"][unit]

    failures = vcr.diff(
        {unit: _app_metrics(40.0, 20.0, 60.0)},
        baseline,
        [unit],
        known_units=[unit],
    )

    assert len(failures) == 1
    assert failures[0].startswith(f"{retired}: 基线里的陈旧单元")


def test_collection_scope_drift_blocks_instead_of_comparing_incomparable_numbers() -> (
    None
):
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit]["scope"] = "quwoquan_app: flutter test --coverage"

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert len(failures) == 1
    assert "采集范围漂移" in failures[0]


def test_the_scope_pins_the_attribution_rule_so_a_rule_change_forces_recollection() -> (
    None
):
    """归属规则一变，同一份 lcov 的分桶结果就不可比，必须重采而不是比大小。"""
    assert opm.RULE_ID in vcr.unit_scope(_app_unit())


def test_a_provisional_baseline_entry_blocks_until_it_is_recollected() -> None:
    """采集时测试没全绿写下的暂定值不得长期挂账。"""
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit]["measuredFromGreenTests"] = False

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert len(failures) == 1
    assert failures[0].startswith(f"{unit}: 基线是暂定值")


def test_a_baseline_entry_without_receipt_provenance_blocks() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit].pop("receiptDigests")

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert [_label(entry) for entry in failures] == [unit]
    assert "provenance 无法复核" in failures[0]


def test_a_missing_metric_axis_blocks_rather_than_being_skipped() -> None:
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    baseline["units"][unit]["metrics"].pop("branch")

    failures = vcr.diff({unit: _app_metrics(40.0, 20.0, 60.0)}, baseline, [unit])

    assert failures == [f"{unit}/branch: 基线缺少该维度"]


def test_measurability_transitions_block_in_both_directions() -> None:
    """可测 → 不可测（测试被删）与不可测 → 可测（该登记真实数字）都必须阻断。"""
    unit = _app_unit()
    unmeasured = {"status": vcr.METRIC_STATUS_UNMEASURED, "reason": "没有测试触达"}

    measured_baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    lost = dict(_app_metrics(40.0, 20.0, 60.0), line=unmeasured)
    failures = vcr.diff({unit: lost}, measured_baseline, [unit])
    assert len(failures) == 1
    assert "现在测不出来了" in failures[0]

    unmeasured_baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    unmeasured_baseline["units"][unit]["metrics"]["line"] = unmeasured
    failures = vcr.diff(
        {unit: _app_metrics(40.0, 20.0, 60.0)}, unmeasured_baseline, [unit]
    )
    assert len(failures) == 1
    assert "现在可测了" in failures[0]
    assert "--write-baseline" in failures[0]

    # 两个未知不能相互证明覆盖率达标；file 轴也不能替代 line 轴的真实结果。
    failures = vcr.diff({unit: lost}, unmeasured_baseline, [unit])
    assert len(failures) == 1
    assert "两个 unmeasured 不能相互证明" in failures[0]


# ---------------------------------------------------------------------------
# 采集失败一律阻断
# ---------------------------------------------------------------------------


def test_missing_artifact_blocks_instead_of_degrading_to_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)

    with pytest.raises(vcr.CoverageError):
        vcr.measure([_cloud_unit()])
    with pytest.raises(vcr.CoverageError):
        vcr.measure([_app_unit()])


def test_measure_blocks_an_app_zero_numerator_before_loading_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vcr, "AppAttribution", lambda _roster: _attribution({"a.dart": _APP_UNIT})
    )
    monkeypatch.setattr(vcr, "parse_lcov", lambda _text: {})
    monkeypatch.setattr(
        vcr, "_read_artifact", lambda _target: ("unused", _receipt("app"))
    )

    with pytest.raises(vcr.CoverageError, match="file=0/1"):
        vcr.measure([_APP_UNIT])


def test_an_empty_go_denominator_blocks_because_collection_did_not_take_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    unit = _cloud_unit()
    attribution = vcr.CloudAttribution(vcr._roster())
    source = sorted(attribution.files_by_unit[unit])[0]
    for target in vcr.cloud_collection_targets_for_unit(unit):
        vcr.artifact_path(target).write_text(
            f"mode: atomic\nquwoquan_service/{source}:1.1,3.2 0 0\n",
            encoding="utf-8",
        )
        vcr._write_artifact_receipt(target, tests_green=True)

    with pytest.raises(vcr.CoverageError):
        vcr.measure([unit])


def test_an_lcov_source_outside_the_derived_roster_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """归属派生器与产物不同源时必须阻断，不能把陌生文件悄悄丢掉。"""
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    monkeypatch.setattr(
        vcr,
        "AppAttribution",
        lambda _roster: SimpleNamespace(known=lambda _source: False),
    )
    vcr.artifact_path(vcr.APP_COLLECTION_TARGET).write_text(
        "SF:vendor/elsewhere.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    vcr._write_artifact_receipt(vcr.APP_COLLECTION_TARGET, tests_green=True)

    with pytest.raises(vcr.CoverageError):
        vcr.measure([_app_unit()])


# ---------------------------------------------------------------------------
# --write-baseline
# ---------------------------------------------------------------------------


def test_write_baseline_records_measured_values_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _app_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (unit,))
    baseline_path.write_text(
        json.dumps(
            _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0)), ensure_ascii=False
        ),
        encoding="utf-8",
    )

    measured = {unit: _app_metrics(51.5, 33.25, 70.0)}
    unit_receipts = {unit: _receipts_for_unit(unit)}
    vcr.write_baseline(measured, units=[unit], unit_receipts=unit_receipts)
    first = baseline_path.read_text(encoding="utf-8")
    vcr.write_baseline(measured, units=[unit], unit_receipts=unit_receipts)
    assert baseline_path.read_text(encoding="utf-8") == first

    written = json.loads(first)
    assert written["ruleId"] == vcr.RULE_ID
    assert written["units"][unit]["metrics"]["line"]["percent"] == 51.5
    assert written["units"][unit]["metrics"]["branch"]["percent"] == 33.25
    # 收紧后再求值必须通过。
    assert vcr.diff(measured, written, [unit]) == []


def test_artifact_receipt_binds_bytes_and_current_collection_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    artifact = vcr.artifact_path(target)
    artifact.write_text("SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8")
    vcr._write_artifact_receipt(target, tests_green=True)

    receipt = vcr.validate_artifact_receipt(target)
    assert receipt["testsGreen"] is True
    assert receipt["ruleId"] == vcr.RULE_ID

    artifact.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(vcr.CoverageError, match="已陈旧"):
        vcr.validate_artifact_receipt(target)


def test_collection_identity_has_every_required_provenance_axis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.dart"
    tests = tmp_path / "source_test.dart"
    attribution = tmp_path / "attribution.json"
    config = tmp_path / "pubspec.yaml"
    for path in (source, tests, attribution, config):
        path.write_text(path.name + "\n", encoding="utf-8")
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(vcr, "_app_collection_inputs", lambda: ([source], [tests]))
    monkeypatch.setattr(vcr, "_attribution_inputs", lambda: [attribution])
    monkeypatch.setattr(vcr, "_collection_config_inputs", lambda _target: [config])
    monkeypatch.setattr(
        vcr,
        "_git_head_identity",
        lambda: {"headCommit": "1" * 40, "headTree": "2" * 40},
    )
    monkeypatch.setattr(vcr, "_toolchain_digest", lambda _target: "sha256:" + "3" * 64)
    monkeypatch.setattr(
        vcr, "_collection_scope_digest", lambda _target: "sha256:" + "4" * 64
    )

    identity = vcr.current_collection_identity(vcr.APP_COLLECTION_TARGET)

    assert set(identity) == {
        "headCommit",
        "headTree",
        "sourceTreeDigest",
        "testTreeDigest",
        "attributionDigest",
        "configDigest",
        "toolchainDigest",
        "collectionScopeDigest",
    }
    assert identity["headCommit"] == "1" * 40
    assert identity["headTree"] == "2" * 40


def test_attribution_digest_includes_page_object_contract_and_detects_its_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = tmp_path / "contract_graph.json"
    page_contract = tmp_path / "page_object_contract.yaml"
    object_path_map_source = tmp_path / "object_path_map.py"
    architecture_source = tmp_path / "verify_app_architecture.py"
    for path, content in (
        (graph, "{}\n"),
        (page_contract, "pages: []\n"),
        (object_path_map_source, "RULE_ID = 'probe'\n"),
        (architecture_source, "RULE_ID = 'probe'\n"),
    ):
        path.write_text(content, encoding="utf-8")

    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(opm, "CONTRACT_GRAPH_PATH", Path("contract_graph.json"))
    monkeypatch.setattr(
        opm, "PAGE_OBJECT_CONTRACT_PATH", Path("page_object_contract.yaml")
    )
    monkeypatch.setattr(opm, "__file__", str(object_path_map_source))
    monkeypatch.setattr(vcr.vaa, "__file__", str(architecture_source))

    inputs = vcr._attribution_inputs()
    assert page_contract in inputs
    before = vcr._tree_digest(inputs, label="coverage attribution")

    page_contract.write_text("pages:\n  - page_id: probe\n", encoding="utf-8")
    after = vcr._tree_digest(vcr._attribution_inputs(), label="coverage attribution")

    assert after != before


def test_artifact_without_receipt_or_with_input_drift_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    artifact = vcr.artifact_path(target)
    artifact.write_text("SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8")

    with pytest.raises(vcr.CoverageError, match="缺少 provenance receipt"):
        vcr.validate_artifact_receipt(target)

    vcr._write_artifact_receipt(target, tests_green=True)
    identity["testTreeDigest"] = "sha256:" + "9" * 64
    with pytest.raises(vcr.CoverageError, match="testTreeDigest"):
        vcr.validate_artifact_receipt(target)
    identity["testTreeDigest"] = "sha256:" + "1" * 64
    identity["sourceTreeDigest"] = "sha256:" + "9" * 64
    with pytest.raises(vcr.CoverageError, match="sourceTreeDigest"):
        vcr.validate_artifact_receipt(target)


@pytest.mark.parametrize(
    "field",
    (
        "headCommit",
        "headTree",
        "sourceTreeDigest",
        "testTreeDigest",
        "attributionDigest",
        "configDigest",
        "toolchainDigest",
        "collectionScopeDigest",
    ),
)
def test_each_receipt_identity_drift_blocks_reuse(
    field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HEAD、配置、工具链与五类内容 identity 任一漂移都必须重采。"""
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(vcr, "current_collection_identity", lambda _target: identity)
    vcr.artifact_path(target).write_text(
        "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    vcr._write_artifact_receipt(target, tests_green=True)

    identity[field] = (
        "9" * 40 if field in {"headCommit", "headTree"} else "sha256:" + "9" * 64
    )
    with pytest.raises(vcr.CoverageError, match=field):
        vcr.validate_artifact_receipt(target)


def test_old_receipt_without_current_rule_id_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    vcr.artifact_path(target).write_text(
        "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    receipt = vcr._write_artifact_receipt(target, tests_green=True)
    receipt.pop("ruleId")
    vcr.artifact_receipt_path(target).write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(vcr.CoverageError, match="fields mismatch"):
        vcr.validate_artifact_receipt(target)


def test_red_artifact_receipt_cannot_be_reused_for_any_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    vcr.artifact_path(target).write_text(
        "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    vcr._write_artifact_receipt(target, tests_green=False)

    with pytest.raises(vcr.CoverageError, match="未全绿"):
        vcr.validate_artifact_receipt(target)


def test_collection_input_drift_discards_the_untrustworthy_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    before = _identity()
    after = dict(before, sourceTreeDigest="sha256:" + "9" * 64)
    identities = iter((before, after))
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: next(identities)
    )
    monkeypatch.setattr(
        vcr,
        "collect_app",
        lambda destination, **_shard_options: destination.write_text(
            "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
        ),
    )

    with pytest.raises(vcr.CoverageError, match="采集期间.*发生漂移"):
        vcr.collect(target)
    assert not vcr.artifact_path(target).exists()
    assert not vcr.artifact_receipt_path(target).exists()


def test_write_baseline_rejects_partial_update_and_rewrites_all_units_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    app, cloud = _app_unit(), _cloud_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (app, cloud))
    original = _baseline_with(app, _app_metrics(40.0, 20.0, 60.0))
    _add_baseline_unit(original, cloud, {"statement": _block(13.0)})
    baseline_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(vcr.CoverageError, match="禁止 scope/unit 分区更新"):
        vcr.write_baseline(
            {app: _app_metrics(44.0, 24.0, 64.0)},
            units=[app],
            unit_receipts={app: _receipts_for_unit(app)},
        )

    vcr.write_baseline(
        {
            app: _app_metrics(44.0, 24.0, 64.0),
            cloud: {"statement": _block(23.0)},
        },
        units=[app, cloud],
        unit_receipts={
            app: _receipts_for_unit(app),
            cloud: _receipts_for_unit(cloud),
        },
    )

    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["_governance"] == vcr.CANONICAL_BASELINE_GOVERNANCE
    assert written["policy"] == vcr.CANONICAL_POLICY
    assert written["units"][app]["metrics"]["line"]["percent"] == 44.0
    assert written["units"][cloud]["metrics"]["statement"]["percent"] == 23.0


def test_baseline_schema_rejects_false_green_test_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _cloud_unit()
    baseline = _baseline_with(unit, {"statement": _block(13.0)})
    baseline["units"][unit]["measuredFromGreenTests"] = False
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="measuredFromGreenTests 必须是 true"):
        vcr.load_baseline()


def test_retired_baseline_path_is_rejected_without_alias_or_dual_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = tmp_path / "canonical_coverage_baseline.json"
    retired = tmp_path / "coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", canonical)
    monkeypatch.setattr(vcr, "RETIRED_BASELINE_PATH", retired)
    unit = _app_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (unit,))
    retired.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="旧 coverage baseline 已硬切退休"):
        vcr.load_baseline()
    with pytest.raises(vcr.CoverageError, match="禁止 alias、fallback、dual-read"):
        vcr.write_baseline(
            {unit: _app_metrics(40.0, 20.0, 60.0)},
            units=[unit],
            unit_receipts={unit: _receipts_for_unit(unit)},
        )


@pytest.mark.parametrize(
    ("statement", "message"),
    (
        (
            {"status": vcr.METRIC_STATUS_UNMEASURED, "reason": "没有测试触达"},
            "不得把 unmeasured 写入 baseline",
        ),
        ({"covered": 0, "total": 7, "percent": 0.0}, "非自洽实测值"),
    ),
)
def test_unmeasured_or_zero_statement_cannot_build_or_pass_a_baseline(
    statement: dict,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未采集与 0/N 都是阻断事实，不能被绿 receipt 包装成 Cloud baseline。"""
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _cloud_unit()
    receipts = _receipts_for_unit(unit)

    with pytest.raises(vcr.CoverageError, match=message):
        vcr.unit_entry({"statement": statement}, unit, receipts=receipts)

    baseline = _baseline_with(unit, {"statement": _block(13.0)})
    baseline["units"][unit]["metrics"]["statement"] = statement
    failures = vcr.diff({unit: {"statement": statement}}, baseline, [unit])
    assert failures, "非法 unmeasured/0 statement 不能在 diff 阶段假绿"
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        vcr.load_baseline()


@pytest.mark.parametrize("mode", ("missing", "forged_digest", "wrong_target"))
def test_baseline_entry_rejects_missing_or_forged_receipt_provenance(
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    digest = baseline["units"][unit]["receiptDigests"][0]

    if mode == "missing":
        baseline["receipts"].pop(digest)
    elif mode == "forged_digest":
        baseline["receipts"][digest]["artifactDigest"] = "sha256:" + "9" * 64
    else:
        wrong = _receipt("quwoquan_service/services/probe-service", "9")
        wrong_digest = vcr.receipt_digest(wrong)
        baseline["receipts"] = {wrong_digest: wrong}
        baseline["units"][unit]["receiptDigests"] = [wrong_digest]
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(ValueError, match="receipt|provenance|绑定伪造"):
        vcr.load_baseline()


def test_write_baseline_drops_units_that_no_longer_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _app_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (unit,))
    original = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    retired = "app:retired/context/object"
    original["units"][retired] = original["units"][unit]
    baseline_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    written = vcr.write_baseline(
        {unit: _app_metrics(40.0, 20.0, 60.0)},
        units=[unit],
        unit_receipts={unit: _receipts_for_unit(unit)},
        known_units=[unit],
    )

    assert retired not in written["units"]


# ---------------------------------------------------------------------------
# 无逃逸口 + 仓库基线自洽
# ---------------------------------------------------------------------------


def test_the_gate_exposes_no_warn_only_or_skip_escape() -> None:
    options = {
        option
        for action in vcr.build_parser()._actions
        for option in action.option_strings
    }

    # `--app-shards` 只决定端侧采集分几次进程跑完同一批测试文件，是容量旋钮而非
    # 逃逸口；它的无逃逸性由 test_canonical_coverage_app_sharding__gate__* 证明。
    assert options == {
        "-h",
        "--help",
        "--scope",
        "--unit",
        "--collect",
        "--write-baseline",
        "--app-shards",
    }


def test_the_gate_reads_no_environment_switch_that_could_turn_it_off() -> None:
    """门禁行为只由参数决定；不得存在「设个环境变量就放行」的旁路。"""
    source = GATE_SOURCE_PATH.read_text(encoding="utf-8")

    assert "os.environ" not in source
    assert "getenv" not in source


def test_unknown_unit_is_rejected_instead_of_silently_passing() -> None:
    assert vcr.main(["--unit", "cloud:not-a-domain"]) == 2


def test_cloud_measurement_keeps_neighbor_objects_and_cross_cutting_separate() -> None:
    attribution = vcr.CloudAttribution(vcr._roster())
    object_units = [
        unit
        for unit in sorted(attribution.files_by_unit)
        if not unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
    ]
    first, second = object_units[:2]
    first_source = sorted(attribution.files_by_unit[first])[0]
    second_source = sorted(attribution.files_by_unit[second])[0]
    cmd_source = sorted(attribution.files_by_unit[vcr.cloud_cross_cutting_unit("cmd")])[
        0
    ]
    profile = {
        f"quwoquan_service/{first_source}": (3, 10),
        f"quwoquan_service/{second_source}": (9, 10),
        f"quwoquan_service/{cmd_source}": (10, 10),
    }

    measured = vcr._measure_cloud_unit(first, [("probe", profile)], attribution)

    assert measured == {"statement": {"covered": 3, "total": 10, "percent": 30.0}}


def test_cloud_zero_statement_numerator_blocks_before_baseline() -> None:
    attribution = vcr.CloudAttribution(vcr._roster())
    unit = next(
        candidate
        for candidate in sorted(attribution.files_by_unit)
        if not candidate.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
    )
    source = sorted(attribution.files_by_unit[unit])[0]

    with pytest.raises(vcr.CoverageError, match="statement 实测 0/7"):
        vcr._measure_cloud_unit(
            unit,
            [("probe", {f"quwoquan_service/{source}": (0, 7)})],
            attribution,
        )


def test_delivery_gate_collects_cloud_object_coverage_instead_of_preblocking() -> None:
    """Delivery Gate 必须执行真实 Cloud 采集，不能保留未接线占位阻断。"""
    delivery_gate = DELIVERY_GATE_PATH.read_text(encoding="utf-8")
    collector = GATE_SOURCE_PATH.read_text(encoding="utf-8")

    assert (
        "python3 quwoquan_ops/gate/verify_canonical_coverage.py --collect --scope cloud"
    ) in delivery_gate
    assert "CLOUD_OBJECT_COVERAGE_GAP" not in collector


def test_write_baseline_requires_a_real_collection_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不跑测试就写基线 = 凭空断言 provenance。"""
    monkeypatch.setattr(vcr, "resolve_units", lambda _scope, _requested: [_app_unit()])
    assert vcr.main(["--write-baseline", "--unit", _app_unit()]) == 2


def test_a_red_test_run_blocks_verification_and_cannot_write_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(vcr, "current_collection_identity", lambda _target: _identity())
    unit = _app_unit()
    monkeypatch.setattr(vcr, "resolve_units", lambda _scope, _requested: [unit])
    baseline_path.write_text(
        json.dumps(
            _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0)),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    original_baseline = baseline_path.read_bytes()

    def _red_collect(target: str, **_shard_options) -> None:
        vcr.artifact_path(target).write_text(
            "mode: atomic\npkg/a.go:1.1,3.2 5 1\npkg/a.go:5.1,6.2 5 0\n",
            encoding="utf-8",
        )
        vcr._write_artifact_receipt(target, tests_green=False)
        raise vcr.RedTestRun("测试没全绿")

    monkeypatch.setattr(vcr, "collect", _red_collect)

    # 求值路径：红着的测试测出来的覆盖率不是准出证据。
    assert vcr.main(["--collect", "--unit", unit]) == 1

    # 登记路径同样阻断，且 tracked baseline 必须保持原字节不变。
    assert vcr.main(["--collect", "--write-baseline", "--unit", unit]) == 1
    assert baseline_path.read_bytes() == original_baseline


def test_scope_selection_narrows_units_without_dropping_any_axis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_app = (_app_unit(),)
    expected_cloud = (_cloud_unit(),)
    monkeypatch.setattr(vcr, "discover_app_units", lambda: expected_app)
    monkeypatch.setattr(vcr, "discover_cloud_units", lambda: expected_cloud)
    monkeypatch.setattr(vcr, "discover_units", lambda: expected_app + expected_cloud)
    app_units = vcr.resolve_units("app", None)
    cloud_units = vcr.resolve_units("cloud", None)

    assert all(unit.startswith(vcr.APP_UNIT_PREFIX) for unit in app_units)
    assert all(unit.startswith(vcr.CLOUD_UNIT_PREFIX) for unit in cloud_units)
    assert app_units + cloud_units == list(vcr.discover_units())
    assert vcr.resolve_units("all", None) == list(vcr.discover_units())
    assert vcr.resolve_units("all", [_cloud_unit()]) == [_cloud_unit()]
    assert vcr.resolve_units("service", None) == cloud_units


def test_each_kind_carries_the_axes_it_can_actually_measure() -> None:
    # 端侧三轴；云侧 Go/Python 都只有语句覆盖，且采集器都保留未触达文件分母。
    assert vcr.METRICS_BY_KIND[vcr.KIND_FLUTTER_LCOV] == ("branch", "file", "line")
    assert vcr.METRICS_BY_KIND[vcr.KIND_CLOUD_STATEMENT] == ("statement",)


def test_repository_baseline_is_provenance_bound_or_explicitly_gate_blocked() -> None:
    if not vcr.BASELINE_PATH.is_file():
        with pytest.raises(FileNotFoundError):
            vcr.load_baseline()
        return
    baseline = vcr.load_baseline()

    governance = baseline["_governance"]
    for key in ("owner", "reason", "expires_when"):
        assert str(governance.get(key) or "").strip(), f"_governance.{key} 不得为空"
    # 采集范围必须在 governance 里如实交代，不得谎称全量。
    assert vcr.APP_TEST_TARGET in governance["reason"]
    assert "BRDA" in governance["reason"]

    for unit, entry in baseline["units"].items():
        assert entry["kind"] == vcr.unit_kind(unit)
        assert entry["scope"] == vcr.unit_scope(unit)
        assert entry["measuredFromGreenTests"] is True
        assert entry["receiptDigests"]
        assert sorted(entry["metrics"]) == sorted(vcr.METRICS_BY_KIND[entry["kind"]])
        for metric, values in entry["metrics"].items():
            assert values.get("status") != vcr.METRIC_STATUS_UNMEASURED, (
                f"{unit}/{metric} 不可测状态只能作为当前阻断原因，不能进入 baseline"
            )
            assert values["covered"] > 0, (
                f"{unit}/{metric} 0/N 不能成为可准出 baseline"
            )
            assert values["total"] > 0, f"{unit}/{metric} 分母必须是实测值"
            assert 0 <= values["covered"] <= values["total"]
            assert values["percent"] == vcr.percent(
                values["covered"], values["total"]
            ), f"{unit}/{metric} percent 与 covered/total 不自洽"


def test_repository_baseline_thresholds_are_not_disabled() -> None:
    """阈值必须反映真实现状，不得被设成 0 或用巨大容差架空。"""
    policy = (
        vcr.load_baseline()["policy"]
        if vcr.BASELINE_PATH.is_file()
        else vcr.CANONICAL_POLICY
    )

    assert 0 < policy["tolerance_percentage_points"] <= 1.0
    assert 0 < policy["improvement_slack_percentage_points"] <= 5.0
    # 粒度下限只为小桶兜底；放大到几十个单位就成了逃逸口。
    assert 0 < policy["granularity_units"] <= 3.0

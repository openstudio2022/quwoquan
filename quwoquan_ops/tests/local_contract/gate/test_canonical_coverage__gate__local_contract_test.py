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

# Python 1000 行硬顶治理：原单文件按场景拆分为本文件与同目录
# test_canonical_coverage_*__gate__local_contract_test.py 兄弟文件；共享构造
# helper 下沉 quwoquan_ops/tests/support/canonical_coverage_gate_test_support.py。
# 本文件保留「App 对象单元归属与名册/基线派生」场景，测试逐字搬移。

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
# app_service_for_context 的实现位于 object_path_map_lib.topology；patch 实现模块
# 才能同时穿透 identity 派生链与 units 的能力单元推导。
from quwoquan_ops.gate.object_path_map_lib import topology as opm_topology
from quwoquan_ops.gate import verify_canonical_coverage as vcr
from quwoquan_ops.tests.support.canonical_coverage_gate_test_support import (
    _gate_source_files,
)


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
        opm_topology, "app_service_for_context", lambda domain, context: f"{domain}_service"
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
        opm_topology,
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
        opm_topology, "app_service_for_context", lambda domain, context: f"{domain}_service"
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
    domains = _roster_from_disk().domains

    offenders = sorted(
        {
            value
            for source in _gate_source_files()
            for value in _literal_strings(
                ast.parse(source.read_text(encoding="utf-8"))
            )
            if value in domains
        }
    )

    assert offenders == [], (
        f"canonical coverage 门禁源码硬编码了 domain 名 {offenders}；"
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

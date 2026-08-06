"""`verify_app_architecture.py`（端侧对象化架构门禁 v1）的本地契约。

本测试锁定三件事：

1. 规则来源单一：顶层白名单与对象归属都必须从 `object_path_map.py` 与
   `quwoquan_app/l10n.yaml` 派生，门禁不得内置第二套路径反推或 domain 名单。
2. ratchet 语义：新违规与陈旧基线条目都必须阻断，`--domain` 只收窄 R2/R3 的比对
   范围，共享的顶层规则在任何 scope 下都全量求值。
3. 仓库当前基线已收敛：门禁在无参数与 `--domain` 下都能跑通。

这里刻意不绑定
`specs/feature-tree/runtime/runtime-control-plane-foundation/`
`domain-onboarding-acceptance-governance/spec.md#gwt-001`：端侧对象化目录尚未搬迁，
本门禁只提供其中的静态约束与基线部分，不代表 OPEN-001 关闭。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_app_architecture as vaa


@pytest.fixture(scope="module")
def roster() -> opm.ObjectRoster:
    return vaa.load_roster()


@pytest.fixture(scope="module")
def evaluation(roster: opm.ObjectRoster) -> dict:
    return vaa._normalized(vaa.evaluate(roster))


# ---------------------------------------------------------------------------
# 规则来源单一
# ---------------------------------------------------------------------------


def test_top_level_whitelist_is_derived_and_not_hardcoded(
    roster: opm.ObjectRoster,
) -> None:
    allowed = vaa.allowed_top_level_directories(roster)

    # 业务部分来自 ContractGraph roster，横切部分来自派生器的唯一两个横切根。
    assert set(roster.domains) <= allowed
    assert set(opm.APP_CROSS_CUTTING_ROOTS) <= allowed
    # l10n 根来自 l10n.yaml 的 arb-dir，不是门禁里写死的字符串。
    assert vaa.l10n_top_level_segment() in allowed
    assert allowed == set(roster.domains) | set(opm.APP_CROSS_CUTTING_ROOTS) | {
        vaa.l10n_top_level_segment()
    }
    # 现状按技术角色分层的顶层目录一律不在白名单内。
    assert not {"ui", "core", "cloud", "components", "app", "application"} & allowed


def test_only_entry_files_are_allowed_at_the_lib_top_level() -> None:
    assert vaa.TOP_LEVEL_ENTRY_RE.match("main.dart")
    assert vaa.TOP_LEVEL_ENTRY_RE.match("main_prod.dart")
    # bootstrap 与 shell 属于 runtime/shell/，不是入口。
    assert not vaa.TOP_LEVEL_ENTRY_RE.match("app_bootstrap.dart")
    assert not vaa.TOP_LEVEL_ENTRY_RE.match("quwoquan_app_shell.dart")


def test_import_resolution_only_keeps_in_package_library_edges() -> None:
    assert (
        vaa._resolve_import_uri("core/providers/app_providers.dart", "../errors/x.dart")
        == "core/errors/x.dart"
    )
    assert (
        vaa._resolve_import_uri("main.dart", "package:quwoquan_app/ui/chat/x.dart")
        == "ui/chat/x.dart"
    )
    # dart:*、其他 package:* 不构成本包内依赖边。
    assert vaa._resolve_import_uri("main.dart", "dart:async") is None
    assert vaa._resolve_import_uri("main.dart", "package:flutter/material.dart") is None


def test_target_root_folds_object_path_map_claims(roster: opm.ObjectRoster) -> None:
    by_domain: dict[str, str] = {}
    for object_id, record in sorted(roster.objects.items()):
        by_domain.setdefault(record["domain"], object_id)
    first_domain, second_domain = sorted(by_domain)[:2]

    assert vaa.derive_target_root(
        {"objectId": by_domain[first_domain], "domain": first_domain}, roster
    ) == ("domain", first_domain)
    # 只能反推到 bounded context / domain 时，仍按该 domain 计。
    assert vaa.derive_target_root({"contextIds": [f"{first_domain}.x"]}, roster) == (
        "domain",
        first_domain,
    )
    assert vaa.derive_target_root({"domains": [second_domain]}, roster) == (
        "domain",
        second_domain,
    )
    # 跨 domain 的歧义绝不代替业务择一。
    assert vaa.derive_target_root(
        {"objectIds": [by_domain[first_domain], by_domain[second_domain]]}, roster
    ) == ("unresolved", None)
    assert vaa.derive_target_root({"crossCuttingRoot": "design_system"}, roster) == (
        "cross_cutting",
        "design_system",
    )
    assert vaa.derive_target_root({}, roster) == ("unresolved", None)


def test_composition_root_exemption_is_limited_to_entry_and_runtime_di() -> None:
    composition_target = opm.derive_app_cross_cutting_target_path(
        "runtime", ("core", "di", "app_production_composition.dart")
    )
    # 例外范围由派生出的目标路径决定，不是另写一份现状路径名单。
    assert composition_target == (
        "quwoquan_app/lib/runtime/di/app_production_composition.dart"
    )
    assert vaa.is_composition_root(
        "core/di/app_production_composition.dart", composition_target
    )
    assert vaa.is_composition_root("main.dart", "quwoquan_app/lib/runtime/main.dart")
    # 已经搬到目标形态的组合根：派生目标会被再套一层 `runtime/`，必须按物理路径判定。
    assert vaa.is_composition_root(
        "runtime/di/content_dependencies.dart",
        opm.derive_app_cross_cutting_target_path(
            "runtime", ("runtime", "di", "content_dependencies.dart")
        ),
    )

    provider_target = opm.derive_app_cross_cutting_target_path(
        "runtime", ("core", "providers", "app_providers.dart")
    )
    assert not vaa.is_composition_root(
        "core/providers/app_providers.dart", provider_target
    )
    assert not vaa.is_composition_root(
        "app_bootstrap.dart", "quwoquan_app/lib/runtime/app_bootstrap.dart"
    )


def test_recorded_reverse_import_edges_stay_within_the_derived_direction(
    evaluation: dict,
    roster: opm.ObjectRoster,
) -> None:
    """每条记录在案的违规边都必须是「横切面 → 业务对象」，方向不得反着记。"""
    index = vaa.AppSourceIndex(roster)

    checked = 0
    for domain, section in evaluation["domains"].items():
        for edge in section[vaa.RULE_TARGET_REVERSE_IMPORT]:
            source, target = edge.split(" -> ")
            assert index.target_root[source][0] == "cross_cutting"
            assert index.target_root[target] == ("domain", domain)
            assert source not in index.composition_root
            checked += 1
    assert checked > 0


# ---------------------------------------------------------------------------
# ratchet 语义
# ---------------------------------------------------------------------------


def _document(shared: list[str], domains: dict[str, list[str]]) -> dict:
    return vaa._normalized(
        {
            "shared": {vaa.RULE_TOP_LEVEL: shared},
            "domains": {
                domain: {vaa.RULE_TARGET_REVERSE_IMPORT: edges}
                for domain, edges in domains.items()
            },
        }
    )


def test_ratchet_blocks_both_new_violations_and_stale_baseline_entries() -> None:
    baseline = _document(["ui/"], {"content": ["runtime/a.dart -> content/b.dart"]})
    current = _document(
        ["ui/", "legacy/"], {"content": ["runtime/a.dart -> content/c.dart"]}
    )

    new_violations, stale_entries = vaa.diff(current, baseline, None)

    assert new_violations == [
        f"{vaa.RULE_TOP_LEVEL}: legacy/",
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: runtime/a.dart -> content/c.dart",
    ]
    # 违规消失后必须显式收敛基线，不允许长期挂账。
    assert stale_entries == [
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: runtime/a.dart -> content/b.dart"
    ]
    assert vaa.diff(baseline, baseline, None) == ([], [])


def test_domain_scope_narrows_domain_rules_but_keeps_the_shared_top_level_rule() -> None:
    baseline = _document([], {})
    current = _document(
        ["legacy/"],
        {
            "content": ["runtime/a.dart -> content/b.dart"],
            "chat": ["runtime/a.dart -> chat/b.dart"],
        },
    )

    new_violations, _ = vaa.diff(current, baseline, "content")

    assert new_violations == [
        f"{vaa.RULE_TOP_LEVEL}: legacy/",
        f"{vaa.RULE_TARGET_REVERSE_IMPORT}[content]: runtime/a.dart -> content/b.dart",
    ]


def test_domain_scoped_baseline_write_preserves_other_domains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "app_architecture_baseline.json"
    monkeypatch.setattr(vaa, "BASELINE_PATH", baseline_path)

    original = _document(
        ["ui/"],
        {
            "content": ["runtime/a.dart -> content/b.dart"],
            "chat": ["runtime/a.dart -> chat/b.dart"],
        },
    )
    vaa.write_baseline(original, domain=None)
    first = baseline_path.read_text(encoding="utf-8")
    vaa.write_baseline(original, domain=None)
    assert baseline_path.read_text(encoding="utf-8") == first

    fixed_content = _document(["ui/"], {"chat": ["runtime/a.dart -> chat/b.dart"]})
    vaa.write_baseline(fixed_content, domain="content")

    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["ruleId"] == vaa.RULE_ID
    assert "content" not in written["domains"]
    # 其他并行流的分区与共享分区不得被顺带改写。
    assert written["domains"]["chat"][vaa.RULE_TARGET_REVERSE_IMPORT] == [
        "runtime/a.dart -> chat/b.dart"
    ]
    assert written["shared"][vaa.RULE_TOP_LEVEL] == ["ui/"]


def test_unknown_domain_is_rejected_instead_of_silently_passing() -> None:
    assert vaa.main(["--domain", "not_a_domain"]) == 2


# ---------------------------------------------------------------------------
# 仓库当前基线已收敛
# ---------------------------------------------------------------------------


def test_repository_baseline_is_converged_and_domain_scope_runs(
    evaluation: dict,
) -> None:
    assert vaa.main([]) == 0
    assert vaa.main(["--domain", "content"]) == 0

    recorded = vaa.load_baseline()
    assert recorded["ruleId"] == vaa.RULE_ID
    assert vaa._normalized(recorded) == evaluation


def test_evaluation_is_idempotent(roster: opm.ObjectRoster, evaluation: dict) -> None:
    assert vaa._normalized(vaa.evaluate(roster)) == evaluation

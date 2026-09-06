# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/spec.md#sit-001
"""棘轮基线治理留痕门禁的行为契约。

重点不是「字段齐不齐」，而是换度量口径这条路必须留下痕迹：换口径能让新旧数字
不可比、漂移重新归零、门禁全程显示绿色，是这类基线唯一真正的逃逸方式。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_ratchet_baseline_governance as gate

COMPLETE = {
    "owner": "runtime-client-foundation",
    "reason": "debt may only decrease",
    "expires_when": "count reaches zero",
    "measure": "counts X under lib/**",
}


def write_json_baseline(path: Path, governance: dict[str, str]) -> None:
    path.write_text(
        json.dumps({"_governance": governance, "some/file.dart": 3}, indent=2),
        encoding="utf-8",
    )


@pytest.fixture
def gate_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    baselines = tmp_path / "quwoquan_ops" / "policies" / "gates"
    baselines.mkdir(parents=True)
    # owner 的有效性由规格树派生，所以隔离树里也必须有一棵，否则测的就不是同一条规则。
    (tmp_path / "specs" / "feature-tree" / "runtime" / COMPLETE["owner"]).mkdir(
        parents=True
    )
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "BASELINE_PATHS", ("quwoquan_ops/policies/gates",))
    return baselines


def test_complete_governance_passes(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_json_baseline(gate_root / "sample_baseline.json", COMPLETE)
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.main() == 0


def test_missing_measure_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    incomplete = {key: value for key, value in COMPLETE.items() if key != "measure"}
    write_json_baseline(gate_root / "sample_baseline.json", incomplete)
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.main() == 1
    assert "治理块缺 measure" in capsys.readouterr().out


def test_changing_measure_without_recording_the_old_one_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """换口径而不留痕必须阻断。

    这正是 assistant 弱类型棘轮漂移到 292/522、以及 ui_map 预算长期假绿时
    发生的事：口径换了，旧口径下的实测值再也无从对照。
    """
    path = gate_root / "sample_baseline.json"
    write_json_baseline(path, {**COMPLETE, "measure": "counts X under lib/new_root/**"})
    head_body = json.dumps({"_governance": COMPLETE, "some/file.dart": 3})
    monkeypatch.setattr(gate, "head_revision", lambda _: head_body)

    assert gate.main() == 1
    output = capsys.readouterr().out
    assert "measure 相对 HEAD 已变更" in output
    assert "superseded_measure" in output


def test_changing_measure_with_the_old_one_recorded_passes(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = gate_root / "sample_baseline.json"
    write_json_baseline(
        path,
        {
            **COMPLETE,
            "measure": "counts X under lib/new_root/**",
            "superseded_measure": "scanned lib/old_root, which no longer exists; "
            "the count silently fell to 0. Re-measured at 69.",
        },
    )
    head_body = json.dumps({"_governance": COMPLETE, "some/file.dart": 3})
    monkeypatch.setattr(gate, "head_revision", lambda _: head_body)

    assert gate.main() == 0


def test_first_time_measure_is_not_treated_as_a_change(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HEAD 尚未声明口径时补上 measure，不该被当成换口径。"""
    write_json_baseline(gate_root / "sample_baseline.json", COMPLETE)
    without_measure = {key: value for key, value in COMPLETE.items() if key != "measure"}
    head_body = json.dumps({"_governance": without_measure, "some/file.dart": 3})
    monkeypatch.setattr(gate, "head_revision", lambda _: head_body)

    assert gate.main() == 0


def test_yaml_governance_block_is_parsed(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (gate_root / "sample_ratchet.yaml").write_text(
        "schema: sample\n"
        "governance:\n"
        "  owner: repository-architecture\n"
        "  reason: debt may only decrease\n"
        "  expires_when: entries is empty\n"
        "  measure: |\n"
        "    counts Y across the tree and blocks when the total grows.\n"
        "entries: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.main() == 0


def test_yaml_allowance_cannot_raise_or_add_path_debt(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    path = gate_root / "sample_allowlist.yaml"
    path.write_text(
        """governance:
  owner: repository-architecture
  reason: debt may only decrease
  expires_when: allow is empty
  measure: max_lines by path
allow:
- path: some/file.dart
  max_lines: 1002
- path: another/file.dart
  max_lines: 1001
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate,
        "head_revision",
        lambda _: """governance:
  owner: repository-architecture
  reason: debt may only decrease
  expires_when: allow is empty
  measure: max_lines by path
allow:
- path: some/file.dart
  max_lines: 1001
""",
    )

    assert gate.main() == 1
    output = capsys.readouterr().out
    assert "some/file.dart::max_lines: 1001 -> 1002" in output
    assert "another/file.dart::max_lines: 0 -> 1001" in output

def test_manifests_and_policies_are_out_of_scope(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不承载可增长计数的清单不该被拖进棘轮治理。"""
    (gate_root / "settings_canonical_manifest.yaml").write_text(
        "pages:\n  - path: a.dart\n", encoding="utf-8"
    )
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.main() == 0


def test_an_owner_nobody_can_be_held_to_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """写一个看起来像 owner 的字符串必须被拦下。

    垂类棘轮的 owner 长期写着 `cross-domain-architecture`，那个名字在规格树里根本
    不存在 —— 字段填了，责任却落不到任何人身上。
    """
    write_json_baseline(
        gate_root / "sample_baseline.json", {**COMPLETE, "owner": "nobody-at-all"}
    )
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.main() == 1
    assert "无法追责的 owner" in capsys.readouterr().out


def test_a_horizontal_governance_function_is_a_valid_owner(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """门禁耗时、仓库结构这类债归职能而非产品节点，硬塞节点只会造成错误归属。"""
    write_json_baseline(
        gate_root / "sample_baseline.json", {**COMPLETE, "owner": "delivery-gate"}
    )
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.main() == 0


def test_every_real_baseline_in_the_repository_is_governed() -> None:
    """真实仓库里的棘轮基线必须已经全部留痕，否则这道门只是摆设。"""
    assert gate.main() == 0


def head_with(entries: dict[str, object]) -> str:
    return json.dumps({"_governance": COMPLETE, **entries})


def test_raising_a_debt_count_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """`_governance` 文字写得再完整，也不能替代单调性检查。

    留痕字段齐全时门禁放行，等于把「债只能减」交给作者自觉——而改基线数字恰好是
    最省事的绕过方式。
    """
    path = gate_root / "sample_baseline.json"
    path.write_text(
        json.dumps({"_governance": COMPLETE, "some/file.dart": 4}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate, "head_revision", lambda _: head_with({"some/file.dart": 3})
    )

    assert gate.main() == 1
    output = capsys.readouterr().out
    assert "债务条目相对 HEAD 变大或新增" in output
    assert "some/file.dart: 3 -> 4" in output


def test_lowering_a_debt_count_passes(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = gate_root / "sample_baseline.json"
    path.write_text(
        json.dumps({"_governance": COMPLETE, "some/file.dart": 2}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate, "head_revision", lambda _: head_with({"some/file.dart": 3})
    )

    assert gate.main() == 0


def test_same_file_identity_swap_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """同文件内删一处、换个函数再加一处，总数不变——按文件计数时门禁看不见。"""
    path = gate_root / "sample_baseline.json"
    path.write_text(
        json.dumps(
            {"_governance": COMPLETE, "some/port.go": {"FindLater": 1}}, indent=2
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate,
        "head_revision",
        lambda _: head_with({"some/port.go": {"FindEarlier": 1}}),
    )

    assert gate.main() == 1
    assert "some/port.go::FindLater" in capsys.readouterr().out


def test_adding_a_new_debt_file_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    path = gate_root / "sample_baseline.json"
    path.write_text(
        json.dumps(
            {"_governance": COMPLETE, "some/file.dart": 3, "another/file.dart": 1},
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate, "head_revision", lambda _: head_with({"some/file.dart": 3})
    )

    assert gate.main() == 1
    assert "another/file.dart: 0 -> 1" in capsys.readouterr().out


def test_timing_budget_keys_are_not_treated_as_debt(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """耗时预算的键是场景名而不是文件路径，调高预算不是「债增长」。

    两者形状相同（都是 名字 -> 数字），靠键里有没有 `/` 区分；混判会让预算调整
    被当成债务增长，把门禁变成噪音源。
    """
    path = gate_root / "timing_budget.json"
    path.write_text(
        json.dumps({"_governance": COMPLETE, "cold_start": 900}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        gate, "head_revision", lambda _: head_with({"cold_start": 800})
    )

    assert gate.main() == 0


def test_exact_range_reads_base_and_candidate_git_trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    repo = tmp_path / "repo"
    gate_root = repo / "quwoquan_ops/policies/gates"
    gate_root.mkdir(parents=True)
    (repo / "specs/feature-tree/runtime" / COMPLETE["owner"]).mkdir(parents=True)
    monkeypatch.setattr(gate, "ROOT", repo)
    monkeypatch.setattr(gate, "BASELINE_PATHS", ("quwoquan_ops/policies/gates",))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
    write_json_baseline(gate_root / "sample_baseline.json", COMPLETE)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    (gate_root / "sample_baseline.json").write_text(
        json.dumps({"_governance": COMPLETE, "some/file.dart": 4}, indent=2),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate"], cwd=repo, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    assert gate.main(["--base-sha", base, "--head-sha", head]) == 1
    assert "some/file.dart: 3 -> 4" in capsys.readouterr().out


def test_recursive_baseline_discovery_includes_policies_baselines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path / "quwoquan_ops/policies/baselines/nested/sample_baseline.json"
    baseline.parent.mkdir(parents=True)
    write_json_baseline(baseline, COMPLETE)
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "BASELINE_PATHS", ("quwoquan_ops/policies/baselines",))

    assert gate.baseline_files() == [baseline]


def promotion_policy() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract_id": "promotion-timing-ratchet-v1",
        "governance": {
            "owner": "delivery-gate",
            "reason": "all eligible events",
            "expires_when": "never",
            "measure": "immutable promotionReadyAt to mainReadbackAt measure",
        },
        "metricId": "dev1-main-promotion-ready-to-main-readback",
        "attemptClock": "first_attempt",
        "denominator": "all_eligible_promotion_events",
        "windowAnchorUtc": "1970-01-01T00:00:00Z",
        "windowDays": 14,
        "quantile": "nearest_rank",
        "quantilePercent": 95,
        "roundingSeconds": 60,
        "targetP95Seconds": 300,
        "enforcementBudgetSeconds": 1800,
        "minimumEligibleEvents": 30,
        "consecutiveQualifiedWindows": 2,
        "requiredTimingCompleteness": 1.0,
        "allowedUnclassifiedCancellations": 0,
        "allowedDuplicateEvents": 0,
        "allowedMissingEvidence": 0,
        "classifications": [
            "success", "failure", "infra", "superseded", "unclassified", "incomplete"
        ],
        "monotonic": {
            "upperBoundFields": [
                "enforcementBudgetSeconds", "targetP95Seconds",
                "allowedUnclassifiedCancellations", "allowedDuplicateEvents",
                "allowedMissingEvidence",
            ],
            "lowerBoundFields": [
                "minimumEligibleEvents", "consecutiveQualifiedWindows",
                "requiredTimingCompleteness",
            ],
            "requiredSetFields": ["classifications"],
        },
    }


def write_promotion_policy(path: Path, value: dict[str, object]) -> None:
    import yaml
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def test_promotion_timing_policy_is_validated_by_full_partial_order(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = gate_root / "promotion_timing_ratchet.yaml"
    write_promotion_policy(path, promotion_policy())
    monkeypatch.setattr(gate, "head_revision", lambda _: None)

    assert gate.debt_entries(promotion_policy()) == {}
    assert gate.main() == 0


def test_promotion_timing_budget_raise_blocks(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    path = gate_root / "promotion_timing_ratchet.yaml"
    candidate = promotion_policy()
    candidate["enforcementBudgetSeconds"] = 1801
    write_promotion_policy(path, candidate)
    import yaml
    monkeypatch.setattr(gate, "head_revision", lambda _: yaml.safe_dump(promotion_policy(), sort_keys=False))

    assert gate.main() == 1
    assert "upper-bound field widened" in capsys.readouterr().out


def test_promotion_minimum_events_and_measure_cannot_weaken(
    gate_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import yaml
    for field, value, expected in (
        ("minimumEligibleEvents", 29, "at least 30"),
        ("governance", {**promotion_policy()["governance"], "measure": "changed"}, "measure drifted"),
    ):
        candidate = promotion_policy()
        candidate[field] = value
        write_promotion_policy(gate_root / "promotion_timing_ratchet.yaml", candidate)
        monkeypatch.setattr(gate, "head_revision", lambda _: yaml.safe_dump(promotion_policy(), sort_keys=False))
        assert gate.main() == 1
        assert expected in capsys.readouterr().out

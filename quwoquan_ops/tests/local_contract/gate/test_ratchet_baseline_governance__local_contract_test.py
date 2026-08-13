# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/spec.md#sit-001
"""棘轮基线治理留痕门禁的行为契约。

重点不是「字段齐不齐」，而是换度量口径这条路必须留下痕迹：换口径能让新旧数字
不可比、漂移重新归零、门禁全程显示绿色，是这类基线唯一真正的逃逸方式。
"""
from __future__ import annotations

import json
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

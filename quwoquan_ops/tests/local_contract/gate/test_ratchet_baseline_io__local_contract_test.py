# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/spec.md#sit-001
"""棘轮基线读写的共享契约。

治理块与计数必须住在同一个文件里，否则 owner / 度量口径 / 退役条件跟数字一分家，
换口径重建基线就不再留下任何痕迹。而每个棘轮脚本都带 `--update-baseline`，一次固化
就会把整个文件重写 —— 治理块能不能活过固化，决定了留痕机制是真约束还是摆设。
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_app" / "scripts"))

from _common.ratchet_baseline import load_counts, write_counts  # noqa: E402

GOVERNANCE = {
    "owner": "runtime-client-foundation",
    "reason": "debt may only decrease",
    "expires_when": "count reaches zero",
    "measure": "counts X under lib/**",
}


def test_governance_block_survives_a_baseline_update(tmp_path: Path) -> None:
    path = tmp_path / "sample_baseline.json"
    path.write_text(
        json.dumps({"_governance": GOVERNANCE, "lib/a.dart": 3, "lib/b.dart": 1}),
        encoding="utf-8",
    )

    write_counts(path, {"lib/a.dart": 2})

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["_governance"] == GOVERNANCE
    assert document["lib/a.dart"] == 2
    assert "lib/b.dart" not in document


def test_load_skips_the_governance_block(tmp_path: Path) -> None:
    """治理块不能被当成一个「文件计数为 dict」的条目参与比较。"""
    path = tmp_path / "sample_baseline.json"
    path.write_text(
        json.dumps({"_governance": GOVERNANCE, "lib/a.dart": 3}), encoding="utf-8"
    )

    assert load_counts(path) == {"lib/a.dart": 3}


def test_writing_a_fresh_baseline_needs_no_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "sample_baseline.json"

    write_counts(path, {"lib/a.dart": 1})

    assert load_counts(path) == {"lib/a.dart": 1}


def test_quality_axis_baseline_preserves_an_edited_governance_block(
    tmp_path: Path, monkeypatch
) -> None:
    """写入路径不得用硬编码治理块覆盖已有的那份。

    `_write_baseline` 原先把治理块直接写死在代码里，看上去在维护治理块，实际每次
    `--update-baseline` 都用一份过时副本静默还原编辑——`measure` 就是这样被抹掉的，
    而它正是防止「换口径重建基线」无痕销账的那个字段。
    """
    # 该 gate 与同目录的 lib 平级 import，所以按它自己的方式加载而不是当包导入。
    sys.path.insert(0, str(ROOT / "quwoquan_ops" / "gate" / "scaffold"))
    import verify_quality_axis_coverage as axis

    baseline = tmp_path / "quality_axis_ratchet_baseline.json"
    edited = {**GOVERNANCE, "measure": "口径 A：只数 user_acceptance"}
    baseline.write_text(
        json.dumps({"_governance": edited, "minimumAxisTotals": {"a11y": 1}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(axis, "BASELINE_PATH", baseline)

    axis._write_baseline({"a11y": 5})

    document = json.loads(baseline.read_text(encoding="utf-8"))
    assert document["_governance"] == edited
    assert document["minimumAxisTotals"] == {"a11y": 5}


def test_every_app_ratchet_baseline_keeps_counts_and_governance_together() -> None:
    """真实仓库里的 App 棘轮基线必须已经带上治理块，否则这条约束只是纸面规定。"""
    roots = (
        ROOT / "quwoquan_app" / "scripts" / "runtime" / "observability",
        ROOT / "quwoquan_app" / "scripts" / "runtime" / "page",
    )
    checked = 0
    for root in roots:
        for path in sorted(root.glob("*baseline.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            assert "_governance" in document, f"{path.name} 缺治理块"
            checked += 1
    # 下界只用来证明 glob 路径仍然有效；不锁定基线数量，否则棘轮退役会被这条
    # 断言反向阻止，等于把存量当契约。
    assert checked >= 1

"""内容漂移检测 + golden 闭环 contract tests。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_content_drift__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core import content_drift as cd  # noqa: E402


def test_firing_gates_catches_contact_and_heading():
    article = "## 节点顺序\n\n咨询电话：0836-6966022。"
    fired = cd.firing_gates(article, {"writingIntent": "planning_consultation"}, [])
    assert "contactInfo" in fired
    assert "mechanicalHeading" in fired


def test_drift_report_alerts_on_rate_rise():
    bad = "## 实用信息\n\n电话 13912345678。"
    samples = [{"ref": "r1", "article": bad, "meta": {}}, {"ref": "r2", "article": bad, "meta": {}}]
    baseline = {"firingRates": {"contactInfo": 0.0, "mechanicalHeading": 0.0}}
    rep = cd.drift_report(samples, baseline)
    assert rep["drifted"] is True
    assert any("contactInfo" in a for a in rep["alerts"])
    # 无 baseline → 只快照不告警
    assert cd.drift_report(samples)["drifted"] is False


def test_promote_to_golden_requires_confirmation_and_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        gd = Path(d)
        (gd / "labels.json").write_text(
            json.dumps({"schema": "quwoquan_data.gate_goldenset", "items": []}), encoding="utf-8"
        )
        # 未确认 → 不入集
        res = cd.promote_to_golden(
            gd, file_name="promoted_x.md", article="## 注意事项\n\n电话 010-12345678",
            label="bad", meta={"carrier": "article"}, expect_gates=["mechanicalHeading"], confirmed=False,
        )
        assert res["promoted"] is False
        # 确认 → 入集，写 md + labels
        res2 = cd.promote_to_golden(
            gd, file_name="promoted_x.md", article="## 注意事项\n\n电话 010-12345678",
            label="bad", meta={"carrier": "article"}, expect_gates=["mechanicalHeading"], confirmed=True,
        )
        assert res2["promoted"] is True
        assert (gd / "promoted_x.md").is_file()
        labels = json.loads((gd / "labels.json").read_text(encoding="utf-8"))
        assert any(it["file"] == "promoted_x.md" for it in labels["items"])
        # 幂等：重复晋级不追加
        res3 = cd.promote_to_golden(
            gd, file_name="promoted_x.md", article="...", label="bad", meta={}, confirmed=True,
        )
        assert res3["promoted"] is False and "idempotent" in res3["reason"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content_drift tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

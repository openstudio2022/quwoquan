"""verify_handoff_manifest 的负例合约。

交接单是 HANDOFF 的物理形态；校验器一旦永远转绿，断链与悬空未决项就会
重新以聊天文本形态逃过下一轮 RESOLVE。每类缺陷都必须有能让它变红的负例。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GATE = _REPO_ROOT / "quwoquan_ops/gate/verify_handoff_manifest.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_handoff_manifest", _GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID = """# 轮次交接单

- intent 终版：示例轮次（范围变更：无）
- 新轮触发判定：不触发（依据：判据全绿）

## 产出物

- 实现增量一份 + POST 评审结论

## 未决项去向

- 谓词单轨缺口（一类：已全仓 AST 扫描收敛并加防回潮锁）：转 `OPEN-007`
- 组网知识升格（孤例）：下一工作流 `prd` 承接

## 唯一合法下游

- plan-next；PRE 输入：本单证据链与 OPEN 变化

## 证据链

- `make verify-feature-tree` exit=0 2026-08-25T12:00:00+08:00 abc1234
"""


class HandoffManifestGateTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t1

    def setUp(self) -> None:
        self.module = _load_gate()

    def test_valid_manifest_passes(self) -> None:
        self.assertEqual([], self.module.validate(VALID, "m.md"))

    def test_detects_missing_constitution_section(self) -> None:
        text = VALID.replace("## 唯一合法下游", "## 别的段")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺宪法四项段落「## 唯一合法下游」" in i for i in issues), issues)

    def test_detects_missing_head_field(self) -> None:
        text = VALID.replace("- 新轮触发判定：不触发（依据：判据全绿）", "")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺头部字段「新轮触发判定」" in i for i in issues), issues)

    def test_detects_dangling_pending_item(self) -> None:
        """未决项没有三向裁决就是悬空——历史上缺口悬空到下轮才暴露的主形态。"""
        text = VALID.replace("转 `OPEN-007`", "还没想好怎么办")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("未决项悬空" in i for i in issues), issues)

    def test_detects_pending_item_without_generalization(self) -> None:
        """有裁决但缺「孤例/一类」泛化判定——举一反三必须留痕，不许只靠自觉。"""
        text = VALID.replace(
            "- 组网知识升格（孤例）：下一工作流 `prd` 承接",
            "- 组网知识升格：下一工作流 `prd` 承接",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺泛化判定" in i for i in issues), issues)
        self.assertFalse(any("未决项悬空" in i for i in issues), issues)

    def test_detects_evidence_without_fields(self) -> None:
        """无退出码/时间戳/SHA 的证据无法复跑，只能被转抄——必须拦。"""
        text = VALID.replace(
            "- `make verify-feature-tree` exit=0 2026-08-25T12:00:00+08:00 abc1234",
            "- 测试都跑过了，全绿",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("证据条目缺字段" in i for i in issues), issues)

    def test_detects_empty_evidence_chain(self) -> None:
        text = VALID.replace(
            "- `make verify-feature-tree` exit=0 2026-08-25T12:00:00+08:00 abc1234",
            "",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("证据链为空" in i for i in issues), issues)

    def test_accepts_explicit_no_pending_declaration(self) -> None:
        text = VALID.replace(
            "- 谓词单轨缺口：转 `OPEN-007`\n- 组网知识升格：下一工作流 `prd` 承接",
            "- 无未决项",
        )
        self.assertEqual([], self.module.validate(text, "m.md"))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

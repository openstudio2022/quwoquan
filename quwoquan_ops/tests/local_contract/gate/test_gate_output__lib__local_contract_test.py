"""gate_output 统一 GATE_BLOCK 输出 schema 的合约。

门禁失败信息一旦回退为纯自由文本，AI 消费与自动修复闭环就失去定位字段。
本合约锁住 schema 字段齐全、status 推导、path/line 尽力提取三条语义。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LIB = _REPO_ROOT / "quwoquan_ops/cli/lib/gate_output.py"


def _load_lib() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_gate_output", _LIB)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_lib = _load_lib()


class GateOutputSchemaTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001

    def test_finding_extracts_path_and_line_from_message(self) -> None:
        item = _lib.finding(
            "specs/feature-tree/runtime/spec.md:42 首行必须以 `# L1` 开始"
        )
        self.assertEqual(item["path"], "specs/feature-tree/runtime/spec.md")
        self.assertEqual(item["line"], 42)

    def test_finding_without_path_keeps_null_not_fabricated(self) -> None:
        item = _lib.finding("禁止全局注册表回潮")
        self.assertIsNone(item["path"])
        self.assertIsNone(item["line"])
        self.assertIsNone(item["fix"])
        self.assertIsNone(item["truth_ref"])

    def test_explicit_fields_win_over_extraction(self) -> None:
        item = _lib.finding(
            "quwoquan_ops/gate/x.py 有问题",
            path="quwoquan_ops/gate/y.py",
            fix="改 y.py",
            truth_ref="specs/feature-tree/platform-ops-governance/spec.md#dom-001",
        )
        self.assertEqual(item["path"], "quwoquan_ops/gate/y.py")
        self.assertEqual(item["fix"], "改 y.py")

    def test_emit_block_schema_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = _lib.emit_gate_result(
                "verify-demo", [_lib.finding("quwoquan_app/lib/a.dart 越界")], Path(tmp)
            )
            payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload),
            {"gate", "status", "findings", "generated_at", "head_sha"},
        )
        self.assertEqual(payload["status"], "block")
        self.assertEqual(
            set(payload["findings"][0]),
            {"message", "path", "line", "fix", "truth_ref"},
        )

    def test_emit_pass_when_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = _lib.emit_gate_result("verify-demo", [], Path(tmp))
            payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["findings"], [])
        self.assertTrue(
            out.as_posix().endswith(".qwq_output/env/repo/runs/gate/verify-demo.json")
        )

    def test_emit_never_raises_on_readonly_filesystem(self) -> None:
        """落盘失败不得改变门禁退出语义：只读环境实测曾把通过的门弄挂。"""
        with tempfile.TemporaryDirectory() as tmp:
            readonly_root = Path(tmp) / "readonly-repo"
            readonly_root.mkdir()
            readonly_root.chmod(0o500)
            try:
                out = _lib.emit_gate_result("verify-demo", [], readonly_root)
            finally:
                readonly_root.chmod(0o700)
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()

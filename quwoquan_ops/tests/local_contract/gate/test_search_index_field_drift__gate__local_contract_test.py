"""verify_search_index_field_drift 的解析与 fail-closed 合约。

覆盖：投影器源读取解析（plain 函数与 receiver-qualified `Type.Method`）、
函数体缺失必须 ScanError、lower_camel 缩写词映射、空对象扫描必须 ScanError、
门禁与本测试必须留在 gate 链上。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_search_index_field_drift.py"
GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE = ROOT / "Makefile"

SPEC = importlib.util.spec_from_file_location("verify_search_index_field_drift", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

GO_SOURCE = '''package application

func ProjectDemoToSearchDocument(demo Demo) Document {
\treturn Document{
\t\tTitle: demo.Nickname,
\t\tFields: map[string]string{
\t\t\t"authorId": demo.UserID,
\t\t},
\t}
}

func (event DemoProjectionEvent) Document() Document {
\treturn Document{
\t\tTitle:   event.Nickname,
\t\tSummary: event.Bio,
\t\tFields: map[string]string{
\t\t\t"avatarUrl": event.AvatarURL,
\t\t},
\t}
}
'''


class ProjectorSourceReadContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        target = self.repo_root / "svc/projection.go"
        target.parent.mkdir(parents=True)
        target.write_text(GO_SOURCE, encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def test_plain_function_reads_first_parameter(self) -> None:
        field_keys, selectors = gate.projector_source_reads(
            self.repo_root, "svc/projection.go#ProjectDemoToSearchDocument"
        )
        self.assertIn("authorId", field_keys)
        self.assertIn("Nickname", selectors)
        self.assertIn("UserID", selectors)

    def test_receiver_method_reads_receiver_selectors(self) -> None:
        field_keys, selectors = gate.projector_source_reads(
            self.repo_root, "svc/projection.go#DemoProjectionEvent.Document"
        )
        self.assertIn("avatarUrl", field_keys)
        self.assertIn("Nickname", selectors)
        self.assertIn("Bio", selectors)
        self.assertIn("AvatarURL", selectors)

    def test_missing_body_raises_instead_of_pass(self) -> None:
        with self.assertRaises(gate.ScanError):
            gate.projector_source_reads(
                self.repo_root, "svc/projection.go#GhostEvent.Document"
            )


class LowerCamelContract(unittest.TestCase):
    def test_acronym_forms(self) -> None:
        self.assertEqual(gate.lower_camel("ID"), "id")
        self.assertEqual(gate.lower_camel("UserID"), "userId")
        self.assertEqual(gate.lower_camel("AvatarURL"), "avatarUrl")
        self.assertEqual(gate.lower_camel("Nickname"), "nickname")


class FailClosedContract(unittest.TestCase):
    def test_empty_object_scan_raises(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.object_paths(Path(empty))


class WiringContract(unittest.TestCase):
    def test_gate_is_on_gate_repo_chain(self) -> None:
        self.assertIn(
            "quwoquan_ops/gate/verify_search_index_field_drift.py",
            GATE_REPO.read_text(encoding="utf-8"),
        )

    def test_companion_test_is_executed(self) -> None:
        self.assertIn(Path(__file__).name, MAKEFILE.read_text(encoding="utf-8"))


class LiveRepositoryContract(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        counts, failures = gate.run(ROOT)
        self.assertGreater(counts["objects"], 0)
        self.assertGreater(counts["projectors"], 0)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()

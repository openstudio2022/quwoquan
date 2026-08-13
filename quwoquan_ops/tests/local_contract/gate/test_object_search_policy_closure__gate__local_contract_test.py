"""verify_object_search_policy_closure 的 fail-closed 合约。

覆盖：Go 符号解析（plain 与 receiver-qualified `Type.Method` 两种引用形态）、
空扫描必须 ScanError 而非 PASS、缺 search_policy 声明必须阻断、
门禁与本测试必须留在 gate 链上。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_object_search_policy_closure.py"
GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE = ROOT / "Makefile"

SPEC = importlib.util.spec_from_file_location("verify_object_search_policy_closure", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

GO_SOURCE = '''package application

func ProjectDemoToSearchDocument(demo Demo) Document {
\treturn Document{}
}

func (event DemoProjectionEvent) Document() Document {
\treturn Document{}
}

func (pointer *PointerEvent) Emit() Document {
\treturn Document{}
}
'''


class ResolveGoSymbolContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        target = self.repo_root / "svc/demo.go"
        target.parent.mkdir(parents=True)
        target.write_text(GO_SOURCE, encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def test_plain_function_resolves(self) -> None:
        self.assertIsNone(
            gate.resolve_go_symbol(self.repo_root, "svc/demo.go#ProjectDemoToSearchDocument")
        )

    def test_receiver_qualified_method_resolves(self) -> None:
        self.assertIsNone(
            gate.resolve_go_symbol(self.repo_root, "svc/demo.go#DemoProjectionEvent.Document")
        )

    def test_pointer_receiver_method_resolves(self) -> None:
        self.assertIsNone(
            gate.resolve_go_symbol(self.repo_root, "svc/demo.go#PointerEvent.Emit")
        )

    def test_missing_method_fails(self) -> None:
        problem = gate.resolve_go_symbol(
            self.repo_root, "svc/demo.go#DemoProjectionEvent.Missing"
        )
        self.assertIsNotNone(problem)
        self.assertIn("DemoProjectionEvent", problem)

    def test_wrong_receiver_type_fails(self) -> None:
        problem = gate.resolve_go_symbol(self.repo_root, "svc/demo.go#OtherEvent.Document")
        self.assertIsNotNone(problem)

    def test_missing_file_fails(self) -> None:
        problem = gate.resolve_go_symbol(self.repo_root, "svc/absent.go#Anything")
        self.assertIsNotNone(problem)
        self.assertIn("missing file", problem)

    def test_call_site_is_not_a_definition(self) -> None:
        caller = self.repo_root / "svc/caller.go"
        caller.write_text(
            "package application\n\nfunc use() { _ = event.Document() }\n",
            encoding="utf-8",
        )
        problem = gate.resolve_go_symbol(
            self.repo_root, "svc/caller.go#DemoProjectionEvent.Document"
        )
        self.assertIsNotNone(problem)


class FailClosedContract(unittest.TestCase):
    def test_empty_scan_raises_instead_of_pass(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(gate.ScanError):
                gate.load_objects(Path(empty))

    def test_object_without_search_policy_blocks(self) -> None:
        objects = {
            "content.demo": (
                ROOT / "quwoquan_service/services/x/contracts/content/demo/object.yaml",
                {},
            )
        }
        failures = gate.validate_declarations(ROOT, objects)
        self.assertTrue(any("no search_policy declared" in item for item in failures))

    def test_exposed_none_requires_reason(self) -> None:
        objects = {
            "content.demo": (
                ROOT / "quwoquan_service/services/x/contracts/content/demo/object.yaml",
                {"search_policy": {"exposed": "none"}},
            )
        }
        failures = gate.validate_declarations(ROOT, objects)
        self.assertTrue(any("not_exposed_reason" in item for item in failures))


class WiringContract(unittest.TestCase):
    def test_gate_is_on_gate_repo_chain(self) -> None:
        self.assertIn(
            "quwoquan_ops/gate/verify_object_search_policy_closure.py",
            GATE_REPO.read_text(encoding="utf-8"),
        )

    def test_companion_test_is_executed(self) -> None:
        self.assertIn(Path(__file__).name, MAKEFILE.read_text(encoding="utf-8"))


class LiveRepositoryContract(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        scanned, failures, registrations = gate.run(ROOT)
        self.assertGreater(scanned, 0)
        self.assertGreater(registrations, 0)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()

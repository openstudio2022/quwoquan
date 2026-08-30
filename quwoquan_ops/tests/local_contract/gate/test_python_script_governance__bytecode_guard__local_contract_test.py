# spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-004
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.gate.verify_python_script_governance import derive_report

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
GUARD_CODE = "PYTHON.BYTECODE_GUARD_MISSING"


class PythonScriptGovernanceBytecodeGuardTest(unittest.TestCase):
    """入口必须自行抑制字节码，缓存禁令不依赖调用方环境变量。"""

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def _write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _guard_issue_paths(self) -> set[str]:
        report = derive_report(self.root, ("ops",))
        return {
            str(issue["path"])
            for issue in report["issues"]  # type: ignore[index]
            if issue["code"] == GUARD_CODE  # type: ignore[index]
        }

    def test_entry_importing_repository_without_guard_is_blocked(self) -> None:
        self._write(
            "quwoquan_ops/gate/verify_unguarded.py",
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "ROOT = Path(__file__).resolve().parents[2]\n"
            "if str(ROOT) not in sys.path:\n"
            "    sys.path.insert(0, str(ROOT))\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(0)\n",
        )

        self.assertIn(
            "quwoquan_ops/gate/verify_unguarded.py",
            self._guard_issue_paths(),
        )

    def test_guard_before_first_repository_import_passes(self) -> None:
        self._write(
            "quwoquan_ops/gate/verify_guarded.py",
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "sys.dont_write_bytecode = True\n"
            "\n"
            "ROOT = Path(__file__).resolve().parents[2]\n"
            "if str(ROOT) not in sys.path:\n"
            "    sys.path.insert(0, str(ROOT))\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(0)\n",
        )

        self.assertEqual(set(), self._guard_issue_paths())

    def test_guard_after_the_first_repository_import_is_still_blocked(
        self,
    ) -> None:
        """守卫晚于首次仓内 import 时 pyc 已写出，因此不算满足。"""
        self._write(
            "quwoquan_ops/gate/verify_late_guard.py",
            "import sys\n"
            "\n"
            "from quwoquan_ops.cli.lib import anything\n"
            "\n"
            "sys.dont_write_bytecode = True\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    raise SystemExit(0)\n",
        )

        self.assertIn(
            "quwoquan_ops/gate/verify_late_guard.py",
            self._guard_issue_paths(),
        )

    def test_entry_without_any_repository_import_needs_no_guard(self) -> None:
        """无仓内 import 的入口不可能写出仓内 pyc，不应被要求加守卫。"""
        self._write(
            "quwoquan_ops/gate/verify_standalone.py",
            "import json\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    print(json.dumps({}))\n",
        )

        self.assertEqual(set(), self._guard_issue_paths())

    def test_library_module_without_main_block_is_out_of_scope(self) -> None:
        """非入口由其调用入口的守卫覆盖，重复要求只会制造噪声。"""
        self._write(
            "quwoquan_ops/cli/lib/plain_library.py",
            "import sys\n"
            "\n"
            "from quwoquan_ops.cli.lib import sibling\n"
            "\n"
            "VALUE = sys.maxsize\n",
        )

        self.assertEqual(set(), self._guard_issue_paths())

    def test_repository_entries_all_carry_the_guard(self) -> None:
        """真仓回归：任一入口缺守卫都会让直接调用污染源码树。"""
        report = derive_report(REPOSITORY_ROOT, ("app", "service", "ops", "data"))
        offenders = sorted(
            str(issue["path"])
            for issue in report["issues"]  # type: ignore[index]
            if issue["code"] == GUARD_CODE  # type: ignore[index]
        )

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = ROOT / "quwoquan_app" / "scripts" / "runtime" / "verify_lib_dart_io_budget.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_lib_dart_io_budget", GATE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load gate: {GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LibDartIoBudgetTerminalAllowlistTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_gate()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.app_lib = self.root / "lib"
        self.allowlist = self.root / "lib_dart_io_import_allowlist.yaml"
        self.app_lib.mkdir(parents=True)
        self.module.APP_LIB = self.app_lib
        self.module.ALLOWLIST = self.allowlist

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _run(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", [str(GATE_PATH), *args]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = self.module.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def _write_importer(self, relative_path: str) -> None:
        path = self.app_lib / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import 'dart:io';\n", encoding="utf-8")

    def test_missing_allowlist_is_the_valid_zero_debt_terminal_state(self) -> None:
        self._write_importer("runtime/platform/local_file_gateway.dart")

        result, stdout, stderr = self._run()

        self.assertEqual(result, 0)
        self.assertIn("allowlist=retired, current=0", stdout)
        self.assertEqual(stderr, "")

    def test_retired_allowlist_fails_closed_for_a_new_non_platform_importer(self) -> None:
        self._write_importer("content/content/post/presentation/page.dart")

        result, _, stderr = self._run()

        self.assertEqual(result, 2)
        self.assertIn("allowlist is retired", stderr)
        self.assertIn("new importer: content/content/post/presentation/page.dart", stderr)

    def test_empty_allowlist_file_is_stale_after_debt_reaches_zero(self) -> None:
        self.allowlist.write_text("allowed: []\n", encoding="utf-8")

        result, _, stderr = self._run()

        self.assertEqual(result, 1)
        self.assertIn("stale empty allowlist", stderr)

    def test_write_baseline_removes_the_policy_when_debt_is_zero(self) -> None:
        self.allowlist.write_text("allowed:\n  - stale.dart\n", encoding="utf-8")

        result, stdout, stderr = self._run("--write-baseline")

        self.assertEqual(result, 0)
        self.assertIn("retired empty baseline", stdout)
        self.assertEqual(stderr, "")
        self.assertFalse(self.allowlist.exists())


if __name__ == "__main__":
    unittest.main()

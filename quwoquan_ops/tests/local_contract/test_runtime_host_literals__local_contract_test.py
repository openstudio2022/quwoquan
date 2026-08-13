from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "quwoquan_app/scripts/env/verify_runtime_host_literals.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("runtime_host_literals", VERIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 runtime host literal 门禁")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeHostLiteralsLocalContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = _load_verifier()

    def test_url_shaped_redaction_regex_is_not_treated_as_runtime_host(self) -> None:
        line = r"RegExp(r'(https://[^\s?#]+)\?[^\s#]*')"

        self.assertTrue(
            self.verifier._is_regular_expression_source(
                line,
                line.index("https://"),
            )
        )

    def test_malformed_runtime_url_is_reported_without_verifier_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_lib = Path(temporary_directory)
            source = app_lib / "invalid_host.dart"
            source.write_text(
                "const endpoint = 'https://[not-a-host';\n",
                encoding="utf-8",
            )
            original = self.verifier.APP_LIB
            self.verifier.APP_LIB = app_lib
            try:
                issues = self.verifier.runtime_host_literal_issues()
            finally:
                self.verifier.APP_LIB = original

        self.assertEqual(
            issues,
            ["invalid_host.dart:1: invalid URL literal (https://[not-a-host)"],
        )

    def test_non_allowlisted_runtime_host_remains_a_gate_violation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            app_lib = Path(temporary_directory)
            source = app_lib / "external_host.dart"
            source.write_text(
                "const endpoint = 'https://tracker.example.com/pixel';\n",
                encoding="utf-8",
            )
            original = self.verifier.APP_LIB
            self.verifier.APP_LIB = app_lib
            try:
                issues = self.verifier.runtime_host_literal_issues()
            finally:
                self.verifier.APP_LIB = original

        self.assertEqual(
            issues,
            [
                "external_host.dart:1: tracker.example.com "
                "(https://tracker.example.com/pixel)"
            ],
        )


if __name__ == "__main__":
    unittest.main()

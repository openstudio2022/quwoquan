# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
"""App 错误码断言覆盖棘轮门禁的配套合约。

覆盖 `verify_app_error_code_assertion_coverage.py`：码字面量与 enum 值引用
均计为断言证据、缺失数超过基线即阻断、豁免码不计入缺失、实树缺失数
不超过声明基线。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "error"
    / "verify_app_error_code_assertion_coverage.py"
)

GENERATED_ENUM = """enum ExampleErrorCode {
  exampleNotFound('EXAMPLE.USER.not_found', 'x', 'y', 404, 'surface', 'inlineCard', 0, ''),
  exampleStorageDown('EXAMPLE.SYSTEM.storage_unavailable', 'x', 'y', 503, 'retry', 'snackbar', 5, ''),
}
"""


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_app_error_code_assertion_coverage_for_contract_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppErrorCodeAssertionCoverageContractTest(unittest.TestCase):
    def _run(
        self,
        test_sources: dict[str, str],
        ceiling: int,
        exempt: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        import tempfile

        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated_root = root / "lib/runtime/errors/generated/example"
            generated_root.mkdir(parents=True)
            (generated_root / "example_errors.g.dart").write_text(
                GENERATED_ENUM, encoding="utf-8"
            )
            test_root = root / "test"
            for relative, source in test_sources.items():
                target = test_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            test_root.mkdir(parents=True, exist_ok=True)
            verifier.GENERATED_ROOT = root / "lib/runtime/errors/generated"
            verifier.TEST_ROOT = test_root
            verifier.MISSING_CEILING = ceiling
            verifier.EXEMPT_CODES = exempt or {}
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = verifier.main()
            return code, stdout.getvalue()

    def test_code_literal_counts_as_assertion_evidence(self) -> None:
        code, output = self._run(
            {
                "local_contract/example_test.dart": (
                    "// expects 'EXAMPLE.USER.not_found' and "
                    "'EXAMPLE.SYSTEM.storage_unavailable'\n"
                )
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)
        self.assertIn("missing=0", output)

    def test_enum_value_reference_counts_as_assertion_evidence(self) -> None:
        code, output = self._run(
            {
                "local_contract/example_test.dart": (
                    "expect(code, ExampleErrorCode.exampleNotFound);\n"
                    "expect(code, ExampleErrorCode.exampleStorageDown);\n"
                )
            },
            ceiling=0,
        )
        self.assertEqual(code, 0, output)

    def test_missing_growth_beyond_ceiling_is_blocked(self) -> None:
        code, output = self._run({}, ceiling=1)
        self.assertEqual(code, 1, output)
        self.assertIn("grew to 2", output)

    def test_exempt_codes_do_not_count_as_missing(self) -> None:
        code, output = self._run(
            {
                "local_contract/example_test.dart": (
                    "expect(code, ExampleErrorCode.exampleNotFound);\n"
                )
            },
            ceiling=0,
            exempt={"EXAMPLE.SYSTEM.storage_unavailable": "service internal only"},
        )
        self.assertEqual(code, 0, output)

    def test_real_tree_missing_holds_the_declared_ceiling(self) -> None:
        verifier = load_verifier()
        codes = verifier.declared_codes()
        text = verifier.asserted_text()
        missing = [
            code
            for code, tokens in codes.items()
            if code not in verifier.EXEMPT_CODES
            and not any(token in text for token in tokens)
        ]
        self.assertLessEqual(len(missing), verifier.MISSING_CEILING, missing[:5])


if __name__ == "__main__":
    unittest.main()

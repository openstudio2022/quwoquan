# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-001
"""错误码断言覆盖棘轮门禁的配套合约。

覆盖 `verify_error_code_assertion_coverage.py`：声明码被测试断言后不再计入
缺失、缺失数超过服务基线即阻断、未登记服务被拒、豁免码不计入缺失。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT / "quwoquan_ops/gate/verify_error_code_assertion_coverage.py"
)

ERRORS_YAML = """errors:
- code: EXAMPLE.SYSTEM.storage_unavailable
  reason: storage_unavailable
- code: EXAMPLE.USER.not_found
  reason: not_found
"""

TEST_ASSERTING_BOTH = (
    "package tests\n"
    "// asserts EXAMPLE.SYSTEM.storage_unavailable and EXAMPLE.USER.not_found\n"
)

TEST_ASSERTING_ONE = "package tests\n// asserts EXAMPLE.USER.not_found only\n"


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_error_code_assertion_coverage_for_contract_test", VERIFIER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErrorCodeAssertionCoverageContractTest(unittest.TestCase):
    def _run(
        self,
        files: dict[str, str],
        ceilings: dict[str, int],
        exempt: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            services_root = root / "quwoquan_service/services"
            for relative, source in files.items():
                target = services_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            verifier.SERVICES_ROOT = services_root
            verifier.MISSING_CEILING = ceilings
            if exempt is not None:
                verifier.EXEMPT_CODES = exempt
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = verifier.main()
            return code, stdout.getvalue()

    def test_asserted_codes_do_not_count_as_missing(self) -> None:
        code, output = self._run(
            {
                "example-service/contracts/ctx/obj/errors.yaml": ERRORS_YAML,
                "example-service/tests/local_contract/ctx/obj/"
                "obj__local_contract_test.go": TEST_ASSERTING_BOTH,
            },
            ceilings={"example-service": 0},
        )
        self.assertEqual(code, 0, output)
        self.assertIn("missing=0", output)

    def test_missing_growth_beyond_ceiling_is_blocked(self) -> None:
        code, output = self._run(
            {
                "example-service/contracts/ctx/obj/errors.yaml": ERRORS_YAML,
                "example-service/tests/local_contract/ctx/obj/"
                "obj__local_contract_test.go": TEST_ASSERTING_ONE,
            },
            ceilings={"example-service": 0},
        )
        self.assertEqual(code, 1, output)
        self.assertIn("EXAMPLE.SYSTEM.storage_unavailable", output)

    def test_missing_within_ceiling_passes(self) -> None:
        code, output = self._run(
            {
                "example-service/contracts/ctx/obj/errors.yaml": ERRORS_YAML,
                "example-service/tests/local_contract/ctx/obj/"
                "obj__local_contract_test.go": TEST_ASSERTING_ONE,
            },
            ceilings={"example-service": 1},
        )
        self.assertEqual(code, 0, output)

    def test_unregistered_service_is_blocked(self) -> None:
        code, output = self._run(
            {"example-service/contracts/ctx/obj/errors.yaml": ERRORS_YAML},
            ceilings={},
        )
        self.assertEqual(code, 1, output)
        self.assertIn("not registered in MISSING_CEILING", output)

    def test_exempt_codes_do_not_count_as_missing(self) -> None:
        code, output = self._run(
            {
                "example-service/contracts/ctx/obj/errors.yaml": ERRORS_YAML,
                "example-service/tests/local_contract/ctx/obj/"
                "obj__local_contract_test.go": TEST_ASSERTING_ONE,
            },
            ceilings={"example-service": 0},
            exempt={
                "EXAMPLE.SYSTEM.storage_unavailable": "process-level fallback"
            },
        )
        self.assertEqual(code, 0, output)

    def test_generated_const_alias_counts_as_assertion_evidence(self) -> None:
        """经 generated 常量（go_const/dart_const）断言的码不得误判为未覆盖。"""
        errors_yaml = (
            "errors:\n"
            "- code: EXAMPLE.USER.idempotency_conflict\n"
            "  reason: idempotency_conflict\n"
            "  go_const: ErrIdempotencyConflict\n"
            "  dart_const: exampleIdempotencyConflict\n"
        )
        const_asserting_test = (
            "package tests\n"
            "// asserts generated.ErrIdempotencyConflict semantics\n"
        )
        code, output = self._run(
            {
                "example-service/contracts/ctx/obj/errors.yaml": errors_yaml,
                "example-service/tests/local_contract/ctx/obj/"
                "obj__local_contract_test.go": const_asserting_test,
            },
            ceilings={"example-service": 0},
        )
        self.assertEqual(code, 0, output)
        self.assertIn("missing=0", output)

    def test_real_tree_missing_counts_hold_their_ceilings(self) -> None:
        verifier = _load_verifier()
        for service_dir in sorted(verifier.SERVICES_ROOT.iterdir()):
            if not service_dir.is_dir():
                continue
            declared = verifier.declared_codes(service_dir)
            if not declared:
                continue
            text = verifier.asserted_text(service_dir)
            missing = [
                code
                for code, tokens in declared.items()
                if code not in verifier.EXEMPT_CODES
                and not any(token in text for token in tokens)
            ]
            ceiling = verifier.MISSING_CEILING.get(service_dir.name)
            self.assertIsNotNone(
                ceiling, f"{service_dir.name} missing from MISSING_CEILING"
            )
            self.assertLessEqual(
                len(missing),
                ceiling,
                f"{service_dir.name}: {missing[:5]}",
            )


if __name__ == "__main__":
    unittest.main()

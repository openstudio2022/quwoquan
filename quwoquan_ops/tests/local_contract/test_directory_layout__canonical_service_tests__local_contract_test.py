from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = REPO_ROOT / "quwoquan_ops/gate/scaffold/verify_test_directory_layout.py"


def _load_verifier():
    scaffold_dir = str(VERIFIER_PATH.parent)
    if scaffold_dir not in sys.path:
        sys.path.insert(0, scaffold_dir)
    spec = importlib.util.spec_from_file_location(
        "verify_test_directory_layout_for_contract_test",
        VERIFIER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CanonicalServiceTestDirectoryContractTest(unittest.TestCase):
    def _verify(self, relative_test_path: str) -> list[str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            service_root = root / "quwoquan_service/services/example-service"
            target = service_root / relative_test_path
            target.parent.mkdir(parents=True)
            target.write_text(
                "package example\n\nimport \"testing\"\n\n"
                "func TestExample(t *testing.T) {}\n",
                encoding="utf-8",
            )
            previous_root = verifier.ROOT
            previous_service_root = verifier.SERVICE_ROOT
            verifier.ROOT = root
            verifier.SERVICE_ROOT = root / "quwoquan_service/services"
            try:
                failures = verifier.Failures()
                verifier.verify_service(failures)
                return failures.items
            finally:
                verifier.ROOT = previous_root
                verifier.SERVICE_ROOT = previous_service_root

    def test_internal_go_test_is_rejected(self) -> None:
        failures = self._verify(
            "internal/example/item/domain/example__local_contract_test.go"
        )
        self.assertTrue(
            any("outside canonical" in failure for failure in failures),
            failures,
        )

    def test_cmd_go_test_is_rejected(self) -> None:
        failures = self._verify("cmd/api/main__local_contract_test.go")
        self.assertTrue(
            any("outside canonical" in failure for failure in failures),
            failures,
        )

    def test_canonical_object_test_is_accepted(self) -> None:
        failures = self._verify(
            "tests/local_contract/example/item/example__local_contract_test.go"
        )
        self.assertEqual(failures, [])

    def test_nested_go_package_under_owned_object_is_accepted(self) -> None:
        failures = self._verify(
            "tests/local_contract/example/item/internal/application/"
            "example__local_contract_test.go"
        )
        self.assertEqual(failures, [])

    def _verify_runtime(self, relative_test_path: str) -> list[str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "quwoquan_service/runtime"
            target = runtime_root / relative_test_path
            target.parent.mkdir(parents=True)
            target.write_text(
                "//go:build api_integration\n\n"
                "package reliabletask_test\n\n"
                "import \"testing\"\n\n"
                "func TestExample(t *testing.T) {}\n",
                encoding="utf-8",
            )
            previous_root = verifier.ROOT
            previous_runtime_root = verifier.RUNTIME_ROOT
            previous_runtime_test_root = verifier.RUNTIME_TEST_ROOT
            verifier.ROOT = root
            verifier.RUNTIME_ROOT = runtime_root
            verifier.RUNTIME_TEST_ROOT = runtime_root / "tests"
            try:
                failures = verifier.Failures()
                verifier.verify_runtime(failures)
                return failures.items
            finally:
                verifier.ROOT = previous_root
                verifier.RUNTIME_ROOT = previous_runtime_root
                verifier.RUNTIME_TEST_ROOT = previous_runtime_test_root

    def test_runtime_canonical_api_integration_test_is_reachable(self) -> None:
        failures = self._verify_runtime(
            "tests/api_integration/reliabletask/"
            "data_content_fleet__reliability__api_integration_test.go"
        )
        self.assertEqual(failures, [])

    def test_runtime_api_integration_test_outside_canonical_root_is_rejected(self) -> None:
        failures = self._verify_runtime(
            "reliabletask/data_content_fleet__reliability__api_integration_test.go"
        )
        self.assertTrue(
            any("runtime api_integration test outside canonical" in failure for failure in failures),
            failures,
        )


if __name__ == "__main__":
    unittest.main()

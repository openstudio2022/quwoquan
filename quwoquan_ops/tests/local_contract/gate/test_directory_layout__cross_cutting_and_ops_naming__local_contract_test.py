"""横切区 Go 测试层后缀与 Ops pytest 命名收口的门禁配套合约。

覆盖 `verify_test_directory_layout.py` 的三组新规则：
1. runtime/internal/tools/cmd 旁路同包 Go 测试必须带 `__local_contract_test.go`；
2. Ops local_contract / acceptance 的 pytest 套件必须以 `test_` 开头；
3. Ops local_contract 内非测试 Python 只允许 provider conformance 残量且只减不增。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = REPO_ROOT / "quwoquan_ops/gate/scaffold/verify_test_directory_layout.py"


def _load_verifier():
    scaffold_dir = str(VERIFIER_PATH.parent)
    if scaffold_dir not in sys.path:
        sys.path.insert(0, scaffold_dir)
    spec = importlib.util.spec_from_file_location(
        "verify_test_directory_layout_for_cross_cutting_contract_test",
        VERIFIER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GO_TEST_SOURCE = (
    "package example\n\nimport \"testing\"\n\nfunc TestExample(t *testing.T) {}\n"
)


class CrossCuttingGoLayerSuffixContractTest(unittest.TestCase):
    def _verify_runtime(self, relative_test_path: str, source: str = GO_TEST_SOURCE) -> list[str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root = root / "quwoquan_service/runtime"
            (runtime_root / "tests" / "local_contract").mkdir(parents=True)
            target = runtime_root / relative_test_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
            previous = (verifier.ROOT, verifier.RUNTIME_ROOT, verifier.RUNTIME_TEST_ROOT)
            verifier.ROOT = root
            verifier.RUNTIME_ROOT = runtime_root
            verifier.RUNTIME_TEST_ROOT = runtime_root / "tests"
            try:
                failures = verifier.Failures()
                verifier.verify_runtime(failures)
                return failures.items
            finally:
                verifier.ROOT, verifier.RUNTIME_ROOT, verifier.RUNTIME_TEST_ROOT = previous

    def _verify_cross_cutting(self, relative_test_path: str, source: str = GO_TEST_SOURCE) -> list[str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            domain_root = root / "quwoquan_service"
            target = domain_root / relative_test_path
            target.parent.mkdir(parents=True)
            target.write_text(source, encoding="utf-8")
            previous = (verifier.ROOT, verifier.SERVICE_DOMAIN_ROOT)
            verifier.ROOT = root
            verifier.SERVICE_DOMAIN_ROOT = domain_root
            try:
                failures = verifier.Failures()
                verifier.verify_service_domain_cross_cutting(failures)
                return failures.items
            finally:
                verifier.ROOT, verifier.SERVICE_DOMAIN_ROOT = previous

    def test_runtime_plain_package_local_test_is_rejected(self) -> None:
        failures = self._verify_runtime("auth/jwt_test.go")
        self.assertTrue(
            any("must end with '__local_contract_test.go'" in item for item in failures),
            failures,
        )

    def test_runtime_package_local_local_contract_test_is_accepted(self) -> None:
        failures = self._verify_runtime("auth/jwt__local_contract_test.go")
        self.assertEqual(failures, [])

    def test_runtime_local_contract_suffix_with_api_integration_tag_is_rejected(self) -> None:
        failures = self._verify_runtime(
            "auth/jwt__local_contract_test.go",
            source="//go:build api_integration\n\n" + GO_TEST_SOURCE,
        )
        self.assertTrue(
            any("carries the api_integration build tag" in item for item in failures),
            failures,
        )

    def test_internal_plain_test_is_rejected(self) -> None:
        failures = self._verify_cross_cutting("internal/platform/redis/client_test.go")
        self.assertTrue(
            any("must end with '__local_contract_test.go'" in item for item in failures),
            failures,
        )

    def test_tools_local_contract_test_is_accepted(self) -> None:
        failures = self._verify_cross_cutting(
            "tools/codegen_example/main__local_contract_test.go"
        )
        self.assertEqual(failures, [])

    def test_cmd_local_contract_test_is_accepted(self) -> None:
        failures = self._verify_cross_cutting(
            "cmd/service-core/main__local_contract_test.go"
        )
        self.assertEqual(failures, [])

    def test_canonical_tests_tree_is_out_of_cross_cutting_scope(self) -> None:
        failures = self._verify_cross_cutting(
            "internal/tests/local_contract/example/example_test.go"
        )
        self.assertEqual(failures, [])


class OpsPytestNamingContractTest(unittest.TestCase):
    def _verify_ops(self, files: dict[str, str]) -> list[str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ops_test_root = root / "quwoquan_ops/tests"
            (ops_test_root / "local_contract").mkdir(parents=True)
            acceptance_root = ops_test_root / "acceptance"
            (acceptance_root / "api_integration").mkdir(parents=True)
            (acceptance_root / "user_acceptance").mkdir(parents=True)
            for relative, source in files.items():
                target = ops_test_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
            previous = (verifier.ROOT, verifier.OPS_TEST_ROOT, verifier.OPS_ACCEPTANCE_ROOT)
            verifier.ROOT = root
            verifier.OPS_TEST_ROOT = ops_test_root
            verifier.OPS_ACCEPTANCE_ROOT = acceptance_root
            try:
                failures = verifier.Failures()
                verifier.verify_ops(failures)
                return failures.items
            finally:
                verifier.ROOT, verifier.OPS_TEST_ROOT, verifier.OPS_ACCEPTANCE_ROOT = previous

    def test_local_contract_suite_without_pytest_prefix_is_rejected(self) -> None:
        failures = self._verify_ops(
            {"local_contract/deployment_manifest__contract__local_contract_test.py": ""}
        )
        self.assertTrue(
            any("must start with 'test_'" in item for item in failures),
            failures,
        )

    def test_acceptance_suite_without_pytest_prefix_is_rejected(self) -> None:
        failures = self._verify_ops(
            {
                "acceptance/api_integration/"
                "provider_governance__api_integration_test.py": ""
            }
        )
        self.assertTrue(
            any("must start with 'test_'" in item for item in failures),
            failures,
        )

    def test_prefixed_suites_in_a_registered_concern_are_accepted(self) -> None:
        failures = self._verify_ops(
            {
                "local_contract/gate/"
                "test_deployment_manifest__contract__local_contract_test.py": "",
                "acceptance/api_integration/"
                "test_provider_governance__api_integration_test.py": "",
                "acceptance/user_acceptance/"
                "test_provider_governance__user_acceptance_test.py": "",
            }
        )
        self.assertEqual(failures, [])

    def test_flat_suite_at_the_local_contract_root_is_rejected(self) -> None:
        """终态规则：分域归零后根平铺套件直接 BLOCK，不再有棘轮容忍。"""
        failures = self._verify_ops(
            {
                "local_contract/"
                "test_deployment_manifest__contract__local_contract_test.py": ""
            }
        )
        self.assertTrue(
            any("flat suite at the ops local_contract root" in item for item in failures),
            failures,
        )

    def test_non_test_python_in_local_contract_is_rejected(self) -> None:
        failures = self._verify_ops(
            {"local_contract/promotion_evidence_test_support.py": ""}
        )
        self.assertTrue(
            any("is not a pytest suite" in item for item in failures),
            failures,
        )

    def test_conftest_is_allowed(self) -> None:
        failures = self._verify_ops({"local_contract/conftest.py": ""})
        self.assertEqual(failures, [])

    @staticmethod
    def _declaration(adapter_id: str, layer: str) -> str:
        return (
            "# provider_conformance: "
            f'{{"adapterId":"{adapter_id}","testLayer":"{layer}"}}\n'
        )

    def _matrix_files(self, adapter_id: str = "ext.example") -> dict[str, str]:
        return {
            "local_contract/service_ops/example-service/ci/"
            "ext_example_provider_conformance.py": self._declaration(
                adapter_id, "local_contract"
            ),
            "acceptance/api_integration/service_ops/example-service/ci/"
            "ext_example_provider_conformance.py": self._declaration(
                adapter_id, "api_integration"
            ),
            "acceptance/user_acceptance/service_ops/example-service/ci/"
            "ext_example_provider_conformance.py": self._declaration(
                adapter_id, "user_acceptance"
            ),
        }

    def test_paired_conformance_declarations_are_accepted(self) -> None:
        failures = self._verify_ops(self._matrix_files())
        self.assertEqual(failures, [])

    def test_declared_layer_must_match_the_hosting_tree(self) -> None:
        files = self._matrix_files()
        files[
            "local_contract/service_ops/example-service/ci/"
            "ext_example_provider_conformance.py"
        ] = self._declaration("ext.example", "api_integration")
        failures = self._verify_ops(files)
        self.assertTrue(
            any("declares testLayer" in item for item in failures),
            failures,
        )

    def test_adapter_missing_a_layer_declaration_is_rejected(self) -> None:
        files = self._matrix_files()
        files.pop(
            "acceptance/user_acceptance/service_ops/example-service/ci/"
            "ext_example_provider_conformance.py"
        )
        failures = self._verify_ops(files)
        self.assertTrue(
            any("missing conformance declarations in user_acceptance" in item for item in failures),
            failures,
        )

    def test_duplicate_adapter_declaration_in_one_layer_is_rejected(self) -> None:
        files = self._matrix_files()
        files[
            "local_contract/service_ops/example-service/ci/"
            "ext_example_copy_provider_conformance.py"
        ] = self._declaration("ext.example", "local_contract")
        failures = self._verify_ops(files)
        self.assertTrue(
            any("each layer declares one file per adapter" in item for item in failures),
            failures,
        )

    def test_unparseable_declaration_header_is_rejected(self) -> None:
        files = self._matrix_files()
        files[
            "local_contract/service_ops/example-service/ci/"
            "ext_example_provider_conformance.py"
        ] = "print('no declaration header')\n"
        failures = self._verify_ops(files)
        self.assertTrue(
            any("no parseable" in item for item in failures),
            failures,
        )

    def test_declaration_roster_cannot_grow_beyond_the_ceiling(self) -> None:
        verifier = _load_verifier()
        ceiling = verifier.OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING
        files: dict[str, str] = {}
        for index in range(ceiling + 1):
            adapter = f"ext.example{index}"
            for layer, root in (
                ("local_contract", "local_contract"),
                ("api_integration", "acceptance/api_integration"),
                ("user_acceptance", "acceptance/user_acceptance"),
            ):
                files[
                    f"{root}/service_ops/example-service/ci/"
                    f"ext_example{index}_provider_conformance.py"
                ] = self._declaration(adapter, layer)
        failures = self._verify_ops(files)
        self.assertTrue(
            any("grow the provider roster" in item for item in failures),
            failures,
        )


if __name__ == "__main__":
    unittest.main()

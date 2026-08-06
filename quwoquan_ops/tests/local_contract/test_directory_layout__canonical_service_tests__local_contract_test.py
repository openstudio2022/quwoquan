from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = REPO_ROOT / "quwoquan_ops/gate/scaffold/verify_test_directory_layout.py"
CONTRACT_GRAPH_PATH = REPO_ROOT / "quwoquan_service/generated/contract_graph.json"


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
    def setUp(self) -> None:
        graph = json.loads(CONTRACT_GRAPH_PATH.read_text(encoding="utf-8"))
        entry = next(
            item
            for item in graph.get("objects") or []
            if len(str(item.get("sourcePath") or "").split("/")) >= 3
        )
        parts = str(entry["sourcePath"]).split("/")
        self.domain = str(entry.get("domain") or parts[0])
        self.context = parts[1]
        self.object_name = parts[2]

    def _verify(
        self,
        relative_test_path: str,
        *,
        control_plane: bool = False,
    ) -> list[str]:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "quwoquan_service/services").mkdir(parents=True)
            (root / "quwoquan_service/control-plane").mkdir(parents=True)
            owner_root = "control-plane" if control_plane else "services"
            service_root = root / "quwoquan_service" / owner_root / "example-service"
            contracts = service_root / "contracts"
            contracts.mkdir(parents=True)
            (contracts / "domain.yaml").write_text(
                f"domain: {self.domain}\n", encoding="utf-8"
            )
            object_contract = contracts / self.context / self.object_name / "object.yaml"
            object_contract.parent.mkdir(parents=True)
            object_contract.write_text("kind: aggregate_root\n", encoding="utf-8")
            target = service_root / relative_test_path
            target.parent.mkdir(parents=True)
            target.write_text(
                "package example\n\nimport \"testing\"\n\n"
                "func TestExample(t *testing.T) {}\n",
                encoding="utf-8",
            )
            previous_root = verifier.ROOT
            previous_service_root = verifier.SERVICE_ROOT
            previous_control_plane_root = verifier.CONTROL_PLANE_ROOT
            verifier.ROOT = root
            verifier.SERVICE_ROOT = root / "quwoquan_service/services"
            verifier.CONTROL_PLANE_ROOT = root / "quwoquan_service/control-plane"
            try:
                failures = verifier.Failures()
                verifier.verify_service(failures)
                return failures.items
            finally:
                verifier.ROOT = previous_root
                verifier.SERVICE_ROOT = previous_service_root
                verifier.CONTROL_PLANE_ROOT = previous_control_plane_root

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
            f"tests/local_contract/{self.context}/{self.object_name}/"
            "example__local_contract_test.go"
        )
        self.assertEqual(failures, [])

    def test_nested_go_package_under_owned_object_is_accepted(self) -> None:
        failures = self._verify(
            f"tests/local_contract/{self.context}/{self.object_name}/internal/application/"
            "example__local_contract_test.go"
        )
        self.assertEqual(failures, [])

    def test_non_test_prefixed_python_file_is_in_service_roster_validation(self) -> None:
        failures = self._verify(
            f"tests/api_integration/{self.context}/{self.object_name}/"
            "projection__api_integration_test.py"
        )
        self.assertEqual(failures, [])

    def test_non_test_prefixed_python_file_with_unknown_object_is_rejected(self) -> None:
        failures = self._verify(
            f"tests/local_contract/{self.context}/not_a_roster_object/"
            "projection__local_contract_test.py"
        )
        self.assertTrue(any("ContractGraph roster" in item for item in failures), failures)

    def test_current_non_test_prefixed_python_files_are_in_canonical_inventory(
        self,
    ) -> None:
        verifier = _load_verifier()
        inventory = {
            path.relative_to(REPO_ROOT).as_posix()
            for owner, path, _layer in verifier.iter_canonical_files()
            if owner == "service"
        }
        expected = {
            "quwoquan_service/services/recommendation-service/tests/api_integration/"
            "recommendation/recommendation_model_release/"
            "model_release_outbox__api_integration_test.py",
            "quwoquan_service/services/recommendation-service/tests/local_contract/"
            "recommendation/recommendation_model_release/"
            "intersection_kind_registry__producer_shape__local_contract_test.py",
            "quwoquan_service/services/recommendation-service/tests/local_contract/"
            "recommendation/recommendation_model_release/"
            "outbox_relay__reliability__local_contract_test.py",
        }
        self.assertEqual(expected - inventory, set())

    def test_real_context_with_unknown_object_is_rejected(self) -> None:
        failures = self._verify(
            f"tests/local_contract/{self.context}/not_a_roster_object/"
            "example__local_contract_test.go"
        )
        self.assertTrue(any("ContractGraph roster" in item for item in failures), failures)

    def test_unknown_context_with_real_object_is_rejected(self) -> None:
        failures = self._verify(
            f"tests/api_integration/not_a_roster_context/{self.object_name}/"
            "example__api_integration_test.go"
        )
        self.assertTrue(any("ContractGraph roster" in item for item in failures), failures)

    def test_control_plane_object_test_uses_the_same_roster_rule(self) -> None:
        failures = self._verify(
            f"tests/local_contract/{self.context}/{self.object_name}/"
            "example__local_contract_test.go",
            control_plane=True,
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

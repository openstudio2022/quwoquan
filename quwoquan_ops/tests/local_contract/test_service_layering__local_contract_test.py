from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_service"
    / "scripts"
    / "verify"
    / "structure"
    / "verify_service_layering.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_service_layering", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ServiceLayeringContractTest(unittest.TestCase):
    def test_service_layering_has_no_reverse_dependencies(self) -> None:
        gate = _load_gate()
        scanned = gate._production_source_files(gate._services_root())
        self.assertTrue(scanned, "service layering scanner must inspect real sources")
        issues = gate.collect_issues()
        self.assertEqual([], issues, "\n".join(issues))

    def test_empty_service_scan_fails_closed(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            gate.SERVICE_ROOT = Path(temp_dir)
            (gate.SERVICE_ROOT / "services").mkdir()
            issues = gate.collect_issues()
        self.assertTrue(
            any("scanner matched zero" in issue for issue in issues),
            issues,
        )

    def test_context_object_layer_path_drives_go_and_python_checks(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            internal = (
                service_root
                / "services"
                / "sample_service"
                / "internal"
                / "sample"
                / "sample_object"
            )
            domain = internal / "domain"
            application = internal / "application"
            adapters = internal / "adapters" / "inbound"
            domain.mkdir(parents=True)
            application.mkdir(parents=True)
            adapters.mkdir(parents=True)
            (domain / "aggregate.go").write_text(
                "package domain\n"
                'import "quwoquan_service/services/sample_service/'
                'internal/sample/sample_object/application"\n',
                encoding="utf-8",
            )
            (application / "service.py").write_text(
                "from quwoquan_service.services.sample_service.internal.sample."
                "sample_object.adapters import inbound\n"
                "import pymongo\n",
                encoding="utf-8",
            )
            (adapters / "handler.go").write_text(
                "package inbound\n"
                'import "go.mongodb.org/mongo-driver/v2/mongo"\n',
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertTrue(
            any("domain 反向依赖" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("application 反向依赖" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("application 直接导入存储驱动 pymongo" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("adapters 直接导入存储驱动" in issue for issue in issues),
            issues,
        )

    def test_api_routes_require_source_and_path_evidence(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            object_root = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "sample"
                / "sample_object"
            )
            contract = (
                service_root
                / "services"
                / "sample-service"
                / "contracts"
                / "sample"
                / "sample_object"
            )
            evidence = (
                service_root
                / "services"
                / "sample-service"
                / "tests"
                / "api_integration"
                / "sample"
                / "sample_object"
            )
            (object_root / "domain").mkdir(parents=True)
            contract.mkdir(parents=True)
            evidence.mkdir(parents=True)
            (object_root / "domain" / "entity.go").write_text(
                "package domain\n",
                encoding="utf-8",
            )
            (contract / "operations.yaml").write_text(
                "api_routes:\n"
                "- method: GET\n"
                "  path: /sample/items\n"
                "  operation: ListSampleItems\n",
                encoding="utf-8",
            )
            evidence_file = evidence / "items__api_integration_test.go"
            evidence_file.write_text(
                'package api_integration\nconst samplePath = "/sample/items"\n',
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root
            self.assertEqual([], gate.collect_issues())

            evidence_file.unlink()
            issues = gate.collect_issues()

        self.assertTrue(
            any(
                "api_routes 对象缺少 api_integration API evidence" in issue
                for issue in issues
            ),
            issues,
        )

if __name__ == "__main__":
    unittest.main()

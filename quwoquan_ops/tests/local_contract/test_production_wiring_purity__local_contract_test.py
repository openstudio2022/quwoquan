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
    / "verify_production_wiring_purity.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_production_wiring_purity", SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionWiringPurityContractTest(unittest.TestCase):
    def test_production_wiring_has_no_memory_noop_or_mock(self) -> None:
        issues = _load_gate().collect_issues()
        self.assertEqual([], issues, "\n".join(issues))

    def test_all_command_binaries_and_application_fallbacks_are_scanned(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            worker = service_root / "services" / "sample-service" / "cmd" / "worker"
            application = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "application"
            )
            adapters = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "adapters"
                / "http"
            )
            worker.mkdir(parents=True)
            application.mkdir(parents=True)
            adapters.mkdir(parents=True)
            (worker / "main.go").write_text(
                "package main\nfunc main() { NewMemoryStore() }\n",
                encoding="utf-8",
            )
            api = service_root / "services" / "sample-service" / "cmd" / "api"
            api.mkdir(parents=True)
            (api / "main.go").write_text(
                "package main\nfunc main() { SeedFixture() }\n",
                encoding="utf-8",
            )
            (application / "service.go").write_text(
                'package application\nvar fallback = NoopGateway{}\n'
                "var publisher = NoopPublisher()\n"
                'var endpoint = "https://service.invalid"\n',
                encoding="utf-8",
            )
            (adapters / "handler.go").write_text(
                "package http\nfunc newHandler() { NewFakeGateway() }\n",
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertTrue(
            any("cmd/worker/main.go" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("internal/application/service.go" in issue for issue in issues),
            issues,
        )
        self.assertTrue(any("生产 API 装配" in issue for issue in issues), issues)
        self.assertTrue(any("生产默认值" in issue for issue in issues), issues)
        self.assertTrue(
            any("internal/adapters/http/handler.go" in issue for issue in issues),
            issues,
        )

    def test_test_and_infrastructure_doubles_do_not_block_production_gate(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            api = service_root / "services" / "sample-service" / "cmd" / "api"
            infrastructure = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "infrastructure"
                / "persistence"
            )
            api.mkdir(parents=True)
            infrastructure.mkdir(parents=True)
            (api / "main__local_contract_test.go").write_text(
                "package main\nfunc testStore() { NewMemoryStore() }\n",
                encoding="utf-8",
            )
            (infrastructure / "memory_store.go").write_text(
                "package persistence\nfunc NewMemoryStore() any { return nil }\n",
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertEqual([], issues)

    def test_beta_gamma_and_prod_configs_cannot_select_fake_storage(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            for environment, config in (
                ("beta", "storage:\n  mode: memory\n"),
                ("gamma", "storage:\n  mode: noop\n"),
                ("prod", "storage:\n  mode: mock\nseedRefs: [forbidden]\n"),
            ):
                config_dir = (
                    service_root
                    / "services"
                    / "sample-service"
                    / "configs"
                    / environment
                )
                config_dir.mkdir(parents=True)
                (config_dir / "config.yaml").write_text(config, encoding="utf-8")
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertTrue(any("beta 配置" in issue for issue in issues), issues)
        self.assertTrue(any("gamma 配置" in issue for issue in issues), issues)
        self.assertTrue(any("prod 配置" in issue for issue in issues), issues)
        self.assertTrue(any("seedRefs" in issue for issue in issues), issues)


if __name__ == "__main__":
    unittest.main()

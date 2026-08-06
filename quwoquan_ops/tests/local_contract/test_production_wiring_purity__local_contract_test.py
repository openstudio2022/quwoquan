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
                / "sample"
                / "sample_object"
                / "application"
            )
            adapters = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "sample"
                / "sample_object"
                / "adapters"
                / "http"
            )
            worker.mkdir(parents=True)
            application.mkdir(parents=True)
            adapters.mkdir(parents=True)
            (worker / "main.go").write_text(
                "package main\n\n"
                "import (\n"
                '\t"quwoquan_service/services/sample-service/internal/sample/'
                'sample_object/infrastructure/testsupport"\n'
                ")\n\n"
                "func main() { _ = testsupport.Store{} }\n",
                encoding="utf-8",
            )
            api = service_root / "services" / "sample-service" / "cmd" / "api"
            api.mkdir(parents=True)
            (api / "main.go").write_text(
                "package main\nfunc main() { SeedFixture() }\n",
                encoding="utf-8",
            )
            (application / "service.go").write_text(
                "package application\n\n"
                'import "github.com/stretchr/testify/require"\n\n'
                'var endpoint = "https://service.invalid"\n',
                encoding="utf-8",
            )
            (adapters / "handler.go").write_text(
                "//go:build test\n\npackage http\nfunc newHandler() {}\n",
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertTrue(
            any(
                "cmd/worker/main.go" in issue and "测试专用包" in issue
                for issue in issues
            ),
            issues,
        )
        self.assertTrue(
            any(
                "application/service.go" in issue and "测试框架" in issue
                for issue in issues
            ),
            issues,
        )
        self.assertTrue(any("生产 API 装配" in issue for issue in issues), issues)
        self.assertTrue(any("生产默认值" in issue for issue in issues), issues)
        self.assertTrue(
            any(
                "adapters/http/handler.go" in issue and "测试构建约束" in issue
                for issue in issues
            ),
            issues,
        )

    def test_business_concept_named_memory_is_not_flagged(self) -> None:
        """`MemoryProfile` 是 assistant 长期记忆的业务概念，撞词不得判为内存替身。"""
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            application = (
                service_root
                / "services"
                / "assistant-service"
                / "internal"
                / "assistant"
                / "skill_package_release"
                / "application"
                / "packageasset"
            )
            application.mkdir(parents=True)
            (application / "profile_assets.go").write_text(
                "package packageasset\n\n"
                "type MemoryProfile struct {\n"
                "\tProfileID string `json:\"profileId\"`\n"
                "\tDigest    string `json:\"digest\"`\n"
                "}\n\n"
                "type AssetCatalog struct {\n"
                "\tMemoryProfiles []MemoryProfile `json:\"memoryProfiles\"`\n"
                "}\n\n"
                "func memoryDigest(value MemoryProfile) (string, string, error) {\n"
                "\treturn value.ProfileID, value.Digest, nil\n"
                "}\n\n"
                "func newCatalog() AssetCatalog { return AssetCatalog{} }\n",
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertEqual([], issues, issues)

    def test_real_in_memory_double_wired_into_production_is_flagged(self) -> None:
        """真替身即使不叫 Memory/Mock/Fake，只要被生产装配引用就必须命中。"""
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            api = service_root / "services" / "sample-service" / "cmd" / "api"
            double = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "sample"
                / "sample_object"
                / "infrastructure"
                / "testsupport"
            )
            api.mkdir(parents=True)
            double.mkdir(parents=True)
            # 替身自己完全不带 double 词汇，只叫 Store。
            (double / "post_store.go").write_text(
                "package testsupport\n\n"
                "import (\n\t\"context\"\n\t\"sync\"\n)\n\n"
                "type Store struct {\n"
                "\tmu    sync.RWMutex\n"
                "\titems map[string]string\n"
                "}\n\n"
                "func (s *Store) Save(ctx context.Context, id string) error "
                "{ return nil }\n",
                encoding="utf-8",
            )
            (api / "main.go").write_text(
                "package main\n\n"
                "import (\n"
                '\t"quwoquan_service/services/sample-service/internal/sample/'
                'sample_object/infrastructure/testsupport"\n'
                ")\n\n"
                "func main() { _ = &testsupport.Store{} }\n",
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertTrue(
            any(
                "cmd/api/main.go" in issue and "测试专用包" in issue
                for issue in issues
            ),
            issues,
        )
        self.assertFalse(
            any("infrastructure/testsupport/post_store.go" in issue for issue in issues),
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
                / "sample"
                / "sample_object"
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

    def test_python_command_and_application_test_symbols_are_blocked(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir)
            command = (
                service_root / "services" / "sample-service" / "cmd" / "worker"
            )
            application = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "sample"
                / "sample_object"
                / "application"
            )
            infrastructure = (
                service_root
                / "services"
                / "sample-service"
                / "internal"
                / "sample"
                / "sample_object"
                / "infrastructure"
            )
            command.mkdir(parents=True)
            application.mkdir(parents=True)
            infrastructure.mkdir(parents=True)
            (command / "main.py").write_text(
                "from tests.support import sample_fixture\n",
                encoding="utf-8",
            )
            (application / "service.py").write_text(
                "from unittest.mock import MagicMock\n\ngateway = MagicMock()\n",
                encoding="utf-8",
            )
            (infrastructure / "memory_store.py").write_text(
                "def NewMemoryStore():\n    return object()\n",
                encoding="utf-8",
            )
            gate.SERVICE_ROOT = service_root

            issues = gate.collect_issues()

        self.assertTrue(any("cmd/worker/main.py" in issue for issue in issues), issues)
        self.assertTrue(
            any("application/service.py" in issue for issue in issues),
            issues,
        )
        self.assertFalse(
            any("infrastructure/memory_store.py" in issue for issue in issues),
            issues,
        )

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
                    / "environments"
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

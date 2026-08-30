from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCAFFOLD = ROOT / "quwoquan_ops/gate/scaffold/new_service.py"


class ServiceAssetScaffoldContractTest(unittest.TestCase):
    def test_scaffold_rejects_same_context_and_object_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            service = repo / "quwoquan_service/services/contract-probe-service"
            contracts = service / "contracts"
            object_root = contracts / "probe/probe"
            object_root.mkdir(parents=True)
            (contracts / "domain.yaml").write_text("domain: probe\n", encoding="utf-8")
            (contracts / "probe/context.yaml").write_text(
                "role: test\n", encoding="utf-8"
            )
            (object_root / "object.yaml").write_text(
                "kind: aggregate_root\n", encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD),
                    "--service",
                    "contract-probe-service",
                    "--context",
                    "probe.probe",
                    "--object",
                    "probe",
                    "--language",
                    "go",
                    "--repo-root",
                    str(repo),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn(
                "bounded context and business object must use distinct",
                result.stderr,
            )
            self.assertFalse((service / "internal").exists())

    def test_scaffold_requires_existing_unowned_metadata_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            service = repo / "quwoquan_service/services/contract-probe-service"
            contracts = service / "contracts"
            context = contracts / "context"
            object_root = context / "probe_object"
            object_root.mkdir(parents=True)
            (contracts / "domain.yaml").write_text("domain: probe\n", encoding="utf-8")
            (context / "context.yaml").write_text("role: test\n", encoding="utf-8")
            (object_root / "object.yaml").write_text(
                "kind: aggregate_root\n", encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "python3",
                    str(SCAFFOLD),
                    "--service",
                    "contract-probe-service",
                    "--context",
                    "probe.context",
                    "--object",
                    "probe_object",
                    "--language",
                    "go",
                    "--repo-root",
                    str(repo),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (
                    service
                    / "internal/context/probe_object/domain/object.go"
                ).is_file()
            )
            self.assertTrue(
                (
                    service
                    / "tests/local_contract/context/probe_object/object__local_contract_test.go"
                ).is_file()
            )
            self.assertTrue(
                (
                    service
                    / "tests/api_integration/context/probe_object/handler__api_integration_test.go"
                ).is_file()
            )
            for required in (
                "AGENTS.md",
                "Makefile",
                "cmd/api/bootstrap.go",
                "cmd/standalone-api/main.go",
                "config/schema.yaml",
                "deploy/base/kustomization.yaml",
                "deploy/base/deployment.yaml",
                "deploy/base/service.yaml",
                "deploy/compose.yaml",
                "environments/alpha/config.yaml",
                "environments/beta/deploy/kustomization.yaml",
                "environments/gamma/config.yaml",
                "environments/prod/deploy/kustomization.yaml",
            ):
                self.assertTrue((service / required).is_file(), required)
            for forbidden in ("configs", "README.md"):
                self.assertFalse((service / forbidden).exists())
            deployment = (service / "deploy/base/deployment.yaml").read_text(
                encoding="utf-8"
            )
            compose = (service / "deploy/compose.yaml").read_text(encoding="utf-8")
            self.assertEqual(
                deployment.count("quwoquan.io/image-version: package-required"),
                2,
            )
            self.assertIn(
                "fieldPath: metadata.annotations['quwoquan.io/image-version']",
                deployment,
            )
            self.assertIn("_IMAGE:?fixed contract-probe-service image", compose)
            self.assertIn("QWQ_COMPOSE_IMAGE_VERSION:?immutable image identity", compose)
            # Dockerfile 构建入口必须与生成的 standalone 壳同源：入口路径漂移
            # 会让镜像构建到不存在的 main 包。
            dockerfile = (service / "build/Dockerfile").read_text(encoding="utf-8")
            self.assertIn(
                "./services/contract-probe-service/cmd/standalone-api",
                dockerfile,
            )
            standalone_main = (service / "cmd/standalone-api/main.go").read_text(
                encoding="utf-8"
            )
            self.assertIn("package main", standalone_main)
            self.assertIn("servicekit.RunStandalone", standalone_main)
            bootstrap_source = (service / "cmd/api/bootstrap.go").read_text(
                encoding="utf-8"
            )
            self.assertIn("package bootstrap", bootstrap_source)

    def test_scaffold_declares_object_first_single_track_contract(self) -> None:
        text = SCAFFOLD.read_text(encoding="utf-8")

        for token in (
            "--context",
            "--object",
            "--language",
            "tests/local_contract",
            "tests/api_integration",
            "build/Dockerfile",
            "config/schema.yaml",
            "deploy/base/kustomization.yaml",
            "deploy/compose.yaml",
            '("alpha", "beta", "gamma", "prod")',
            "contract object already has source owner",
        ):
            self.assertIn(token, text)
        for forbidden in (
            "service_asset_profiles.json",
            "bootstrap_service_config_layout.sh",
            "readiness.yaml",
            "deploy/Dockerfile",
        ):
            self.assertNotIn(forbidden, text)

    def test_python_scaffold_is_importable_from_service_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            service = repo / "quwoquan_service/services/probe-service"
            contracts = service / "contracts"
            object_root = contracts / "context/probe_object"
            object_root.mkdir(parents=True)
            (contracts / "domain.yaml").write_text("domain: probe\n", encoding="utf-8")
            (contracts / "context/context.yaml").write_text("role: test\n", encoding="utf-8")
            (object_root / "object.yaml").write_text(
                "kind: aggregate_root\n", encoding="utf-8"
            )
            scaffold = subprocess.run(
                [
                    sys.executable,
                    str(SCAFFOLD),
                    "--service",
                    "probe-service",
                    "--context",
                    "probe.context",
                    "--object",
                    "probe_object",
                    "--language",
                    "python",
                    "--repo-root",
                    str(repo),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(scaffold.returncode, 0, scaffold.stderr)
            test_result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "from internal.context.probe_object.adapters.inbound.http.handler "
                        "import handle; assert handle('object-1') == {'id': 'object-1'}"
                    ),
                ],
                cwd=service,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            self.assertEqual(
                test_result.returncode,
                0,
                f"stdout={test_result.stdout}\nstderr={test_result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()

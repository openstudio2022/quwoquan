from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from quwoquan_ops.cli.lib.runtime_topology_package import (
    CONTENT_COMMERCIAL_SERVICES,
    CONTENT_RELEASE_SERVICES,
    RuntimeTopologyPackageError,
    load_runtime_topology_package,
    materialize_runtime_topology_package,
)
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_MODULE_SET,
    SERVICE_CORE_WORKLOAD,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


class RuntimeTopologyPackageSecurityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.candidate = self.root / "candidate"
        self.shared = self.candidate / "packages/runtime-shared"
        self.shared.mkdir(parents=True)

        services = sorted(
            CONTENT_COMMERCIAL_SERVICES
            | SERVICE_CORE_MODULE_SET
        )
        self._write_topology(
            self.repo
            / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
            ["mongodb", "platform-ops-service", *services],
        )
        for service in services:
            self._write_config_schema(
                self.repo
                / "quwoquan_service/services"
                / service
                / "config/schema.yaml"
            )
            self._write_compose(
                self.repo
                / "quwoquan_service/services"
                / service
                / "deploy/compose.yaml",
                service,
            )
            self._write_compose(
                self.repo
                / "quwoquan_service/services"
                / service
                / "environments/gamma/deploy/compose.yaml",
                service,
                build=False,
            )
        self._write_config_schema(
            self.repo
            / "quwoquan_service/control-plane/platform-ops/config/schema.yaml"
        )
        self._write_compose(
            self.repo
            / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml",
            "platform-ops",
        )
        self._write_config_schema(
            self.repo
            / "quwoquan_service/services/travel-service/config/schema.yaml"
        )
        self._write_compose(
            self.repo
            / "quwoquan_service/services/travel-service/deploy/compose.yaml",
            "travel-service",
        )
        self._write_compose(
            self.repo
            / "quwoquan_service/services/travel-service/environments/gamma/deploy/compose.yaml",
            "travel-service",
            build=False,
        )
        policy = (
            self.repo
            / "quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
        )
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text("schema: recommendation-policy\n", encoding="utf-8")
        alert_policy = (
            self.repo
            / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml"
        )
        alert_policy.parent.mkdir(parents=True, exist_ok=True)
        alert_policy.write_text("schema: telemetry-alert-policy\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_compose(
        path: Path,
        service: str,
        *,
        build: bool = True,
        volumes: list[str] | None = None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        definition: dict[str, object] = {"image": f"example/{service}:sealed"}
        if build:
            definition["build"] = {"context": "../../../live-workspace"}
        if volumes is not None:
            definition["volumes"] = volumes
        path.write_text(
            yaml.safe_dump(
                {"services": {service: definition}},
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_config_schema(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("configs: []\n", encoding="utf-8")

    @staticmethod
    def _write_topology(path: Path, services: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {"services": {service: {"image": service} for service in services}},
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _materialize(self) -> dict[str, object]:
        return materialize_runtime_topology_package(
            "gamma",
            "gamma-local",
            self.shared,
            repo_root=self.repo,
        )

    def test_full_runtime_uses_only_candidate_artifacts_without_build_contexts(self) -> None:
        manifest = self._materialize()

        source = (
            self.repo
            / "quwoquan_service/services/content-service/deploy/compose.yaml"
        )
        source.write_text("services: {}\n", encoding="utf-8")
        result = load_runtime_topology_package(
            self.candidate,
            environment="gamma",
            target="gamma-local",
            workload="full",
        )

        self.assertEqual(result["topologyDigest"], manifest["topologyDigest"])
        self.assertGreater(len(result["composeFiles"]), len(manifest["serviceNames"]))
        self.assertTrue(all(path.is_relative_to(self.candidate) for path in result["composeFiles"]))
        for path in result["composeFiles"]:
            compose = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertTrue(
                all("build" not in service for service in compose["services"].values())
            )
            self.assertFalse(
                SERVICE_CORE_MODULE_SET & set(compose["services"])
            )
        self.assertIn(SERVICE_CORE_WORKLOAD, result["runtimeServiceNames"])
        self.assertIn("search-service", result["serviceCoreModules"])
        base = yaml.safe_load(result["composeFiles"][0].read_text(encoding="utf-8"))
        aliases = set(
            base["services"][SERVICE_CORE_WORKLOAD]["networks"]["default"]["aliases"]
        )
        self.assertEqual(aliases, SERVICE_CORE_MODULE_SET)
        sbom = json.loads(
            result["compositionSbomFile"].read_text(encoding="utf-8")
        )
        component_names = {item["name"] for item in sbom["components"]}
        self.assertIn(SERVICE_CORE_WORKLOAD, component_names)
        self.assertFalse(SERVICE_CORE_MODULE_SET & component_names)
        self.assertTrue(result["policyFile"].is_relative_to(self.candidate))

    def test_retired_service_source_cannot_enter_runtime_package(self) -> None:
        manifest = self._materialize()

        self.assertNotIn("travel-service", manifest["serviceNames"])
        self.assertNotIn(
            "/services/travel-service/",
            "\n".join(str(item["ref"]) for item in manifest["compose"]),
        )

    def test_retired_service_symlink_does_not_block_runtime_package(self) -> None:
        travel = self.repo / "quwoquan_service/services/travel-service"
        materialized = self.root / "travel-service-materialized"
        travel.rename(materialized)
        travel.symlink_to(materialized)

        manifest = self._materialize()

        self.assertNotIn("travel-service", manifest["serviceNames"])
        self.assertGreaterEqual(len(manifest["serviceNames"]), 1)

    def test_current_repository_materializes_a_complete_runtime_topology(self) -> None:
        manifest = materialize_runtime_topology_package(
            "gamma",
            "gamma-local",
            self.shared,
            repo_root=REPO_ROOT,
        )

        result = load_runtime_topology_package(
            self.candidate,
            environment="gamma",
            target="gamma-local",
            workload="full",
        )

        self.assertEqual(result["topologyDigest"], manifest["topologyDigest"])
        self.assertEqual(set(result["serviceNames"]), set(manifest["serviceNames"]))
        self.assertGreaterEqual(len(result["serviceNames"]), 14)
        self.assertNotIn("travel-service", result["serviceNames"])

    def _merged_workload_services(
        self,
        workload: str,
    ) -> dict[str, dict[str, object]]:
        result = load_runtime_topology_package(
            self.candidate,
            environment="gamma",
            target="gamma-local",
            workload=workload,
        )
        merged: dict[str, dict[str, object]] = {}
        for path in result["composeFiles"]:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            for name, definition in (document.get("services") or {}).items():
                merged.setdefault(name, {}).update(definition or {})
        return merged

    def test_every_workload_closure_is_a_valid_compose_project(self) -> None:
        """投影掉某服务的 image 来源时,共享注册条目必须被 profile 门控。

        共享 compose 的服务集是 first_party_service_names 判定活跃 image owner
        的真相源,所以 rtc-service、realtime-gateway、product-ops-service 与
        platform-ops-service 必须留在那里,而它们的 image 只由各自 fragment 提
        供。bounded content workload 整份投影掉那些 fragment,若共享条目没有
        profile,残留条目就是一个无 image 无 build 的服务:`docker compose` 判
        定整个 project 失效,连 `down` 都执行不了——而 `up` 要求先 `down`,环境
        由此彻底死锁。带上 profile 后 Compose 在该 profile 未激活时整体排除该
        服务,投影与激活重新对齐。
        """

        materialize_runtime_topology_package(
            "gamma",
            "gamma-local",
            self.shared,
            repo_root=REPO_ROOT,
        )

        full = self._merged_workload_services("full")
        self.assertEqual(
            sorted(
                name
                for name, definition in full.items()
                if "image" not in definition and "build" not in definition
            ),
            [],
        )

        for workload in ("content-release", "content-commercial"):
            with self.subTest(workload=workload):
                merged = self._merged_workload_services(workload)
                ungated = sorted(
                    name
                    for name, definition in merged.items()
                    if "image" not in definition
                    and "build" not in definition
                    and not definition.get("profiles")
                )
                self.assertEqual(ungated, [])

    def test_stackctl_runtime_shared_package_seals_the_runtime_topology(self) -> None:
        from quwoquan_ops.cli import stackctl

        candidate = self.root / "stackctl-candidate"
        shared = candidate / "packages/runtime-shared"
        with patch.object(
            stackctl,
            "runtime_shared_deployment_package_dir",
            return_value=shared,
        ):
            package_dir = stackctl._build_runtime_shared_package(
                "gamma",
                target="gamma-local",
            )

        self.assertEqual(package_dir, shared)
        result = load_runtime_topology_package(
            candidate,
            environment="gamma",
            target="gamma-local",
            workload="full",
        )
        self.assertTrue(result["composeFiles"])
        self.assertTrue(result["policyFile"].is_relative_to(candidate))

    def test_bounded_workloads_select_the_exact_service_closure(self) -> None:
        self._materialize()

        release = load_runtime_topology_package(
            self.candidate,
            environment="gamma",
            target="gamma-local",
            workload="content-release",
        )
        commercial = load_runtime_topology_package(
            self.candidate,
            environment="gamma",
            target="gamma-local",
            workload="content-commercial",
        )

        release_paths = "\n".join(str(path) for path in release["composeFiles"])
        commercial_paths = "\n".join(str(path) for path in commercial["composeFiles"])
        for service in CONTENT_RELEASE_SERVICES:
            self.assertIn(f"/services/{service}/", release_paths)
        self.assertNotIn("/services/product-ops-service/", release_paths)
        self.assertIn("/services/product-ops-service/", commercial_paths)
        self.assertIn("/services/chat-service/", commercial_paths)
        self.assertIn("/services/search-service/", commercial_paths)
        self.assertNotIn("/control-plane/", commercial_paths)

    def test_symlinked_candidate_artifact_is_rejected(self) -> None:
        manifest = self._materialize()
        first_ref = Path(manifest["compose"][0]["ref"])
        artifact = self.candidate / first_ref
        external = self.root / "external.compose.yaml"
        external.write_text("services: {external: {image: external}}\n", encoding="utf-8")
        artifact.unlink()
        artifact.symlink_to(external)

        with self.assertRaisesRegex(RuntimeTopologyPackageError, "unsafe or missing"):
            load_runtime_topology_package(
                self.candidate,
                environment="gamma",
                target="gamma-local",
                workload="full",
            )

    def test_digest_drift_is_rejected(self) -> None:
        manifest = self._materialize()
        first_ref = Path(manifest["compose"][0]["ref"])
        artifact = self.candidate / first_ref
        artifact.write_text("services: {changed: {image: changed}}\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeTopologyPackageError, "drifted"):
            load_runtime_topology_package(
                self.candidate,
                environment="gamma",
                target="gamma-local",
                workload="full",
            )

    def test_manifest_cannot_drop_a_service_base(self) -> None:
        manifest = self._materialize()
        manifest_path = self.shared / "runtime-topology/manifest.json"
        manifest["compose"] = [
            item
            for item in manifest["compose"]
            if not (
                item["role"] == "service"
                and item["service"] == "content-service"
                and item["layer"] == "base"
            )
        ]
        identity = {
            "compose": manifest["compose"],
            "policy": manifest["policy"],
            "observabilityPolicy": manifest["observabilityPolicy"],
            "serviceNames": manifest["serviceNames"],
            "runtimeServiceNames": manifest["runtimeServiceNames"],
            "serviceCoreModules": manifest["serviceCoreModules"],
            "compositionSbom": manifest["compositionSbom"],
        }
        # Keep the manifest internally self-consistent; the closure check must
        # still reject the omitted canonical service base.
        import hashlib

        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        manifest["topologyDigest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeTopologyPackageError, "closure is incomplete"):
            load_runtime_topology_package(
                self.candidate,
                environment="gamma",
                target="gamma-local",
                workload="full",
            )

    def test_declared_relative_bind_mount_is_sealed_into_the_candidate(self) -> None:
        self._write_compose(
            self.repo
            / "quwoquan_service/services/product-ops-service/deploy/compose.yaml",
            "product-ops-service",
            volumes=[
                "../../../quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml"
                ":/etc/qwq/observability/product_telemetry_alerts.yaml:ro",
            ],
        )

        self._materialize()
        result = load_runtime_topology_package(
            self.candidate,
            environment="gamma",
            target="gamma-local",
            workload="full",
        )

        sealed_policy = (
            self.shared / "runtime-topology/policies/product_telemetry_alerts.yaml"
        )
        self.assertEqual(
            sealed_policy.read_text(encoding="utf-8"),
            "schema: telemetry-alert-policy\n",
        )
        sealed_compose = next(
            path
            for path in result["composeFiles"]
            if "/services/product-ops-service/" in str(path)
        )
        compose = yaml.safe_load(sealed_compose.read_text(encoding="utf-8"))
        self.assertEqual(
            compose["services"]["product-ops-service"]["volumes"],
            [
                "./policies/product_telemetry_alerts.yaml"
                ":/etc/qwq/observability/product_telemetry_alerts.yaml:ro",
            ],
        )

    def test_undeclared_relative_bind_mount_is_rejected(self) -> None:
        self._write_compose(
            self.repo
            / "quwoquan_service/services/product-ops-service/deploy/compose.yaml",
            "product-ops-service",
            volumes=["../secrets.yaml:/etc/qwq/secrets.yaml:ro"],
        )

        with self.assertRaisesRegex(
            RuntimeTopologyPackageError,
            "escapes the immutable candidate",
        ):
            self._materialize()

    def test_observability_policy_drift_is_rejected(self) -> None:
        self._materialize()
        sealed_policy = (
            self.shared / "runtime-topology/policies/product_telemetry_alerts.yaml"
        )
        sealed_policy.write_text("schema: tampered\n", encoding="utf-8")

        with self.assertRaisesRegex(
            RuntimeTopologyPackageError,
            "observability policy artifact drifted",
        ):
            load_runtime_topology_package(
                self.candidate,
                environment="gamma",
                target="gamma-local",
                workload="full",
            )


if __name__ == "__main__":
    unittest.main()

"""local_contract: 部署包 provenance、结构闭包与凭据注入判据的正负例。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_environment_packaging_contract.py"

GIT_REVISION = "0" * 39 + "1"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_environment_packaging_contract", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(path: Path, payload: object) -> Path:
    return _write(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


class AppProvenanceTest(unittest.TestCase):
    """report.json 声明的摘要必须与包内真实字节一致。"""

    def _package(self, tmp: str) -> Path:
        package_dir = Path(tmp) / "app"
        _write(package_dir / "app_runtime.yaml", "gatewayBaseUrl: https://example\n")
        _write(package_dir / "config.yaml", "env: alpha\n")
        return package_dir

    def _report(self, package_dir: Path) -> dict[str, object]:
        return {
            "provenance": {
                "gitRevision": GIT_REVISION,
                "files": {
                    "appRuntime": _digest(package_dir / "app_runtime.yaml"),
                    "environmentConfig": _digest(package_dir / "config.yaml"),
                },
            }
        }

    def test_matching_digests_are_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            self.assertEqual(
                module.validate_provenance(self._report(package_dir), package_dir),
                [],
            )

    def test_missing_provenance_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            self.assertEqual(
                module.validate_provenance({"env": "alpha"}, package_dir),
                ["missing provenance"],
            )

    def test_non_exact_git_revision_is_rejected(self) -> None:
        """provenance 只接受 40 位精确 SHA：短 SHA 或分支名都无法唯一回指一次构建。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            report = self._report(package_dir)
            report["provenance"]["gitRevision"] = GIT_REVISION[:12]
            self.assertEqual(
                module.validate_provenance(report, package_dir),
                ["invalid provenance gitRevision"],
            )

    def test_empty_provenance_files_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            report = self._report(package_dir)
            report["provenance"]["files"] = {}
            self.assertEqual(
                module.validate_provenance(report, package_dir),
                ["missing provenance files"],
            )

    def test_digest_drift_after_packaging_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            report = self._report(package_dir)
            _write(package_dir / "app_runtime.yaml", "gatewayBaseUrl: https://tampered\n")
            self.assertEqual(
                module.validate_provenance(report, package_dir),
                ["provenance digest mismatch for appRuntime"],
            )

    def test_unknown_provenance_label_is_rejected(self) -> None:
        """标签是封闭映射；未知标签意味着包里多了一份没人校验的真相源。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            report = self._report(package_dir)
            report["provenance"]["files"]["extraRuntime"] = _digest(
                package_dir / "config.yaml"
            )
            self.assertEqual(
                module.validate_provenance(report, package_dir),
                ["unknown or missing provenance file extraRuntime"],
            )

    def test_legacy_release_files_provenance_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = self._package(tmp)
            report = self._report(package_dir)
            report["provenance"]["releaseFiles"] = {}
            self.assertEqual(
                module.validate_provenance(report, package_dir),
                ["legacy releaseFiles provenance is forbidden"],
            )


class PackageOutputBoundaryTest(unittest.TestCase):
    def test_package_inside_its_target_root_is_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "packages"
            package_dir = package_root / "app"
            package_dir.mkdir(parents=True)
            self.assertEqual(
                module.package_output_boundary_issues(package_dir, package_root),
                [],
            )

    def test_package_outside_its_target_root_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "packages"
            package_root.mkdir()
            package_dir = Path(tmp) / "elsewhere" / "app"
            package_dir.mkdir(parents=True)
            issues = module.package_output_boundary_issues(package_dir, package_root)
            self.assertEqual(len(issues), 1)
            self.assertIn("package escapes deployment package root", issues[0])

    def test_package_under_disposable_output_is_rejected(self) -> None:
        """`.qwq_output` 可以随时被删除重建，发布 payload 落在那里等于把交付物寄存在垃圾桶。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            disposable = Path(tmp) / "qwq-output"
            package_root = disposable / "packages"
            package_dir = package_root / "app"
            package_dir.mkdir(parents=True)
            previous = os.environ.get("QWQ_OUTPUT_ROOT")
            os.environ["QWQ_OUTPUT_ROOT"] = str(disposable)
            try:
                issues = module.package_output_boundary_issues(package_dir, package_root)
            finally:
                if previous is None:
                    os.environ.pop("QWQ_OUTPUT_ROOT", None)
                else:
                    os.environ["QWQ_OUTPUT_ROOT"] = previous
            self.assertEqual(len(issues), 1)
            self.assertIn("must not reside under disposable output", issues[0])


def _write_runtime_shared(module, package_dir: Path, environment: str) -> None:
    """铺出一份自洽的 runtime-shared 包：五份共享运行时文件 + provenance。"""
    payloads = {
        "Caddyfile": ":80 {\n\trespond 200\n}\n",
        "livekit.yaml": "port: 7880\n",
        "module_catalog.yaml": "modules: []\n",
        "object-storage-lifecycle.json": '{"rules": []}\n',
        "retention_policy.yaml": "retentionDays: 30\n",
    }
    files: dict[str, dict[str, str]] = {}
    for name, text in payloads.items():
        path = _write(package_dir / name, text)
        files[name] = {
            "source": module.RUNTIME_SHARED_SOURCE_PREFIXES[name] + name,
            "sha256": _digest(path),
        }
    _write_json(
        package_dir / "manifest.json",
        {
            "schema": "qwq.runtime_shared_package",
            "environment": environment,
            "provenance": {"files": files},
        },
    )


def _oci_images_payload(environment: str, target: str) -> dict[str, object]:
    images = {
        "demo-service": {
            "ref": "localhost/quwoquan_service_demo_service:" + "a" * 64,
            "imageDigest": "sha256:" + "b" * 64,
        }
    }
    image_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            images, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "stackctl-package-oci-images",
        "environment": environment,
        "target": target,
        "configurationDigest": "sha256:" + "c" * 64,
        "buildInputDigest": "sha256:" + "d" * 64,
        "imageDigest": image_digest,
        "images": images,
    }


class RuntimeSharedPackageTest(unittest.TestCase):
    def test_self_consistent_package_is_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            self.assertEqual(
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
                [],
            )

    def test_missing_manifest_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            package_dir.mkdir()
            self.assertEqual(
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
                ["missing runtime-shared manifest"],
            )

    def test_unparseable_manifest_is_reported_instead_of_raised(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write(package_dir / "manifest.json", "{not json")
            issues = module.validate_runtime_shared_package(
                package_dir, "alpha", "alpha-local"
            )
            self.assertEqual(len(issues), 1)
            self.assertIn("invalid runtime-shared manifest", issues[0])

    def test_environment_identity_mismatch_is_rejected(self) -> None:
        """包身份必须自带环境：错环境的 runtime-shared 装进来，服务会读到另一套端点。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "beta")
            issues = module.validate_runtime_shared_package(
                package_dir, "alpha", "alpha-local"
            )
            self.assertIn("runtime-shared package environment mismatch", issues)

    def test_incomplete_provenance_file_set_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest["provenance"]["files"].pop("livekit.yaml")
            _write_json(package_dir / "manifest.json", manifest)
            self.assertIn(
                "runtime-shared package provenance files mismatch",
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
            )

    def test_payload_digest_drift_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            _write(package_dir / "Caddyfile", ":80 {\n\trespond 500\n}\n")
            self.assertIn(
                "runtime-shared provenance digest mismatch for Caddyfile",
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
            )

    def test_provenance_source_outside_its_owning_tree_is_rejected(self) -> None:
        """每份共享文件只有一个 canonical owner 目录；source 指向别处就是第二真相源。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest["provenance"]["files"]["retention_policy.yaml"]["source"] = (
                "quwoquan_ops/environments/retention_policy.yaml"
            )
            _write_json(package_dir / "manifest.json", manifest)
            self.assertIn(
                "runtime-shared provenance source invalid for retention_policy.yaml",
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
            )

    def test_provenance_source_under_a_repo_checkout_prefix_is_accepted(self) -> None:
        """打包机上的 source 会带 `/…/repo/` 前缀；判据认的是归属目录而不是绝对路径。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest["provenance"]["files"]["livekit.yaml"]["source"] = (
                "/build/workspace/repo/quwoquan_ops/external/livekit/livekit.yaml"
            )
            _write_json(package_dir / "manifest.json", manifest)
            self.assertEqual(
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
                [],
            )

    def test_unexpected_extra_payload_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            _write(package_dir / "operator_notes.md", "手工补的文件\n")
            self.assertIn(
                "runtime-shared package structure contains unexpected or missing files",
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
            )

    def test_registered_extra_top_level_payload_is_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            _write(package_dir / "provider-runtime" / "bindings.json", "{}\n")
            self.assertEqual(
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
                [],
            )

    def test_oci_image_manifest_is_accepted_when_digest_covers_the_image_set(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            _write_json(
                package_dir / "oci-images.json",
                _oci_images_payload("alpha", "alpha-local"),
            )
            self.assertEqual(
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
                [],
            )

    def test_oci_image_set_digest_drift_is_rejected(self) -> None:
        """imageDigest 是整份镜像组合的唯一身份；换掉一个 ref 而不更新它就是身份撒谎。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            payload = _oci_images_payload("alpha", "alpha-local")
            payload["images"]["demo-service"]["imageDigest"] = "sha256:" + "e" * 64
            _write_json(package_dir / "oci-images.json", payload)
            self.assertIn(
                "package OCI image set digest mismatch",
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
            )

    def test_oci_image_target_identity_mismatch_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            _write_json(
                package_dir / "oci-images.json",
                _oci_images_payload("alpha", "beta-local"),
            )
            self.assertIn(
                "package OCI image manifest target identity mismatch",
                module.validate_runtime_shared_package(package_dir, "alpha", "alpha-local"),
            )

    def test_oci_image_descriptor_without_digest_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "runtime-shared"
            _write_runtime_shared(module, package_dir, "alpha")
            payload = _oci_images_payload("alpha", "alpha-local")
            payload["images"] = {"demo-service": {"ref": "localhost/demo"}}
            _write_json(package_dir / "oci-images.json", payload)
            issues = module.validate_runtime_shared_package(
                package_dir, "alpha", "alpha-local"
            )
            self.assertIn("package OCI image identity is invalid for demo-service", issues)


def _write_legal_static(package_root: Path, environment: str) -> Path:
    package_dir = package_root / "20260820T000000Z"
    _write_json(
        package_dir / "release_metadata.json",
        {"packageKind": "legal-static", "env": environment},
    )
    _write_json(package_dir / "public/legal/manifest.json", {"documents": []})
    checksums = {
        path.relative_to(package_dir).as_posix(): _digest(path)
        for path in sorted(package_dir.rglob("*"))
        if path.is_file()
    }
    _write_json(package_dir / "checksums.json", checksums)
    (package_root / "current").symlink_to(package_dir.name)
    return package_dir


class LegalStaticPackageTest(unittest.TestCase):
    def test_self_consistent_package_is_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "legal-static"
            package_root.mkdir()
            _write_legal_static(package_root, "gamma")
            self.assertEqual(
                module.validate_legal_static_package(package_root, "gamma"), []
            )

    def test_missing_current_pointer_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "legal-static"
            package_root.mkdir()
            self.assertEqual(
                module.validate_legal_static_package(package_root, "gamma"),
                ["missing legal-static current package pointer"],
            )

    def test_current_pointer_escaping_the_package_root_is_rejected(self) -> None:
        """`current` 是原子切换点；它指到包根之外，激活的就不再是本 target 的交付物。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "legal-static"
            package_root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (package_root / "current").symlink_to(outside)
            self.assertEqual(
                module.validate_legal_static_package(package_root, "gamma"),
                ["legal-static current package pointer escapes package root"],
            )

    def test_environment_mismatch_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "legal-static"
            package_root.mkdir()
            _write_legal_static(package_root, "beta")
            self.assertIn(
                "legal-static package environment mismatch",
                module.validate_legal_static_package(package_root, "gamma"),
            )

    def test_checksum_drift_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "legal-static"
            package_root.mkdir()
            package_dir = _write_legal_static(package_root, "gamma")
            _write_json(package_dir / "public/legal/manifest.json", {"documents": ["tos"]})
            self.assertIn(
                "legal-static digest mismatch for public/legal/manifest.json",
                module.validate_legal_static_package(package_root, "gamma"),
            )

    def test_unlisted_package_file_is_rejected(self) -> None:
        """checksums 必须是包内容的完备投影，否则夹带的文件永远不进校验面。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "legal-static"
            package_root.mkdir()
            package_dir = _write_legal_static(package_root, "gamma")
            _write(package_dir / "public/legal/extra.html", "<html></html>\n")
            self.assertIn(
                "legal-static checksum structure does not match package files",
                module.validate_legal_static_package(package_root, "gamma"),
            )


def _write_ops_portal(
    module,
    package_root: Path,
    environment: str,
    target: str,
) -> Path:
    staging = package_root / "staging"
    _write(staging / "dist/index.html", "<html>portal</html>\n")
    _write(staging / "dist/assets/app.js", "console.info('portal');\n")
    package_digest = module._sha256_tree(staging / "dist")
    package_dir = package_root / package_digest.removeprefix("sha256:")
    staging.rename(package_dir)

    manifest_path = _write_json(
        package_dir / "manifest.json",
        {
            "schema": "qwq.ops_portal_application",
            "sourceGitSha": GIT_REVISION,
            "sourceTreeDigest": "sha256:" + "f" * 64,
            "opsBaseUrl": "https://ops.example",
            "contentBaseUrl": "https://content.example",
            "entityBaseUrl": "https://entity.example",
            "oidcIssuer": "https://issuer.example",
            "oidcClientId": "ops-portal",
            "packageDigest": package_digest,
        },
    )
    _write_json(
        package_dir / "provenance.json",
        {
            "schema": "qwq.ops_portal_package",
            "packageKind": "ops-portal",
            "environment": environment,
            "target": target,
            "packageDigest": package_digest,
            "gitRevision": GIT_REVISION,
            "digests": {
                "manifest": _digest(manifest_path),
                "distTree": package_digest,
            },
        },
    )
    (package_root / "current").symlink_to(package_dir.name)
    return package_dir


class OpsPortalPackageTest(unittest.TestCase):
    def test_self_consistent_package_is_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "ops-portal"
            package_root.mkdir()
            _write_ops_portal(module, package_root, "prod", "prod-hosted")
            self.assertEqual(
                module.validate_ops_portal_package(
                    package_root, "prod", target="prod-hosted"
                ),
                [],
            )

    def test_dist_drift_after_naming_the_package_is_rejected(self) -> None:
        """包目录名即 dist 内容摘要；改完静态产物不重新打包就会被这条判据当场抓住。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "ops-portal"
            package_root.mkdir()
            package_dir = _write_ops_portal(module, package_root, "prod", "prod-hosted")
            _write(package_dir / "dist/index.html", "<html>tampered</html>\n")
            issues = module.validate_ops_portal_package(
                package_root, "prod", target="prod-hosted"
            )
            self.assertIn("ops-portal packageDigest does not match dist content", issues)
            self.assertIn("ops-portal provenance digest mismatch for distTree", issues)

    def test_missing_dist_entrypoint_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "ops-portal"
            package_root.mkdir()
            package_dir = _write_ops_portal(module, package_root, "prod", "prod-hosted")
            (package_dir / "dist/index.html").unlink()
            self.assertEqual(
                module.validate_ops_portal_package(
                    package_root, "prod", target="prod-hosted"
                ),
                ["ops-portal package dist/index.html missing"],
            )

    def test_target_mismatch_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "ops-portal"
            package_root.mkdir()
            _write_ops_portal(module, package_root, "prod", "prod-sim")
            self.assertIn(
                "ops-portal provenance target mismatch",
                module.validate_ops_portal_package(
                    package_root, "prod", target="prod-hosted"
                ),
            )

    def test_provenance_source_git_divergence_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "ops-portal"
            package_root.mkdir()
            package_dir = _write_ops_portal(module, package_root, "prod", "prod-hosted")
            provenance_path = package_dir / "provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["gitRevision"] = "1" * 40
            _write_json(provenance_path, provenance)
            self.assertIn(
                "ops-portal provenance source Git mismatch",
                module.validate_ops_portal_package(
                    package_root, "prod", target="prod-hosted"
                ),
            )

    def test_manifest_missing_a_required_endpoint_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_root = Path(tmp) / "ops-portal"
            package_root.mkdir()
            package_dir = _write_ops_portal(module, package_root, "prod", "prod-hosted")
            manifest_path = package_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["oidcIssuer"] = ""
            _write_json(manifest_path, manifest)
            issues = module.validate_ops_portal_package(
                package_root, "prod", target="prod-hosted"
            )
            self.assertIn("ops-portal manifest missing oidcIssuer", issues)


def _write_service_package(package_dir: Path) -> dict[str, str]:
    image_lock = _write(package_dir / "image.lock", "demo-service@sha256:" + "a" * 64 + "\n")
    config = _write(package_dir / "config/config.yaml", "env: alpha\n")
    manifests = _write(package_dir / "manifests/all.yaml", "apiVersion: v1\n")
    return {
        "imageLock": _digest(image_lock),
        "config": _digest(config),
        "manifests": _digest(manifests),
        "resources": "sha256:" + "1" * 64,
        "sourceTree": "sha256:" + "2" * 64,
    }


class ServiceProvenanceTest(unittest.TestCase):
    def _provenance(self, package_dir: Path) -> dict[str, object]:
        return {
            "schema": "qwq.service_package",
            "service": "demo-service",
            "environment": "alpha",
            "gitRevision": GIT_REVISION,
            "digests": _write_service_package(package_dir),
        }

    def test_self_consistent_package_is_accepted(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "demo-service"
            provenance = self._provenance(package_dir)
            self.assertEqual(
                module.validate_service_provenance(
                    provenance, package_dir, "demo-service", "alpha"
                ),
                [],
            )

    def test_identity_mismatch_is_rejected(self) -> None:
        """包身份必须同时锁住 service 与 environment，否则一份包能被装到任意位置。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "demo-service"
            provenance = self._provenance(package_dir)
            self.assertIn(
                "service package identity mismatch",
                module.validate_service_provenance(
                    provenance, package_dir, "demo-service", "beta"
                ),
            )

    def test_config_drift_after_packaging_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "demo-service"
            provenance = self._provenance(package_dir)
            _write(package_dir / "config/config.yaml", "env: beta\n")
            self.assertIn(
                "service package digest mismatch for config",
                module.validate_service_provenance(
                    provenance, package_dir, "demo-service", "alpha"
                ),
            )

    def test_missing_image_lock_is_rejected(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "demo-service"
            provenance = self._provenance(package_dir)
            (package_dir / "image.lock").unlink()
            self.assertIn(
                "missing imageLock artifact",
                module.validate_service_provenance(
                    provenance, package_dir, "demo-service", "alpha"
                ),
            )

    def test_absent_source_tree_digest_is_rejected(self) -> None:
        """`sourceTree` 是可复现构建的唯一锚点，缺席不能降级成「无所谓」。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "demo-service"
            provenance = self._provenance(package_dir)
            provenance["digests"].pop("sourceTree")
            self.assertIn(
                "invalid service package digest for sourceTree",
                module.validate_service_provenance(
                    provenance, package_dir, "demo-service", "alpha"
                ),
            )

    def test_missing_digests_short_circuits_without_raising(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "demo-service"
            _write_service_package(package_dir)
            provenance = {
                "schema": "qwq.service_package",
                "service": "demo-service",
                "environment": "alpha",
                "gitRevision": GIT_REVISION,
            }
            self.assertEqual(
                module.validate_service_provenance(
                    provenance, package_dir, "demo-service", "alpha"
                ),
                ["missing service package digests"],
            )


class ProductTelemetrySecretTest(unittest.TestCase):
    """Elasticsearch 凭据只能在部署期注入，包内不得留下已解析的值。"""

    def _issues(self, text: str) -> list[str]:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "product-ops-service"
            _write(package_dir / "config/config.yaml", text)
            return module.validate_product_telemetry_secret_package(package_dir)

    def test_unresolved_reference_is_accepted(self) -> None:
        self.assertEqual(
            self._issues('PRODUCT_OPS_ELASTICSEARCH_API_KEY: "${PRODUCT_OPS_ELASTICSEARCH_API_KEY}"\n'),
            [],
        )

    def test_empty_placeholder_is_accepted(self) -> None:
        self.assertEqual(
            self._issues('PRODUCT_OPS_ELASTICSEARCH_API_KEY: ""\n'),
            [],
        )

    def test_embedded_literal_is_rejected(self) -> None:
        issues = self._issues("PRODUCT_OPS_ELASTICSEARCH_API_KEY: redacted-literal\n")
        self.assertEqual(len(issues), 1)
        self.assertIn("PRODUCT_OPS_ELASTICSEARCH_API_KEY", issues[0])
        self.assertIn("injected at deployment time", issues[0])

    def test_embedded_literal_in_manifest_env_list_is_rejected(self) -> None:
        """k8s 的 `- name/value` 形态和 dotenv 形态是同一件事，判据不能只覆盖其中一种。"""
        issues = self._issues(
            "env:\n"
            "  - name: PRODUCT_OPS_ELASTICSEARCH_API_KEY\n"
            "    value: redacted-literal\n"
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("PRODUCT_OPS_ELASTICSEARCH_API_KEY", issues[0])

    def test_secret_key_reference_in_manifest_env_list_is_accepted(self) -> None:
        self.assertEqual(
            self._issues(
                "env:\n"
                "  - name: PRODUCT_OPS_ELASTICSEARCH_API_KEY\n"
                "    valueFrom:\n"
                "      secretKeyRef:\n"
                "        name: product-ops-telemetry\n"
                "        key: elasticsearchApiKey\n"
            ),
            [],
        )

    def test_unrelated_variable_is_not_inspected(self) -> None:
        self.assertEqual(self._issues("PRODUCT_OPS_LOG_LEVEL: info\n"), [])


class PackagedServiceRosterTest(unittest.TestCase):
    def test_service_roster_is_derived_from_the_physical_tree(self) -> None:
        """服务名册按物理树实时派生；写死清单会让新服务永远不进打包校验面。"""
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("demo-service", "another-service"):
                (root / "quwoquan_service/services" / name).mkdir(parents=True)
            _write(root / "quwoquan_service/services/README.md", "not a service\n")
            module.ROOT = root
            self.assertEqual(
                module.expected_services(), ["another-service", "demo-service"]
            )

            _write(
                root / "quwoquan_service/control-plane/platform-ops/config/schema.yaml",
                "service: platform-ops-service\n",
            )
            self.assertEqual(
                module.expected_services(),
                ["another-service", "demo-service", "platform-ops-service"],
            )

    def test_real_repository_roster_covers_first_party_services(self) -> None:
        module = _load_module()
        services = module.expected_services()
        self.assertEqual(services, sorted(services))
        self.assertIn("content-service", services)
        self.assertIn("platform-ops-service", services)

    def test_sha256_pattern_rejects_short_and_uppercase_digests(self) -> None:
        module = _load_module()
        self.assertIsNotNone(module.SHA256_RE.fullmatch("sha256:" + "a" * 64))
        self.assertIsNone(module.SHA256_RE.fullmatch("sha256:" + "a" * 63))
        self.assertIsNone(module.SHA256_RE.fullmatch("sha256:" + "A" * 64))
        self.assertIsNone(module.SHA256_RE.fullmatch("a" * 64))


if __name__ == "__main__":
    unittest.main()

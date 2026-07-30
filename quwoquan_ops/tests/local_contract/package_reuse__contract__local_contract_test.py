from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import package_reuse


class PackageReuseContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative, content in (
            ("quwoquan_app/source.txt", "app-source\n"),
            ("quwoquan_ops/source.txt", "ops-source\n"),
            (
                "quwoquan_service/services/content-service/source.txt",
                "content-source\n",
            ),
            (
                "quwoquan_service/services/user-service/source.txt",
                "user-source\n",
            ),
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "add", "quwoquan_app", "quwoquan_ops", "quwoquan_service"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Package Contract",
                "-c",
                "user.email=package-contract@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture baseline",
            ],
            cwd=self.root,
            check=True,
        )

        self.candidate_root = self.root / "deployment/candidate"
        self.package_root = self.candidate_root / "packages"
        self.app_dir = self.package_root / "app"
        self.shared_dir = self.package_root / "runtime-shared"
        self.legal_dir = self.package_root / "legal-static"
        self.service_root = self.package_root / "services"
        self.active_baseline_id = ""
        (self.app_dir / "report.json").parent.mkdir(parents=True, exist_ok=True)
        (self.app_dir / "report.json").write_text("{}\n", encoding="utf-8")
        (self.shared_dir / "manifest.json").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        (self.shared_dir / "manifest.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (self.legal_dir / "current").mkdir(parents=True)
        (self.legal_dir / "current/release_metadata.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        for service in ("content-service", "user-service"):
            path = self.service_root / service / "provenance.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")

        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(mock.patch.object(package_reuse, "ROOT", self.root))
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "app_deployment_package_dir",
                side_effect=lambda _env, *, target: self.app_dir,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "runtime_shared_deployment_package_dir",
                side_effect=lambda _env, *, target: self.shared_dir,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "legal_static_deployment_package_dir",
                side_effect=lambda _env, *, target: self.legal_dir,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "service_deployment_package_dir",
                side_effect=lambda _env, service, *, target: (
                    self.service_root / service
                ),
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "active_deployment_candidate",
                side_effect=lambda target: {
                    "target": target,
                    "baselineId": self.active_baseline_id,
                },
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "validate_candidate_manifest",
                side_effect=lambda payload, **_kwargs: payload,
            )
        )

    def _write(self, services: list[str] | None = None) -> Path:
        path = package_reuse.write_package_fingerprint(
            "alpha",
            "alpha-local",
            report_dir=".qwq_output/env/alpha/runs/package",
            include_services=True,
            details=["ready"],
            service_packages=services
            if services is not None
            else ["content-service", "user-service"],
        )
        fingerprint = json.loads(path.read_text(encoding="utf-8"))
        self.active_baseline_id = fingerprint["baselineId"]
        (self.candidate_root / "manifest.json").write_text(
            json.dumps(
                {
                    "baselineId": fingerprint["baselineId"],
                    "sourceRevision": fingerprint["sourceRevision"],
                    "workspaceStatusDigest": fingerprint["workspaceStatusDigest"],
                    "workspaceDigest": fingerprint["deploymentInputs"]["digest"],
                    "packageDigest": fingerprint["packageContent"]["digest"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_reuse_binds_current_managed_inputs_and_package_bytes(self) -> None:
        self._write()
        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")
        self.assertTrue(ok, detail)

        input_path = self.root / "quwoquan_ops/source.txt"
        input_path.write_text("changed\n", encoding="utf-8")
        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")
        self.assertFalse(ok)
        self.assertIn("baselineId mismatch", detail)

        input_path.write_text("ops-source\n", encoding="utf-8")
        package_path = self.service_root / "content-service/provenance.json"
        package_path.write_text('{"changed":true}\n', encoding="utf-8")
        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")
        self.assertFalse(ok)
        self.assertIn("package content digest mismatch", detail)

    def test_untracked_managed_input_invalidates_reuse(self) -> None:
        self._write()
        untracked = self.root / "quwoquan_ops/new_runtime_input.txt"
        untracked.write_text("new input\n", encoding="utf-8")
        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")
        self.assertFalse(ok)
        self.assertTrue(
            "baselineId mismatch" in detail
            or "workspaceStatusDigest mismatch" in detail
            or "deployment input digest mismatch" in detail,
            detail,
        )

    def test_old_or_identity_drifted_fingerprint_is_rejected(self) -> None:
        path = self._write()
        canonical = json.loads(path.read_text(encoding="utf-8"))
        cases = {
            "old contract": {
                "schema": "stackctl-package-fingerprint",
                "env": "alpha",
                "target": "alpha-local",
            },
            "environment drift": {**canonical, "environment": "beta"},
            "target drift": {**canonical, "target": "beta-local"},
            "includeServices drift": {**canonical, "includeServices": False},
            "schema drift": {
                **canonical,
                "schema": "stackctl-package-fingerprint",
            },
        }
        for label, payload in cases.items():
            with self.subTest(label=label):
                path.write_text(
                    json.dumps(payload, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                ok, detail = package_reuse.can_reuse_package(
                    "alpha",
                    "alpha-local",
                )
                self.assertFalse(ok, detail)
        path.write_text(
            json.dumps(canonical, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def test_partial_service_package_cannot_claim_full_reuse(self) -> None:
        self._write(["content-service"])
        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")
        self.assertFalse(ok)
        self.assertIn("servicePackages mismatch", detail)

    def test_fingerprint_file_is_not_part_of_its_own_package_digest(self) -> None:
        path = self._write()
        first = json.loads(path.read_text(encoding="utf-8"))
        self._write()
        second = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(first["packageContent"], second["packageContent"])


if __name__ == "__main__":
    unittest.main()

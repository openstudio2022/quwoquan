from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
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
        self.active_candidate_root = self.candidate_root
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
                    "candidateDir": str(self.active_candidate_root),
                },
            )
        )
        self.validate_candidate_manifest = mock.Mock(
            side_effect=lambda payload, **_kwargs: payload,
        )
        self.patches.enter_context(
            mock.patch.object(
                package_reuse,
                "validate_candidate_manifest",
                self.validate_candidate_manifest,
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

    def test_workspace_drift_reports_start_and_end_identity(self) -> None:
        start = package_reuse.workspace_snapshot()
        changed = self.root / "quwoquan_ops/new-runtime-input.txt"
        changed.write_text("changed during package\n", encoding="utf-8")
        end = package_reuse.workspace_snapshot()

        details = package_reuse.workspace_drift_details(start, end)

        self.assertEqual(
            details[0],
            "workspace changed while package was being materialized",
        )
        self.assertIn(f"startBaselineId={start['baselineId']}", details)
        self.assertIn(f"endBaselineId={end['baselineId']}", details)
        self.assertIn(
            "startDeploymentInputDigest="
            f"{start['deploymentInputDigest']}",
            details,
        )
        self.assertIn(
            "endDeploymentInputDigest="
            f"{end['deploymentInputDigest']}",
            details,
        )
        self.assertEqual(package_reuse.workspace_drift_details(end, end), [])

    def test_reuse_binds_current_managed_inputs_and_package_bytes(self) -> None:
        self._write()
        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")
        self.assertTrue(ok, detail)
        self.assertEqual(
            self.validate_candidate_manifest.call_args.kwargs["candidate_root"],
            self.candidate_root,
        )

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

    def test_fingerprint_never_uses_or_overwrites_fixed_temporary_entry(
        self,
    ) -> None:
        path = package_reuse.fingerprint_path("alpha", "alpha-local")
        fixed_temporary = path.with_name(f".{path.name}.tmp")
        external = self.root / "external-fingerprint.json"
        external.write_text("external remains unchanged\n", encoding="utf-8")
        safe_digest = package_reuse.package_content_digest(
            "alpha",
            "alpha-local",
            service_packages=["content-service", "user-service"],
        )

        for kind in ("symlink", "fifo", "regular"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    fixed_temporary.symlink_to(external)
                elif kind == "fifo":
                    os.mkfifo(fixed_temporary)
                else:
                    fixed_temporary.write_text("occupied\n", encoding="utf-8")
                before = os.lstat(fixed_temporary)
                with (
                    mock.patch.object(
                        package_reuse,
                        "package_content_digest",
                        return_value=safe_digest,
                    ),
                    self.assertRaisesRegex(
                        ValueError,
                        "legacy temporary path is occupied",
                    ),
                ):
                    self._write()
                after = os.lstat(fixed_temporary)
                self.assertEqual(
                    (before.st_dev, before.st_ino),
                    (after.st_dev, after.st_ino),
                )
                self.assertEqual(
                    external.read_text(encoding="utf-8"),
                    "external remains unchanged\n",
                )
                fixed_temporary.unlink()

        written = self._write()
        self.assertTrue(written.is_file())
        self.assertFalse(written.is_symlink())

    def test_fingerprint_rejects_unsafe_final_entry_without_touching_target(
        self,
    ) -> None:
        path = package_reuse.fingerprint_path("alpha", "alpha-local")
        external = self.root / "external-final.json"
        external.write_text("external remains unchanged\n", encoding="utf-8")
        path.unlink(missing_ok=True)
        path.symlink_to(external)

        with self.assertRaisesRegex(ValueError, "final path is a symlink"):
            self._write()

        self.assertTrue(path.is_symlink())
        self.assertEqual(
            external.read_text(encoding="utf-8"),
            "external remains unchanged\n",
        )

    def test_fingerprint_rejects_a_symlinked_parent_without_external_write(
        self,
    ) -> None:
        external_app = self.root / "external-app"
        external_app.mkdir()
        alias_root = self.root / "alias-packages"
        alias_root.mkdir()
        alias_app = alias_root / "app"
        alias_app.symlink_to(external_app, target_is_directory=True)
        previous_app_dir = self.app_dir
        self.app_dir = alias_app
        try:
            with (
                mock.patch.object(
                    package_reuse,
                    "package_content_digest",
                    return_value=("sha256:" + "a" * 64, 1),
                ),
                self.assertRaisesRegex(ValueError, "symlink or non-directory"),
            ):
                self._write()
        finally:
            self.app_dir = previous_app_dir

        self.assertFalse(
            (external_app / package_reuse.FINGERPRINT_NAME).exists()
        )

    def test_inherited_package_root_override_cannot_select_another_candidate(
        self,
    ) -> None:
        self._write()
        inherited_packages = self.root / "deployment/other/packages"
        with mock.patch.dict(
            os.environ,
            {package_reuse.PACKAGE_ROOT_OVERRIDE_ENV: str(inherited_packages)},
        ):
            ok, detail = package_reuse.can_reuse_package(
                "alpha",
                "alpha-local",
            )
        self.assertFalse(ok)
        self.assertIn("override is forbidden", detail)

    def test_non_active_candidate_fingerprint_is_not_reused(self) -> None:
        fingerprint = self._write()
        self.assertTrue(fingerprint.is_file())
        self.active_candidate_root = self.root / "deployment/active-candidate"

        ok, detail = package_reuse.can_reuse_package("alpha", "alpha-local")

        self.assertFalse(ok)
        self.assertIn(str(self.active_candidate_root), detail)
        self.assertIn("missing fingerprint", detail)

    def test_explicit_staging_candidate_can_be_reused_before_activation(self) -> None:
        self._write()
        self.active_candidate_root = self.root / "deployment/other-active"
        with mock.patch.dict(
            os.environ,
            {
                package_reuse.PACKAGE_ROOT_OVERRIDE_ENV: str(
                    self.candidate_root / "packages"
                )
            },
        ):
            ok, detail = package_reuse.can_reuse_package(
                "alpha",
                "alpha-local",
                candidate_root=self.candidate_root,
            )

        self.assertTrue(ok, detail)
        self.assertEqual(
            self.validate_candidate_manifest.call_args.kwargs["candidate_root"],
            self.candidate_root,
        )


if __name__ == "__main__":
    unittest.main()

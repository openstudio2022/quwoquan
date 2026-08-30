"""Package input capsule bytes and failure evidence stay CAS-bound.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import package_domain, package_runtime
from quwoquan_ops.cli.lib import package_reuse


class PackageInputCapsuleSizeContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / "quwoquan_ops/empty.bin"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"")
        (source.parent / "empty-link.bin").symlink_to("empty.bin")
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "quwoquan_ops"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Capsule Contract",
                "-c",
                "user.email=capsule-contract@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "empty input",
            ],
            cwd=self.root,
            check=True,
        )
        self.capsule_root = self.root / "capsule"
        with mock.patch.object(package_reuse, "ROOT", self.root):
            package_reuse.materialize_package_input_capsule(
                ["quwoquan_ops"],
                capsule_root=self.capsule_root,
            )

    def _manifest(self) -> dict[str, object]:
        return json.loads(
            (self.capsule_root / "manifest.json").read_text(encoding="utf-8")
        )

    def _write_manifest(self, payload: dict[str, object]) -> None:
        path = self.capsule_root / "manifest.json"
        path.chmod(0o600)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        path.chmod(0o444)

    def _entry(self, kind: str) -> dict[str, object]:
        return next(
            entry for entry in self._manifest()["entries"] if entry["kind"] == kind
        )

    def test_zero_byte_entry_is_valid_and_content_tamper_is_rejected(self) -> None:
        manifest = package_reuse.verify_package_input_capsule(self.capsule_root)
        entry = next(item for item in manifest["entries"] if item["kind"] == "file")
        self.assertEqual(entry["size"], 0)

        payload = self.capsule_root / str(entry["capsulePath"])
        payload.chmod(0o600)
        payload.write_bytes(b"tampered")
        payload.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "entry CAS mismatch"):
            package_reuse.verify_package_input_capsule(self.capsule_root)

    def test_size_field_rejects_bool_negative_string_and_other_types(self) -> None:
        canonical = self._manifest()
        for invalid in (True, False, -1, "0", 0.0, None, {}, []):
            with self.subTest(size=invalid):
                payload = json.loads(json.dumps(canonical))
                payload["entries"][0]["size"] = invalid
                self._write_manifest(payload)
                with self.assertRaisesRegex(ValueError, "entry size is invalid"):
                    package_reuse.verify_package_input_capsule(self.capsule_root)

    def test_file_mode_requires_exact_integer_schema_and_exact_permissions(
        self,
    ) -> None:
        canonical = self._manifest()
        file_index = next(
            index
            for index, entry in enumerate(canonical["entries"])
            if entry["kind"] == "file"
        )
        for invalid in (True, False, "292", 292.0, None, {}, []):
            with self.subTest(mode=invalid):
                payload = json.loads(json.dumps(canonical))
                payload["entries"][file_index]["mode"] = invalid
                self._write_manifest(payload)
                with self.assertRaisesRegex(ValueError, "entry mode is invalid"):
                    package_reuse.verify_package_input_capsule(self.capsule_root)

        payload = json.loads(json.dumps(canonical))
        payload["entries"][file_index]["mode"] = 0o555
        self._write_manifest(payload)
        with self.assertRaisesRegex(ValueError, "file mode drifted"):
            package_reuse.verify_package_input_capsule(self.capsule_root)

        file_entry = canonical["entries"][file_index]
        file_path = self.capsule_root / str(file_entry["capsulePath"])
        file_path.chmod(0o455)
        payload["entries"][file_index]["mode"] = 0o555
        self._write_manifest(payload)
        with self.assertRaisesRegex(ValueError, "file mode drifted"):
            package_reuse.verify_package_input_capsule(self.capsule_root)

    def test_symlink_mode_requires_exact_integer_zero(self) -> None:
        canonical = self._manifest()
        symlink_index = next(
            index
            for index, entry in enumerate(canonical["entries"])
            if entry["kind"] == "symlink"
        )
        for invalid in (True, False, "0", 0.0, None, {}, [], 0o444):
            with self.subTest(mode=invalid):
                payload = json.loads(json.dumps(canonical))
                payload["entries"][symlink_index]["mode"] = invalid
                self._write_manifest(payload)
                with self.assertRaisesRegex(ValueError, "entry mode is invalid"):
                    package_reuse.verify_package_input_capsule(self.capsule_root)


class PackageCapsuleFailureReceiptContractTest(unittest.TestCase):
    @staticmethod
    def _args(report_dir: Path) -> argparse.Namespace:
        return argparse.Namespace(
            command="package",
            kind="runtime",
            env="alpha",
            target="alpha-local",
            service="content-service",
            include_services=False,
            release_attestation="",
            rollback_release_attestation="",
            report_dir=str(report_dir),
        )

    def test_capsule_cas_failure_persists_typed_redacted_report_and_summary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_dir = root / "declared-report"
            source_root = root / "source"
            capsule_root = root / ".package-staging-test/input-capsule"
            source_root.mkdir()
            capsule_root.mkdir(parents=True)
            service_package = root / "service-package"
            completed = subprocess.CompletedProcess([], 0, "", "")
            with (
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value={}
                ),
                mock.patch.object(
                    stackctl, "resolve_report_dir", return_value=report_dir
                ),
                mock.patch.object(
                    stackctl, "target_cache_dir", return_value=root / "cache"
                ),
                mock.patch.object(
                    stackctl, "output_root", return_value=root / "output"
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_work_root",
                    return_value=root / "deploy/alpha-local",
                ),
                mock.patch.object(
                    stackctl,
                    "_run_runtime_compile_preflight",
                    return_value=([], ""),
                ),
                mock.patch.object(stackctl, "run", return_value=completed),
                mock.patch.object(
                    stackctl,
                    "service_deployment_package_dir",
                    return_value=service_package,
                ),
                mock.patch.object(
                    stackctl,
                    "verify_package_input_capsule",
                    side_effect=ValueError(
                        "token=must-not-leak package capsule byte drift"
                    ),
                ),
            ):
                result = package_runtime._command_package_unlocked(
                    self._args(report_dir),
                    package_snapshot={"baselineId": "sha256:" + "a" * 64},
                    package_input_roots=["quwoquan_ops"],
                    package_source_root=source_root,
                    package_capsule_root=capsule_root,
                )

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(
                result["firstBlocker"],
                package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER,
            )
            self.assertEqual(Path(result["reportDir"]), report_dir)
            for name in ("report.json", "summary.json", "summary.md"):
                path = report_dir / name
                self.assertTrue(path.is_file(), name)
                self.assertNotIn("must-not-leak", path.read_text(encoding="utf-8"))
            report = json.loads((report_dir / "report.json").read_text())
            self.assertEqual(report["status"], "GATE_BLOCK")
            self.assertEqual(
                report["firstBlocker"],
                package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER,
            )
            self.assertEqual(list(report_dir.glob(".*.tmp-*")), [])

    def test_mode_schema_drift_persists_typed_report_and_both_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_dir = root / "declared-report"
            source_root = root / "source"
            capsule_root = root / ".package-staging-test/input-capsule"
            source_root.mkdir()
            capsule_payload = capsule_root / "repo/input.bin"
            capsule_payload.parent.mkdir(parents=True)
            capsule_payload.write_bytes(b"")
            capsule_payload.chmod(0o444)
            capsule_payload.parent.chmod(0o555)
            manifest = {
                "schema": package_reuse.PACKAGE_INPUT_CAPSULE_SCHEMA,
                "baselineId": "sha256:" + "a" * 64,
                "sourceRevision": "b" * 40,
                "workspaceStatusDigest": "sha256:" + "c" * 64,
                "deploymentInputRoots": ["quwoquan_ops"],
                "deploymentInputDigest": "sha256:" + "d" * 64,
                "deploymentInputFileCount": 1,
                "entries": [
                    {
                        "logicalPath": "quwoquan_ops/input.bin",
                        "capsulePath": "repo/input.bin",
                        "kind": "file",
                        "digest": "sha256:"
                        + "e3b0c44298fc1c149afbf4c8996fb924"
                        + "27ae41e4649b934ca495991b7852b855",
                        "size": 0,
                        "mode": {},
                    }
                ],
            }
            manifest_path = capsule_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            manifest_path.chmod(0o444)
            capsule_root.chmod(0o555)
            completed = subprocess.CompletedProcess([], 0, "", "")
            with (
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value={}
                ),
                mock.patch.object(
                    stackctl, "resolve_report_dir", return_value=report_dir
                ),
                mock.patch.object(
                    stackctl, "target_cache_dir", return_value=root / "cache"
                ),
                mock.patch.object(
                    stackctl, "output_root", return_value=root / "output"
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_work_root",
                    return_value=root / "deploy/alpha-local",
                ),
                mock.patch.object(
                    stackctl,
                    "_run_runtime_compile_preflight",
                    return_value=([], ""),
                ),
                mock.patch.object(stackctl, "run", return_value=completed),
                mock.patch.object(
                    stackctl,
                    "service_deployment_package_dir",
                    return_value=root / "service-package",
                ),
            ):
                result = package_runtime._command_package_unlocked(
                    self._args(report_dir),
                    package_snapshot={"baselineId": "sha256:" + "a" * 64},
                    package_input_roots=["quwoquan_ops"],
                    package_source_root=source_root,
                    package_capsule_root=capsule_root,
                )

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(
                result["firstBlocker"],
                package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER,
            )
            for name in ("report.json", "summary.json"):
                payload = json.loads((report_dir / name).read_text(encoding="utf-8"))
                self.assertEqual(
                    payload["firstBlocker"],
                    package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER,
                    name,
                )
            summary_markdown = (report_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn(package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER, summary_markdown)


class PackageStagingCleanupContractTest(unittest.TestCase):
    def test_cas_primary_survives_cleanup_and_read_only_staging_is_removed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            baseline = "sha256:" + "b" * 64
            primary = package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER
            use_lock = mock.Mock()
            use_lock.close = mock.Mock()

            def candidate_dir(_target: str, identity: str) -> Path:
                return candidates / identity.replace(":", "-")

            def materialize(
                _roots: list[str], *, capsule_root: Path
            ) -> dict[str, object]:
                payload = capsule_root / "repo/input.bin"
                payload.parent.mkdir(parents=True)
                payload.write_bytes(b"")
                payload.chmod(0o444)
                payload.parent.chmod(0o555)
                capsule_root.chmod(0o555)
                return {"baselineId": baseline}

            def blocked(*_args: object, **_kwargs: object) -> dict[str, object]:
                return {
                    "exitCode": 2,
                    "summary": "capsule CAS blocked",
                    "details": ["primary CAS drift"],
                    "firstBlocker": primary,
                    "reportDir": str(root / "report"),
                }

            args = argparse.Namespace(
                command="package",
                kind="runtime",
                env="alpha",
                target="alpha-local",
                service="",
                include_services=True,
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
            )
            with (
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value={}
                ),
                mock.patch.object(
                    stackctl, "get_target", return_value={"backend": "local"}
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": [], "blocker": "", "evidence": {}},
                ),
                mock.patch.object(
                    stackctl, "validate_release_attestations", return_value={}
                ),
                mock.patch.object(
                    stackctl, "acquire_local_runtime_use_lock", return_value=use_lock
                ),
                mock.patch.object(
                    stackctl,
                    "_target_package_lock",
                    side_effect=lambda _target: contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "deployment_input_roots", return_value=[]),
                mock.patch.object(
                    stackctl,
                    "_resolve_graphql_read_signing_for_local_target",
                    return_value=object(),
                ),
                mock.patch.object(
                    stackctl, "deployment_candidate_dir", side_effect=candidate_dir
                ),
                mock.patch.object(
                    stackctl,
                    "materialize_package_input_capsule",
                    side_effect=materialize,
                ),
                mock.patch.object(
                    stackctl, "_command_package_unlocked", side_effect=blocked
                ),
            ):
                result = package_domain.command_package(args)

            self.assertEqual(result["firstBlocker"], primary)
            self.assertEqual(list(candidates.glob(".package-staging-*")), [])

    def test_cleanup_failure_is_secondary_to_the_capsule_cas_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary = package_runtime.PACKAGE_CAPSULE_CAS_BLOCKER
            payload = {
                "exitCode": 2,
                "details": ["primary CAS drift"],
                "firstBlocker": primary,
            }
            staging = root / ".package-staging-test"
            staging.mkdir()
            with mock.patch.object(
                package_domain,
                "remove_private_tree",
                side_effect=OSError("token=must-not-leak cleanup failed"),
            ):
                result = package_domain._cleanup_package_staging(staging, payload)

            self.assertEqual(result["firstBlocker"], primary)
            self.assertIn("primary CAS drift", result["details"])
            self.assertEqual(len(result["cleanupWarnings"]), 1)
            self.assertNotIn("must-not-leak", json.dumps(result))

    def test_materializer_runtime_error_survives_secondary_cleanup_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidates = root / "candidates"
            use_lock = mock.Mock()
            use_lock.close = mock.Mock()
            args = argparse.Namespace(
                command="package",
                kind="runtime",
                env="alpha",
                target="alpha-local",
                service="",
                include_services=True,
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
            )
            with (
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value={}
                ),
                mock.patch.object(
                    stackctl, "get_target", return_value={"backend": "local"}
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": [], "blocker": "", "evidence": {}},
                ),
                mock.patch.object(
                    stackctl, "validate_release_attestations", return_value={}
                ),
                mock.patch.object(
                    stackctl, "acquire_local_runtime_use_lock", return_value=use_lock
                ),
                mock.patch.object(
                    stackctl,
                    "_target_package_lock",
                    side_effect=lambda _target: contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "deployment_input_roots", return_value=[]),
                mock.patch.object(
                    stackctl,
                    "_resolve_graphql_read_signing_for_local_target",
                    return_value=object(),
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    side_effect=lambda _target, identity: (
                        candidates / identity.replace(":", "-")
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "materialize_package_input_capsule",
                    side_effect=RuntimeError("primary materializer failure"),
                ),
                mock.patch.object(
                    package_domain,
                    "remove_private_tree",
                    side_effect=OSError("token=must-not-leak cleanup failed"),
                ),
                self.assertRaisesRegex(
                    RuntimeError, "primary materializer failure"
                ) as raised,
            ):
                package_domain.command_package(args)

            notes = getattr(raised.exception, "__notes__", [])
            self.assertEqual(len(notes), 1)
            self.assertIn(package_domain.PACKAGE_STAGING_CLEANUP_BLOCKER, notes[0])
            self.assertNotIn("must-not-leak", notes[0])
            self.assertEqual(len(list(candidates.glob(".package-staging-*"))), 1)


if __name__ == "__main__":
    unittest.main()

"""Package input capsule bytes and failure evidence stay CAS-bound.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import package_domain, package_runtime
from quwoquan_ops.cli.lib import package_reuse
from quwoquan_ops.cli.lib.package_reuse import input_capsule


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


class PackageDependencyCapsuleReuseContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.candidates = self.root / "candidates/runtime-full"
        self.current = self.candidates / ".package-staging-current/input-capsule"
        self.current.parent.mkdir(parents=True)
        self.expected = {
            "dependency:dart-pub-cache-v2": {"schema": "production"},
            "dependency:patrol-host-dart-pub-cache-v1": {"schema": "patrol"},
            "dependency:production-ios-cocoapods-v2": {"schema": "production-ios"},
            "dependency:patrol-host-ios-cocoapods-v2": {"schema": "patrol-ios"},
            "dependency:android-gradle-v1": {"schema": "android"},
        }

    def _completed_capsule(self, name: str = "sha256-old") -> Path:
        candidate = self.candidates / name
        capsule = candidate / "input-capsule"
        (capsule / "dependencies").mkdir(parents=True)
        (capsule / "dependencies/payload").write_bytes(b"dependency")
        (candidate / "manifest.json").write_text(
            json.dumps(
                {
                    "candidateType": "runtime-full",
                    "baselineId": "sha256:" + "a" * 64,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (capsule / "manifest.json").write_text("{}\n", encoding="utf-8")
        return capsule

    def test_same_active_manifests_select_completed_capsule_despite_source_change(self) -> None:
        old = self._completed_capsule()
        records = [
            {"logicalPath": logical, "capsulePath": f"dependencies/{index}.json"}
            for index, logical in enumerate(self.expected)
        ]
        with (
            mock.patch.object(
                input_capsule,
                "_read_capsule_manifest",
                return_value={
                    "baselineId": "sha256:" + "a" * 64,
                    "entries": records,
                },
            ),
            mock.patch.object(
                input_capsule,
                "_capsule_dependency_payloads",
                return_value=self.expected,
            ),
            mock.patch.object(
                package_reuse,
                "validate_candidate_manifest",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ) as validate_candidate,
        ):
            selected = input_capsule._matching_dependency_capsules(
                capsule_root=self.current, expected=self.expected
            )

        self.assertEqual(selected, [(old, records)])
        validate_candidate.assert_called_once()

    def test_partial_candidate_manifest_is_rejected(self) -> None:
        self._completed_capsule()
        records = [
            {"logicalPath": logical, "capsulePath": f"dependencies/{index}.json"}
            for index, logical in enumerate(self.expected)
        ]
        with (
            mock.patch.object(
                input_capsule,
                "_read_capsule_manifest",
                return_value={
                    "baselineId": "sha256:" + "a" * 64,
                    "entries": records,
                },
            ),
            mock.patch.object(
                input_capsule,
                "_capsule_dependency_payloads",
                return_value=self.expected,
            ),
            mock.patch.object(
                package_reuse,
                "validate_candidate_manifest",
                side_effect=ValueError("deployment candidate manifest fields mismatch"),
            ),
            self.assertRaisesRegex(
                input_capsule.PackageDependencyDonorIntegrityError,
                "dependency_donor_integrity",
            ),
        ):
            input_capsule._matching_dependency_capsules(
                capsule_root=self.current, expected=self.expected
            )

    def test_cocoapods_identity_drift_rejected_before_donor_selection(self) -> None:
        manifests = dict(self.expected)
        manifests["dependency:production-ios-cocoapods-v2"] = {
            "schema": "production-ios",
            "cocoaPods": {"version": "stale"},
        }
        manifests["dependency:patrol-host-ios-cocoapods-v2"] = {
            "schema": "patrol-ios",
            "cocoaPods": {"version": "stale"},
        }
        with mock.patch.object(
            input_capsule,
            "_current_cocoapods_manifest_identity",
            return_value={"version": "current"},
        ), self.assertRaisesRegex(ValueError, "cocoapods_mixed"):
            input_capsule._assert_current_cocoapods_identity(manifests)

    def test_normal_five_component_donor_reuse_dispatches_clone_cas(self) -> None:
        old = self._completed_capsule()
        records = [
            {"logicalPath": logical, "capsulePath": f"dependencies/{index}.json"}
            for index, logical in enumerate(self.expected)
        ]
        staging = self.root / "package-staging-normal"
        staging.mkdir()
        marker_bytes = json.dumps({"schema": "marker"}).encode()
        clone_result = {"records": records}
        for index in range(len(records)):
            marker = staging / f"dependencies/{index}.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(marker_bytes)
        operations: list[str] = []

        def managed(operation: str, **_kwargs: object) -> dict[str, object]:
            operations.append(operation)
            if operation == "load-active":
                return {"manifests": self.expected}
            if operation == "clone-verify-dependencies":
                return clone_result
            if operation == "verify-full":
                expected_snapshot = _kwargs["expected_snapshot"]
                return {
                    "baselineId": expected_snapshot["baselineId"],
                    "deploymentInputDigest": expected_snapshot["deploymentInputDigest"],
                }
            raise AssertionError(operation)

        with (
            mock.patch.object(input_capsule, "dependency_required", return_value=True),
            mock.patch.object(
                input_capsule,
                "_enumerated_deployment_inputs",
                return_value=(["quwoquan_app"], []),
            ),
            mock.patch.object(
                input_capsule,
                "_matching_dependency_capsules",
                return_value=[(old, records)],
            ),
            mock.patch.object(
                input_capsule, "_run_capsule_managed_operation", side_effect=managed
            ),
            mock.patch.object(input_capsule.tempfile, "mkdtemp", return_value=str(staging)),
            mock.patch.object(package_reuse, "ROOT", self.root),
            mock.patch.object(
                input_capsule.subprocess,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "a" * 40 + "\n", ""),
                    subprocess.CompletedProcess([], 0, b"", b""),
                ],
            ),
        ):
            manifest = input_capsule.materialize_package_input_capsule(
                ["quwoquan_app"], capsule_root=self.root / "normal-capsule"
            )

        self.assertEqual(
            operations, ["load-active", "clone-verify-dependencies", "verify-full"]
        )
        self.assertEqual(
            len(
                [
                    item
                    for item in manifest["entries"]
                    if str(item["logicalPath"]).startswith("dependency:")
                ]
            ),
            5,
        )

    def test_stale_manifest_is_not_reused(self) -> None:
        self._completed_capsule()
        with (
            mock.patch.object(
                input_capsule,
                "_read_capsule_manifest",
                return_value={
                    "baselineId": "sha256:" + "a" * 64,
                    "entries": [],
                },
            ),
            mock.patch.object(
                input_capsule,
                "_capsule_dependency_payloads",
                return_value={"dependency:dart-pub-cache-v2": {"schema": "stale"}},
            ),
            mock.patch.object(
                package_reuse,
                "validate_candidate_manifest",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
        ):
            selected = input_capsule._matching_dependency_capsules(
                capsule_root=self.current, expected=self.expected
            )

        self.assertEqual(selected, [])

    def test_incomplete_and_staging_candidates_are_excluded(self) -> None:
        incomplete = self.candidates / "sha256-incomplete/input-capsule"
        incomplete.mkdir(parents=True)
        staging = self.candidates / ".package-staging-failed/input-capsule"
        staging.mkdir(parents=True)

        self.assertEqual(input_capsule._completed_capsule_candidates(self.current), [])

    def test_matching_donor_tamper_is_typed_fail_closed(self) -> None:
        old = self._completed_capsule()
        records = [{"logicalPath": logical} for logical in self.expected]
        staging = self.root / "package-staging"
        staging.mkdir()
        with (
            mock.patch.object(input_capsule, "dependency_required", return_value=True),
            mock.patch.object(
                input_capsule,
                "_enumerated_deployment_inputs",
                return_value=(["quwoquan_app"], []),
            ),
            mock.patch.object(
                input_capsule,
                "_run_capsule_managed_operation",
                side_effect=[
                    {"manifests": self.expected},
                    ValueError("cloned dependency CAS mismatch"),
                ],
            ),
            mock.patch.object(
                input_capsule,
                "_matching_dependency_capsules",
                return_value=[(old, records)],
            ),
            mock.patch.object(input_capsule.tempfile, "mkdtemp", return_value=str(staging)),
            mock.patch.object(package_reuse, "ROOT", self.root),
            self.assertRaisesRegex(
                input_capsule.PackageDependencyDonorIntegrityError,
                "dependency_donor_integrity",
            ),
        ):
            input_capsule.materialize_package_input_capsule(
                ["quwoquan_app"], capsule_root=self.root / "new-capsule"
            )

    def test_clone_verifies_new_dependency_bytes_and_rejects_tamper(self) -> None:
        old = self._completed_capsule()
        staging = self.root / "tampered-staging"
        staging.mkdir()
        request = {
            "operation": "clone-verify-dependencies",
            "repoRoot": str(self.root),
            "staging": str(staging),
            "sourceCapsule": str(old),
            "records": [{"logicalPath": "dependency:fixture"}],
            "resultPath": str(self.root / "tampered-result.json"),
        }

        request["requestDigest"] = "sha256:" + input_capsule.hashlib.sha256(
            input_capsule._canonical_json_bytes(request)
        ).hexdigest()

        def reject_clone(*, capsule_root: Path, manifest_entries: object) -> None:
            self.assertEqual(capsule_root, staging)
            self.assertEqual(
                (capsule_root / "dependencies/payload").read_bytes(), b"dependency"
            )
            self.assertEqual(manifest_entries, request["records"])
            raise ValueError("cloned dependency CAS mismatch")

        with mock.patch.object(
            input_capsule,
            "verify_dependency_bundle_capsule",
            side_effect=reject_clone,
        ):
            result = input_capsule._managed_child(request)

        self.assertEqual(result, 2)
        receipt = json.loads(Path(request["resultPath"]).read_text())
        self.assertEqual(receipt["status"], "error")
        self.assertIn("CAS mismatch", receipt["payload"]["detail"])

    def test_clone_accepts_only_after_new_dependency_cas(self) -> None:
        old = self._completed_capsule()
        staging = self.root / "verified-staging"
        staging.mkdir()
        result_path = self.root / "verified-result.json"
        request = {
            "operation": "clone-verify-dependencies",
            "repoRoot": str(self.root),
            "staging": str(staging),
            "sourceCapsule": str(old),
            "records": [{"logicalPath": "dependency:fixture"}],
            "resultPath": str(result_path),
        }
        request["requestDigest"] = "sha256:" + input_capsule.hashlib.sha256(
            input_capsule._canonical_json_bytes(request)
        ).hexdigest()
        verified = mock.Mock()
        with mock.patch.object(
            input_capsule,
            "verify_dependency_bundle_capsule",
            return_value=verified,
        ) as verifier:
            result = input_capsule._managed_child(request)

        self.assertEqual(result, 0)
        verifier.assert_called_once()
        self.assertEqual(json.loads(result_path.read_text())["status"], "ok")
        self.assertFalse((staging / "repo").exists())

    def test_managed_timeout_kills_and_reaps_blocking_process_group(self) -> None:
        script = self.root / "blocking.py"
        child_pid = self.root / "child.pid"
        fifo = self.root / "blocked-open.fifo"
        input_capsule.os.mkfifo(fifo)
        script.write_text(
            "import os, pathlib\n"
            f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid()))\n"
            f"open({str(fifo)!r}, 'rb').read()\n",
            encoding="utf-8",
        )
        real_runner = input_capsule.run_managed_subprocess
        request = mock.patch.object(
            input_capsule,
            "run_managed_subprocess",
            side_effect=lambda *_args, **kwargs: real_runner(
                [input_capsule.sys.executable, "-B", str(script)],
                cwd=self.root,
                env=dict(input_capsule.os.environ),
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=0.2,
            ),
        )
        with request, self.assertRaises(input_capsule.PackageDependencyInputTimeoutError):
            input_capsule._run_capsule_managed_operation(
                "verify-full",
                staging=self.current,
                expected_snapshot={},
                timeout=1,
            )
        pid = int(child_pid.read_text())
        with self.assertRaises(ProcessLookupError):
            input_capsule.os.kill(pid, 0)


class ManagedCapsuleRequestFileContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.staging = self.root / "attempt-staging"
        self.staging.mkdir()

    def _request(self, control: Path) -> dict[str, object]:
        return {
            "schema": input_capsule._MANAGED_RESULT_SCHEMA,
            "operation": "verify-full",
            "repoRoot": str(self.root),
            "staging": str(self.staging),
            "sourceCapsule": None,
            "records": [],
            "expectedSnapshot": {"baselineId": "sha256:" + "a" * 64},
            "resultPath": str(control / "result.json"),
        }

    def _write_request(self, control: Path, request: dict[str, object]) -> tuple[Path, str]:
        path = control / "request.json"
        encoded = input_capsule._canonical_json_bytes(request)
        input_capsule._write_private_managed_request(path, encoded)
        return path, "sha256:" + hashlib.sha256(encoded).hexdigest()

    def test_large_records_never_enter_argv_and_dispatch_succeeds(self) -> None:
        records = [{"logicalPath": f"dependency:{index}", "blob": "x" * 4096} for index in range(1024)]
        observed: dict[str, object] = {}

        def dispatch(command: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            argv = list(command)
            observed["argv"] = argv
            request_path = Path(argv[argv.index("--managed-request-path") + 1])
            control_root = Path(argv[argv.index("--managed-control-root") + 1])
            digest = argv[argv.index("--managed-request-digest") + 1]
            request = input_capsule._read_private_managed_request(
                request_path=request_path,
                control_root=control_root,
                declared_digest=digest,
            )
            self.assertGreater(len(input_capsule._canonical_json_bytes(request)), 4_000_000)
            input_capsule._write_managed_result(
                {**request, "requestDigest": digest},
                status="ok",
                payload={"records": records},
            )
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with (
            mock.patch.object(package_reuse, "ROOT", self.root),
            mock.patch.object(input_capsule, "run_managed_subprocess", side_effect=dispatch),
        ):
            payload = input_capsule._run_capsule_managed_operation(
                "clone-verify-dependencies",
                staging=self.staging,
                source_capsule=self.root / "donor",
                records=records,
                timeout=2,
            )
        self.assertEqual(payload["records"], records)
        self.assertLess(sum(len(str(item)) for item in observed["argv"]), 4096)
        self.assertEqual(list(self.root.glob("*.control")), [])

    def test_request_tamper_is_rejected_and_cleanup_is_possible(self) -> None:
        control = input_capsule._managed_control_root(self.staging, "verify-full")
        request = self._request(control)
        path, digest = self._write_request(control, request)
        path.write_bytes(path.read_bytes() + b" ")
        path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            input_capsule._read_private_managed_request(
                request_path=path, control_root=control, declared_digest=digest
            )
        path.unlink()
        control.rmdir()

    def test_symlink_escape_and_permissive_mode_are_rejected(self) -> None:
        for defect in ("symlink", "escape", "mode"):
            with self.subTest(defect=defect):
                control = input_capsule._managed_control_root(self.staging, "verify-full")
                request = self._request(control)
                path = control / "request.json"
                encoded = input_capsule._canonical_json_bytes(request)
                digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
                if defect == "symlink":
                    target = control / "target.json"
                    input_capsule._write_private_managed_request(target, encoded)
                    path.symlink_to(target)
                else:
                    input_capsule._write_private_managed_request(path, encoded)
                    if defect == "escape":
                        outside = self.root / "request.json"
                        path.replace(outside)
                        path = outside
                    else:
                        path.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "unsafe|escapes|identity mismatch"):
                    input_capsule._read_private_managed_request(
                        request_path=path,
                        control_root=control,
                        declared_digest=digest,
                    )
                if path.exists() or path.is_symlink():
                    path.unlink()
                target = control / "target.json"
                target.unlink(missing_ok=True)
                control.rmdir()

    def test_attempt_binding_rejects_result_path_drift(self) -> None:
        control = input_capsule._managed_control_root(self.staging, "verify-full")
        request = self._request(control)
        request["resultPath"] = str(self.root / "escaped-result.json")
        path, digest = self._write_request(control, request)
        with self.assertRaisesRegex(ValueError, "attempt binding mismatch"):
            input_capsule._read_private_managed_request(
                request_path=path, control_root=control, declared_digest=digest
            )
        path.unlink()
        control.rmdir()


class ManagedRuntimePackageEntryContractTest(unittest.TestCase):
    def test_entry_timeout_covers_attestation_open_and_reaps_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "blocking-package.py"
            child_pid = root / "child.pid"
            fifo = root / "attestation.fifo"
            input_capsule.os.mkfifo(fifo)
            script.write_text(
                "import os, pathlib, sys\n"
                f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid()))\n"
                "print('[package-entry-stage] before release attestation reads', "
                "file=sys.stderr, flush=True)\n"
                f"open({str(fifo)!r}, 'rb').read()\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(command="package", kind="runtime")
            original_argv = list(stackctl.sys.argv)
            original_executable = stackctl.sys.executable
            try:
                stackctl.sys.argv = [str(script)]
                stackctl.sys.executable = input_capsule.sys.executable
                with mock.patch.dict(
                    input_capsule.os.environ,
                    {"QWQ_PACKAGE_DEPENDENCY_LOAD_TIMEOUT_SECONDS": "1"},
                ):
                    payload = package_domain.run_managed_runtime_package_cli(args)
            finally:
                stackctl.sys.argv = original_argv
                stackctl.sys.executable = original_executable

            self.assertEqual(
                payload["firstBlocker"], package_domain.PACKAGE_ATTEMPT_TIMEOUT_BLOCKER
            )
            pid = int(child_pid.read_text())
            with self.assertRaises(ProcessLookupError):
                input_capsule.os.kill(pid, 0)

    def test_ambient_managed_child_environment_cannot_bypass_dispatch(self) -> None:
        args = argparse.Namespace(command="package", kind="runtime")
        with mock.patch.dict(
            input_capsule.os.environ,
            {"QWQ_PACKAGE_MANAGED_CHILD": "1"},
        ):
            self.assertTrue(package_domain.should_manage_runtime_package_cli(args))

    def test_real_inherited_capability_prevents_recursive_dispatch(self) -> None:
        args = argparse.Namespace(command="package", kind="runtime")
        with mock.patch.object(
            package_domain, "has_managed_parent_capability", return_value=True
        ):
            self.assertFalse(package_domain.should_manage_runtime_package_cli(args))

    def test_entry_timeout_reports_latest_runtime_stage(self) -> None:
        args = argparse.Namespace(command="package", kind="runtime")

        def timeout(*_args: object, **kwargs: object) -> object:
            kwargs["on_stderr"]("[runtime-package-stage] local-oci-images\n")
            raise subprocess.TimeoutExpired(["stackctl"], 1)

        with (
            mock.patch.object(package_domain.sys, "argv", ["stackctl.py", "package"]),
            mock.patch.object(package_domain, "run_managed_subprocess", side_effect=timeout),
            mock.patch.dict(
                input_capsule.os.environ,
                {"QWQ_PACKAGE_DEPENDENCY_LOAD_TIMEOUT_SECONDS": "1"},
            ),
        ):
            payload = package_domain.run_managed_runtime_package_cli(args)

        self.assertEqual(payload["firstBlocker"], package_domain.PACKAGE_ATTEMPT_TIMEOUT_BLOCKER)
        self.assertEqual(payload["timeoutStage"], "local-oci-images")

    def test_entry_normalizes_both_output_format_spellings_to_json(self) -> None:
        args = argparse.Namespace(command="package", kind="runtime")
        for supplied in (
            ["stackctl.py", "--output-format", "text", "package"],
            ["stackctl.py", "--output-format=text", "package"],
        ):
            with self.subTest(argv=supplied):
                captured: dict[str, object] = {}

                def run(command: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                    captured["command"] = command
                    return subprocess.CompletedProcess(
                        command, 0, stdout='{"exitCode":0}', stderr=""
                    )

                with (
                    mock.patch.object(package_domain.sys, "argv", supplied),
                    mock.patch.object(package_domain, "run_managed_subprocess", side_effect=run),
                ):
                    package_domain.run_managed_runtime_package_cli(args)
                command = list(captured["command"])
                self.assertEqual(command[3:5], ["--output-format", "json"])
                self.assertNotIn("text", command)
                self.assertNotIn("--output-format=text", command)


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

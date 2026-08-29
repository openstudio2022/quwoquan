"""Local contract for run-bound mutable-runtime content evidence.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import test_live_content_binding as subject
from quwoquan_ops.cli.lib import test_live_startup_attempt_receipt as startup_receipt

_A = "sha256:" + "a" * 64
_B = "sha256:" + "b" * 64
_C = "sha256:" + "c" * 64
_D = "sha256:" + "d" * 64
_E = "sha256:" + "e" * 64
_F = "sha256:" + "f" * 64


def _checksum(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class TestLiveContentBindingContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # macOS exposes /var as a symlink to /private/var.  The production
        # reader intentionally rejects symlinked parents, so build the fixture
        # below the canonical real temporary-directory path.
        self.root = Path(self.temporary.name).resolve() / "output"
        self.environment = "alpha"
        self.target = "alpha-local"
        self.attempt_id = "attempt-alpha-0001"
        self.release_id = "release-panda-001"
        self.verify_run_id = "verify-alpha-001"
        self.manifest_digest = _A
        self.process_dir = self.root / "env/alpha/local/alpha-local/process"
        self.runs_root = self.root / "env/alpha/runs"
        self.patches = (
            mock.patch.object(subject, "output_root", return_value=self.root),
            mock.patch.object(subject, "env_runs_root", return_value=self.runs_root),
            mock.patch.object(startup_receipt, "env_runs_root", return_value=self.runs_root),
            mock.patch.object(subject, "target_process_dir", return_value=self.process_dir),
            mock.patch.object(
                subject,
                "test_live_startup_attempt_path",
                return_value=self.process_dir / "test_live_startup_attempt.json",
            ),
        )
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.process_dir.mkdir(parents=True)
        self._write_startup()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _startup(self, *, status: str = "running", attempt_id: str | None = None) -> dict[str, object]:
        return {
            "schema": "stackctl.mutable_test_live_startup_attempt",
            "launchPolicy": "test_live",
            "nonPromotable": True,
            "contentBindingState": "unbound",
            "attemptId": attempt_id or self.attempt_id,
            "environment": self.environment,
            "target": self.target,
            "status": status,
            "workload": "full",
            "composeProject": "quwoquan_alpha_test_live",
            "composeDigest": _B,
            "configurationDigest": _C,
            "providerRuntimeDigest": _D,
            "portProfile": "alpha-local",
            "portBlock": {"start": 17000, "end": 17999},
            "publishedPorts": [
                {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"},
            ],
            "tlsProfile": "local-managed",
            "resolverHandoffDigest": _E,
            "publicWebPackage": {
                "environment": "alpha",
                "packageVersion": "web-release-alpha",
                "manifestDigest": _B,
                "contentDigest": _C,
                "publicOrigin": "https://alpha.quwoquan.com:17000",
            },
            "sourceRevision": "1" * 40,
            "workspaceStatusDigest": _F,
            "mutableStateDigest": _A,
            "runRoot": str(self.runs_root / "dev-session/run-alpha"),
            "startedAt": "2026-08-09T00:00:00Z",
            "updatedAt": "2026-08-09T00:01:00Z",
            "failure": None,
        }

    def _write_startup(self, *, status: str = "running", attempt_id: str | None = None) -> None:
        _write_json(
            self.process_dir / "test_live_startup_attempt.json",
            self._startup(status=status, attempt_id=attempt_id),
        )

    def _attestation(self, *, release_id: str, manifest_digest: str, commercial: bool) -> dict[str, object]:
        release_class = "commercial" if commercial else "research"
        return {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": release_id,
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": release_class,
            "productLifecycleState": release_class,
            "sourceRevision": _B,
            "sourceDigest": _C,
            "entityCatalogDigest": _D,
            "payloadSha256": manifest_digest,
        }

    def _readiness(
        self,
        *,
        release_id: str,
        verify_run_id: str,
        manifest_digest: str,
        phase: str,
        environment: str | None = None,
        import_run_id: str = "import-alpha-001",
    ) -> dict[str, object]:
        release_class = "commercial" if phase == "commercial" else "research"
        app_uat_envelope = {
            "releaseId": release_id,
            "releaseClass": release_class,
            "productLifecycleState": release_class,
            "homepageId": "homepage-harbour",
            "homepageTitle": "海港灯塔",
            "articleWorkId": "article-a",
            "articleTitle": "灯塔维护手记",
            "imageWorkId": "image-a",
            "imageTitle": "潮汐时刻",
            "videoWorkId": "video-a",
            "creatorName": "灯塔观察员",
            "creatorUserHandle": "lighthouse_observer",
            "creatorPersonaId": "persona-lighthouse",
            "creatorAvatarAssetId": "avatar-lighthouse",
            "tagLabel": "海港",
            "videoAttribution": "公开来源",
        }
        value: dict[str, object] = {
            "schema": "quwoquan_data.environment_release_readiness",
            "environment": environment or self.environment,
            "releaseId": release_id,
            "releaseKind": "content",
            "sourceOwner": "qwq_data",
            "releaseClass": release_class,
            "productLifecycleState": release_class,
            "sourceRevision": _B,
            "sourceDigest": _C,
            "entityCatalogDigest": _D,
            "readinessPhase": phase,
            "manifestDigest": manifest_digest,
            "importRunId": import_run_id,
            "verifyRunId": verify_run_id,
            "postIds": ["article-a", "image-a", "video-a"],
            "feedQueries": [
                {"name": "typed_video", "matchedPostIds": ["video-a"]},
                {
                    "name": "homepage_recommend",
                    "matchedPostIds": ["article-a", "image-a", "video-a"],
                },
            ],
            "appUatEnvelope": app_uat_envelope,
            "appUatEnvelopeDigest": _checksum(app_uat_envelope),
            "passed": True,
        }
        value["activationEnvelope"] = {
            "schema": "quwoquan_data.environment_activation_envelope",
            "environment": environment or self.environment,
            "releaseId": release_id,
            "manifestDigest": manifest_digest,
            "sourceRevision": _B,
            "sourceDigest": _C,
            "entityCatalogDigest": _D,
            "releaseClass": release_class,
            "productLifecycleState": release_class,
            "readinessPhase": phase,
            "importRunId": import_run_id,
            "verifyRunId": verify_run_id,
            "importReportRef": (
                f"env/{environment or self.environment}/runs/data-release/"
                f"{release_id}/{import_run_id}/import.json"
            ),
            "importReportDigest": _E,
            "appUatEnvelopeDigest": value["appUatEnvelopeDigest"],
        }
        value["activationEnvelopeDigest"] = _checksum(
            value["activationEnvelope"]  # type: ignore[arg-type]
        )
        value["verificationChecksum"] = _checksum(value)
        return value

    def _write_release(
        self,
        *,
        release_id: str | None = None,
        verify_run_id: str | None = None,
        manifest_digest: str | None = None,
        phase: str = "consumer",
        readiness_environment: str | None = None,
        import_run_id: str = "import-alpha-001",
    ) -> tuple[Path, Path]:
        release_id = release_id or self.release_id
        verify_run_id = verify_run_id or self.verify_run_id
        manifest_digest = manifest_digest or self.manifest_digest
        attestation_path = self.root / f"data/releases/{release_id}/attestations/release.json"
        readiness_path = self.runs_root / (
            f"data-release/{release_id}/{verify_run_id}/release-readiness.json"
        )
        _write_json(
            attestation_path,
            self._attestation(
                release_id=release_id,
                manifest_digest=manifest_digest,
                commercial=phase == "commercial",
            ),
        )
        _write_json(
            readiness_path,
            self._readiness(
                release_id=release_id,
                verify_run_id=verify_run_id,
                manifest_digest=manifest_digest,
                phase=phase,
                environment=readiness_environment,
                import_run_id=import_run_id,
            ),
        )
        return attestation_path, readiness_path

    def _rewrite_release_as_aggregate_identity(
        self,
        attestation_path: Path,
        readiness_path: Path,
    ) -> dict[str, object]:
        identities: list[dict[str, object]] = [
            {
                "sourceRevision": _B,
                "sourceDigest": _C,
                "entityCatalogDigest": _D,
                "executionIds": ["execution-alpha-001", "execution-alpha-002"],
            }
        ]
        identity = {
            "sourceIdentities": identities,
            "sourceIdentitySetDigest": _checksum(
                {
                    "schema": "quwoquan_data.source_identity_set",
                    "sourceIdentities": identities,
                }
            ),
        }
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        for document in (attestation, readiness, readiness["activationEnvelope"]):
            for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
                document.pop(field)
            document.update(identity)
        readiness["activationEnvelopeDigest"] = _checksum(
            readiness["activationEnvelope"]
        )
        readiness.pop("verificationChecksum")
        readiness["verificationChecksum"] = _checksum(readiness)
        _write_json(attestation_path, attestation)
        _write_json(readiness_path, readiness)
        return identity

    def _lifecycle(
        self,
        *,
        release_id: str,
        manifest_digest: str,
        exit_run_id: str,
        original_verify_run_id: str,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": "quwoquan_data.environment_release_lifecycle_exit",
            "environment": self.environment,
            "sourceOwner": "qwq_data",
            "exitRunId": exit_run_id,
            "originalReleaseId": release_id,
            "originalManifestDigest": manifest_digest,
            "originalImportRunId": "import-alpha-001",
            "originalVerifyRunId": original_verify_run_id,
            "originalImportResultRef": f"env/alpha/runs/data-release/{release_id}/import-alpha-001/result.json",
            "originalVerifyResultRef": f"env/alpha/runs/data-release/{release_id}/{original_verify_run_id}/result.json",
            "rollbackToReleaseId": "release-baseline-001",
            "rollbackToManifestDigest": _B,
            "rollbackRunId": "rollback-alpha-001",
            "rollbackVerifyRunId": "rollback-verify-alpha-001",
            "rollbackResultRef": "env/alpha/runs/data-release/release-baseline-001/rollback-alpha-001/result.json",
            "rollbackVerifyResultRef": "env/alpha/runs/data-release/release-baseline-001/rollback-verify-alpha-001/result.json",
            "replayImportRunId": "replay-alpha-001",
            "replayVerifyRunId": "replay-verify-alpha-001",
            "replayManifestDigest": manifest_digest,
            "replayImportResultRef": f"env/alpha/runs/data-release/{release_id}/replay-alpha-001/result.json",
            "replayVerifyResultRef": f"env/alpha/runs/data-release/{release_id}/replay-verify-alpha-001/result.json",
            "recordedAt": "2026-08-09T00:02:00Z",
            "passed": True,
        }
        value["verificationChecksum"] = _checksum(value)
        return value

    def _create(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "environment": self.environment,
            "target": self.target,
            "startup_attempt_id": self.attempt_id,
            "release_id": self.release_id,
            "verify_run_id": self.verify_run_id,
            "manifest_digest": self.manifest_digest,
        }
        arguments.update(overrides)
        return subject.create_test_live_content_binding(**arguments)  # type: ignore[arg-type]

    def test_consumer_binding_is_create_once_run_bound_and_non_promotable(self) -> None:
        self._write_release()

        first = self._create()
        second = self._create()

        self.assertEqual(first, second)
        self.assertEqual(first["launchPolicy"], "test_live")
        self.assertIs(first["nonPromotable"], True)
        self.assertEqual(first["retentionClass"], "run_bound")
        self.assertEqual(first["contentBindingState"], "bound")
        self.assertEqual(first["startupAttemptId"], self.attempt_id)
        self.assertEqual(first["readinessPhase"], "consumer")
        self.assertEqual(
            first["dataSourceIdentity"],
            {
                "sourceRevision": _B,
                "sourceDigest": _C,
                "entityCatalogDigest": _D,
            },
        )
        activation = first["activationEnvelope"]
        self.assertIsInstance(activation, dict)
        self.assertEqual(first["activationEnvelopeDigest"], _checksum(activation))
        self.assertEqual(
            activation["appUatEnvelopeDigest"],
            first["appUatEnvelopeDigest"],
        )
        self.assertEqual(first["lifecycleExitRef"], "")
        self.assertEqual(
            first["appUatPlan"]["searchCanaries"][0],
            {
                "kind": "post",
                "query": "灯塔维护手记",
                "expectedObjectType": "content.post",
                "expectedObjectId": "article-a",
            },
        )
        self.assertEqual(
            first["appUatPlan"]["videoPlaybackCanaries"],
            [{"position": "first", "index": 0, "workId": "video-a"}],
        )
        self.assertEqual(first["appUatPlanDigest"], _checksum(first["appUatPlan"]))
        self.assertNotIn("candidate", json.dumps(first).lower())
        self.assertNotIn("package", json.dumps(first).lower())
        binding_path = self.process_dir / (
            f"test_live_content_binding.{self.attempt_id}.json"
        )
        self.assertTrue(stat.S_ISREG(binding_path.lstat().st_mode))
        self.assertEqual(stat.S_IMODE(binding_path.stat().st_mode), 0o600)
        self.assertEqual(subject.load_test_live_content_binding(self.target), first)

    def test_binding_rejects_an_unreviewed_readiness_receipt_digest(self) -> None:
        self._write_release()

        with self.assertRaisesRegex(ValueError, "readiness receipt digest mismatch"):
            self._create(expected_readiness_receipt_digest=_A)

    def test_consumer_binding_accepts_canonical_aggregate_source_identity(self) -> None:
        attestation_path, readiness_path = self._write_release()
        identity = self._rewrite_release_as_aggregate_identity(
            attestation_path,
            readiness_path,
        )

        result = self._create()

        self.assertEqual(result["dataSourceIdentity"], identity)
        self.assertEqual(result["activationEnvelope"]["sourceIdentities"], identity["sourceIdentities"])

    def test_consumer_binding_rejects_mixed_source_identity_representations(self) -> None:
        attestation_path, readiness_path = self._write_release()
        self._rewrite_release_as_aggregate_identity(attestation_path, readiness_path)
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        attestation["sourceRevision"] = _B
        _write_json(attestation_path, attestation)

        with self.assertRaisesRegex(ValueError, "representations must not be mixed"):
            self._create()

    def test_research_binding_never_requires_commercial_lifecycle_exit(self) -> None:
        self._write_release(phase="research")

        result = self._create(lifecycle_exit_ref="")

        self.assertEqual(result["readinessPhase"], "research")
        self.assertEqual(result["lifecycleExitRef"], "")
        self.assertEqual(result["lifecycleExitDigest"], "")

    def test_commercial_requires_complete_lifecycle_quartet(self) -> None:
        self._write_release(phase="commercial")
        with self.assertRaisesRegex(ValueError, "requires explicit lifecycleExitRef"):
            self._create()

        ref = (
            f"env/alpha/runs/release-lifecycle-exit/{self.release_id}/"
            "exit-alpha-001/lifecycle-exit.json"
        )
        _write_json(
            self.root / ref,
            self._lifecycle(
                release_id=self.release_id,
                manifest_digest=self.manifest_digest,
                exit_run_id="exit-alpha-001",
                original_verify_run_id=self.verify_run_id,
            ),
        )
        result = self._create(lifecycle_exit_ref=ref)
        self.assertEqual(result["readinessPhase"], "commercial")
        self.assertEqual(result["lifecycleExitRef"], ref)
        self.assertRegex(str(result["lifecycleExitDigest"]), r"^sha256:[0-9a-f]{64}$")

    def test_rejects_stale_partial_cross_environment_and_implicit_identity(self) -> None:
        self._write_release()
        with self.assertRaisesRegex(ValueError, "startupAttemptId is invalid"):
            self._create(startup_attempt_id="")
        with self.assertRaisesRegex(ValueError, "releaseId is invalid"):
            self._create(release_id="")
        with self.assertRaisesRegex(ValueError, "verifyRunId is invalid"):
            self._create(verify_run_id="")
        with self.assertRaisesRegex(ValueError, "manifestDigest"):
            self._create(manifest_digest="")
        with self.assertRaisesRegex(ValueError, "exact running startup attempt"):
            self._create(startup_attempt_id="attempt-alpha-stale")
        self._write_startup(status="partial")
        with self.assertRaisesRegex(ValueError, "exact running startup attempt"):
            self._create()
        self._write_startup()
        self._write_release(readiness_environment="beta")
        with self.assertRaisesRegex(ValueError, "readiness environment mismatch"):
            self._create()

    def test_rejects_symlink_escape_and_in_process_evidence_change(self) -> None:
        _attestation, readiness = self._write_release()
        real_readiness = readiness.with_name("real-release-readiness.json")
        readiness.replace(real_readiness)
        os.symlink(real_readiness, readiness)
        with self.assertRaisesRegex(subject.UnsafeTestLiveContentBindingPath, "symlink"):
            self._create()

        readiness.unlink()
        real_readiness.replace(readiness)
        first = subject._load_evidence(
            environment=self.environment,
            target=self.target,
            startup_attempt_id=self.attempt_id,
            release_id=self.release_id,
            verify_run_id=self.verify_run_id,
            manifest_digest=self.manifest_digest,
            lifecycle_exit_ref="",
        )
        changed_snapshot = replace(
            first.readiness_snapshot,
            digest=_B,
        )
        changed = replace(first, readiness_snapshot=changed_snapshot)
        with mock.patch.object(subject, "_load_evidence", side_effect=[first, changed]):
            with self.assertRaisesRegex(
                subject.UnsafeTestLiveContentBindingPath,
                "changed before binding",
            ):
                self._create()

    def test_existing_binding_cannot_be_rebound_but_new_attempt_gets_new_record(self) -> None:
        self._write_release()
        first = self._create()

        release_b = "release-panda-002"
        verify_b = "verify-alpha-002"
        manifest_b = _B
        self._write_release(
            release_id=release_b,
            verify_run_id=verify_b,
            manifest_digest=manifest_b,
        )
        with self.assertRaisesRegex(ValueError, "cannot be rebound"):
            self._create(
                release_id=release_b,
                verify_run_id=verify_b,
                manifest_digest=manifest_b,
            )

        self._write_startup(attempt_id="attempt-alpha-0002")
        self.assertIsNone(subject.load_test_live_content_binding(self.target))
        second = subject.create_test_live_content_binding(
            environment=self.environment,
            target=self.target,
            startup_attempt_id="attempt-alpha-0002",
            release_id=self.release_id,
            verify_run_id=self.verify_run_id,
            manifest_digest=self.manifest_digest,
        )
        self.assertEqual(second["startupAttemptId"], "attempt-alpha-0002")
        self.assertEqual(first["startupAttemptId"], self.attempt_id)

    def test_lifecycle_ref_is_environment_scoped_and_cannot_escape(self) -> None:
        self._write_release(phase="commercial")
        for ref in (
            "../lifecycle-exit.json",
            f"env/beta/runs/release-lifecycle-exit/{self.release_id}/exit/lifecycle-exit.json",
            "env/alpha/runs/release-lifecycle-exit/other-release/exit/lifecycle-exit.json",
        ):
            with self.subTest(ref=ref):
                with self.assertRaisesRegex(ValueError, "lifecycleExitRef"):
                    self._create(lifecycle_exit_ref=ref)


if __name__ == "__main__":
    unittest.main()

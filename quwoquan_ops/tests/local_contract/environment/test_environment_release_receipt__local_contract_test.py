# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.ci.render_environment_release_receipt import (
    RELEASE_CLOSURE_PATHS,
    _canonical_digest,
    archive_environment_evidence,
    archive_exact_files,
    render,
    validate_release_closure_sources,
)


class EnvironmentReleaseReceiptTest(unittest.TestCase):
    candidate_id = "sha256:" + "c" * 64
    source_git_sha = "a" * 40
    source_tree_digest = "sha1:" + "b" * 40
    contract_graph_digest = "sha256:" + "9" * 64
    # Each environment builds its own gateway image from the shared capsule, so
    # no two environments may present the same immutable digest.
    image_digest_by_environment = {
        "alpha": "sha256:" + "a" * 64,
        "beta": "sha256:" + "b" * 64,
        "gamma": "sha256:" + "c" * 63 + "1",
        "prod": "sha256:" + "e" * 64,
    }

    def _image(self, environment: str) -> dict[str, str]:
        digest = self.image_digest_by_environment[environment]
        return {
            "ref": f"ghcr.io/owner/repo/gateway-{environment}@{digest}",
            "digest": digest,
        }

    def _manifest(self, *, status: str = "candidate-ready") -> dict:
        return {
            "status": status,
            "candidateId": self.candidate_id,
            "artifactDigest": "sha256:" + "d" * 64,
            "contractGraphDigest": self.contract_graph_digest,
            "source": {
                "gitSha": self.source_git_sha,
                "treeDigest": self.source_tree_digest,
                "repository": "owner/repo",
            },
            "environmentArtifacts": {
                environment: {
                    "environment": environment,
                    "images": {"gateway": self._image(environment)},
                }
                for environment in self.image_digest_by_environment
            },
        }

    def _runtime_up(self, environment: str) -> dict:
        return {
            "command": "up",
            "target": f"{environment}-local",
            "steps": [{"name": "compose", "exitCode": 0}],
            "formalRelease": True,
            "releaseInputClassification": "commercial_inputs",
            "contractGraphDigest": self.contract_graph_digest,
            "runtimeMode": "immutable-oci",
            "runtimeCandidateDigest": self.candidate_id,
            "runtimeImages": {"gateway": self._image(environment)},
            "destructiveRepairPerformed": False,
            "destructiveActions": [],
            "endedAt": "2026-07-28T00:00:11Z",
        }

    def _preprod_evidence(self, environment: str) -> dict[str, dict]:
        evidence = {
            "up": self._runtime_up(environment),
            "health": {
                "command": "health",
                "target": f"{environment}-local",
                "checks": [{"ok": True}],
                "findings": [],
                "endedAt": "2026-07-28T00:00:12Z",
            },
            "verify": {
                "status": "passed",
                "env": environment,
                "target": f"{environment}-local",
                "endedAt": "2026-07-28T00:00:13Z",
            },
        }
        if environment == "beta":
            evidence["devices"] = {
                "schema": "release-device-matrix-evidence",
                "environment": "beta",
                "target": "beta-local",
                "status": "passed",
                "candidateId": self.candidate_id,
                "sourceGitSha": self.source_git_sha,
                "sourceTreeDigest": self.source_tree_digest,
                "platforms": {
                    "android": {"android.json": "sha256:" + "1" * 64},
                    "ios": {"ios.json": "sha256:" + "2" * 64},
                },
                "endedAt": "2026-07-28T00:00:14Z",
            }
        return evidence

    def _release_closure(self, environment: str) -> dict[str, dict]:
        candidate = {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": "pilot-003",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "payloadSha256": "sha256:" + "6" * 64,
            "recordedAt": "2026-07-28T00:00:05Z",
        }
        rollback = {
            "schema": "quwoquan_data.release_attestation",
            "releaseId": "pilot-002",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "payloadSha256": "sha256:" + "7" * 64,
            "recordedAt": "2026-07-28T00:00:04Z",
        }
        lifecycle = {
            "schema": "quwoquan_data.environment_release_lifecycle_exit",
            "environment": environment,
            "passed": True,
            "sourceOwner": "qwq_data",
            "originalReleaseId": candidate["releaseId"],
            "originalManifestDigest": candidate["payloadSha256"],
            "replayManifestDigest": candidate["payloadSha256"],
            "rollbackToReleaseId": rollback["releaseId"],
            "rollbackToManifestDigest": rollback["payloadSha256"],
            "recordedAt": "2026-07-28T00:00:15Z",
        }
        lifecycle["verificationChecksum"] = _canonical_digest(lifecycle)
        return {
            "pilot-release": candidate,
            "pilot-rollback": rollback,
            "content-lifecycle": lifecycle,
        }

    def _package(self, *, environment: str = "alpha") -> dict:
        target = {
            "alpha": "alpha-local",
            "beta": "beta-local",
            "gamma": "gamma-local",
            "prod": "prod-hosted",
        }[environment]
        return {
            "command": "package",
            "env": environment,
            "target": target,
            "status": "ok",
            "candidateId": self.candidate_id,
            "artifactDigest": "sha256:" + "d" * 64,
            "sourceGitSha": self.source_git_sha,
            "sourceTreeDigest": self.source_tree_digest,
            "releaseInputClassification": "commercial_inputs",
            "contractGraphDigest": self.contract_graph_digest,
            "endedAt": "2026-07-28T00:00:10Z",
        }

    def _render(
        self,
        *,
        root: Path,
        package: dict | None = None,
        extra: dict[str, dict] | None = None,
        environment: str = "alpha",
    ) -> dict:
        evidence: dict[str, tuple[Path, dict]] = {}
        package_payload = package or self._package(environment=environment)
        package_path = root / "package.json"
        package_path.write_text(json.dumps(package_payload), encoding="utf-8")
        evidence["package"] = (package_path, package_payload)
        supplemental = (
            {
                **self._preprod_evidence(environment),
                **self._release_closure(environment),
            }
            if environment in {"alpha", "beta", "gamma"}
            else {}
        )
        supplemental.update(extra or {})
        for label, payload in supplemental.items():
            path = root / f"{label}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            evidence[label] = (path, payload)
        with patch(
            "quwoquan_ops.ci.render_environment_release_receipt.validate_manifest"
        ):
            return render(
                manifest=self._manifest(
                    status="deployable" if environment == "prod" else "candidate-ready"
                ),
                environment=environment,
                evidence=evidence,
                required_evidence=list(evidence),
                archive_prefix=f"evidence/raw/environments/{environment}/raw",
            )

    def test_passed_package_binds_candidate_and_source_without_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = self._render(root=Path(temporary))
        self.assertEqual(receipt["candidateId"], self.candidate_id)
        self.assertEqual(receipt["sourceGitSha"], self.source_git_sha)
        self.assertRegex(receipt["evidenceDigest"], r"^sha256:[0-9a-f]{64}$")

    def test_native_stackctl_reports_are_hashed_without_rewrapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = self._render(
                root=Path(temporary),
                extra={
                    "up": {
                        **self._runtime_up("alpha"),
                    },
                    "health": {
                        "command": "health",
                        "target": "alpha-local",
                        "checks": [{"ok": True}],
                        "findings": [],
                        "endedAt": "2026-07-28T00:00:12Z",
                    },
                },
            )
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["verifiedAt"], "2026-07-28T00:00:15Z")
        self.assertEqual(
            receipt["evidence"]["files"]["pilot-release"]["path"],
            RELEASE_CLOSURE_PATHS["pilot-release"],
        )

    def test_rewrapped_candidate_evidence_is_rejected(self) -> None:
        wrapped = {
            "schema": "candidate-bound-environment-evidence",
            "status": "passed",
            "endedAt": "2026-07-28T00:00:10Z",
        }
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError, "rewrapped"
        ):
            self._render(root=Path(temporary), extra={"verify": wrapped})

    def test_package_must_bind_exact_candidate_and_source(self) -> None:
        cases = {
            "candidateId": "candidateId",
            "artifactDigest": "artifactDigest",
            "sourceGitSha": "source Git SHA",
            "sourceTreeDigest": "source tree",
        }
        for field, message in cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                payload = self._package()
                payload[field] = "wrong"
                with self.assertRaisesRegex(ValueError, message):
                    self._render(root=Path(temporary), package=payload)

    def test_missing_direct_package_binding_is_gate_block(self) -> None:
        payload = self._package()
        payload.pop("candidateId")
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError, "direct candidateId"
        ):
            self._render(root=Path(temporary), package=payload)

    def test_package_release_and_graph_identity_are_required(self) -> None:
        cases = (
            ("releaseInputClassification", None, "release input classification"),
            ("releaseInputClassification", "research_inputs", "commercial release inputs"),
            ("contractGraphDigest", None, "ContractGraph"),
            ("contractGraphDigest", "sha256:" + "8" * 64, "ContractGraph"),
        )
        for field, value, message in cases:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory(
            ) as temporary, self.assertRaisesRegex(ValueError, message):
                package = self._package()
                if value is None:
                    package.pop(field)
                else:
                    package[field] = value
                self._render(root=Path(temporary), package=package)

    def test_beta_device_matrix_must_bind_exact_candidate_and_source(self) -> None:
        devices = {
            "schema": "release-device-matrix-evidence",
            "environment": "beta",
            "target": "beta-local",
            "status": "passed",
            "candidateId": self.candidate_id,
            "sourceGitSha": self.source_git_sha,
            "sourceTreeDigest": self.source_tree_digest,
            "platforms": {
                "android": {"android.json": "sha256:" + "1" * 64},
                "ios": {"ios.json": "sha256:" + "2" * 64},
            },
            "endedAt": "2026-07-28T00:00:20Z",
        }
        with tempfile.TemporaryDirectory() as temporary:
            receipt = self._render(
                root=Path(temporary), environment="beta", extra={"devices": devices}
            )
        self.assertEqual(receipt["environment"], "beta")

        devices["candidateId"] = "sha256:" + "e" * 64
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError, "devices evidence candidateId mismatch"
        ):
            self._render(
                root=Path(temporary), environment="beta", extra={"devices": devices}
            )

    def test_failed_health_evidence_is_never_promoted(self) -> None:
        health = {
            "command": "health",
            "target": "alpha-local",
            "checks": [{"ok": False}],
            "findings": ["down"],
            "endedAt": "2026-07-28T00:00:10Z",
        }
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError, "health evidence is not passed"
        ):
            self._render(root=Path(temporary), extra={"health": health})

    def test_source_built_or_destructively_repaired_runtime_is_never_promoted(self) -> None:
        up = self._runtime_up("alpha")
        up["formalRelease"] = False
        up["runtimeMode"] = "source-build"
        up["destructiveRepairPerformed"] = True
        up["destructiveActions"] = ["wipe-postgres-migration-drift"]
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError, "immutable candidate runtime"
        ):
            self._render(root=Path(temporary), extra={"up": up})

    def test_formal_runtime_rejects_research_or_mixed_release_inputs(self) -> None:
        for classification in ("research_inputs", "mixed_inputs"):
            up = self._runtime_up("alpha")
            up["releaseInputClassification"] = classification
            with self.subTest(classification=classification), tempfile.TemporaryDirectory(
            ) as temporary, self.assertRaisesRegex(
                ValueError,
                "commercial release inputs",
            ):
                self._render(root=Path(temporary), extra={"up": up})

    def test_formal_runtime_rejects_contract_graph_drift(self) -> None:
        up = self._runtime_up("alpha")
        up["contractGraphDigest"] = "sha256:" + "8" * 64
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError,
            "ContractGraph",
        ):
            self._render(root=Path(temporary), extra={"up": up})

    def test_package_evidence_is_mandatory(self) -> None:
        up = {
            "command": "up",
            "target": "alpha-local",
            "steps": [{"exitCode": 0}],
            "endedAt": "2026-07-28T00:00:10Z",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "up.json"
            path.write_text(json.dumps(up), encoding="utf-8")
            with patch(
                "quwoquan_ops.ci.render_environment_release_receipt.validate_manifest"
            ), self.assertRaisesRegex(ValueError, "environment evidence is missing"):
                render(
                    manifest=self._manifest(),
                    environment="alpha",
                    evidence={"up": (path, up)},
                    required_evidence=["up"],
                    archive_prefix="evidence/raw/environments/alpha/raw",
                )

    def test_exact_byte_archiver_stages_raw_and_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_bytes(b'{"exact":"bytes"}\n')
            descriptors = archive_exact_files(
                archive_root=root / "artifact",
                files={"green-matrix": (source, RELEASE_CLOSURE_PATHS["green-matrix"])},
            )
            archived = root / "artifact" / RELEASE_CLOSURE_PATHS["green-matrix"]
            self.assertEqual(archived.read_bytes(), source.read_bytes())
            self.assertEqual(
                descriptors["green-matrix"]["digest"],
                "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            with self.assertRaisesRegex(ValueError, "path is unsafe"):
                archive_exact_files(
                    archive_root=root / "artifact",
                    files={"escape": (source, "../escape.json")},
                )

    def test_environment_archiver_requires_manifest_bound_release_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            staging = root / "staging"
            canonical = artifact / RELEASE_CLOSURE_PATHS["pilot-release"]
            canonical.parent.mkdir(parents=True)
            canonical.write_bytes(b'{"release":"canonical"}\n')
            raw = root / "raw-package.json"
            raw.write_bytes(b'{"package":"exact"}\n')
            descriptors = {
                "pilot-release": {
                    "path": RELEASE_CLOSURE_PATHS["pilot-release"],
                    "digest": "sha256:"
                    + hashlib.sha256(canonical.read_bytes()).hexdigest(),
                },
                "package": {
                    "path": "evidence/raw/environments/alpha/raw/package.json",
                    "digest": "sha256:"
                    + hashlib.sha256(raw.read_bytes()).hexdigest(),
                },
            }
            archive_environment_evidence(
                artifact_root=artifact,
                staging_root=staging,
                environment="alpha",
                evidence_paths={"pilot-release": canonical, "package": raw},
                descriptors=descriptors,
            )
            self.assertEqual(
                (staging / "raw/package.json").read_bytes(),
                raw.read_bytes(),
            )
            wrong = root / "wrong-release.json"
            wrong.write_bytes(canonical.read_bytes())
            with self.assertRaisesRegex(ValueError, "manifest-bound exact file"):
                archive_environment_evidence(
                    artifact_root=artifact,
                    staging_root=staging,
                    environment="alpha",
                    evidence_paths={"pilot-release": wrong},
                    descriptors={"pilot-release": descriptors["pilot-release"]},
                )

    def test_full_release_closure_rejects_wrong_green_matrix_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            common = self._release_closure("alpha")
            candidate_path = root / "candidate.json"
            rollback_path = root / "rollback.json"
            candidate_path.write_text(
                json.dumps(common["pilot-release"]), encoding="utf-8"
            )
            rollback_path.write_text(
                json.dumps(common["pilot-rollback"]), encoding="utf-8"
            )
            lifecycle_paths: dict[str, Path] = {}
            environments: dict[str, dict] = {}
            for environment in ("alpha", "beta", "gamma"):
                lifecycle = self._release_closure(environment)[
                    "content-lifecycle"
                ]
                lifecycle_path = root / f"lifecycle-{environment}.json"
                lifecycle_path.write_text(
                    json.dumps(lifecycle), encoding="utf-8"
                )
                lifecycle_paths[environment] = lifecycle_path
                target = f"{environment}-local"
                environments[target] = {
                    "environment": environment,
                    "target": target,
                    "release": {
                        "releaseId": "pilot-003",
                        "releaseDigest": "sha256:" + "6" * 64,
                    },
                    "rollbackRelease": {
                        "releaseId": "pilot-002",
                        "releaseDigest": "sha256:" + "7" * 64,
                    },
                }
            matrix = {
                "schema": "quwoquan.test.case-result",
                "caseId": "stackctl.local-env-gate.alpha-beta-gamma",
                "status": "passed",
                "claim": "ALPHA_BETA_GAMMA_LOCAL_GREEN",
                "executionClass": "live",
                "targets": ["alpha-local", "beta-local", "gamma-local"],
                "executed": 3,
                "skipped": 0,
                "failureCategory": "",
                "baselineId": "sha256:" + "8" * 64,
                "releaseId": "pilot-003",
                "releaseDigest": "sha256:" + "6" * 64,
                "generatedAt": "2026-07-28T00:00:16Z",
                "phases": [{"name": "all", "status": "passed"}],
                "environments": environments,
            }
            matrix_path = root / "matrix.json"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
            payloads = validate_release_closure_sources(
                pilot_release_attestation=candidate_path,
                pilot_rollback_attestation=rollback_path,
                lifecycle_exits=lifecycle_paths,
                green_matrix=matrix_path,
            )
            self.assertEqual(set(payloads), set(RELEASE_CLOSURE_PATHS))
            matrix["claim"] = (
                "ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN"
            )
            matrix["deviceProfile"] = "emulator_only"
            matrix["nonPromotable"] = True
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "not the live pilot release result"
            ):
                validate_release_closure_sources(
                    pilot_release_attestation=candidate_path,
                    pilot_rollback_attestation=rollback_path,
                    lifecycle_exits=lifecycle_paths,
                    green_matrix=matrix_path,
                )
            matrix["claim"] = "ALPHA_BETA_GAMMA_LOCAL_GREEN"
            matrix.pop("deviceProfile")
            matrix.pop("nonPromotable")
            matrix["environments"]["beta-local"]["environment"] = "gamma"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "beta release binding mismatch"
            ):
                validate_release_closure_sources(
                    pilot_release_attestation=candidate_path,
                    pilot_rollback_attestation=rollback_path,
                    lifecycle_exits=lifecycle_paths,
                    green_matrix=matrix_path,
                )

    def test_prod_dry_run_cannot_generate_a_passed_receipt(self) -> None:
        dry_run = {
            "command": "deploy",
            "target": "prod-hosted",
            "exitCode": 0,
            "dryRun": True,
            "rolloutDecision": "continue",
            "releaseReceiptId": "",
            "releaseReceiptRef": "",
            "releaseState": {},
            "postDeployFailures": [],
            "rollback": {"triggered": False},
            "endedAt": "2026-07-28T00:00:20Z",
        }
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(
            ValueError, "full evidence is not passed"
        ):
            self._render(
                root=Path(temporary), environment="prod", extra={"full": dry_run}
            )


if __name__ == "__main__":
    unittest.main()

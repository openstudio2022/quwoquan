# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.ci.render_environment_release_receipt import render


class EnvironmentReleaseReceiptTest(unittest.TestCase):
    candidate_id = "sha256:" + "c" * 64
    source_git_sha = "a" * 40
    source_tree_digest = "sha1:" + "b" * 40
    image_digest = "sha256:" + "e" * 64
    image_ref = "ghcr.io/owner/repo/gateway@" + image_digest

    def _manifest(self, *, status: str = "candidate-ready") -> dict:
        return {
            "status": status,
            "candidateId": self.candidate_id,
            "artifactDigest": "sha256:" + "d" * 64,
            "source": {
                "gitSha": self.source_git_sha,
                "treeDigest": self.source_tree_digest,
                "repository": "owner/repo",
            },
            "images": {
                "gateway": {
                    "ref": self.image_ref,
                    "digest": self.image_digest,
                }
            },
        }

    def _runtime_up(self, environment: str) -> dict:
        return {
            "command": "up",
            "target": f"{environment}-local",
            "steps": [{"name": "compose", "exitCode": 0}],
            "formalRelease": True,
            "runtimeMode": "immutable-oci",
            "runtimeCandidateDigest": self.candidate_id,
            "runtimeImages": {
                "gateway": {
                    "ref": self.image_ref,
                    "digest": self.image_digest,
                }
            },
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
            self._preprod_evidence(environment)
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
        self.assertEqual(receipt["verifiedAt"], "2026-07-28T00:00:13Z")

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

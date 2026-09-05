from __future__ import annotations

import unittest
from unittest.mock import patch

from quwoquan_ops.ci.render_provider_conformance_source import (
    expected_required_cell_count_from_readiness,
    render as render_source,
)
from quwoquan_ops.ci.render_provider_release_evidence import render

ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")


def _environment_artifacts() -> dict:
    """Bind one environment-owned service image per environment.

    Provider readiness evidence is per environment, so the component material it
    quotes must be too: a single shared image digest would let one environment's
    readiness stand in for another's.
    """

    return {
        environment: {
            "environment": environment,
            "environmentArtifactDigest": f"sha256:{index:064x}",
            "images": {"service": {"digest": f"sha256:{index + 16:064x}"}},
        }
        for index, environment in enumerate(ENVIRONMENTS, start=1)
    }


class ProviderReleaseEvidenceTest(unittest.TestCase):
    def _source_evidence(self, evidence_count: int) -> dict:
        return {
            "ref": "oci://ghcr.io/owner/repo/provider-evidence@sha256:" + "e" * 64,
            "digest": "sha256:" + "e" * 64,
            "files": {
                f"evidence/raw/provider/env/prod/runs/run-{index}/provider-conformance.evidence.json": (
                    "sha256:" + f"{index + 1:064x}"
                )
                for index in range(evidence_count)
            },
        }

    def _capability(self, *, required: bool, ready: bool, prod: bool) -> dict:
        payload = {
            "state": "enabled",
            "required": required,
            "adapter_id": "ext.provider.canonical",
            "local_substitute": not prod,
            "adapter_preflight_ready": ready,
            "adapter_ready": ready,
            "evidence_ready": ready,
            "matrix_selected_adapters_ready": ready,
            "capability_ready": ready,
        }
        if prod:
            payload["prod_remote_release_ready"] = ready
        return payload

    def _readiness(self, capability_count: int = 2) -> dict[str, dict]:
        capability_ids = [
            f"fixture.capability.{index:02d}" for index in range(capability_count)
        ]
        return {
            environment: {
                capability_id: self._capability(
                    required=True,
                    ready=True,
                    prod=environment == "prod",
                )
                for capability_id in capability_ids
            }
            for environment in ("alpha", "beta", "gamma", "prod")
        }

    def _manifest(self) -> dict:
        return {
            "releaseCompositionId": None,
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + "b" * 40,
                "repository": "owner/repo",
                "workflowRunId": "123",
            },
            "environmentArtifacts": _environment_artifacts(),
        }

    def test_readiness_derived_size_fixture_passes(self) -> None:
        readiness = self._readiness()
        evidence_count = expected_required_cell_count_from_readiness(readiness)
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": evidence_count,
            "sourceEvidence": self._source_evidence(evidence_count),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": readiness,
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ):
            payload = render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["evidenceCount"], evidence_count)

    def test_cell_count_tracks_an_arbitrary_capability_set(self) -> None:
        readiness = self._readiness(capability_count=2)
        evidence_count = expected_required_cell_count_from_readiness(readiness)
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": evidence_count,
            "sourceEvidence": self._source_evidence(evidence_count),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": readiness,
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ):
            payload = render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )
        self.assertEqual(payload["evidenceCount"], evidence_count)

        conformance["evidenceCount"] = evidence_count + 1
        conformance["sourceEvidence"] = self._source_evidence(evidence_count + 1)
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ), self.assertRaisesRegex(ValueError, "readiness-derived required cell count"):
            render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )

    def test_capability_set_drift_across_environments_blocks(self) -> None:
        readiness = self._readiness(capability_count=2)
        readiness["beta"].pop("fixture.capability.01")
        with self.assertRaisesRegex(
            ValueError,
            "capability set differs across environments",
        ):
            expected_required_cell_count_from_readiness(readiness)

    def test_required_unready_capability_blocks(self) -> None:
        readiness = self._readiness()
        evidence_count = expected_required_cell_count_from_readiness(readiness)
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": evidence_count,
            "sourceEvidence": self._source_evidence(evidence_count),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": readiness,
        }
        conformance["readiness"]["prod"]["fixture.capability.00"][
            "capability_ready"
        ] = False
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ), self.assertRaisesRegex(ValueError, "required ready"):
            render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )

    def test_old_or_versioned_provider_source_is_rejected(self) -> None:
        conformance = {
            "schema": "provider-conformance-readiness",
            "version": 1,
            "evidenceCount": 1,
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": {"prod": {}},
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ), self.assertRaisesRegex(ValueError, "fields are not canonical"):
            render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )

    def test_source_projection_drops_repository_report_identity(self) -> None:
        readiness = self._readiness()
        evidence_count = expected_required_cell_count_from_readiness(readiness)
        report = {
            "schema": "provider-conformance-readiness",
            "evidenceCount": evidence_count,
            "executableSourceCount": 4,
            "sourceCoverageIssues": [],
            "readiness": readiness,
            "issues": [],
        }
        with patch(
            "quwoquan_ops.ci.render_provider_conformance_source.readiness_issues",
            return_value=[],
        ):
            payload = render_source(
                report,
                validation_issues=[],
                environment="prod",
                source_evidence=self._source_evidence(evidence_count),
            )
        self.assertEqual(payload["schema"], "provider-conformance-source")
        self.assertNotIn("version", payload)
        self.assertNotIn("executableSourceCount", payload)


class ProviderReleaseEvidenceProducerTest(unittest.TestCase):
    def _released_manifest(self, *, candidate_id: object = None) -> dict:
        return {
            "releaseCompositionId": candidate_id or "sha256:" + "d" * 64,
            "artifactDigest": "sha256:" + "f" * 64,
            "status": "released",
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + "b" * 40,
                "repository": "owner/repo",
                "workflowRunId": "123",
            },
            "environmentArtifacts": _environment_artifacts(),
        }

    def test_workflow_delegates_exact_cell_ownership_to_canonical_python(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[4]
        workflow = (
            root / ".github/workflows/provider-release-evidence.yml"
        ).read_text(encoding="utf-8")
        producer = (
            root / "quwoquan_ops/ci/provider_release_evidence.py"
        ).read_text(encoding="utf-8")
        self.assertIn("git status --porcelain --untracked-files=all", workflow)
        self.assertIn("QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT", workflow)
        self.assertIn("secrets.QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY", workflow)
        self.assertIn("consume_released_release_evidence.py", workflow)
        self.assertIn("vars.RELEASED_RELEASE_EVIDENCE_REF", workflow)
        self.assertIn("execute-nonprod", workflow)
        self.assertIn("--environment-matrix", producer)
        self.assertIn(
            "Execute all compiled required nonprod Provider cells",
            workflow,
        )
        self.assertIn(
            "provider_conformance.expected_required_cell_keys(compiled)",
            producer,
        )
        self.assertIn("exact_required_cell_issues", producer)
        for fixed_count_token in (
            "126 nonprod",
            "140-cell",
            '!= "140"',
            "exactly 140",
        ):
            self.assertNotIn(fixed_count_token, workflow)
        self.assertIn("QWQ_OUTPUT_ROOT=$RUNNER_TEMP/", workflow)
        self.assertNotIn("local-sha256", workflow)
        self.assertNotIn("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY: local", workflow)

    def test_identity_requires_released_candidate_and_writes_derived_outputs(
        self,
    ) -> None:
        import argparse
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from quwoquan_ops.ci import provider_release_evidence as producer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            github_output = root / "github_output"
            missing_candidate = self._released_manifest(candidate_id="")
            missing_candidate["releaseCompositionId"] = None
            manifest_path.write_text(json.dumps(missing_candidate), encoding="utf-8")
            with patch.object(
                producer,
                "validate_manifest",
                side_effect=lambda payload, allowed_statuses=None: None,
            ), patch.object(
                producer.subprocess,
                "run",
                return_value=type(
                    "Completed",
                    (),
                    {"stdout": "a" * 40 + "\n"},
                )(),
            ), self.assertRaisesRegex(
                ValueError,
                "released releaseCompositionId",
            ):
                producer._release_identity(
                    manifest_path,
                    "ghcr.io/owner/repo/release-artifact@sha256:" + "e" * 64,
                )

            released_manifest = self._released_manifest()
            manifest_path.write_text(json.dumps(released_manifest), encoding="utf-8")
            github_output.write_text("", encoding="utf-8")
            with patch.object(
                producer,
                "validate_manifest",
                side_effect=lambda payload, allowed_statuses=None: None,
            ), patch.object(
                producer.subprocess,
                "run",
                return_value=type(
                    "Completed",
                    (),
                    {"stdout": "a" * 40 + "\n"},
                )(),
            ):
                code = producer.command_identity(
                    argparse.Namespace(
                        release_manifest=manifest_path,
                        release_evidence_ref=(
                            "ghcr.io/owner/repo/release-artifact@sha256:" + "e" * 64
                        ),
                        github_output=str(github_output),
                    )
                )
            self.assertEqual(code, 0)
            output = github_output.read_text(encoding="utf-8")
            self.assertIn("expectedImageDigest=sha256:", output)
            self.assertIn(
                "releaseEvidenceRef=ghcr.io/owner/repo/release-artifact@sha256:",
                output,
            )
            self.assertIn("releaseCompositionId=sha256:", output)
            self.assertIn("artifactDigest=sha256:", output)

    def test_execute_prod_invokes_stackctl_for_enabled_bindings_only(self) -> None:
        import argparse
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from quwoquan_ops.ci import provider_release_evidence as producer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            report_dir = root / "reports"
            manifest_path.write_text(
                json.dumps(self._released_manifest()),
                encoding="utf-8",
            )
            commands: list[list[str]] = []

            def _run(command, cwd=None, env=None, check=None, **_kwargs):
                if command[:2] == ["git", "rev-parse"]:
                    return type("Completed", (), {"stdout": "a" * 40 + "\n"})()
                commands.append(list(command))
                return type("Completed", (), {"stdout": ""})()

            with patch.object(
                producer,
                "validate_manifest",
                side_effect=lambda payload, allowed_statuses=None: None,
            ), patch.object(
                producer.governance,
                "load_and_compile",
                return_value=(
                    {
                        "selectedBindings": {
                            "prod": {
                                **{
                                    f"required.capability.{index:02d}": {
                                        "state": "enabled",
                                        "adapter_id": f"ext.provider.canonical.{index:02d}",
                                        "adapter_kind": "external",
                                    }
                                    for index in range(2)
                                },
                                "blocked.capability": {
                                    "state": "blocked",
                                    "adapter_id": "ext.provider.blocked",
                                },
                            }
                        },
                        "providerConformanceCapabilityIds": [
                            f"required.capability.{index:02d}" for index in range(2)
                        ],
                    },
                    [],
                ),
            ), patch.object(
                producer.governance,
                "requires_provider_conformance",
                side_effect=lambda binding: binding.get("state") == "enabled",
            ), patch.object(producer.subprocess, "run", side_effect=_run):
                code = producer.command_execute_prod(
                    argparse.Namespace(
                        release_manifest=manifest_path,
                        release_evidence_ref=(
                            "ghcr.io/owner/repo/release-artifact@sha256:" + "e" * 64
                        ),
                        report_dir=report_dir,
                    )
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(commands), 2)
            command = commands[0]
            self.assertEqual(command[1:4], [
                "quwoquan_ops/cli/stackctl.py",
                "provider-conformance",
                "--adapter-id",
            ])
            self.assertIn("ext.provider.canonical.00", command)
            self.assertIn("--env", command)
            self.assertIn("prod", command)
            self.assertIn("--execute", command)
            self.assertIn("--layer", command)
            self.assertIn("user_acceptance", command)

    def test_execute_nonprod_invokes_three_deterministic_environment_matrices(
        self,
    ) -> None:
        import argparse
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from quwoquan_ops.ci import provider_release_evidence as producer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(self._released_manifest()),
                encoding="utf-8",
            )
            commands: list[list[str]] = []

            def _run(command, cwd=None, env=None, check=None, **_kwargs):
                if command[:2] == ["git", "rev-parse"]:
                    return type("Completed", (), {"stdout": "a" * 40 + "\n"})()
                commands.append(list(command))
                return type("Completed", (), {"stdout": ""})()

            capability_ids = [
                f"required.capability.{index:02d}" for index in range(2)
            ]
            with patch.object(
                producer,
                "validate_manifest",
                side_effect=lambda payload, allowed_statuses=None: None,
            ), patch.object(
                producer.governance,
                "load_and_compile",
                return_value=(
                    {"providerConformanceCapabilityIds": capability_ids},
                    [],
                ),
            ), patch.object(producer.subprocess, "run", side_effect=_run):
                code = producer.command_execute_nonprod(
                    argparse.Namespace(
                        release_manifest=manifest_path,
                        release_evidence_ref=(
                            "ghcr.io/owner/repo/release-artifact@sha256:" + "e" * 64
                        ),
                        report_dir=root / "reports",
                    )
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(commands), 3)
            self.assertEqual(
                [command[command.index("--env") + 1] for command in commands],
                ["alpha", "beta", "gamma"],
            )
            self.assertTrue(
                all("--environment-matrix" in command for command in commands)
            )

    def test_package_gate_blocks_when_executed_evidence_is_empty(self) -> None:
        import argparse
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from quwoquan_ops.ci import provider_release_evidence as producer

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            output_dir = root / "oci"
            manifest_path.write_text(
                json.dumps(self._released_manifest()),
                encoding="utf-8",
            )
            with patch.object(
                producer,
                "validate_manifest",
                side_effect=lambda payload, allowed_statuses=None: None,
            ), patch.object(
                producer.subprocess,
                "run",
                return_value=type(
                    "Completed",
                    (),
                    {"stdout": "a" * 40 + "\n"},
                )(),
            ), patch.object(
                producer,
                "output_root",
                return_value=root,
            ), patch.object(
                producer.governance,
                "load_and_compile",
                return_value=({}, []),
            ), patch.object(
                producer.provider_conformance,
                "load_validate_and_derive",
                return_value=({"schema": "provider-conformance-readiness"}, []),
            ), patch.object(
                producer.provider_conformance,
                "readiness_issues",
                return_value=[],
            ), patch.object(
                producer.provider_conformance,
                "load_evidence",
                return_value=([], []),
            ), patch.object(
                producer.provider_conformance,
                "exact_required_cell_issues",
                return_value=[],
            ), self.assertRaisesRegex(ValueError, "defines no capabilities"):
                producer.command_package(
                    argparse.Namespace(
                        release_manifest=manifest_path,
                        release_evidence_ref=(
                            "ghcr.io/owner/repo/release-artifact@sha256:" + "e" * 64
                        ),
                        release_root=root,
                        output_dir=output_dir,
                        github_output="",
                    )
                )

    def test_package_uses_only_manifest_bound_release_closure(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[4]
        producer = (
            root / "quwoquan_ops/ci/provider_release_evidence.py"
        ).read_text(encoding="utf-8")
        self.assertIn("RELEASE_CLOSURE_PATHS", producer)
        self.assertIn("released manifest closure digest mismatch", producer)
        self.assertIn("sha256_file(source_path)", producer)
        self.assertNotIn("_matrix_lifecycle_sources", producer)


if __name__ == "__main__":
    unittest.main()

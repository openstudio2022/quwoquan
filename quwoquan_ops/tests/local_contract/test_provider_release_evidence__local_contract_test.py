from __future__ import annotations

import unittest
from unittest.mock import patch

from quwoquan_ops.ci.render_provider_conformance_source import render as render_source
from quwoquan_ops.ci.render_provider_release_evidence import render


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

    def _readiness(self, prod: dict[str, dict]) -> dict[str, dict]:
        return {
            environment: {
                "fixture.capability": self._capability(
                    required=True,
                    ready=True,
                    prod=False,
                )
            }
            for environment in ("alpha", "beta", "gamma")
        } | {"prod": prod}

    def _manifest(self) -> dict:
        return {
            "candidateId": None,
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + "b" * 40,
                "repository": "owner/repo",
                "workflowRunId": "123",
            },
            "images": {
                "service": {"digest": "sha256:" + "c" * 64},
            },
        }

    def test_optional_unready_capability_does_not_block_required_ready(self) -> None:
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": 2,
            "sourceEvidence": self._source_evidence(2),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": self._readiness(
                {
                    "required.capability": {
                        **self._capability(required=True, ready=True, prod=True),
                    },
                    "optional.capability": {
                        **self._capability(required=False, ready=False, prod=True),
                    },
                }
            ),
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
        self.assertEqual(payload["evidenceCount"], 2)

    def test_required_unready_capability_blocks(self) -> None:
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": 1,
            "sourceEvidence": self._source_evidence(1),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": self._readiness(
                {
                    "required.capability": {
                        **self._capability(required=True, ready=False, prod=True),
                    }
                }
            ),
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ), self.assertRaisesRegex(ValueError, "not ready"):
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
        report = {
            "schema": "provider-conformance-readiness",
            "evidenceCount": 1,
            "executableSourceCount": 4,
            "sourceCoverageIssues": [],
            "readiness": self._readiness(
                {
                    "required.capability": self._capability(
                        required=True,
                        ready=True,
                        prod=True,
                    )
                }
            ),
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
                source_evidence=self._source_evidence(1),
            )
        self.assertEqual(payload["schema"], "provider-conformance-source")
        self.assertNotIn("version", payload)
        self.assertNotIn("executableSourceCount", payload)


class ProviderReleaseEvidenceProducerTest(unittest.TestCase):
    def _component_manifest(self, *, candidate_id: object = None) -> dict:
        return {
            "candidateId": candidate_id,
            "status": "component-ready",
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + "b" * 40,
                "repository": "owner/repo",
                "workflowRunId": "123",
            },
            "images": {
                "service": {"digest": "sha256:" + "c" * 64},
            },
        }

    def test_identity_rejects_sealed_candidate_and_writes_binding_outputs(
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
            sealed = self._component_manifest(candidate_id="sha256:" + "d" * 64)
            manifest_path.write_text(json.dumps(sealed), encoding="utf-8")
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
                with self.assertRaisesRegex(
                    ValueError,
                    "Provider qualification must precede candidate sealing",
                ):
                    producer._component_identity(
                        manifest_path,
                        "ghcr.io/owner/repo/component@sha256:" + "e" * 64,
                    )

            open_manifest = self._component_manifest()
            manifest_path.write_text(json.dumps(open_manifest), encoding="utf-8")
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
                        component_manifest=manifest_path,
                        component_evidence_ref=(
                            "ghcr.io/owner/repo/component@sha256:" + "e" * 64
                        ),
                        github_output=str(github_output),
                    )
                )
            self.assertEqual(code, 0)
            output = github_output.read_text(encoding="utf-8")
            self.assertIn("expectedImageDigest=sha256:", output)
            self.assertIn(
                "componentEvidenceRef=ghcr.io/owner/repo/component@sha256:",
                output,
            )

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
                json.dumps(self._component_manifest()),
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
                                "required.capability": {
                                    "state": "enabled",
                                    "adapter_id": "ext.provider.canonical",
                                },
                                "blocked.capability": {
                                    "state": "blocked",
                                    "adapter_id": "ext.provider.blocked",
                                },
                            }
                        }
                    },
                    [],
                ),
            ), patch.object(producer.subprocess, "run", side_effect=_run):
                code = producer.command_execute_prod(
                    argparse.Namespace(
                        component_manifest=manifest_path,
                        component_evidence_ref=(
                            "ghcr.io/owner/repo/component@sha256:" + "e" * 64
                        ),
                        report_dir=report_dir,
                    )
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(commands), 1)
            command = commands[0]
            self.assertEqual(command[1:4], [
                "quwoquan_ops/cli/stackctl.py",
                "provider-conformance",
                "--adapter-id",
            ])
            self.assertIn("ext.provider.canonical", command)
            self.assertIn("--env", command)
            self.assertIn("prod", command)
            self.assertIn("--execute", command)
            self.assertIn("--layer", command)
            self.assertIn("user_acceptance", command)

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
                json.dumps(self._component_manifest()),
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
                producer.provider_conformance,
                "load_validate_and_derive",
                return_value=({"schema": "provider-conformance-readiness"}, []),
            ), patch.object(
                producer.provider_conformance,
                "readiness_issues",
                return_value=[],
            ), patch.object(
                producer.provider_conformance,
                "evidence_files",
                return_value=[],
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "executed Provider evidence set is empty",
                ):
                    producer.command_package(
                        argparse.Namespace(
                            component_manifest=manifest_path,
                            component_evidence_ref=(
                                "ghcr.io/owner/repo/component@sha256:" + "e" * 64
                            ),
                            output_dir=output_dir,
                            github_output="",
                        )
                    )


if __name__ == "__main__":
    unittest.main()

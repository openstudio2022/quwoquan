# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#req-001
# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#req-003
from __future__ import annotations

import os
import re
import subprocess
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.gate import verify_github_supply_chain


ROOT = Path(__file__).resolve().parents[4]
SERVICE_FACTORY = ROOT / ".github" / "workflows" / "service_pipeline.yml"
QUALIFICATION_FACTORY = ROOT / ".github" / "workflows" / "release-qualification.yml"
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
SERVICE_CONSUMER_OUTPUTS = {
    "component_evidence_ref",
    "component_artifact_digest",
    "source_git_sha",
    "source_tree_digest",
    "qualification_request_ref",
    "qualification_request_digest",
    "service_material_digest",
}


def _workflow(path: Path) -> dict:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(payload, dict)
    return payload


class ServiceSupplyChainProvenanceContractTest(unittest.TestCase):
    def test_github_actions_are_pinned_and_critical_paths_are_owned(self) -> None:
        result = subprocess.run(
            ["python3", "quwoquan_ops/gate/verify_github_supply_chain.py"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_factory_matches_exact_qualification_consumer_contract(
        self,
    ) -> None:
        text = SERVICE_FACTORY.read_text(encoding="utf-8")
        workflow = _workflow(SERVICE_FACTORY)
        call = workflow["on"]["workflow_call"]

        self.assertEqual(
            set(call["inputs"]),
            {
                "source_sha",
                "rc_tag_admission_ref",
                "qualification_request_ref",
                "qualification_request_digest",
                "artifact_build_number",
                "artifact_build_number_allocation_ref",
                "artifact_build_number_allocation_digest",
            },
        )
        self.assertTrue(
            all(value["required"] == "true" for value in call["inputs"].values())
        )
        self.assertEqual(set(call["outputs"]), SERVICE_CONSUMER_OUTPUTS)

        qualification = QUALIFICATION_FACTORY.read_text(encoding="utf-8")
        consumed = set(
            re.findall(r"needs\.service_factory\.outputs\.([a-z_]+)", qualification)
        )
        self.assertEqual(consumed, SERVICE_CONSUMER_OUTPUTS)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotIn("${{ inputs.source_sha ||", text)
        self.assertNotIn("${{ github.sha }}", text)
        self.assertNotIn("base_sha", call["inputs"])

    def test_service_factory_publishes_only_canonical_bound_material(self) -> None:
        text = SERVICE_FACTORY.read_text(encoding="utf-8")

        for retired in (
            "ReleaseEvidenceManifest",
            '"schema": "release-evidence-manifest"',
            '"schema": "quwoquan_ops.service_component_manifest"',
            "generate_mainline_release_artifact.py",
            "collect_mainline_image_descriptors.py",
            "finalize_mainline_release_artifact.py",
            "fetch_mainline_release_artifact.py",
            "--previous-manifest",
            "imagetools create",
        ):
            self.assertNotIn(retired, text)

        for required in (
            '"schema": "quwoquan_ops.service_factory_material"',
            '"sourceGitSha": source',
            '"sourceTree": tree',
            '"qualificationRequest": {',
            '"requestId": os.environ["QUALIFICATION_REQUEST_ID"]',
            '"rcTagAdmission": {',
            '"admissionId": os.environ["RC_TAG_ADMISSION_ID"]',
            '"serviceDigest": service_digest',
            '"signature": {',
            '"issuer": OIDC_ISSUER',
            '"signerWorkflow": signer_workflow',
            '"attestations": {',
            '"predicateType": PREDICATES[name]',
            '"verificationDigest": signed_attestations[name]',
            '"buildPolicy": "build_sign_attest_once"',
            'material["materialDigest"] = canonical_digest(material)',
            '"prodRuntimeConfigDeploymentBundle": prod_bundle',
            '"schema": "quwoquan_ops.prod_runtime_config_deployment_bundle.v1"',
            '"algorithm": "sha256_sorted_tracked_path_bytes_v1"',
            '"artifactBuildNumberAllocation": {',
            '"--source-digest", source',
            'SUBJECT_NAME="${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/service-factory-material"',
            'REF="$SUBJECT_NAME@$DIGEST"',
        ):
            self.assertIn(required, text)

        self.assertIn("promotion_evidence.py materialize-oci", text)
        self.assertIn("materialize_evidence_oci.py", text)
        self.assertIn("Read back exact published service factory material", text)
        self.assertIn("published service factory material drifted", text)
        self.assertIn("cmp ", text)
        self.assertIn("request_id != canonical_digest(request_body)", text)
        self.assertIn("admission_id != canonical_digest(admission_body)", text)
        self.assertIn('admission.get("peeledCommit") != source', text)
        self.assertIn('admission.get("sourceTree") != source_tree', text)
        self.assertIn("Reject image reuse in RC factory", text)
        self.assertIn("canonical service image order/set drifted", text)
        self.assertNotIn(":latest", text)

    def test_embedded_python_is_syntactically_valid(self) -> None:
        text = SERVICE_FACTORY.read_text(encoding="utf-8")
        blocks = re.findall(
            r"<<'(?P<marker>PY_[A-Z]+)'[^\n]*\n(?P<body>.*?)(?:^\s*)(?P=marker)$",
            text,
            re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(blocks), 4)
        for marker, body in blocks:
            with self.subTest(marker=marker):
                compile(
                    textwrap.dedent(body),
                    f"service_pipeline.yml:{marker}",
                    "exec",
                )

    def test_service_factory_permissions_actions_and_shell_are_bounded(self) -> None:
        text = SERVICE_FACTORY.read_text(encoding="utf-8")
        workflow = _workflow(SERVICE_FACTORY)
        jobs = workflow["jobs"]

        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(
            jobs["prepare-release"]["permissions"],
            {"contents": "read", "packages": "read"},
        )
        self.assertEqual(
            jobs["build-release-images"]["permissions"],
            {
                "contents": "read",
                "id-token": "write",
                "attestations": "write",
                "packages": "write",
            },
        )
        self.assertEqual(
            jobs["validate-deploy"]["permissions"],
            {"contents": "read", "packages": "write"},
        )
        self.assertEqual(
            jobs["service_pipeline_summary"]["permissions"],
            {"contents": "read", "actions": "read"},
        )

        action_refs = re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", text, re.MULTILINE)
        self.assertTrue(action_refs)
        self.assertTrue(all(PINNED_ACTION.fullmatch(ref) for ref in action_refs))
        self.assertIn(
            "docker.io/tonistiigi/binfmt@sha256:"
            "b4c6a09270133b3c5b4dff94f83067df4dd27eced195fc6a1dbad102999e24dd",
            text,
        )
        self.assertIn("set -euo pipefail", text)
        self.assertNotIn("shopt ", text)
        self.assertNotIn("readarray ", text)
        self.assertNotIn("mapfile ", text)

    def test_production_workflow_uses_real_arm64_runner_without_retired_label(
        self,
    ) -> None:
        workflow = ROOT / ".github" / "workflows" / "deploy-prod-auto.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("runs-on: [self-hosted, macOS, ARM64]", text)
        self.assertNotIn("prod-release", text)

    def test_retired_prod_runner_label_fails_closed(self) -> None:
        production = ROOT / ".github" / "workflows" / "deploy-prod-auto.yml"
        forged = production.read_text(encoding="utf-8").replace(
            "runs-on: [self-hosted, macOS, ARM64]",
            "runs-on: [self-hosted, macOS, prod-release]",
        )
        original_read_text = Path.read_text

        def read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path == production:
                return forged
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text):
            failures = (
                verify_github_supply_chain.verify_production_execution_isolation()
            )

        self.assertTrue(
            any("retired prod-release runner label" in failure for failure in failures),
            failures,
        )
        self.assertTrue(
            any(
                "missing production isolation control: "
                "runs-on: [self-hosted, macOS, ARM64]" in failure
                for failure in failures
            ),
            failures,
        )

if __name__ == "__main__":
    unittest.main()

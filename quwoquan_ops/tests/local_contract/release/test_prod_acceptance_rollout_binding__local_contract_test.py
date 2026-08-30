# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.commands import deploy_domain, deploy_release_inputs
from quwoquan_ops.cli.commands.deploy_release_state import _validate_release_transition
from quwoquan_ops.cli.lib import environment_acceptance_fact as acceptance
from quwoquan_ops.cli.prod import hosted_release_ledger


D = "sha256:" + "a" * 64
CANDIDATE = "sha256:" + "b" * 64
APPROVAL = "sha256:" + "c" * 64
ELIGIBILITY = "sha256:" + "d" * 64
GAMMA = "sha256:" + "e" * 64


class ProdAcceptanceRolloutBindingContractTest(unittest.TestCase):
    def test_parser_exposes_exact_acceptance_pair(self) -> None:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        stub = types.SimpleNamespace(
            TARGETS=("prod-hosted",), ENVIRONMENTS=("prod",)
        )
        with mock.patch.dict(sys.modules, {"quwoquan_ops.cli.stackctl": stub}):
            deploy_domain.register_parser(subparsers)
        args = parser.parse_args(
            [
                "deploy", "--target", "prod-hosted",
                "--environment-acceptance-ref", "prod/fact.json",
                "--environment-acceptance-sha256", D,
            ]
        )
        self.assertEqual(args.environment_acceptance_ref, "prod/fact.json")
        self.assertEqual(args.environment_acceptance_sha256, D)

    def test_prevalidate_rejects_formal_acceptance_and_dry_run_is_non_eligible(self) -> None:
        source = Path(deploy_domain.__file__).read_text(encoding="utf-8")
        self.assertIn('"environment_acceptance_ref"', source)
        self.assertIn('"environment_acceptance_sha256"', source)
        self.assertIn('"environment_acceptance_root"', source)
        rollout_source = Path(
            __file__
        ).parents[3] / "cli/commands/deploy_rollout.py"
        rollout_text = rollout_source.read_text(encoding="utf-8")
        self.assertIn('"non-eligible"', rollout_text)
        self.assertIn("if not dry_run_requested", rollout_text)

    def test_missing_fact_and_bundle_substitution_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "requires --environment-acceptance-ref"):
                deploy_release_inputs._load_prod_environment_acceptance(
                    "", expected_digest="", evidence_root=root,
                    release_id=CANDIDATE, release_digest=D, candidate_digest=CANDIDATE,
                )
            (root / "bundle.json").write_text(
                json.dumps({"schema": "workflow-success-bundle", "status": "passed"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "EnvironmentAcceptanceFact"):
                deploy_release_inputs._load_prod_environment_acceptance(
                    "bundle.json",
                    expected_digest=acceptance.exact_byte_digest(root / "bundle.json"),
                    evidence_root=root, release_id=CANDIDATE, release_digest=D,
                    candidate_digest=CANDIDATE,
                )

    def test_cross_candidate_or_release_and_predecessor_drift_block(self) -> None:
        fact = {
            "schema": acceptance.SCHEMA,
            "environment": "prod",
            "target": "prod-hosted",
            "factId": D,
            "releaseId": CANDIDATE,
            "releaseDigest": D,
            "predecessorAcceptance": {
                "environment": "gamma", "factId": GAMMA,
                "ref": "gamma/fact.json", "digest": GAMMA,
            },
            "prodReleaseFacts": {
                "engineeringEligibility": {"ref": "prod/eligible.json", "digest": ELIGIBILITY},
                "durableApproval": {"ref": "prod/approval.json", "digest": APPROVAL},
                "rolloutStages": [
                    {"stage": stage, "ref": f"prod/{stage}.json", "digest": D}
                    for stage in acceptance.PROD_ROLLOUT_STAGES
                ],
                "rollbackReadiness": {"ref": "prod/rollback.json", "digest": D},
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "prod").mkdir()
            (root / "prod/fact.json").write_text(json.dumps(fact), encoding="utf-8")
            digest = acceptance.exact_byte_digest(root / "prod/fact.json")
            with mock.patch.object(
                acceptance, "load_environment_acceptance_fact",
                return_value=(fact, digest),
            ):
                with self.assertRaisesRegex(RuntimeError, "candidate"):
                    deploy_release_inputs._load_prod_environment_acceptance(
                        "prod/fact.json", expected_digest=digest, evidence_root=root,
                        release_id=CANDIDATE, release_digest=D, candidate_digest="sha256:" + "f" * 64,
                    )
                wrong_release = dict(fact, releaseDigest="sha256:" + "f" * 64)
                with mock.patch.object(
                    acceptance, "load_environment_acceptance_fact",
                    return_value=(wrong_release, digest),
                ), self.assertRaisesRegex(RuntimeError, "releaseDigest"):
                    deploy_release_inputs._load_prod_environment_acceptance(
                        "prod/fact.json", expected_digest=digest, evidence_root=root,
                        release_id=CANDIDATE, release_digest=D, candidate_digest=CANDIDATE,
                    )
                no_gamma = dict(fact, predecessorAcceptance=None)
                with mock.patch.object(
                    acceptance, "load_environment_acceptance_fact",
                    return_value=(no_gamma, digest),
                ), self.assertRaisesRegex(RuntimeError, "Gamma predecessor"):
                    deploy_release_inputs._load_prod_environment_acceptance(
                        "prod/fact.json", expected_digest=digest, evidence_root=root,
                        release_id=CANDIDATE, release_digest=D, candidate_digest=CANDIDATE,
                    )

    def test_stage_jump_and_approval_drift_are_blocked(self) -> None:
        state = {
            "schema": "prod-release-ledger", "generation": "1",
            "stage": "canary", "decision": "continue",
            "from_candidate_digest": D, "to_candidate_digest": CANDIDATE,
            "environment_acceptance_digest": D,
            "engineering_eligibility_digest": ELIGIBILITY,
            "durable_approval_digest": APPROVAL,
        }
        stub = types.SimpleNamespace(
            _release_stage_from_state=lambda value: value["stage"]
        )
        with mock.patch.dict(sys.modules, {"quwoquan_ops.cli.stackctl": stub}):
            with self.assertRaisesRegex(RuntimeError, "cannot advance"):
                _validate_release_transition(
                    state, from_candidate_digest=D, to_candidate_digest=CANDIDATE,
                    stage="20", acceptance_digest=D,
                    engineering_eligibility_digest=ELIGIBILITY,
                    durable_approval_digest=APPROVAL,
                )
            with self.assertRaisesRegex(RuntimeError, "durable_approval_digest"):
                _validate_release_transition(
                    state, from_candidate_digest=D, to_candidate_digest=CANDIDATE,
                    stage="5", acceptance_digest=D,
                    engineering_eligibility_digest=ELIGIBILITY,
                    durable_approval_digest="sha256:" + "f" * 64,
                )

    def test_legal_canary_persists_acceptance_and_approval_identity(self) -> None:
        request = {
            "schema": hosted_release_ledger.REQUEST_SCHEMA, "service": "mainline",
            "fromCandidateDigest": D, "toCandidateDigest": CANDIDATE,
            "step": "0", "stage": "canary", "triggerStage": "canary",
            "fromReleaseEvidenceRef": f"ghcr.io/owner/release@{D}",
            "toReleaseEvidenceRef": f"ghcr.io/owner/release@{CANDIDATE}",
            "fromImageTransportTag": "old", "toImageTransportTag": "new",
            "decision": "continue", "rollbackOutcome": "not_triggered",
            "rollbackEvidence": {"triggered": False}, "artifactDigest": D,
            "environmentAcceptanceRef": "prod/fact.json",
            "environmentAcceptanceDigest": D, "environmentAcceptanceFactId": D,
            "gammaPredecessorFactId": GAMMA, "gammaPredecessorDigest": GAMMA,
            "engineeringEligibilityRef": "prod/eligible.json",
            "engineeringEligibilityDigest": ELIGIBILITY,
            "durableApprovalRef": "prod/approval.json",
            "durableApprovalDigest": APPROVAL,
            "imageDigest": D, "configDigest": D,
            "contractGraphDigest": D, "adapterDigest": D,
            "expectedGeneration": 0, "sloReadback": {}, "postChecks": [],
            "lastGoodCandidateDigest": D, "verifiedAt": "2026-08-29T08:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temporary:
            readback = hosted_release_ledger.commit(Path(temporary), request)
        self.assertEqual(readback["state"]["stage"], "canary")
        self.assertEqual(readback["receipt"]["environmentAcceptanceDigest"], D)
        self.assertEqual(readback["receipt"]["durableApprovalDigest"], APPROVAL)


if __name__ == "__main__":
    unittest.main()

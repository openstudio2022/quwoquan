# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
# spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-004
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import argparse
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import generate_mainline_release_artifact as generator
from quwoquan_ops.cli.prod import hosted_release_ledger


ROOT = Path(__file__).resolve().parents[3]


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class ProdReleaseTransactionContractTest(unittest.TestCase):
    def test_service_images_alone_are_not_marked_deployable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            descriptors = root / "image-descriptors"
            artifact.mkdir()
            descriptors.mkdir()
            generator.write_json(
                artifact / "manifest.json",
                {
                    "schema": "mainline-release-artifact",
                    "requiredImages": [],
                    "imageRepositories": {},
                    "versions": {"imageVersion": "1.0.0"},
                    "releaseFiles": {},
                    "releaseFileDigests": {},
                },
            )
            finalized = finalizer.finalize(artifact, descriptors)
            self.assertEqual(finalized["status"], "component-ready")
            self.assertNotIn("artifacts", finalized)

    def test_manifest_requires_every_digest_and_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            descriptors = root / "descriptors"
            artifact_descriptors = root / "artifact-descriptors"
            artifact.mkdir()
            descriptors.mkdir()
            artifact_descriptors.mkdir()
            image_version = "1.20260720.1"
            config_version = "v2026.07.20.1"

            release_files: dict[str, str] = {}
            release_digests: dict[str, str] = {}
            for service in generator.RELEASE_SERVICES:
                relative = Path("packages/services") / service / "config/config.yaml"
                path = artifact / relative
                generator.write_release_snapshot(
                    path,
                    generator.render_release_snapshot(service, config_version),
                )
                release_files[service] = relative.as_posix()
                release_digests[service] = generator.sha256_file(path)
            repositories = {
                service: f"ghcr.io/example/{service}"
                for service in generator.DEPLOYED_SERVICES
            }
            manifest = {
                "schema": "mainline-release-artifact",
                "artifactName": generator.ARTIFACT_NAME,
                "status": "build-input",
                "source": {
                    "gitSha": _git_head(),
                    "runNumber": 1,
                    "repository": "example/quwoquan",
                },
                "versions": {
                    "imageVersion": image_version,
                    "configVersion": config_version,
                },
                "requiredImages": list(generator.DEPLOYED_SERVICES),
                "imageRepositories": repositories,
                "images": {},
                "releaseFiles": release_files,
                "releaseFileDigests": release_digests,
            }
            generator.write_json(artifact / "manifest.json", manifest)

            artifact_schemas = {
                "publicWeb": "qwq.public-web.release.v1",
                "androidOfficialRelease": "qwq.android.official-release.v1",
                "opsPortal": "qwq.ops_portal_package.v1",
                "contractGraph": "qwq.contract-graph.v1",
                "providerBindings": "compiled-external-provider-bindings",
                "testEvidence": "qwq.three-layer-case-results.v1",
            }
            for artifact_id in finalizer.REQUIRED_RELEASE_ARTIFACTS:
                relative = Path("artifacts") / f"{artifact_id}.json"
                artifact_path = artifact / relative
                generator.write_json(
                    artifact_path,
                    {"schema": artifact_schemas[artifact_id]},
                )
                generator.write_json(
                    artifact_descriptors / f"{artifact_id}.json",
                    {
                        "artifactId": artifact_id,
                        "schema": artifact_schemas[artifact_id],
                        "path": relative.as_posix(),
                        "sha256": generator.sha256_file(artifact_path),
                    },
                )

            for index, service in enumerate(generator.DEPLOYED_SERVICES, start=1):
                repository = repositories[service]
                digest = f"sha256:{index:064x}"
                ref = f"{repository}@{digest}"
                generator.write_json(
                    descriptors / f"{service}.json",
                    {
                        "service": service,
                        "repository": repository,
                        "tag": image_version,
                        "digest": digest,
                        "ref": ref,
                        "attestations": {
                            "spdxSbom": f"oci://{ref}#spdxSbom",
                            "slsaProvenance": f"oci://{ref}#slsaProvenance",
                        },
                    },
                )

            finalized = finalizer.finalize(
                artifact,
                descriptors,
                artifact_descriptors,
            )
            self.assertEqual(
                set(finalized["artifacts"]),
                set(finalizer.REQUIRED_RELEASE_ARTIFACTS),
            )
            generator.write_json(
                artifact / "governance-receipt.json",
                {
                    "schema": "prod-release-governance-receipt",
                    "repository": "example/quwoquan",
                    "gitSha": _git_head(),
                    "manifestDigest": finalized["manifestDigest"],
                    "approvers": ["reviewer"],
                    "distinctPrincipals": ["author", "reviewer"],
                },
            )
            path, digest, loaded = stackctl._deployable_release_manifest(
                str(artifact / "manifest.json"),
                image_version=image_version,
                config_version=config_version,
            )
            self.assertEqual(path, (artifact / "manifest.json").resolve())
            self.assertEqual(digest, finalized["manifestDigest"])
            self.assertEqual(set(loaded["images"]), set(generator.DEPLOYED_SERVICES))

            first_config = artifact / next(iter(release_files.values()))
            first_config.write_text("tampered: true\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "config digest mismatch"):
                stackctl._deployable_release_manifest(
                    str(artifact / "manifest.json"),
                    image_version=image_version,
                    config_version=config_version,
                )

    def test_release_ledger_is_cas_ordered_and_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary).resolve()
            digest = "sha256:" + ("a" * 64)
            request = {
                "schema": hosted_release_ledger.REQUEST_SCHEMA,
                "service": "prod-stack",
                "fromImage": "1.0.0",
                "toImage": "1.1.0",
                "fromConfig": "v1",
                "toConfig": "v2",
                "step": "5",
                "stage": "gray-initial",
                "decision": "continue",
                "rollbackOutcome": "not_triggered",
                "manifestDigest": digest,
                "imageDigest": digest,
                "configDigest": digest,
                "contractGraphDigest": digest,
                "adapterDigest": digest,
                "expectedGeneration": 0,
                "sloReadback": {"source": "prometheus"},
                "postChecks": [
                    {
                        "name": "health",
                        "status": "passed",
                        "receiptDigest": digest,
                    }
                ],
                "lastGoodTarget": {"image": "1.0.0", "config": "v1"},
                "verifiedAt": "2026-07-26T00:00:00+00:00",
            }
            readback = hosted_release_ledger.commit(state_dir, request)
            self.assertEqual(readback["state"]["generation"], "1")
            self.assertRegex(readback["receiptRef"], r"^receipt:hosted:[0-9a-f]{64}$")
            self.assertEqual(
                hosted_release_ledger.fetch(state_dir, "prod-stack"),
                readback,
            )
            action, generation = stackctl._validate_release_transition(
                readback["state"],
                from_image="1.0.0",
                to_image="1.1.0",
                from_config="v1",
                to_config="v2",
                stage="carry-on",
                manifest_digest=digest,
            )
            self.assertEqual((action, generation), ("advance", 1))
            with self.assertRaisesRegex(RuntimeError, "CAS conflict"):
                hosted_release_ledger.commit(state_dir, request)

            receipt_path = state_dir / "receipts" / (
                readback["receipt"]["receiptId"] + ".json"
            )
            receipt_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest or ledger binding"):
                hosted_release_ledger.fetch(state_dir, "prod-stack")

    def test_warning_slo_pauses_gray_but_rolls_back_full(self) -> None:
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "gray-initial",
            ),
            ("pause", "slo gate decision=pause"),
        )

    def test_operator_receipt_readback_accepts_only_hosted_candidate_binding(self) -> None:
        digest = "sha256:" + ("a" * 64)
        receipt = {
            "schema": hosted_release_ledger.RECEIPT_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "service": "prod-stack",
            "fromImage": "1.0.0",
            "toImage": "1.1.0",
            "fromConfig": "v1",
            "toConfig": "v2",
            "step": "100",
            "stage": "full",
            "decision": "continue",
            "rollbackOutcome": "not_triggered",
            "manifestDigest": digest,
            "imageDigest": digest,
            "configDigest": digest,
            "contractGraphDigest": digest,
            "adapterDigest": digest,
            "expectedGeneration": 2,
            "committedGeneration": 3,
            "sloReadback": {},
            "postChecks": [],
            "lastGoodTarget": {"image": "1.1.0", "config": "v2"},
            "verifiedAt": "2026-07-26T00:00:00+00:00",
        }
        receipt_id = hosted_release_ledger._receipt_id(receipt)
        receipt["receiptId"] = receipt_id
        readback = {
            "schema": hosted_release_ledger.RECEIPT_READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        }
        args = argparse.Namespace(
            service="prod-stack",
            receipt_id=receipt_id,
            purpose="last-good",
            image_digest=digest,
            config_digest=digest,
            contract_graph_digest=digest,
            adapter_digest=digest,
        )
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["receiptRef"], f"receipt:hosted:{receipt_id}")

        rollback_receipt = dict(receipt)
        rollback_receipt.update(
            {
                "fromImage": "1.1.0",
                "toImage": "1.0.0",
                "fromConfig": "v2",
                "toConfig": "v1",
                "decision": "rolled_back",
                "rollbackOutcome": "rolled_back",
                "lastGoodTarget": {"image": "1.0.0", "config": "v1"},
            }
        )
        rollback_id = hosted_release_ledger._receipt_id(rollback_receipt)
        rollback_receipt["receiptId"] = rollback_id
        rollback_readback = {
            "schema": hosted_release_ledger.RECEIPT_READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "receipt": rollback_receipt,
            "receiptRef": f"receipt:hosted:{rollback_id}",
        }
        args.receipt_id = rollback_id
        args.purpose = "rollback"
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=rollback_readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 0)

        args.receipt_id = receipt_id
        args.purpose = "last-good"
        args.adapter_digest = "sha256:" + ("b" * 64)
        with patch.object(
            stackctl,
            "_run_hosted_release_ledger",
            return_value=readback,
        ):
            result = stackctl.command_hosted_release_receipt(args)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "full",
            ),
            ("rollback", "full rollout cannot remain paused on warning SLO"),
        )

    def test_global_release_lock_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(
                os.environ,
                {"QWQ_PROD_RELEASE_STATE_DIR": str(Path(temporary).resolve())},
                clear=False,
            ):
                with stackctl._prod_release_lock():
                    with self.assertRaisesRegex(RuntimeError, "lock is held"):
                        with stackctl._prod_release_lock():
                            self.fail("nested release lock must not be acquired")


if __name__ == "__main__":
    unittest.main()

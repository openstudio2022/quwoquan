from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import generate_mainline_release_artifact as generator


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
    def test_manifest_requires_every_digest_and_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact"
            descriptors = root / "descriptors"
            artifact.mkdir()
            descriptors.mkdir()
            image_version = "1.20260720.1"
            config_version = "v2026.07.20.1"

            release_files: dict[str, str] = {}
            release_digests: dict[str, str] = {}
            for service in generator.RELEASE_SERVICES:
                relative = Path("releases/config") / service / f"{config_version}.yaml"
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

            finalized = finalizer.finalize(artifact, descriptors)
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
            with patch.dict(
                os.environ,
                {"QWQ_PROD_RELEASE_STATE_DIR": str(state_dir)},
                clear=False,
            ):
                action, generation = stackctl._validate_release_transition(
                    {},
                    from_image="1.0.0",
                    to_image="1.1.0",
                    from_config="v1",
                    to_config="v2",
                    stage="gray-initial",
                    manifest_digest="sha256:" + ("a" * 64),
                )
                self.assertEqual((action, generation), ("advance", 0))
                state, receipt = stackctl._commit_release_transition(
                    service="prod-stack",
                    from_image="1.0.0",
                    to_image="1.1.0",
                    from_config="v1",
                    to_config="v2",
                    step="5",
                    stage="gray-initial",
                    decision="continue",
                    manifest_digest="sha256:" + ("a" * 64),
                    expected_generation=0,
                    receipt_id="receipt-1",
                    slo_readback={"source": "prometheus"},
                )
                self.assertEqual(state["generation"], "1")
                self.assertTrue(receipt.is_file())

                action, generation = stackctl._validate_release_transition(
                    stackctl._load_release_state("prod-stack"),
                    from_image="1.0.0",
                    to_image="1.1.0",
                    from_config="v1",
                    to_config="v2",
                    stage="gray-initial",
                    manifest_digest="sha256:" + ("a" * 64),
                )
                self.assertEqual((action, generation), ("replay", 1))

                action, generation = stackctl._validate_release_transition(
                    stackctl._load_release_state("prod-stack"),
                    from_image="1.0.0",
                    to_image="1.1.0",
                    from_config="v1",
                    to_config="v2",
                    stage="carry-on",
                    manifest_digest="sha256:" + ("a" * 64),
                )
                self.assertEqual((action, generation), ("advance", 1))
                with self.assertRaisesRegex(RuntimeError, "CAS conflict"):
                    stackctl._update_release_state(
                        "prod-stack",
                        from_image="1.0.0",
                        to_image="1.1.0",
                        from_config="v1",
                        to_config="v2",
                        step="25",
                        stage="carry-on",
                        decision="continue",
                        manifest_digest="sha256:" + ("a" * 64),
                        expected_generation=0,
                        receipt_id="stale",
                    )

    def test_warning_slo_pauses_gray_but_rolls_back_full(self) -> None:
        self.assertEqual(
            stackctl._decision_from_slo_output(
                "decision=pause reason=warning_threshold",
                "gray-initial",
            ),
            ("pause", "slo gate decision=pause"),
        )
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

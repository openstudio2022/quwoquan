# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-003
from __future__ import annotations

import json
import hashlib
import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import oci_supply_chain

DIGEST = "sha256:" + ("a" * 64)
REF = f"ghcr.io/owner/repo/content-service@{DIGEST}"
RELEASE_REF = f"ghcr.io/owner/repo/release-artifact@{DIGEST}"
REPOSITORY = "owner/repo"
SIGNER = "owner/repo/.github/workflows/service_pipeline.yml"
RELEASE_SIGNER = "owner/repo/.github/workflows/deploy-prod-auto.yml"


def completed(
    payload: object, *, returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        [],
        returncode,
        stdout=json.dumps(payload),
        stderr="" if returncode == 0 else "verification failed",
    )


def verification_payload() -> list[dict[str, object]]:
    return [
        {
            "verificationResult": {
                "statement": {
                    "subject": [
                        {
                            "name": "ghcr.io/owner/repo/content-service",
                            "digest": {"sha256": "a" * 64},
                        }
                    ]
                }
            }
        }
    ]


class OciSupplyChainSecurityContractTest(unittest.TestCase):
    def test_local_slsa_v1_requires_buildkit_invocation_identity(self) -> None:
        predicate = {
            "buildDefinition": {
                "buildType": "https://mobyproject.org/buildkit@v1",
                "resolvedDependencies": [],
            },
            "runDetails": {
                "builder": {"id": ""},
                "metadata": {
                    "invocationId": "local-build",
                    "buildkit_metadata": {"vcs": {"revision": "a" * 40}},
                },
            },
        }
        self.assertTrue(oci_supply_chain._has_slsa_provenance(predicate))
        predicate["runDetails"]["metadata"].pop("invocationId")
        self.assertFalse(oci_supply_chain._has_slsa_provenance(predicate))

    def _local_oci_archive(
        self,
        path: Path,
        *,
        include_provenance: bool = True,
    ) -> None:
        with tarfile.open(path, "w") as archive:
            descriptors: list[dict[str, object]] = []

            def add_json(payload: object) -> dict[str, object]:
                content = json.dumps(payload).encode()
                digest = hashlib.sha256(content).hexdigest()
                member = tarfile.TarInfo(f"blobs/sha256/{digest}")
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
                return {
                    "mediaType": "application/vnd.in-toto+json",
                    "digest": f"sha256:{digest}",
                    "size": len(content),
                }

            layers = [
                add_json(
                    {
                        "predicateType": "https://spdx.dev/Document/v2.3",
                        "predicate": {
                            "spdxVersion": "SPDX-2.3",
                            "SPDXID": "SPDXRef-DOCUMENT",
                            "packages": [{"name": "elasticsearch-cjk"}],
                        },
                    }
                )
            ]
            if include_provenance:
                layers.append(
                    add_json(
                        {
                            "predicateType": "https://slsa.dev/provenance/v1",
                            "predicate": {
                                "builder": {"id": "buildkit"},
                                "buildType": "https://mobyproject.org/buildkit@v1",
                                "materials": [],
                            },
                        }
                    )
                )
            manifest = add_json({"layers": layers})
            manifest["annotations"] = {
                "vnd.docker.reference.type": "attestation-manifest"
            }
            descriptors.append(manifest)
            index = json.dumps({"manifests": descriptors}).encode()
            member = tarfile.TarInfo("index.json")
            member.size = len(index)
            archive.addfile(member, io.BytesIO(index))

    def test_local_oci_attestations_are_non_promotable_and_structured(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "image.oci.tar"
            self._local_oci_archive(archive)
            verified = oci_supply_chain.inspect_local_oci_archive_attestations(
                archive
            )
            self.assertTrue(verified["nonPromotable"])
            self.assertEqual(verified["promotionEligibility"], "GATE_BLOCK")

            missing = Path(temporary) / "missing-provenance.oci.tar"
            self._local_oci_archive(missing, include_provenance=False)
            with self.assertRaisesRegex(RuntimeError, "SLSA provenance"):
                oci_supply_chain.inspect_local_oci_archive_attestations(missing)

    def test_structured_buildkit_predicates_are_required(self) -> None:
        runner = mock.Mock(
            side_effect=[
                completed(
                    {
                        "SPDX": {
                            "spdxVersion": "SPDX-2.3",
                            "SPDXID": "SPDXRef-DOCUMENT",
                            "packages": [{"name": "content-service"}],
                        }
                    }
                ),
                completed(
                    {
                        "SLSA": {
                            "builder": {"id": "buildkit"},
                            "buildType": "https://mobyproject.org/buildkit@v1",
                            "materials": [],
                        }
                    }
                ),
            ]
        )
        spdx = oci_supply_chain.inspect_buildkit_attestations(REF, runner=runner)
        self.assertEqual(spdx["spdxVersion"], "SPDX-2.3")
        self.assertEqual(runner.call_count, 2)

    def test_human_readable_words_cannot_replace_structured_attestations(self) -> None:
        runner = mock.Mock(return_value=completed("sbom provenance"))
        with self.assertRaisesRegex(RuntimeError, "structured SPDX"):
            oci_supply_chain.inspect_buildkit_attestations(REF, runner=runner)

    def test_signed_claims_enforce_repo_workflow_issuer_and_exact_subject(self) -> None:
        runner = mock.Mock(
            side_effect=[
                completed(verification_payload()),
                completed(verification_payload()),
            ]
        )
        verified = oci_supply_chain.verify_signed_attestations(
            REF,
            repository=REPOSITORY,
            signer_workflow=SIGNER,
            source_digest="b" * 40,
            runner=runner,
        )
        self.assertEqual(set(verified), set(oci_supply_chain.PREDICATES))
        for call in runner.call_args_list:
            argv = call.args[0]
            self.assertIn("--bundle-from-oci", argv)
            self.assertIn("--signer-workflow", argv)
            self.assertIn(SIGNER, argv)
            self.assertIn("--cert-oidc-issuer", argv)
            self.assertIn(oci_supply_chain.OIDC_ISSUER, argv)
            self.assertIn("--source-digest", argv)

    def test_wrong_signer_or_subject_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "not canonical"):
            oci_supply_chain.verify_signed_attestations(
                REF,
                repository=REPOSITORY,
                signer_workflow="owner/repo/.github/workflows/other.yml",
            )
        runner = mock.Mock(return_value=completed([]))
        with self.assertRaisesRegex(RuntimeError, "does not bind"):
            oci_supply_chain.verify_signed_attestations(
                REF,
                repository=REPOSITORY,
                signer_workflow=SIGNER,
                runner=runner,
            )

    def test_prod_workflow_can_sign_only_release_artifacts(self) -> None:
        release_payload = verification_payload()
        release_payload[0]["verificationResult"]["statement"]["subject"][0]["name"] = (
            "ghcr.io/owner/repo/release-artifact"
        )
        runner = mock.Mock(
            side_effect=[completed(release_payload), completed(release_payload)]
        )
        verified = oci_supply_chain.verify_signed_attestations(
            RELEASE_REF,
            repository=REPOSITORY,
            signer_workflow=RELEASE_SIGNER,
            source_digest="b" * 40,
            runner=runner,
        )
        self.assertEqual(set(verified), set(oci_supply_chain.PREDICATES))
        with self.assertRaisesRegex(ValueError, "not canonical"):
            oci_supply_chain.verify_signed_attestations(
                REF,
                repository=REPOSITORY,
                signer_workflow=RELEASE_SIGNER,
            )

    def test_cli_extracts_only_canonical_spdx_json(self) -> None:
        spdx = {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "packages": [{"name": "content-service"}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "sbom.spdx.json"
            with (
                mock.patch.object(
                    oci_supply_chain,
                    "parse_args",
                    return_value=mock.Mock(
                        command="extract-sbom",
                        ref=REF,
                        output=output,
                    ),
                ),
                mock.patch.object(
                    oci_supply_chain,
                    "inspect_buildkit_attestations",
                    return_value=spdx,
                ),
            ):
                self.assertEqual(oci_supply_chain.main(), 0)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                spdx,
            )


if __name__ == "__main__":
    unittest.main()

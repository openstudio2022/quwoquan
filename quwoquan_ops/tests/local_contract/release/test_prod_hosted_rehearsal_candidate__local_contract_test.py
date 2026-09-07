"""prod-hosted exact dev candidate rehearsal 合同（不可提升的第二类 prevalidate 输入）。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t1
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t2
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t3
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t4
spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t1
spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t2
spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t3
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import legal_static, stackctl
from quwoquan_ops.cli.commands import deploy_rollout
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    manifest as candidate_manifest,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    prod_hosted_rehearsal as rehearsal,
)
from quwoquan_ops.cli.lib.immutable_image_composition import runtime_image_owner_names
from quwoquan_ops.cli.prod import load_prod_plane_images as loader
from quwoquan_ops.cli.prod import prevalidate_prod_hosted as prevalidate


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


CANDIDATE = _sha("rehearsal-candidate")
SOURCE = "a" * 40
PROVIDER_RUNTIME_DIGEST = _sha("provider-runtime")


def _rehearsal_oci(
    *,
    legal_placeholder: bool = True,
    configuration_digest: str = _sha("configuration"),
) -> dict[str, object]:
    owners = runtime_image_owner_names()
    images = {
        owner: {
            "ref": f"{rehearsal.local_image_repository(owner)}:{hashlib.sha256(owner.encode()).hexdigest()}",
            "imageDigest": _sha(f"image-{owner}"),
        }
        for owner in owners
    }
    refs = {owner: descriptor["ref"] for owner, descriptor in images.items()}
    return {
        "schema": stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
        "environment": "prod",
        "target": "prod-hosted",
        "configurationDigest": configuration_digest,
        "buildInputDigest": rehearsal.rehearsal_build_input_digest(
            refs,
            provider_runtime_digest=PROVIDER_RUNTIME_DIGEST,
            legal_static_placeholder=legal_placeholder,
        ),
        "imageDigest": rehearsal._sha256_json(images),
        "images": images,
        "materialSource": rehearsal.REHEARSAL_MATERIAL_SOURCE,
        "platform": rehearsal.REHEARSAL_PLATFORM,
        "nonPromotable": True,
        "legalStaticPlaceholder": legal_placeholder,
        "publicEntry": rehearsal.REHEARSAL_PUBLIC_ENTRY,
    }


def _git_runner(*, dirty: str = "", head: str = SOURCE, dev_head: str = SOURCE):
    def fake_run(argv, **_kwargs):
        args = list(argv)
        if args[1] == "status":
            return subprocess.CompletedProcess(args, 0, stdout=dirty, stderr="")
        if args[1] == "rev-parse" and args[-1] == "HEAD":
            return subprocess.CompletedProcess(args, 0, stdout=head + "\n", stderr="")
        if args[1] == "rev-parse" and args[-1] == rehearsal.DEV_REF:
            return subprocess.CompletedProcess(args, 0, stdout=dev_head + "\n", stderr="")
        raise AssertionError(f"unexpected git call: {args}")

    return fake_run


class RehearsalSourceGateContractTest(unittest.TestCase):
    """SIT-003 t1 / GWT-005 t1：候选来源、架构与 digest 任一不一致均在传输前 fail closed。"""

    def test_source_gate_requires_clean_tree_and_exact_dev_head(self) -> None:
        candidate = {"sourceRevision": SOURCE}
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner(dirty=" M x")):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "uncommitted worktree"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner(head="b" * 40)):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "does not match HEAD"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner(dev_head="c" * 40)):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "exact local dev1.0 head"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner()):
            gate = rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        self.assertEqual(gate, {"head": SOURCE, "devHead": SOURCE, "sourceRevision": SOURCE})

    def test_rehearsal_manifest_only_accepts_local_amd64_digest_closure(self) -> None:
        oci = _rehearsal_oci()
        self.assertEqual(set(rehearsal.validate_rehearsal_oci_manifest(oci)), set(runtime_image_owner_names()))
        for mutation, pattern in (
            ({"platform": "linux/arm64"}, "linux/amd64"),
            ({"nonPromotable": False}, "nonPromotable=true"),
            ({"publicEntry": "public-ca-prod"}, "host-shared-edge"),
            ({"materialSource": "factory"}, "materialSource mismatch"),
        ):
            with self.assertRaisesRegex(rehearsal.RehearsalError, pattern):
                rehearsal.validate_rehearsal_oci_manifest({**oci, **mutation})
        ghcr = json.loads(json.dumps(oci))
        owner = next(iter(ghcr["images"]))
        ghcr["images"][owner]["ref"] = f"ghcr.io/owner/repo/{owner}-prod@{_sha('x')}"
        with self.assertRaisesRegex(rehearsal.RehearsalError, "local build digest"):
            rehearsal.validate_rehearsal_oci_manifest(ghcr)
        partial = json.loads(json.dumps(oci))
        partial["images"].pop(owner)
        with self.assertRaisesRegex(rehearsal.RehearsalError, "owner closure"):
            rehearsal.validate_rehearsal_oci_manifest(partial)

    def test_local_images_must_exist_be_amd64_and_match_candidate_digest(self) -> None:
        oci = _rehearsal_oci()
        images = oci["images"]

        def inspect(ref: str, template: str) -> str | None:
            owner = next(o for o, d in images.items() if d["ref"] == ref)
            if template == "{{.Architecture}}":
                return "arm64" if owner == "rtc-service" else "amd64"
            return images[owner]["imageDigest"]

        with mock.patch.object(rehearsal, "_docker_inspect", side_effect=inspect):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "not linux/amd64"):
                rehearsal.verify_local_rehearsal_images(oci)

        def drifted(ref: str, template: str) -> str | None:
            if template == "{{.Architecture}}":
                return "amd64"
            return _sha("someone-rebuilt-it")

        with mock.patch.object(rehearsal, "_docker_inspect", side_effect=drifted):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "content digest drifted"):
                rehearsal.verify_local_rehearsal_images(oci)
        with mock.patch.object(rehearsal, "_docker_inspect", return_value=None):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "missing locally"):
                rehearsal.verify_local_rehearsal_images(oci)

        def exact(ref: str, template: str) -> str | None:
            owner = next(o for o, d in images.items() if d["ref"] == ref)
            return "amd64" if template == "{{.Architecture}}" else images[owner]["imageDigest"]

        with mock.patch.object(rehearsal, "_docker_inspect", side_effect=exact):
            verified = rehearsal.verify_local_rehearsal_images(oci)
        self.assertEqual(verified, {o: d["imageDigest"] for o, d in images.items()})


class RehearsalImageDeliveryContractTest(unittest.TestCase):
    """SIT-003 t2：候选镜像只经 exact digest 从本机交付，交付 tag 与渲染面一致。"""

    def test_loader_maps_compose_services_to_owner_images_and_shares_render_tag(self) -> None:
        oci = _rehearsal_oci()
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "oci-images.json"
            manifest_path.write_text(json.dumps(oci), encoding="utf-8")
            with mock.patch.object(rehearsal, "verify_local_rehearsal_images", return_value={}):
                sources = loader._local_rehearsal_image_sources(
                    manifest_path,
                    services=["content-service", "api-edge", "recommendation-service", "rtc-service"],
                    candidate_digest=CANDIDATE,
                )
        core_ref = oci["images"]["service-core"]["ref"]
        self.assertEqual(sources["content-service"], core_ref)
        self.assertEqual(sources["api-edge"], core_ref)
        self.assertEqual(sources["recommendation-service"], oci["images"]["recommendation-service"]["ref"])
        self.assertEqual(sources["rtc-service"], oci["images"]["rtc-service"]["ref"])
        transport_tag = CANDIDATE.removeprefix("sha256:")
        refs = loader._compose_image_refs(
            ["content-service"], candidate_digest=CANDIDATE, image_transport_tag=transport_tag
        )
        self.assertEqual(refs["content-service"], f"localhost/quwoquan_service_content-service:{transport_tag}")
        with self.assertRaisesRegex(SystemExit, "valid OCI tag"):
            loader._compose_image_refs(["content-service"], candidate_digest=CANDIDATE, image_transport_tag="bad tag")

    def test_loader_rejects_factory_manifest_for_local_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "oci-images.json"
            manifest_path.write_text(json.dumps({"images": {}}), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "local-build rehearsal manifest"):
                loader._local_rehearsal_image_sources(
                    manifest_path, services=["content-service"], candidate_digest=CANDIDATE
                )
        with self.assertRaisesRegex(SystemExit, "candidate-oci-manifest is required"):
            loader._local_rehearsal_image_sources(None, services=["content-service"], candidate_digest=CANDIDATE)

    def test_executor_parser_makes_snapshot_and_exact_candidate_mutually_exclusive(self) -> None:
        transport_tag = CANDIDATE.removeprefix("sha256:")
        with mock.patch.object(
            prevalidate.sys,
            "argv",
            [
                "prevalidate",
                "--exact-candidate",
                CANDIDATE,
                "--image-transport-tag",
                transport_tag,
                "--candidate-digest",
                CANDIDATE,
                "--data-mode",
                "isolated",
                "--scope",
                "first-party",
            ],
        ):
            parsed = prevalidate.parse_args()
        self.assertEqual(parsed.exact_candidate, CANDIDATE)
        self.assertIsNone(parsed.frozen_diagnostic_snapshot)
        with mock.patch.object(
            prevalidate.sys,
            "argv",
            [
                "prevalidate",
                "--exact-candidate",
                CANDIDATE,
                "--frozen-diagnostic-snapshot",
                "/tmp/manifest.json",
                "--image-transport-tag",
                transport_tag,
                "--candidate-digest",
                CANDIDATE,
                "--data-mode",
                "isolated",
                "--scope",
                "first-party",
            ],
        ):
            with self.assertRaises(SystemExit):
                prevalidate.parse_args()


class RehearsalNonPromotableBoundaryContractTest(unittest.TestCase):
    """SIT-003 t3 / GWT-005 t2：报告分轴且 releaseEligibility 恒 GATE_BLOCK；候选不进 formal/snapshot 路径。"""

    def _deploy_args(self, tmp: str, *extra: str):
        return stackctl.build_parser().parse_args(
            [
                "deploy",
                "--target",
                "prod-hosted",
                "--mode",
                "prevalidate",
                "--data-mode",
                "isolated",
                "--prevalidate-scope",
                "first-party",
                "--host-id",
                "prod-host-01",
                "--report-dir",
                tmp,
                *extra,
            ]
        )

    def test_prevalidate_rejects_mixing_snapshot_and_exact_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = self._deploy_args(
                tmp, "--exact-candidate", CANDIDATE, "--frozen-diagnostic-snapshot", "/tmp/manifest.json"
            )
            with (
                mock.patch.object(stackctl, "_validate_prod_prevalidation_public_bases"),
                mock.patch.object(stackctl, "_exact_candidate_rehearsal_inputs") as exact_inputs,
                mock.patch.object(stackctl, "_frozen_diagnostic_snapshot") as snapshot_inputs,
                mock.patch.object(
                    stackctl,
                    "_prod_prevalidation_executor",
                    return_value=(
                        subprocess.CompletedProcess(["prevalidate"], 0, stdout="{}", stderr=""),
                        {"containerDeployment": {"status": "planned"}},
                    ),
                ),
            ):
                result = stackctl.command_deploy(args)
            self.assertEqual(result["exitCode"], 2)
            self.assertTrue(any("not both" in item for item in result["details"]))
            exact_inputs.assert_not_called()
            snapshot_inputs.assert_not_called()

    def test_rehearsal_report_is_non_promotable_and_skips_repackage(self) -> None:
        oci = _rehearsal_oci(legal_placeholder=True)
        with tempfile.TemporaryDirectory() as tmp:
            args = self._deploy_args(tmp, "--exact-candidate", CANDIDATE, "--dry-run", "true")
            planned = {
                "hostPreflight": {"status": "checked"},
                "containerDeployment": {"status": "planned"},
                "providerReadiness": {"status": "GATE_BLOCK", "excludedCapabilities": ["apns"]},
            }
            with (
                mock.patch.object(stackctl, "_validate_prod_prevalidation_public_bases"),
                mock.patch.object(
                    stackctl,
                    "_exact_candidate_rehearsal_inputs",
                    return_value=(
                        Path(tmp) / "oci-images.json",
                        CANDIDATE,
                        oci,
                        CANDIDATE.removeprefix("sha256:"),
                        CANDIDATE,
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_prod_prevalidation_executor",
                    return_value=(
                        subprocess.CompletedProcess(["prevalidate"], 0, stdout="{}", stderr=""),
                        planned,
                    ),
                ) as executor,
                mock.patch.object(stackctl, "run") as package_run,
                mock.patch.object(stackctl, "_run_hosted_release_ledger") as ledger,
                mock.patch.object(stackctl, "_prod_release_lock") as release_lock,
            ):
                result = stackctl.command_deploy(args)
            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(result["releaseEligibility"], "GATE_BLOCK")
            self.assertEqual(result["providerReadiness"], "GATE_BLOCK")
            self.assertEqual(result["containerDeployment"], "planned")
            package_run.assert_not_called()
            ledger.assert_not_called()
            release_lock.assert_not_called()
            self.assertEqual(executor.call_args.kwargs["material_source"], "local-build")
            report = json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["materialSource"], "local-build")
            self.assertEqual(report["releaseEligibility"]["status"], "GATE_BLOCK")
            self.assertFalse(report["releaseEligibility"]["promotable"])
            self.assertFalse(report["releaseEligibility"]["ledgerWritten"])
            self.assertFalse(report["releaseEligibility"]["receiptWritten"])
            self.assertEqual(report["package"]["skipped"], "exact-candidate rehearsal consumes the sealed local-build candidate")
            self.assertEqual(report["releaseEvidence"]["candidateId"], CANDIDATE)

    def test_formal_rollout_and_snapshot_paths_refuse_rehearsal_material(self) -> None:
        oci = _rehearsal_oci()
        with tempfile.TemporaryDirectory() as tmp:
            candidate_root = Path(tmp) / "candidates" / "runtime-full" / CANDIDATE.replace(":", "-")
            (candidate_root / "packages" / "runtime-shared").mkdir(parents=True)
            (candidate_root / "packages" / "runtime-shared" / "oci-images.json").write_text(
                json.dumps(oci), encoding="utf-8"
            )
            with mock.patch.object(stackctl, "deployment_candidate_dir", return_value=candidate_root):
                with self.assertRaisesRegex(ValueError, "rejects a local-build rehearsal candidate"):
                    deploy_rollout._reject_rehearsal_candidate_for_formal_rollout(CANDIDATE)
                deploy_rollout._reject_rehearsal_candidate_for_formal_rollout("not-a-digest")
        # frozen snapshot 输入面只接受 Service Pipeline manifest，不接受本地 oci 清单。
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "manifest.json"
            snapshot.write_text(json.dumps(oci), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "canonical deployable release evidence"):
                stackctl._frozen_diagnostic_snapshot(str(snapshot))

    def test_executor_requires_exact_candidate_to_equal_candidate_digest_and_tag(self) -> None:
        args = mock.Mock()
        args.exact_candidate = CANDIDATE
        args.candidate_digest = _sha("other")
        args.image_transport_tag = CANDIDATE.removeprefix("sha256:")
        with self.assertRaisesRegex(prevalidate.PrevalidationError, "must equal --candidate-digest"):
            prevalidate.validate_rehearsal_candidate(args)
        args.candidate_digest = CANDIDATE
        args.image_transport_tag = "latest"
        with self.assertRaisesRegex(prevalidate.PrevalidationError, "candidate digest hex"):
            prevalidate.validate_rehearsal_candidate(args)
        args.exact_candidate = ""
        self.assertEqual(prevalidate.validate_rehearsal_candidate(args), {"materialSource": "factory"})


class RehearsalDiagnosticMarkerContractTest(unittest.TestCase):
    """SIT-003 t4 / GWT-005 t3：legal 占位、宿主 edge TLS 与 release readback 只是 rehearsal 诊断标记。"""

    def test_legal_static_placeholder_policy_blocks_by_default_and_only_marks_for_rehearsal(self) -> None:
        manifest, issues = legal_static.validate_manifest("prod")
        self.assertIsInstance(manifest, dict)
        blocking, placeholders = legal_static._split_placeholder_issues(
            ["owner.operatorName contains placeholder text", "schema must be legal-static"]
        )
        self.assertEqual(blocking, ["schema must be legal-static"])
        self.assertEqual(placeholders, ["owner.operatorName"])
        self.assertEqual(legal_static._placeholder_policy(""), "block")
        self.assertEqual(legal_static._placeholder_policy("mark"), "mark")
        with self.assertRaisesRegex(ValueError, "placeholder policy is invalid"):
            legal_static._placeholder_policy("skip")
        with mock.patch.dict(
            legal_static.os.environ, {legal_static.PLACEHOLDER_POLICY_ENV: "mark"}, clear=False
        ):
            self.assertEqual(legal_static._placeholder_policy(""), "mark")
        del issues

    def test_rehearsal_report_marks_legal_placeholder_and_host_shared_edge_as_diagnostic(self) -> None:
        oci = _rehearsal_oci(legal_placeholder=True)
        with tempfile.TemporaryDirectory() as tmp:
            args = stackctl.build_parser().parse_args(
                [
                    "deploy",
                    "--target",
                    "prod-hosted",
                    "--mode",
                    "prevalidate",
                    "--data-mode",
                    "isolated",
                    "--prevalidate-scope",
                    "first-party",
                    "--exact-candidate",
                    CANDIDATE,
                    "--dry-run",
                    "true",
                    "--report-dir",
                    tmp,
                ]
            )
            with (
                mock.patch.object(stackctl, "_validate_prod_prevalidation_public_bases"),
                mock.patch.object(
                    stackctl,
                    "_exact_candidate_rehearsal_inputs",
                    return_value=(Path(tmp) / "oci-images.json", CANDIDATE, oci, CANDIDATE[7:], CANDIDATE),
                ),
                mock.patch.object(
                    stackctl,
                    "_prod_prevalidation_executor",
                    return_value=(
                        subprocess.CompletedProcess(["prevalidate"], 0, stdout="{}", stderr=""),
                        {"hostPreflight": {"status": "checked"}, "containerDeployment": {"status": "planned"}},
                    ),
                ),
                mock.patch.object(stackctl, "run"),
            ):
                stackctl.command_deploy(args)
            report = json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(
            report["rehearsal"],
            {
                "nonPromotable": True,
                "legalStaticPlaceholder": True,
                "publicEntry": rehearsal.REHEARSAL_PUBLIC_ENTRY,
                "platform": rehearsal.REHEARSAL_PLATFORM,
                "evidenceClass": "rehearsal-diagnostic",
            },
        )
        self.assertEqual(report["releaseEligibility"]["status"], "GATE_BLOCK")

    def test_candidate_validator_accepts_rehearsal_binding_without_release_evidence(self) -> None:
        services = ["content-service", "user-service"]
        with tempfile.TemporaryDirectory() as tmp:
            # candidate 根读取拒绝符号链接祖先；macOS 的 /var 是 /private/var 的链接。
            root = Path(tmp).resolve()
            versions: dict[str, str] = {}
            for service in services:
                package_dir = root / "packages" / "services" / service
                (package_dir / "config").mkdir(parents=True)
                config = package_dir / "config" / "config.yaml"
                config.write_text(f"config:\n  service: {service}\n", encoding="utf-8")
                config_digest = "sha256:" + hashlib.sha256(config.read_bytes()).hexdigest()
                versions[service] = _sha(f"version-{service}")
                (package_dir / "provenance.json").write_text(
                    json.dumps(
                        {
                            "schema": "qwq.service_package",
                            "service": service,
                            "environment": "prod",
                            "gitRevision": SOURCE,
                            "configVersion": versions[service],
                            "digests": {"config": config_digest},
                        }
                    ),
                    encoding="utf-8",
                )
            (root / "packages" / "app").mkdir(parents=True)
            (root / "packages" / "app" / "package-fingerprint.json").write_text(
                json.dumps({"servicePackages": services}), encoding="utf-8"
            )
            oci = _rehearsal_oci(configuration_digest=rehearsal._sha256_json(versions))
            (root / "packages" / "runtime-shared").mkdir(parents=True)
            (root / "packages" / "runtime-shared" / "oci-images.json").write_text(
                json.dumps(oci), encoding="utf-8"
            )
            candidate = {
                "target": "prod-hosted",
                "sourceRevision": SOURCE,
                "providerRuntime": {
                    "images": {},
                    "composition": {"runtimeCompositionDigest": PROVIDER_RUNTIME_DIGEST},
                },
            }
            candidate_manifest._validate_prod_hosted_oci_binding(candidate, candidate_root=root)
            with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner()):
                candidate_manifest._validate_prod_hosted_release_evidence_currentness(
                    candidate, candidate_root=root
                )
            drifted = json.loads(json.dumps(oci))
            drifted["legalStaticPlaceholder"] = False
            (root / "packages" / "runtime-shared" / "oci-images.json").write_text(
                json.dumps(drifted), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "buildInputDigest closure mismatch"):
                candidate_manifest._validate_prod_hosted_oci_binding(candidate, candidate_root=root)


if __name__ == "__main__":
    unittest.main()

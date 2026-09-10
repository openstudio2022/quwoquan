"""prod-hosted exact dev candidate rehearsal 合同（不可提升的第二类 prevalidate 输入）。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t1
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t2
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t3
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t4
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t5
spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t6
spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t1
spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t2
spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-005.t3
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

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


def _git_runner(
    *,
    dirty: str = "",
    head: str = SOURCE,
    dev_head: str = SOURCE,
    ancestor: bool = True,
    changed_inputs: str = "",
):
    def fake_run(argv, **_kwargs):
        args = list(argv)
        if args[1] == "status":
            return subprocess.CompletedProcess(args, 0, stdout=dirty, stderr="")
        if args[1] == "rev-parse" and args[-1] == "HEAD":
            return subprocess.CompletedProcess(args, 0, stdout=head + "\n", stderr="")
        if args[1] == "rev-parse" and args[-1] == rehearsal.DEV_REF:
            return subprocess.CompletedProcess(args, 0, stdout=dev_head + "\n", stderr="")
        if args[1] == "merge-base":
            return subprocess.CompletedProcess(args, 0 if ancestor else 1, stdout="", stderr="")
        if args[1] == "diff":
            return subprocess.CompletedProcess(args, 0, stdout=changed_inputs, stderr="")
        raise AssertionError(f"unexpected git call: {args}")

    return fake_run


def _capsule_root(tmp: str) -> Path:
    root = Path(tmp).resolve()
    (root / "input-capsule").mkdir(parents=True, exist_ok=True)
    (root / "input-capsule" / "manifest.json").write_text(
        json.dumps(
            {
                "deploymentInputRoots": [
                    "/outside/release.json",
                    "quwoquan_ops",
                    "quwoquan_service/services",
                ]
            }
        ),
        encoding="utf-8",
    )
    return root


class RehearsalSourceGateContractTest(unittest.TestCase):
    """SIT-003 t1 / GWT-005 t1：候选来源、架构与 digest 任一不一致均在传输前 fail closed。"""

    def test_source_gate_requires_clean_tree_and_exact_dev_head(self) -> None:
        candidate = {"sourceRevision": SOURCE}
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner(dirty=" M x")):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "uncommitted worktree"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        newer = "b" * 40
        # HEAD 前移但候选不是其祖先（或无 capsule 可比较）→ 拒绝。
        with mock.patch.object(
            rehearsal.subprocess, "run", side_effect=_git_runner(head=newer, dev_head=newer, ancestor=False)
        ):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "does not match HEAD"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        with mock.patch.object(
            rehearsal.subprocess, "run", side_effect=_git_runner(head=newer, dev_head=newer)
        ):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "inputs are unavailable"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner(dev_head="c" * 40)):
            with self.assertRaisesRegex(rehearsal.RehearsalError, "exact local dev1.0 head"):
                rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        with mock.patch.object(rehearsal.subprocess, "run", side_effect=_git_runner()):
            gate = rehearsal.rehearsal_candidate_source_gate(candidate, repo_root=Path("/repo"))
        self.assertEqual(
            gate,
            {"head": SOURCE, "devHead": SOURCE, "sourceRevision": SOURCE, "reusedFromAncestor": "false"},
        )
        # 内容寻址复用：候选是 HEAD 祖先且打包输入路径无改动 → 接受并标记 reusedFromAncestor。
        with tempfile.TemporaryDirectory() as tmp:
            root = _capsule_root(tmp)
            with mock.patch.object(
                rehearsal.subprocess, "run", side_effect=_git_runner(head=newer, dev_head=newer)
            ):
                gate = rehearsal.rehearsal_candidate_source_gate(
                    candidate, repo_root=Path("/repo"), candidate_root=root
                )
            self.assertEqual(gate["reusedFromAncestor"], "true")
            with mock.patch.object(
                rehearsal.subprocess,
                "run",
                side_effect=_git_runner(head=newer, dev_head=newer, changed_inputs="quwoquan_ops/cli/x.py\n"),
            ):
                with self.assertRaisesRegex(rehearsal.RehearsalError, "package inputs changed"):
                    rehearsal.rehearsal_candidate_source_gate(
                        candidate, repo_root=Path("/repo"), candidate_root=root
                    )

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

    def test_loader_streams_each_content_digest_once_and_tags_the_rest(self) -> None:
        """SIT-003 t2：同一 content digest 只跨网交付一次，其余 compose 服务只在远端按 digest 打 tag。"""
        core = _sha("core-image")
        rec = _sha("rec-image")
        refs = {
            "content-service": "localhost/quwoquan_service_content-service:t",
            "chat-service": "localhost/quwoquan_service_chat-service:t",
            "recommendation-service": "localhost/quwoquan_service_recommendation-service:t",
        }
        local = {"content-service": core, "chat-service": core, "recommendation-service": rec}
        remote: dict[str, str] = {rec: rec}  # 上一候选已把 rec 镜像交付到远端（按 ID 可见）

        def remote_digest(ref, *_args):
            return remote.get(ref)

        def stream(ref, *_args):
            remote[ref] = local[next(s for s, r in refs.items() if r == ref)]
            return remote[ref]

        def tag(source, target, *_args):
            remote[target] = remote[source]
            return remote[target]

        args = mock.Mock(host="h", image_source="local", dry_run=False, platform="linux/amd64")
        with (
            mock.patch.object(loader, "_remote_image_digest", side_effect=remote_digest),
            mock.patch.object(loader, "_stream_image", side_effect=stream) as streamed,
            mock.patch.object(loader, "_tag_remote_image", side_effect=tag) as tagged,
        ):
            transport = loader._deliver_images(
                ["content-service", "chat-service", "recommendation-service"],
                image_refs=refs,
                local_digests=local,
                account="prod-service-svc",
                host=args.host,
                key_file=Path("/k"),
            )
        self.assertEqual(
            transport,
            {
                "content-service": "streamed",
                "chat-service": "remote-tag",
                "recommendation-service": "remote-tag-by-digest",
            },
        )
        self.assertEqual(streamed.call_count, 1)
        self.assertEqual(tagged.call_count, 2)
        self.assertEqual(remote[refs["chat-service"]], core)
        self.assertEqual(remote[refs["recommendation-service"]], rec)

    def test_render_rewrites_artifact_identity_and_platform_ops_facts_mounts(self) -> None:
        """SIT-003 t2：渲染面必须把 DEC-005 的两处 `${...:?}` 只读挂载改写为 render 输出内的材料，
        否则 user systemd unit 在 compose 插值阶段即失败，永远到不了 enabled/active。"""
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib import volume_layout

        common = dict(
            config_root="./runtime/config-root",
            media_root="./runtime/media",
            legal_root="./runtime/legal",
            portal_root="./runtime/portal",
            caddyfile_path="./runtime/Caddyfile",
            model_cache_root="./runtime/model-cache",
        )
        self.assertEqual(
            volume_layout._rewrite_volume_with_layout(
                "${QWQ_COMPOSE_ARTIFACT_IDENTITY_FILE:?artifact identity mount is required}"
                ":/etc/quwoquan/artifact-identity.json:ro",
                **common,
            ),
            "./runtime/artifact-identity.json:/etc/quwoquan/artifact-identity.json:ro",
        )
        self.assertEqual(
            volume_layout._rewrite_volume_with_layout(
                "${QWQ_COMPOSE_PLATFORM_OPS_FACTS_ROOT:?platform-ops runtime facts mount is required}:/app:ro",
                **common,
            ),
            "./runtime/platform-ops-facts:/app:ro",
        )
        # 精确 target 匹配：/app/cache 与嵌套 process 目录不被 /app 规则吞掉。
        self.assertEqual(
            volume_layout._rewrite_volume_with_layout("model-cache:/app/cache", **common),
            "./runtime/model-cache:/app/cache",
        )
        nested = "platform-ops-prevalidation-state:/app/.qwq_output/env/repo/local/control-plane/process/platform-ops-service"
        self.assertEqual(volume_layout._rewrite_volume_with_layout(nested, **common), nested)
        from quwoquan_ops.cli.prod import render_prod_plane_stack as render

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = render._write_artifact_identity_and_platform_ops_facts(
                output_root=out, candidate_digest=CANDIDATE
            )
            identity = json.loads((out / "runtime" / "artifact-identity.json").read_text())
            self.assertEqual(identity["environment"], "prod")
            self.assertEqual(identity["configDigest"], CANDIDATE)
            facts = out / "runtime" / "platform-ops-facts"
            self.assertTrue((facts / "quwoquan_ops/environments/prod/runtime.yaml").is_file())
            self.assertTrue(
                (facts / "quwoquan_service/control-plane/platform-ops/environments/prod").is_dir()
            )
            self.assertIn("user-service", result["platformOpsFactsServices"])

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
    """SIT-003 t3、t4 / GWT-005 t2：报告分轴且 releaseEligibility 恒 GATE_BLOCK（t3）；
    候选不进 formal rollout / frozen snapshot / tag / admission / ledger 路径（t4）。"""

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
    """SIT-003 t5、t6 / GWT-005 t3：release readback 只记为 rehearsal 诊断（evidenceClass），
    legal 占位与宿主 edge TLS 承接在候选与报告中显式标记为非准出证据。"""

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

    def test_provider_oci_binding_accepts_rehearsal_shape_and_still_rejects_unknown_fields(self) -> None:
        """SIT-003 t4：候选封存的 Provider/OCI 交叉校验必须认得 rehearsal 12 字段形态，
        而 factory 形态仍只允许 7 个字段——两类输入互斥，不得靠放宽字段集合合流。"""
        oci = _rehearsal_oci()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "packages" / "runtime-shared").mkdir(parents=True)
            oci_path = root / "packages" / "runtime-shared" / "oci-images.json"
            oci_path.write_text(json.dumps(oci), encoding="utf-8")
            candidate = {
                "environment": "prod",
                "target": "prod-hosted",
                "buildInputDigest": oci["buildInputDigest"],
                "imageDigest": oci["imageDigest"],
                "configurationDigest": oci["configurationDigest"],
                "providerRuntime": {
                    "images": {},
                    "composition": {"runtimeCompositionDigest": PROVIDER_RUNTIME_DIGEST},
                },
            }
            candidate_manifest._validate_candidate_provider_oci_binding(
                candidate, candidate_root=root
            )

            factory_with_extra = {
                key: value
                for key, value in oci.items()
                if key not in {"platform", "nonPromotable", "legalStaticPlaceholder", "publicEntry"}
            }
            factory_with_extra["materialSource"] = "factory"
            oci_path.write_text(json.dumps(factory_with_extra), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OCI image manifest fields mismatch"):
                candidate_manifest._validate_candidate_provider_oci_binding(
                    candidate, candidate_root=root
                )

            rehearsal_missing_marker = {
                key: value for key, value in oci.items() if key != "nonPromotable"
            }
            oci_path.write_text(json.dumps(rehearsal_missing_marker), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OCI manifest fields mismatch"):
                candidate_manifest._validate_candidate_provider_oci_binding(
                    candidate, candidate_root=root
                )


class RehearsalRenderSafetyContractTest(unittest.TestCase):
    """SIT-003：渲染身份、未实现依赖、插值和隔离发布口均在启动前裁定。"""

    def test_startup_includes_api_edge_but_blocks_unavailable_prod_otp(self) -> None:
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib import data_plane_wiring as wiring
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.package_inputs import _prevalidation_spec

        spec = _prevalidation_spec()
        service = spec["planes"]["service"]
        self.assertIn("api-edge", service["startupServices"])
        self.assertIn("integration-service", service["imageAndConfigOnlyServices"])
        with self.assertRaisesRegex(SystemExit, "user-service startup dependency unavailable: integration-service"):
            wiring._validate_prevalidation_startup(set(service["startupServices"]) | {"gamma-proxy"})
        wiring._validate_prevalidation_startup({"rtc-service", "realtime-gateway"})
        self.assertEqual(spec["resourceLimits"]["services"]["object-storage"]["memLimit"], "384m")

    def test_ports_are_manifest_owned_and_always_loopback_in_both_syntaxes(self) -> None:
        from quwoquan_ops.cli.prod import render_prod_plane_stack as render
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib import data_plane_wiring as wiring

        bindings = wiring._prevalidation_port_bindings()
        ports = {item["published"] for item in bindings}
        self.assertTrue({39260, 39280, 39300} <= ports)
        self.assertTrue({39010, 39100, 39310}.isdisjoint(ports))
        for raw in ("0.0.0.0:19210:18081", "[::]:19210:18081", "${QWQ_COMPOSE_USER_PORT:-19210}:18081"):
            self.assertEqual(render._prevalidation_published_ports("user-service", [raw]), ["127.0.0.1:39210:18081"])
        self.assertEqual(
            render._prevalidation_published_ports("user-service", [{"target": 18081, "published": "19210", "host_ip": "0.0.0.0"}]),
            [{"target": 18081, "published": "39210", "host_ip": "127.0.0.1", "protocol": "tcp"}],
        )
        self.assertEqual(render._prevalidation_published_ports("integration-service", ["39310:18086"]), [])
        for raw in ("19210:19999", "19210:18081/udp"):
            with self.assertRaisesRegex(SystemExit, "undeclared"):
                render._prevalidation_published_ports("user-service", [raw])
        with self.assertRaisesRegex(SystemExit, "no listener mapping"):
            render._prevalidation_published_ports("user-service", [])
        changed = [{**item, "published": 39910} if item["service"] == "user-service" else item for item in bindings]
        with mock.patch.object(render, "_prevalidation_port_bindings", return_value=changed):
            self.assertEqual(render._prevalidation_published_ports("user-service", ["19210:18081"]), ["127.0.0.1:39910:18081"])

    def test_urls_and_networks_respect_plane_instance_and_replica(self) -> None:
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib import data_plane_wiring as wiring

        self.assertEqual(
            wiring._rewrite_prevalidation_urls({"USER_SERVICE_BASE_URL": "http://user-service:18081/path?a=1"}, {"rtc-service"}),
            {"USER_SERVICE_BASE_URL": "http://host.containers.internal:39210/path?a=1"},
        )
        self.assertEqual(wiring._rewrite_prevalidation_urls("http://realtime-gateway:18090", {"notification-service"}), "http://host.containers.internal:39340")
        self.assertEqual(wiring._rewrite_prevalidation_urls("http://user-service:18082", {"user-service"}), "http://user-service:18081")
        names = {wiring._runtime_network_name(plane, instance, replica)
                 for plane in ("edge", "service") for instance in ("prod", "gray", "prevalidate") for replica in ("r0", "r1")}
        self.assertEqual(len(names), 12)

    def test_config_projection_disables_formal_rollout_and_rewrites_edge_upstreams(self) -> None:
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.package_inputs import _project_isolated_prevalidation_config

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api-edge.yaml"
            path.write_text(yaml.safe_dump({
                "config": {"version": "old"},
                "redis": {"admission": {"mode": "cluster", "addrs": ["prod-redis:6379"], "tls": True, "password": "API_EDGE_REDIS_PASSWORD"}},
                "rollout": {"enabled": True, "policy_file": "prod.yaml", "allocation_key": "formal-key"},
                "candidate_upstreams": {"user": "http://host.containers.internal:29210"},
                "upstreams": {"realtime": "http://realtime-gateway:18090", "user": "http://user-service:18081"},
            }))
            result = _project_isolated_prevalidation_config(path, selected={"api-edge", "user-service", "redis"})
            projected = yaml.safe_load(path.read_text())
        self.assertFalse(projected["rollout"]["enabled"])
        self.assertEqual(projected["candidate_upstreams"], {})
        self.assertEqual(projected["redis"]["admission"], {"mode": "standalone", "addr": "redis:6379", "tls": False, "password": ""})
        self.assertEqual(projected["upstreams"]["realtime"], "http://host.containers.internal:39340")
        self.assertEqual(projected["config"]["version"], result["projectedConfigurationDigest"])

    def test_config_tree_copies_api_edge_registry_and_schema_without_touching_package(self) -> None:
        from quwoquan_ops.cli.prod import render_prod_plane_stack as render

        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "package"
            config = package / "config"
            config.mkdir(parents=True)
            (config / "config.yaml").write_text(yaml.safe_dump({"config": {"version": "source-version"}, "graphql_read": {"enabled": True, "registry_file": "graphql-read-registry.json", "schema_file": "graphql-read-schema.graphqls"}}))
            (config / "graphql-read-registry.json").write_text('{"signed":"registry"}')
            (config / "graphql-read-schema.graphqls").write_text("type Query { health: String }")
            (package / "provenance.json").write_text(json.dumps({"configVersion": "source-version"}))
            output = Path(tmp) / "render"
            with (
                mock.patch.object(render, "service_deployment_package_dir", return_value=package),
                mock.patch.object(render, "_verified_package_config", return_value=config / "config.yaml"),
                mock.patch.object(render, "_write_artifact_identity_and_platform_ops_facts", return_value={}),
            ):
                render._write_config_tree(config_services=["api-edge"], candidate_digest=CANDIDATE, output_root=output)
                for filename in ("graphql-read-registry.json", "graphql-read-schema.graphqls"):
                    self.assertEqual((output / "runtime/config-root" / filename).read_bytes(), (config / filename).read_bytes())
                (config / "graphql-read-schema.graphqls").unlink()
                with self.assertRaisesRegex(SystemExit, "missing api-edge package schema_file"):
                    render._write_config_tree(config_services=["api-edge"], candidate_digest=CANDIDATE, output_root=output)

    def test_full_compose_interpolation_checks_inactive_services_and_mounts(self) -> None:
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.package_inputs import _validate_prevalidation_interpolation

        payload = {"services": {"image-only": {
            "image": "${IMAGE:?required}", "volumes": ["${MTLS:?required}:/secret:ro"],
            "command": ["echo $$SHELL_VAR ${OPTIONAL:-default} $TOKEN"],
            "healthcheck": {"test": ["${PROBE?required}"]},
        }}}
        with self.assertRaisesRegex(SystemExit, "MTLS, PROBE, TOKEN"):
            _validate_prevalidation_interpolation(payload, {"IMAGE": "pinned"})
        _validate_prevalidation_interpolation(payload, {"IMAGE": "pinned", "MTLS": "valid", "TOKEN": "valid", "PROBE": "valid"})
        with self.assertRaisesRegex(SystemExit, "IMAGE"):
            _validate_prevalidation_interpolation({"image": "${IMAGE:?required}"}, {"IMAGE": ""})

    def test_real_compose_projection_interpolation_and_native_edge_connections(self) -> None:
        from quwoquan_ops.cli.prod import render_prod_plane_stack as render
        from quwoquan_ops.cli.lib.compose_layout import domain_service_compose_files
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.package_inputs import _validate_prevalidation_interpolation

        root = render.ROOT
        source = yaml.safe_load((root / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml").read_text())["services"]
        for fragment in domain_service_compose_files(root) + [root / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml", root / "quwoquan_service/services/product-ops-service/deploy/local-elasticsearch.compose.yaml"]:
            for name, spec in yaml.safe_load(fragment.read_text())["services"].items():
                source[name] = {**source.get(name, {}), **spec}
        prevalidation = render._prevalidation_spec()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            with (
                mock.patch.object(render, "_prevalidation_secret_environment", return_value={key: "test-secret" for key in render.PREVALIDATION_AUTH_SECRET_KEYS}),
                mock.patch("quwoquan_ops.cli.lib.local_assistant_skill_package_keys.prepare_rehearsal_assistant_skill_package_keys", return_value=mock.Mock(public_keys_json='{"test":"key"}')),
            ):
                render._write_env_file(output, CANDIDATE, "candidate-tag", "prevalidate")
            self.assertFalse((output / "runtime/integration-mtls").exists())
            environment = dict(line.split("=", 1) for line in (output / "stack.env").read_text().splitlines())
            for plane in ("edge", "service"):
                selected = set(prevalidation["planes"][plane]["startupServices"])
                selected.update(prevalidation["planes"][plane]["imageAndConfigOnlyServices"])
                if plane == "service":
                    selected.update(prevalidation["isolatedData"]["services"])
                    selected.add("gamma-proxy")
                projected = {}
                for name in selected:
                    projected[name] = render._rewrite_service(
                        name, source[name], selected, image_version="candidate-tag", config_version=_sha(name),
                        versioned_image=name not in prevalidation["isolatedData"]["services"] and name != "gamma-proxy",
                        instance="prevalidate", replica_id="r0", config_root="runtime/config-root", media_root="/state/media",
                        legal_root="runtime/legal", portal_root="runtime/portal", web_root="runtime/web", caddyfile_path="runtime/Caddyfile",
                        model_cache_root="runtime/cache", data_mode="isolated", startup_services=selected,
                        prevalidation_images=prevalidation["isolatedData"]["images"],
                    )
                    projected[name]["networks"] = ["service-plane"]
                expected_ports = {
                    f"127.0.0.1:{binding['published']}:{binding['target']}"
                    for binding in prevalidation["planes"][plane]["publishedPorts"]
                    if binding["service"] in selected
                }
                self.assertEqual(
                    {port for spec in projected.values() for port in spec.get("ports", [])},
                    expected_ports,
                )
                for name, spec in projected.items():
                    self.assertNotEqual(spec.get("network_mode"), "host", name)
                    self.assertFalse(any("host.containers.internal" in item for item in spec.get("extra_hosts", [])), name)
                if plane == "edge":
                    _validate_prevalidation_interpolation({"services": projected}, environment)
                    rtc = projected["rtc-service"]
                    self.assertEqual(rtc["environment"]["USER_SERVICE_BASE_URL"], "http://host.containers.internal:39210")
                    self.assertEqual(rtc["environment"]["RTC_MONGO_URI"], "mongodb://host.containers.internal:39410/?directConnection=true")
                    self.assertNotIn("extra_hosts", rtc)
                else:
                    support = set(prevalidation["isolatedData"]["services"]) | {"gamma-proxy"}
                    initializers = {"mongo-init", "object-storage-init"}
                    for name in support - initializers:
                        healthcheck = projected[name].get("healthcheck") or {}
                        self.assertFalse(healthcheck.get("disable"), name)
                        self.assertIn((healthcheck.get("test") or [None])[0], {"CMD", "CMD-SHELL"}, name)
                        for field in ("interval", "timeout", "retries"):
                            self.assertTrue(healthcheck.get(field), f"{name}.{field}")
                    for name in initializers:
                        self.assertEqual(projected[name]["labels"]["com.quwoquan.runtime.one-shot"], "true")
                        self.assertEqual(projected[name]["restart"], "no")
                    self.assertEqual(
                        projected["object-storage"]["healthcheck"]["test"],
                        ["CMD", "curl", "-f", "-s", "--connect-timeout", "2", "--max-time", "4", "http://127.0.0.1:9000/minio/health/cluster"],
                    )
                    self.assertEqual(projected["object-storage-init"]["depends_on"]["object-storage"], {"condition": "service_healthy"})
                    self.assertIn("api-edge", projected["gamma-proxy"]["depends_on"])
                    self.assertEqual(projected["integration-service"]["ports"], [])
                    with self.assertRaisesRegex(SystemExit, "INTEGRATION_SERVICE_MTLS"):
                        _validate_prevalidation_interpolation({"services": projected}, environment)
                    projected.pop("user-service")
                    _validate_prevalidation_interpolation({"services": projected}, environment)

    def test_systemd_prevalidates_full_compose_and_bounds_start_stop(self) -> None:
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.runtime_outputs import _write_runtime_systemd_unit

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = _write_runtime_systemd_unit(root, plane={"credentialsPath": "/credentials"}, plane_name="edge", instance="prevalidate", replica_id="r0", remote_root="/stack/instances/prevalidate/r0", startup_services=["rtc-service", "realtime-gateway"])
            unit = (root / "systemd" / name).read_text()
            self.assertIn("TimeoutStartSec=300", unit)
            self.assertIn("TimeoutStopSec=120", unit)
            self.assertIn("config --quiet", unit)
            self.assertLess(unit.index("ExecStartPre="), unit.index("ExecStart="))
            self.assertNotIn("EnvironmentFile=", unit)
            with self.assertRaisesRegex(SystemExit, "integration-service"):
                _write_runtime_systemd_unit(root, plane={"credentialsPath": "/credentials"}, plane_name="service", instance="prevalidate", replica_id="r0", remote_root="/stack", startup_services=["api-edge", "user-service"])

    def test_sync_materializes_only_owned_persistent_media_and_refuses_symlinks(self) -> None:
        from quwoquan_ops.cli.prod.render_prod_plane_stack_lib import volume_layout

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            base = root / "stack"
            remote = base / "instances/prevalidate/r0"
            media = base / "state/prevalidate/r0/process/volumes/media"
            plane = {"composeProjectRoot": str(base), "rootlessRuntimeLayout": {"mediaStateRef": "process/volumes/media"}}
            (root / "provenance.json").write_text(json.dumps({"plane": "service", "instance": "prevalidate", "replicaId": "r0", "remoteRoot": str(remote), "mediaRoot": str(media)}))
            with mock.patch("quwoquan_ops.cli.prod.render_prod_plane_stack_lib.package_inputs._plane_spec", return_value=plane):
                command = volume_layout._persistent_media_sync_command(root, "service", str(remote))
                completed = subprocess.run(shlex.split(command), capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(media.stat().st_mode & 0o777, 0o750)
                self.assertEqual(media.stat().st_uid, root.stat().st_uid)
                media.rmdir()
                media.symlink_to(root, target_is_directory=True)
                refused = subprocess.run(shlex.split(command), capture_output=True, text=True)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("symlink", refused.stderr)
                with self.assertRaisesRegex(SystemExit, "identity mismatch"):
                    volume_layout._persistent_media_sync_command(root, "service", "/other")


if __name__ == "__main__":
    unittest.main()

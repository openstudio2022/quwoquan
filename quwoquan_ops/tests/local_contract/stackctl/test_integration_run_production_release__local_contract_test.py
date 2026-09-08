# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004
#
# integrate 的 Data release 输入按 DEC-041 单一 production 类别：attestation 只接受
# releaseClass=productLifecycleState=production；进入环境只经现役 `qwq-data ship`
# 的 handoff-ref 准入（apply → activate → verify --readiness-phase production），
# 不再以 release id 隐式选择、也不接受 research/commercial。

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import integration_run  # noqa: E402
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    RELEASE_INPUT_CLASSIFICATIONS,
    release_input_classification,
)

VALID_REF = "handoff-ref-v1:sha256:" + "a" * 64 + ":sha256:" + "b" * 64


def _attestation(root: Path, release_id: str, release_class: str) -> Path:
    payload = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "releaseClass": release_class,
        "productLifecycleState": release_class,
        "payloadSha256": "sha256:" + "c" * 64,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    local = root / "data/releases" / release_id / "attestations/release.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(encoded)
    given = root / f"{release_id}.json"
    given.write_bytes(encoded)
    return given


class IntegrationRunProductionReleaseContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="qwq-integrate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        patcher = mock.patch.object(integration_run, "OUTPUT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_release_id_accepts_only_production_attestations(self) -> None:
        production = _attestation(self.root, "rel-production", "production")
        self.assertEqual(integration_run._release_id(production), ("rel-production", "production"))
        for retired in ("research", "commercial"):
            with self.subTest(retired=retired), self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._release_id(_attestation(self.root, f"rel-{retired}", retired))
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.INPUT_INVALID")
            self.assertIn("production", blocked.exception.detail)

    def test_handoff_ref_must_be_canonical_v1(self) -> None:
        self.assertEqual(integration_run._handoff_ref(VALID_REF, label="--release-handoff-ref"), VALID_REF)
        for bad in ("", "rel-production", "handoff-ref-v1:sha256:abc", "sha256:" + "a" * 64):
            with self.subTest(bad=bad), self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._handoff_ref(bad, label="--release-handoff-ref")
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_apply_data_release_drives_current_ship_cli_with_handoff_ref(self) -> None:
        attestation = _attestation(self.root, "rel-production", "production")
        calls: list[tuple[str, ...]] = []

        def fake_ship(*args: str, log_dir: Path, label: str) -> None:
            calls.append(tuple(args))
            if args[0] == "verify":
                readiness = self.root / "env/alpha/runs/data-release/rel-production/run-1-verify/release-readiness.json"
                readiness.parent.mkdir(parents=True, exist_ok=True)
                readiness.write_text("{}", encoding="utf-8")

        def fake_bootstrap(**kwargs: object) -> None:
            calls.append(("premium-pool", str(kwargs["environment"]), str(kwargs["import_run"])))

        args = SimpleNamespace(release_attestation=attestation, release_handoff_ref=VALID_REF)
        with (
            mock.patch.object(integration_run, "_data_ship", side_effect=fake_ship),
            mock.patch.object(integration_run, "_bootstrap_premium_pool", side_effect=fake_bootstrap),
        ):
            readiness = integration_run._apply_data_release(
                environment="alpha", run_id="run-1", args=args, log_dir=self.root / "logs", previous_readiness=None,
            )
        self.assertTrue(readiness.is_file())
        # 精选池首次激活夹在 activate 与 verify 之间：verify 的 premium_stream 判据依赖它
        self.assertEqual([call[0] for call in calls], ["apply", "activate", "premium-pool", "verify"])
        self.assertEqual(calls[2], ("premium-pool", "alpha", "run-1-import"))
        calls = [call for call in calls if call[0] != "premium-pool"]
        for call in calls:
            self.assertIn("--handoff-ref", call)
            self.assertIn(VALID_REF, call)
            self.assertNotIn("--release-id", call)
        self.assertIn("--full-sync", calls[0])
        self.assertIn("--import", calls[0])
        verify = calls[2]
        self.assertEqual(verify[verify.index("--readiness-phase") + 1], "production")
        # verify 的前驱是 completed 的 activate run，而不是 prepared 的 apply run
        self.assertEqual(verify[verify.index("--import-run-id") + 1], "run-1-activate")
        activate = calls[1]
        self.assertEqual(activate[activate.index("--import-run-id") + 1], "run-1-import")

    def test_premium_pool_bootstrap_resolves_sample_video_to_environment_post_id(self) -> None:
        attestation = _attestation(self.root, "rel-production", "production")
        report = self.root / "env/alpha/runs/data-release/rel-production/run-1-import/import.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({
            "manifestDigest": "sha256:" + "a" * 64,
            "postBindings": [
                {"contentType": "article", "contentId": "qwq_data_" + "2" * 24, "postId": "data_post_" + "e" * 64},
                {"contentType": "video", "contentId": "qwq_data_" + "1" * 24, "postId": "data_post_" + "d" * 64},
            ],
        }), encoding="utf-8")
        plan = {"samples": [{"carrier": "video", "objectId": "qwq_data_" + "1" * 24}]}
        seen: list[tuple[str, ...]] = []

        def fake_stackctl(*args: str, log_dir: Path, env=None):
            seen.append(args)
            return integration_run.StackctlResult(" ".join(args), {"exitCode": 0}, "")

        with (
            mock.patch("quwoquan_ops.cli.lib.app_content_uat_plan.load_release_uat_sample_plan", return_value=(plan, "ref", "sha256:" + "f" * 64)),
            mock.patch.object(integration_run, "_stackctl", side_effect=fake_stackctl),
        ):
            (attestation.parent.parent / "payload").mkdir(parents=True, exist_ok=True)
            (attestation.parent.parent / "payload/release.json").write_text("{}", encoding="utf-8")
            integration_run._bootstrap_premium_pool(
                environment="alpha", release_id="rel-production", import_run="run-1-import",
                attestation=attestation, log_dir=self.root / "logs",
            )
        self.assertEqual(len(seen), 1)
        call = seen[0]
        self.assertEqual(call[:2], ("premium-pool", "--target"))
        self.assertEqual(call[call.index("--launch-policy") + 1], "release-import")
        # 传给 stackctl 的是绑定到样本的环境 postId，而不是 canonical objectId
        self.assertEqual(call[call.index("--content-id") + 1], "data_post_" + "d" * 64)
        self.assertEqual(call[call.index("--readiness-receipt") + 1], str(report))

    def test_package_identity_accepts_reused_candidate_only_from_an_ancestor(self) -> None:
        # 候选身份内容寻址：data-only 候选复用祖先 commit 打出的同一不可变候选是合法的；
        # 非复用或非祖先的 sourceRevision 仍是身份漂移。
        reused = integration_run.StackctlResult("package", {"exitCode": 0, "summary": "stackctl package reused immutable candidate for alpha"}, "")
        fresh = integration_run.StackctlResult("package", {"exitCode": 0, "summary": "stackctl package built candidate for alpha"}, "")
        head = integration_run._git("rev-parse", "HEAD")
        parent = integration_run._git("rev-parse", "HEAD~1")
        integration_run._assert_package_identity(packaged_revision=head, candidate_commit=head, package=fresh)
        integration_run._assert_package_identity(packaged_revision=parent, candidate_commit=head, package=reused)
        for packaged, package in ((parent, fresh), ("0" * 40, reused)):
            with self.subTest(packaged=packaged[:9], summary=package.payload["summary"]):
                with self.assertRaises(integration_run.IntegrationRunError) as blocked:
                    integration_run._assert_package_identity(packaged_revision=packaged, candidate_commit=head, package=package)
                self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.PACKAGE_IDENTITY_INVALID")

    def test_parser_requires_candidate_handoff_ref_only(self) -> None:
        # integrate 只对 candidate 执行 ship apply/activate/verify；rollback release 只参与
        # stackctl package 的候选绑定，因此不需要 rollback handoff-ref。
        parser = integration_run._parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--release-attestation", "a", "--rollback-release-attestation", "b"])
        parsed = parser.parse_args([
            "--release-attestation", "a", "--rollback-release-attestation", "b",
            "--release-handoff-ref", VALID_REF,
        ])
        self.assertEqual(parsed.release_handoff_ref, VALID_REF)
        self.assertFalse(hasattr(parsed, "rollback_handoff_ref"))
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("RELEASE_HANDOFF_REF", makefile)
        self.assertNotIn("ROLLBACK_HANDOFF_REF", makefile)
        self.assertIn('--release-handoff-ref "$(RELEASE_HANDOFF_REF)"', makefile)

    def test_acceptance_mode_is_lane_side_and_never_publishes(self) -> None:
        # Alpha/Beta 只能在产出 handoff 的 lane 工作树完成（ship admission 重算当前工作树的
        # candidate evidence）；integration 工作区只承担 admit/publish 与 gamma/prod。
        parser = integration_run._parser()
        base = ["--release-attestation", "a", "--rollback-release-attestation", "b", "--release-handoff-ref", VALID_REF]
        self.assertEqual(parser.parse_args(base).mode, "integrate")
        parsed = parser.parse_args([*base, "--mode", "acceptance", "--baseline", "abc123"])
        self.assertEqual((parsed.mode, parsed.baseline), ("acceptance", "abc123"))
        with self.assertRaises(SystemExit):
            parser.parse_args([*base, "--mode", "gamma"])
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("\naccept:\n", makefile)
        self.assertIn("--mode acceptance", makefile)
        self.assertIn("--baseline %s", makefile)
        accept_block = makefile.split("\naccept:\n", 1)[1].split("\n.PHONY", 1)[0]
        self.assertNotIn("--publish", accept_block)

    def test_acceptance_mode_rejects_publish_and_integrate_rejects_baseline(self) -> None:
        production = _attestation(self.root, "rel-candidate", "production")
        rollback = _attestation(self.root, "rel-rollback", "production")
        base = ["--release-attestation", str(production), "--rollback-release-attestation", str(rollback),
                "--release-handoff-ref", VALID_REF]
        with mock.patch.object(integration_run, "RUNS_ROOT", self.root / "runs"), \
                mock.patch.object(integration_run, "ed25519_signer", return_value=object()), \
                mock.patch.object(integration_run, "load_keyring", return_value={}), \
                mock.patch.object(integration_run, "key_root", return_value=self.root):
            for run_id, argv in (
                ("acceptance-publish", [*base, "--mode", "acceptance", "--publish"]),
                ("integrate-baseline", [*base, "--mode", "integrate", "--baseline", "abc123"]),
            ):
                with self.subTest(run_id=run_id):
                    self.assertEqual(integration_run.main([*argv, "--run-id", run_id]), 1)
                    payload = json.loads((self.root / "runs" / run_id / "summary.json").read_text(encoding="utf-8"))
                    self.assertEqual(payload["terminal"], "GATE_BLOCK")
                    self.assertEqual(payload["blocker"]["code"], "INTEGRATION_RUN.INPUT_INVALID")

    def test_acceptance_readiness_identity_is_the_lane_branch_itself(self) -> None:
        # readiness 的 push identity 要求 local ref 精确解析到 candidate：integrate 用 refs/heads/dev1.0，
        # acceptance 用 lane 自己的 branch ref，且必须是当前分支的 head；detached/非 lane/漂移一律拒绝。
        commit = "1" * 40
        integrate = SimpleNamespace(mode="integrate")
        self.assertEqual(integration_run._readiness_local_ref(args=integrate, commit=commit), "refs/heads/dev1.0")
        acceptance = SimpleNamespace(mode="acceptance")
        with mock.patch.object(integration_run, "_git", side_effect=lambda *a: {"symbolic-ref": "refs/heads/lane/product-mainline", "rev-parse": commit}[a[0]]):
            self.assertEqual(integration_run._readiness_local_ref(args=acceptance, commit=commit), "refs/heads/lane/product-mainline")
        for branch, head in (("refs/heads/dev1.0", commit), ("", commit), ("refs/heads/lane/product-mainline", "2" * 40)):
            with self.subTest(branch=branch, head=head[:4]), \
                    mock.patch.object(integration_run, "_git", side_effect=lambda *a, b=branch, h=head: {"symbolic-ref": b, "rev-parse": h}[a[0]]), \
                    self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._readiness_local_ref(args=acceptance, commit=commit)
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.LANE_IDENTITY_INVALID")

    def test_production_pair_classifies_as_production_inputs(self) -> None:
        def binding(release_class: str) -> dict[str, str]:
            return {
                "releaseId": f"rel-{release_class}", "releaseDigest": "sha256:" + "1" * 64,
                "attestationRef": "x", "attestationDigest": "sha256:" + "2" * 64,
                "releaseClass": release_class, "productLifecycleState": release_class,
            }

        self.assertIn("production_inputs", RELEASE_INPUT_CLASSIFICATIONS)
        self.assertEqual(
            release_input_classification({"candidate": binding("production"), "rollback": binding("production")}),
            "production_inputs",
        )
        self.assertEqual(
            release_input_classification({"candidate": binding("production"), "rollback": binding("research")}),
            "mixed_inputs",
        )


if __name__ == "__main__":
    unittest.main()

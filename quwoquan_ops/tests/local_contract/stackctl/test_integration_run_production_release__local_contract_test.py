# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t6
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t7
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t8
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t9
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t10
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t11
#
# lane 验收（`--mode acceptance`）按 DEC-041 消费无类别 Data attestation；
# 进入环境只经现役 `qwq-data ship` 的 handoff-ref 准入（apply → activate → verify），
# 不以 release id 隐式选择，也不保留类别字段或选择器。Beta 显式 opt-in；accepted 终态
# 产出 acceptance bundle；integrate（integration 工作区）只消费 bundle 做 admit/publish（DEC-014）。

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import integration_run  # noqa: E402
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (  # noqa: E402
    release_attestation_payload,
)

VALID_REF = "handoff-ref-v1:sha256:" + "a" * 64 + ":sha256:" + "b" * 64


def _attestation(root: Path, release_id: str) -> Path:
    payload = release_attestation_payload(release_id, "sha256:" + "c" * 64)
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

    def test_release_id_accepts_no_category_and_rejects_retired_fields(self) -> None:
        attestation = _attestation(self.root, "rel-candidate")
        self.assertEqual(integration_run._release_id(attestation), "rel-candidate")
        canonical = json.loads(attestation.read_text(encoding="utf-8"))
        for field in ("releaseClass", "productLifecycleState", "releaseInputClassification", "unexpectedField"):
            attestation.write_text(json.dumps({**canonical, field: "production"}), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._release_id(attestation)
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_handoff_ref_must_be_canonical_v1(self) -> None:
        self.assertEqual(integration_run._handoff_ref(VALID_REF, label="--release-handoff-ref"), VALID_REF)
        for bad in ("", "rel-production", "handoff-ref-v1:sha256:abc", "sha256:" + "a" * 64):
            with self.subTest(bad=bad), self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._handoff_ref(bad, label="--release-handoff-ref")
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_apply_data_release_drives_current_ship_cli_with_handoff_ref(self) -> None:
        attestation = _attestation(self.root, "rel-production")
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
        self.assertNotIn("--readiness-phase", verify)
        # verify 的前驱是 completed 的 activate run，而不是 prepared 的 apply run
        self.assertEqual(verify[verify.index("--import-run-id") + 1], "run-1-activate")
        activate = calls[1]
        self.assertEqual(activate[activate.index("--import-run-id") + 1], "run-1-import")

    def test_premium_pool_bootstrap_resolves_sample_video_to_environment_post_id(self) -> None:
        attestation = _attestation(self.root, "rel-production")
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

    def test_release_inputs_belong_to_acceptance_and_need_candidate_handoff_ref_only(self) -> None:
        # Data release 输入（两份 attestation + candidate handoff-ref）只属于 acceptance；rollback release 只参与
        # stackctl package 的候选绑定，因此不需要 rollback handoff-ref。parser 不再在 integrate 上强制它们。
        parser = integration_run._parser()
        parsed = parser.parse_args(["--mode", "integrate", "--acceptance-bundle", "/tmp/bundle"])
        self.assertIsNone(parsed.release_attestation)
        self.assertEqual(parsed.release_handoff_ref, "")
        self.assertFalse(hasattr(parsed, "rollback_handoff_ref"))
        production = _attestation(self.root, "rel-candidate")
        rollback = _attestation(self.root, "rel-rollback")
        with self._runtime_patches():
            for run_id, argv in (
                ("acceptance-no-handoff", ["--mode", "acceptance", "--release-attestation", str(production),
                                           "--rollback-release-attestation", str(rollback)]),
                ("acceptance-no-attestation", ["--mode", "acceptance", "--release-handoff-ref", VALID_REF]),
            ):
                with self.subTest(run_id=run_id):
                    self.assertEqual(self._blocker(run_id, argv), "INTEGRATION_RUN.INPUT_INVALID")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("RELEASE_HANDOFF_REF", makefile)
        self.assertNotIn("ROLLBACK_HANDOFF_REF", makefile)
        accept_block = makefile.split("\naccept:\n", 1)[1].split("\n.PHONY", 1)[0]
        self.assertIn('--release-handoff-ref "$(RELEASE_HANDOFF_REF)"', accept_block)

    def _runtime_patches(self) -> ExitStack:
        exit_stack = ExitStack()
        for patcher in (
            mock.patch.object(integration_run, "RUNS_ROOT", self.root / "runs"),
            mock.patch.object(integration_run, "ed25519_signer", return_value=object()),
            mock.patch.object(integration_run, "load_keyring", return_value={}),
            mock.patch.object(integration_run, "key_root", return_value=self.root),
        ):
            exit_stack.enter_context(patcher)
        return exit_stack

    def _blocker(self, run_id: str, argv: list[str]) -> str:
        self.assertEqual(integration_run.main([*argv, "--run-id", run_id]), 1)
        payload = json.loads((self.root / "runs" / run_id / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["terminal"], "GATE_BLOCK")
        return payload["blocker"]["code"]

    def test_acceptance_mode_is_lane_side_and_never_publishes(self) -> None:
        # Alpha（可选 Beta）只能在产出 handoff 的 lane 工作树完成（ship admission 重算当前工作树的
        # candidate evidence）；integration 工作区只消费 bundle 做 admit/publish 与 gamma/prod。
        parser = integration_run._parser()
        base = ["--release-attestation", "a", "--rollback-release-attestation", "b", "--release-handoff-ref", VALID_REF]
        self.assertEqual(parser.parse_args([]).mode, "integrate")
        parsed = parser.parse_args([*base, "--mode", "acceptance", "--baseline", "abc123", "--beta",
                                    "--merged-lanes", "lane/ops", "--merged-lanes", "lane/engineering"])
        self.assertEqual((parsed.mode, parsed.baseline, parsed.beta), ("acceptance", "abc123", True))
        self.assertEqual(parsed.merged_lanes, ["lane/ops", "lane/engineering"])
        self.assertFalse(parser.parse_args([*base, "--mode", "acceptance"]).beta)
        with self.assertRaises(SystemExit):
            parser.parse_args([*base, "--mode", "gamma"])
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("\naccept:\n", makefile)
        accept_block = makefile.split("\naccept:\n", 1)[1].split("\n.PHONY", 1)[0]
        self.assertIn("--mode acceptance", accept_block)
        self.assertIn("--baseline %s", accept_block)
        self.assertIn("'--beta'", accept_block)
        self.assertIn("MERGED_LANES", accept_block)
        self.assertNotIn("--publish", accept_block)

    def test_integrate_consumes_bundle_only_and_rejects_acceptance_inputs(self) -> None:
        # integrate 不签发、不跑环境：必须给 --acceptance-bundle，任何 acceptance 专用输入都是 INPUT_INVALID；
        # acceptance 反之不得携带 bundle 或 --publish。
        production = _attestation(self.root, "rel-candidate")
        rollback = _attestation(self.root, "rel-rollback")
        acceptance = ["--mode", "acceptance", "--release-attestation", str(production),
                      "--rollback-release-attestation", str(rollback), "--release-handoff-ref", VALID_REF]
        with self._runtime_patches():
            self.assertEqual(self._blocker("integrate-no-bundle", ["--mode", "integrate"]), "INTEGRATION_RUN.ACCEPTANCE_REQUIRED")
            for run_id, argv in (
                ("acceptance-publish", [*acceptance, "--publish"]),
                ("acceptance-bundle", [*acceptance, "--acceptance-bundle", str(self.root)]),
                ("integrate-baseline", ["--mode", "integrate", "--acceptance-bundle", str(self.root), "--baseline", "abc123"]),
                ("integrate-beta", ["--mode", "integrate", "--acceptance-bundle", str(self.root), "--beta"]),
                ("integrate-attestation", ["--mode", "integrate", "--acceptance-bundle", str(self.root), "--release-attestation", str(production)]),
                ("integrate-handoff", ["--mode", "integrate", "--acceptance-bundle", str(self.root), "--release-handoff-ref", VALID_REF]),
            ):
                with self.subTest(run_id=run_id):
                    self.assertEqual(self._blocker(run_id, argv), "INTEGRATION_RUN.INPUT_INVALID")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        integrate_block = makefile.split("\nintegrate:\n", 1)[1].split("\n.PHONY", 1)[0]
        self.assertIn("ACCEPTANCE_BUNDLE", integrate_block)
        self.assertIn('--acceptance-bundle "$(ACCEPTANCE_BUNDLE)"', integrate_block)
        self.assertIn("--mode integrate", integrate_block)
        for retired in ("--release-attestation", "--release-handoff-ref", "--readiness-level", "--owner-identity"):
            self.assertNotIn(retired, integrate_block)

    def test_beta_policy_branch_is_independent_of_impact_depth(self) -> None:
        # 从 main 执行实际分流；环境/签发是测试替身，不把本合同当成 runtime 验收。
        commit, tree, parent = "1" * 40, "2" * 40, "0" * 40
        store, refs = self._fake_store("policy-store", commit=commit, tree=tree, parent=parent)
        release, rollback = _attestation(self.root, "rel-a"), _attestation(self.root, "rel-b")
        plan_path = self.root / "plan.json"
        plan_path.write_text("{}", encoding="utf-8")
        answers = {("status",): "", ("rev-parse", "HEAD^{commit}"): commit,
                   ("rev-parse", "HEAD"): commit, ("ls-remote",): f"{parent}\trefs/heads/dev1.0", ("show",): tree}

        def fake_git(*args):
            return next(value for key, value in answers.items() if args[:len(key)] == key)

        def run_environment(**kwargs):
            kwargs["summary"]["environments"][kwargs["environment"]] = {"executed": True}
            return {"readiness": {}}

        for depth in ("alpha_integration", "abg_release_sensitive"):
            for opted_in in (False, True):
                with self.subTest(depth=depth, opted_in=opted_in), self._runtime_patches(), ExitStack() as patches:
                    replacements = {"_store": store, "_readiness_local_ref": "refs/heads/lane/product-mainline",
                                    "_merged_lanes": [], "_impact_plan": ({"integration_depth": depth, "plan_digest": "d", "scopes": {}}, plan_path),
                                    "_local_readiness": (self.root / "receipt.json", {}), "build_head_candidate": store / refs["candidate"]["ref"],
                                    "create_source_fact": store / refs["sourceFact"]["ref"], "_issue": refs["alphaFact"], "release_claim": None}
                    for name, result in replacements.items():
                        patches.enter_context(mock.patch.object(integration_run, name, return_value=result))
                    patches.enter_context(mock.patch.object(integration_run, "_git", side_effect=fake_git))
                    patches.enter_context(mock.patch("subprocess.run", return_value=SimpleNamespace(returncode=0)))
                    patches.enter_context(mock.patch.object(integration_run, "store_ref", return_value=refs["candidate"]))
                    run = patches.enter_context(mock.patch.object(integration_run, "_run_environment", side_effect=run_environment))
                    skip = patches.enter_context(mock.patch.object(integration_run, "_not_required_beta", return_value={}))
                    bundle = patches.enter_context(mock.patch.object(integration_run, "_write_acceptance_bundle",
                        side_effect=integration_run.IntegrationRunError("TEST.BUNDLE_REACHED", "stop before bundle")))
                    run_id = f"policy-{depth}-{opted_in}"
                    argv = ["--mode", "acceptance", "--release-attestation", str(release), "--rollback-release-attestation", str(rollback),
                            "--release-handoff-ref", VALID_REF, *(["--beta"] if opted_in else [])]
                    self.assertEqual(self._blocker(run_id, argv), "TEST.BUNDLE_REACHED")
                    self.assertEqual([call.kwargs["environment"] for call in run.call_args_list], ["alpha", "beta"] if opted_in else ["alpha"])
                    self.assertEqual(bundle.call_args.kwargs["beta_status"], "passed" if opted_in else "not_required")
                    if opted_in:
                        skip.assert_not_called()
                        self.assertIsNone(bundle.call_args.kwargs["beta_reason"])
                    else:
                        skip.assert_called_once()
                        self.assertEqual(skip.call_args.kwargs["reason_code"], integration_run.BETA_OPTIONAL_BY_POLICY)
                        self.assertEqual(bundle.call_args.kwargs["beta_reason"], integration_run.BETA_OPTIONAL_BY_POLICY)

    def test_beta_is_explicit_opt_in_with_typed_reason(self) -> None:
        # 政策跳过原因落在 EAF 与 named evidence；passed case result 不携带 reasonCode。
        # 通用签发函数仍支持 ImpactPlan 免环境原因，不等于 acceptance 的缺省分流。
        from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import (
            BETA_OPTIONAL_BY_POLICY,
            NO_LIVE_ENVIRONMENT_REQUIRED,
        )

        plan_path = self.root / "runs/r1/impact-plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text('{"integration_depth": "abg_release_sensitive"}\n', encoding="utf-8")
        store = self.root / "store"
        candidate = {"candidateId": "sha256:" + "1" * 64, "commit": "2" * 40, "tree": "3" * 40}
        with mock.patch.object(integration_run, "_store", return_value=store):
            evidence = integration_run._not_required_beta(
                candidate=candidate, impact_plan_digest="sha256:" + "4" * 64, impact_plan_path=plan_path,
                profile="integration", reason_code=BETA_OPTIONAL_BY_POLICY,
            )
            self.assertEqual(evidence["reasonCode"], BETA_OPTIONAL_BY_POLICY)
            case = json.loads((store / evidence["cases"][0]["ref"]).read_text(encoding="utf-8"))
            # canonical ReadinessCaseResult：passed 结果不得带 reasonCode；原因落在 EAF 与 named evidence
            self.assertEqual(case["status"], "passed")
            self.assertNotIn("reasonCode", case)
            runtime_identity = json.loads((store / evidence["named"]["runtime_identity"]["ref"]).read_text(encoding="utf-8"))
            self.assertEqual(runtime_identity["source"]["basis"], BETA_OPTIONAL_BY_POLICY)
            self.assertIs(runtime_identity["source"]["executed"], False)
            issued: dict[str, object] = {}

            def fake_issue(**kwargs: object) -> Path:
                issued.update(kwargs)
                fact = store / "environment-execution/acceptance/x/beta.json"
                fact.parent.mkdir(parents=True, exist_ok=True)
                fact.write_text("{}", encoding="utf-8")
                return fact

            with mock.patch.object(integration_run, "create_execution_request", return_value=store / "req.json"), \
                    mock.patch.object(integration_run, "request_exact_ref", return_value={"ref": "req.json", "digest": "sha256:" + "5" * 64}), \
                    mock.patch.object(integration_run, "append_task_state"), \
                    mock.patch.object(integration_run, "issue_environment_acceptance_fact", side_effect=fake_issue):
                args = SimpleNamespace(fact_ttl_hours=1, signer_identity="s")
                integration_run._issue(environment="beta", candidate_ref={"ref": "c", "digest": "d"}, impact_plan_digest="sha256:" + "4" * 64,
                                       evidence=evidence, status="not_required", predecessor={"ref": "a", "digest": "b"},
                                       profile="integration", args=args, signer=object())
                self.assertEqual(issued["reason_code"], BETA_OPTIONAL_BY_POLICY)
                integration_run._issue(environment="beta", candidate_ref={"ref": "c", "digest": "d"}, impact_plan_digest="sha256:" + "4" * 64,
                                       evidence={"named": evidence["named"], "cases": evidence["cases"]}, status="not_required",
                                       predecessor={"ref": "a", "digest": "b"}, profile="integration", args=args, signer=object())
                self.assertEqual(issued["reason_code"], NO_LIVE_ENVIRONMENT_REQUIRED)
                integration_run._issue(environment="alpha", candidate_ref={"ref": "c", "digest": "d"}, impact_plan_digest="sha256:" + "4" * 64,
                                       evidence=evidence, status="passed", predecessor=None, profile="integration", args=args, signer=object())
                self.assertIsNone(issued["reason_code"])

    def _fake_store(self, name: str, *, commit: str, tree: str, parent: str) -> tuple[Path, dict[str, dict[str, str]]]:
        """构造一个含 candidate/claim/source fact/Alpha+Beta EAF 及其全部 exact 证据的假 store。"""
        store = self.root / name
        digest = integration_run.exact_file_digest

        def write(ref: str, payload: dict[str, object]) -> dict[str, str]:
            path = store / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(integration_run._canonical_bytes(payload) + b"\n")
            return {"ref": ref, "digest": digest(path)}

        candidate_id = "sha256:" + "a" * 64
        claim = write("claims/c1.json", {"claimId": "sha256:" + "c" * 64, "paths": ["x.txt"]})
        candidate_body = {
            "schema": "quwoquan_ops.exact_integration_candidate.v1", "commit": commit, "tree": tree,
            "expectedParent": parent, "claimRef": claim["ref"], "claimDigest": claim["digest"], "paths": ["x.txt"],
            "impactPlanDigest": "sha256:" + "9" * 64,
        }
        candidate_id = integration_run._sha256_hex(integration_run._canonical_bytes(candidate_body))
        candidate = write("candidates/a.json", {**candidate_body, "candidateId": candidate_id})
        receipt = self.root / "env/repo/local/local-readiness/process/receipts/r1.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(b'{"status":"passed"}\n')
        source = write("source-facts/s.json", {
            "status": "passed", "candidateId": candidate_id, "commit": commit, "tree": tree,
            "candidate": candidate, "kind": "local_readiness_fast",
            "receipt": {"ref": ".qwq_output/" + receipt.relative_to(self.root).as_posix(), "digest": digest(receipt)},
        })
        facts: dict[str, dict[str, str]] = {"candidate": candidate, "claim": claim, "sourceFact": source}
        for environment in ("alpha", "beta"):
            named = {
                field: write(f"environment-evidence/{'a' * 64}/{environment}/{field}.json", {"role": field, "environment": environment})
                for field in integration_run._EAF_NAMED_FIELDS
            }
            cases = [write(f"environment-evidence/{'a' * 64}/{environment}/cases/000.json", {"caseId": f"{environment}-0"})]
            facts[f"{environment}Fact"] = write(f"environment-execution/acceptance/{'a' * 64}/{environment}.json", {
                "schema": "quwoquan_ops.environment_acceptance_fact.v2", "environment": environment,
                "status": "passed" if environment == "alpha" else "not_required",
                "profile": "integration", "nonPromotable": False, "impactPlanDigest": "sha256:" + "9" * 64,
                "predecessor": None if environment == "alpha" else facts["alphaFact"],
                **({"reasonCode": integration_run.BETA_OPTIONAL_BY_POLICY} if environment == "beta" else {}),
                "candidate": {"candidateId": candidate_id, "commit": commit, "tree": tree},
                "caseResultRefs": cases, **named, "signer": {"identity": "quwoquan-environment-ops-local", "signature": "ed25519:x"},
            })
        return store, facts

    def _bundle_from_fake_store(self, *, commit: str, tree: str, parent: str) -> tuple[Path, dict[str, dict[str, str]], Path]:
        store, facts = self._fake_store("lane-store", commit=commit, tree=tree, parent=parent)
        run_dir = self.root / "runs/acc-1"
        run_dir.mkdir(parents=True)
        plan_path = run_dir / "impact-plan.json"
        plan_path.write_text('{"integration_depth":"alpha_integration"}\n', encoding="utf-8")
        summary = {"runId": "acc-1", "impactPlan": {"digest": "sha256:" + "9" * 64, "integrationDepth": "alpha_integration"},
                   "dataReleases": ["rel-a", "rel-b"], "dataReleaseHandoffRef": VALID_REF}
        args = SimpleNamespace(signer_identity="quwoquan-environment-ops-local", profile="integration")
        with mock.patch.object(integration_run, "_store", return_value=store):
            bundle_dir = integration_run._write_acceptance_bundle(
                run_dir=run_dir, candidate_ref=facts["candidate"], source_ref=facts["sourceFact"], alpha_ref=facts["alphaFact"],
                beta_ref=facts["betaFact"], identity={"commit": commit, "parent": parent, "tree": tree, "remoteHead": parent},
                plan_path=plan_path, summary=summary, beta_status="not_required", beta_reason=integration_run.BETA_OPTIONAL_BY_POLICY,
                lane_branch="refs/heads/lane/product-mainline",
                merged_lanes=[{"branch": "refs/heads/lane/product-mainline", "commit": commit}], args=args,
            )
        return bundle_dir, facts, store

    def _signed_bundle(self):
        """仅本地合同：临时密钥真实签发，真实验签；不连接环境，不签发运行时资格。"""
        from quwoquan_ops.tests.support.evidence_signing_test_support import create_temporary_signing
        from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import _EVIDENCE_ROLE_CONTRACT

        commit, tree, parent = "1" * 40, "2" * 40, "0" * 40
        bundle, refs, store = self._bundle_from_fake_store(commit=commit, tree=tree, parent=parent)
        signing = create_temporary_signing(self.root / "test-signing")
        now = datetime.now(timezone.utc)
        issued = (now - timedelta(minutes=1)).isoformat()
        expires = (now + timedelta(hours=1)).isoformat()
        impact = "sha256:" + "9" * 64
        predecessor = None
        args = SimpleNamespace(signer_identity=integration_run.DEFAULT_SIGNER, profile="integration", fact_ttl_hours=1)
        for environment in ("alpha", "beta"):
            fact = json.loads((store / refs[f"{environment}Fact"]["ref"]).read_bytes())
            identity = fact["candidate"]
            for field, (role, statuses) in _EVIDENCE_ROLE_CONTRACT.items():
                path = store / fact[field]["ref"]
                path.write_bytes(integration_run._canonical_bytes({
                    "role": role, "status": sorted(statuses)[0], "environment": environment,
                    "profile": "integration", "impactPlanDigest": impact, **identity,
                }) + b"\n")
                fact[field]["digest"] = integration_run.exact_file_digest(path)
            case_path = store / fact["caseResultRefs"][0]["ref"]
            from quwoquan_ops.cli.lib.readiness_case_result import write_readiness_case_result
            write_readiness_case_result(case_path.with_name("signed.json"), {
                "objectId": environment, "caseId": environment,
                "specRef": "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001",
                "producer": "ops", "layer": "environment_acceptance", "status": "passed",
                "target": {"kind": "operation", "id": environment}, "commitSha": commit,
                "contractGraphSourceHash": "4" * 64, "deploymentTarget": f"{environment}-local",
                "baselineId": "contract", "packageDigest": "sha256:" + "5" * 64,
                "configurationDigest": "sha256:" + "6" * 64, "candidateManifestSha256": "7" * 64,
                "candidateDigest": identity["candidateId"], "environment": environment,
                "provider": "local-contract", "startedAt": issued, "completedAt": issued,
                "runnerIdentity": "local-contract", "artifactSha256": "8" * 64, "receiptRef": "contract/test",
            }, generated_at=issued)
            case_path = case_path.with_name("signed.json")
            case_path.write_bytes(case_path.read_bytes() + b"\n")
            case = {"ref": case_path.relative_to(store).as_posix(), "digest": integration_run.exact_file_digest(case_path)}
            request = integration_run.create_execution_request(store_root=store, candidate_ref=refs["candidate"],
                environment=environment, impact_plan_digest=impact, priority=1)
            request_ref = integration_run.request_exact_ref(store, request)
            integration_run.append_task_state(store_root=store, request_ref=request_ref, state="queued")
            if environment == "alpha":
                integration_run.append_task_state(store_root=store, request_ref=request_ref, state="mutation_started")
            named_args = dict(zip(("runtime_identity", "data_lifecycle", "provider_readiness", "observability_readiness",
                                  "inspect_evidence", "doctor_evidence", "cleanup_evidence", "lease_closure_evidence"),
                                 (fact[field] for field in integration_run._EAF_NAMED_FIELDS)))
            path = integration_run.issue_environment_acceptance_fact(store_root=store, request_ref=request_ref,
                profile="integration", status="passed" if environment == "alpha" else "not_required",
                case_result_refs=[case], predecessor=predecessor, signer_identity=args.signer_identity,
                signer=signing.signer(args.signer_identity), expires_at=expires, issued_at=issued, non_promotable=False,
                reason_code=None if environment == "alpha" else integration_run.BETA_OPTIONAL_BY_POLICY, **named_args)
            predecessor = refs[f"{environment}Fact"] = {
                "ref": path.relative_to(store).as_posix(), "digest": integration_run.exact_file_digest(path)}
        run = self.root / "runs/signed"
        with mock.patch.object(integration_run, "_store", return_value=store):
            bundle = integration_run._write_acceptance_bundle(run_dir=run, candidate_ref=refs["candidate"],
                source_ref=refs["sourceFact"], alpha_ref=refs["alphaFact"], beta_ref=refs["betaFact"],
                identity={"parent": parent, "remoteHead": parent}, plan_path=bundle.parent / "impact-plan.json",
                summary={"runId": "signed", "impactPlan": {"digest": impact}}, beta_status="not_required",
                beta_reason=integration_run.BETA_OPTIONAL_BY_POLICY, lane_branch="refs/heads/lane/product-mainline",
                merged_lanes=[{"branch": "refs/heads/lane/product-mainline", "commit": commit}], args=args)
        return bundle, refs, store, signing, args

    def test_signed_bundle_portability_and_manifest_bindings(self) -> None:
        bundle, refs, lane, signing, args = self._signed_bundle()
        commit, tree, parent = "1" * 40, "2" * 40, "0" * 40
        manifest = json.loads((bundle / "bundle.json").read_bytes())
        for attack in ("plan", "beta", "missing-member", "source-symlink", "target-symlink", "wrong-key"):
            with self.subTest(attack=attack):
                copied = self.root / attack
                shutil.copytree(bundle, copied)
                changed = json.loads((copied / "bundle.json").read_bytes())
                target = self.root / f"target-{attack}"
                keyring = signing.keyring()
                if attack == "plan":
                    (copied / "impact-plan.json").write_bytes(b"{}")
                elif attack == "beta":
                    changed["beta"] = {"status": "passed", "executed": True, "reasonCode": None}
                elif attack == "missing-member":
                    changed["storeFiles"] = [r for r in changed["storeFiles"] if r != refs["sourceFact"]]
                elif attack in ("source-symlink", "target-symlink"):
                    root = copied / "store" if attack == "source-symlink" else target
                    link = root / refs["sourceFact"]["ref"]
                    link.parent.mkdir(parents=True, exist_ok=True)
                    if link.exists():
                        link.unlink()
                    link.symlink_to(lane / refs["sourceFact"]["ref"])
                elif attack == "wrong-key":
                    from quwoquan_ops.tests.support.evidence_signing_test_support import create_temporary_signing
                    keyring = create_temporary_signing(self.root / "other-key").keyring()
                changed["bundleId"] = integration_run._sha256_hex(integration_run._canonical_bytes({k: v for k, v in changed.items() if k != "bundleId"}))
                (copied / "bundle.json").write_bytes(integration_run._canonical_bytes(changed))
                with mock.patch.object(integration_run, "_store", return_value=target), self.assertRaises(
                    (integration_run.IntegrationRunError, integration_run.EnvironmentSchedulerError)):
                    integration_run._import_acceptance_bundle(bundle_dir=copied, commit=commit, tree=tree, parent=parent, args=args, keyring=keyring)
        # lane 原始输出不存在时，bundle 仍必须包含 source receipt 的 exact bytes。
        receipt = json.loads((lane / refs["sourceFact"]["ref"]).read_bytes())["receipt"]
        self.assertIn("sourceReceipt", manifest)
        self.assertEqual(manifest["sourceReceipt"], receipt)
        receipt_bytes = (self.root / receipt["ref"].removeprefix(".qwq_output/")).read_bytes()
        self.assertEqual((bundle / "repository" / receipt["ref"]).read_bytes(), receipt_bytes)
        target = self.root / "signed-import"
        output = self.root / "integration-output"
        shutil.rmtree(lane)
        (self.root / receipt["ref"].removeprefix(".qwq_output/")).unlink()
        with mock.patch.object(integration_run, "_store", return_value=target), mock.patch.object(integration_run, "OUTPUT_ROOT", output):
            result = integration_run._import_acceptance_bundle(bundle_dir=bundle, commit=commit, tree=tree, parent=parent, args=args, keyring=signing.keyring())
            again = integration_run._import_acceptance_bundle(bundle_dir=bundle, commit=commit, tree=tree, parent=parent, args=args, keyring=signing.keyring())
        self.assertEqual(result["candidate"]["commit"], commit)
        self.assertEqual(again["importedFiles"], 0)
        self.assertEqual((output / receipt["ref"].removeprefix(".qwq_output/")).read_bytes(), receipt_bytes)
        # 只替换本地 store 定位；执行真正 admission，不调用 publish、不触碰任何 ref。
        from quwoquan_ops.ci.scoped_candidate import core
        with mock.patch.object(core, "_claim_root", return_value=target):
            admission = integration_run.create_publish_admission(repository=ROOT, policy_path=integration_run.POLICY,
                candidate_ref=refs["candidate"], source_fact_refs=[refs["sourceFact"]],
                alpha_fact_ref=refs["alphaFact"], beta_fact_ref=refs["betaFact"], expected_remote_oid=parent)
        self.assertEqual(json.loads(admission.read_bytes())["decision"], "admitted")

    def test_real_policy_beta_issuance_and_expiry(self) -> None:
        bundle, refs, store, signing, args = self._signed_bundle()
        candidate = json.loads((store / refs["candidate"]["ref"]).read_bytes())
        identity = {key: candidate[key] for key in ("candidateId", "commit", "tree")}
        store = self.root / "policy-signing-store"
        shutil.copytree(bundle / "store", store)
        (store / refs["betaFact"]["ref"]).unlink()
        with mock.patch.object(integration_run, "_store", return_value=store):
            evidence = integration_run._not_required_beta(candidate=identity, impact_plan_digest=candidate["impactPlanDigest"],
                impact_plan_path=bundle / "impact-plan.json", profile="integration", reason_code=integration_run.BETA_OPTIONAL_BY_POLICY)
            beta = integration_run._issue(environment="beta", candidate_ref=refs["candidate"],
                impact_plan_digest=candidate["impactPlanDigest"], evidence=evidence, status="not_required",
                predecessor=refs["alphaFact"], profile="integration", args=args, signer=signing.signer(args.signer_identity))
        fact = json.loads((store / beta["ref"]).read_bytes())
        integration_run.validate_environment_acceptance_fact(fact, store_root=store, verify_references=True,
            signature_verifier=signing.environment_verifier(), expected_signer_identity=args.signer_identity)
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        with mock.patch.object(integration_run, "datetime") as clock, self.assertRaises(integration_run.EnvironmentSchedulerError) as blocked:
            clock.now.return_value = future
            integration_run._import_acceptance_bundle(bundle_dir=bundle, commit=identity["commit"], tree=identity["tree"],
                parent=candidate["expectedParent"], args=args, keyring=signing.keyring())
        self.assertEqual(blocked.exception.code, "ENVIRONMENT_SCHEDULER.ACCEPTANCE_EXPIRED")

    def test_bundle_create_once_loser_does_not_overwrite_winner(self) -> None:
        import os
        target = self.root / "race"
        original = os.link

        def race(source, destination):
            Path(destination).write_bytes(b"winner")
            original(source, destination)

        with mock.patch.object(integration_run.os, "link", side_effect=race), self.assertRaises(integration_run.IntegrationRunError) as blocked:
            integration_run._bundle_put(target, "fact.json", b"loser")
        self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.BUNDLE_DRIFT")
        self.assertEqual((target / "fact.json").read_bytes(), b"winner")
        self.assertEqual(sorted(path.name for path in target.iterdir()), ["fact.json"])

    def test_acceptance_bundle_round_trips_exact_bytes_into_integration_store(self) -> None:
        # accepted 终态把 candidate/claim/source fact/两份 EAF 及其全部 case/named 证据按 store 相对路径复制成 bundle；
        # integration 逐字节复核后 create-once 导入自己的 store，再次导入幂等（0 新文件）。
        commit, tree, parent = "1" * 40, "2" * 40, "0" * 40
        bundle_dir, facts, lane_store = self._bundle_from_fake_store(commit=commit, tree=tree, parent=parent)
        manifest = json.loads((bundle_dir / "bundle.json").read_bytes())
        self.assertEqual(manifest["schema"], integration_run.ACCEPTANCE_BUNDLE_SCHEMA)
        self.assertEqual((manifest["commit"], manifest["tree"], manifest["expectedParent"]), (commit, tree, parent))
        # 3 + 2 × (fact + 8 named + 1 case) = 23 个 exact store 文件
        self.assertEqual(len(manifest["storeFiles"]), 23)
        self.assertEqual(manifest["mergedLanes"][0]["branch"], "refs/heads/lane/product-mainline")
        self.assertEqual(manifest["beta"], {"status": "not_required", "executed": False, "reasonCode": integration_run.BETA_OPTIONAL_BY_POLICY})
        self.assertEqual(manifest["dataReleaseHandoffRef"], VALID_REF)
        for exact in manifest["storeFiles"]:
            self.assertEqual((bundle_dir / "store" / exact["ref"]).read_bytes(), (lane_store / exact["ref"]).read_bytes())
        self.assertTrue((bundle_dir / "impact-plan.json").is_file())

        integration_store = self.root / "integration-store"
        seen: list[dict[str, object]] = []

        def fake_validate(fact, **kwargs):
            seen.append({"fact": fact, **kwargs})
            return fact

        args = SimpleNamespace(signer_identity="quwoquan-environment-ops-local")
        with mock.patch.object(integration_run, "_store", return_value=integration_store), \
                mock.patch.object(integration_run, "validate_environment_acceptance_fact", side_effect=fake_validate), \
                mock.patch.object(integration_run, "ed25519_environment_verifier", return_value=lambda *a: True):
            imported = integration_run._import_acceptance_bundle(bundle_dir=bundle_dir, commit=commit, tree=tree, parent=parent, args=args, keyring=object())
            self.assertEqual((imported["importedFiles"], imported["storeFiles"]), (23, 23))
            self.assertEqual(imported["candidate"]["candidateId"], manifest["candidateId"])
            again = integration_run._import_acceptance_bundle(bundle_dir=bundle_dir, commit=commit, tree=tree, parent=parent, args=args, keyring=object())
            self.assertEqual(again["importedFiles"], 0)
        for exact in manifest["storeFiles"]:
            self.assertEqual((integration_store / exact["ref"]).read_bytes(), (lane_store / exact["ref"]).read_bytes())
        # 先以 portable bundle 为根复核闭包，验证通过才原子写入 integration store。
        self.assertEqual([item["fact"]["environment"] for item in seen], ["alpha", "beta", "alpha", "beta"])
        for item in seen:
            self.assertEqual(item["store_root"], bundle_dir / "store")
            self.assertTrue(item["verify_references"])
            self.assertEqual(item["expected_signer_identity"], "quwoquan-environment-ops-local")

    def test_bundle_import_rejects_drift_mismatch_and_stale_parent(self) -> None:
        commit, tree, parent = "1" * 40, "2" * 40, "0" * 40
        bundle_dir, facts, _ = self._bundle_from_fake_store(commit=commit, tree=tree, parent=parent)
        args = SimpleNamespace(signer_identity="quwoquan-environment-ops-local")
        manifest = json.loads((bundle_dir / "bundle.json").read_bytes())

        def attempt(name: str, *, bundle: Path = bundle_dir, commit_: str = commit, tree_: str = tree, parent_: str = parent) -> str:
            store = self.root / f"store-{name}"
            with mock.patch.object(integration_run, "_store", return_value=store), \
                    mock.patch.object(integration_run, "validate_environment_acceptance_fact", side_effect=lambda fact, **_: fact), \
                    mock.patch.object(integration_run, "ed25519_environment_verifier", return_value=lambda *a: True), \
                    self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._import_acceptance_bundle(bundle_dir=bundle, commit=commit_, tree=tree_, parent=parent_, args=args, keyring=object())
            return blocked.exception.code

        self.assertEqual(attempt("commit", commit_="f" * 40), "INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH")
        self.assertEqual(attempt("parent", parent_="e" * 40), "INTEGRATION_RUN.BUNDLE_STALE")
        self.assertEqual(attempt("missing", bundle=self.root / "nowhere"), "INTEGRATION_RUN.ACCEPTANCE_REQUIRED")
        # store 文件字节被改 → 与 manifest digest 不符
        tampered = self.root / "tampered"
        shutil.copytree(bundle_dir, tampered)
        victim = tampered / "store" / facts["sourceFact"]["ref"]
        victim.write_bytes(victim.read_bytes().replace(b"passed", b"failed"))
        self.assertEqual(attempt("tampered", bundle=tampered), "INTEGRATION_RUN.BUNDLE_DRIFT")
        # manifest 被改 → bundleId 不再绑定
        edited = self.root / "edited"
        shutil.copytree(bundle_dir, edited)
        (edited / "bundle.json").write_bytes(integration_run._canonical_bytes({**manifest, "laneBranch": "refs/heads/lane/ops"}) + b"\n")
        self.assertEqual(attempt("edited", bundle=edited), "INTEGRATION_RUN.BUNDLE_DRIFT")
        # integration store 已有同 ref 不同字节 → create-once 拒绝
        occupied = self.root / "store-occupied"
        existing = occupied / facts["candidate"]["ref"]
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"{}\n")
        self.assertEqual(attempt("occupied"), "INTEGRATION_RUN.BUNDLE_DRIFT")
        # bundle 的 signer 与 integration 期望的 signer 不一致
        self.assertEqual(self._import_with_signer(bundle_dir, commit, tree, parent, "someone-else"), "INTEGRATION_RUN.BUNDLE_INVALID")

    def _import_with_signer(self, bundle_dir: Path, commit: str, tree: str, parent: str, signer: str) -> str:
        with mock.patch.object(integration_run, "_store", return_value=self.root / "store-signer"), \
                mock.patch.object(integration_run, "validate_environment_acceptance_fact", side_effect=lambda fact, **_: fact), \
                self.assertRaises(integration_run.IntegrationRunError) as blocked:
            integration_run._import_acceptance_bundle(
                bundle_dir=bundle_dir, commit=commit, tree=tree, parent=parent, args=SimpleNamespace(signer_identity=signer), keyring=object(),
            )
        return blocked.exception.code

    def test_integrate_runs_no_environment_phase_and_admits_from_imported_facts(self) -> None:
        # integrate 的相位只有 preflight → import-bundle → admit（→ publish）；不调用 readiness、build-head、
        # 任何 stackctl 环境相位或 Data ship；admission 绑定的是导入的 candidate/source/EAF exact ref。
        commit, tree, parent = "1" * 40, "2" * 40, "0" * 40
        bundle_dir, facts, _ = self._bundle_from_fake_store(commit=commit, tree=tree, parent=parent)
        manifest = json.loads((bundle_dir / "bundle.json").read_bytes())
        integration_store = self.root / "integration-store"
        git_answers = {
            ("status",): "", ("rev-parse", f"HEAD^{{commit}}"): commit, ("ls-remote",): f"{parent}\trefs/heads/dev1.0",
            ("symbolic-ref",): "refs/heads/dev1.0", ("rev-parse", "HEAD"): commit, ("show",): tree,
        }

        def fake_git(*args: str) -> str:
            for key, value in git_answers.items():
                if args[: len(key)] == key:
                    return value
            raise AssertionError(f"unexpected git {args}")

        admitted: dict[str, object] = {}

        def fake_admit(**kwargs: object) -> Path:
            admitted.update(kwargs)
            path = integration_store / "admissions/adm.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            return path

        forbidden = {name: mock.patch.object(integration_run, name, side_effect=AssertionError(f"{name} must not run in integrate"))
                     for name in ("_run_environment", "_local_readiness", "_impact_plan", "_apply_data_release", "_stackctl", "_data_ship",
                                  "build_head_candidate", "create_source_fact", "_not_required_beta", "_issue", "_write_acceptance_bundle")}
        with self._runtime_patches(), mock.patch.object(integration_run, "_store", return_value=integration_store), \
                mock.patch.object(integration_run, "_git", side_effect=fake_git), \
                mock.patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")), \
                mock.patch.object(integration_run, "validate_environment_acceptance_fact", side_effect=lambda fact, **_: fact), \
                mock.patch.object(integration_run, "ed25519_environment_verifier", return_value=lambda *a: True), \
                mock.patch.object(integration_run, "create_publish_admission", side_effect=fake_admit), \
                mock.patch.object(integration_run, "release_claim"), \
                mock.patch.object(integration_run, "store_ref", side_effect=lambda **kw: {"ref": kw["path"].name, "digest": "sha256:" + "0" * 64}):
            for patcher in forbidden.values():
                patcher.start()
                self.addCleanup(patcher.stop)
            self.assertEqual(integration_run.main(["--mode", "integrate", "--acceptance-bundle", str(bundle_dir), "--run-id", "int-1"]), 0)
        summary = json.loads((self.root / "runs/int-1/summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["terminal"], "admitted")
        self.assertEqual([phase["name"] for phase in summary["phases"]], ["preflight", "import-bundle", "admit"])
        self.assertEqual(summary["acceptanceBundle"]["bundleId"], manifest["bundleId"])
        self.assertEqual(summary["environments"]["alpha"]["imported"], True)
        self.assertEqual(summary["environments"]["beta"]["reasonCode"], integration_run.BETA_OPTIONAL_BY_POLICY)
        self.assertEqual(admitted["candidate_ref"], facts["candidate"])
        self.assertEqual(admitted["source_fact_refs"], [facts["sourceFact"]])
        self.assertEqual((admitted["alpha_fact_ref"], admitted["beta_fact_ref"]), (facts["alphaFact"], facts["betaFact"]))
        self.assertEqual(admitted["expected_remote_oid"], parent)

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

    def test_attestation_exact_readback_is_required_without_category(self) -> None:
        attestation = _attestation(self.root, "rel-candidate")
        local = self.root / "data/releases/rel-candidate/attestations/release.json"
        local.write_bytes(local.read_bytes() + b"\n")
        with self.assertRaises(integration_run.IntegrationRunError) as blocked:
            integration_run._release_id(attestation)
        self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()

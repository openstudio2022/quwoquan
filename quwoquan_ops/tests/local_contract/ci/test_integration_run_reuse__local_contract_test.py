# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t2
"""lane `make accept REUSE=1` 的 candidate/Alpha/Beta 事实复用合同。

复用只按 exact 身份（commit、tree、expectedParent、ImpactPlan digest、profile）精确匹配，并要求既有
Alpha 事实通过 canonical 校验；任一漂移、校验失败或事实缺失都视为不存在，不按时间窗或分支名复用。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/cli/integration_run.py"
SPEC = importlib.util.spec_from_file_location("integration_run_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
integration_run = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integration_run
SPEC.loader.exec_module(integration_run)

COMMIT = "c" * 40
TREE = "t" * 40
PARENT = "p" * 40
IMPACT = "sha256:" + "1" * 64
PROFILE = "integration"


def _release_args(store: Path):
    from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import release_attestation_payload

    paths = []
    for role, marker in (("release", "c"), ("rollback", "d")):
        path = store / f"{role}.json"
        if not path.exists():
            path.write_text(json.dumps(release_attestation_payload(role, "sha256:" + marker * 64)), encoding="utf-8")
        paths.append(path)
    return SimpleNamespace(release_attestation=paths[0], rollback_release_attestation=paths[1], workload="full",
                           release_handoff_ref="handoff-ref-v1:sha256:" + "a" * 64 + ":sha256:" + "b" * 64)


def _binding(store: Path):
    inputs = integration_run._acceptance_release_inputs(_release_args(store))
    refs = {}
    for field in ("packageManifest", "releaseReadiness"):
        path = store / f"{field}.json"
        if not path.exists():
            path.write_text(json.dumps({"original": field}), encoding="utf-8")
        refs[field] = {"ref": path.name, "digest": integration_run.exact_file_digest(path)}
    return {"inputs": inputs, **refs}


def _candidate(store: Path, *, candidate_id: str, created_at: str, **overrides: object) -> Path:
    body: dict[str, object] = {
        "schema": integration_run._CANDIDATE_SCHEMA,
        "candidateId": candidate_id,
        "commit": COMMIT,
        "tree": TREE,
        "expectedParent": PARENT,
        "impactPlanDigest": IMPACT,
        "claimRef": f"claims/{candidate_id.removeprefix('sha256:')}.json",
        "createdAt": created_at,
    }
    body.update(overrides)
    path = store / "candidates" / f"{candidate_id.removeprefix('sha256:')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _acceptance(store: Path, *, candidate_id: str, environment: str, status: str = "passed", **overrides: object) -> Path:
    body: dict[str, object] = {
        "schema": integration_run._ACCEPTANCE_SCHEMA,
        "environment": environment,
        "profile": PROFILE,
        "status": status,
        "candidate": {"candidateId": candidate_id, "commit": COMMIT, "tree": TREE},
        "impactPlanDigest": IMPACT,
        "nonPromotable": False,
        "predecessor": None,
    }
    if environment == "beta":
        alpha = store / "environment-execution/acceptance" / candidate_id.removeprefix("sha256:") / "alpha.json"
        body["predecessor"] = {"ref": alpha.relative_to(store).as_posix(), "digest": integration_run.exact_file_digest(alpha)}
    if status == "not_required":
        body["reasonCode"] = integration_run.BETA_OPTIONAL_BY_POLICY
    runtime = store / f"runtime-{candidate_id.removeprefix('sha256:')}-{environment}.json"
    runtime.write_text(json.dumps({"source": {"acceptanceBinding": _binding(store)}}), encoding="utf-8")
    body["runtimeIdentity"] = {"ref": runtime.name, "digest": integration_run.exact_file_digest(runtime)}
    body.update(overrides)
    path = store / "environment-execution/acceptance" / candidate_id.removeprefix("sha256:") / f"{environment}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # 此 fixture 只隔离查找/政策分流；真实验签、过期与 evidence refs 另有下方真实签发合同。
    def fake_validate(payload, *, store_root, verify_references, accepted_at, signature_verifier, expected_signer_identity):
        assert verify_references is True and store_root == tmp_path
        assert accepted_at.tzinfo is not None
        if payload.get("__invalid"):
            raise integration_run.EnvironmentSchedulerError("ENVIRONMENT_SCHEDULER.ACCEPTANCE_EXPIRED", "acceptance fact is expired")
        return dict(payload)

    monkeypatch.setattr(integration_run, "validate_environment_acceptance_fact", fake_validate)
    monkeypatch.setattr(integration_run, "OUTPUT_ROOT", tmp_path)
    return tmp_path


def _lookup(store: Path, **overrides: object):
    params: dict[str, object] = {"store": store, "commit": COMMIT, "tree": TREE, "parent": PARENT, "impact_plan_digest": IMPACT, "profile": PROFILE,
                                 "release_inputs": integration_run._acceptance_release_inputs(_release_args(store))}
    params.update(overrides)
    return integration_run._find_reusable_candidate(**params)


def test_exact_candidate_with_passed_alpha_is_reused_and_beta_optional(store: Path) -> None:
    candidate_id = "sha256:" + "a" * 64
    path = _candidate(store, candidate_id=candidate_id, created_at="2026-01-01T00:00:00Z")
    alpha = _acceptance(store, candidate_id=candidate_id, environment="alpha")

    found = _lookup(store)

    assert found is not None
    assert found["candidatePath"] == path and found["candidate"]["candidateId"] == candidate_id
    assert found["candidateRef"]["ref"] == f"candidates/{'a' * 64}.json"
    assert found["alpha"]["ref"] == alpha.relative_to(store).as_posix()
    assert found["beta"] is None

    _acceptance(store, candidate_id=candidate_id, environment="beta", status="not_required")
    assert _lookup(store)["beta"]["ref"].endswith("/beta.json")


def test_missing_alpha_or_no_candidates_means_no_reuse(store: Path) -> None:
    assert _lookup(store) is None
    _candidate(store, candidate_id="sha256:" + "a" * 64, created_at="2026-01-01T00:00:00Z")
    assert _lookup(store) is None, "没有 Alpha 事实的 candidate 不构成复用"


@pytest.mark.parametrize(
    "candidate_override, acceptance_override, lookup_override",
    [
        ({"impactPlanDigest": "sha256:" + "2" * 64}, {}, {}),
        ({"expectedParent": "q" * 40}, {}, {}),
        ({"commit": "d" * 40}, {}, {}),
        ({}, {"profile": "smoke"}, {}),
        ({}, {"impactPlanDigest": "sha256:" + "2" * 64}, {}),
        ({}, {"status": "failed"}, {}),
        ({}, {"candidate": {"candidateId": "sha256:" + "f" * 64, "commit": COMMIT, "tree": TREE}}, {}),
        ({}, {}, {"profile": "smoke"}),
        ({}, {"__invalid": True}, {}),
    ],
)
def test_any_identity_drift_or_validation_failure_disables_reuse(store: Path, candidate_override, acceptance_override, lookup_override) -> None:
    candidate_id = "sha256:" + "a" * 64
    _candidate(store, candidate_id=candidate_id, created_at="2026-01-01T00:00:00Z", **candidate_override)
    _acceptance(store, candidate_id=candidate_id, environment="alpha", **acceptance_override)

    assert _lookup(store, **lookup_override) is None


def test_newest_matching_candidate_wins(store: Path) -> None:
    older, newer = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    _candidate(store, candidate_id=older, created_at="2026-01-01T00:00:00Z")
    _acceptance(store, candidate_id=older, environment="alpha")
    _candidate(store, candidate_id=newer, created_at="2026-02-01T00:00:00Z")
    _acceptance(store, candidate_id=newer, environment="alpha")

    found = _lookup(store)

    assert found is not None and found["candidate"]["candidateId"] == newer


def test_reuse_flag_is_opt_in_and_summary_renders_reused_line() -> None:
    parser = integration_run._parser()
    args = parser.parse_args(["--release-attestation", "a.json", "--rollback-release-attestation", "b.json"])
    assert args.reuse is False
    assert parser.parse_args(["--release-attestation", "a.json", "--rollback-release-attestation", "b.json", "--reuse"]).reuse is True

    rendered = integration_run._render_summary({
        "runId": "r", "terminal": "admitted", "phases": [],
        "reused": {"readiness": True, "candidate": True, "alpha": True, "beta": False},
    })
    assert "- reused: alpha=yes, beta=no, candidate=yes, readiness=yes" in rendered


@pytest.mark.parametrize("opted_in", [False, True])
@pytest.mark.parametrize("status, reason", [
    ("passed", None),
    ("not_required", integration_run.BETA_OPTIONAL_BY_POLICY),
    ("not_required", integration_run.NO_LIVE),
])
def test_reuse_requires_current_beta_policy(store: Path, opted_in: bool, status: str, reason: str | None) -> None:
    candidate_id = "sha256:" + "a" * 64
    _candidate(store, candidate_id=candidate_id, created_at="2026-01-01T00:00:00Z")
    _acceptance(store, candidate_id=candidate_id, environment="alpha")
    _acceptance(store, candidate_id=candidate_id, environment="beta", status=status, reasonCode=reason)

    found = _lookup(store, beta=opted_in)
    matches = (status == "passed") if opted_in else (status == "not_required" and reason == integration_run.BETA_OPTIONAL_BY_POLICY)
    if matches:
        assert found is not None and found["beta"] is not None
    elif opted_in:
        assert found is not None and found["beta"] is None, "not_required 不能冒充真实 Beta"
    else:
        assert found is None, "旧 Beta slot 不能被改写为政策跳过，必须重建 candidate"


def test_beta_reuse_requires_exact_alpha_predecessor(store: Path) -> None:
    candidate_id = "sha256:" + "a" * 64
    _candidate(store, candidate_id=candidate_id, created_at="2026-01-01T00:00:00Z")
    _acceptance(store, candidate_id=candidate_id, environment="alpha")
    _acceptance(store, candidate_id=candidate_id, environment="beta", predecessor={"ref": "other.json", "digest": IMPACT})
    assert _lookup(store, beta=True)["beta"] is None


def test_complete_beta_chain_wins_over_newer_alpha_only(store: Path) -> None:
    older, newer = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    for candidate_id, created in ((older, "2026-01-01T00:00:00Z"), (newer, "2026-02-01T00:00:00Z")):
        _candidate(store, candidate_id=candidate_id, created_at=created)
        _acceptance(store, candidate_id=candidate_id, environment="alpha")
    _acceptance(store, candidate_id=older, environment="beta")
    assert _lookup(store, beta=True)["candidate"]["candidateId"] == older


@pytest.mark.parametrize("damage", ["candidate-link", "acceptance-link", "non-promotable", "partial-beta"])
def test_unsafe_or_unusable_candidate_is_not_reused(store: Path, damage: str) -> None:
    candidate_id = "sha256:" + "a" * 64
    candidate = _candidate(store, candidate_id=candidate_id, created_at="2026-01-01T00:00:00Z")
    alpha = _acceptance(store, candidate_id=candidate_id, environment="alpha", nonPromotable=damage == "non-promotable")
    if damage in {"candidate-link", "acceptance-link"}:
        path = candidate if damage == "candidate-link" else alpha
        target = path.with_suffix(".linked")
        path.rename(target)
        path.symlink_to(target)
    elif damage == "partial-beta":
        (store / "environment-evidence" / candidate_id.removeprefix("sha256:") / "beta").mkdir(parents=True)
    assert _lookup(store) is None


@pytest.fixture
def acceptance_main(store: Path, monkeypatch: pytest.MonkeyPatch):
    """仅驱动编排分流；环境、签发和发布由替身隔离，不作为 runtime 资格。"""
    candidate_id = "sha256:" + "a" * 64
    candidate_path = _candidate(store, candidate_id=candidate_id, created_at="2026-01-01T00:00:00Z")
    _acceptance(store, candidate_id=candidate_id, environment="alpha")
    new_candidate_path = store / "fresh-candidate.json"
    new_candidate_path.write_text(json.dumps({**json.loads(candidate_path.read_bytes()), "candidateId": "sha256:" + "b" * 64}), encoding="utf-8")
    plan_path = store / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    release, rollback = store / "release.json", store / "rollback.json"
    _release_args(store)
    lane = "refs/heads/lane/product-mainline"
    merged_lanes = [{"branch": lane, "commit": COMMIT}, {"branch": "refs/heads/lane/engineering", "commit": PARENT}]
    git_answers = {
        "status": "", "rev-parse": COMMIT, "ls-remote": f"{PARENT}\trefs/heads/dev1.0", "show": TREE,
    }
    monkeypatch.setattr(integration_run, "_git", lambda *args: git_answers[args[0]])
    monkeypatch.setattr(integration_run.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    for name, value in {"OUTPUT_ROOT": store, "RUNS_ROOT": store / "runs"}.items():
        monkeypatch.setattr(integration_run, name, value)
    replacements = {
        "_store": store, "load_keyring": {}, "ed25519_signer": object(),
        "ed25519_environment_verifier": object(), "key_root": store,
        "_readiness_local_ref": lane, "_merged_lanes": merged_lanes,
        "_impact_plan": ({"integration_depth": "abg_release_sensitive", "plan_digest": IMPACT, "scopes": ["app", "data"]}, plan_path),
        "_local_readiness": (store / "readiness.json", {"cache_hit": True}),
        "build_head_candidate": new_candidate_path, "create_source_fact": store / "source.json", "release_claim": None,
        "_not_required_beta": {}, "_issue": {"ref": "issued.json", "digest": IMPACT},
        "_alpha_offline_pages": {"caseCount": 26},
    }
    calls = {}
    for name, value in replacements.items():
        calls[name] = mock.Mock(return_value=value)
        monkeypatch.setattr(integration_run, name, calls[name])
    monkeypatch.setattr(integration_run, "_release_id", lambda path: path.stem)
    monkeypatch.setattr(integration_run, "store_ref", lambda **kwargs: {"ref": kwargs["path"].relative_to(store).as_posix(), "digest": IMPACT})

    def run_environment(**kwargs):
        kwargs["summary"]["environments"][kwargs["environment"]] = {"executed": True}
        return {"readiness": store / "alpha-release-readiness.json"}

    def write_bundle(**kwargs):
        path = kwargs["run_dir"] / "acceptance-bundle"
        path.mkdir()
        (path / "bundle.json").write_text(json.dumps({"bundleId": IMPACT, "storeFiles": []}), encoding="utf-8")
        return path

    for name, effect in {"_run_environment": run_environment, "_write_acceptance_bundle": write_bundle}.items():
        calls[name] = mock.Mock(side_effect=effect)
        monkeypatch.setattr(integration_run, name, calls[name])
    for name in ("create_publish_admission", "local_git_cas_publish", "_stackctl", "_data_ship"):
        calls[name] = mock.Mock(side_effect=AssertionError(f"unexpected {name}"))
        monkeypatch.setattr(integration_run, name, calls[name])
    argv = ["--mode", "acceptance", "--run-id", "policy-reuse", "--release-attestation", str(release),
            "--rollback-release-attestation", str(rollback),
            "--release-handoff-ref", "handoff-ref-v1:sha256:" + "a" * 64 + ":sha256:" + "b" * 64,
            "--merged-lanes", "lane/engineering"]
    return SimpleNamespace(store=store, candidate_id=candidate_id, argv=argv, calls=calls, merged_lanes=merged_lanes)


@pytest.mark.parametrize("opted_in", [False, True])
@pytest.mark.parametrize("existing_beta", ["missing", "passed", "policy", "no-live"])
def test_acceptance_main_reuse_honors_beta_opt_in(acceptance_main, opted_in: bool, existing_beta: str) -> None:
    setup = acceptance_main
    if existing_beta != "missing":
        _acceptance(setup.store, candidate_id=setup.candidate_id, environment="beta",
                    status="passed" if existing_beta == "passed" else "not_required",
                    reasonCode=None if existing_beta == "passed" else (
                        integration_run.BETA_OPTIONAL_BY_POLICY if existing_beta == "policy" else integration_run.NO_LIVE))
    code = integration_run.main([*setup.argv, "--reuse", *(["--beta"] if opted_in else [])])
    summary = json.loads((setup.store / "runs/policy-reuse/summary.json").read_bytes())
    blocked = opted_in and existing_beta != "passed"
    assert code == (1 if blocked else 0)
    assert summary["mergedLanes"] == setup.merged_lanes
    if blocked:
        assert summary["blocker"]["code"] == "INTEGRATION_RUN.BETA_REUSE_UNAVAILABLE"
        setup.calls["_run_environment"].assert_not_called()
        setup.calls["_issue"].assert_not_called()
        setup.calls["_write_acceptance_bundle"].assert_not_called()
    else:
        assert summary["terminal"] == "accepted" and "admission" not in summary and "publish" not in summary
        expected_status = "passed" if opted_in else "not_required"
        expected_reason = None if opted_in else integration_run.BETA_OPTIONAL_BY_POLICY
        assert (summary["acceptance"]["betaStatus"], summary["acceptance"]["betaReasonCode"]) == (expected_status, expected_reason)
        bundle = setup.calls["_write_acceptance_bundle"].call_args.kwargs
        assert (bundle["beta_status"], bundle["beta_reason"]) == (expected_status, expected_reason)
        reused_beta = (opted_in and existing_beta == "passed") or (not opted_in and existing_beta == "policy")
        assert summary["reused"]["beta"] is reused_beta
        fresh = not opted_in and existing_beta in {"passed", "no-live"}
        assert summary["reused"]["candidate"] is (not fresh)
        assert summary["reused"]["alpha"] is (not fresh)
        assert [call.kwargs["environment"] for call in setup.calls["_run_environment"].call_args_list] == (["alpha"] if fresh else [])
        if fresh:
            assert setup.calls["_run_environment"].call_args.kwargs["scopes"] == ("app", "data")
        rendered = (setup.store / "runs/policy-reuse/summary.md").read_text(encoding="utf-8")
        assert "- mergedLanes:" in rendered and "- reused:" in rendered
    assert summary["reused"]["readiness"] is True
    for name in ("create_publish_admission", "local_git_cas_publish", "_stackctl", "_data_ship"):
        setup.calls[name].assert_not_called()


def test_existing_candidate_is_used_before_pages_without_claim_or_release(acceptance_main, monkeypatch) -> None:
    setup = acceptance_main
    candidate = json.loads((setup.store / "fresh-candidate.json").read_bytes())
    exact = {"ref": "fresh-candidate.json", "digest": IMPACT}
    existing = mock.Mock(return_value=(exact, candidate))
    monkeypatch.setattr(integration_run, "_existing_candidate", existing)
    assert integration_run.main([*setup.argv, "--candidate-ref", exact["ref"] + "=" + IMPACT]) == 0
    setup.calls["build_head_candidate"].assert_not_called()
    setup.calls["release_claim"].assert_not_called()
    assert setup.calls["create_source_fact"].call_args.kwargs["candidate_ref"] == exact
    assert setup.calls["_alpha_offline_pages"].call_args.kwargs["candidate_ref"] == exact
    assert setup.calls["_run_environment"].call_args.kwargs["offline_pages"] == {"caseCount": 26}
    summary = json.loads((setup.store / "runs/policy-reuse/summary.json").read_bytes())
    names = [phase["name"] for phase in summary["phases"]]
    assert names.index("alpha.offline-pages") < names.index("alpha.issue")


def test_offline_failure_stops_before_services_and_fact_issuance(acceptance_main) -> None:
    setup = acceptance_main
    setup.calls["_alpha_offline_pages"].side_effect = integration_run.IntegrationRunError("INTEGRATION_RUN.APP_LAUNCH_FAILED", "missing case")
    assert integration_run.main(setup.argv) == 1
    setup.calls["_run_environment"].assert_not_called()
    setup.calls["_issue"].assert_not_called()
    setup.calls["_write_acceptance_bundle"].assert_not_called()


def test_acceptance_without_reuse_runs_fresh_alpha_and_explicit_beta(acceptance_main) -> None:
    setup = acceptance_main
    _acceptance(setup.store, candidate_id=setup.candidate_id, environment="beta")
    assert integration_run.main([*setup.argv, "--beta"]) == 0
    calls = setup.calls["_run_environment"].call_args_list
    assert [call.kwargs["environment"] for call in calls] == ["alpha", "beta"]
    assert calls[1].kwargs["previous_readiness"] == setup.store / "alpha-release-readiness.json"
    summary = json.loads((setup.store / "runs/policy-reuse/summary.json").read_bytes())
    assert summary["reused"] == {"readiness": True, "candidate": False, "alpha": False, "beta": False}


@pytest.mark.parametrize("failed", [False, True])
def test_wall_clock_counts_nested_phases_once_and_includes_cleanup(acceptance_main, monkeypatch, failed):
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004
    setup = acceptance_main
    clock = [100.0]
    monkeypatch.setattr(integration_run.time, "monotonic", lambda: clock[0])

    def elapsed(seconds):
        clock[0] += seconds

    def environment(**kwargs):
        kwargs["summary"]["environments"]["alpha"] = {"executed": True}

        def nested():
            kwargs["phases"].run("alpha.nested-probe", lambda: elapsed(4))
            elapsed(2)
            if failed:
                raise integration_run.IntegrationRunError("INTEGRATION_RUN.INSPECT_FAILED", "probe failed")

        kwargs["phases"].run("alpha.outer-probe", nested)
        return {"readiness": setup.store / "alpha-release-readiness.json"}

    setup.calls["_run_environment"].side_effect = environment
    setup.calls["release_claim"].side_effect = lambda **kwargs: elapsed(5)
    assert integration_run.main(setup.argv) == (1 if failed else 0)
    summary = json.loads((setup.store / "runs/policy-reuse/summary.json").read_bytes())
    assert summary["wallClockSeconds"] == 11.0
    assert sum(phase["durationSeconds"] for phase in summary["phases"]) == 10.0
    setup.calls["release_claim"].assert_called_once()
    if failed:
        assert summary["blocker"]["code"] == "INTEGRATION_RUN.INSPECT_FAILED"


def test_integrate_rejects_acceptance_only_reuse(acceptance_main) -> None:
    setup = acceptance_main
    assert integration_run.main(["--mode", "integrate", "--acceptance-bundle", str(setup.store), "--reuse", "--run-id", "integrate-reuse"]) == 1
    summary = json.loads((setup.store / "runs/integrate-reuse/summary.json").read_bytes())
    assert summary["blocker"]["code"] == "INTEGRATION_RUN.INPUT_INVALID"
    setup.calls["_run_environment"].assert_not_called()
    setup.calls["_local_readiness"].assert_not_called()


@pytest.fixture
def signed_release_case(monkeypatch: pytest.MonkeyPatch):
    """真正 Ed25519 签发并验签：只隔离输出根和临时证据，不 mock 绑定校验。"""
    from quwoquan_ops.tests.local_contract.stackctl import test_integration_run_production_release__local_contract_test as support_module

    support = support_module.IntegrationRunProductionReleaseContractTest()
    support.setUp()
    monkeypatch.setattr(integration_run, "OUTPUT_ROOT", support.root)
    issue = support_module.integration_run.issue_environment_acceptance_fact

    def issue_bound(**kwargs):
        exact = kwargs["runtime_identity"]
        path = kwargs["store_root"] / exact["ref"]
        payload = json.loads(path.read_bytes())
        report = support.root / "reports" / payload["environment"] / "report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(b'{ "report": "original signed input" }\n')
        result = integration_run.StackctlResult("health", {"exitCode": 0, "reportDir": str(report.parent)}, "")
        with mock.patch.object(integration_run, "_store", return_value=kwargs["store_root"]):
            source = integration_run._report_source(result)
        payload["source"] = {**source, "acceptanceBinding": _binding(support.root)}
        path.write_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n")
        kwargs["runtime_identity"] = {"ref": exact["ref"], "digest": integration_run.exact_file_digest(path)}
        return issue(**kwargs)

    try:
        with mock.patch.object(support_module.integration_run, "issue_environment_acceptance_fact", side_effect=issue_bound):
            bundle, refs, store, signing, args = support._signed_bundle()
        candidate = json.loads((store / refs["candidate"]["ref"]).read_bytes())
        lookup = {"store": store, "commit": candidate["commit"], "tree": candidate["tree"],
                  "parent": candidate["expectedParent"], "impact_plan_digest": candidate["impactPlanDigest"],
                  "profile": args.profile, "signature_verifier": signing.environment_verifier(),
                  "expected_signer_identity": args.signer_identity}
        release_args = _release_args(support.root)
        yield SimpleNamespace(root=support.root, bundle=bundle, refs=refs, store=store, lookup=lookup, args=release_args,
                              signing=signing, import_args=args, candidate=candidate)
    finally:
        support.doCleanups()


@pytest.mark.parametrize("damage", ["none", "release", "rollback", "handoff", "roles", "workload", "missing-binding",
                                    "package-drift", "activation-drift", "missing-receipt", "tampered-binding"])
def test_real_signed_reuse_requires_exact_release_inputs(signed_release_case, damage: str) -> None:
    setup = signed_release_case
    if damage in {"release", "rollback"}:
        path = getattr(setup.args, "release_attestation" if damage == "release" else "rollback_release_attestation")
        payload = json.loads(path.read_bytes())
        payload["payloadSha256"] = "sha256:" + "e" * 64  # 同 releaseId，不同 exact 内容也必须重跑。
        path.write_text(json.dumps(payload), encoding="utf-8")
    elif damage == "handoff":
        setup.args.release_handoff_ref = "handoff-ref-v1:sha256:" + "e" * 64 + ":sha256:" + "f" * 64
    elif damage == "roles":
        setup.args.release_attestation, setup.args.rollback_release_attestation = setup.args.rollback_release_attestation, setup.args.release_attestation
    elif damage == "workload":
        setup.args.workload = "content-release"
    elif damage in {"package-drift", "activation-drift", "missing-receipt"}:
        path = setup.root / ("packageManifest.json" if damage == "package-drift" else "releaseReadiness.json")
        if damage == "missing-receipt":
            path.unlink()
        else:
            path.write_bytes(b"{}")
    elif damage in {"missing-binding", "tampered-binding"}:
        fact = json.loads((setup.store / setup.refs["alphaFact"]["ref"]).read_bytes())
        path = setup.store / fact["runtimeIdentity"]["ref"]
        payload = json.loads(path.read_bytes())
        payload["source"] = {} if damage == "missing-binding" else {"acceptanceBinding": {"inputs": {}}}
        path.write_text(json.dumps(payload), encoding="utf-8")
    found = integration_run._find_reusable_candidate(**setup.lookup, release_inputs=integration_run._acceptance_release_inputs(setup.args))
    assert (found is not None) is (damage == "none")
    if found is not None:
        assert found["alpha"] == setup.refs["alphaFact"] and found["beta"] == setup.refs["betaFact"]


@pytest.mark.parametrize("damage", ["none", "omitted", "drift", "escape"])
def test_signed_bundle_carries_exact_report_closure(signed_release_case, monkeypatch, damage):
    setup = signed_release_case
    manifest_path = setup.bundle / "bundle.json"
    manifest = json.loads(manifest_path.read_bytes())
    report = next(exact for exact in manifest["storeFiles"] if exact["ref"].startswith("runtime-reports/"))
    if damage == "omitted":
        manifest["storeFiles"].remove(report)
    elif damage == "drift":
        (setup.bundle / "store" / report["ref"]).write_bytes(b"{}")
    elif damage == "escape":
        report["ref"] = "../outside.json"
    if damage in {"omitted", "escape"}:
        manifest["bundleId"] = integration_run._sha256_hex(integration_run._canonical_bytes({k: v for k, v in manifest.items() if k != "bundleId"}))
        manifest_path.write_bytes(integration_run._canonical_bytes(manifest) + b"\n")
    target = setup.root / "destination-store"
    monkeypatch.setattr(integration_run, "_store", lambda: target)
    params = {"bundle_dir": setup.bundle, "commit": setup.candidate["commit"], "tree": setup.candidate["tree"],
              "parent": setup.candidate["expectedParent"], "args": setup.import_args, "keyring": setup.signing.keyring()}
    if damage == "none":
        imported = integration_run._import_acceptance_bundle(**params)
        assert imported["importedFiles"] == len(manifest["storeFiles"])
        assert (target / report["ref"]).read_bytes() == (setup.bundle / "store" / report["ref"]).read_bytes()
    else:
        with pytest.raises(integration_run.IntegrationRunError):
            integration_run._import_acceptance_bundle(**params)
        assert not target.exists(), "源 store 残留不得补齐不完整 bundle"


def test_bundle_cannot_relabel_signed_old_acceptance(signed_release_case, monkeypatch: pytest.MonkeyPatch) -> None:
    setup = signed_release_case
    setup.args.release_handoff_ref = "handoff-ref-v1:sha256:" + "e" * 64 + ":sha256:" + "f" * 64
    monkeypatch.setattr(integration_run, "_store", lambda: setup.store)
    destination = setup.root / "relabelled"
    with pytest.raises(integration_run.IntegrationRunError, match="cannot relabel old acceptance"):
        integration_run._write_acceptance_bundle(
            run_dir=destination, candidate_ref=setup.refs["candidate"], source_ref=setup.refs["sourceFact"],
            alpha_ref=setup.refs["alphaFact"], beta_ref=setup.refs["betaFact"], identity={}, plan_path=setup.bundle / "impact-plan.json",
            summary={"reused": {"alpha": True}, "dataReleases": ["release", "rollback"],
                     "dataReleaseHandoffRef": setup.args.release_handoff_ref},
            beta_status="not_required", beta_reason=integration_run.BETA_OPTIONAL_BY_POLICY,
            lane_branch="refs/heads/lane/product-mainline", merged_lanes=[], args=setup.args)
    assert not destination.exists(), "拒绝新标签时不得先落盘 bundle"


@pytest.mark.parametrize("damage", ["release", "rollback", "handoff"])
@pytest.mark.parametrize("opted_in", [False, True])
def test_changed_inputs_rerun_instead_of_reusing_or_blocking(acceptance_main, damage: str, opted_in: bool) -> None:
    setup = acceptance_main
    if damage == "handoff":
        index = setup.argv.index("--release-handoff-ref") + 1
        setup.argv[index] = "handoff-ref-v1:sha256:" + "e" * 64 + ":sha256:" + "f" * 64
    else:
        path = setup.store / f"{damage}.json"
        payload = json.loads(path.read_bytes())
        payload["payloadSha256"] = "sha256:" + "e" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")
    assert integration_run.main([*setup.argv, "--reuse", *(["--beta"] if opted_in else [])]) == 0
    summary = json.loads((setup.store / "runs/policy-reuse/summary.json").read_bytes())
    assert summary["reused"]["candidate"] is False and summary["reused"]["alpha"] is False
    assert [call.kwargs["environment"] for call in setup.calls["_run_environment"].call_args_list] == (["alpha", "beta"] if opted_in else ["alpha"])


@pytest.mark.parametrize("damage", ["none", "expired", "wrong-key", "evidence-drift"])
def test_reusable_acceptance_revalidates_real_signed_evidence(damage: str) -> None:
    from quwoquan_ops.tests.local_contract.stackctl.test_integration_run_production_release__local_contract_test import (
        IntegrationRunProductionReleaseContractTest,
    )
    from quwoquan_ops.tests.support.evidence_signing_test_support import create_temporary_signing

    support = IntegrationRunProductionReleaseContractTest()
    support.setUp()
    try:
        _bundle, refs, store, signing, args = support._signed_bundle()
        fact = json.loads((store / refs["alphaFact"]["ref"]).read_bytes())
        verifier = signing.environment_verifier()
        if damage == "wrong-key":
            verifier = create_temporary_signing(support.root / "other-reuse-key").environment_verifier()
        elif damage == "evidence-drift":
            (store / fact["runtimeIdentity"]["ref"]).write_bytes(b"{}")
        with mock.patch.object(integration_run, "datetime") as clock:
            clock.now.return_value = datetime.now(timezone.utc) + (timedelta(hours=2) if damage == "expired" else timedelta())
            found = integration_run._reusable_acceptance(
                store=store, candidate_id=fact["candidate"]["candidateId"], commit=fact["candidate"]["commit"],
                tree=fact["candidate"]["tree"], environment="alpha", profile=args.profile,
                impact_plan_digest=fact["impactPlanDigest"], allowed_status={"passed"},
                signature_verifier=verifier, expected_signer_identity=args.signer_identity,
            )
        assert found == (refs["alphaFact"] if damage == "none" else None)
    finally:
        support.doCleanups()


@pytest.fixture
def host_reports(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    host, output, store = root / "host", root / "repo-output", root / "store"
    monkeypatch.setattr(integration_run, "OUTPUT_ROOT", output)
    monkeypatch.setattr(integration_run, "env_runs_root", lambda env: host / "env" / env / "runs")
    monkeypatch.setattr(integration_run, "_store", lambda: store)
    path = host / "env/alpha/runs/health-exact/report.json"
    path.parent.mkdir(parents=True)
    raw = b'{ "checks": [], "original": "exact bytes" }\n'
    path.write_bytes(raw)
    result = integration_run.StackctlResult("health --target alpha-local", {"exitCode": 0, "reportDir": str(path.parent)}, "")
    return SimpleNamespace(host=host, output=output, store=store, path=path, raw=raw, result=result)


def test_host_report_import_is_exact_read_only_and_store_relative(host_reports):
    setup = host_reports
    source = integration_run._report_source(setup.result)
    assert source["reportRoot"] == "store"
    exact = {"ref": source["reportRef"], "digest": source["reportDigest"]}
    assert integration_run._bundle_bytes(setup.store, exact) == setup.raw
    assert setup.path.read_bytes() == setup.raw
    assert not setup.output.exists(), "不得在 repo/env/alpha 中制造 live 事实副本"
    assert str(setup.host) not in json.dumps(source)
    named = integration_run._write_canonical(setup.store / "named.json", {"source": source})
    assert integration_run._report_fact_refs(store=setup.store, fact={"runtimeIdentity": named}) == [exact]
    (setup.store / exact["ref"]).write_bytes(b"drift")
    with pytest.raises(integration_run.IntegrationRunError, match="exact bytes drifted"):
        integration_run._report_fact_refs(store=setup.store, fact={"runtimeIdentity": named})


@pytest.mark.parametrize("damage", ["outside", "traversal", "file-link", "parent-link"])
def test_host_report_rejects_noncanonical_paths_before_import(host_reports, damage):
    setup = host_reports
    path = setup.path
    if damage == "outside":
        path = setup.host / "private/report.json"
        path.parent.mkdir()
        path.write_bytes(setup.raw)
    elif damage == "traversal":
        path = path.parent / ".." / path.parent.name / path.name
    elif damage == "file-link":
        original = path.with_suffix(".original")
        path.rename(original)
        path.symlink_to(original)
    else:
        original = path.parent.with_name("original")
        path.parent.rename(original)
        path.parent.symlink_to(original, target_is_directory=True)
    result = integration_run.StackctlResult("health", {"exitCode": 0, "reportDir": str(path.parent)}, "")
    with pytest.raises(integration_run.IntegrationRunError):
        integration_run._report_source(result)
    assert not setup.store.exists()


@pytest.mark.parametrize("when", ["after-read", "during-copy", "removed"])
def test_host_report_source_drift_never_returns_authoritative_ref(host_reports, monkeypatch, when):
    setup = host_reports
    setup.result.report_json()
    if when == "after-read":
        setup.path.write_bytes(b"{}")
    elif when == "removed":
        setup.path.unlink()
    else:
        put = integration_run._bundle_put
        def drifting_put(*args):
            result = put(*args)
            setup.path.write_bytes(b"{}")
            return result
        monkeypatch.setattr(integration_run, "_bundle_put", drifting_put)
    with pytest.raises(integration_run.IntegrationRunError, match="drifted|changed|disappeared"):
        integration_run._report_source(setup.result)

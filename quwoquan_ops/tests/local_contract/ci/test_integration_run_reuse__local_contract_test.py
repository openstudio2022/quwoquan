# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t2
"""`make integrate REUSE=1` 的 candidate/Alpha 事实复用合同。

复用只按 exact 身份（commit、tree、expectedParent、ImpactPlan digest、profile）精确匹配，并要求既有
Alpha 事实通过 canonical 校验；任一漂移、校验失败或事实缺失都视为不存在，不按时间窗或分支名复用。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
    }
    body.update(overrides)
    path = store / "environment-execution/acceptance" / candidate_id.removeprefix("sha256:") / f"{environment}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, sort_keys=True) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # canonical 校验器在真实链路里重验签名与 evidence refs；这里只保留其「校验失败即不可复用」契约，
    # 用 payload 自身的 `__invalid` 标记模拟过期/篡改。
    def fake_validate(payload, *, store_root, verify_references):
        assert verify_references is True and store_root == tmp_path
        if payload.get("__invalid"):
            raise integration_run.EnvironmentSchedulerError("ENVIRONMENT_SCHEDULER.ACCEPTANCE_EXPIRED", "acceptance fact is expired")
        return dict(payload)

    monkeypatch.setattr(integration_run, "validate_environment_acceptance_fact", fake_validate)
    return tmp_path


def _lookup(store: Path, **overrides: object):
    params: dict[str, object] = {"store": store, "commit": COMMIT, "tree": TREE, "parent": PARENT, "impact_plan_digest": IMPACT, "profile": PROFILE}
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

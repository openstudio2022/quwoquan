# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-003
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

from quwoquan_ops.ci import environment_scheduler as scheduler


def _request(store: Path, environment: str) -> dict[str, str]:
    body = {"schema": "quwoquan_ops.exact_integration_candidate.v1", "commit": "a" * 40, "tree": "b" * 40, "impactPlanDigest": "sha256:" + "c" * 64}
    body["candidateId"] = scheduler.canonical_digest(body)
    candidate = scheduler.write_create_once(store / "candidate.json", body)
    path = scheduler.create_execution_request(store_root=store, candidate_ref={"ref": "candidate.json", "digest": scheduler.exact_file_digest(candidate)}, environment=environment, impact_plan_digest=body["impactPlanDigest"], priority=1)
    return scheduler.request_exact_ref(store, path)


def _claim(store: str, deploy: str, ref: dict[str, str], start: object, results: object) -> None:
    os.environ["QWQ_DEPLOY_WORK_ROOT"] = deploy
    assert start.wait(10)
    try:
        claim = scheduler.claim_execution_request(store_root=Path(store), request_ref=ref)
        results.put(claim["claimId"])
    except scheduler.EnvironmentSchedulerError as error:
        results.put(error.code)


def test_claim_one_winner_and_no_dead_owner_takeover(tmp_path: Path, monkeypatch: object) -> None:
    store, deploy = tmp_path / "facts", tmp_path / "deploy"
    ref = _request(store, "beta")
    ctx = multiprocessing.get_context("spawn")
    start, results = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_claim, args=(str(store), str(deploy), ref, start, results)) for _ in range(2)]
    for worker in workers:
        worker.start()
    start.set()
    values = [results.get(timeout=12) for _ in workers]
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    assert sum(value.startswith("sha256:") for value in values) == 1
    assert "ENVIRONMENT_SCHEDULER.EXECUTION_IN_USE" in values
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy))
    try:
        scheduler.claim_execution_request(store_root=store, request_ref=ref)
    except scheduler.EnvironmentSchedulerError as error:
        assert error.code == "ENVIRONMENT_SCHEDULER.EXECUTION_IN_USE"
    else:
        raise AssertionError("dead owner must not release execution authority")
    assert scheduler.select_next_request(store_root=store, request_refs=[ref]) is None
    gamma = _request(store, "gamma")
    claim = scheduler.claim_execution_request(store_root=store, request_ref=gamma)
    assert claim["target"] == "gamma-local"


def test_execute_exact_claim_closes_only_after_success(tmp_path: Path, monkeypatch: object) -> None:
    import argparse
    import subprocess
    from quwoquan_ops.cli import environment_execution as executor
    store = tmp_path / "facts"
    ref = _request(store, "beta")
    claim = scheduler.claim_execution_request(store_root=store, request_ref=ref)
    observed = []
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        observed.append((argv, kwargs))
        assert Path(claim["path"]).exists()
        return subprocess.CompletedProcess(argv, 0, "{}", "")
    monkeypatch.setattr(executor.subprocess, "run", run)
    args = argparse.Namespace(store_root=store, repository=Path(__file__).resolve().parents[4], request=ref, claim_id=claim["claimId"], operation="up")
    result = executor._handle_execute(args)
    assert result["terminal"] == "executed"
    assert observed[0][0][-3:] == ["--target", "beta-local", "--skip-app"]
    assert observed[0][1]["env"]["QWQ_ENVIRONMENT_EXECUTION_CLAIM_ID"] == claim["claimId"]
    assert observed[0][1]["pass_fds"] == (int(observed[0][1]["env"]["QWQ_ENVIRONMENT_EXECUTION_FD"]),)
    assert not Path(claim["path"]).exists()


def test_execute_failure_and_supersede_never_allow_replay(tmp_path: Path, monkeypatch: object) -> None:
    import argparse
    import subprocess
    import pytest
    from quwoquan_ops.cli import environment_execution as executor
    store = tmp_path / "facts"
    ref = _request(store, "beta")
    claim = scheduler.claim_execution_request(store_root=store, request_ref=ref)
    monkeypatch.setattr(executor.subprocess, "run", lambda argv, **_: subprocess.CompletedProcess(argv, 9, "", ""))
    args = argparse.Namespace(store_root=store, repository=Path(__file__).resolve().parents[4], request=ref, claim_id=claim["claimId"], operation="up")
    assert executor._handle_execute(args)["terminal"] == "GATE_BLOCK"
    assert Path(claim["path"]).exists()
    with pytest.raises(executor.EnvironmentExecutionError, match="RECONCILE_REQUIRED"):
        executor._handle_execute(args)

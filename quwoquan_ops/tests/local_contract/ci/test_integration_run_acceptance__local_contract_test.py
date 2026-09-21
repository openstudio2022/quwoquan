# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
"""integration 预检只拦 HEAD...candidate 重叠脏文件。"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli.integration_run_acceptance import preflight_identity
from quwoquan_ops.cli.integration_run_bundle import IntegrationRunError
from quwoquan_ops.cli.lib.dirty_worktree import overlapping_dirty_paths, parse_porcelain_z


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise IntegrationRunError("INTEGRATION_RUN.GIT", completed.stderr or completed.stdout)
    return completed.stdout.rstrip("\n\r")


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    target = tmp_path / "integration"
    remote = tmp_path / "hub.git"
    target.mkdir()
    git(target, "init", "-b", "dev1.0")
    git(target, "config", "user.name", "Test")
    git(target, "config", "user.email", "test@example.com")
    (target / "owned.txt").write_text("before\n")
    (target / "other.txt").write_text("other\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "parent")
    parent = git(target, "rev-parse", "HEAD")
    git(tmp_path, "init", "--bare", "-b", "dev1.0", str(remote))
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "-q", "origin", "dev1.0")
    (target / "owned.txt").write_text("after\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "candidate")
    commit = git(target, "rev-parse", "HEAD")
    git(target, "reset", "--hard", parent)
    return target, parent, commit


def bind_git(repo: Path):
    def runner(*args: str) -> str:
        return git(repo, *args)

    def is_ancestor(parent: str, commit: str) -> bool:
        return subprocess.run(
            ["git", "merge-base", "--is-ancestor", parent, commit], cwd=repo, check=False,
        ).returncode == 0

    return runner, is_ancestor


def args_for(commit: str) -> argparse.Namespace:
    return argparse.Namespace(
        candidate=commit, remote="origin", baseline=None, mode="integrate", validate_bundle_only=True,
    )


def test_published_mode_keeps_normal_acceptance_empty_range_protection(tmp_path: Path, monkeypatch) -> None:
    from quwoquan_ops.cli.integration_run_acceptance import published_identity, validate_mode_inputs
    from quwoquan_ops.ci.scoped_candidate import core
    from quwoquan_ops.ci.scoped_candidate import exact_digest
    import json
    target, parent, commit = make_repo(tmp_path)
    git(target, "reset", "--hard", commit)
    git(target, "push", "origin", "dev1.0")
    normal = args_for(commit); normal.mode = "acceptance"
    runner, is_ancestor = bind_git(target)
    with pytest.raises(IntegrationRunError, match="NOTHING_TO_ACCEPT"):
        preflight_identity(normal, git=runner, is_ancestor=is_ancestor)
    store = tmp_path / "store"; store.mkdir()
    def write(name, body):
        (store/name).write_text(json.dumps(body))
        return {"ref": name, "digest": exact_digest(store/name)}
    candidate = {"commit": commit, "tree": git(target, "rev-parse", "HEAD^{tree}"), "expectedParent": parent}
    candidate["candidateId"] = exact_digest(candidate)
    cref = write("candidate.json", candidate)
    admission = {"candidate": cref, "admissionId": "sha256:"+"a"*64}
    aref = write("admission.json", admission)
    result = {"terminal": "published", "targetRef": "refs/heads/dev1.0", "admission": aref,
              "admissionId": admission["admissionId"], "beforeOid": parent, "afterOid": commit, "readbackOid": commit}
    result["publishResultId"] = exact_digest(result)
    rref = write("published.json", result)
    monkeypatch.setattr(core, "_validated_admission", lambda *a: admission)
    args = argparse.Namespace(mode="published-validation", candidate_ref=cref['ref']+'='+cref['digest'],
        publish_result=rref['ref']+'='+rref['digest'], remote="origin", publish=False,
        acceptance_bundle=None, baseline="", reuse=False, validate_bundle_only=False)
    validate_mode_inputs(args)
    assert published_identity(args, repository=target, store=store, policy=Path("unused"), git=runner)[1]["commit"] == commit
    runtime_wip = target / "quwoquan_data" / "uncommitted.py"
    runtime_wip.parent.mkdir(); runtime_wip.write_text("foreign work")
    assert published_identity(args, repository=target, store=store, policy=Path("unused"), git=runner)[1]["commit"] == commit
    assert runtime_wip.read_text() == "foreign work"
    (target / "owned.txt").write_text("dirty overlap\n")
    with pytest.raises(IntegrationRunError, match="DIRTY_WORKTREE"):
        published_identity(args, repository=target, store=store, policy=Path("unused"), git=runner)
    runtime_wip.unlink()
    git(target, "checkout", "--", "owned.txt")
    (store/"published.json").write_text("{}")
    with pytest.raises(core.ScopedCandidateError, match="STALE"):
        published_identity(args, repository=target, store=store, policy=Path("unused"), git=runner)
    rref = write("published.json", result)
    git(target, "reset", "--hard", parent)
    with pytest.raises(IntegrationRunError, match="PUBLISHED_IDENTITY_INVALID"):
        published_identity(args, repository=target, store=store, policy=Path("unused"), git=runner)


@pytest.mark.parametrize("fail_at", [None, "beta"])
def test_published_chain_uses_same_candidate_and_stops_before_failed_issue(tmp_path, monkeypatch, fail_at):
    from quwoquan_ops.cli import integration_run as run
    from quwoquan_ops.ci import environment_scheduler as scheduler
    from contextlib import contextmanager
    store = tmp_path / "store"; store.mkdir()
    candidate = {"candidateId": "sha256:"+"a"*64, "commit": "b"*40, "tree": "c"*40,
                 "expectedParent": "d"*40, "impactPlanDigest": "sha256:"+"e"*64}
    cref = {"ref": "candidate.json", "digest": "sha256:"+"f"*64}
    monkeypatch.setattr(run, "_store", lambda: store)
    monkeypatch.setattr(run, "published_identity", lambda *a, **k: (cref, candidate, {"publishResultId": "published"}))
    monkeypatch.setattr(run, "_impact_plan", lambda **k: ({"plan_digest": candidate["impactPlanDigest"], "scopes": []}, tmp_path / "plan.json"))
    monkeypatch.setattr(run, "_output_ref", lambda p: str(p))
    monkeypatch.setattr(run, "_acceptance_release_inputs", lambda args: {})
    requests = {}; calls = []; issued = []
    def request(**kw):
        assert kw["candidate_ref"] == cref
        p=store/(kw["environment"]+".request"); requests[p.name]=kw["environment"]; return p
    monkeypatch.setattr(run, "create_execution_request", request)
    monkeypatch.setattr(run, "request_exact_ref", lambda s,p: {"ref":p.name,"digest":"sha256:"+"1"*64})
    @contextmanager
    def fenced(**kw):
        calls.append("claim:"+requests[kw["request_ref"]["ref"]]); yield {}
        calls.append("closed:"+requests[kw["request_ref"]["ref"]])
    monkeypatch.setattr(scheduler, "execution_fence", fenced)
    def execute(**kw):
        env=kw["environment"]; calls.append("execute:"+env)
        assert kw["candidate"] == {k:candidate[k] for k in ("candidateId","commit","tree")}
        if env == fail_at: raise IntegrationRunError("INTEGRATION_RUN.VERIFY_FAILED", "first failure")
        summary["environments"][env]={}
        return {"cases":[],"named":{},"readiness":tmp_path/env}
    monkeypatch.setattr(run, "_run_environment", execute)
    def issue(**kw):
        env=requests[kw["request_ref"]["ref"]]
        assert "closed:"+env in calls and kw["status"]=="passed"
        assert kw["predecessor"] == (None if not issued else {"ref":issued[-1]+".json","digest":"sha256:"+"2"*64})
        issued.append(env); return store/(env+".json")
    monkeypatch.setattr(run, "issue_environment_acceptance_fact", issue)
    monkeypatch.setattr(run, "exact_file_digest", lambda p: "sha256:"+"2"*64)
    args=argparse.Namespace(app_platform="ios",ios_device_id="explicit-test-device",profile="integration",fact_ttl_hours=1,signer_identity="test")
    summary={"runId":"live-attempt","environments":{}}
    if fail_at:
        with pytest.raises(IntegrationRunError,match="first failure"):
            run._published_environment_chain(args,phases=run.Phases(),summary=summary,run_dir=tmp_path,signer=lambda x:"unused")
        assert issued==["alpha"] and "execute:gamma" not in calls
    else:
        run._published_environment_chain(args,phases=run.Phases(),summary=summary,run_dir=tmp_path,signer=lambda x:"unused")
        assert issued==["alpha","beta","gamma"] and summary["terminal"]=="environments_passed"


def test_offline_ios_syncs_missing_dependency_bundle_once(tmp_path, monkeypatch):
    from quwoquan_ops.cli import integration_run as run
    calls = []
    receipt_dir = tmp_path / "uat"
    receipt_dir.mkdir()
    (receipt_dir / "receipt.json").write_text("{}")
    def stackctl(*args, **kw):
        calls.append(args[0])
        if args[0] == "app-content-uat":
            if "app-dependency-sync" not in calls:
                return run.StackctlResult("uat", {"exitCode": 2, "firstBlocker": "APP.DEPENDENCY.bundle_missing", "summary": "GATE_BLOCK"}, "")
            return run.StackctlResult("uat", {"exitCode": 0, "reportDir": str(receipt_dir)}, "")
        if args[0] == "app-dependency-sync":
            return run.StackctlResult("sync", {"exitCode": 0}, "")
        raise AssertionError(args)
    monkeypatch.setattr(run, "_stackctl", stackctl)
    monkeypatch.setattr(run, "_evidence_location", lambda p: (tmp_path, "receipt.json"))
    monkeypatch.setattr(run, "exact_file_digest", lambda p: "sha256:" + "2" * 64)
    monkeypatch.setattr(run, "_bundle_put", lambda *a, **k: None)
    monkeypatch.setattr(run, "_store", lambda: tmp_path)
    monkeypatch.setattr(run, "_bundle_bytes", lambda *a, **k: b"{}")
    import quwoquan_ops.cli.lib.integration_app_launch as launch
    monkeypatch.setattr(launch, "offline_receipt_evidence", lambda **k: {"files": [], "cases": []})
    args = argparse.Namespace(app_platform="ios", ios_device_id="device", android_device_id="")
    run._alpha_offline_pages(
        candidate={"candidateId": "sha256:" + "a" * 64, "commit": "b" * 40, "tree": "c" * 40},
        candidate_ref={"ref": "c.json", "digest": "sha256:" + "f" * 64},
        args=args, run_dir=tmp_path, phases=run.Phases(),
    )
    assert calls == ["app-content-uat", "app-dependency-sync", "app-content-uat"]


def test_overlapping_dirty_paths_include_parent_child() -> None:
    assert overlapping_dirty_paths(["gamma/wip.txt"], ["owned.txt"]) == ()
    assert overlapping_dirty_paths(["owned.txt"], ["owned.txt"]) == ("owned.txt",)
    assert overlapping_dirty_paths(["dir/file.txt"], ["dir"]) == ("dir/file.txt",)
    assert parse_porcelain_z(" M owned.txt\0?? gamma.txt\0") == ("owned.txt", "gamma.txt")


def test_preflight_allows_non_overlapping_dirty_and_untracked(tmp_path: Path) -> None:
    target, _parent, commit = make_repo(tmp_path)
    (target / "other.txt").write_text("dirty other\n")
    (target / "gamma.wip").write_text("untracked\n")
    runner, is_ancestor = bind_git(target)
    identity = preflight_identity(args_for(commit), git=runner, is_ancestor=is_ancestor)
    assert identity["commit"] == commit
    assert identity["parent"] == git(target, "rev-parse", "HEAD")


def test_preflight_blocks_overlapping_dirty_path(tmp_path: Path) -> None:
    target, _parent, commit = make_repo(tmp_path)
    (target / "owned.txt").write_text("dirty overlap\n")
    runner, is_ancestor = bind_git(target)
    with pytest.raises(IntegrationRunError, match="DIRTY_WORKTREE"):
        preflight_identity(args_for(commit), git=runner, is_ancestor=is_ancestor)


def test_preflight_blocks_overlapping_untracked_path(tmp_path: Path) -> None:
    target, parent, commit = make_repo(tmp_path)
    git(target, "reset", "--hard", commit)
    (target / "added.txt").write_text("in candidate\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "add path")
    added = git(target, "rev-parse", "HEAD")
    git(target, "reset", "--hard", parent)
    (target / "added.txt").write_text("untracked overlap\n")
    runner, is_ancestor = bind_git(target)
    with pytest.raises(IntegrationRunError, match="DIRTY_WORKTREE"):
        preflight_identity(args_for(added), git=runner, is_ancestor=is_ancestor)

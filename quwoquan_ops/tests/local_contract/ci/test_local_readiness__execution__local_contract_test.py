"""Local readiness immutable execution, worker, and inspection contracts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.local_readiness.core import (  # noqa: E402
    LocalReadinessError,
    _run_check,
    _state_root,
    enqueue_paths,
    inspect_state,
    parse_push_updates,
    plan_readiness,
    run_readiness,
    source_execution_root,
    staged_paths,
    worker_once,
)
from lib.local_readiness.queue import clear_queue_exact  # noqa: E402
from quwoquan_ops.ci.local_readiness_planner import build_impact_plan  # noqa: E402


def _repo() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory()


def _init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "checkout", "-qb", "dev1.0"], cwd=path, check=True)
    (path / "source.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=path, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "base",
        ],
        cwd=path,
        check=True,
    )


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", message],
        cwd=repo,
        check=True,
    )
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_dirty_unstaged_byte_cannot_affect_staged_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        source = repo / "source.txt"
        source.write_text("index-byte\n", encoding="utf-8")
        subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
        source.write_text("dirty-byte\n", encoding="utf-8")
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="staged")

        observed: list[str] = []
        monkeypatch.setattr(
            "lib.local_readiness.core._run_check",
            lambda check, log_path, *, repo_root, execution_env=None, timeout_seconds=None: (
                observed.append((repo_root / "source.txt").read_text(encoding="utf-8"))
                or {"id": check["id"], "status": "PASS", "exit_code": 0, "elapsed_ms": 0, "log": str(log_path)}
            ),
        )
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["status"] == "PASS"
        assert receipt["source_execution"] == "immutable_capsule"
        assert observed == ["index-byte\n"]
        assert source.read_text(encoding="utf-8") == "dirty-byte\n"


def test_staged_capsule_materializes_exact_add_delete_rename_mode_and_symlink() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "delete.txt").write_text("delete\n", encoding="utf-8")
        (repo / "rename.txt").write_text("rename\n", encoding="utf-8")
        (repo / "target.txt").write_text("target\n", encoding="utf-8")
        os.symlink("target.txt", repo / "link.txt")
        _commit_all(repo, "fixture")
        (repo / "added.txt").write_text("added\n", encoding="utf-8")
        (repo / "delete.txt").unlink()
        subprocess.run(["git", "mv", "rename.txt", "renamed.txt"], cwd=repo, check=True)
        subprocess.run(["chmod", "+x", "source.txt"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        (repo / "added.txt").write_text("dirty-after-index\n", encoding="utf-8")
        plan = plan_readiness(level="fast", paths=staged_paths(repo), repo_root=repo, mode="staged")
        state = repo / "state"
        with source_execution_root(repo_root=repo, mode="staged", state_root=_state_root(state), fingerprint=plan["fingerprint"]) as (capsule, env, entries):
            assert (capsule / "added.txt").read_text(encoding="utf-8") == "added\n"
            assert not (capsule / "delete.txt").exists()
            assert not (capsule / "rename.txt").exists()
            assert (capsule / "renamed.txt").read_text(encoding="utf-8") == "rename\n"
            assert os.access(capsule / "source.txt", os.X_OK)
            assert (capsule / "link.txt").is_symlink()
            assert os.readlink(capsule / "link.txt") == "target.txt"
            assert Path(env["GIT_DIR"]).parent.parent == _state_root(state) / "process/materializations"
            assert Path(env["GIT_DIR"]).is_dir()
            assert any(entry["path"] == "added.txt" for entry in entries)
        assert not list((state / "process/materializations").glob("*-*"))


def test_commit_and_push_capsules_execute_exact_commit_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        source = repo / "source.txt"
        source.write_text("commit-byte\n", encoding="utf-8")
        previous = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        head = _commit_all(repo, "candidate")
        source.write_text("dirty-byte\n", encoding="utf-8")
        monkeypatch.setattr(
            "lib.local_readiness.core._run_check",
            lambda check, log_path, *, repo_root, execution_env=None, timeout_seconds=None: {
                "id": check["id"],
                "status": "PASS" if (repo_root / "source.txt").read_text(encoding="utf-8") == "commit-byte\n" else "FAIL",
                "exit_code": 0 if (repo_root / "source.txt").read_text(encoding="utf-8") == "commit-byte\n" else 1,
                "elapsed_ms": 0,
                "log": str(log_path),
            },
        )
        commit_plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="commit")
        assert run_readiness(commit_plan, repo_root=repo, state_root=repo / "commit-state")["status"] == "PASS"
        updates = parse_push_updates(f"refs/heads/dev1.0 {head} refs/heads/dev1.0 {previous}\n")
        push_plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="push", push_updates=updates)
        assert run_readiness(push_plan, repo_root=repo, push_updates=updates, state_root=repo / "push-state")["status"] == "PASS"


def test_source_drift_during_worktree_run_stales_receipt_without_green(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        def drift(check, log_path, *, repo_root, execution_env=None, timeout_seconds=None):
            (repo_root / "source.txt").write_text("drift\n", encoding="utf-8")
            return {"id": check["id"], "status": "PASS", "exit_code": 0, "elapsed_ms": 0, "log": str(log_path)}

        monkeypatch.setattr("lib.local_readiness.core._run_check", drift)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["status"] == "FAIL"
        assert receipt["input_stable"] is False
        assert not (state / "process/receipts/current").exists()


def test_capsule_rejects_symlink_escape_and_cleans_process_root() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        os.symlink("../../outside", repo / "escape")
        subprocess.run(["git", "add", "escape"], cwd=repo, check=True)
        plan = plan_readiness(level="fast", paths=["escape"], repo_root=repo, mode="staged")
        state = repo / "state"
        with pytest.raises(LocalReadinessError, match="symlink target 越出"):
            with source_execution_root(repo_root=repo, mode="staged", state_root=_state_root(state), fingerprint=plan["fingerprint"]):
                pass
        materializations = state / "process/materializations"
        assert not list(materializations.iterdir())


def test_data_release_readiness_is_local_and_promotion_does_not_repeat_data_gates() -> None:
    plan = build_impact_plan(
        [
            "quwoquan_data/tests/local_contract/execution/"
            "test_execution_kernel__minimal__contract__local_contract_test.py"
        ],
        level="release",
    )
    assert plan["deferred"] == []
    assert any(
        check["id"] == "release:data"
        and check["command"] == ["bash", "quwoquan_ops/gate/gate_repo.sh", "--scope", "data"]
        for check in plan["checks"]
    )

    workflow = __import__("yaml").safe_load(
        (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]
    # 回同步走 integration FF 通道（make promotion-backsync），Gate 只剩两 job。
    assert list(jobs) == ["promotion_verify", "main_source_seal"]
    assert jobs["promotion_verify"]["if"] == (
        "${{ github.event_name == 'pull_request' || github.event_name == 'pull_request_review' }}"
    )
    assert jobs["main_source_seal"]["if"] == (
        "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    )
    promotion_steps = json.dumps(jobs["promotion_verify"]["steps"], ensure_ascii=False)
    main_steps = json.dumps(jobs["main_source_seal"]["steps"], ensure_ascii=False)
    assert "PromotionAdmissionReceipt" in promotion_steps
    assert "post-merge MainSourceSeal: not issued on pull_request" in promotion_steps
    assert "main-seal" not in promotion_steps
    assert "main-seal" in main_steps
    assert "MainSourceSeal" in main_steps
    serialized = json.dumps(jobs, ensure_ascii=False)
    for token in ("quwoquan_data", "gate_repo.sh", "pytest", "stackctl.py package"):
        assert token not in serialized

def test_failed_queue_item_backs_off_does_not_starve_and_dead_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "z-ready.txt").write_text("ready\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt", "z-ready.txt"], state_root=state)
        original_run = __import__("lib.local_readiness.core", fromlist=["run_readiness"]).run_readiness

        def selective(plan, **kwargs):
            if plan["paths"] == ["source.txt"]:
                raise LocalReadinessError("deterministic failure")
            return original_run(plan, **kwargs)

        monkeypatch.setattr("lib.local_readiness.core.run_readiness", selective)
        first = worker_once(state_root=state, debounce_seconds=0)
        assert first["status"] == "PENDING"
        assert first["processed"] == ["source.txt", "z-ready.txt"]
        items = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))["items"]
        assert [item["path"] for item in items] == ["source.txt"]
        failed = items[0]
        assert failed["attempt_count"] == 1
        assert failed["next_eligible_at"] is not None
        assert failed["last_error_digest"].startswith("sha256:")
        assert failed["evidence_fingerprint_ref"].startswith("evidence-fingerprint-v1:")
        identity = (failed["evidence_fingerprint_ref"], failed["check_identity_digest"])
        payload = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))
        payload["items"][0]["next_eligible_at"] = "2999-01-01T00:00:00+00:00"
        (state / "process/deferred-queue.json").write_text(json.dumps(payload), encoding="utf-8")
        backing_off = worker_once(state_root=state, debounce_seconds=0)
        assert backing_off["status"] == "BACKING_OFF"
        for _attempt in range(failed["max_attempts"] - 1):
            payload = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))
            payload["items"][0]["next_eligible_at"] = "2000-01-01T00:00:00+00:00"
            (state / "process/deferred-queue.json").write_text(json.dumps(payload), encoding="utf-8")
            terminal = worker_once(state_root=state, debounce_seconds=0)
        assert terminal["status"] == "GATE_BLOCK"
        inspected = __import__("lib.local_readiness.core", fromlist=["inspect_state"]).inspect_state(state_root=state)
        assert inspected["readiness"] == "ADVISORY"
        assert inspected["queue_closure"]["blocking"] == []
        assert inspected["dead_letter"][0]["terminal"]["code"] == "LOCAL_READINESS.RETRY_EXHAUSTED"
        assert (inspected["dead_letter"][0]["evidence_fingerprint_ref"], inspected["dead_letter"][0]["check_identity_digest"]) == identity
        pointer_root = state / "process/receipts/current"
        failed_receipts = [] if not pointer_root.exists() else [
            json.loads(Path(json.loads(pointer.read_text(encoding="utf-8"))["receipt"]).read_text(encoding="utf-8"))
            for pointer in pointer_root.glob("*.json")
        ]
        assert all(receipt.get("paths") != ["source.txt"] for receipt in failed_receipts)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _forking_sleep_command(child_pid_path: Path) -> list[str]:
    fixture = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    return [sys.executable, "-c", fixture]


def test_readiness_check_timeout_kills_forked_process_group(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    check = {
        "id": "focused:hanging-fixture", "scope": "spec_contract",
        "phase": "focused", "command": _forking_sleep_command(child_pid_path),
        "cwd": ".", "resources": ["fixture"], "timeout_seconds": 1,
    }

    result = _run_check(check, tmp_path / "timeout.log", repo_root=ROOT)

    assert result["status"] == "FAIL"
    assert result["exit_code"] == 124
    assert result["timed_out"] is True
    assert result["termination_signal"] in {"SIGTERM", "SIGKILL"}
    assert result["outcome"] == "timeout"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    for _ in range(50):
        if not _pid_exists(child_pid):
            break
        import time as _time
        _time.sleep(0.02)
    assert not _pid_exists(child_pid)


def test_worker_budget_terminates_current_check_process_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        child_pid_path = tmp_path / "worker-child.pid"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        contract = __import__("lib.local_readiness.core", fromlist=["_load_contract"])._load_contract()
        contract["worker"]["wall_clock_budget_seconds"] = 2.0
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)
        enqueue_paths(["source.txt"], state_root=state)
        check = {
            "id": "focused:worker-hang", "scope": "spec_contract",
            "phase": "focused", "command": _forking_sleep_command(child_pid_path),
            "cwd": ".", "resources": ["fixture"], "timeout_seconds": 30,
        }
        canonical = build_impact_plan(["source.txt"], level="fast", repo_root=repo)
        canonical["checks"] = [check]
        monkeypatch.setattr(
            "lib.local_readiness.core.build_impact_plan",
            lambda paths, *, level, repo_root: {
                **canonical, "paths": list(paths), "level": level,
            },
        )
        started = __import__("time").monotonic()
        result = worker_once(state_root=state, debounce_seconds=0)
        elapsed = __import__("time").monotonic() - started

        assert elapsed < 6
        assert result["status"] == "PENDING"
        assert result["budget_exhausted"] is True
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        for _ in range(50):
            if not _pid_exists(child_pid):
                break
            __import__("time").sleep(0.02)
        assert not _pid_exists(child_pid)


def test_worker_once_honors_contract_item_cap_and_stable_order(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        for name in ("a.txt", "b.txt", "c.txt"):
            (repo / name).write_text(name + "\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        contract = __import__("lib.local_readiness.core", fromlist=["_load_contract"])._load_contract()
        contract["worker"]["max_items_per_run"] = 2
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)
        enqueue_paths(["c.txt", "a.txt", "b.txt"], state_root=state)
        queue_path = state / "process/deferred-queue.json"
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        for item in payload["items"]:
            item["enqueued_at"] = "2026-01-01T00:00:00+00:00"
            item["next_eligible_at"] = "2026-01-01T00:00:00+00:00"
        queue_path.write_text(json.dumps(payload), encoding="utf-8")

        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["processed"] == ["a.txt", "b.txt"]
        assert result["status"] == "PENDING"
        assert result["budget_exhausted"] is True
        assert [item["path"] for item in json.loads(queue_path.read_text())["items"]] == ["c.txt"]


def test_worker_wall_clock_budget_is_checked_before_next_item(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "later.txt").write_text("later\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        contract = __import__("lib.local_readiness.core", fromlist=["_load_contract"])._load_contract()
        contract["worker"]["max_items_per_run"] = 2
        contract["worker"]["wall_clock_budget_seconds"] = 1
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)
        enqueue_paths(["source.txt", "later.txt"], state_root=state)
        ticks = iter((0.0, 0.0, 0.0, 2.0))
        last_tick = [2.0]

        def monotonic() -> float:
            last_tick[0] = next(ticks, last_tick[0])
            return last_tick[0]

        monkeypatch.setattr("lib.local_readiness.worker.time.monotonic", monotonic)
        processed_by_runner: list[str] = []

        def consume(plan, **kwargs):
            assert 0 < kwargs["wall_clock_budget_seconds"] <= 1
            processed_by_runner.extend(plan["paths"])
            clear_queue_exact(plan["paths"], state_root=kwargs["state_root"])
            return {"status": "PASS"}

        monkeypatch.setattr("lib.local_readiness.core.run_readiness", consume)
        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["processed"] == processed_by_runner
        assert len(result["processed"]) == 1
        assert result["budget_exhausted"] is True
        assert result["status"] == "PENDING"


def test_inspect_exposes_backlog_oldest_and_failure_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "failed.txt").write_text("failed\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt", "failed.txt"], state_root=state)
        queue_path = state / "process/deferred-queue.json"
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        payload["items"][0]["enqueued_at"] = "2026-01-01T00:00:00+00:00"
        payload["items"][0]["next_eligible_at"] = "2026-01-01T00:00:00+00:00"
        payload["items"][0]["attempt_count"] = 1
        payload["items"][0]["last_error_digest"] = "sha256:" + "1" * 64
        queue_path.write_text(json.dumps(payload), encoding="utf-8")
        (repo / "source.txt").write_text("stale\n", encoding="utf-8")

        inspected = inspect_state(state_root=state)
        assert inspected["backlog_count"] == 2
        assert inspected["summary"]["pending_count"] == 2
        assert inspected["oldest_enqueued_at"] == "2026-01-01T00:00:00+00:00"
        assert inspected["oldest_age_seconds"] > 0
        assert inspected["failed_count"] == 1
        assert inspected["stale_count"] == 1
        assert inspected["running_count"] == 0
        assert len(inspected["queue"]["items"]) == 2
        assert inspected["queue_closure"]["enforcement"] == (
            "advisory_until_verified_consumer"
        )
        assert inspected["queue_closure"]["blocking"] == []
        assert {
            (item["classification"], item["path"])
            for item in inspected["queue_closure"]["advisories"]
        } == {
            ("exact-pending", "failed.txt"),
            ("foreign-pending", "source.txt"),
        }

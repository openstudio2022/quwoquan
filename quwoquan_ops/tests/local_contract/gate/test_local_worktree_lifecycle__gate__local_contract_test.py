# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t5
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t5
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t6
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t7
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t4
"""本地工作副本生命周期治理的行为级 local_contract。

决策表覆盖三件事：授权闸在两个执行面的不对等输出、滞留提醒的去重与不漏报、
hooks 安装自检与安装入口的路径解析回归。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
# 按目录加进 sys.path，而不是 `from quwoquan_ops.hooks import ...`：后者把 quwoquan_ops
# 当成真包导入，会在源码树留下 __pycache__，而仓库要求源码树缓存为零。
for extra in (ROOT / "quwoquan_ops/cli/lib", ROOT / "quwoquan_ops/hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import local_worktree_inventory as inventory  # noqa: E402
import worktree_authz_guard as guard  # noqa: E402
import worktree_merge_reminder as reminder  # noqa: E402

AUTHZ_SCRIPT = ROOT / "quwoquan_ops/hooks/worktree_authz_guard.py"
INSTALL_SCRIPT = ROOT / "quwoquan_ops/hooks/run_install_hooks.sh"
GATE_SCRIPT = ROOT / "quwoquan_ops/gate/verify_local_worktree_lifecycle.py"
REMINDER_GATE = ROOT / "quwoquan_ops/hooks/worktree_session_reminder_gate.sh"
ALLOWED = frozenset({"dev1.0", "main"})


@pytest.fixture(scope="module")
def policy() -> inventory.WorktreePolicy:
    return inventory.load_policy()


def _detect(command: str) -> guard.Detection | None:
    return guard.detect(command, allowed_branches=ALLOWED, repo_root=ROOT)


# --- GWT-001 创建授权闸 ---------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected_kind"),
    [
        ("git worktree add /tmp/probe", "worktree_add"),
        ("cd /tmp && git worktree add probe", "worktree_add"),
        ("git -C /elsewhere worktree add p2", "worktree_add"),
        ("git checkout -b feature/foo", "branch_create"),
        ("git switch -c hotfix", "branch_create"),
        ("git branch experiment", "branch_create"),
        ("git clone git@github.com-quwoquan:openstudio2022/quwoquan.git /tmp/y", "clone"),
    ],
)
def test_gwt_001_t1_identifies_creation_surface(command: str, expected_kind: str) -> None:
    detection = _detect(command)
    assert detection is not None, command
    assert detection.kind == expected_kind


@pytest.mark.parametrize(
    "command",
    [
        "git worktree list",
        "git worktree remove /tmp/x",
        "git worktree prune",
        "git status",
        "git checkout dev1.0",
        "git checkout -b dev1.0",
        "git checkout -b main",
        "git branch",
        "git branch -d stale",
        "git branch --show-current",
        "git clone https://github.com/flutter/flutter.git",
        "echo 'git worktree add' >> notes.md",
    ],
)
def test_gwt_001_t2_leaves_unrelated_commands_alone(command: str) -> None:
    """白名单分支、只读子命令与第三方 clone 不在识别面内。误伤会让这道闸很快被绕过。"""
    assert _detect(command) is None, command


def _run_guard(harness: str, command: str) -> dict[str, object]:
    payload = {"command": command} if harness == "cursor" else {"tool_input": {"command": command}}
    completed = subprocess.run(
        [sys.executable, str(AUTHZ_SCRIPT), "--harness", harness],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout or "{}")


def test_gwt_001_t3_two_harnesses_emit_their_own_protocol() -> None:
    """Cursor 升级为人工批准，Codex 只能拒绝——按能力分叉，不取交集也不取并集。"""
    command = "git worktree add /tmp/probe"
    cursor = _run_guard("cursor", command)
    codex = _run_guard("codex", command)

    assert cursor["permission"] == "ask"
    assert cursor["user_message"]
    hook_output = codex["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    # Codex 不支持 ask：返回它会被判为 hook 运行失败并放行工具调用。
    assert hook_output["permissionDecision"] != "ask"

    reason = hook_output["permissionDecisionReason"]
    assert "OPS.WORKTREE.NOT_AUTHORIZED" in reason
    assert "QWQ_WORKTREE_AUTHZ" in reason, "拒绝理由必须给出取得授权的确切方式"


def test_gwt_001_t4_explicit_authorization_passes_on_both_harnesses(policy) -> None:
    command = f'{policy.authorization_env_var}="用户同意排查" git worktree add /tmp/probe'
    assert guard.is_authorized(command, policy.authorization_env_var) is True
    assert _run_guard("cursor", command)["permission"] == "allow"
    assert _run_guard("codex", command) == {}

    unauthorized = "git worktree add /tmp/probe"
    assert guard.is_authorized(unauthorized, policy.authorization_env_var) is False
    assert guard.is_authorized(
        f"{policy.authorization_env_var}= git worktree add /tmp/probe", policy.authorization_env_var
    ) is False, "空理由不构成授权"


# --- GWT-002 滞留提醒 -----------------------------------------------------


def _copy(path: str, *, ahead: int = 0, dirty: int = 0, stashes: int = 0, epoch: int | None = None):
    return inventory.WorkCopy(
        path=path,
        kind="clone",
        branch="dev1.0",
        ahead=ahead,
        dirty=dirty,
        stashes=stashes,
        oldest_unmerged_epoch=epoch,
        probe_error="",
    )


def test_gwt_002_t1_reports_path_counts_and_stale_days(policy) -> None:
    now = 1_000_000_000
    overdue_epoch = now - int((policy.unmerged_reminder_after_days + 2) * 86400)
    copies = [_copy("/tmp/stale", ahead=3, dirty=12, stashes=1, epoch=overdue_epoch)]

    summary = inventory.summarize(copies, policy, now=now)
    assert summary["withUnmergedWork"] == 1
    assert summary["overdue"] == 1
    item = summary["items"][0]
    assert item["path"] == "/tmp/stale"
    assert item["ahead"] == 3 and item["dirty"] == 12 and item["stashes"] == 1
    assert item["staleDays"] == pytest.approx(policy.unmerged_reminder_after_days + 2, abs=0.1)

    message = reminder.build_message(summary, hooks_ok=True, policy=policy)
    assert policy.failure_code("unmerged_overdue") in message
    assert "/tmp/stale" in message


def test_gwt_002_t2_clean_copies_never_appear(policy) -> None:
    """三类未合入事实全为空的副本不产生提醒。它存在但没压着任何工作。"""
    now = 1_000_000_000
    summary = inventory.summarize([_copy("/tmp/clean")], policy, now=now)

    assert summary["totalWorkCopies"] == 1
    assert summary["withUnmergedWork"] == 0
    assert summary["items"] == []
    assert reminder.build_message(summary, hooks_ok=True, policy=policy) == ""


def test_gwt_002_t3_threshold_splits_soft_and_strong(policy) -> None:
    now = 1_000_000_000
    threshold = policy.unmerged_reminder_after_days
    fresh = _copy("/tmp/fresh", dirty=1, epoch=now - int((threshold - 1) * 86400))
    aged = _copy("/tmp/aged", dirty=1, epoch=now - int((threshold + 1) * 86400))

    assert fresh.is_overdue(policy, now=now) is False
    assert aged.is_overdue(policy, now=now) is True

    summary = inventory.summarize([fresh, aged], policy, now=now)
    assert summary["withUnmergedWork"] == 2
    assert summary["overdue"] == 1


def test_gwt_002_t4_dedup_never_suppresses_new_overdue(policy) -> None:
    """提交后必提醒；会话按间隔去重；新超期项立即穿透；状态丢失只多提醒一次。"""
    now = 1_000_000_000
    interval = policy.reminder_min_interval_hours
    recent = {"at": now - 60, "overduePaths": ["/tmp/known"]}

    assert reminder.should_emit(recent, reason="commit", overdue_paths=[], interval_hours=interval, now=now) is True
    assert (
        reminder.should_emit(recent, reason="session", overdue_paths=["/tmp/known"], interval_hours=interval, now=now)
        is False
    )
    assert (
        reminder.should_emit(recent, reason="session", overdue_paths=["/tmp/new"], interval_hours=interval, now=now)
        is True
    ), "新出现的超期副本不得被 24h 去重吞掉"

    stale_state = {"at": now - interval * 3600 - 1, "overduePaths": []}
    assert reminder.should_emit(stale_state, reason="session", overdue_paths=[], interval_hours=interval, now=now) is True
    assert reminder.should_emit({}, reason="session", overdue_paths=[], interval_hours=interval, now=now) is True


def _run_git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_gwt_002_t5_shared_stash_never_fakes_staleness(tmp_path: Path, policy) -> None:
    """未合入事实必须归属到真正持有它的副本。

    stash 存在 common dir，主 worktree 与全部 linked worktree 共享同一份。把它记到副本
    头上，一个刚创建、自身完全干净的 worktree 会立刻显示为滞留数天——实测出现过 2.5 天
    的假滞留。假报警几次之后，整条提醒就不再被阅读。
    """
    main = tmp_path / "main"
    main.mkdir()
    _run_git(main, "init", "-q", "-b", "dev1.0")
    (main / "seed.txt").write_text("v1", encoding="utf-8")
    _run_git(main, "add", "seed.txt")
    _run_git(main, "commit", "-qm", "seed")

    (main / "seed.txt").write_text("v2", encoding="utf-8")
    _run_git(main, "stash", "push", "-q", "-m", "shared")
    assert _run_git(main, "stash", "list", "--format=%ct"), "前置条件：主仓库确有 stash"

    linked = tmp_path / "linked"
    _run_git(main, "worktree", "add", "-q", "--detach", str(linked), "HEAD")

    as_linked = inventory.probe_work_copy(
        linked, kind="linked_worktree", branch="", policy=policy, repo_root=main
    )
    assert as_linked.probe_error == ""
    assert as_linked.stashes == 0, "共享 stash 不归 linked worktree"
    assert as_linked.ahead == 0, "HEAD 可达主仓库集成分支即为已合入"
    assert as_linked.has_unmerged is False
    assert as_linked.oldest_unmerged_epoch is None

    # 同一路径按 clone 判定时 stash 计入，证明差异来自归属规则而不是读不到 stash。
    as_clone = inventory.probe_work_copy(linked, kind="clone", branch="", policy=policy, repo_root=main)
    assert as_clone.stashes == 1


def _run_reminder_gate(output_root: Path):
    return subprocess.run(
        ["bash", str(REMINDER_GATE)],
        input='{"command":"ls"}',
        capture_output=True,
        text=True,
        env={**os.environ, "QWQ_OUTPUT_ROOT": str(output_root)},
        cwd=ROOT,
    )


def test_gwt_002_t6_cursor_fallback_channel_stays_silent_until_due(tmp_path: Path) -> None:
    """Cursor 的 sessionStart 不声明任何输出字段，提醒回落到 beforeShellExecution。

    该通道对每条 shell 命令都触发，未到时点必须只返回放行、不带任何消息；无论是否到点
    都必须放行，因为提醒是告知而不是阻断。
    """
    cache = tmp_path / "env/repo/local/worktree-governance/cache"
    cache.mkdir(parents=True)
    sentinel = cache / "next-reminder-at"

    sentinel.write_text(f"{int(time.time()) + 86_400}\n", encoding="utf-8")
    early = _run_reminder_gate(tmp_path)
    assert early.returncode == 0
    assert json.loads(early.stdout) == {"permission": "allow"}, "未到时点必须纯短路，不带消息"

    sentinel.write_text("0\n", encoding="utf-8")
    due = _run_reminder_gate(tmp_path)
    assert due.returncode == 0
    assert json.loads(due.stdout)["permission"] == "allow"


def test_gwt_002_t7_short_circuit_never_inlines_the_interval(tmp_path: Path, policy) -> None:
    """短路判断只读一个 epoch sentinel，提醒间隔因此仍然只有策略文件一个来源。

    把间隔写进 shell 会让它成为第二真相源：改策略文件不再改变实际提醒频率，而两处
    不一致时没有任何门禁会红。
    """
    source = REMINDER_GATE.read_text(encoding="utf-8")
    for literal in ("86400", "86_400", "3600", str(policy.reminder_min_interval_hours * 3600)):
        assert literal not in source, f"提醒间隔不得内联进 shell（发现 {literal}）"

    cache = tmp_path / "env/repo/local/worktree-governance/cache"
    cache.mkdir(parents=True)
    (cache / "next-reminder-at").write_text("0\n", encoding="utf-8")
    assert _run_reminder_gate(tmp_path).returncode == 0

    # sentinel 由 python 侧按策略间隔写回，内容是纯 epoch，shell 无从得知间隔本身。
    written = (cache / "next-reminder-at").read_text(encoding="utf-8").strip()
    assert written.isdigit()
    assert int(written) > int(time.time()), "sentinel 必须指向未来的下一次提醒时点"


# --- GWT-003 hooks 安装自检 ------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "dev1.0", str(path)], check=True, capture_output=True)


def test_gwt_003_t1_detects_missing_hooks_path(tmp_path: Path, policy) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / policy.hooks_path).mkdir(parents=True)

    assert inventory.hooks_installed(root=repo, policy=policy) is False


def test_gwt_003_t2_accepts_only_in_repo_hooks_path(tmp_path: Path, policy) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / policy.hooks_path).mkdir(parents=True)

    subprocess.run(["git", "config", "core.hooksPath", policy.hooks_path], cwd=repo, check=True)
    assert inventory.hooks_installed(root=repo, policy=policy) is True

    outside = tmp_path / "outside-hooks"
    outside.mkdir()
    subprocess.run(["git", "config", "core.hooksPath", str(outside)], cwd=repo, check=True)
    assert inventory.hooks_installed(root=repo, policy=policy) is False, "仓外 hook 目录不算已安装"


def test_gwt_003_t3_install_entrypoint_resolves_repo_root(tmp_path: Path, policy) -> None:
    """安装入口的路径解析回归。

    这里曾经写成 `/../../..`，多退一级落到仓库外的父目录，`git config` 静默失败，
    core.hooksPath 长期未设置，pre-commit 与 pre-push 从未生效。
    """
    repo = tmp_path / "nested" / "repo"
    _init_repo(repo)
    hook_dir = repo / policy.hooks_path
    hook_dir.mkdir(parents=True)
    for name in ("pre-commit", "pre-push", "post-commit"):
        shutil.copy(ROOT / policy.hooks_path / name, hook_dir / name)
    shutil.copy(INSTALL_SCRIPT, hook_dir / INSTALL_SCRIPT.name)

    completed = subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)], capture_output=True, text=True, cwd=tmp_path
    )
    assert completed.returncode == 0, completed.stderr

    readback = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert readback.stdout.strip() == policy.hooks_path
    # 幂等：重复安装不改变结果，也不报错。
    assert subprocess.run(["bash", str(hook_dir / INSTALL_SCRIPT.name)], capture_output=True).returncode == 0


def test_gwt_003_t4_install_refuses_outside_git_toplevel(tmp_path: Path, policy) -> None:
    """非 git 顶层目录下必须 fail-closed，而不是把配置写去别处后声称成功。"""
    plain = tmp_path / "plain"
    hook_dir = plain / policy.hooks_path
    hook_dir.mkdir(parents=True)
    for name in ("pre-commit", "pre-push", "post-commit"):
        shutil.copy(ROOT / policy.hooks_path / name, hook_dir / name)
    shutil.copy(INSTALL_SCRIPT, hook_dir / INSTALL_SCRIPT.name)

    completed = subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)], capture_output=True, text=True, cwd=tmp_path
    )
    assert completed.returncode == 2
    assert "not the git toplevel" in completed.stderr


def test_gate_entrypoint_is_executable_and_reports_typed_codes() -> None:
    """门禁本身必须可被 gate 链执行，且失败身份用稳定错误码表达。"""
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--json"], capture_output=True, text=True, cwd=ROOT
    )
    assert completed.returncode in (0, 2)
    payload = json.loads(completed.stdout)
    assert "issues" in payload and "summary" in payload
    for issue in payload["issues"]:
        assert issue.startswith("OPS.WORKTREE."), issue


def test_policy_install_command_matches_real_entrypoint(policy) -> None:
    """策略里的安装命令与真实入口不得漂移——两处字面量是这类治理最容易烂掉的地方。"""
    assert policy.install_command.endswith(str(INSTALL_SCRIPT.relative_to(ROOT)))
    assert INSTALL_SCRIPT.is_file()
    assert (ROOT / policy.hooks_path).is_dir()

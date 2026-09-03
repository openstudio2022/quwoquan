# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t5
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t6
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t5
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t6
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t7
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t8
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-002.t9
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-003.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t4
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-004.t5
"""本地工作副本生命周期治理的行为级 local_contract。

决策表覆盖四件事：授权提醒在两个执行面只注入不阻断、滞留提醒的去重与不漏报、
hooks 安装自检与安装入口的路径解析回归、lane 身份在准出门禁中 fail-closed。
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
# 按目录加进 sys.path，而不是 `from quwoquan_ops.hooks import ...`：后者把 quwoquan_ops
# 当成真包导入，会在源码树留下 __pycache__，而仓库要求源码树缓存为零。
for extra in (ROOT / "quwoquan_ops/cli/lib", ROOT / "quwoquan_ops/hooks"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import local_worktree_inventory as inventory  # noqa: E402
from quwoquan_ops.cli import lane_worktree_commands  # noqa: E402
import worktree_authz_guard as guard  # noqa: E402
import worktree_merge_reminder as reminder  # noqa: E402

AUTHZ_SCRIPT = ROOT / "quwoquan_ops/hooks/worktree_authz_guard.py"
INSTALL_SCRIPT = ROOT / "quwoquan_ops/hooks/run_install_hooks.sh"
GATE_SCRIPT = ROOT / "quwoquan_ops/gate/verify_local_worktree_lifecycle.py"
REMINDER_GATE = ROOT / "quwoquan_ops/hooks/worktree_session_reminder_gate.sh"
REMINDER_SCRIPT = ROOT / "quwoquan_ops/hooks/worktree_merge_reminder.py"
CURSOR_HOOKS = ROOT / ".cursor/hooks.json"
CODEX_HOOKS = ROOT / ".codex/hooks.json"
POST_COMMIT = ROOT / "quwoquan_ops/hooks/post-commit"
SPEC = ROOT / "specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md"
ALLOWED = frozenset({"dev1.0", "main", "lane/product-mainline", "lane/data-engineering", "lane/engineering", "lane/ops", "lane/small-fix", "lane/refactor"})


@pytest.fixture(scope="module")
def policy() -> inventory.WorktreePolicy:
    return inventory.load_policy()


def _detect(command: str) -> guard.Detection | None:
    return guard.detect(command, allowed_branches=ALLOWED, repo_root=ROOT)


# --- GWT-001 创建授权提醒（observe-only） ----------------------------------


@pytest.mark.parametrize(
    ("command", "expected_kind"),
    [
        ("git worktree add /tmp/probe", "worktree_add"),
        ("cd /tmp && git worktree add probe", "worktree_add"),
        ("git -C /elsewhere worktree add p2", "worktree_add"),
        ("git checkout -b feature/foo", "branch_create"),
        ("git switch -c hotfix", "branch_create"),
        ("git branch experiment", "branch_create"),
        ("git clone https://github.example.invalid/example/quwoquan.git /tmp/y", "clone"),
        (
            "git clone --branch main https://github.example.invalid/example/quwoquan.git /tmp/y",
            "clone",
        ),
        (
            (
                "git clone --depth 1 --origin upstream "
                "https://github.example.invalid/example/quwoquan.git /tmp/y"
            ),
            "clone",
        ),
        (
            (
                "git clone --branch=main --depth=1 "
                "https://github.example.invalid/example/quwoquan.git /tmp/y"
            ),
            "clone",
        ),
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
        "git checkout -b lane/small-fix",
        "git branch",
        "git branch -d stale",
        "git branch --show-current",
        "git clone https://github.example.invalid/example/flutter.git",
        "git clone https://github.example.invalid/example/worktree.git",
        "git clone https://github.example.invalid/example/myquwoquan.git",
        "git clone --branch main https://github.example.invalid/example/flutter.git /tmp/quwoquan",
        "git clone --reference /tmp/quwoquan https://github.example.invalid/example/flutter.git",
        "echo 'git worktree add' >> notes.md",
    ],
)
def test_gwt_001_t2_leaves_unrelated_commands_alone(command: str) -> None:
    """白名单分支、只读子命令与第三方 clone 不在识别面内。误伤会让这道闸很快被绕过。"""
    assert _detect(command) is None, command


def _run_guard(harness: str, command: str, env: dict[str, str] | None = None) -> dict[str, object]:
    payload = {"command": command} if harness == "cursor" else {"tool_input": {"command": command}}
    completed = subprocess.run(
        [sys.executable, str(AUTHZ_SCRIPT), "--harness", harness],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return json.loads(completed.stdout or "{}")


def _message(harness: str, output: dict[str, object]) -> str:
    if harness == "cursor":
        assert output["permission"] == "allow", output
        return str(output.get("agent_message") or "")
    hook = output.get("hookSpecificOutput")
    if hook is None:
        return ""
    assert hook["hookEventName"] == "PreToolUse"
    assert hook["permissionDecision"] == "allow", output
    assert "permissionDecisionReason" not in hook
    return str(hook.get("additionalContext") or "")


def test_gwt_001_t3_two_harnesses_inject_context_without_blocking() -> None:
    """hook 面零硬门：两个执行面都 allow，只按各自协议注入授权规则与留痕方式。"""
    command = "git clone https://github.example.invalid/example/quwoquan.git /tmp/probe"
    for harness in ("cursor", "codex"):
        output = _run_guard(harness, command)
        message = _message(harness, output)
        assert "OPS.WORKTREE.NOT_AUTHORIZED" in message, output
        assert "QWQ_WORKTREE_AUTHZ" in message, "提醒必须给出授权留痕的确切方式"
        assert "AGENTS.md" in message
        assert "未阻断" in message
    cursor = _run_guard("cursor", command)
    assert cursor["user_message"] == cursor["agent_message"]


def test_gwt_001_t3_fast_path_skips_policy_for_unrelated_commands(monkeypatch, capsys) -> None:
    """Codex 对每条 Bash 都调用本 hook：命中不到创建面时不得加载 policy，也不得带消息。"""
    monkeypatch.setattr(
        inventory, "load_policy", lambda: (_ for _ in ()).throw(AssertionError("policy loaded"))
    )
    for harness, payload, expected in (
        ("cursor", {"command": "ls -la && git status"}, {"permission": "allow"}),
        ("codex", {"tool_input": {"command": "pytest -q quwoquan_ops/tests"}}, {}),
    ):
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps(payload)))
        assert guard.main(["--harness", harness]) == 0
        assert json.loads(capsys.readouterr().out) == expected


# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t8
def test_gwt_001_t4_explicit_authorization_records_and_stays_silent(
    policy, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        guard,
        "_git",
        lambda _root, *args: (0, "a" * 40) if args and args[0] == "rev-parse" else (0, ""),
    )
    command = (
        f'{policy.authorization_env_var}="用户同意排查" git worktree add '
        '--branch lane/data-engineering /tmp/probe origin/dev1.0'
    )
    assert guard.is_authorized(command, policy.authorization_env_var) is True
    detections = guard.detect_all(
        command,
        allowed_branches=policy.allowed_local_branches,
        repo_root=ROOT,
        env_var=policy.authorization_env_var,
    )
    assert detections[0].authorized is True
    assert detections[0].invalid_reason == ""

    unauthorized = "git worktree add /tmp/probe"
    assert guard.is_authorized(unauthorized, policy.authorization_env_var) is False
    assert guard.is_authorized(
        f"{policy.authorization_env_var}= git worktree add /tmp/probe", policy.authorization_env_var
    ) is False, "空理由不构成授权"

    # 端到端：授权且 canonical 的 segment 静默放行并留可删除记录；未授权的只注入提醒。
    authorized = _run_guard(
        "cursor",
        f'{policy.authorization_env_var}="用户同意" git worktree add -b lane/ops '
        f"{tmp_path / 'ops'} origin/dev1.0",
        env={"QWQ_OUTPUT_ROOT": str(tmp_path / "out")},
    )
    assert authorized == {"permission": "allow"}
    ledger = tmp_path / "out/env/repo/local/worktree-governance/cache/authorizations.jsonl"
    assert ledger.is_file() and "lane/ops" in ledger.read_text(encoding="utf-8")

    reminded = _run_guard(
        "codex",
        f"git worktree add -b lane/ops {tmp_path / 'ops2'} origin/dev1.0",
        env={"QWQ_OUTPUT_ROOT": str(tmp_path / "out")},
    )
    message = _message("codex", reminded)
    assert "OPS.WORKTREE.NOT_AUTHORIZED" in message
    assert "OPS.WORKTREE.INVALID_ADD" not in message, "canonical 形态不应再附模板"


@pytest.mark.parametrize("harness", ["cursor", "codex"])
def test_gwt_001_t5_policy_failure_allows_with_typed_context(monkeypatch, capsys, harness: str) -> None:
    monkeypatch.setattr(inventory, "load_policy", lambda: (_ for _ in ()).throw(ValueError("broken")))
    monkeypatch.setattr(
        sys, "stdin", __import__("io").StringIO(json.dumps(
            {"command": "git worktree add /tmp/x", "tool_input": {"command": "git worktree add /tmp/x"}}
        )),
    )

    assert guard.main(["--harness", harness]) == 0
    output = json.loads(capsys.readouterr().out)
    reason = _message(harness, output)
    assert "OPS.WORKTREE.POLICY_INVALID" in reason
    assert "recovery=repair_canonical_worktree_policy" in reason
    assert "未被阻断" in reason


# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t7
def test_gwt_001_compound_authorization_is_per_segment(policy, monkeypatch) -> None:
    monkeypatch.setattr(
        guard,
        "_git",
        lambda _root, *args: (0, "a" * 40) if args and args[0] == "rev-parse" else (0, ""),
    )
    command = (
        'QWQ_WORKTREE_AUTHZ="first" git worktree add --branch lane/data-engineering /tmp/a HEAD && '
        'git worktree add --branch lane/refactor /tmp/b HEAD'
    )
    detections = guard.detect_all(
        command,
        allowed_branches=policy.allowed_local_branches,
        repo_root=ROOT,
        env_var=policy.authorization_env_var,
    )
    assert [item.authorized for item in detections] == [True, False]


@pytest.mark.parametrize(
    "args",
    [
        ["add", "--detach", "/tmp/x", "HEAD"],
        ["add", "--force", "--branch", "lane/data-engineering", "/tmp/x", "HEAD"],
        ["add", "-B", "lane/data-engineering", "/tmp/x", "HEAD"],
        ["add", "--branch", "feature/nope", "/tmp/x", "HEAD"],
        ["add", "/tmp/x", "HEAD"],
        ["add", "--branch", "lane/data-engineering", "/tmp/x"],
    ],
)
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md#gwt-001.t8
def test_gwt_001_flags_noncanonical_worktree_add_shapes(args) -> None:
    _, reason = guard._validate_worktree_add(args, allowed_branches=ALLOWED, repo_root=ROOT)
    assert reason
    detection = guard.Detection("worktree_add", "x", segment="git worktree add", invalid_reason=reason)
    message = guard.observation(
        detection, env_var="QWQ_WORKTREE_AUTHZ", code="OPS.WORKTREE.NOT_AUTHORIZED", lanes=ALLOWED
    )
    assert "OPS.WORKTREE.INVALID_ADD" in message
    assert "git worktree add -b <lane/...> <path> origin/dev1.0" in message


def test_gwt_001_flags_noncanonical_start_point_from_any_worktree(monkeypatch) -> None:
    """不再要求从 dev1.0 worktree 发起；只对 start-point 是否指向 dev1.0 给出提醒。"""

    def fake_git(_root, *args):
        if args[0] == "branch":
            return 0, "lane/data-engineering"
        if args[-1] in {"origin/dev1.0", "dev1.0"}:
            return 0, "a" * 40
        return 0, "b" * 40

    monkeypatch.setattr(guard, "_git", fake_git)
    _, reason = guard._validate_worktree_add(
        ["add", "--branch", "lane/data-engineering", "/tmp/x", "main"],
        allowed_branches=ALLOWED,
        repo_root=ROOT,
    )
    assert "start-point" in reason
    assert not hasattr(guard, "_bootstrap_authority")


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


def test_gwt_002_t2_clean_copies_have_identity_but_no_unmerged_item(policy) -> None:
    """干净副本不进滞留 items，但会话 identity 必须持续可见。"""
    now = 1_000_000_000
    summary = inventory.summarize([_copy("/tmp/clean")], policy, now=now)

    assert summary["totalWorkCopies"] == 1
    assert summary["withUnmergedWork"] == 0
    assert summary["items"] == []
    message = reminder.build_message(summary, hooks_ok=True, policy=policy)
    assert "identity=dev1.0" in message
    assert "ahead=0 behind=0 dirty=0" in message


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


def test_gwt_002_t4_post_commit_mark_due_skips_policy_inventory_and_git(
    monkeypatch, tmp_path: Path
) -> None:
    """post-commit 窄路径只原子写 due marker，不得加载完整判定依赖。"""
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        inventory, "load_policy", lambda: (_ for _ in ()).throw(AssertionError("policy loaded"))
    )
    monkeypatch.setattr(
        reminder, "collect", lambda _policy: (_ for _ in ()).throw(AssertionError("inventory collected"))
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("git/subprocess run"))
    )

    assert reminder.main(["--harness", "git", "--mode", "mark-due"]) == 0
    marker = tmp_path / "env/repo/local/worktree-governance/cache/reminder-due.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["reason"] == "post-commit"
    assert isinstance(payload["dueAt"], int)
    assert list(marker.parent.glob(f".{marker.name}.tmp.*")) == [], "原子临时文件不得残留"


def test_gwt_002_t4_due_check_uses_marker_or_persisted_next_at(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    now = 1_000_000_000
    assert reminder.scan_is_due(now=now) is True, "状态缺失只退化为本次扫描"

    reminder.save_state(at=now, overdue_paths=[], next_at=now + 3600)
    assert reminder.scan_is_due(now=now) is False
    reminder.mark_due(now=now)
    assert reminder.scan_is_due(now=now) is True

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


def _run_reminder(
    output_root: Path, *args: str, input_text: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REMINDER_SCRIPT), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env={**os.environ, "QWQ_OUTPUT_ROOT": str(output_root)},
        cwd=ROOT,
        check=False,
    )


def test_gwt_002_t6_cursor_session_start_json_shape_and_wiring(tmp_path: Path, monkeypatch, capsys) -> None:
    """Cursor 使用官方 sessionStart 顶层 additional_context，不保留 every-shell fallback。"""
    payload = json.loads(CURSOR_HOOKS.read_text(encoding="utf-8"))
    hooks = payload["hooks"]
    assert hooks["sessionStart"] == [
        {
            "command": (
                "PYTHONDONTWRITEBYTECODE=1 python3 "
                "quwoquan_ops/hooks/worktree_merge_reminder.py --harness cursor --reason session"
            )
        }
    ]
    assert all(
        "worktree_merge_reminder" not in item["command"]
        and "worktree_session_reminder_gate" not in item["command"]
        for item in hooks["beforeShellExecution"]
    )

    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(reminder, "scan_is_due", lambda: True)
    monkeypatch.setattr(
        reminder,
        "_run_bounded_scan",
        lambda: reminder.ScanAttempt(
            {
                "ok": True,
                "message": "session context",
                "overduePaths": [],
                "intervalHours": 24,
            },
            "",
            False,
            7,
        ),
    )
    assert reminder.main(["--harness", "cursor", "--reason", "session"]) == 0
    assert json.loads(capsys.readouterr().out) == {"additional_context": "session context"}

    assert reminder.main(["--harness", "codex", "--reason", "session"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "session context",
        }
    }
    codex = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
    assert codex["hooks"]["SessionStart"][0]["hooks"][0]["command"].endswith(
        'worktree_merge_reminder.py" --harness codex --reason session'
    )
    spec_text = SPEC.read_text(encoding="utf-8")
    assert "OPS.WORKTREE.CLOUD_SESSION_REMINDER_UNSUPPORTED" in spec_text
    assert "hooks 配置热重载，无需 Reload Window" in spec_text


def test_gwt_002_t7_session_scans_only_when_due(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    now = 1_000_000_000
    reminder.save_state(at=now, overdue_paths=[], next_at=now + 3600)
    monkeypatch.setattr(
        reminder,
        "_run_bounded_scan",
        lambda: (_ for _ in ()).throw(AssertionError("scan started before due")),
    )
    assert reminder.main(["--harness", "cursor", "--reason", "session"]) == 0
    assert capsys.readouterr().out == ""


def test_gwt_002_t8_scan_timeout_is_fail_open_and_records_status(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    reminder.mark_due(now=1)
    monkeypatch.setattr(
        reminder,
        "_run_bounded_scan",
        lambda: reminder.ScanAttempt(None, "budget exhausted", True, 20_123),
    )

    assert reminder.main(["--harness", "cursor", "--reason", "session"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert list(output) == ["additional_context"]
    assert "未被阻断" in output["additional_context"]
    status_path = tmp_path / "env/repo/local/worktree-governance/cache/last-scan-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["outcome"] == "timeout"
    assert status["elapsedMs"] == 20_123
    assert status["lastError"] == "budget exhausted"
    assert (status_path.parent / "reminder-due.json").is_file(), "失败后 marker 保留供下次重试"


def test_gwt_002_t9_full_scan_has_an_overall_process_group_deadline(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    attempt = reminder._run_bounded_scan(budget_seconds=0.0)
    assert attempt.payload is None
    assert attempt.timed_out is True
    assert "wall-clock budget" in attempt.error


def test_gwt_002_t10_new_commit_marker_survives_an_inflight_scan(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    reminder.mark_due(now=1)
    old_token = reminder._due_token()
    assert old_token is not None
    reminder.mark_due(now=2)
    reminder._clear_due_if_unchanged(old_token)
    marker = tmp_path / "env/repo/local/worktree-governance/cache/reminder-due.json"
    assert json.loads(marker.read_text(encoding="utf-8"))["dueAt"] == 2


def test_gwt_002_t9_all_hook_paths_are_fail_open(tmp_path: Path) -> None:
    invalid = _run_reminder(tmp_path, "--not-a-real-option")
    assert invalid.returncode == 0

    blocked_output = tmp_path / "output-is-a-file"
    blocked_output.write_text("x", encoding="utf-8")
    mark = _run_reminder(blocked_output, "--harness", "git", "--mode", "mark-due")
    assert mark.returncode == 0
    assert "未被阻断" in mark.stdout

    source = REMINDER_SCRIPT.read_text(encoding="utf-8")
    post_source = POST_COMMIT.read_text(encoding="utf-8")
    assert "exit 2" not in source
    assert "failClosed" not in source
    assert "--mode mark-due" in post_source
    assert "--reason commit" not in post_source

def _linked(
    path: str,
    branch: str,
    *,
    probe_error: str = "",
    head: str = "same",
    clean: bool = True,
    dirty: int = 0,
) -> inventory.WorkCopy:
    return inventory.WorkCopy(
        path=path,
        kind="linked_worktree",
        branch=branch,
        ahead=0,
        dirty=dirty,
        stashes=0,
        oldest_unmerged_epoch=None,
        probe_error=probe_error,
        head=head,
        clean=clean,
    )


def test_inventory_list_failure_is_typed_fail_closed(monkeypatch, policy) -> None:
    monkeypatch.setattr(inventory, "_git", lambda *_args: (2, "authority down"))
    with pytest.raises(inventory.InventoryError) as caught:
        inventory.discover_work_copies(root=ROOT, policy=policy)
    assert caught.value.code == inventory.INVENTORY_UNAVAILABLE


def _canonical_path(policy, branch: str) -> str:
    if branch == policy.integration_branch:
        return str(ROOT.parent / policy.integration_directory)
    return str(ROOT.parent / dict(policy.lane_worktree_directories)[branch])


def _integration(policy, *, head: str = "same", clean: bool = True, dirty: int = 0):
    return _linked(
        _canonical_path(policy, policy.integration_branch),
        policy.integration_branch,
        head=head,
        clean=clean,
        dirty=dirty,
    )


def test_porcelain_parser_preserves_bare_record_without_branch() -> None:
    parsed = inventory.parse_worktree_list(
        "worktree /tmp/project/quwoquan.git\nbare\n\n"
        "worktree /tmp/project/engineering\nHEAD abc\n"
        "branch refs/heads/lane/engineering\n"
    )
    assert parsed == [
        inventory.WorktreeListEntry(
            path="/tmp/project/quwoquan.git", branch="", bare=True
        ),
        inventory.WorktreeListEntry(
            path="/tmp/project/engineering", branch="lane/engineering", bare=False
        ),
    ]


def test_discovery_validates_bare_hub_without_probing_it(tmp_path, policy, monkeypatch) -> None:
    project = tmp_path / "quwoquan"
    hub = project / policy.bare_hub_directory
    integration = project / policy.integration_directory
    hub.mkdir(parents=True)
    integration.mkdir()
    porcelain = (
        f"worktree {hub}\nbare\n\n"
        f"worktree {integration}\nHEAD {'a' * 40}\n"
        f"branch refs/heads/{policy.integration_branch}\n"
    )
    actual_git = inventory._git

    def fake_git(cwd, *args):
        if args == ("worktree", "list", "--porcelain"):
            return 0, porcelain
        return actual_git(cwd, *args)

    probed: list[Path] = []

    def fake_probe(path, **kwargs):
        probed.append(path)
        return _linked(str(path), kwargs["branch"])

    monkeypatch.setattr(inventory, "_git", fake_git)
    monkeypatch.setattr(inventory, "probe_work_copy", fake_probe)
    monkeypatch.setattr(inventory, "_scan_for_clones", lambda *_args: [])
    copies = inventory.discover_work_copies(root=integration, policy=policy)
    assert probed == [integration.resolve()]
    assert all(copy.path != str(hub) for copy in copies)


@pytest.fixture
def hook_env_temp_path() -> Iterator[Path]:
    """在仓外系统临时目录创建并清理跨仓 Git 环境回归夹具。"""
    system_temp_root = Path("/tmp").resolve()
    assert system_temp_root.is_dir()
    with tempfile.TemporaryDirectory(
        prefix="qwq-hook-env-regression-", dir=system_temp_root
    ) as temp_dir:
        path = Path(temp_dir).resolve()
        assert not path.is_relative_to(ROOT.resolve())
        yield path


def test_discovery_ignores_hook_repository_environment_and_preserves_copy_facts(
    hook_env_temp_path: Path, policy, monkeypatch
) -> None:
    project = hook_env_temp_path / "project"
    hub = project / policy.bare_hub_directory
    integration = project / policy.integration_directory
    lane = project / dict(policy.lane_worktree_directories)["lane/engineering"]
    hub.parent.mkdir(parents=True)
    _run_git(hub.parent, "init", "--bare", "-q", str(hub))
    _run_git(hub, "worktree", "add", "-q", "-b", policy.integration_branch, str(integration))
    (integration / "seed.txt").write_text("seed\n", encoding="utf-8")
    _run_git(integration, "add", "seed.txt")
    _run_git(integration, "commit", "-qm", "seed")
    _run_git(
        hub,
        "worktree",
        "add",
        "-q",
        "-b",
        "lane/engineering",
        str(lane),
        policy.integration_branch,
    )
    (lane / "ahead.txt").write_text("ahead\n", encoding="utf-8")
    _run_git(lane, "add", "ahead.txt")
    _run_git(lane, "commit", "-qm", "ahead")
    (lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    test_policy = inventory.WorktreePolicy(
        **{
            **vars(policy),
            "project_root": str(project),
            "discovery_roots": (str(project),),
        }
    )
    monkeypatch.setenv("GIT_DIR", str(hub / "worktrees" / lane.name))
    monkeypatch.setenv("GIT_WORK_TREE", str(lane))

    copies = inventory.discover_work_copies(root=integration, policy=test_policy)
    by_branch = {copy.branch: copy for copy in copies}
    assert set(by_branch) == {policy.integration_branch, "lane/engineering"}
    assert all(copy.path != str(hub.resolve()) for copy in copies), "bare hub is authority, not a copy"
    assert all(copy.probe_error == "" for copy in copies)
    assert by_branch[policy.integration_branch].dirty == 0
    assert by_branch[policy.integration_branch].ahead == 0
    assert by_branch["lane/engineering"].dirty == 1
    assert by_branch["lane/engineering"].ahead == 1


@pytest.mark.parametrize(
    "copies_factory, fragment",
    [
        (lambda policy: [_integration(policy), _linked("/tmp/detached", "")], "detached"),
        (lambda policy: [_integration(policy), _linked("/tmp/main", "main")], "not integration or a fixed lane"),
        (
            lambda policy: [
                _integration(policy),
                _linked(_canonical_path(policy, "lane/ops"), "lane/ops", probe_error="status failed"),
            ],
            "probe failed",
        ),
        (
            lambda policy: [
                _integration(policy),
                _linked(_canonical_path(policy, "lane/ops"), "lane/ops"),
                _linked("/tmp/ops-copy", "lane/ops"),
            ],
            "duplicate lane binding",
        ),
        (
            lambda policy: [
                _integration(policy),
                _linked("/tmp/same", "lane/ops"),
                _linked("/tmp/same", "lane/refactor"),
            ],
            "duplicate worktree path",
        ),
        (
            lambda policy: [
                _integration(policy),
                _linked("/tmp/wrong-ops", "lane/ops"),
            ],
            "lane path mismatch",
        ),
    ],
)
def test_discovered_linked_identity_failures_block(policy, copies_factory, fragment) -> None:
    issues = inventory.validate_worktree_identity(copies_factory(policy), policy)
    assert any(fragment in issue for issue in issues), issues


def test_integration_is_unique_clean_and_bound_to_integration_directory(policy) -> None:
    assert inventory.validate_worktree_identity([_integration(policy)], policy) == []
    dirty = inventory.validate_worktree_identity(
        [_integration(policy, clean=False, dirty=1)], policy
    )
    assert any("integration worktree is not clean" in issue for issue in dirty)
    missing = inventory.validate_worktree_identity([], policy)
    assert any("integration worktree must appear exactly once" in issue for issue in missing)


def test_require_all_lanes_checks_clean_and_canonical_head(monkeypatch, policy) -> None:
    lanes = sorted(branch for branch in policy.allowed_local_branches if branch.startswith("lane/"))
    copies = [
        _integration(policy),
        *[_linked(_canonical_path(policy, branch), branch) for branch in lanes],
    ]
    monkeypatch.setattr(inventory, "_integration_ref", lambda _root, _policy: "origin/dev1.0")
    monkeypatch.setattr(inventory, "_git", lambda *_args: (0, "same"))
    assert inventory.validate_worktree_identity(
        copies, policy, require_all_lanes=True, repo_root=ROOT
    ) == []

    dirty = list(copies)
    dirty[1] = _linked(dirty[1].path, dirty[1].branch, clean=False, dirty=1)
    dirty[2] = _linked(dirty[2].path, dirty[2].branch, head="other")
    issues = inventory.validate_worktree_identity(
        dirty, policy, require_all_lanes=True, repo_root=ROOT
    )
    assert any("lane worktree is not clean" in issue for issue in issues)
    assert any("lane HEAD differs from origin/dev1.0" in issue for issue in issues)

    integration_drift = list(copies)
    integration_drift[0] = _integration(policy, head="other")
    issues = inventory.validate_worktree_identity(
        integration_drift, policy, require_all_lanes=True, repo_root=ROOT
    )
    assert any("integration HEAD differs from origin/dev1.0" in issue for issue in issues)

    missing = inventory.validate_worktree_identity(
        copies[:-1], policy, require_all_lanes=True, repo_root=ROOT
    )
    assert any("require-all-lanes mismatch" in issue for issue in missing)


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
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    readback = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert readback.stdout.strip() == policy.hooks_path
    # 幂等：重复安装不改变结果，也不报错。
    assert subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)],
        capture_output=True,
        check=False,
    ).returncode == 0


def test_gwt_003_t4_install_refuses_outside_git_toplevel(tmp_path: Path, policy) -> None:
    """非 git 顶层目录下必须 fail-closed，而不是把配置写去别处后声称成功。"""
    plain = tmp_path / "plain"
    hook_dir = plain / policy.hooks_path
    hook_dir.mkdir(parents=True)
    for name in ("pre-commit", "pre-push", "post-commit"):
        shutil.copy(ROOT / policy.hooks_path / name, hook_dir / name)
    shutil.copy(INSTALL_SCRIPT, hook_dir / INSTALL_SCRIPT.name)

    completed = subprocess.run(
        ["bash", str(hook_dir / INSTALL_SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 2
    assert "not the git toplevel" in completed.stderr


def test_gate_entrypoint_is_executable_and_reports_typed_codes() -> None:
    """门禁本身必须可被 gate 链执行，且失败身份用稳定错误码表达。"""
    completed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode in (0, 2)
    payload = json.loads(completed.stdout)
    assert "issues" in payload and "summary" in payload
    for issue in payload["issues"]:
        assert issue.startswith("OPS.WORKTREE."), issue


@pytest.mark.parametrize(
    ("policy_mutator", "branch_mutator"),
    [
        (lambda raw: raw + b"unknown_field: true\n", lambda raw: raw),
        (
            lambda raw: raw.replace(
                b"authorization_env_var: QWQ_WORKTREE_AUTHZ\n",
                b"authorization_env_var: QWQ_WORKTREE_AUTHZ\n"
                b"authorization_env_var: OTHER\n",
            ),
            lambda raw: raw,
        ),
        (lambda raw: raw, lambda raw: raw + b"unknown_field: true\n"),
        (
            lambda raw: raw,
            lambda raw: raw.replace(
                b"integration_branch: dev1.0\n",
                b"integration_branch: dev1.0\nintegration_branch: main\n",
            ),
        ),
        (
            lambda raw: raw,
            lambda raw: raw.replace(
                b"production_workflow: .github/workflows/deploy-prod-auto.yml\n",
                b"",
            ),
        ),
        (
            lambda raw: raw,
            lambda raw: raw.replace(
                b"  state: active\n",
                b"  state: pending\n",
                1,
            ),
        ),
    ],
)
def test_policy_loader_rejects_unknown_duplicate_and_incomplete_contracts(
    tmp_path: Path, policy_mutator, branch_mutator,
) -> None:
    policy_path = tmp_path / "worktree_policy.yaml"
    branch_path = tmp_path / "branch_policy.yaml"
    policy_path.write_bytes(
        policy_mutator(
            (ROOT / "quwoquan_ops/policies/worktree_policy.yaml").read_bytes()
        )
    )
    branch_path.write_bytes(
        branch_mutator(
            (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
        )
    )

    with pytest.raises(inventory.PolicyError):
        inventory.load_policy(
            policy_path=policy_path,
            branch_policy_path=branch_path,
        )


def test_policy_declares_fixed_project_hub_integration_and_lane_directories(policy) -> None:
    assert policy.schema_version == 2
    assert policy.project_root == "{repo_parent}"
    assert policy.bare_hub_directory == "quwoquan.git"
    assert (policy.integration_directory, policy.integration_branch) == ("integration", "dev1.0")
    source = (ROOT / "quwoquan_ops/policies/worktree_policy.yaml").read_text(encoding="utf-8")
    assert "lane_worktree_directory_rule: branch_suffix" in source
    assert "lane/engineering:" not in source, "分支闭集不得复制到物理布局策略"
    assert dict(policy.lane_worktree_directories) == {
        branch: branch.removeprefix("lane/")
        for branch in ALLOWED
        if branch.startswith("lane/")
    }


def test_lane_command_targets_render_without_mutation_and_derive_policy(policy) -> None:
    bootstrap = lane_worktree_commands.render("bootstrap")
    resync = lane_worktree_commands.render("resync")
    assert len(bootstrap) == len(resync) == 6
    for branch, directory in policy.lane_worktree_directories:
        assert any(branch in command and f"/{directory}" in command for command in bootstrap)
        assert any(f"/{directory}" in command and "merge --ff-only dev1.0" in command for command in resync)
    source = (ROOT / "quwoquan_ops/cli/lane_worktree_commands.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "os.system" not in source


def test_lane_ownership_schema_is_closed_and_uses_branch_policy_lanes(policy) -> None:
    lanes = frozenset(branch for branch in ALLOWED if branch.startswith("lane/"))
    rules = inventory.load_lane_ownership(allowed_lanes=lanes)
    assert inventory.ownership_owner("quwoquan_ops/gate/verify_root_layout.py", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/cli/stackctl.py", rules) == "lane/ops"
    assert inventory.ownership_owner("quwoquan_ops/policies/branch_policy.yaml", rules) == "lane/engineering"
    assert inventory.ownership_owner("quwoquan_ops/policies/app_build_projection_policy.json", rules) == "lane/ops"


def test_policy_install_command_matches_real_entrypoint(policy) -> None:
    """策略里的安装命令与真实入口不得漂移——两处字面量是这类治理最容易烂掉的地方。"""
    assert policy.install_command.endswith(str(INSTALL_SCRIPT.relative_to(ROOT)))
    assert INSTALL_SCRIPT.is_file()
    assert (ROOT / policy.hooks_path).is_dir()

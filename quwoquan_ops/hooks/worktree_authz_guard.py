#!/usr/bin/env python3
"""创建授权闸：新 worktree、同源 clone 与非白名单分支必须先取得显式授权。

角色：hook。由 `.cursor/hooks.json` 的 `beforeShellExecution` 与 `.codex/hooks.json`
的 `PreToolUse`(Bash) 调用，`--harness` 决定输出协议。

行为语义归属：
`specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md`
的 REQ-001。

两个执行面能力不对等，只在输出层分叉，判定共用同一实现：Cursor 支持
`permission: "ask"`，可把动作升级为人工批准；Codex 的 `PreToolUse` 不支持 `ask`
（返回该值会被判为 hook 运行失败并继续执行工具调用），只能 `deny` 并给出授权方式。

本闸只能阻断意外，不能阻断刻意绕过：执行体有权自行设置环境变量。Cursor 的人工
批准弹窗是其中唯一执行体无法自行绕过的一环。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 由 harness 直接调用时命令行没有 `-B`，import 会在源码树留下 __pycache__，
# 而仓库要求源码树缓存为零。必须在 import 之前关掉。
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

_GIT_OPTS_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
)
_BRANCH_CREATE_FLAGS = frozenset({"-b", "-B", "-c", "-C"})
_BRANCH_NON_CREATE_FLAGS = frozenset(
    {
        "-d", "-D", "--delete", "-m", "-M", "--move", "--list", "-l", "-a", "-r",
        "--all", "--remotes", "-v", "-vv", "--verbose", "--show-current", "--merged",
        "--no-merged", "--contains", "--sort", "--format", "--edit-description",
        "--set-upstream-to", "-u", "--unset-upstream", "--copy",
    }
)
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = frozenset({"sudo", "env", "time", "nohup", "command", "exec"})


@dataclass(frozen=True)
class Detection:
    kind: str
    detail: str

    @property
    def summary(self) -> str:
        return {
            "worktree_add": f"新建 linked worktree（{self.detail}）",
            "clone": f"再次 clone 本仓库（{self.detail}）",
            "branch_create": f"创建非白名单分支 `{self.detail}`",
        }.get(self.kind, self.kind)


def _split_segments(command: str) -> list[str]:
    """按 shell 连接符切分。复合命令的后半段同样要判定，否则 `cd x && git worktree add` 会漏。"""
    return [seg.strip() for seg in re.split(r"&&|\|\||[;\n|]", command) if seg.strip()]


def _tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _strip_prefix(tokens: list[str]) -> tuple[list[str], list[str]]:
    """剥离前置环境变量赋值与 sudo/env 之类包装，返回 (赋值列表, 剩余 token)。"""
    assignments: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _ENV_ASSIGN.match(token):
            assignments.append(token)
            index += 1
            continue
        if token in _WRAPPERS:
            index += 1
            continue
        break
    return assignments, tokens[index:]


def _git_subcommand(tokens: list[str]) -> tuple[str, list[str]]:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _GIT_OPTS_WITH_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, tokens[index + 1 :]
    return "", []


def _detect_branch_create(args: list[str], allowed: frozenset[str]) -> Detection | None:
    for position, token in enumerate(args):
        if token in _BRANCH_CREATE_FLAGS and position + 1 < len(args):
            name = args[position + 1]
            if name not in allowed:
                return Detection("branch_create", name)
            return None
    return None


def _detect_branch_command(args: list[str], allowed: frozenset[str]) -> Detection | None:
    """`git branch <name>` 创建分支；删除、改名、列出等形态不属于识别面。"""
    for token in args:
        if token in _BRANCH_NON_CREATE_FLAGS or token.startswith("--sort=") or token.startswith("--format="):
            return None
    positional = [token for token in args if not token.startswith("-")]
    if not positional:
        return None
    name = positional[0]
    return None if name in allowed else Detection("branch_create", name)


def _detect_clone(args: list[str], repo_name: str, repo_root: Path) -> Detection | None:
    """只拦同源 clone。克隆第三方仓库是正常操作，一并拦住会让这道闸很快被绕过。"""
    for token in args:
        if token.startswith("-"):
            continue
        lowered = token.lower()
        if repo_name and repo_name in lowered:
            return Detection("clone", token)
        try:
            if Path(token).expanduser().resolve(strict=False) == repo_root.resolve():
                return Detection("clone", token)
        except OSError:
            continue
        return None
    return None


def detect(command: str, *, allowed_branches: frozenset[str], repo_root: Path) -> Detection | None:
    repo_name = repo_root.name.lower()
    for segment in _split_segments(command):
        tokens = _tokenize(segment)
        if not tokens:
            continue
        _, tokens = _strip_prefix(tokens)
        if not tokens or Path(tokens[0]).name != "git":
            continue
        sub, args = _git_subcommand(tokens)
        if sub == "worktree" and args and args[0] == "add":
            return Detection("worktree_add", " ".join(args[1:]) or "未指定路径")
        if sub == "clone":
            found = _detect_clone(args, repo_name, repo_root)
            if found:
                return found
        if sub in {"checkout", "switch"}:
            found = _detect_branch_create(args, allowed_branches)
            if found:
                return found
        if sub == "branch":
            found = _detect_branch_command(args, allowed_branches)
            if found:
                return found
    return None


def is_authorized(command: str, env_var: str) -> bool:
    """授权凭据：命令内联赋值优先，其次进程环境。两者都是一次性声明，不落台账。"""
    for segment in _split_segments(command):
        assignments, _ = _strip_prefix(_tokenize(segment))
        for assignment in assignments:
            name, _, value = assignment.partition("=")
            if name == env_var and value.strip():
                return True
    return bool(os.environ.get(env_var, "").strip())


def record_authorization(detection: Detection, command: str, *, output_root: Path) -> None:
    """授权理由只作可删除运行记录留痕，删除后不改变任何后续判定。"""
    target = output_root / "env/repo/local/worktree-governance/cache"
    try:
        target.mkdir(parents=True, exist_ok=True)
        entry = {
            "at": int(time.time()),
            "kind": detection.kind,
            "detail": detection.detail,
            "command": command[:500],
        }
        with (target / "authorizations.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return


def _guidance(detection: Detection, env_var: str, code: str) -> str:
    return (
        f"{code}：{detection.summary} 需要用户显式授权。\n"
        "本仓库只允许 dev1.0 与 main 两个分支，且工作副本失控是已发生过的事故——"
        "意外多出的 worktree 与 clone 会把未合入的改动压在里面很久不被发现。\n"
        f"请先向用户说明为什么需要这个工作副本并取得同意，再以 "
        f"`{env_var}=\"<用户同意的理由>\" <原命令>` 执行。"
    )


def _emit_cursor(detection: Detection | None, env_var: str, code: str) -> dict[str, object]:
    if detection is None:
        return {"permission": "allow"}
    return {
        "permission": "ask",
        "user_message": (
            f"{detection.summary}。确认要新建这个工作副本吗？\n"
            "未合入的工作滞留在额外副本里是本仓库发生过的事故，批准后它会进入超期合并提醒。"
        ),
        "agent_message": _guidance(detection, env_var, code),
    }


def _emit_codex(detection: Detection | None, env_var: str, code: str) -> dict[str, object]:
    if detection is None:
        return {}
    # Codex 的 PreToolUse 不支持 ask，只能 deny；理由里必须给出取得授权的确切方式。
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _guidance(detection, env_var, code),
        }
    }


def _read_command(harness: str, payload: dict[str, object]) -> str:
    if harness == "codex":
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            return str(tool_input.get("command") or "")
        return ""
    return str(payload.get("command") or "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=("cursor", "codex"), required=True)
    args = parser.parse_args(argv)

    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    command = _read_command(args.harness, payload)

    try:
        import local_worktree_inventory as inventory

        policy = inventory.load_policy()
        env_var = policy.authorization_env_var
        allowed = policy.allowed_local_branches
        code = policy.failure_code("not_authorized")
    except Exception as exc:  # noqa: BLE001 - 策略不可读时放行但必须可见，不静默失去保护
        message = f"worktree 授权闸未生效：策略不可读（{exc}）。请修复 quwoquan_ops/policies/worktree_policy.yaml。"
        output = {"permission": "allow", "agent_message": message} if args.harness == "cursor" else {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": message}
        }
        print(json.dumps(output, ensure_ascii=False))
        return 0

    detection = detect(command, allowed_branches=allowed, repo_root=ROOT)
    if detection is not None and is_authorized(command, env_var):
        record_authorization(
            detection,
            command,
            output_root=Path(os.environ.get("QWQ_OUTPUT_ROOT", str(ROOT / ".qwq_output"))),
        )
        detection = None

    emit = _emit_cursor if args.harness == "cursor" else _emit_codex
    print(json.dumps(emit(detection, env_var, code), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

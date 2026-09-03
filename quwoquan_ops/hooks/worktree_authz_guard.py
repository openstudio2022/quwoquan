#!/usr/bin/env python3
"""创建授权提醒（observe-only）：识别 lane worktree bootstrap 与同源 clone，只注入上下文，不阻断。

根 `AGENTS.md` 的 Git 不变量要求新建 linked worktree / 再次 clone 先取得用户明确授权。
本 hook 不替执行体做决定：始终 allow，只在检测到未留痕授权或非 canonical 形态时把规则、
授权留痕方式与 canonical 命令模板注入给 Cursor/Codex 自行判断。硬门只在准出（lane→dev1.0
合入、交接）环节，由 `verify_local_worktree_lifecycle.py` 与 CI 承担。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

# 与 .cursor/hooks.json 的 matcher 同源；Codex 对每条 Bash 都会调用本脚本，命中不到创建面时
# 必须在导入 policy/inventory 之前返回，避免每条命令背负约 1s 的 YAML + git 探测开销。
_CREATION_HINT = re.compile(
    r"worktree\s+add|git\b.*\bclone\b|checkout\s+-[bB]|switch\s+-[cC]|git\b.*\bbranch\b"
)
_ENV_VAR_FALLBACK = "QWQ_WORKTREE_AUTHZ"

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
_CLONE_OPTIONS_WITH_VALUE = frozenset(
    {
        "-b", "--branch", "--revision", "-o", "--origin", "-u", "--upload-pack",
        "--depth", "--shallow-since", "--shallow-exclude", "--reference",
        "--reference-if-able", "--separate-git-dir", "--ref-format", "--config", "-c",
        "--filter", "--server-option", "--template", "--bundle-uri", "--jobs", "-j",
    }
)
_WORKTREE_OPTIONS_WITH_VALUE = frozenset({"--lock", "--reason"})


@dataclass(frozen=True)
class Detection:
    kind: str
    detail: str
    segment: str = ""
    authorized: bool = False
    invalid_reason: str = ""

    @property
    def summary(self) -> str:
        if self.invalid_reason:
            return f"非 canonical worktree add（{self.invalid_reason}）"
        return {
            "worktree_add": f"新建 linked worktree（{self.detail}）",
            "clone": f"再次 clone 本仓库（{self.detail}）",
            "branch_create": f"创建非白名单分支 `{self.detail}`",
        }.get(self.kind, self.kind)


def _split_segments(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"&&|\|\||[;\n|]", command) if segment.strip()]


def _tokenize(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _strip_prefix(tokens: list[str]) -> tuple[list[str], list[str]]:
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


def _assignment_value(assignments: list[str], name: str) -> str:
    for assignment in assignments:
        key, _, value = assignment.partition("=")
        if key == name:
            return value.strip()
    return ""


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
            return None if name in allowed else Detection("branch_create", name)
    return None


def _detect_branch_command(args: list[str], allowed: frozenset[str]) -> Detection | None:
    for token in args:
        if token in _BRANCH_NON_CREATE_FLAGS or token.startswith(("--sort=", "--format=")):
            return None
    positional = [token for token in args if not token.startswith("-")]
    if not positional:
        return None
    return None if positional[0] in allowed else Detection("branch_create", positional[0])


def _repository_names(repo_root: Path) -> frozenset[str]:
    code, source = _git(repo_root, "remote", "get-url", "origin")
    if code == 0 and source:
        remote_name = re.split(r"[:/]", source.rstrip("/"))[-1].removesuffix(".git").lower()
        if remote_name:
            return frozenset({remote_name})
    return frozenset({repo_root.name.lower()})


def _clone_source(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return args[index + 1] if index + 1 < len(args) else None
        option = token.split("=", 1)[0]
        if option in _CLONE_OPTIONS_WITH_VALUE:
            index += 1 if "=" in token else 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def _detect_clone(args: list[str], repo_names: frozenset[str], repo_root: Path) -> Detection | None:
    source = _clone_source(args)
    if source is None:
        return None
    source_name = re.split(r"[:/]", source.rstrip("/"))[-1].removesuffix(".git").lower()
    if source_name in repo_names:
        return Detection("clone", source)
    try:
        if Path(source).expanduser().resolve(strict=False) == repo_root.resolve():
            return Detection("clone", source)
    except OSError:
        return None
    return None


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError) as error:
        return 1, str(error)
    output = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        output = completed.stderr.strip()
    return completed.returncode, output


def _parse_worktree_add(args: list[str]) -> tuple[str, str, str]:
    """返回 (branch, start_point, invalid_reason)。"""
    if not args or args[0] != "add":
        return "", "", "worktree 子命令不是 add"
    rest = args[1:]
    branch = ""
    positional: list[str] = []
    index = 0
    while index < len(rest):
        token = rest[index]
        option, separator, value = token.partition("=")
        if option in {"--detach", "--force", "-f", "-B", "--force-create"}:
            return "", "", f"不建议的选项 {option}"
        if option in {"-b", "--branch"}:
            if separator:
                branch = value.strip()
                index += 1
            elif index + 1 < len(rest):
                branch = rest[index + 1]
                index += 2
            else:
                return "", "", f"{option} 缺少 branch"
            continue
        if option in _WORKTREE_OPTIONS_WITH_VALUE:
            if separator:
                index += 1
            elif index + 1 < len(rest):
                index += 2
            else:
                return "", "", f"{option} 缺少值"
            continue
        if token == "--":
            positional.extend(rest[index + 1 :])
            break
        if token.startswith("-"):
            index += 1
            continue
        positional.append(token)
        index += 1
    if not branch:
        return "", "", "应显式使用 -b/--branch 指定 fixed lane branch"
    if len(positional) < 2:
        return branch, "", "应同时指定 path 与 start-point"
    if len(positional) > 2:
        return branch, "", "worktree add 存在多余 positional 参数"
    return branch, positional[1], ""


def _canonical_start_shas(repo_root: Path) -> set[str]:
    shas: set[str] = set()
    for ref in ("origin/dev1.0", "dev1.0"):
        code, sha = _git(repo_root, "rev-parse", "--verify", ref)
        if code == 0 and sha:
            shas.add(sha)
    return shas


def _validate_worktree_add(
    args: list[str], *, allowed_branches: frozenset[str], repo_root: Path
) -> tuple[str, str]:
    """返回 (detail, invalid_reason)。invalid 只用于注入 canonical 模板，不阻断。"""
    branch, start_point, invalid = _parse_worktree_add(args)
    lanes = frozenset(name for name in allowed_branches if name.startswith("lane/"))
    if invalid:
        return " ".join(args[1:]) or "未指定路径", invalid
    if branch not in lanes:
        return branch, f"branch 应是六条 fixed lane 之一，actual={branch or '<missing>'}"
    code, start_sha = _git(repo_root, "rev-parse", "--verify", f"{start_point}^{{commit}}")
    if code != 0 or not start_sha:
        return branch, f"start-point 不可解析：{start_point}"
    canonical = _canonical_start_shas(repo_root)
    if canonical and start_sha not in canonical:
        return branch, "start-point 应解析为 origin/dev1.0（或本地 dev1.0）"
    return branch, ""


def detect_all(
    command: str,
    *,
    allowed_branches: frozenset[str],
    repo_root: Path,
    env_var: str,
) -> list[Detection]:
    repo_names = _repository_names(repo_root)
    detections: list[Detection] = []
    for segment in _split_segments(command):
        assignments, tokens = _strip_prefix(_tokenize(segment))
        if not tokens or Path(tokens[0]).name != "git":
            continue
        subcommand, args = _git_subcommand(tokens)
        detection: Detection | None = None
        if subcommand == "worktree" and args and args[0] == "add":
            detail, invalid = _validate_worktree_add(
                args, allowed_branches=allowed_branches, repo_root=repo_root
            )
            detection = Detection(
                "worktree_add",
                detail,
                segment=segment,
                authorized=bool(_assignment_value(assignments, env_var)),
                invalid_reason=invalid,
            )
        elif subcommand == "clone":
            found = _detect_clone(args, repo_names, repo_root)
            if found:
                detection = Detection(
                    found.kind,
                    found.detail,
                    segment=segment,
                    authorized=bool(_assignment_value(assignments, env_var)),
                )
        elif subcommand in {"checkout", "switch"}:
            detection = _detect_branch_create(args, allowed_branches)
        elif subcommand == "branch":
            detection = _detect_branch_command(args, allowed_branches)
        if detection is not None:
            if not detection.segment:
                detection = Detection(
                    detection.kind,
                    detection.detail,
                    segment=segment,
                    authorized=bool(_assignment_value(assignments, env_var)),
                    invalid_reason=detection.invalid_reason,
                )
            detections.append(detection)
    return detections


def detect(command: str, *, allowed_branches: frozenset[str], repo_root: Path) -> Detection | None:
    """兼容测试/调用方的单 detection 视图；主判定使用 detect_all。"""
    detections = detect_all(
        command,
        allowed_branches=allowed_branches,
        repo_root=repo_root,
        env_var=_ENV_VAR_FALLBACK,
    )
    return detections[0] if detections else None


def is_authorized(command: str, env_var: str) -> bool:
    """兼容单 segment 授权查询；主流程始终逐 detection 检查。"""
    for segment in _split_segments(command):
        assignments, tokens = _strip_prefix(_tokenize(segment))
        if not tokens or Path(tokens[0]).name != "git":
            continue
        subcommand, args = _git_subcommand(tokens)
        if subcommand == "worktree" and args and args[0] == "add":
            return bool(_assignment_value(assignments, env_var))
        if subcommand in {"clone", "checkout", "switch", "branch"}:
            return bool(_assignment_value(assignments, env_var))
    return False


def record_authorization(detection: Detection, command: str, *, output_root: Path) -> None:
    target = output_root / "env/repo/local/worktree-governance/cache"
    try:
        target.mkdir(parents=True, exist_ok=True)
        with (target / "authorizations.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "at": int(time.time()),
                        "kind": detection.kind,
                        "detail": detection.detail,
                        "command": command[:500],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        return


def _canonical_template(env_var: str) -> str:
    return (
        f'{env_var}="<用户原话>" git worktree add -b <lane/...> <path> origin/dev1.0'
    )


def observation(
    detection: Detection, *, env_var: str, code: str, lanes: frozenset[str]
) -> str:
    """把一条未留痕/非 canonical 的检测转成注入给执行体的上下文；不含任何阻断语义。"""
    lines: list[str] = []
    if detection.invalid_reason:
        lines.append(
            f"OPS.WORKTREE.INVALID_ADD：{detection.invalid_reason}。"
            f"canonical 形态：{_canonical_template(env_var)}"
        )
    if not detection.authorized:
        lines.append(
            f"{code}：{detection.summary}。根 AGENTS.md Git 不变量要求先取得用户明确授权；"
            f'已获授权请在该 segment 前缀 `{env_var}="<用户同意的理由>"` 留痕，'
            "同一 compound command 中各 segment 分别留痕。"
        )
    if detection.kind == "branch_create" and lanes:
        lines.append("fixed lane 白名单：" + ", ".join(sorted(lanes)))
    lines.append("以上只是上下文提醒，未阻断命令；是否继续由你按用户意图判断。")
    return "\n".join(lines)


def _emit_cursor(message: str) -> dict[str, object]:
    if not message:
        return {"permission": "allow"}
    return {"permission": "allow", "user_message": message, "agent_message": message}


def _emit_codex(message: str) -> dict[str, object]:
    if not message:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": message,
        }
    }


def _read_command(harness: str, payload: dict[str, object]) -> str:
    if harness == "codex":
        tool_input = payload.get("tool_input")
        return str(tool_input.get("command") or "") if isinstance(tool_input, dict) else ""
    return str(payload.get("command") or "")


def _policy_failure_message(error: BaseException) -> str:
    detail = " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__
    return (
        "OPS.WORKTREE.POLICY_INVALID：worktree 授权策略不可读，本次未能核对创建形态"
        f"（{detail}）；recovery=repair_canonical_worktree_policy。"
        "命令未被阻断；新建 worktree/clone 仍须先取得用户明确授权。"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=("cursor", "codex"), required=True)
    args = parser.parse_args(argv)
    emit = _emit_cursor if args.harness == "cursor" else _emit_codex

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook payload must be an object")
        command = _read_command(args.harness, payload)
        if not _CREATION_HINT.search(command):
            print(json.dumps(emit(""), ensure_ascii=False))
            return 0
        import local_worktree_inventory as inventory

        policy = inventory.load_policy()
        env_var = policy.authorization_env_var
        code = policy.failure_code("not_authorized")
        lanes = frozenset(
            name for name in policy.allowed_local_branches if name.startswith("lane/")
        )
        detections = detect_all(
            command,
            allowed_branches=policy.allowed_local_branches,
            repo_root=ROOT,
            env_var=env_var,
        )
        messages: list[str] = []
        output_root = Path(os.environ.get("QWQ_OUTPUT_ROOT", str(ROOT / ".qwq_output")))
        for item in detections:
            if item.invalid_reason or not item.authorized:
                messages.append(observation(item, env_var=env_var, code=code, lanes=lanes))
            else:
                record_authorization(item, item.segment, output_root=output_root)
        output = emit("\n\n".join(messages))
    except Exception as exc:  # noqa: BLE001 - hook 必须把所有异常转为 allow + 观测消息
        output = emit(_policy_failure_message(exc))
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

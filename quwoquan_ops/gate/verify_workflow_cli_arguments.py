#!/usr/bin/env python3
"""阻断 workflow 调用仓内 Python CLI 时漏传 required 参数。

这类缺陷只会在 hosted 运行期以 argparse exit 2 暴露：workflow 静态合法、脚本单测通过、
本地 commit gate 全绿，然后门禁在第一个 step 上死掉。它不能靠 workflow lint 或脚本
自身测试发现，只能把「调用点传了什么」与「脚本声明必须要什么」放在同一处比对。

判定范围刻意收窄为可静态确定的部分：只看 `run:` 块中以 `python3`（可带 `-B`）直接
执行 `quwoquan_*/**.py` 的命令；required 集合按 argparse parser 变量追踪，子命令按
`add_parser("name")` 的名字归属到调用行的第一个位置参数。以下形态无法静态判定，
一律跳过且不伪装成已检查：`$(...)` / 反引号捕获、heredoc、`"${arr[@]}"` 数组展开、
`$VAR` 位置透传、mutually exclusive group、通过函数或 `main(argv)` 间接构造的 parser。
"""

from __future__ import annotations

import argparse
import ast
import re
import shlex
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REPO_SCRIPT = re.compile(r"^quwoquan_(?:app|service|data|ops)/[A-Za-z0-9_./-]+\.py$")
SHELL_BREAK = {"|", "||", "&&", ";", ">", ">>", "2>", "2>&1", "<"}
# 出现这些 token 说明参数来自运行期展开，静态无法判定。
OPAQUE_TOKEN = re.compile(r"^\"?\$\{?[A-Za-z_][A-Za-z0-9_]*(?:\[@\]|\[\*\])?\}?\"?$")


@dataclass
class ParserSpec:
    """一个脚本的 argparse 形状：顶层 required 与各子命令 required。

    `dynamic_required` 表示存在名字由运行期表达式（f-string、变量）决定的 required
    选项；这类选项无法静态比对，此时只能对已知常量名做检查，且缺失判定不再宣称完整。
    """

    top_level: frozenset[str] = frozenset()
    subcommands: dict[str, frozenset[str]] = field(default_factory=dict)
    has_subcommands: bool = False
    dynamic_required: bool = False


def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _name_of(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def parser_spec(script: Path) -> ParserSpec | None:
    """从源码静态还原 argparse 形状；脚本不用 argparse 或无法解析时返回 None。"""
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return None
    # 变量名 -> 该 parser 收集的 required 长选项
    required_by_parser: dict[str, set[str]] = {}
    # 子命令 parser 变量名 -> 子命令名
    subcommand_name: dict[str, str] = {}
    subparser_vars: set[str] = set()
    root_parsers: set[str] = set()
    uses_argparse = False
    dynamic_required = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            func = call.func
            targets = [_name_of(target) for target in node.targets]
            target = next((item for item in targets if item), None)
            if target is None:
                continue
            if isinstance(func, ast.Attribute) and func.attr == "ArgumentParser":
                root_parsers.add(target)
                required_by_parser.setdefault(target, set())
                uses_argparse = True
            elif isinstance(func, ast.Attribute) and func.attr == "add_subparsers":
                subparser_vars.add(target)
                uses_argparse = True
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "add_parser"
                and _name_of(func.value) in subparser_vars
                and call.args
                and _const_str(call.args[0]) is not None
            ):
                subcommand_name[target] = _const_str(call.args[0]) or ""
                required_by_parser.setdefault(target, set())
                uses_argparse = True
        elif isinstance(node, ast.Call):
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
                continue
            owner = _name_of(func.value)
            if owner is None:
                continue
            uses_argparse = True
            is_required = any(
                keyword.arg == "required"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            if not is_required:
                continue
            for arg in node.args:
                value = _const_str(arg)
                if value and value.startswith("--"):
                    required_by_parser.setdefault(owner, set()).add(value)
                elif value is None:
                    dynamic_required = True

    if not uses_argparse:
        return None
    top_level: set[str] = set()
    for name in root_parsers:
        top_level |= required_by_parser.get(name, set())
    subcommands = {
        command: frozenset(required_by_parser.get(var, set()))
        for var, command in subcommand_name.items()
    }
    return ParserSpec(
        top_level=frozenset(top_level),
        subcommands=subcommands,
        has_subcommands=bool(subparser_vars),
        dynamic_required=dynamic_required,
    )


@lru_cache(maxsize=None)
def _spec_for(root: Path, relative: str) -> ParserSpec | None:
    return parser_spec(root / relative)


def _run_blocks(text: str) -> list[str]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    blocks: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            run = value.get("run")
            if isinstance(run, str):
                blocks.append(run)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    return blocks


def _logical_commands(block: str) -> list[str]:
    """合并反斜杠续行，按行拆成单条命令；heredoc 正文整段跳过。"""
    commands: list[str] = []
    buffer = ""
    heredoc_terminator: str | None = None
    for raw in block.splitlines():
        if heredoc_terminator is not None:
            if raw.strip() == heredoc_terminator:
                heredoc_terminator = None
            continue
        heredoc = re.search(r"<<-?\s*'?([A-Za-z_][A-Za-z0-9_]*)'?", raw)
        if heredoc is not None:
            heredoc_terminator = heredoc.group(1)
            continue
        if raw.rstrip().endswith("\\"):
            buffer += raw.rstrip()[:-1] + " "
            continue
        commands.append(buffer + raw)
        buffer = ""
    if buffer:
        commands.append(buffer)
    return commands


def _python_invocations(command: str) -> list[tuple[str, list[str]]]:
    """返回 (仓内脚本相对路径, 其后 token 列表)；含命令替换或反引号的整行不解析。"""
    if "$(" in command or "`" in command:
        return []
    try:
        tokens = shlex.split(command, comments=True, posix=True)
    except ValueError:
        return []
    invocations: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(tokens):
        if tokens[index] in {"python3", "python"}:
            cursor = index + 1
            while cursor < len(tokens) and tokens[cursor].startswith("-") and tokens[cursor] != "-":
                cursor += 1
            if cursor < len(tokens) and REPO_SCRIPT.fullmatch(tokens[cursor]):
                tail: list[str] = []
                for token in tokens[cursor + 1 :]:
                    if token in SHELL_BREAK:
                        break
                    tail.append(token)
                invocations.append((tokens[cursor], tail))
                index = cursor + 1 + len(tail)
                continue
        index += 1
    return invocations


def _is_opaque(tail: list[str]) -> bool:
    """变量出现在位置参数位置（不是某个选项的值）时，静态无法判定 required 是否被覆盖。

    `--flag "$VALUE"` 里的 `$VALUE` 只是选项值，选项名本身已可见，不算透传；
    `"${args[@]}"` 或独立的 `$EXTRA` 才可能在运行期展开成任意选项。
    """
    previous_is_option = False
    for token in tail:
        if token.startswith("--"):
            previous_is_option = "=" not in token
            continue
        if OPAQUE_TOKEN.fullmatch(token) is not None and not previous_is_option:
            return True
        previous_is_option = False
    return False


def _passed_options(tail: list[str]) -> set[str]:
    return {token.split("=", 1)[0] for token in tail if token.startswith("--")}


def missing_required(script: str, tail: list[str], *, root: Path = ROOT) -> list[str] | None:
    """返回缺失的 required 常量选项；无法静态判定时返回 None。

    脚本含运行期命名的 required 选项（f-string、变量）时整体不可判定：即便常量名齐全，
    动态名仍可能缺失，报"完整"是假绿；只报常量缺失又会让调用方以为补齐即可。
    这类脚本的合同由其自身 local_contract 与 hosted 运行承担。
    """
    spec = _spec_for(root, script)
    if spec is None or spec.dynamic_required or _is_opaque(tail):
        return None
    expected = set(spec.top_level)
    if spec.has_subcommands:
        positional = next((token for token in tail if not token.startswith("-")), None)
        if positional is None or positional not in spec.subcommands:
            return None
        expected |= spec.subcommands[positional]
    if not expected:
        return []
    return sorted(expected - _passed_options(tail))


def verify(root: Path = ROOT, *, only: frozenset[str] | None = None) -> list[str]:
    """`only` 为仓根相对路径集合；给出时只校验其中的 workflow（L0 按 staged 收窄）。"""
    workflow_root = root / ".github" / "workflows"
    issues: list[str] = []
    for workflow in sorted([*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")]):
        if only is not None and workflow.relative_to(root).as_posix() not in only:
            continue
        text = workflow.read_text(encoding="utf-8")
        for block in _run_blocks(text):
            for command in _logical_commands(block):
                for script, tail in _python_invocations(command):
                    missing = missing_required(script, tail, root=root)
                    if missing:
                        issues.append(
                            f"{workflow.relative_to(root)}: {script} invoked without required "
                            f"{', '.join(missing)}; argparse exits 2 at runtime"
                        )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--workflow", action="append", default=[],
        help="仓根相对路径；给出时只校验这些 workflow（可重复）。默认全量。",
    )
    args = parser.parse_args(argv)
    only = frozenset(args.workflow) if args.workflow else None
    issues = verify(args.repo_root.resolve(), only=only)
    if issues:
        print("[verify_workflow_cli_arguments] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_workflow_cli_arguments] OK")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())

"""Python 文件行数硬顶。

预算范围：四棵树内所有派生边界为 ``managed_script`` / ``production_module`` /
``test_support`` / ``test_evidence`` 的 Python 文件，实现与测试统一 1000 行
（pylint ``max-module-lines`` 默认值）。``vendor`` / ``generated`` 不占预算；
``quwoquan_data/scripts/**`` 不在本预算内——它由 ``verify_script_architecture``
的 600/500/400 更严硬顶单轨负责，这里重复计数只会制造第二真相源。

零 allowlist、零 baseline：存量清零前由 ``PYTHON_LINE_BUDGET_ENFORCEMENT``
保持 ``warn``，清零后切 ``block`` 进入 check 阻断。唯一的结构性例外从
shell 编排事实机器派生（见 ``stdin_piped_contract_scripts``），依据
``specs/feature-tree/platform-ops-governance/config-and-reliability-governance/``
``spec.md#sit-002``。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from .constants import (
    PYTHON_LINE_BUDGET_MAX_LINES,
    TRAVERSAL_IGNORED_DIR_NAMES,
)
from .models import Issue, PythonFileRecord
from .references import read_text

_BUDGETED_BOUNDARIES = frozenset(
    {
        "managed_script",
        "production_module",
        "test_support",
        "test_evidence",
    }
)
_DATA_SCRIPTS_PREFIX = "quwoquan_data/scripts/"

#: 裸 ``python3 -`` stdin 执行形态；``python3 - <<`` 是内联 heredoc，不是把
#: 某个仓库文件整文件 pipe 出去，因此显式排除。
_STDIN_PYTHON_RE = re.compile(r"python3\s+-\s*(?!<)", re.MULTILINE)
_REPO_PY_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(quwoquan_(?:app|service|data|ops)/[A-Za-z0-9_./-]+\.py)"
    r"(?![A-Za-z0-9_.-])"
)
#: ``var="…/xxx.py"`` 形态的变量赋值：捕获变量名与仓库相对 py 路径。
_VAR_PY_ASSIGN_RE = re.compile(
    r"^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)=[\"']?[^\n\"']*?"
    r"(?P<path>quwoquan_(?:app|service|data|ops)/[A-Za-z0-9_./-]+\.py)[\"']?\s*$",
    re.MULTILINE,
)
#: ``< "$var"`` / ``< $var`` 形态的 stdin 重定向消费。
_STDIN_REDIRECT_VAR_RE = re.compile(r"<\s*\"?\$\{?(?P<var>[A-Za-z_][A-Za-z0-9_]*)\}?\"?")
#: ``python3 - < "path.py"`` 直接字面量重定向。
_DIRECT_PIPE_RE = re.compile(
    r"python3\s+-\s*<\s*\"?"
    r"(?P<path>[^\"\n]*quwoquan_(?:app|service|data|ops)/[A-Za-z0-9_./-]+\.py)\"?"
)


@lru_cache(maxsize=4)
def stdin_piped_contract_scripts(root: Path) -> frozenset[str]:
    """从 shell 编排事实派生「整文件经 stdin pipe 到裸 python3 执行」的脚本集。

    这类脚本（如 ``sync_prod_plane_stack.sh`` 之于 ``hosted_release_ledger.py``）
    在远端裸 ``python3 -`` 环境执行（远端无仓库树可 import），单文件自包含是
    物理设计契约，行数预算不适用。豁免由 shell 调用形态机器验证派生，不是
    人工 allowlist，判据同一 shell 文件内三者同源缺一不可：

    1. 存在非 heredoc 的 ``python3 -`` stdin 执行形态（含赋给变量再执行）；
    2. 某变量被赋值为该 Python 文件路径，且该变量以 ``< "$var"`` 被消费为
       stdin（或存在 ``python3 - < "path.py"`` 直接重定向）；
    3. 该 Python 文件物理存在。

    契约锚点见 ``config-and-reliability-governance/spec.md#sit-002``；协议
    改造后取消豁免由同 spec ``#sit-003`` / ``OPEN-002`` 承接。
    """
    exempt: set[str] = set()
    ops_root = root / "quwoquan_ops"
    if not ops_root.is_dir():
        return frozenset()
    for shell_path in sorted(ops_root.rglob("*.sh")):
        if any(part in TRAVERSAL_IGNORED_DIR_NAMES for part in shell_path.parts):
            continue
        text = read_text(shell_path)
        if not text or not _STDIN_PYTHON_RE.search(text):
            continue
        candidates: set[str] = set()
        assignments = {
            match.group("var"): match.group("path")
            for match in _VAR_PY_ASSIGN_RE.finditer(text)
        }
        consumed_vars = {
            match.group("var") for match in _STDIN_REDIRECT_VAR_RE.finditer(text)
        }
        for var, path in assignments.items():
            if var in consumed_vars:
                candidates.add(path)
        for match in _DIRECT_PIPE_RE.finditer(text):
            repo_match = _REPO_PY_PATH_RE.search(match.group("path"))
            if repo_match:
                candidates.add(repo_match.group(1))
        for candidate in candidates:
            if (root / candidate).is_file():
                exempt.add(candidate)
    return frozenset(exempt)


def _line_count(path: Path) -> int:
    text = read_text(path)
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def line_budget_issues(
    root: Path,
    python_file_records: Sequence[PythonFileRecord],
) -> list[Issue]:
    issues: list[Issue] = []
    piped_contract_scripts = stdin_piped_contract_scripts(root)
    for record in python_file_records:
        if record.boundary not in _BUDGETED_BOUNDARIES:
            continue
        if record.path.startswith(_DATA_SCRIPTS_PREFIX):
            continue
        if record.path in piped_contract_scripts:
            continue
        lines = _line_count(root / record.path)
        if lines <= PYTHON_LINE_BUDGET_MAX_LINES:
            continue
        issues.append(
            Issue(
                code="PYTHON.LINE_BUDGET_EXCEEDED",
                path=record.path,
                message=(
                    f"{lines} lines exceeds the "
                    f"{PYTHON_LINE_BUDGET_MAX_LINES}-line module budget; "
                    "split by responsibility into the owning package"
                ),
            )
        )
    return issues

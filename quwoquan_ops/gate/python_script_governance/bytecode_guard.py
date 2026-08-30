"""可直接调用入口的字节码抑制守卫。

源码树禁留 `__pycache__` 是仓库不变量，但它此前只由调用方环境变量保证：
`Makefile` 导出 `PYTHONDONTWRITEBYTECODE`，凡绕过 make 直接
`python3 quwoquan_ops/gate/<x>.py` 的调用都会把 pyc 写进源码树，随后被
`PYTHON.SOURCE_CACHE_FORBIDDEN` 报成违规——门禁自己制造自己的失败。

被导入的模块在**执行前**就已写出 pyc，所以守卫只能落在入口自身，且必须早于
第一次仓内 import。本检查因此要求：任何带 `__main__` 块的稳定脚本，若会触发
仓内 import（`sys.path` 变更、`quwoquan_*` 包、bootstrap 同级模块或相对
import），必须先设 `sys.dont_write_bytecode = True`。无仓内 import 的入口不
可能污染，不受本检查约束。

范围取 `enumerate_scripts` 的稳定脚本闭集，与 AGENTS.md 的脚本角色治理同源。
测试树不在内：pytest 入口由 `-B` 与 cache_dir 重定向这条既有约定负责，两套
机制各自完整，不互相复制。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Sequence

from .inventory import enumerate_scripts
from .models import Issue, relative_path

_SYS_PATH_MUTATORS = frozenset({"insert", "append", "extend"})


def _is_guard(node: ast.AST) -> bool:
    """`sys.dont_write_bytecode = True` 赋值。"""
    if not isinstance(node, ast.Assign):
        return False
    if not (isinstance(node.value, ast.Constant) and node.value.value is True):
        return False
    return any(
        isinstance(target, ast.Attribute)
        and target.attr == "dont_write_bytecode"
        and isinstance(target.value, ast.Name)
        and target.value.id == "sys"
        for target in node.targets
    )


def _is_sys_path_mutation(node: ast.AST) -> bool:
    """`sys.path.insert/append/extend(...)` 调用。"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in _SYS_PATH_MUTATORS):
        return False
    owner = func.value
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "path"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "sys"
    )


def _bootstrap_module_names(root: Path, path: Path) -> frozenset[str]:
    """入口经 `sys.path` 提升后可裸 import 的仓内同级/祖先模块名。"""
    names: set[str] = set()
    for parent in path.parents:
        if not parent.is_relative_to(root):
            break
        names.update(
            candidate.stem
            for candidate in parent.glob("*.py")
            if candidate.is_file()
        )
    return frozenset(names)


def _imports_repository_module(
    node: ast.AST,
    *,
    bootstrap_names: frozenset[str],
) -> bool:
    if isinstance(node, ast.ImportFrom):
        if node.level:
            return True
        module = (node.module or "").split(".")[0]
        return module.startswith("quwoquan_") or module in bootstrap_names
    if isinstance(node, ast.Import):
        return any(
            alias.name.split(".")[0].startswith("quwoquan_")
            or alias.name.split(".")[0] in bootstrap_names
            for alias in node.names
        )
    return False


def _is_main_entry(tree: ast.Module) -> bool:
    """模块级 `if __name__ == "__main__":` 使文件可被直接调用。"""
    for statement in tree.body:
        if not isinstance(statement, ast.If):
            continue
        test = statement.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and any(
                isinstance(comparator, ast.Constant)
                and comparator.value == "__main__"
                for comparator in test.comparators
            )
        ):
            return True
    return False


def _guard_precedes_repository_import(
    tree: ast.Module,
    *,
    bootstrap_names: frozenset[str],
) -> bool:
    """按模块级语句序判定守卫是否早于第一次仓内 import。

    bootstrap 把 `sys.path.insert` 藏在 `if` 里，所以逐条顶层语句要递归查找，
    只有顶层顺序才决定先后。
    """
    for statement in tree.body:
        nodes = list(ast.walk(statement))
        if any(_is_guard(node) for node in nodes):
            return True
        if any(
            _is_sys_path_mutation(node)
            or _imports_repository_module(node, bootstrap_names=bootstrap_names)
            for node in nodes
        ):
            return False
    # 没有任何仓内 import：入口不可能写出仓内 pyc。
    return True


def bytecode_guard_issues(root: Path, scopes: Sequence[str]) -> list[Issue]:
    issues: list[Issue] = []
    for scope in scopes:
        for path in enumerate_scripts(root, scope):
            if path.suffix != ".py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeError):
                continue
            if not _is_main_entry(tree):
                continue
            if _guard_precedes_repository_import(
                tree,
                bootstrap_names=_bootstrap_module_names(root, path),
            ):
                continue
            issues.append(
                Issue(
                    code="PYTHON.BYTECODE_GUARD_MISSING",
                    path=relative_path(root, path),
                    message=(
                        "directly invocable entry must set "
                        "sys.dont_write_bytecode = True before its first "
                        "repository import, so running it never writes pyc "
                        "into the source tree"
                    ),
                )
            )
    return issues

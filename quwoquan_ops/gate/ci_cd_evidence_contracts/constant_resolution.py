"""静态解析仓内常量的取值，含跨模块引用溯源。

schema identity 的正确形态是「一处定义、别处引用」。若只认字面量，引用共享常量
反而会被判成漂移，把契约推回复制粘贴。因此这里在字面量求值之外，额外沿
`from <module> import <name>` 溯源到定义模块继续求值。
"""

from __future__ import annotations

import ast
from pathlib import Path

MAX_REFERENCE_DEPTH = 3


def module_path(module: str, root: Path) -> Path | None:
    """把 `a.b.c` 解析成仓内文件；解析不到就是不可静态判定，返回缺席。"""
    candidate = root / Path(*module.split("."))
    if candidate.is_dir():
        candidate = candidate / "__init__.py"
    else:
        candidate = candidate.with_suffix(".py")
    return candidate if candidate.is_file() else None


def imported_constant_source(
    tree: ast.Module, name: str, root: Path
) -> Path | None:
    """找出 `from <module> import <name>` 中 name 的定义文件。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.level:
            # 相对导入的锚点是包路径而非仓库根，这里不猜，交由调用方按缺席处理。
            continue
        for alias in node.names:
            if (alias.asname or alias.name) == name:
                return module_path(node.module, root)
    return None


def resolve_literal(
    tree: ast.Module, node: ast.expr, root: Path, depth: int = 0
) -> object:
    """按字面量求值，并额外解析对同仓常量的引用。

    跨模块链路有限深度，无法静态判定即返回缺席。
    """
    if depth > MAX_REFERENCE_DEPTH:
        return None
    if isinstance(node, ast.Name):
        source = imported_constant_source(tree, node.id, root)
        if source is None:
            return None
        return constant_value(source, node.id, root, depth + 1)
    if isinstance(node, ast.Dict):
        resolved: dict[object, object] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                return None
            key = resolve_literal(tree, key_node, root, depth)
            value = resolve_literal(tree, value_node, root, depth)
            if key is None or value is None:
                return None
            resolved[key] = value
        return resolved
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def constant_value(
    path: Path, constant_name: str, root: Path, depth: int = 0
) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == constant_name
            for target in targets
        ):
            continue
        value = node.value
        if value is None:
            return None
        return resolve_literal(tree, value, root, depth)
    return None

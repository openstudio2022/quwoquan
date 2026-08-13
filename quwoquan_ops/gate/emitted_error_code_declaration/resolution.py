"""发射侧公共设施：作用域内标识符解析与各语言生产源文件枚举。"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import (
    SERVICE_DIR,
    _GO_SKIP_DIRS,
    _FUNC_SPLIT,
    _MAX_RESOLVE_DEPTH,
    _QUALIFIED_IDENT,
    _STRING_LITERAL,
)


def _assignment_values(scope_text: str, ident: str) -> list[str]:
    """收集作用域内对 ident 的全部赋值右值（`=` / `:=`，排除 `==` 等比较）。"""
    pattern = re.compile(
        r"(?:^|[^\w.])" + re.escape(ident) + r"\s*(?<![=!<>])(?::=|=)(?!=)\s*(?P<rhs>[^\n]+)"
    )
    values: list[str] = []
    for match in pattern.finditer(scope_text):
        rhs = match.group("rhs").strip().rstrip(",").strip()
        if rhs and rhs not in values:
            values.append(rhs)
    return values


def _resolve_symbol(
    expression: str,
    scopes: tuple[str, ...],
    table: dict[str, str],
    converter: re.Pattern[str],
    depth: int = 0,
) -> set[str]:
    """把 module/kind 表达式解析成取值集合。空集合代表解析失败。"""
    expression = expression.strip()
    if not expression or depth > _MAX_RESOLVE_DEPTH:
        return set()
    conversion = converter.match(expression)
    if conversion:
        return {conversion.group(1)}
    literal = _STRING_LITERAL.match(expression)
    if literal:
        return {literal.group(1)}
    ident_match = _QUALIFIED_IDENT.match(expression)
    if ident_match is None:
        return set()
    ident = ident_match.group(1)
    if ident in table:
        return {table[ident]}
    resolved: set[str] = set()
    for scope_text in scopes:
        for value in _assignment_values(scope_text, ident):
            resolved |= _resolve_symbol(value, scopes, table, converter, depth + 1)
        if resolved:
            break
    return resolved


def _resolve_reason(
    expression: str,
    scopes: tuple[str, ...],
    reasons: dict[str, str],
    depth: int = 0,
) -> set[str]:
    expression = expression.strip().rstrip(",").strip()
    if not expression or depth > _MAX_RESOLVE_DEPTH:
        return set()
    literal = _STRING_LITERAL.match(expression)
    if literal:
        value = literal.group(1)
        return {value} if re.fullmatch(r"[a-z][a-z0-9_]*", value) else set()
    ident_match = _QUALIFIED_IDENT.match(expression)
    if ident_match is None:
        return set()
    ident = ident_match.group(1)
    if ident in reasons:
        return {reasons[ident]}
    resolved: set[str] = set()
    for scope_text in scopes:
        for value in _assignment_values(scope_text, ident):
            resolved |= _resolve_reason(value, scopes, reasons, depth + 1)
        if resolved:
            break
    return resolved


def _function_name(function_text: str) -> str:
    match = re.match(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z0-9_]+)", "func " + function_text)
    return match.group(1) if match else "<file-scope>"


def _split_functions(text: str) -> list[str]:
    parts = _FUNC_SPLIT.split(text)
    return parts[1:] if len(parts) > 1 else []


def _package_scope(text: str) -> str:
    """函数体之外的文本，用于解析包级 const/var 别名（moduleTag / moduleSearch）。"""
    parts = _FUNC_SPLIT.split(text)
    return parts[0] if parts else text


def _go_files(root: Path) -> list[Path]:
    service_root = root / SERVICE_DIR
    if not service_root.is_dir():
        return []
    files: list[Path] = []
    for path in service_root.rglob("*.go"):
        if path.name.endswith("_test.go"):
            continue
        if any(part in _GO_SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _dart_files(root: Path) -> list[Path]:
    app_root = root / "quwoquan_app" / "lib"
    if not app_root.is_dir():
        return []
    return sorted(
        path
        for path in app_root.rglob("*.dart")
        if "generated" not in path.parts
        and not any(part in _GO_SKIP_DIRS for part in path.parts)
    )


def _swift_files(root: Path) -> list[Path]:
    """Return first-party iOS production sources, excluding Pods/generated/tests."""
    runner_root = root / "quwoquan_app" / "ios" / "Runner"
    if not runner_root.is_dir():
        return []
    return sorted(
        path
        for path in runner_root.rglob("*.swift")
        if "generated" not in path.parts
        and "Tests" not in path.parts
        and not any(part in _GO_SKIP_DIRS for part in path.parts)
    )


def _python_files(root: Path) -> list[Path]:
    services_root = root / "quwoquan_service" / "services"
    if not services_root.is_dir():
        return []
    return sorted(
        path
        for path in services_root.rglob("*.py")
        if "internal" in path.parts
        and "generated" not in path.parts
        and "tests" not in path.parts
        and "test" not in path.parts
        and not path.name.startswith("test_")
        and not any(part in _GO_SKIP_DIRS for part in path.parts)
    )

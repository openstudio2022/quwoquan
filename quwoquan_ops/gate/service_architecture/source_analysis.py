"""源码实质性判定：非占位实现/测试识别、spec_ref 追溯与 lifecycle handler 绑定。"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
import re
from typing import Iterable

from .constants import OBJECT_TEST_SPEC_REF_RE, ROOT
from .object_semantics import camel_to_snake


def is_substantive_implementation_source(path: Path) -> bool:
    """Return whether *path* contains non-test implementation, not a placeholder.

    Object ownership is code ownership.  Package declarations, imports, comments,
    docstrings and ``pass``-only Python modules cannot satisfy a DDD layer.
    """

    if path.suffix not in {".go", ".py"}:
        return False
    if (
        path.name.endswith("_test.go")
        or path.name.startswith("test_")
        or "__local_contract_test" in path.name
        or "__api_integration_test" in path.name
    ):
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return False
    if path.suffix == ".py":
        try:
            module = ast.parse(text)
        except SyntaxError:
            # Syntax validation belongs to the language gate.  It must not let a
            # malformed file masquerade as an empty placeholder here.
            return True
        meaningful = []
        for node in ast.walk(module):
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.Pass)):
                continue
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue
            meaningful.append(node)
        return bool(meaningful)

    without_block_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    without_line_comments = re.sub(r"(?m)//.*$", "", without_block_comments)
    without_package = re.sub(
        r"(?m)^\s*package\s+[A-Za-z_][A-Za-z0-9_]*\s*$", "", without_line_comments
    )
    without_import_blocks = re.sub(
        r'(?ms)^\s*import\s*\(.*?^\s*\)\s*$', "", without_package
    )
    without_single_imports = re.sub(
        r'(?m)^\s*import\s+(?:[A-Za-z_][A-Za-z0-9_]*\s+)?"[^"]+"\s*$',
        "",
        without_import_blocks,
    )
    return bool(without_single_imports.strip())


def go_import_declarations(text: str) -> str:
    """Return only the import declarations of a Go source file.

    Cross-service dependency can only be established through an import.  Service
    paths appearing elsewhere are data — scan roots, contract inventories, error
    strings — and treating them as dependencies makes the boundary check fire on
    tests that legitimately enumerate other services' paths.
    """

    blocks = re.findall(r"(?ms)^\s*import\s*\((.*?)^\s*\)\s*$", text)
    singles = re.findall(
        r'(?m)^\s*import\s+(?:[A-Za-z_][A-Za-z0-9_]*\s+)?("[^"]+")\s*$', text
    )
    return "\n".join([*blocks, *singles])


def is_substantive_test_source(path: Path) -> bool:
    """Return whether *path* contains at least one non-empty executable test.

    Object-level evidence cannot be satisfied by a package marker, support file,
    test fixture or an empty test function merely placed under the right path.
    Service tests are Go or Python today, so keep this check deliberately narrow
    and fail closed for other file types.
    """

    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".go" and path.name.endswith("_test.go"):
        without_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        without_comments = re.sub(r"(?m)//.*$", "", without_comments)
        for match in re.finditer(
            r"(?ms)^\s*func\s+Test[A-Za-z0-9_]*\s*\([^)]*\)\s*\{(?P<body>.*?)^\s*\}",
            without_comments,
        ):
            if match.group("body").strip():
                return True
        return False
    if path.suffix == ".py" and path.name.startswith("test_"):
        try:
            module = ast.parse(text)
        except SyntaxError:
            return False
        for node in module.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            meaningful = [
                item
                for item in node.body
                if not isinstance(item, ast.Pass)
                and not (
                    isinstance(item, ast.Expr)
                    and isinstance(item.value, ast.Constant)
                    and isinstance(item.value.value, str)
                )
            ]
            if meaningful:
                return True
        return False
    return False


def valid_object_test_spec_refs(
    path: Path,
    repo_root: Path = ROOT,
) -> tuple[set[str], list[str]]:
    """Return valid feature-tree acceptance refs declared by an executable test.

    Object evidence is only traceable when the physical test names a repository
    feature-tree spec and an existing UAT/DOM/SIT/GWT anchor.  A support file,
    arbitrary Markdown path or missing heading cannot satisfy this contract.
    """

    source = path.read_text(encoding="utf-8", errors="replace")
    refs: set[str] = set()
    issues: list[str] = []
    feature_tree_root = (repo_root / "specs" / "feature-tree").resolve()
    for spec_path, case_id in OBJECT_TEST_SPEC_REF_RE.findall(source):
        target = (repo_root / spec_path).resolve()
        try:
            target.relative_to(feature_tree_root)
        except ValueError:
            issues.append(f"spec_ref escapes feature tree: {spec_path}#{case_id}")
            continue
        reference = f"{spec_path}#{case_id.lower()}"
        if not target.is_file():
            issues.append(f"spec_ref target does not exist: {reference}")
            continue
        anchor = f'<a id="{case_id.lower()}"></a>'
        if anchor not in target.read_text(encoding="utf-8", errors="replace").lower():
            issues.append(f"spec_ref acceptance anchor does not exist: {reference}")
            continue
        refs.add(reference)
    return refs, issues


def _go_source_without_comments_or_literals(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"(?m)//.*$", "", source)
    source = re.sub(r"`[^`]*`", "", source, flags=re.DOTALL)
    source = re.sub(r'"(?:\\.|[^"\\])*"', "", source)
    source = re.sub(r"'(?:\\.|[^'\\])'", "", source)
    return source


def _python_decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _python_decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _python_decorator_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _python_not_implemented_value(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"NotImplemented", "NotImplementedError"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"NotImplemented", "NotImplementedError"}
    if isinstance(node, ast.Call):
        return _python_not_implemented_value(node.func)
    return False


def _python_handler_method_is_substantive(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    if any(
        _python_decorator_name(decorator).split(".")[-1] == "abstractmethod"
        for decorator in node.decorator_list
    ):
        return False

    meaningful: list[ast.stmt] = []
    for statement in node.body:
        if isinstance(statement, ast.Pass):
            continue
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and (
                isinstance(statement.value.value, str)
                or statement.value.value is Ellipsis
            )
        ):
            continue
        meaningful.append(statement)
    if not meaningful:
        return False

    def is_not_implemented_only(statement: ast.stmt) -> bool:
        if isinstance(statement, ast.Raise):
            return _python_not_implemented_value(statement.exc)
        if isinstance(statement, ast.Return):
            return statement.value is None or _python_not_implemented_value(
                statement.value
            )
        if isinstance(statement, ast.Expr):
            return _python_not_implemented_value(statement.value)
        return False

    return not all(is_not_implemented_only(statement) for statement in meaningful)


def _matching_delimiter(
    source: str,
    start: int,
    opening: str,
    closing: str,
) -> int | None:
    if start >= len(source) or source[start] != opening:
        return None
    depth = 0
    for index in range(start, len(source)):
        character = source[index]
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _go_method_body_open(source: str, start: int) -> int | None:
    paren_depth = 0
    bracket_depth = 0
    index = start
    while index < len(source):
        character = source[index]
        if character == "(":
            paren_depth += 1
        elif character == ")":
            paren_depth = max(0, paren_depth - 1)
        elif character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif character == "{" and paren_depth == 0 and bracket_depth == 0:
            prefix = source[start:index].rstrip()
            if re.search(r"\b(?:struct|interface)\s*$", prefix):
                closing = _matching_delimiter(source, index, "{", "}")
                if closing is None:
                    return None
                start = closing + 1
                index = start
                continue
            return index
        index += 1
    return None


def _go_return_is_literal_only(body: str) -> bool:
    normalized = re.sub(r"\s+", " ", body).strip().rstrip(";").strip()
    if not normalized.startswith("return"):
        return False
    remainder = normalized.removeprefix("return").strip()
    if not remainder:
        return True
    literal = re.compile(
        r"(?:nil|true|false|"
        r"[-+]?(?:0[xX][0-9A-Fa-f]+|0[bB][01]+|0[oO][0-7]+|"
        r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?))"
    )
    return all(
        not value.strip() or literal.fullmatch(value.strip())
        for value in remainder.split(",")
    )


def _go_handler_method_is_substantive(
    source: str,
    facet: str,
    method_names: set[str],
) -> bool:
    method_head = re.compile(
        rf"\bfunc\s*\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?\*?\s*"
        rf"{re.escape(facet)}(?:\[[^\]]+\])?\s*\)\s+"
        rf"({'|'.join(re.escape(name) for name in sorted(method_names))})\s*"
    )
    for match in method_head.finditer(source):
        parameter_open = match.end()
        if parameter_open >= len(source) or source[parameter_open] != "(":
            continue
        parameter_close = _matching_delimiter(source, parameter_open, "(", ")")
        if parameter_close is None:
            continue
        body_open = _go_method_body_open(source, parameter_close + 1)
        if body_open is None:
            continue
        body_close = _matching_delimiter(source, body_open, "{", "}")
        if body_close is None:
            continue
        body = source[body_open + 1 : body_close].strip().strip(";").strip()
        if not body:
            continue
        if re.fullmatch(r"panic\s*\(.*\)", body, flags=re.DOTALL):
            continue
        if _go_return_is_literal_only(body):
            continue
        return True
    return False


def lifecycle_handler_binding_issues(
    consumers: list[dict[str, str]],
    object_source_root: Path,
    source_paths: Iterable[Path],
) -> list[str]:
    """Bind every authored lifecycle edge to a same-object concrete handler."""

    python_classes: dict[str, set[str]] = defaultdict(set)
    go_sources: list[str] = []
    resolved_root = object_source_root.resolve()
    for source_path in source_paths:
        try:
            source_path.resolve().relative_to(resolved_root)
        except ValueError:
            continue
        if source_path.suffix == ".py":
            try:
                module = ast.parse(source_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in module.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                methods = {
                    child.name
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and _python_handler_method_is_substantive(child)
                }
                python_classes[node.name].update(methods)
        elif source_path.suffix == ".go":
            go_sources.append(
                _go_source_without_comments_or_literals(
                    source_path.read_text(encoding="utf-8", errors="replace")
                )
            )

    go_source = "\n".join(go_sources)
    issues: list[str] = []
    for consumer in consumers:
        facet = consumer["facet"]
        method = consumer["method"]
        python_methods = {method, camel_to_snake(method)}
        python_bound = bool(python_classes.get(facet, set()) & python_methods)
        go_method = method[:1].upper() + method[1:]
        go_type = bool(re.search(rf"\btype\s+{re.escape(facet)}\s+struct\b", go_source))
        go_bound = go_type and _go_handler_method_is_substantive(
            go_source,
            facet,
            {method, go_method},
        )
        if not python_bound and not go_bound:
            issues.append(
                f"lifecycle consumer {consumer['name']} must bind same-object "
                f"handler {facet}.{method}"
            )
    return issues

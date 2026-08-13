"""Go/Dart/TS/Python 的最小词法与 import 边提取：注释与字符串诱饵不参与判定。"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path


def _c_style_tokens(text: str) -> list[tuple[str, str]]:
    """Small lexer for Go/Dart/TS: discard comments, preserve strings and code."""
    tokens: list[tuple[str, str]] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            depth = 1
            index += 2
            while index < length and depth:
                if text.startswith("/*", index):
                    depth += 1
                    index += 2
                elif text.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            continue
        if char in {"'", '"', "`"}:
            delimiter = char
            if char != "`" and text.startswith(char * 3, index):
                delimiter = char * 3
            index += len(delimiter)
            value: list[str] = []
            while index < length:
                if text.startswith(delimiter, index):
                    index += len(delimiter)
                    tokens.append(("string", "".join(value)))
                    break
                if char != "`" and text[index] == "\\" and index + 1 < length:
                    value.append(text[index + 1])
                    index += 2
                    continue
                value.append(text[index])
                index += 1
            continue
        if char.isalpha() or char in {"_", "$"}:
            end = index + 1
            while end < length and (
                text[end].isalnum() or text[end] in {"_", "$"}
            ):
                end += 1
            tokens.append(("identifier", text[index:end]))
            index = end
            continue
        tokens.append(("punctuation", char))
        index += 1
    return tokens


def _go_imported_modules(tokens: list[tuple[str, str]]) -> set[str]:
    modules: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] != ("identifier", "import"):
            index += 1
            continue
        cursor = index + 1
        if cursor < len(tokens) and tokens[cursor] == ("punctuation", "("):
            depth = 1
            cursor += 1
            while cursor < len(tokens) and depth:
                if tokens[cursor] == ("punctuation", "("):
                    depth += 1
                elif tokens[cursor] == ("punctuation", ")"):
                    depth -= 1
                elif depth == 1 and tokens[cursor][0] == "string":
                    modules.add(tokens[cursor][1])
                cursor += 1
            index = cursor
            continue
        while cursor < len(tokens) and cursor <= index + 3:
            if tokens[cursor][0] == "string":
                modules.add(tokens[cursor][1])
                break
            cursor += 1
        index = cursor + 1
    return modules


def _dart_directive_modules(
    tokens: list[tuple[str, str]],
    directives: frozenset[str],
) -> set[str]:
    """Return every URI branch from selected Dart directives."""
    modules: set[str] = set()
    index = 0
    while index < len(tokens):
        if not (
            tokens[index][0] == "identifier"
            and tokens[index][1] in directives
        ):
            index += 1
            continue
        directive = tokens[index][1]
        cursor = index + 1
        if (
            directive == "part"
            and cursor < len(tokens)
            and tokens[cursor] == ("identifier", "of")
        ):
            cursor += 1
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "string":
                modules.add(tokens[cursor][1])
            cursor += 1
        index = cursor + 1
    return modules


def _dart_named_directive_values(
    tokens: list[tuple[str, str]],
    first: str,
    second: str | None = None,
) -> set[str]:
    values: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] != ("identifier", first):
            index += 1
            continue
        cursor = index + 1
        if second is not None:
            if cursor >= len(tokens) or tokens[cursor] != ("identifier", second):
                index += 1
                continue
            cursor += 1
        if cursor < len(tokens) and tokens[cursor][0] == "string":
            index += 1
            continue
        parts: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "identifier":
                parts.append(tokens[cursor][1])
            elif tokens[cursor] == ("punctuation", "."):
                parts.append(".")
            cursor += 1
        value = "".join(parts)
        if value:
            values.add(value)
        index = cursor + 1
    return values


def _python_tree(text: str) -> ast.AST | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _lexical_code_text(path: Path, text: str) -> str:
    """Return executable tokens only; comments and string decoys disappear."""
    if path.suffix == ".py":
        try:
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)
            return " ".join(
                token.string
                for token in tokens
                if token.type
                not in {
                    tokenize.COMMENT,
                    tokenize.ENCODING,
                    tokenize.ENDMARKER,
                    tokenize.NL,
                    tokenize.NEWLINE,
                    tokenize.STRING,
                }
            )
        except (tokenize.TokenError, IndentationError):
            return ""
    return " ".join(
        value for kind, value in _c_style_tokens(text) if kind != "string"
    )


def _python_imported_modules(tree: ast.AST | None) -> set[str]:
    modules: set[str] = set()
    if tree is None:
        return modules
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            if base:
                modules.add(base)
            for alias in node.names:
                separator = "" if base.endswith(".") else "."
                modules.add(f"{base}{separator}{alias.name}")
    return modules


def imported_modules(path: Path, text: str) -> set[str]:
    """Lex/parse import edges without accepting comments or string decoys."""
    if path.suffix == ".go":
        return _go_imported_modules(_c_style_tokens(text))
    if path.suffix == ".py":
        return _python_imported_modules(_python_tree(text))
    if path.suffix in {".dart", ".ts"}:
        return _dart_directive_modules(
            _c_style_tokens(text), frozenset({"import"})
        )
    return set()


def authored_support_modules(path: Path, text: str) -> set[str]:
    """Edges that can pull first-party support into the current library."""
    if path.suffix == ".dart":
        return _dart_directive_modules(
            _c_style_tokens(text), frozenset({"import", "export", "part"})
        )
    return imported_modules(path, text)

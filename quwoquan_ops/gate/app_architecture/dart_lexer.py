"""最小 Dart 词法扫描：URI directive 解析与类型声明提取。"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import DART_URI_DIRECTIVE_KINDS


@dataclass(frozen=True)
class DartUriDirective:
    """剥除注释/普通字符串后得到的一条 authored Dart URI directive。"""

    kind: str
    uri: str


def _is_dart_identifier_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "$"}


def _skip_dart_interpolation_expression(source: str, index: int) -> int:
    """Skip a ``${...}`` body, including nested strings/comments/braces."""
    depth = 1
    length = len(source)
    while index < length:
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            comment_start = index
            comment_depth = 1
            index += 2
            while index < length and comment_depth:
                if source.startswith("/*", index):
                    comment_depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    comment_depth -= 1
                    index += 2
                else:
                    index += 1
            if comment_depth:
                raise ValueError(
                    f"unterminated Dart block comment at offset {comment_start}"
                )
            continue
        if source[index] in {"'", '"'}:
            index, _ = _read_dart_string(source, index)
            continue
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError("unterminated Dart string interpolation")


def _read_dart_string(source: str, start: int) -> tuple[int, str]:
    """Read one Dart string without letting interpolation strings desync the lexer."""
    quote = source[start]
    raw = (
        start > 0
        and source[start - 1] in {"r", "R"}
        and (start < 2 or not _is_dart_identifier_char(source[start - 2]))
    )
    delimiter = quote * (3 if source.startswith(quote * 3, start) else 1)
    index = start + len(delimiter)
    length = len(source)
    value: list[str] = []
    while index < length:
        if source.startswith(delimiter, index):
            return index + len(delimiter), "".join(value)
        if not raw and source[index] == "\\":
            if index + 1 >= length:
                break
            value.extend((source[index], source[index + 1]))
            index += 2
            continue
        if not raw and source[index] == "$":
            value.append("$")
            if index + 1 < length and source[index + 1] == "{":
                index = _skip_dart_interpolation_expression(source, index + 2)
                continue
            index += 1
            while index < length and _is_dart_identifier_char(source[index]):
                index += 1
            continue
        value.append(source[index])
        index += 1
    raise ValueError(f"unterminated Dart string at offset {start}")


def _dart_source_tokens(source: str) -> list[tuple[str, str]]:
    """以最小 Dart 词法扫描剥除注释并隔离字符串内容。

    只保留 directive 识别需要的 identifier/string/punctuation token。字符串内容
    作为单个 token 返回，因此其中伪造的 ``import``/``export``/``part`` 永远不会
    被当成代码；嵌套 block comment 与三引号字符串也在词法层处理。
    """
    tokens: list[tuple[str, str]] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if source.startswith("/*", index):
            start = index
            depth = 1
            index += 2
            while index < length and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError(f"unterminated Dart block comment at offset {start}")
            continue
        if char in {"'", '"'}:
            index, value = _read_dart_string(source, index)
            tokens.append(("string", value))
            continue
        if char.isalpha() or char in {"_", "$"}:
            end = index + 1
            while end < length and _is_dart_identifier_char(source[end]):
                end += 1
            tokens.append(("identifier", source[index:end]))
            index = end
            continue
        tokens.append(("punctuation", char))
        index += 1
    return tokens


def parse_dart_uri_directives(source: str) -> list[DartUriDirective]:
    """返回 import/export 的全部 conditional URI 与 authored ``part`` URI。

    ``part of`` 声明只标识当前 library owner，不是从本文件发出的依赖边，因此不
    返回。缺分号或缺 URI 的 malformed directive 直接失败，不降级为“无依赖”。
    """
    tokens = _dart_source_tokens(source)
    directives: list[DartUriDirective] = []
    index = 0
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    while index < len(tokens):
        token = tokens[index]
        if token[0] == "punctuation":
            if token[1] == "{":
                brace_depth += 1
            elif token[1] == "}":
                brace_depth = max(0, brace_depth - 1)
            elif token[1] == "(":
                paren_depth += 1
            elif token[1] == ")":
                paren_depth = max(0, paren_depth - 1)
            elif token[1] == "[":
                bracket_depth += 1
            elif token[1] == "]":
                bracket_depth = max(0, bracket_depth - 1)
        if brace_depth or paren_depth or bracket_depth:
            index += 1
            continue
        if token[0] != "identifier" or token[1] not in DART_URI_DIRECTIVE_KINDS:
            index += 1
            continue
        kind = token[1]
        cursor = index + 1
        if kind == "part" and cursor < len(tokens) and tokens[cursor] == (
            "identifier",
            "of",
        ):
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                cursor += 1
            if cursor >= len(tokens):
                raise ValueError("unterminated Dart part-of directive")
            index = cursor + 1
            continue
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor][0] != "string":
            # ``part`` 是 contextual keyword，允许作为普通 identifier（例如
            # closure parameter）。只有 statement boundary 上的 directive 形态才
            # 对缺 URI fail-closed。
            previous = tokens[index - 1] if index else None
            if previous is None or previous == ("punctuation", ";"):
                raise ValueError(f"Dart {kind} directive is missing a URI literal")
            index += 1
            continue
        directive_uris: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "string":
                directive_uris.append(tokens[cursor][1])
            cursor += 1
        if cursor >= len(tokens):
            raise ValueError(f"unterminated Dart {kind} directive")
        if kind == "part" and len(directive_uris) != 1:
            raise ValueError("Dart part directive must contain exactly one URI")
        directives.extend(DartUriDirective(kind, uri) for uri in directive_uris)
        index = cursor + 1
    return directives


def _dart_type_declarations(
    tokens: list[tuple[str, str]],
) -> list[tuple[str, str, str | None]]:
    """返回 ``(kind, name, extends)``，忽略注释与字符串里的伪声明。"""
    declarations: list[tuple[str, str, str | None]] = []
    for index, token in enumerate(tokens):
        if token[0] != "identifier" or token[1] not in {"class", "enum", "typedef"}:
            continue
        if index + 1 >= len(tokens) or tokens[index + 1][0] != "identifier":
            continue
        kind = token[1]
        name = tokens[index + 1][1]
        base: str | None = None
        cursor = index + 2
        while cursor < len(tokens):
            current = tokens[cursor]
            if current in {("punctuation", "{"), ("punctuation", ";")}:
                break
            if current == ("identifier", "extends"):
                if cursor + 1 < len(tokens) and tokens[cursor + 1][0] == "identifier":
                    base = tokens[cursor + 1][1]
                break
            cursor += 1
        declarations.append((kind, name, base))
    return declarations

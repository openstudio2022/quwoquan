"""Shared, fail-closed Flutter test-tag selection for gates and coverage."""

from __future__ import annotations

import re
from pathlib import Path


TEST_CALL_PATTERN = re.compile(r"\b(?:group|test|testWidgets)\s*\(")
TAGS_ANNOTATION_PATTERN = re.compile(r"@Tags\s*\(")
QUOTED_SERIAL_PATTERN = re.compile(r"[\"']serial[\"']")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
TYPE_PREFIX_PATTERN = re.compile(r"^<[^>]+>\s*")


def _skip_opaque(source: str, index: int) -> int:
    """Skip one Dart string/comment, returning ``index`` when none starts."""

    if source.startswith("//", index):
        newline = source.find("\n", index + 2)
        return len(source) if newline < 0 else newline + 1
    if source.startswith("/*", index):
        close = source.find("*/", index + 2)
        return len(source) if close < 0 else close + 2
    if source[index] not in {"'", '"'}:
        return index
    raw_prefix = (
        index > 0
        and source[index - 1] in {"r", "R"}
        and (
            index < 2
            or not (source[index - 2].isalnum() or source[index - 2] == "_")
        )
    )
    quote = source[index]
    delimiter = quote * 3 if source.startswith(quote * 3, index) else quote
    cursor = index + len(delimiter)
    while cursor < len(source):
        if source.startswith(delimiter, cursor):
            return cursor + len(delimiter)
        if source[cursor] == "\\" and not raw_prefix:
            cursor += 2
        else:
            cursor += 1
    return len(source)


def _matching_close(source: str, opening_index: int) -> int:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = [source[opening_index]]
    cursor = opening_index + 1
    while cursor < len(source):
        opaque_end = _skip_opaque(source, cursor)
        if opaque_end != cursor:
            cursor = opaque_end
            continue
        character = source[cursor]
        if character in pairs:
            stack.append(character)
        elif character in pairs.values():
            if not stack or pairs[stack[-1]] != character:
                raise RuntimeError("unbalanced Dart test tag expression")
            stack.pop()
            if not stack:
                return cursor
        cursor += 1
    raise RuntimeError("unterminated Dart test tag expression")


def _expression_end(source: str, start: int) -> int:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    cursor = start
    while cursor < len(source):
        opaque_end = _skip_opaque(source, cursor)
        if opaque_end != cursor:
            cursor = opaque_end
            continue
        character = source[cursor]
        if character in pairs:
            stack.append(character)
        elif character in pairs.values():
            if stack and pairs[stack[-1]] == character:
                stack.pop()
            elif not stack:
                return cursor
        elif character == "," and not stack:
            return cursor
        cursor += 1
    return cursor


def _top_level_tags_argument(call_body: str) -> str | None:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    cursor = 0
    while cursor < len(call_body):
        opaque_end = _skip_opaque(call_body, cursor)
        if opaque_end != cursor:
            cursor = opaque_end
            continue
        character = call_body[cursor]
        if character in pairs:
            stack.append(character)
            cursor += 1
            continue
        if character in pairs.values():
            if stack and pairs[stack[-1]] == character:
                stack.pop()
            cursor += 1
            continue
        if not stack and call_body.startswith("tags", cursor):
            before = call_body[cursor - 1] if cursor else ""
            after = call_body[cursor + 4] if cursor + 4 < len(call_body) else ""
            if (not before or not (before.isalnum() or before == "_")) and (
                not after or not (after.isalnum() or after == "_")
            ):
                colon = cursor + 4
                while colon < len(call_body) and call_body[colon].isspace():
                    colon += 1
                if colon < len(call_body) and call_body[colon] == ":":
                    value_start = colon + 1
                    while (
                        value_start < len(call_body)
                        and call_body[value_start].isspace()
                    ):
                        value_start += 1
                    value_end = _expression_end(call_body, value_start)
                    return call_body[value_start:value_end].strip()
        cursor += 1
    return None


def _test_tag_values(source: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _code_matches(source, TAGS_ANNOTATION_PATTERN):
        opening = match.end() - 1
        values.append(source[opening + 1 : _matching_close(source, opening)].strip())
    for match in _code_matches(source, TEST_CALL_PATTERN):
        opening = match.end() - 1
        call_body = source[opening + 1 : _matching_close(source, opening)]
        value = _top_level_tags_argument(call_body)
        if value is not None:
            values.append(value)
    return tuple(values)


def _code_matches(source: str, pattern: re.Pattern[str]):
    """Yield pattern matches only from Dart code, never comments/strings."""

    cursor = 0
    while cursor < len(source):
        opaque_end = _skip_opaque(source, cursor)
        if opaque_end != cursor:
            cursor = opaque_end
            continue
        match = pattern.match(source, cursor)
        if match is not None:
            yield match
            cursor = match.end()
            continue
        cursor += 1


def _is_literal_tag_value(value: str) -> bool:
    normalized = value.strip()
    if normalized.startswith("const "):
        normalized = normalized.removeprefix("const ").lstrip()
    normalized = TYPE_PREFIX_PATTERN.sub("", normalized, count=1)
    if normalized.startswith(("'", '"')):
        return True
    if not (normalized.startswith("[") and normalized.endswith("]")):
        return False
    if "..." in normalized:
        return False
    remainder = re.sub(r"[\"'][^\"']*[\"']", "", normalized[1:-1])
    return not remainder.replace(",", "").strip()


def declares_serial_tests(path: Path) -> bool:
    """Return serial membership or fail when a test tag value is not auditable."""

    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Flutter test selection requires a safe file: {path}")
    source = path.read_text(encoding="utf-8", errors="replace")
    values = _test_tag_values(source)
    for value in values:
        if IDENTIFIER_PATTERN.fullmatch(value):
            raise RuntimeError(
                "Flutter test tag alias is not auditable; use a literal value: "
                f"{value!r}: {path}"
            )
        if not _is_literal_tag_value(value):
            raise RuntimeError(
                f"Flutter test tags must use literal values: {value!r}: {path}"
            )
        if QUOTED_SERIAL_PATTERN.search(value) is not None:
            return True
    return False

"""Journey/support 边界门禁所需的最小 Dart 词法与 library/part 闭包解析。"""

from __future__ import annotations

from pathlib import Path

from .constants import _DART_URI_SCHEME_RE


def _dart_source_tokens(source: str) -> list[tuple[str, str]]:
    """Lex the Dart shapes needed by the Journey boundary gate.

    Comments are discarded and string literals are emitted as opaque tokens, so
    neither can impersonate an import, Widget/Provider call, or local typed double.
    This deliberately stays smaller than a Dart parser while preserving the exact
    import URI literals needed for physical path resolution.
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
            continue
        if char in {"'", '"'}:
            delimiter = char * (3 if source.startswith(char * 3, index) else 1)
            index += len(delimiter)
            value: list[str] = []
            terminated = False
            while index < length:
                if source.startswith(delimiter, index):
                    index += len(delimiter)
                    terminated = True
                    break
                if source[index] == "\\" and index + 1 < length:
                    value.append(source[index + 1])
                    index += 2
                    continue
                value.append(source[index])
                index += 1
            if terminated:
                tokens.append(("string", "".join(value)))
            continue
        if char.isalpha() or char in {"_", "$"}:
            end = index + 1
            while end < length and (
                source[end].isalnum() or source[end] in {"_", "$"}
            ):
                end += 1
            tokens.append(("identifier", source[index:end]))
            index = end
            continue
        tokens.append(("punctuation", char))
        index += 1
    return tokens


def _dart_directive_uris(
    tokens: list[tuple[str, str]],
    directive: str,
) -> list[str]:
    """Return every URI from a Dart directive, including conditional branches."""
    uris: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] != ("identifier", directive):
            index += 1
            continue
        cursor = index + 1
        if (
            directive == "part"
            and cursor < len(tokens)
            and tokens[cursor] == ("identifier", "of")
        ):
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                cursor += 1
            index = cursor + 1
            continue
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor][0] != "string":
            index += 1
            continue
        directive_uris: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "string":
                directive_uris.append(tokens[cursor][1])
            cursor += 1
        if cursor < len(tokens):
            uris.extend(directive_uris)
            index = cursor + 1
        else:
            index += 1
    return uris


def _dart_import_uris(tokens: list[tuple[str, str]]) -> list[str]:
    """Return URI literals from syntactic Dart import directives only."""
    return _dart_directive_uris(tokens, "import")


def _dart_export_uris(tokens: list[tuple[str, str]]) -> list[str]:
    """Return URI literals from syntactic Dart export directives only."""
    return _dart_directive_uris(tokens, "export")


def _dart_part_uris(tokens: list[tuple[str, str]]) -> list[str]:
    """Return URI literals from ``part '…'`` while excluding ``part of``."""
    return _dart_directive_uris(tokens, "part")


def _dart_part_of_targets(
    tokens: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return ``part of`` URI/library-name targets without textual decoys."""
    targets: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens) - 1:
        if not (
            tokens[index] == ("identifier", "part")
            and tokens[index + 1] == ("identifier", "of")
        ):
            index += 1
            continue
        cursor = index + 2
        if cursor < len(tokens) and tokens[cursor] in {
            ("identifier", "r"),
            ("identifier", "R"),
        }:
            cursor += 1
        if cursor < len(tokens) and tokens[cursor][0] == "string":
            targets.append(("uri", tokens[cursor][1]))
        else:
            name_parts: list[str] = []
            while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
                if tokens[cursor][0] == "identifier":
                    name_parts.append(tokens[cursor][1])
                elif tokens[cursor] == ("punctuation", "."):
                    name_parts.append(".")
                cursor += 1
            name = "".join(name_parts)
            if name:
                targets.append(("library", name))
        while index < len(tokens) and tokens[index] != ("punctuation", ";"):
            index += 1
        index += 1
    return targets


def _dart_library_names(tokens: list[tuple[str, str]]) -> set[str]:
    names: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] != ("identifier", "library"):
            index += 1
            continue
        cursor = index + 1
        name_parts: list[str] = []
        while cursor < len(tokens) and tokens[cursor] != ("punctuation", ";"):
            if tokens[cursor][0] == "identifier":
                name_parts.append(tokens[cursor][1])
            elif tokens[cursor] == ("punctuation", "."):
                name_parts.append(".")
            cursor += 1
        name = "".join(name_parts)
        if name:
            names.add(name)
        index = cursor + 1
    return names


def _dart_library_sources(path: Path) -> list[Path]:
    """Resolve a Dart library's source+parts, including a part-of entry path."""
    queue = [path.resolve()]
    sources: set[Path] = set()
    while queue:
        source = queue.pop()
        if source in sources or not source.is_file() or source.suffix != ".dart":
            continue
        sources.add(source)
        tokens = _dart_source_tokens(
            source.read_text(encoding="utf-8", errors="ignore")
        )
        for uri in _dart_part_uris(tokens):
            if uri and "$" not in uri and not _DART_URI_SCHEME_RE.match(uri):
                queue.append((source.parent / uri).resolve())
        for kind, value in _dart_part_of_targets(tokens):
            if kind == "uri":
                if value and "$" not in value and not _DART_URI_SCHEME_RE.match(value):
                    queue.append((source.parent / value).resolve())
                continue
            for candidate in sorted(source.parent.glob("*.dart")):
                candidate_tokens = _dart_source_tokens(
                    candidate.read_text(encoding="utf-8", errors="ignore")
                )
                if value not in _dart_library_names(candidate_tokens):
                    continue
                declared_parts = {
                    (candidate.parent / uri).resolve()
                    for uri in _dart_part_uris(candidate_tokens)
                    if uri and "$" not in uri and not _DART_URI_SCHEME_RE.match(uri)
                }
                if source in declared_parts:
                    queue.append(candidate.resolve())
    return sorted(sources)

"""App 侧生成错误 enum 成员流入 typed failure 的证据与生产 Python 字面量扫描。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .constants import CODE_PATTERN
from .literal_scan import _strip_comments
from .models import Emission, ScanResult, _read
from .resolution import _dart_files, _python_files


def _app_generated_error_symbols(root: Path) -> dict[str, dict[str, str]]:
    """Build generated-file -> (`ErrorEnum.member` -> stable code).

    App error generators currently emit either a const-enum constructor or a
    switch-backed `code` getter. Both are source-derived generated catalogs;
    only an import-bound use from non-generated production Dart can be emission
    evidence. Keeping the source file in the key prevents a same-named local
    object from borrowing a canonical enum's stable-code mapping.
    """
    generated_root = root / "quwoquan_app" / "lib" / "runtime" / "errors" / "generated"
    if not generated_root.is_dir():
        return {}
    symbols_by_file: dict[str, dict[str, str]] = {}
    for path in sorted(generated_root.rglob("*_errors.g.dart")):
        text = _read(path)
        enum_match = re.search(r"\benum\s+(?P<name>[A-Za-z_]\w*ErrorCode)\s*{", text)
        if enum_match is None:
            continue
        enum_name = enum_match.group("name")
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        symbols: dict[str, str] = {}
        ambiguous: set[str] = set()
        candidates: list[tuple[str, str]] = []
        candidates.extend(
            (match.group("member"), match.group("code"))
            for match in re.finditer(
                r"^\s*(?P<member>[a-zA-Z_]\w*)\(\s*'(?P<code>"
                r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*)'",
                text,
                re.M,
            )
        )
        candidates.extend(
            (match.group("member"), match.group("code"))
            for match in re.finditer(
                rf"\bcase\s+{re.escape(enum_name)}\.(?P<member>[a-zA-Z_]\w*)\s*:"
                r"\s*return\s+'(?P<code>"
                r"[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[a-z][a-z0-9_]*)'",
                text,
            )
        )
        for member, code in candidates:
            symbol = f"{enum_name}.{member}"
            existing = symbols.get(symbol)
            if existing is not None and existing != code:
                ambiguous.add(symbol)
                continue
            symbols[symbol] = code
        for symbol in ambiguous:
            symbols.pop(symbol, None)
        if symbols:
            symbols_by_file[relative] = symbols
    return symbols_by_file


_DART_IMPORT_DIRECTIVE = re.compile(
    r"^import\s+['\"](?P<uri>[^'\"]+)['\"]"
    r"(?:\s+deferred)?(?:\s+as\s+(?P<alias>[A-Za-z_]\w*))?"
    r"(?:\s+(?:show|hide)\s+[^;]+)?\s*;$"
)


def _dart_import_directives(text: str) -> list[tuple[str, str]]:
    """Parse only the leading Dart directive section.

    Imports embedded in comments or later string literals cannot enter this
    section. Multiline/show directives are deliberately skipped rather than
    guessed; canonical generated error imports are single-line directives.
    """
    directives: list[tuple[str, str]] = []
    for raw_line in _strip_comments(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _DART_IMPORT_DIRECTIVE.fullmatch(line)
        if match is not None:
            directives.append((match.group("uri"), match.group("alias") or ""))
            continue
        if line.startswith(("library ", "export ", "part ")):
            continue
        break
    return directives


def _dart_library_source(app_lib: Path, path: Path, text: str) -> Path | None:
    """Resolve a part file to the library that owns its imports."""
    part_of = re.search(
        r"^\s*part\s+of\s+['\"](?P<uri>[^'\"]+)['\"]\s*;",
        _strip_comments(text),
        re.M,
    )
    if part_of is None:
        return path
    uri = part_of.group("uri")
    if uri.startswith("package:quwoquan_app/"):
        candidate = app_lib / uri.removeprefix("package:quwoquan_app/")
    elif ":" not in uri:
        candidate = path.parent / uri
    else:
        return None
    candidate = candidate.resolve()
    try:
        candidate.relative_to(app_lib.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _resolve_dart_import(app_lib: Path, library: Path, uri: str) -> Path | None:
    if uri.startswith("package:quwoquan_app/"):
        candidate = app_lib / uri.removeprefix("package:quwoquan_app/")
    elif ":" not in uri:
        candidate = library.parent / uri
    else:
        return None
    candidate = candidate.resolve()
    try:
        candidate.relative_to(app_lib.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _mask_dart_string_literals(text: str) -> str:
    """Mask Dart string contents while preserving offsets and newlines."""
    output = list(text)
    index = 0
    while index < len(text):
        raw_prefix = text[index] in {"r", "R"} and index + 1 < len(text)
        quote_index = index + 1 if raw_prefix else index
        if text[quote_index] not in {"'", '"'}:
            index += 1
            continue
        quote = text[quote_index]
        triple = text.startswith(quote * 3, quote_index)
        delimiter = quote * (3 if triple else 1)
        start = index
        cursor = quote_index + len(delimiter)
        while cursor < len(text):
            if not raw_prefix and text[cursor] == "\\":
                cursor += 2
                continue
            if text.startswith(delimiter, cursor):
                cursor += len(delimiter)
                break
            cursor += 1
        for position in range(start, min(cursor, len(output))):
            if output[position] != "\n":
                output[position] = " "
        index = max(cursor, index + 1)
    return "".join(output)


def _dart_generated_code_flows_to_error_field(
    code_text: str,
    expression: str,
) -> bool:
    """Prove a generated `.code` value flows through a local typed variable."""
    value_pattern = re.compile(rf"\b{re.escape(expression)}\.code\b")
    assignment_pattern = re.compile(
        r"\b(?:final|var|const)\s+"
        r"(?:[A-Za-z_]\w*(?:<[^;=]+>)?\??\s+)?"
        r"(?P<name>[A-Za-z_]\w*)\s*=\s*[^;]*$",
        re.S,
    )
    for value in value_pattern.finditer(code_text):
        prefix = code_text[max(0, value.start() - 4000) : value.start()]
        assignment = assignment_pattern.search(prefix)
        if assignment is None:
            continue
        variable = assignment.group("name")
        if re.search(
            rf"\b(?:failureCode|errorCode|code)\s*:\s*{re.escape(variable)}\b",
            code_text[value.end() :],
        ):
            return True
    return False


def _scan_app_generated_error_emissions(root: Path, result: ScanResult) -> None:
    symbols_by_file = _app_generated_error_symbols(root)
    if not symbols_by_file:
        return
    app_lib = root / "quwoquan_app" / "lib"
    for path in _dart_files(root):
        raw_text = _read(path)
        text = _strip_comments(raw_text)
        library = _dart_library_source(app_lib, path, raw_text)
        if library is None:
            continue
        imported_symbols: list[tuple[str, dict[str, str]]] = []
        for uri, alias in _dart_import_directives(_read(library)):
            imported = _resolve_dart_import(app_lib, library, uri)
            if imported is None:
                continue
            relative_import = imported.relative_to(root.resolve()).as_posix()
            symbols = symbols_by_file.get(relative_import)
            if symbols:
                imported_symbols.append(((alias + ".") if alias else "", symbols))
        if not imported_symbols:
            continue
        code_text = _mask_dart_string_literals(text)
        has_structured_failure = bool(
            re.search(r"\b(?:RuntimeFailure(?:Base)?|CloudException)\s*\(", code_text)
        )
        relative = path.relative_to(root).as_posix()
        for qualifier, symbols in imported_symbols:
            for symbol, code in sorted(symbols.items()):
                expression = re.escape(qualifier + symbol)
                is_typed_failure_field = bool(
                    re.search(
                        rf"\b(?:failureCode|errorCode|code)\s*:\s*{expression}\.code\b",
                        code_text,
                    )
                )
                is_typed_failure_flow = _dart_generated_code_flows_to_error_field(
                    code_text,
                    qualifier + symbol,
                )
                is_structured_failure_use = has_structured_failure and bool(
                    re.search(rf"\b{expression}\b", code_text)
                )
                if (
                    is_typed_failure_field
                    or is_typed_failure_flow
                    or is_structured_failure_use
                ):
                    result.emissions.append(
                        Emission(
                            code=code,
                            form="app_generated_error_symbol",
                            path=relative,
                            function="<dart-generated-symbol>",
                        )
                    )


def _scan_python_stable_code_literals(root: Path, result: ScanResult) -> None:
    """Scan only AST-backed production error-code assignments/response maps."""
    code_name = re.compile(r"(?:^|_)(?:ERROR_)?CODE$", re.I)
    response_keys = {"code", "errorCode", "failureCode"}
    for path in _python_files(root):
        try:
            tree = ast.parse(_read(path), filename=path.as_posix())
        except SyntaxError:
            continue
        relative = path.relative_to(root).as_posix()
        codes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    continue
                if not CODE_PATTERN.fullmatch(value.value):
                    continue
                if any(
                    isinstance(target, ast.Name) and code_name.search(target.id)
                    for target in targets
                ):
                    codes.add(value.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in response_keys
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and CODE_PATTERN.fullmatch(value.value)
                    ):
                        codes.add(value.value)
        for code in sorted(codes):
            result.emissions.append(
                Emission(
                    code=code,
                    form="python_stable_code_literal",
                    path=relative,
                    function="<python-ast>",
                )
            )

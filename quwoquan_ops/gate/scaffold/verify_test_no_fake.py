#!/usr/bin/env python3
"""Verify canonical test roots do not contain fake or placeholder evidence.

Imports and substitute constructors are inspected as lexical/AST structure.  A
comment or string cannot impersonate code, while same-file doubles and
first-party ``tests/support`` imports remain visible even without a third-party
mock dependency.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import sys
import tokenize
from functools import lru_cache
from pathlib import Path

import yaml

from test_directory_layout_lib import (
    ROOT,
    contains_generated_bridge_marker,
    iter_canonical_files,
)


PLACEHOLDER_PATTERNS = (
    re.compile(r"\bassert\s*\(\s*true\s*\)"),
    re.compile(r"\bexpect\s*\(\s*true\s*,\s*isTrue\s*\)"),
    re.compile(r"\bTODO_FAKE_TEST\b"),
)
SKIP_PATTERNS = (
    re.compile(r"\bpytest\s*\.\s*skip\s*\("),
    re.compile(r"@\s*pytest\s*\.\s*mark\s*\.\s*skip\b"),
    re.compile(r"@\s*unittest\s*\.\s*skip\b"),
    re.compile(r"\b(?:t|b)\s*\.\s*Skip(?:f)?\s*\("),
    re.compile(r"\bskip\s*:\s*true\b"),
    re.compile(r"\bos\s*\.\s*Exit\s*\(\s*0\s*\)"),
)
#: 进程内替身库：这些包的存在意义就是把真实依赖换成替身，判定对象是包名本身。
#: 刻意不含 `net/http/httptest`——api_integration 用 `httptest.NewRecorder/NewRequest`
#: 驱动**真实** handler（今日 142 个文件），它不是替身而是传输壳，列进来等于制造 142 个误报。
SUBSTITUTE_LIBRARY_IMPORTS = (
    "github.com/golang/mock",
    "go.uber.org/mock",
    "github.com/stretchr/testify/mock",
    "github.com/alicebob/miniredis",
    "github.com/DATA-DOG/go-sqlmock",
    "unittest.mock",
    "mock",
    "requests_mock",
    "responses",
    "package:mocktail",
    "package:mockito",
    "package:http/testing.dart",
    "package:quwoquan_cloud_mock",
)
#: 构建约束是编译器可见的结构事实。
FAKE_BUILD_TAG_RE = re.compile(
    r"(?m)^//\s*(?:go:build|\+build)\b.*\b(?:fake|mock|stub)\b"
)
_SUBSTITUTE_INFRA_SUFFIX = (
    r"(?:Store|Repository|Client|Writer|Reader|Executor|Transport|Gateway|"
    r"Clock|Queue|Cache|Database|Backend|Service)"
)
SUBSTITUTE_CALL_NAME_RE = re.compile(
    rf"^(?:(?:New|new)(?:InMemory|Memory)[A-Za-z0-9_]*|"
    rf"(?:InMemory|Memory)[A-Za-z0-9_]*{_SUBSTITUTE_INFRA_SUFFIX}|"
    r"(?:Noop|Mock|Stub|Fake)[A-Za-z0-9_]*)$"
)
SUBSTITUTE_COMPOSITE_NAME_RE = re.compile(
    rf"^(?:(?:InMemory|Memory)[A-Za-z0-9_]*{_SUBSTITUTE_INFRA_SUFFIX}|"
    r"(?:Noop|Mock|Stub|Fake|Recording)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]*(?:Mock|Stub|Fake|Double))$"
)
ENVIRONMENT_CLASS_NAME_RE = re.compile(
    r"^_?(?:Alpha|Beta|Gamma|Prod(?!uct(?:ion)?))[A-Za-z0-9_]*$"
)
ENVIRONMENT_DATA_NAME_RE = re.compile(
    r"(?<![a-z0-9_])(?:alpha|beta|gamma|prod)_[a-z0-9_]+",
    re.IGNORECASE,
)
ENVIRONMENT_PATH_SEGMENT_RE = re.compile(
    r"(?:^|[_-])(?:alpha|beta|gamma|prod)(?:[_-]|$)",
    re.IGNORECASE,
)
FIRST_PARTY_DOUBLE_PATH_RE = re.compile(
    r"(?:^|[_-])(?:fake|mock|stub|noop|memory|typed[_-]?double|test[_-]?double|recording)(?:[_\-.]|$)",
    re.IGNORECASE,
)
FIRST_PARTY_DOUBLE_TYPE_RE = re.compile(
    rf"^_?(?:(?:InMemory|Memory)[A-Za-z0-9_]*{_SUBSTITUTE_INFRA_SUFFIX}|"
    r"(?:Fake|Mock|Stub|Noop|Recording)[A-Za-z0-9_]*|"
    r"[A-Za-z0-9_]*(?:Fake|Mock|Stub|Double))$"
)
DART_TEST_RE = re.compile(r"\b(?:test(?:Widgets)?|patrolTest)\s*\(")
PYTHON_TEST_RE = re.compile(r"\bdef\s+test_[A-Za-z0-9_]+\s*\(")
GO_TEST_ENTRYPOINT_RE = re.compile(
    r"\bfunc\s+(?:Test[A-Za-z0-9_]+|Benchmark[A-Za-z0-9_]+|TestMain)\s*\("
)


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


def substitute_library_imports(path: Path, text: str) -> list[str]:
    """import 了哪些进程内替身库。名字长什么样与判定无关。"""
    found: list[str] = []
    for module in sorted(imported_modules(path, text)):
        for library in SUBSTITUTE_LIBRARY_IMPORTS:
            if module == library or module.startswith(f"{library}/"):
                found.append(module)
                break
            if path.suffix == ".py" and (
                module == library or module.startswith(f"{library}.")
            ):
                found.append(module)
                break
    return found


def _is_test_support_path(path: Path) -> bool:
    parts = path.parts
    return any(
        parts[index : index + 2] in {("test", "support"), ("tests", "support")}
        for index in range(len(parts) - 1)
    )


def first_party_support_imports(path: Path, text: str) -> list[str]:
    """Return imported first-party support edges, including relative Dart URIs."""
    found: set[str] = set()
    for module in authored_support_modules(path, text):
        normalized = module.replace(".", "/")
        if "/tests/support/" in f"/{normalized}/" or "/test/support/" in f"/{normalized}/":
            found.add(module)
            continue
        if path.suffix in {".dart", ".ts"} and not re.match(
            r"^[A-Za-z][A-Za-z0-9+.-]*:", module
        ):
            target = (path.parent / module).resolve()
            if _is_test_support_path(target):
                found.add(module)
        if path.suffix == ".py":
            stripped = module.lstrip(".")
            segments = stripped.split(".") if stripped else []
            if (
                len(segments) >= 2
                and segments[:2] in (["test", "support"], ["tests", "support"])
            ) or (
                module.startswith(".")
                and segments
                and segments[0] == "support"
                and any(parent.name in {"test", "tests"} for parent in path.parents)
            ):
                found.add(module)
    return sorted(
        module
        for module in found
        if not any(
            module != other and module.startswith(f"{other}.")
            for other in found
        )
    )


def _snapshot_path_exists(
    path: Path,
    snapshot_files: frozenset[Path] | None,
) -> bool:
    if snapshot_files is None:
        return path.exists()
    resolved = path.resolve()
    return resolved in snapshot_files or resolved in _snapshot_directories(
        snapshot_files
    )


@lru_cache(maxsize=4)
def _snapshot_directories(snapshot_files: frozenset[Path]) -> frozenset[Path]:
    """Index snapshot directories once instead of rescanning every file per edge."""
    return frozenset(
        parent
        for path in snapshot_files
        for parent in path.parents
    )


@lru_cache(maxsize=4)
def _snapshot_files_by_parent(
    snapshot_files: frozenset[Path],
) -> dict[Path, tuple[Path, ...]]:
    """Index the immutable snapshot by direct parent for package/library lookup."""
    grouped: dict[Path, list[Path]] = {}
    for path in snapshot_files:
        grouped.setdefault(path.parent, []).append(path)
    return {
        parent: tuple(sorted(paths))
        for parent, paths in grouped.items()
    }


def _first_party_support_targets(
    path: Path,
    module: str,
    snapshot_files: frozenset[Path] | None = None,
) -> list[Path]:
    targets: list[Path] = []
    if path.suffix in {".dart", ".ts"} and not re.match(
        r"^[A-Za-z][A-Za-z0-9+.-]*:", module
    ):
        candidate = (path.parent / module).resolve()
        if _is_test_support_path(candidate):
            targets.append(candidate)
    elif path.suffix == ".go" and module.startswith("quwoquan_service/"):
        candidate = (ROOT / module).resolve()
        if _is_test_support_path(candidate):
            targets.append(candidate)
    elif path.suffix == ".py":
        level = len(module) - len(module.lstrip("."))
        segments = module.lstrip(".").split(".")
        base: Path | None = None
        if level:
            base = path.parent
            for _ in range(level - 1):
                base = base.parent
        elif len(segments) >= 2 and segments[:2] in (
            ["test", "support"],
            ["tests", "support"],
        ):
            test_root = next(
                (parent for parent in path.parents if parent.name == segments[0]),
                None,
            )
            if test_root is not None:
                base = test_root
                segments = segments[1:]
        if base is not None:
            for length in range(len(segments), 0, -1):
                candidate = base.joinpath(*segments[:length])
                candidates = (candidate.with_suffix(".py"), candidate / "__init__.py")
                existing = [
                    target
                    for target in candidates
                    if _snapshot_path_exists(target, snapshot_files)
                ]
                if existing:
                    targets.extend(existing)
                    break
    return sorted(
        set(
            target.resolve()
            for target in targets
            if _snapshot_path_exists(target, snapshot_files)
        )
    )


def _support_source_files(
    target: Path,
    snapshot_files: frozenset[Path] | None = None,
) -> list[Path]:
    """Return one imported package/library only, never recursive subpackages."""
    source_suffixes = {".go", ".py", ".dart", ".ts"}
    resolved = target.resolve()
    if snapshot_files is not None:
        if resolved in snapshot_files:
            return [resolved] if resolved.suffix in source_suffixes else []
        return [
            path
            for path in _snapshot_files_by_parent(snapshot_files).get(
                resolved, ()
            )
            if path.suffix in source_suffixes
        ]
    if target.is_file():
        return [resolved] if target.suffix in source_suffixes else []
    if not target.is_dir():
        return []
    return sorted(
        path.resolve()
        for path in target.iterdir()
        if path.is_file() and path.suffix in source_suffixes
    )


def _declared_double_types(path: Path, text: str) -> list[str]:
    names: set[str] = set()
    if path.suffix == ".py":
        tree = _python_tree(text)
        if tree is not None:
            names.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and FIRST_PARTY_DOUBLE_TYPE_RE.fullmatch(node.name)
            )
        return sorted(names)
    tokens = _c_style_tokens(text)
    declaration_keywords = {"class", "type"}
    for index, token in enumerate(tokens[:-1]):
        if token == ("identifier", "class") or (
            token[0] == "identifier" and token[1] in declaration_keywords
        ):
            candidate = tokens[index + 1]
            if candidate[0] == "identifier" and FIRST_PARTY_DOUBLE_TYPE_RE.fullmatch(candidate[1]):
                names.add(candidate[1])
    return sorted(names)


def _support_target_contains_substitute(
    target: Path,
    cache: dict[Path, bool],
    visiting: set[Path],
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> bool:
    key = target.resolve()
    if key in cache:
        return cache[key]
    if key in visiting:
        return False
    visiting.add(key)
    contains = False
    source_payloads: dict[Path, str] = {}
    for source in _support_source_files(target, snapshot_files):
        if source_texts is not None:
            source_text = source_texts.get(source, "")
        else:
            source_text = source.read_text(encoding="utf-8", errors="ignore")
        if source.suffix == ".dart":
            source_payloads.update(
                _dart_library_source_texts(
                    source,
                    source_text,
                    source_texts,
                    snapshot_files,
                )
            )
        else:
            source_payloads[source] = source_text
    for source, source_text in sorted(source_payloads.items()):
        if (
            FIRST_PARTY_DOUBLE_PATH_RE.search(source.name)
            or lexical_substitute_names(source, source_text)
            or substitute_library_imports(source, source_text)
        ):
            contains = True
            break
        for module in first_party_support_imports(source, source_text):
            if any(
                _support_target_contains_substitute(
                    nested,
                    cache,
                    visiting,
                    source_texts,
                    snapshot_files,
                )
                for nested in _first_party_support_targets(
                    source, module, snapshot_files
                )
            ):
                contains = True
                break
        if contains:
            break
    visiting.remove(key)
    cache[key] = contains
    return contains


def first_party_substitute_support_imports(
    path: Path,
    text: str,
    cache: dict[Path, bool] | None = None,
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> list[str]:
    """Follow first-party support edges and report only support carrying a double."""
    classification_cache = cache if cache is not None else {}
    findings: set[str] = set()
    for module in first_party_support_imports(path, text):
        if any(
            _support_target_contains_substitute(
                target,
                classification_cache,
                set(),
                source_texts,
                snapshot_files,
            )
            for target in _first_party_support_targets(
                path, module, snapshot_files
            )
        ):
            findings.add(module)
    return sorted(findings)


def lexical_substitute_names(path: Path, text: str) -> list[str]:
    """Return lexically real substitute declarations and constructor uses."""
    names: set[str] = set()
    if path.suffix == ".py":
        tree = _python_tree(text)
        if tree is None:
            return []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue
            if SUBSTITUTE_CALL_NAME_RE.fullmatch(name):
                names.add(name)
        names.update(_declared_double_types(path, text))
        return sorted(names)
    tokens = _c_style_tokens(text)
    for index, token in enumerate(tokens[:-1]):
        if token[0] != "identifier":
            continue
        next_token = tokens[index + 1]
        if (
            next_token == ("punctuation", "(")
            and SUBSTITUTE_CALL_NAME_RE.fullmatch(token[1])
        ) or (
            next_token == ("punctuation", "{")
            and SUBSTITUTE_COMPOSITE_NAME_RE.fullmatch(token[1])
        ):
            names.add(token[1])
    names.update(_declared_double_types(path, text))
    return sorted(names)


def lexical_memory_modes(path: Path, text: str) -> list[str]:
    """Return real ``mode: memory`` assignments while ignoring comments/decoys."""
    if path.suffix == ".py":
        tree = _python_tree(text)
        if tree is None:
            return []
        hits: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg and node.arg.lower() == "mode":
                if isinstance(node.value, ast.Constant) and str(node.value.value).lower() == "memory":
                    hits.add("mode=memory")
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and str(key.value).lower() == "mode"
                        and isinstance(value, ast.Constant)
                        and str(value.value).lower() == "memory"
                    ):
                        hits.add("mode:memory")
        return sorted(hits)
    tokens = _c_style_tokens(text)
    hits: set[str] = set()
    for index in range(len(tokens) - 2):
        key, separator, value = tokens[index : index + 3]
        if (
            key[0] == "identifier"
            and key[1].lower() == "mode"
            and separator in {("punctuation", ":"), ("punctuation", "=")}
            and value[0] in {"identifier", "string"}
            and value[1].lower() == "memory"
        ):
            hits.add("mode:memory")
    return sorted(hits)


def is_app_user_acceptance_source(path: Path) -> bool:
    return (
        path.suffix == ".dart"
        and "quwoquan_app" in path.parts
        and "user_acceptance" in path.parts
    )


def is_app_local_fixture_source(path: Path) -> bool:
    parts = path.parts
    for index in range(len(parts) - 2):
        if parts[index : index + 3] == ("quwoquan_app", "test", "support"):
            return True
        if parts[index : index + 3] == (
            "quwoquan_app",
            "test",
            "local_contract",
        ):
            return True
    return False


def _source_string_literals(path: Path, text: str) -> list[str]:
    if path.suffix == ".py":
        values: list[str] = []
        try:
            stream = io.StringIO(text).readline
            for token in tokenize.generate_tokens(stream):
                if token.type != tokenize.STRING:
                    continue
                try:
                    value = ast.literal_eval(token.string)
                except (SyntaxError, ValueError):
                    continue
                if isinstance(value, str):
                    values.append(value)
        except (tokenize.TokenError, IndentationError):
            return values
        return values
    return [value for kind, value in _c_style_tokens(text) if kind == "string"]


def _structured_scalar_strings(path: Path, text: str) -> list[str]:
    try:
        if path.suffix == ".json":
            documents = [json.loads(text)]
        else:
            documents = list(yaml.safe_load_all(text))
    except (json.JSONDecodeError, yaml.YAMLError):
        return []
    values: list[str] = []
    pending = list(documents)
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set)):
            pending.extend(value)
        elif isinstance(value, str):
            values.append(value)
    return values


def _environment_class_names(path: Path, text: str) -> list[str]:
    names: set[str] = set()
    if path.suffix == ".py":
        tree = _python_tree(text)
        if tree is not None:
            names.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and ENVIRONMENT_CLASS_NAME_RE.fullmatch(node.name)
            )
        return sorted(names)
    tokens = _c_style_tokens(text)
    for index, token in enumerate(tokens[:-1]):
        if token == ("identifier", "class"):
            candidate = tokens[index + 1]
            if candidate[0] == "identifier" and ENVIRONMENT_CLASS_NAME_RE.fullmatch(candidate[1]):
                names.add(candidate[1])
    return sorted(names)


def app_local_fixture_environment_names(
    path: Path,
    text: str,
) -> tuple[list[str], list[str]]:
    """Return environment-shaped class/data names in ordinary local fixtures."""
    if not is_app_local_fixture_source(path):
        return [], []
    class_names = _environment_class_names(path, text)
    values = _source_string_literals(path, text)
    data_names = {
        match.group(0)
        for value in values
        for match in ENVIRONMENT_DATA_NAME_RE.finditer(value)
    }
    return class_names, sorted(data_names)


def app_local_fixture_environment_path_names(path: Path) -> list[str]:
    if not is_app_local_fixture_source(path):
        return []
    return sorted(
        segment
        for segment in path.parts
        if ENVIRONMENT_PATH_SEGMENT_RE.search(segment)
    )


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        if message not in self.items:
            self.items.append(message)

    def exit_code(self) -> int:
        if not self.items:
            print("[verify] OK: no fake canonical tests detected")
            return 0
        for item in self.items:
            print(f"[verify] FAIL: {item}", file=sys.stderr)
        return 1


EXCLUDED_SCAN_DIRS = frozenset(
    {
        ".git",
        ".dart_tool",
        ".qwq_output",
        ".qwq_sandbox",
        ".qwq_test_venv",
        ".worktrees",
        ".venv",
        "build",
        "node_modules",
        "site-packages",
        "vendor",
    }
)
SNAPSHOT_TEXT_SUFFIXES = frozenset(
    {".dart", ".go", ".json", ".py", ".ts", ".txt", ".yaml", ".yml"}
)


def _snapshot_needs_text(path: Path) -> bool:
    return path.suffix in SNAPSHOT_TEXT_SUFFIXES and any(
        part in {"test", "tests"} for part in path.parts
    )


def scan_repository_snapshot() -> tuple[list[Path], dict[Path, str]]:
    """Capture one deterministic path+source snapshot for the whole gate run."""
    files: list[Path] = []
    source_texts: dict[Path, str] = {}
    for current_root, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(
            name for name in dirnames if name not in EXCLUDED_SCAN_DIRS
        )
        current = Path(current_root)
        for name in sorted(filenames):
            path = current / name
            files.append(path)
            if _snapshot_needs_text(path):
                text = path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                source_texts[path] = text
                source_texts[path.resolve()] = text
    return sorted(files), source_texts


def scan_repository_files() -> list[Path]:
    """Compatibility wrapper for callers that need only stable paths."""
    return scan_repository_snapshot()[0]


def _read_text(path: Path, cache: dict[Path, str]) -> str:
    if path not in cache:
        cache[path] = path.read_text(encoding="utf-8", errors="ignore")
    return cache[path]


def _dart_library_source_texts(
    path: Path,
    root_text: str,
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> list[tuple[Path, str]]:
    """Return source+part/part-of files from one captured Dart snapshot."""
    root = path.resolve()
    queue: list[tuple[Path, str | None]] = [(root, root_text)]
    sources: dict[Path, str] = {}
    while queue:
        source, supplied_text = queue.pop()
        if source in sources:
            continue
        if supplied_text is not None:
            text = supplied_text
        elif source_texts is not None:
            if source not in source_texts:
                continue
            text = source_texts[source]
        elif source.is_file():
            text = source.read_text(encoding="utf-8", errors="ignore")
        else:
            continue
        sources[source] = text
        tokens = _c_style_tokens(text)
        for module in _dart_directive_modules(
            tokens, frozenset({"part"})
        ):
            if not module or "$" in module or re.match(
                r"^[A-Za-z][A-Za-z0-9+.-]*:", module
            ):
                continue
            candidate = (source.parent / module).resolve()
            if _snapshot_path_exists(candidate, snapshot_files):
                queue.append((candidate, None))
        for library_name in _dart_named_directive_values(
            tokens, "part", "of"
        ):
            if snapshot_files is not None:
                candidates = [
                    candidate
                    for candidate in _snapshot_files_by_parent(
                        snapshot_files
                    ).get(source.parent, ())
                    if candidate.suffix == ".dart"
                ]
            else:
                candidates = sorted(source.parent.glob("*.dart"))
            for candidate in candidates:
                candidate = candidate.resolve()
                if candidate == source:
                    continue
                if source_texts is not None:
                    candidate_text = source_texts.get(candidate)
                    if candidate_text is None:
                        continue
                else:
                    candidate_text = candidate.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                candidate_tokens = _c_style_tokens(candidate_text)
                if library_name not in _dart_named_directive_values(
                    candidate_tokens, "library"
                ):
                    continue
                declared_parts = {
                    (candidate.parent / module).resolve()
                    for module in _dart_directive_modules(
                        candidate_tokens, frozenset({"part"})
                    )
                    if module
                    and "$" not in module
                    and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", module)
                }
                if source in declared_parts:
                    queue.append((candidate, candidate_text))
    return sorted(sources.items(), key=lambda item: item[0].as_posix())


def verify_canonical_files(
    failures: Failures,
    canonical_files: list[tuple[str, Path, str]] | None = None,
    text_cache: dict[Path, str] | None = None,
) -> None:
    cache = text_cache if text_cache is not None else {}
    inventory = (
        canonical_files
        if canonical_files is not None
        else iter_canonical_files()
    )
    for _, path, _ in inventory:
        text = _read_text(path, cache)
        code_text = _lexical_code_text(path, text)
        if contains_generated_bridge_marker(path, text):
            failures.add(f"{path.relative_to(ROOT)} contains generated bridge marker")
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(code_text):
                failures.add(f"{path.relative_to(ROOT)} contains placeholder pattern {pattern.pattern!r}")
        for pattern in SKIP_PATTERNS:
            if pattern.search(code_text):
                failures.add(f"{path.relative_to(ROOT)} contains skip pattern {pattern.pattern!r}")
        if (
            path.suffix == ".go"
            and "_support__" not in path.name
            and not GO_TEST_ENTRYPOINT_RE.search(code_text)
        ):
            failures.add(f"{path.relative_to(ROOT)} go canonical test lacks Test*/Benchmark*/TestMain entrypoint")
        if (
            path.suffix == ".py"
            and "importlib . util . spec_from_file_location" not in code_text
            and not PYTHON_TEST_RE.search(code_text)
        ):
            failures.add(f"{path.relative_to(ROOT)} python canonical test lacks real test body")
        if path.suffix == ".dart" and not DART_TEST_RE.search(code_text):
            failures.add(f"{path.relative_to(ROOT)} dart canonical test lacks test/testWidgets/patrolTest body")


def verify_test_artifacts(failures: Failures) -> None:
    test_artifacts = ROOT / ".qwq_output" / "env" / "repo" / "runs" / "tests"
    if not test_artifacts.exists():
        return
    for path in sorted(test_artifacts.rglob("report.json")):
        # Disposable pytest isolation roots are deleted after the suite; ignore
        # any leftover incomplete reports instead of treating them as evidence.
        if any(part.startswith("data-local-contract.") for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '"exit_code"' not in text or '"case_results"' not in text:
            failures.add(f"{path.relative_to(ROOT)} report.json missing exit_code or case_results")


def _environment_data_names_for_file(path: Path, text: str) -> list[str]:
    if path.suffix in {".json", ".yaml", ".yml"}:
        values = _structured_scalar_strings(path, text)
    elif path.suffix in {".dart", ".py", ".go", ".ts", ".txt"}:
        values = _source_string_literals(path, text)
    else:
        return []
    return sorted(
        {
            match.group(0)
            for value in values
            for match in ENVIRONMENT_DATA_NAME_RE.finditer(value)
        }
    )


def verify_app_local_fixture_naming(
    failures: Failures,
    all_files: list[Path] | None = None,
    text_cache: dict[Path, str] | None = None,
) -> None:
    """Environment names in local doubles/fixtures cannot impersonate evidence."""
    cache = text_cache if text_cache is not None else {}
    paths = all_files if all_files is not None else scan_repository_files()
    for path in paths:
        if not is_app_local_fixture_source(path):
            continue
        if all_files is None and not path.is_file():
            continue
        path_names = app_local_fixture_environment_path_names(path)
        if path_names:
            failures.add(
                f"{path.relative_to(ROOT)} uses deployment-environment path names "
                f"{path_names} for an ordinary fixture/double/golden"
            )
        if path.suffix not in {".dart", ".py", ".go", ".ts", ".json", ".yaml", ".yml", ".txt"}:
            continue
        text = _read_text(path, cache)
        class_names = (
            _environment_class_names(path, text)
            if path.suffix in {".dart", ".py"}
            else []
        )
        data_names = _environment_data_names_for_file(path, text)
        if class_names:
            failures.add(
                f"{path.relative_to(ROOT)} uses deployment-environment class names "
                f"{class_names} for an ordinary fixture/typed double"
            )
        if data_names:
            failures.add(
                f"{path.relative_to(ROOT)} uses deployment-environment fixture data "
                f"names {data_names}; use object/behavior fixture identities"
            )


def _app_user_acceptance_single_source_markers(
    path: Path,
    text: str,
    support_cache: dict[Path, bool] | None = None,
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> list[str]:
    tokens = _c_style_tokens(text)
    identifiers = {value for kind, value in tokens if kind == "identifier"}
    markers: set[str] = set()
    call_names = {
        tokens[index][1]
        for index in range(len(tokens) - 1)
        if tokens[index][0] == "identifier"
        and tokens[index + 1] == ("punctuation", "(")
    }
    if "ProviderScope" in call_names:
        markers.add("ProviderScope")
    if "pumpWidget" in call_names:
        markers.add("pumpWidget")
    for index in range(len(tokens) - 2):
        if (
            tokens[index] == ("punctuation", ".")
            and tokens[index + 1][0] == "identifier"
            and tokens[index + 1][1] in {"overrideWith", "overrideWithValue"}
            and tokens[index + 2] == ("punctuation", "(")
        ):
            markers.add(tokens[index + 1][1])
        if (
            tokens[index] == ("identifier", "HttpOverrides")
            and tokens[index + 1] == ("punctuation", ".")
            and tokens[index + 2] == ("identifier", "global")
        ):
            markers.add("HttpOverrides.global")
    markers.update(lexical_substitute_names(path, text))
    markers.update(substitute_library_imports(path, text))
    markers.update(
        first_party_substitute_support_imports(
            path,
            text,
            support_cache,
            source_texts,
            snapshot_files,
        )
    )
    for identifier in {
        "buildAlphaCloudOverrides",
        "providerScopeOverrides",
        "repository_mock_reexports",
        "sourceEvidence",
        "requiredCaseIds",
    }:
        if identifier in identifiers:
            markers.add(identifier)
    if any(
        "coverage evidence is declared" in value
        for value in _source_string_literals(path, text)
    ):
        markers.add("coverage evidence is declared")
    return sorted(markers)


def app_user_acceptance_local_injection_markers(
    path: Path,
    text: str,
    support_cache: dict[Path, bool] | None = None,
    source_texts: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> list[str]:
    """Inspect a UAT's complete Dart library closure from one source snapshot."""
    markers: set[str] = set()
    sources = _dart_library_source_texts(
        path,
        text,
        source_texts,
        snapshot_files,
    )
    for source, source_text in sources:
        markers.update(
            _app_user_acceptance_single_source_markers(
                source,
                source_text,
                support_cache,
                source_texts,
                snapshot_files,
            )
        )
    return sorted(markers)


def verify_all_test_sources(
    failures: Failures,
    all_files: list[Path] | None = None,
    text_cache: dict[Path, str] | None = None,
    snapshot_files: frozenset[Path] | None = None,
) -> None:
    cache = text_cache if text_cache is not None else {}
    paths = all_files if all_files is not None else scan_repository_files()
    support_cache: dict[Path, bool] = {}
    for path in paths:
        name = path.name
        is_canonical_test_source = (
            name.endswith(("_test.go", "_test.py", "_test.dart", "_test.ts"))
            or (name.startswith("test_") and name.endswith(".py"))
        )
        is_api_integration_source = (
            "api_integration" in path.parts
            and path.suffix in {".go", ".py", ".dart", ".ts"}
        )
        if is_api_integration_source:
            text = _read_text(path, cache)
            code_text = _lexical_code_text(path, text)
            for module in substitute_library_imports(path, text):
                failures.add(
                    f"{path.relative_to(ROOT)} imports in-process substitute "
                    f"library {module!r}"
                )
            for module in first_party_substitute_support_imports(
                path,
                text,
                support_cache,
                cache,
                snapshot_files,
            ):
                failures.add(
                    f"{path.relative_to(ROOT)} imports first-party substitute "
                    f"support {module!r} into api_integration"
                )
            for substitute_name in lexical_substitute_names(path, text):
                failures.add(
                    f"{path.relative_to(ROOT)} uses in-process substitute "
                    f"{substitute_name!r} in api_integration"
                )
            for marker in lexical_memory_modes(path, text):
                failures.add(
                    f"{path.relative_to(ROOT)} uses fake integration dependency "
                    f"{marker!r}"
                )
            if FAKE_BUILD_TAG_RE.search(text):
                failures.add(
                    f"{path.relative_to(ROOT)} is gated by a fake/mock/stub "
                    "build constraint"
                )
            for pattern in SKIP_PATTERNS:
                if pattern.search(code_text):
                    failures.add(
                        f"{path.relative_to(ROOT)} contains skip pattern "
                        f"{pattern.pattern!r}"
                    )
        if is_app_user_acceptance_source(path):
            text = _read_text(path, cache)
            for marker in app_user_acceptance_local_injection_markers(
                path,
                text,
                support_cache,
                cache,
                snapshot_files,
            ):
                failures.add(
                    f"{path.relative_to(ROOT)} injects local/mock state into App "
                    f"user-acceptance evidence {marker!r}"
                )
        if not is_canonical_test_source:
            continue
        text = _read_text(path, cache)
        code_text = _lexical_code_text(path, text)
        for pattern in SKIP_PATTERNS:
            if pattern.search(code_text):
                failures.add(
                    f"{path.relative_to(ROOT)} contains skip pattern {pattern.pattern!r}"
                )


def main() -> int:
    failures = Failures()
    all_files, text_cache = scan_repository_snapshot()
    snapshot_files = frozenset(path.resolve() for path in all_files)
    canonical_files = iter_canonical_files(all_files)
    verify_canonical_files(failures, canonical_files, text_cache)
    verify_all_test_sources(
        failures,
        all_files,
        text_cache,
        snapshot_files,
    )
    verify_app_local_fixture_naming(failures, all_files, text_cache)
    verify_test_artifacts(failures)
    return failures.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())

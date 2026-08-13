"""替身识别与第一方 test support 依赖边的递归判定（含 Dart library 闭包）。"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

from test_directory_layout_lib import ROOT

from .lexer import (
    _c_style_tokens,
    _dart_directive_modules,
    _dart_named_directive_values,
    _python_tree,
    authored_support_modules,
    imported_modules,
)
from .patterns import (
    FIRST_PARTY_DOUBLE_PATH_RE,
    FIRST_PARTY_DOUBLE_TYPE_RE,
    SUBSTITUTE_CALL_NAME_RE,
    SUBSTITUTE_COMPOSITE_NAME_RE,
    SUBSTITUTE_LIBRARY_IMPORTS,
)


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

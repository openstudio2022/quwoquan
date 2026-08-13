"""Dart library/part/import 扫描与 entry widget 装配识别。

本模块持有可被测试 monkeypatch 的 ``APP`` 模块属性：
``test_page_object_mount_contract__local_contract_test.py`` 通过
``mock.patch.object(subject.dart_scan, "APP", ...)`` 把扫描根指向临时目录。
"""

from __future__ import annotations

import re
from pathlib import Path

from .context import (
    DART_IMPORT_STATEMENT_RE,
    DART_PART_OF_RE,
    DART_PART_RE,
    DART_URI_LITERAL_RE,
)
from . import context

APP = context.APP


def _dart_library_text(source: Path, errors: list[str], page_id: str) -> str:
    """返回 canonical library 与其直接 Dart part 的源码。

    页面可以通过 ``part`` 拆分，但 page_object_contract 的 ``source_path``
    仍应指向唯一 library 入口，而不是把实现分片登记为第二个页面。这里按 Dart
    library 语义验证 entry widget，同时拒绝缺失或越出 App 根目录的 part。
    """

    source_text = source.read_text(encoding="utf-8", errors="ignore")
    chunks = [source_text]
    for match in re.finditer(
        r"^\s*part\s+['\"]([^'\"]+)['\"]\s*;",
        source_text,
        re.MULTILINE,
    ):
        part_uri = match.group(1)
        part_path = (source.parent / part_uri).resolve()
        try:
            part_path.relative_to(APP.resolve())
        except ValueError:
            errors.append(f"{page_id}: Dart part 越出 App 根目录: {part_uri}")
            continue
        if not part_path.is_file():
            errors.append(f"{page_id}: Dart part 不存在: {part_uri}")
            continue
        chunks.append(part_path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _resolve_app_dart_uri(source: str, uri: str) -> str | None:
    """Resolve one direct App import/export/part without following barrels."""

    if uri.startswith("package:quwoquan_app/"):
        relative = Path("lib") / uri.removeprefix("package:quwoquan_app/")
    elif ":" in uri:
        return None
    else:
        relative = (Path(source).parent / uri)
    candidate = (APP / relative).resolve()
    try:
        return candidate.relative_to(APP.resolve()).as_posix()
    except ValueError:
        return None


def _dart_library_parts(source: str) -> set[str]:
    parts = {source}
    source_file = APP / source
    if not source_file.is_file():
        return parts
    text = source_file.read_text(encoding="utf-8", errors="ignore")
    for uri in DART_PART_RE.findall(text):
        resolved = _resolve_app_dart_uri(source, uri)
        if resolved is not None:
            parts.add(resolved)
    return parts


def _dart_library_owner(source: str) -> str | None:
    source_file = APP / source
    if not source_file.is_file():
        return source
    text = source_file.read_text(encoding="utf-8", errors="ignore")
    if DART_PART_OF_RE.search(text) is None:
        return source
    owners: list[str] = []
    for candidate in source_file.parent.glob("*.dart"):
        relative = candidate.relative_to(APP).as_posix()
        if relative == source:
            continue
        candidate_text = candidate.read_text(encoding="utf-8", errors="ignore")
        if DART_PART_OF_RE.search(candidate_text) is not None:
            continue
        if source in _dart_library_parts(relative):
            owners.append(relative)
    return owners[0] if len(owners) == 1 else None


def _direct_app_import_libraries(source: str) -> set[str]:
    owner = _dart_library_owner(source)
    if owner is None:
        return set()
    source_file = APP / owner
    if not source_file.is_file():
        return set()
    text = source_file.read_text(encoding="utf-8", errors="ignore")
    imported: set[str] = set()
    for statement in DART_IMPORT_STATEMENT_RE.findall(text):
        # Includes every conditional URI in ``import 'a' if (...) 'b'``.
        for uri in DART_URI_LITERAL_RE.findall(statement):
            resolved = _resolve_app_dart_uri(owner, uri)
            if resolved is not None:
                imported_owner = _dart_library_owner(resolved)
                if imported_owner is not None:
                    imported.add(imported_owner)
    return imported


def _direct_app_dart_closure(source: str) -> set[str]:
    """Return parent library+parts and direct import libraries+parts only."""

    owner = _dart_library_owner(source)
    if owner is None:
        return set()
    closure = _dart_library_parts(owner)
    for imported_owner in _direct_app_import_libraries(owner):
        closure.update(_dart_library_parts(imported_owner))
    return closure


def _dart_code_without_comments_and_strings(text: str) -> str:
    """Blank comments and Dart strings while preserving code/newline positions."""

    out = list(text)
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            if end < 0:
                end = length
            for position in range(index, end):
                out[position] = " "
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end < 0 else end + 2
            for position in range(index, end):
                if out[position] != "\n":
                    out[position] = " "
            index = end
            continue
        quote = text[index]
        if quote in {"'", '"'}:
            delimiter = quote * 3 if text.startswith(quote * 3, index) else quote
            end = index + len(delimiter)
            while end < length:
                if text.startswith(delimiter, end):
                    end += len(delimiter)
                    break
                if text[end] == "\\" and len(delimiter) == 1:
                    end += 2
                else:
                    end += 1
            for position in range(index, min(end, length)):
                if out[position] != "\n":
                    out[position] = " "
            index = end
            continue
        index += 1
    return "".join(out)


def _mounts_entry_widget(text: str, entry_widget: str) -> bool:
    text = _dart_code_without_comments_and_strings(text)
    pattern = re.compile(
        rf"(?:\b{re.escape(entry_widget)}"
        r"(?:\.[A-Za-z][A-Za-z0-9_]*)?\s*\("
        rf"|\bextends\s+{re.escape(entry_widget)}\b)"
    )
    return pattern.search(text) is not None


def _direct_constructor_sites(entry_widget: str, *, source: str) -> set[str]:
    """Find production files that directly construct a root-shell widget."""

    source_owner = _dart_library_owner(source)
    if source_owner is None:
        return set()
    source_library = _dart_library_parts(source_owner)
    sites: set[str] = set()
    for path in (APP / "lib").rglob("*.dart"):
        relative = path.relative_to(APP).as_posix()
        if relative == source:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not _mounts_entry_widget(text, entry_widget):
            continue
        consumer_owner = _dart_library_owner(relative)
        if consumer_owner is None:
            continue
        consumer_library = _dart_library_parts(consumer_owner)
        same_library = bool(source_library & consumer_library)
        directly_imported = source_owner in _direct_app_import_libraries(
            consumer_owner
        )
        if same_library or directly_imported:
            sites.add(relative)
    return sites


def _all_dart_type_tokens() -> set[str]:
    tokens: set[str] = set()
    # 页面可直接消费 App 类型或 pure contracts package 的 generated/typed
    # presentation；后者仍属于 production App 编译图，不是 Mock/测试旁路。
    for root in (
        APP / "lib",
        APP / "packages" / "quwoquan_cloud_contracts" / "lib",
    ):
        for path in root.rglob("*.dart"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            tokens.update(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", text))
    return tokens

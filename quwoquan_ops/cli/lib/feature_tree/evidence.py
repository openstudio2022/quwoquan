"""测试树 spec_ref 证据扫描。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from . import context
from .patterns import EVIDENCE_ROOTS, SPEC_REF_MARKER_RE, SPEC_REF_RE, TEST_SUFFIXES


def iter_test_files() -> Iterator[Path]:
    for raw_root in EVIDENCE_ROOTS:
        root = context.REPO_ROOT / raw_root
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in TEST_SUFFIXES:
                continue
            if raw_root == "quwoquan_service" and "test" not in path.name.lower() and "tests" not in path.parts:
                continue
            yield path


def test_spec_refs() -> dict[str, set[str]]:
    """收集带绑定标记的 spec_ref 证据。

    只认单行形态：ref 所在行、ref 出现之前必须有 `spec_ref` 记号
    （SPEC_REF_MARKER_RE，大小写不敏感）。裸字符串字面量不计入。
    """
    refs: dict[str, set[str]] = {}
    for path in iter_test_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found: set[str] = set()
        for line in content.splitlines():
            for match in SPEC_REF_RE.finditer(line):
                if SPEC_REF_MARKER_RE.search(line, 0, match.start()):
                    found.add(match.group(0))
        if found:
            refs[path.relative_to(context.REPO_ROOT).as_posix()] = found
    return refs


def canonical_spec_ref(path: Path, anchor_id: str) -> str:
    return f"{path.relative_to(context.REPO_ROOT).as_posix()}#{anchor_id.lower()}"

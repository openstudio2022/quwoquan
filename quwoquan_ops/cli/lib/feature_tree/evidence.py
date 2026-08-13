"""测试树 spec_ref 证据扫描。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from . import context
from .patterns import EVIDENCE_ROOTS, SPEC_REF_RE, TEST_SUFFIXES


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
    refs: dict[str, set[str]] = {}
    for path in iter_test_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = set(SPEC_REF_RE.findall(content))
        if found:
            refs[path.relative_to(context.REPO_ROOT).as_posix()] = found
    return refs


def canonical_spec_ref(path: Path, anchor_id: str) -> str:
    return f"{path.relative_to(context.REPO_ROOT).as_posix()}#{anchor_id.lower()}"

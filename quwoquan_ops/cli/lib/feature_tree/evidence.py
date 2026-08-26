"""测试树 spec_ref 证据扫描。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from . import context
from .patterns import (
    EVIDENCE_ROOTS,
    SPEC_REF_BLOCK_ITEM_RE,
    SPEC_REF_BLOCK_MARKER_RE,
    SPEC_REF_MARKER_RE,
    SPEC_REF_RE,
    TEST_SUFFIXES,
)


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
    """收集显式 spec_ref 证据；裸字符串字面量不计入。

    合法形态只有两种：ref 同行前置独立 `spec_ref` token，或独占一行的
    `spec_ref:` 后接连续列表项。第二种保留既有测试字节，避免仅为证据格式迁移
    让 ContractGraph readinessEvidence 无谓失效。
    """
    refs: dict[str, set[str]] = {}
    for path in iter_test_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found: set[str] = set()
        in_ref_block = False
        for line in content.splitlines():
            if SPEC_REF_BLOCK_MARKER_RE.fullmatch(line):
                in_ref_block = True
                continue
            if in_ref_block:
                if not line.strip():
                    in_ref_block = False
                    continue
                if SPEC_REF_BLOCK_ITEM_RE.match(line):
                    found.update(match.group(0) for match in SPEC_REF_RE.finditer(line))
                    continue
                in_ref_block = False
            for match in SPEC_REF_RE.finditer(line):
                if SPEC_REF_MARKER_RE.search(line, 0, match.start()):
                    found.add(match.group(0))
        if found:
            refs[path.relative_to(context.REPO_ROOT).as_posix()] = found
    return refs


def canonical_spec_ref(path: Path, anchor_id: str) -> str:
    return f"{path.relative_to(context.REPO_ROOT).as_posix()}#{anchor_id.lower()}"

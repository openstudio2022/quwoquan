"""垂类分叉、contentVertical 使用与 taxonomy 运行时消费者扫描及快照组装。"""

from __future__ import annotations

from pathlib import Path

from .constants import (
    CASE_RE,
    CODE_SUFFIXES,
    CONTENT_VERTICAL_COMPARE_RE,
    CONTENT_VERTICAL_RE,
    DOMAIN_TAXONOMY,
    TAXONOMY_FILENAME_RE,
    TEXT_SUFFIXES,
)
from .fsscan import (
    _code_without_comment_lines,
    _iter_files,
    _normalized_line,
    _read_text,
    _relative,
    _scan_identifier_hits,
    _summary,
)
from .models import HitSummary, Snapshot
from .retired_travel import scan_travel_dependencies
from .taxonomy import load_vertical_terms, scan_service_domains


def scan_content_vertical_usage(root: Path) -> dict[str, HitSummary]:
    roots = (
        Path("quwoquan_app/lib"),
        Path("quwoquan_data/scripts"),
        Path("quwoquan_service/runtime"),
        Path("quwoquan_service/services"),
    )
    return _scan_identifier_hits(
        root,
        _iter_files(root, roots, suffixes=TEXT_SUFFIXES, exclude_copy=True),
        CONTENT_VERTICAL_RE,
    )


def _is_vertical_label(value: str, vertical_terms: frozenset[str]) -> bool:
    normalized = value.lower().replace("-", "_")
    return normalized in vertical_terms or any(
        normalized.startswith(f"{term}_") for term in vertical_terms
    )


def scan_platform_vertical_branches(
    root: Path,
    vertical_terms: frozenset[str],
) -> dict[str, HitSummary]:
    roots = (
        Path("quwoquan_app/lib"),
        Path("quwoquan_data/scripts"),
        Path("quwoquan_service/runtime"),
        Path("quwoquan_service/services"),
    )
    results: dict[str, HitSummary] = {}
    for path in _iter_files(
        root,
        roots,
        suffixes=CODE_SUFFIXES,
        exclude_copy=True,
    ):
        relative = _relative(root, path)
        text = _code_without_comment_lines(_read_text(path))
        found: list[tuple[int, str]] = []
        for match in CASE_RE.finditer(text):
            value = match.group("value")
            if _is_vertical_label(value, vertical_terms):
                found.append((match.start(), f"case:{value}"))
        for match in CONTENT_VERTICAL_COMPARE_RE.finditer(text):
            found.append((match.start(), f"comparison:{match.group(0)}"))
        if not found:
            continue
        fingerprints = [
            f"{kind}|{_normalized_line(text, offset)}" for offset, kind in found
        ]
        samples = [
            f"{relative}: {_normalized_line(text, offset)}" for offset, _ in found
        ]
        results[relative] = _summary(relative, fingerprints, samples)
    return dict(sorted(results.items()))


def scan_taxonomy_runtime_consumers(root: Path) -> dict[str, HitSummary]:
    """只扫可执行业务树；canonical contract、生成体、测试、迁移和 gate 不算消费者。"""

    roots = (
        Path("quwoquan_app/lib"),
        Path("quwoquan_data/scripts"),
        Path("quwoquan_service/runtime"),
        Path("quwoquan_service/services"),
    )
    paths = (
        path
        for path in _iter_files(
            root,
            roots,
            suffixes=TEXT_SUFFIXES,
            exclude_copy=True,
        )
        if "contracts" not in path.relative_to(root).parts
        and path.relative_to(root) != DOMAIN_TAXONOMY
    )
    return _scan_identifier_hits(root, paths, TAXONOMY_FILENAME_RE)


def build_snapshot(root: Path) -> tuple[Snapshot, list[str]]:
    vertical_terms = load_vertical_terms(root)
    service_domains, service_issues = scan_service_domains(root)
    return (
        Snapshot(
            vertical_terms=vertical_terms,
            service_domains=service_domains,
            platform_vertical_branches=scan_platform_vertical_branches(
                root, vertical_terms
            ),
            content_vertical_usage=scan_content_vertical_usage(root),
            domain_taxonomy_runtime_consumers=scan_taxonomy_runtime_consumers(root),
            travel_service_dependencies=scan_travel_dependencies(root),
        ),
        service_issues,
    )

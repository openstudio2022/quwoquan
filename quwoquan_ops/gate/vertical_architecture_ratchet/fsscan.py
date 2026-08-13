"""文件枚举、文本归一、摘要与 YAML/JSON 读取的共享扫描基元。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, Sequence

import yaml

from .constants import COPY_PARTS, SKIP_PARTS
from .models import HitSummary


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_skipped(relative: Path, *, exclude_copy: bool = False) -> bool:
    parts = set(relative.parts)
    return bool(parts & SKIP_PARTS) or (exclude_copy and bool(parts & COPY_PARTS))


def _iter_files(
    root: Path,
    relative_roots: Sequence[Path],
    *,
    suffixes: set[str],
    exclude_copy: bool = False,
) -> Iterable[Path]:
    seen: set[Path] = set()
    for relative_root in relative_roots:
        scan_root = root / relative_root
        if not scan_root.is_dir():
            continue
        for directory, child_directories, filenames in os.walk(scan_root):
            relative_directory = Path(directory).relative_to(root)
            child_directories[:] = sorted(
                name
                for name in child_directories
                if not _is_skipped(
                    relative_directory / name,
                    exclude_copy=exclude_copy,
                )
            )
            for filename in sorted(filenames):
                path = Path(directory) / filename
                if path.suffix.lower() not in suffixes:
                    continue
                if (
                    "_test." in path.name
                    or path.name.startswith("test_")
                    or path.name.endswith("_test.dart")
                ):
                    continue
                relative = path.relative_to(root)
                if _is_skipped(relative, exclude_copy=exclude_copy):
                    continue
                if path in seen:
                    continue
                seen.add(path)
                yield path


def _code_without_comment_lines(text: str) -> str:
    """移除纯注释行，避免文案/说明中的示例被当作控制流。"""

    lines: list[str] = []
    in_block_comment = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            lines.append("")
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped[2:]:
                in_block_comment = True
            lines.append("")
            continue
        if stripped.startswith(("//", "#", "*")):
            lines.append("")
            continue
        lines.append(line)
    return "\n".join(lines)


def _normalized_line(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    return re.sub(r"\s+", " ", text[start:end].strip())


def _digest(path: str, fingerprints: Sequence[str]) -> str:
    payload = json.dumps(
        {"path": path, "fingerprints": sorted(fingerprints)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _summary(path: str, fingerprints: Sequence[str], samples: Sequence[str]) -> HitSummary:
    return HitSummary(
        count=len(fingerprints),
        digest=_digest(path, fingerprints),
        samples=tuple(samples[:5]),
    )


def _load_yaml_mapping(path: Path, *, label: str) -> dict:
    try:
        document = yaml.safe_load(_read_text(path))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{label} 无法读取或解析: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} 必须是 mapping: {path}")
    return document


def _load_json_mapping(path: Path, *, label: str) -> dict:
    try:
        document = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} 无法读取或解析: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} 必须是 mapping: {path}")
    return document


def _scan_identifier_hits(
    root: Path,
    paths: Iterable[Path],
    pattern: re.Pattern[str],
) -> dict[str, HitSummary]:
    results: dict[str, HitSummary] = {}
    for path in paths:
        relative = _relative(root, path)
        text = _code_without_comment_lines(_read_text(path))
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        fingerprints = [
            f"{match.group(0)}|{_normalized_line(text, match.start())}"
            for match in matches
        ]
        samples = [f"{relative}: {_normalized_line(text, match.start())}" for match in matches]
        results[relative] = _summary(relative, fingerprints, samples)
    return dict(sorted(results.items()))

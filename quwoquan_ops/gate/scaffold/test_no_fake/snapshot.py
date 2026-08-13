"""仓库物理树的一次性确定性快照采集与源码文本缓存。"""

from __future__ import annotations

import os
from pathlib import Path

from test_directory_layout_lib import ROOT

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

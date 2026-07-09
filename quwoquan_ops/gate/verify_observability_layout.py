#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import (
    ENVS,
    LOG_FILE_SUFFIX,
    LOG_KINDS,
    OBSERVABILITY_ROOT,
)

ALLOWED_RUN_ENTRIES = frozenset({"manifest.json", "logs", "metrics", "traces", "attachments"})
ALLOWED_METRICS_FILES = frozenset({"snapshot.json", "prometheus.prom"})
ALLOWED_TRACE_FILES = frozenset({"links.json"})
ALLOWED_ATTACHMENT_FILES = frozenset({"stdout.log", "stderr.log"})
ALLOWED_ATTACHMENT_DIRS = frozenset({"screenshots"})


def layout_issues(root: Path = OBSERVABILITY_ROOT) -> list[str]:
    issues: list[str] = []
    runs_root = root / "runs"
    if not root.exists():
        return issues
    root_names = {path.name for path in root.iterdir()}
    unknown_root = root_names - {"runs"}
    if unknown_root:
        issues.append(f"{_rel(root)}: unknown entries {sorted(unknown_root)}")
    if not runs_root.is_dir():
        return [f"{_rel(root)}: observability root may only contain runs/"]
    for entry in sorted(runs_root.iterdir()):
        if not entry.is_dir():
            issues.append(f"{_rel(entry)}: runs/ only allows env directories")
    for env_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        if env_dir.name not in ENVS:
            issues.append(f"{_rel(env_dir)}: unknown env segment")
        for entry in sorted(env_dir.iterdir()):
            if not entry.is_dir():
                issues.append(f"{_rel(entry)}: env segment only allows run directories")
        for run_dir in sorted(path for path in env_dir.iterdir() if path.is_dir()):
            names = {path.name for path in run_dir.iterdir()}
            unknown = names - ALLOWED_RUN_ENTRIES
            if unknown:
                issues.append(f"{_rel(run_dir)}: unknown entries {sorted(unknown)}")
            if "manifest.json" not in names:
                issues.append(f"{_rel(run_dir)}: missing manifest.json")
            issues.extend(_logs_issues(run_dir / "logs"))
            issues.extend(_metrics_issues(run_dir / "metrics"))
            issues.extend(_traces_issues(run_dir / "traces"))
            issues.extend(_attachments_issues(run_dir / "attachments"))
    return issues


def _logs_issues(logs_root: Path) -> list[str]:
    issues: list[str] = []
    if not logs_root.exists():
        return issues
    for path in sorted(logs_root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix != LOG_FILE_SUFFIX:
            issues.append(f"{_rel(path)}: log files must use {LOG_FILE_SUFFIX}")
            continue
        kind = path.stem
        if kind not in LOG_KINDS:
            issues.append(f"{_rel(path)}: unknown log kind")
    return issues


def _metrics_issues(metrics_root: Path) -> list[str]:
    if not metrics_root.exists():
        return []
    return [
        f"{_rel(path)}: metrics only allow {sorted(ALLOWED_METRICS_FILES)}"
        for path in sorted(metrics_root.rglob("*"))
        if path.is_file() and path.name not in ALLOWED_METRICS_FILES
    ]


def _traces_issues(traces_root: Path) -> list[str]:
    if not traces_root.exists():
        return []
    return [
        f"{_rel(path)}: traces only keep backend links, not full spans"
        for path in sorted(traces_root.rglob("*"))
        if path.is_file() and path.name not in ALLOWED_TRACE_FILES
    ]


def _attachments_issues(attachments_root: Path) -> list[str]:
    issues: list[str] = []
    if not attachments_root.exists():
        return issues
    for path in sorted(attachments_root.iterdir()):
        if path.is_dir() and path.name in ALLOWED_ATTACHMENT_DIRS:
            continue
        if path.is_file() and path.name in ALLOWED_ATTACHMENT_FILES:
            continue
        issues.append(f"{_rel(path)}: unsupported attachment")
    return issues


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    issues = layout_issues()
    if issues:
        print("[verify_observability_layout] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_observability_layout] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import (
    LOG_FILE_SUFFIX,
    OBSERVABILITY_ROOT,
    parse_log_records,
    validate_log_record,
)


def envelope_issues(root: Path = OBSERVABILITY_ROOT, *, max_lines_per_file: int = 200) -> list[str]:
    issues: list[str] = []
    log_roots = []
    env_root = root / "env"
    if env_root.exists():
        log_roots.extend(path / "observability" for path in env_root.iterdir() if path.is_dir())
    for path in sorted(
        log_path
        for log_root in log_roots
        for log_path in log_root.rglob(f"*{LOG_FILE_SUFFIX}")
    ):
        kind = path.stem
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            issues.append(f"{_rel(path)}: not valid utf-8")
            continue
        records, parse_issues = parse_log_records(kind, lines[:max_lines_per_file])
        issues.extend(f"{_rel(path)}:{issue}" for issue in parse_issues)
        for index, payload in enumerate(records, start=1):
            for issue in validate_log_record(kind, payload):
                issues.append(f"{_rel(path)}:record{index}: {issue}")
    return issues


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    issues = envelope_issues()
    if issues:
        print("[verify_observability_envelope] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_observability_envelope] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

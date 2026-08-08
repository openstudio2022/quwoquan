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
    # 零日志样本不是通过：没有记录被解析时本门禁没有校验任何信封，
    # 必须阻断而不是返回空 issue 列表。
    issues: list[str] = []
    log_roots = []
    env_root = root / "env"
    if not env_root.is_dir():
        return [
            f"{_rel(env_root)}: 可观测扫描根不存在，没有任何日志样本可校验信封；"
            "空扫描不构成通过证据"
        ]
    log_roots.extend(path / "observability" for path in env_root.iterdir() if path.is_dir())
    log_paths = sorted(
        log_path
        for log_root in log_roots
        for log_path in log_root.rglob(f"*{LOG_FILE_SUFFIX}")
    )
    if not log_paths:
        return [
            f"{_rel(env_root)}: 扫描到 0 份 {LOG_FILE_SUFFIX} 日志样本；"
            "空扫描不构成通过证据"
        ]
    validated_records = 0
    for path in log_paths:
        kind = path.stem
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            issues.append(f"{_rel(path)}: not valid utf-8")
            continue
        records, parse_issues = parse_log_records(kind, lines[:max_lines_per_file])
        issues.extend(f"{_rel(path)}:{issue}" for issue in parse_issues)
        validated_records += len(records)
        for index, payload in enumerate(records, start=1):
            for issue in validate_log_record(kind, payload):
                issues.append(f"{_rel(path)}:record{index}: {issue}")
    if validated_records == 0:
        issues.append(
            f"{_rel(env_root)}: {len(log_paths)} 份日志文件解析出 0 条记录；"
            "零记录不构成信封通过证据"
        )
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

#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import (
    LOG_FILE_SUFFIX,
    LOG_KINDS,
    OBSERVABILITY_ROOT,
    append_log_line,
    write_run_manifest,
)
from quwoquan_ops.cli.lib.output_paths import ENV_SEGMENTS, safe_segment

ALLOWED_RUN_ENTRIES = frozenset({"manifest.json", "logs", "metrics", "traces", "attachments"})
ALLOWED_METRICS_FILES = frozenset({"snapshot.json", "prometheus.prom"})
ALLOWED_TRACE_FILES = frozenset({"links.json"})
ALLOWED_ATTACHMENT_FILES = frozenset({"stdout.log", "stderr.log"})
ALLOWED_ATTACHMENT_DIRS = frozenset({"screenshots"})


def materialize_repo_gate_observability_run(
    root: Path = OBSERVABILITY_ROOT,
) -> Path:
    """Record this real repository gate before validating an otherwise clean checkout."""
    identity = "-".join(
        part
        for part in (
            os.environ.get("GITHUB_RUN_ID", ""),
            os.environ.get("GITHUB_JOB", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        )
        if part
    ) or f"local-{os.getpid()}"
    run_id = safe_segment(f"repo-gate-{identity}")
    run = root / "env" / "repo" / "observability" / run_id
    report_dir = root / "env" / "repo" / "runs" / run_id
    write_run_manifest(
        run,
        env_name="repo",
        run_id=run_id,
        command="gate_repo",
        target="repo",
        report_dir=report_dir,
    )
    append_log_line(
        run / "logs" / "ci" / "repo-gate" / "runtime.log",
        {
            "event": "repository_gate_observability_validation",
            "result": "started",
            "message": "repository gate observability validation started",
            "attributes": {"gate": "gate_repo"},
        },
        resource={"sourceType": "ops", "service": "repo-gate"},
        signal="ops.runtime.process",
    )
    return run


def layout_issues(root: Path = OBSERVABILITY_ROOT) -> list[str]:
    # 空扫描不是通过：扫描根缺失或一个 run 都没有时，本门禁什么都没校验，
    # 等价于没有门禁，因此必须阻断而不是返回空 issue 列表。
    if not root.exists():
        return [
            f"{_rel(root)}: observability 扫描根不存在，无法校验任何布局；"
            "先产出可观测运行输出（stackctl 等），不得按空集报告通过"
        ]
    issues: list[str] = []
    old_root = root / "observability"
    if old_root.exists():
        issues.append(f"{_rel(old_root)}: old observability root is forbidden; use env/<env>/observability")

    env_root = root / "env"
    if not env_root.is_dir():
        issues.append(
            f"{_rel(env_root)}: 缺少 env/ 扫描根，没有任何环境可观测输出可供校验"
        )
    else:
        observed_runs = 0
        for entry in sorted(env_root.iterdir()):
            if not entry.is_dir():
                issues.append(f"{_rel(entry)}: env/ only allows environment directories")
                continue
            if entry.name not in ENV_SEGMENTS:
                issues.append(f"{_rel(entry)}: unknown env segment")
                continue
            observability_root = entry / "observability"
            observed_runs += _observability_run_count(observability_root)
            issues.extend(_observability_runs_issues(observability_root))
        if observed_runs == 0:
            issues.append(
                f"{_rel(env_root)}: 扫描到 0 个 observability run；"
                "空扫描不构成通过证据"
            )
    data_observability = root / "data" / "observability"
    if data_observability.exists():
        issues.append(
            f"{_rel(data_observability)}: data observability is forbidden; use env/repo/observability"
        )
    return issues


def _observability_run_count(observability_root: Path) -> int:
    if not observability_root.is_dir():
        return 0
    return sum(1 for entry in observability_root.iterdir() if entry.is_dir())


def _observability_runs_issues(observability_root: Path) -> list[str]:
    issues: list[str] = []
    if not observability_root.exists():
        return issues
    for entry in sorted(observability_root.iterdir()):
        if not entry.is_dir():
            issues.append(f"{_rel(entry)}: observability only allows run directories")
            continue
        names = {path.name for path in entry.iterdir()}
        unknown = names - ALLOWED_RUN_ENTRIES
        if unknown:
            issues.append(f"{_rel(entry)}: unknown entries {sorted(unknown)}")
        if "manifest.json" not in names:
            issues.append(f"{_rel(entry)}: missing manifest.json")
        issues.extend(_logs_issues(entry / "logs"))
        issues.extend(_metrics_issues(entry / "metrics"))
        issues.extend(_traces_issues(entry / "traces"))
        issues.extend(_attachments_issues(entry / "attachments"))
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
    materialize_repo_gate_observability_run()
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

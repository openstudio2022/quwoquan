"""报告组装、CLI 参数与 main 入口。"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .bootstrap import DEFAULT_ROOT
from .bytecode_guard import bytecode_guard_issues
from .constants import PYTHON_LINE_BUDGET_ENFORCEMENT, SCOPES
from .hygiene import naming_issues, source_hygiene_issues, tool_owner_issues
from .inventory import enumerate_scripts, python_file_records
from .line_budget import line_budget_issues
from .models import Issue, Warning
from .references import import_references, path_references
from .roles import role_records
from .structure import (
    app_structure_issues,
    data_architecture_issues,
    ops_structure_issues,
    service_structure_issues,
    service_verify_single_owner_warnings,
)


def derive_report(root: Path, scopes: Sequence[str]) -> dict[str, object]:
    normalized_root = root.resolve()
    scope_scripts: list[tuple[str, Path]] = []
    scripts_by_scope: dict[str, list[Path]] = {}
    for scope in scopes:
        scripts = enumerate_scripts(normalized_root, scope)
        scripts_by_scope[scope] = scripts
        scope_scripts.extend((scope, path) for path in scripts)

    # Build one reference/import graph across the selected scopes so
    # Ops → Service and Makefile-relative scripts/... edges stay visible.
    all_scripts = [path for _, path in scope_scripts]
    references_by_path = path_references(normalized_root, all_scripts)
    references_by_import = import_references(normalized_root, all_scripts)
    records = role_records(
        normalized_root,
        scope_scripts,
        references_by_path,
        references_by_import,
    )
    file_records = python_file_records(
        normalized_root,
        scopes,
        scripts_by_scope,
    )

    issues: list[Issue] = source_hygiene_issues(normalized_root, scopes)
    issues.extend(bytecode_guard_issues(normalized_root, scopes))
    warnings: list[Warning] = []
    for scope, scripts in scripts_by_scope.items():
        issues.extend(naming_issues(normalized_root, scripts))
        if scope == "app":
            issues.extend(app_structure_issues(normalized_root, scripts))
        elif scope == "service":
            issues.extend(service_structure_issues(normalized_root, scripts))
            warnings.extend(
                service_verify_single_owner_warnings(normalized_root, scripts)
            )
        elif scope == "ops":
            issues.extend(ops_structure_issues(normalized_root))
        elif scope == "data":
            issues.extend(data_architecture_issues(normalized_root))

    for record in records:
        if record.role == "unclassified":
            issues.append(
                Issue(
                    code="SCRIPT.ROLE_UNCLASSIFIED",
                    path=record.path,
                    message="script has no canonical role signal",
                )
            )
    issues.extend(tool_owner_issues(records))
    issues.extend(
        Issue(
            code="PYTHON.BOUNDARY_UNKNOWN",
            path=record.path,
            message="Python file is outside every derived governance boundary",
        )
        for record in file_records
        if record.boundary == "unknown"
    )

    budget_findings = line_budget_issues(normalized_root, file_records)
    if PYTHON_LINE_BUDGET_ENFORCEMENT == "block":
        issues.extend(budget_findings)
    else:
        warnings.extend(
            Warning(
                code=finding.code,
                path=finding.path,
                message=finding.message,
            )
            for finding in budget_findings
        )

    unique_issues = sorted(
        {issue for issue in issues},
        key=lambda issue: (issue.code, issue.path, issue.message),
    )
    unique_warnings = sorted(
        {warning for warning in warnings},
        key=lambda warning: (warning.code, warning.path, warning.message),
    )
    sorted_records = sorted(records, key=lambda record: record.path)
    sorted_python_files = sorted(
        file_records,
        key=lambda record: record.path,
    )
    boundary_counts: dict[str, int] = {}
    for record in sorted_python_files:
        boundary_counts[record.boundary] = (
            boundary_counts.get(record.boundary, 0) + 1
        )
    return {
        "schema": "quwoquan.python-script-governance-report.v2",
        "scopes": list(scopes),
        "summary": {
            "scriptCount": len(sorted_records),
            "pythonFileCount": len(sorted_python_files),
            "pythonBoundaryCounts": {
                key: boundary_counts[key] for key in sorted(boundary_counts)
            },
            "issueCount": len(unique_issues),
            "warningCount": len(unique_warnings),
            "lineBudgetExceededCount": len(budget_findings),
            "orphanCandidateCount": sum(
                1 for record in sorted_records if record.orphanCandidate
            ),
        },
        "issues": [asdict(issue) for issue in unique_issues],
        "warnings": [asdict(warning) for warning in unique_warnings],
        "scripts": [asdict(record) for record in sorted_records],
        "pythonFiles": [asdict(record) for record in sorted_python_files],
    }


def _scopes(value: str) -> tuple[str, ...]:
    return SCOPES if value == "all" else (value,)


def _report_bytes(report: dict[str, object]) -> bytes:
    return (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "派生全 Python 治理边界及 Python/Shell 脚本 owner、角色、结构、"
            "行数预算与卫生违规。"
        )
    )
    parser.add_argument("--scope", choices=(*SCOPES, "all"), default="all")
    parser.add_argument("--mode", choices=("report", "check"), default="check")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Repository root; intended for local_contract fixture trees.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Report path. Defaults under .qwq_output for report mode.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    scopes = _scopes(args.scope)
    report = derive_report(args.repo_root, scopes)
    payload = _report_bytes(report)

    if args.mode == "report":
        output = args.output or (
            args.repo_root
            / ".qwq_output/env/repo/runs/python-script-governance"
            / f"{args.scope}.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        print(
            "[verify_python_script_governance] REPORT "
            f"scripts={report['summary']['scriptCount']} "
            f"pythonFiles={report['summary']['pythonFileCount']} "
            f"issues={report['summary']['issueCount']} "
            f"warnings={report['summary'].get('warningCount', 0)} "
            f"orphanCandidates={report['summary']['orphanCandidateCount']} "
            f"output={output}"
        )
        return 0

    issues = report["issues"]
    warnings = report.get("warnings") or []
    if warnings:
        print("[verify_python_script_governance] WARN")
        for warning in warnings:
            print(
                f"  - {warning['code']} {warning['path']}: {warning['message']}"
            )
    if issues:
        print("[verify_python_script_governance] FAIL")
        for issue in issues:
            print(f"  - {issue['code']} {issue['path']}: {issue['message']}")
        return 1
    print(
        "[verify_python_script_governance] OK "
        f"scripts={report['summary']['scriptCount']} "
        f"pythonFiles={report['summary']['pythonFileCount']} "
        f"warnings={report['summary'].get('warningCount', 0)}"
    )
    return 0

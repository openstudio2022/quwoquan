"""stackctl test-data 命令表面（test-data-request / test-data-evidence）。

从 stackctl.py 逐字迁出两个子命令的 argparse 表面与命令壳：

- `command_test_data_request`：物化七领域 canonical release Journey 的
  强类型 test-data request graph；
- `command_test_data_evidence`：从当前 Provider conformance readiness
  仅投影选中 request 的候选绑定 evidence 闭包并冻结 handoff。

强类型 composition 本体在 `quwoquan_ops/cli/lib/test_data/**`（真相源，
本模块只经 stackctl 命名空间消费其公开入口）；data readiness 读取
（`_load_test_data_release_readiness`）与候选装载仍由 stackctl 命名空间
拥有（verify 域共用）。测试经 ``mock.patch.object(stackctl, ...)``
patch 上述符号，因此函数体内一律经函数内延迟导入 `_stackctl`
属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.content_release_readiness import ProbeOutcome


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    test_data_request_parser = subparsers.add_parser(
        "test-data-request",
        help="生成七领域 canonical Journey 的强类型 test-data request graph",
    )
    test_data_request_parser.add_argument(
        "--report-dir",
        default=argparse.SUPPRESS,
        help="可选输出目录；默认写入 repo 级可重建运行证据目录",
    )

    test_data_evidence_parser = subparsers.add_parser(
        "test-data-evidence",
        help="从当前 Provider conformance 投影选中 request 的候选绑定 evidence",
    )
    test_data_evidence_parser.add_argument(
        "--report-dir",
        default=argparse.SUPPRESS,
    )
    test_data_evidence_parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma"),
        required=True,
    )
    test_data_evidence_parser.add_argument(
        "--target",
        choices=tuple(_stackctl.TEST_DATA_TARGETS),
        required=True,
    )
    test_data_evidence_parser.add_argument("--data-release-id", required=True)
    test_data_evidence_parser.add_argument("--data-verify-run-id", required=True)
    test_data_evidence_parser.add_argument("--data-manifest-digest", required=True)
    test_data_evidence_parser.add_argument("--test-data-request", required=True)


def command_test_data_request(args: argparse.Namespace) -> dict[str, Any]:
    """Materialize the one governed release Journey request composition."""
    import quwoquan_ops.cli.stackctl as _stackctl

    started_monotonic, started_at = _stackctl._start_timing()
    report_dir = _stackctl.resolve_report_dir(args, "repo", "repo")
    document = _stackctl.case_request_document(_stackctl.canonical_acceptance_suite())
    request_path = report_dir / "request.json"
    _stackctl.write_json(request_path, document)
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    summary = {
        "schema": "qwq.test_data_request_summary",
        "caseCount": len(document["cases"]),
        "requestCount": len(document["requests"]),
        "requestDigest": document["requestDigest"],
        "requestPath": _stackctl.relpath(request_path),
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", summary)
    return {
        "exitCode": 0,
        "summary": "canonical typed test-data request generated",
        "details": [
            f"cases={summary['caseCount']}",
            f"requests={summary['requestCount']}",
            f"requestDigest={summary['requestDigest']}",
        ],
        "reportDir": _stackctl.relpath(report_dir),
        "requestPath": _stackctl.relpath(request_path),
        **timing,
    }


def command_test_data_evidence(args: argparse.Namespace) -> dict[str, Any]:
    """Bind selected canonical Provider readiness to one candidate/request."""
    import quwoquan_ops.cli.stackctl as _stackctl

    started_monotonic, started_at = _stackctl._start_timing()
    environment = str(args.env)
    target_name = str(args.target)
    report_dir = _stackctl.resolve_report_dir(args, environment, target_name)
    issues: list[str] = []
    evidence_path = report_dir / "evidence.json"
    try:
        if _stackctl.TEST_DATA_TARGETS.get(target_name) != environment:
            raise ValueError("test-data evidence target/environment mismatch")
        request_path = Path(str(args.test_data_request)).expanduser()
        if not request_path.is_absolute():
            request_path = _stackctl.ROOT / request_path
        request_path = request_path.resolve()
        request_path.relative_to(_stackctl.output_root().expanduser().resolve())
        request_document = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request_document, Mapping):
            raise TypeError("test-data request must be an object")
        # Request identity and strong types belong to TestData owner. Validate
        # them before candidate/Data/Provider reads so an owner-local drift is
        # never hidden behind an unrelated environment readiness blocker.
        _stackctl.load_case_requests(request_document)
        active = _stackctl.active_deployment_candidate(target_name)
        if not isinstance(active, Mapping):
            raise ValueError("active immutable deployment candidate is required")
        manifest = _stackctl.load_candidate_manifest(
            environment,
            target_name,
            str(active.get("baselineId") or ""),
            require_full=True,
        )
        readiness, _ = _stackctl._load_test_data_release_readiness(
            environment=environment,
            release_id=str(args.data_release_id),
            verify_run_id=str(args.data_verify_run_id),
            manifest_digest=str(args.data_manifest_digest),
        )
        candidate = _stackctl.build_candidate_binding(
            environment=environment,
            target=target_name,
            manifest=manifest,
            readiness=readiness,
        )
        readiness_report, readiness_issues = (
            _stackctl._provider_conformance().load_validate_and_derive()
        )
        evidence = _stackctl.build_provider_evidence_document(
            request_document=request_document,
            candidate=candidate,
            readiness_report=readiness_report,
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        _stackctl.write_json(evidence_path, evidence)
        handoff = _stackctl.build_test_data_handoff(
            candidate=candidate,
            readiness=readiness,
            request_document=request_document,
            evidence=evidence,
        )
        _stackctl.write_json(report_dir / "handoff.json", handoff)
        ignored_issue_count = len(readiness_issues)
        status = "passed"
    except (
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        issues.append(str(exc))
        ignored_issue_count = 0
        status = ProbeOutcome.GATE_BLOCK.value
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    report = {
        "schema": "qwq.test_data_evidence_summary",
        "status": status,
        "environment": environment,
        "target": target_name,
        "evidencePath": _stackctl.relpath(evidence_path) if not issues else "",
        "handoffPath": (
            _stackctl.relpath(report_dir / "handoff.json") if not issues else ""
        ),
        "providerReadinessIssueCount": ignored_issue_count,
        "issues": issues,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            "selected test-data Provider evidence generated"
            if not issues
            else "selected test-data Provider evidence is GATE_BLOCK"
        ),
        "details": issues or [f"evidence={_stackctl.relpath(evidence_path)}"],
        "reportDir": _stackctl.relpath(report_dir),
        "evidencePath": _stackctl.relpath(evidence_path) if not issues else "",
        "handoffPath": _stackctl.relpath(report_dir / "handoff.json") if not issues else "",
        **timing,
    }

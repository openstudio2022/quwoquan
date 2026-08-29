"""stackctl `health` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面、HTTP 探针编排与本域私有
helper（`_health_body_evidence` / `_health_request_policy` /
`_script_probes_for_target`）。健康检查矩阵与脚本探针计划归
`commands/diagnostics_shared.py`（与 inspect / status 共用）；启动收据
scope、deadline 与环境集成探针（`_current_runtime_health_scope` /
`_remaining_deadline_seconds` / `_run_environment_integration_probe`）
仍由 stackctl 命名空间拥有（verify 等留守域共用）。测试经
``mock.patch.object(stackctl, ...)`` patch 上述符号，因此函数体内
一律经函数内延迟导入 `_stackctl` 属性访问，保持 monkeypatch 语义
并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib import read_only_user_availability as _read_only_user_availability


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    health_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    health_parser.add_argument(
        "--scope",
        choices=[
            "edge",
            "media",
            "service",
            "content-import",
            "content-consumer",
            "content-commercial",
            "full",
        ],
        # 缺省跟随最近一次 up 的 workload（content-release → content-consumer /
        # content-import）；显式 --scope full 仍可做完整探针。
        default=argparse.SUPPRESS,
    )
    health_parser.add_argument("--request-timeout-seconds", type=int, default=0)
    health_parser.add_argument("--retry-attempts", type=int, default=0)
    health_parser.add_argument("--retry-sleep-seconds", type=float, default=-1.0)


def _health_body_evidence(body: str) -> dict[str, Any]:
    encoded = body.encode("utf-8")
    evidence: dict[str, Any] = {
        "bodyPreview": body[:500],
        "bodySha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "failedChecks": [],
        "failureDetails": {},
    }
    try:
        document = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return evidence
    if not isinstance(document, dict):
        return evidence
    failed = document.get("failedChecks")
    checks = document.get("checks")
    if not isinstance(failed, list) or not isinstance(checks, dict):
        return evidence
    failed_checks = sorted(
        {
            str(name).strip()
            for name in failed
            if isinstance(name, str) and str(name).strip()
        }
    )
    failure_details: dict[str, str] = {}
    for name in failed_checks:
        detail = checks.get(name)
        if not isinstance(detail, str) or not detail.strip():
            continue
        failure_details[name] = detail.strip()
    evidence["failedChecks"] = failed_checks
    evidence["failureDetails"] = failure_details
    return evidence


def _health_request_policy(target_name: str, scope: str) -> dict[str, float | int]:
    policy: dict[str, float | int] = {
        "timeoutSeconds": 6.0,
        "retryAttempts": 2,
        "retrySleepSeconds": 2.0,
    }
    if target_name == "prod-hosted":
        policy.update(
            {
                "timeoutSeconds": 15.0 if scope == "edge" else 20.0,
                "retryAttempts": 3,
                "retrySleepSeconds": 3.0,
            }
        )
    return policy


def _script_probes_for_target(
    topology: dict[str, Any],
    target_name: str,
    scope: str,
    report_dir: Path,
    *,
    require_non_empty_content_feed: bool = False,
    research_anonymous_convergence: bool = False,
    deadline_epoch: int = 0,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    feed_semantics_selected = (
        require_non_empty_content_feed or research_anonymous_convergence
    )
    if scope != "full" and not feed_semantics_selected:
        return [], [], []
    statuses: list[dict[str, Any]] = []
    stdout_sections: list[tuple[str, str]] = []
    findings: list[str] = []

    if target_name in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        probe_timeout = (
            _stackctl._remaining_deadline_seconds(deadline_epoch, "health verification")
            if deadline_epoch > 0
            else None
        )
        # content-consumer / content-release must not require search or other
        # full-stack commercial probes; those belong to scope=full only.
        only_checks: tuple[str, ...] = ()
        if feed_semantics_selected and scope != "full":
            only_checks = (
                "content_feed",
                "video_book_feed",
            )
        status, output, probe_findings = _stackctl._run_environment_integration_probe(
            topology,
            target_name,
            report_dir,
            require_non_empty_content_feed=require_non_empty_content_feed,
            research_anonymous_convergence=research_anonymous_convergence,
            only_checks=only_checks,
            timeout_seconds=probe_timeout,
        )
        if feed_semantics_selected and scope != "full":
            status["scope"] = scope
        statuses.append(status)
        stdout_sections.append((status["name"], output))
        findings.extend(probe_findings)
    return statuses, stdout_sections, findings


def _surface_health(statuses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Report the API plane and the static recovery Web plane independently.

    两个面各自只由自己的探针决定：API 全停不得把静态恢复面标成 failed，
    静态面缺失也不得被 API 的绿色掩盖。
    """
    from quwoquan_ops.cli.commands.diagnostics_shared import (
        PUBLIC_WEB_STATIC_SCOPE,
    )

    def summarize(
        selected: list[dict[str, Any]],
        *,
        blocker: str,
    ) -> dict[str, Any]:
        observed = [item for item in selected if not item.get("skipped")]
        if not observed:
            return {"status": "not_observed", "firstBlocker": "", "checks": []}
        failed = [item for item in observed if not item.get("ok")]
        return {
            "status": "failed" if failed else "ok",
            "firstBlocker": blocker if failed else "",
            "checks": [str(item.get("name") or "") for item in observed],
        }

    return {
        "api": summarize(
            [
                item
                for item in statuses
                if item.get("scope") == "edge" and item.get("name") == "api-health"
            ],
            # API 面没有 launcher typed blocker，沿用 findings 的探针命名。
            blocker="edge/api-health",
        ),
        "publicWeb": summarize(
            [
                item
                for item in statuses
                if item.get("scope") == PUBLIC_WEB_STATIC_SCOPE
            ],
            blocker="APP.WEB.recovery_unavailable",
        ),
    }


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    if not hasattr(args, "scope"):
        args.scope = _stackctl._current_runtime_health_scope(args.target)
    workload = str(getattr(args, "workload", "") or "").strip() or None
    check_resolution_issue: str | None = None
    try:
        checks = _stackctl._health_checks_for_target(
            topology,
            args.target,
            args.scope,
            workload=workload,
        )
    except (RuntimeError, TypeError, ValueError) as error:
        checks = []
        check_resolution_issue = f"health check resolution blocked: {error}"
    policy = _stackctl._health_request_policy(args.target, args.scope)
    timeout_seconds = (
        max(1.0, float(args.request_timeout_seconds))
        if getattr(args, "request_timeout_seconds", 0)
        else float(policy["timeoutSeconds"])
    )
    retry_attempts = (
        max(1, int(args.retry_attempts))
        if getattr(args, "retry_attempts", 0)
        else int(policy["retryAttempts"])
    )
    retry_sleep_seconds = (
        max(0.0, float(args.retry_sleep_seconds))
        if getattr(args, "retry_sleep_seconds", -1.0) >= 0
        else float(policy["retrySleepSeconds"])
    )
    statuses: list[dict[str, Any]] = []
    findings: list[str] = []
    stdout_sections: list[tuple[str, str]] = []
    if check_resolution_issue is not None:
        statuses.append(
            {
                "name": "active-candidate",
                "scope": "config",
                "type": "candidate",
                "url": f"candidate://{args.target}",
                "ok": False,
                "statusCode": None,
                "bodyPreview": check_resolution_issue,
                "skipped": False,
            }
        )
    read_only = bool(getattr(args, "read_only", False))
    deadline_epoch = int(getattr(args, "deadline_epoch", 0) or 0)
    if deadline_epoch > 0:
        retry_attempts = 1
        retry_sleep_seconds = 0.0

    def probe_http_check(item: dict[str, Any]) -> dict[str, Any]:
        if item.get("skip"):
            return {
                "name": item["name"],
                "scope": item["scope"],
                "url": item["url"],
                "ok": True,
                "statusCode": None,
                "bodyPreview": str(item.get("reason", "skipped")),
                "skipped": True,
            }
        try:
            effective_timeout = (
                min(
                    timeout_seconds,
                    _stackctl._remaining_deadline_seconds(
                        deadline_epoch, "health verification"
                    ),
                )
                if deadline_epoch > 0
                else timeout_seconds
            )
        except RuntimeError as error:
            ok, status_code, body, content_type = False, None, str(error), ""
        else:
            ok, status_code, body, content_type = _stackctl.fetch_url(
                item["url"],
                timeout=max(0.05, effective_timeout),
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
                headers=item.get("headers"),
                ca_file=str(item.get("caFile") or ""),
                body_limit=65_536,
            )
        expected_status = item.get("expectedStatus")
        if ok and expected_status is not None and status_code != int(expected_status):
            ok = False
            body = f"expected HTTP {expected_status}, got {status_code}"
        expected_content_type_prefix = str(item.get("expectedContentTypePrefix") or "")
        if (
            ok
            and expected_content_type_prefix
            and not content_type.lower().startswith(expected_content_type_prefix.lower())
        ):
            ok = False
            body = (
                f"expected Content-Type {expected_content_type_prefix}*, "
                f"got {content_type or '<empty>'}"
            )
        body_evidence = _stackctl._health_body_evidence(body)
        return {
            "name": item["name"],
            "scope": item["scope"],
            "url": item["url"],
            "ok": ok,
            "statusCode": status_code,
            "contentType": content_type,
            **body_evidence,
            "skipped": False,
        }

    probe_concurrency = min(16, len(checks))
    if probe_concurrency:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=probe_concurrency,
            thread_name_prefix="stackctl-health",
        ) as executor:
            statuses = list(executor.map(probe_http_check, checks))
    for status in statuses:
        if not status["ok"]:
            detail = str(status.get("bodyPreview") or "").strip()
            findings.append(
                f"{status['scope']}/{status['name']} failed: "
                f"{status['statusCode'] or 'ERR'} {status['url']}"
                + (f": {detail}" if detail else "")
            )
        if not status["skipped"]:
            stdout_sections.append(
                (
                    status["name"],
                    f"{status['statusCode'] or 'ERR'} {status['url']}\n"
                    f"{status['bodyPreview']}",
                )
            )
    api_prerequisite = next(
        (
            item
            for item in statuses
            if item.get("scope") == "edge" and item.get("name") == "api-health"
        ),
        None,
    )
    if not read_only and api_prerequisite is not None and not api_prerequisite["ok"]:
        blocked = "integration-readonly blocked by failed edge/api-health prerequisite"
        statuses.append(
            {
                "name": "integration-readonly",
                "scope": args.scope,
                "type": "script",
                "argv": [],
                "ok": False,
                "statusCode": None,
                "bodyPreview": blocked,
                "skipped": True,
                "reportPath": "",
            }
        )
        stdout_sections.append(("integration-readonly", blocked))
        findings.append(blocked)
    elif not read_only and check_resolution_issue is None:
        try:
            script_statuses, script_stdout_sections, script_findings = _stackctl._script_probes_for_target(
                topology,
                args.target,
                args.scope,
                report_dir,
                require_non_empty_content_feed=bool(
                    getattr(args, "require_non_empty_content_feed", False)
                ),
                research_anonymous_convergence=bool(
                    getattr(args, "research_anonymous_convergence", False)
                ),
                deadline_epoch=deadline_epoch,
            )
        except RuntimeError as error:
            script_statuses = [
                {
                    "name": "integration-readonly",
                    "scope": args.scope,
                    "type": "script",
                    "argv": [],
                    "ok": False,
                    "statusCode": 124,
                    "bodyPreview": str(error),
                    "skipped": False,
                    "reportPath": "",
                }
            ]
            script_stdout_sections = [("integration-readonly", str(error))]
            script_findings = [str(error)]
        statuses.extend(script_statuses)
        stdout_sections.extend(script_stdout_sections)
        findings.extend(script_findings)
    try:
        user_availability = _stackctl._read_only_user_availability_report(args.target)
    except (
        AttributeError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        detail = f"read-only availability aggregation failed: {error}"
        layers = [
            {
                "name": name,
                "status": "blocked",
                "issues": [detail],
            }
            for name in (
                "build_ready",
                "runtime_full_ready",
                "provider_ready",
                "release_active",
                "content_exact_queries_ready",
                "device_bound",
                "content_live_passed",
            )
        ]
        user_availability = {
            "schema": _read_only_user_availability.SCHEMA,
            "target": args.target,
            "environment": env_name,
            "observedAt": _stackctl.utc_now(),
            "status": "failed",
            "firstBlockerClass": "startup_identity",
            "firstBlocker": detail,
            "userAvailability": layers,
            "metrics": [
                {
                    "name": "stackctl_user_availability",
                    "labels": {
                        "target": args.target,
                        "layer": layer["name"],
                        "status": layer["status"],
                    },
                    "value": 1,
                }
                for layer in layers
            ]
            + [
                {
                    "name": "stackctl_first_blocker",
                    "labels": {
                        "target": args.target,
                        "status": "failed",
                        "firstBlockerClass": "startup_identity",
                    },
                    "value": 1,
                }
            ],
            "evidence": {},
        }
        statuses.append(
            {
                "name": "user-availability",
                "scope": "config",
                "type": "aggregate",
                "url": f"availability://{args.target}",
                "ok": False,
                "statusCode": None,
                "bodyPreview": detail,
                "skipped": False,
            }
        )
        findings.append(detail)
    ok_count = sum(1 for item in statuses if item["ok"])
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    surfaces = _surface_health(statuses)
    payload = {
        "command": "health",
        "target": args.target,
        "scope": args.scope,
        "requestTimeoutSeconds": timeout_seconds,
        "retryAttempts": retry_attempts,
        "retrySleepSeconds": retry_sleep_seconds,
        "httpProbeConcurrency": probe_concurrency,
        "checks": statuses,
        "surfaces": surfaces,
        "findings": findings,
        "timestamp": _stackctl.utc_now(),
        "scriptProbes": _stackctl._script_probe_plan_for_target(topology, args.target),
        "readOnly": read_only,
        "userAvailabilityReport": user_availability,
        "userAvailability": user_availability["userAvailability"],
        "firstBlockerClass": user_availability["firstBlockerClass"],
        "observabilityMetrics": user_availability["metrics"],
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "health.json", {"target": args.target, "scope": args.scope, "checks": statuses})
    _stackctl.write_json(report_dir / "findings.json", {"target": args.target, "scope": args.scope, "issues": findings})
    availability_failed = user_availability.get("status") != "ready"
    _stackctl._write_summary_bundle(
        report_dir,
        command="health",
        target=args.target,
        status="ok" if not findings and not availability_failed else "failed",
        summary=f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        details=findings
        or (
            [
                "user availability/"
                + str(user_availability.get("firstBlockerClass") or "unknown")
                + " failed: "
                + str(user_availability.get("firstBlocker") or "required evidence is unavailable")
            ]
            if availability_failed
            else [f"scope={args.scope}", f"healthy checks={ok_count}/{len(statuses)}"]
        ),
        extra={"scope": args.scope},
        timing=timing,
    )
    _stackctl._write_stdout_markdown(report_dir, stdout_sections)
    availability_details = (
        [
            "user availability/"
            + str(user_availability.get("firstBlockerClass") or "unknown")
            + " failed: "
            + str(user_availability.get("firstBlocker") or "required evidence is unavailable")
        ]
        if availability_failed
        else []
    )
    return {
        "exitCode": 0 if not findings and not availability_failed else 1,
        "summary": f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        "details": findings
        or availability_details
        or [
            "{name} -> {status} {target}".format(
                name=item["name"],
                status=item.get("statusCode") or "OK",
                target=item.get("url") or item.get("reportPath") or item.get("bodyPreview", ""),
            ).strip()
            for item in statuses
        ],
        "reportDir": _stackctl.relpath(report_dir),
        "userAvailability": user_availability["userAvailability"],
        "firstBlockerClass": user_availability["firstBlockerClass"],
        **timing,
    }

"""stackctl `inspect` 子命令域（模块名避开内置 inspect）。

从 stackctl.py 逐字迁出 argparse 表面、巡检编排与本域私有报告
helper（`_local_log_report` / `_runtime_log_evidence_report` /
`_data_report` / `_metrics_report` / `_prometheus_scrape_inspection` /
`_security_report`）。健康检查矩阵与候选工作区报告归
`commands/diagnostics_shared.py`；网络/发布状态/prod runtime/发行
分发检查（`_network_report` / `_load_release_state` /
`_prod_instance_runtime_reports` / `_inspect_distribution_for_target`
等）仍由 stackctl 命名空间拥有（up / verify / deploy / repair 等留守
域共用）。测试经 ``mock.patch.object(stackctl, ...)`` patch 上述符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问，保持
monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    inspect_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    inspect_parser.add_argument(
        "--ssh-host",
        default="",
        help="SSH-only host for prod-hosted runtime inspection; never an App public base",
    )
    inspect_parser.add_argument(
        "--host-id",
        default="",
        help="Select one logical prod-hosted host from access-isolation.yaml.",
    )
    inspect_parser.add_argument(
        "--deployment-instance",
        choices=("prevalidate", "gray", "prod"),
        default="prod",
    )
    inspect_parser.add_argument(
        "--scope",
        choices=[
            "logs",
            "network",
            "data",
            "metrics",
            "config",
            "security",
            "release",
            "all",
        ],
        default="all",
    )
    inspect_parser.add_argument(
        "--kind",
        dest="scope",
        choices=[
            "logs",
            "network",
            "data",
            "metrics",
            "config",
            "security",
            "release",
            "all",
        ],
    )
    inspect_parser.add_argument("--distribution-root", default="")
    inspect_parser.add_argument("--verify-hosted", action="store_true")
    inspect_parser.add_argument(
        "--currentness",
        action="store_true",
        help="explicitly compare the active candidate with its declared source closure",
    )


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    scopes = (
        ["logs", "network", "data", "metrics", "config", "security", "release"]
        if args.scope == "all"
        else [args.scope]
    )
    inspection: dict[str, Any] = {}
    findings: list[str] = []
    candidate_workspace = (
        (
            _stackctl._candidate_workspace_report(args.target, purpose="currentness")
            if getattr(args, "currentness", False)
            else _stackctl._candidate_workspace_report(args.target)
        )
        if "config" in scopes or "data" in scopes
        else None
    )
    if "network" in scopes:
        try:
            inspection["network"] = _stackctl._network_report(args.target)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            detail = f"network inspection blocked: {error}"
            inspection["network"] = {
                "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
                "ports": [],
                "publicEndpoints": [],
                "issues": [detail],
            }
            findings.append(detail)
    if "config" in scopes:
        inspection["config"] = {
            "target": target,
            "portProfile": target.get("portProfile"),
            "publicBases": target.get("publicBases", {}),
            "origins": target.get("origins", {}),
            "candidateWorkspace": candidate_workspace,
            "releaseState": (
                _stackctl._load_release_state(_stackctl.PROD_RELEASE_UNIT)
                if args.target == "prod-hosted"
                else {}
            ),
        }
        if args.target == "prod-hosted":
            runtimes = _stackctl._prod_instance_runtime_reports(
                report_dir,
                instance=str(getattr(args, "deployment_instance", "prod") or "prod"),
                host=str(getattr(args, "ssh_host", "") or ""),
                host_id=str(getattr(args, "host_id", "") or ""),
            )
            inspection["config"]["rootlessRuntimeReplicas"] = runtimes
            for runtime in runtimes:
                plane = str(runtime.get("plane") or "unknown")
                findings.extend(_stackctl._prod_plane_runtime_findings(runtime, plane=plane))
            service_runtimes = [
                runtime for runtime in runtimes if runtime.get("plane") == "service"
            ]
            edge_runtimes = [
                runtime for runtime in runtimes if runtime.get("plane") == "edge"
            ]
            if len(service_runtimes) == 1:
                inspection["config"]["rootlessRuntime"] = service_runtimes[0]
            if len(edge_runtimes) == 1:
                inspection["config"]["edgeRootlessRuntime"] = edge_runtimes[0]
        if "data" not in scopes and candidate_workspace is not None:
            findings.extend(
                f"candidate workspace: {issue}"
                for issue in candidate_workspace.get("issues", [])
            )
    if "logs" in scopes:
        inspection["logs"] = _stackctl._local_log_report(args.target)
    if "data" in scopes:
        try:
            inspection["data"] = _stackctl._data_report(
                args.target,
                candidate_workspace=candidate_workspace,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            detail = f"data inspection blocked: {error}"
            inspection["data"] = {
                "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
                "issues": [detail],
            }
        findings.extend(
            f"data: {issue}" for issue in inspection["data"].get("issues", [])
        )
    if "metrics" in scopes:
        try:
            inspection["metrics"] = _stackctl._metrics_report(topology, args.target)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            detail = f"metrics inspection blocked: {error}"
            inspection["metrics"] = {
                "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
                "issues": [detail],
            }
            findings.append(detail)
    if "security" in scopes:
        security = _stackctl._security_report(topology, args.target)
        if args.target in {"alpha-local", "beta-local", "gamma-local"}:
            try:
                tls = _stackctl.verify_certificate(args.target)
                security["publicTls"] = {
                    key: value
                    for key, value in tls.items()
                    if key not in {"certificate", "privateKey"}
                }
            except _stackctl.PublicDomainTlsError as error:
                detail = str(error)
                security["publicTls"] = {
                    "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
                    "issues": [detail],
                }
                findings.append(f"public TLS: {detail}")
        inspection["security"] = security
    if "release" in scopes:
        try:
            release_inspection, _, _ = _stackctl._inspect_distribution_for_target(
                args,
                target_name=args.target,
            )
            inspection["release"] = release_inspection
            findings.extend(
                f"release distribution: {issue}"
                for issue in release_inspection.get("issues", [])
            )
        except (OSError, ValueError, _stackctl.OfficialDistributionReleaseError) as error:
            inspection["release"] = {
                "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
                "issues": [str(error)],
            }
            findings.append(f"release distribution: {error}")
    output_inspection = dict(inspection)
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "inspect",
            "inspection": output_inspection,
            "findings": findings,
            **timing,
        },
    )
    for key, value in inspection.items():
        if key == "config":
            continue
        _stackctl.write_json(report_dir / f"{key}.json", value)
    _stackctl.write_json(
        report_dir / "findings.json",
        {"target": args.target, "scope": args.scope, "issues": findings},
    )
    details = findings or [f"{key}: collected" for key in inspection]
    status = "failed" if findings else "ok"
    summary = (
        f"stackctl inspect failed for {args.target}"
        if findings
        else f"stackctl inspect completed for {args.target}"
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="inspect",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        extra={"scope": args.scope},
        timing=timing,
    )
    return {
        "exitCode": 1 if findings else 0,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _local_log_report(target_name: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    candidates: dict[str, Path] = {
        "alpha-state": _stackctl.target_process_dir("alpha-local"),
        "beta-state": _stackctl.target_process_dir("beta-local"),
        "beta-manual": _stackctl.target_process_dir("beta-local") / "app-beta-manual",
        "app-instances": _stackctl.repo_local_dir("app-instances"),
        "local-gamma": _stackctl.target_process_dir("gamma-local"),
        "release-state": _stackctl._release_state_dir(),
    }
    hits = []
    for name, path in candidates.items():
        if path.exists():
            hits.append({"name": name, "path": _stackctl.relpath(path)})
    extra: dict[str, Any] = {}
    try:
        runtime_root = _stackctl._local_runtime_log_root(target_name)
    except RuntimeError:
        runtime_root = None
    if runtime_root is not None:
        extra["runtimeDiagnostics"] = _stackctl._runtime_log_evidence_report(runtime_root)
    else:
        extra["runtimeDiagnostics"] = {
            "availability": "not_started",
            "recordCount": 0,
            "reason": "local runtime observability root is unavailable",
        }
    if target_name == "prod-hosted":
        extra["prodReleaseState"] = _stackctl._load_release_state(_stackctl.PROD_RELEASE_UNIT)
    return {"paths": hits, **extra}


def _runtime_log_evidence_report(log_root: Path) -> dict[str, Any]:
    """Summarize canonical records without copying raw messages into reports."""
    import quwoquan_ops.cli.stackctl as _stackctl

    severity_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    parse_issues: list[str] = []
    record_count = 0
    files = sorted(path for path in log_root.rglob("*.log") if path.is_file())
    for path in files:
        kind = path.stem
        try:
            records, issues = _stackctl.parse_log_records(
                kind,
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
            )
        except ValueError:
            continue
        record_count += len(records)
        parse_issues.extend(
            f"{_stackctl.relpath(path)}: {issue}" for issue in issues[:5]
        )
        for record in records:
            severity = str(record.get("severity") or "UNKNOWN")
            signal = str(record.get("signal") or "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
    return {
        "availability": "available" if log_root.exists() else "not_started",
        "root": _stackctl.relpath(log_root),
        "files": [_stackctl.relpath(path) for path in files],
        "recordCount": record_count,
        "severityCounts": dict(sorted(severity_counts.items())),
        "topSignals": [
            {"signal": signal, "count": count}
            for signal, count in sorted(
                signal_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:10]
        ],
        "parseIssues": parse_issues[:20],
    }


def _data_report(
    target_name: str,
    *,
    candidate_workspace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return {"ports": []}
    manifest = _stackctl.load_port_manifest()
    report: dict[str, Any] = {
        "ports": {
            "postgres": _stackctl.canonical_port(manifest, profile_name, "postgres"),
            "mongodb": _stackctl.canonical_port(manifest, profile_name, "mongodb"),
            "redis": _stackctl.canonical_port(manifest, profile_name, "redis"),
        },
        "realDataOnly": str(target.get("env")) == "prod",
        "nonprodAcceptanceDatasets": [],
        "issues": [],
    }
    workspace_binding = candidate_workspace or _stackctl._candidate_workspace_report(target_name)
    report["candidateWorkspace"] = workspace_binding
    report["issues"].extend(
        f"candidate workspace: {issue}"
        for issue in workspace_binding.get("issues", [])
    )
    environment = str(target.get("env") or "")
    active_manifest: dict[str, Any] | None = None
    active = _stackctl.active_deployment_candidate(target_name)
    if isinstance(active, dict):
        baseline_id = str(active.get("baselineId") or "").strip()
        try:
            active_manifest = _stackctl.load_candidate_manifest(
                environment,
                target_name,
                baseline_id,
                require_full=True,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report["issues"].append(
                "active candidate manifest is invalid: " + type(exc).__name__
            )
    report["activeCandidateBinding"] = (
        {
            "baselineId": active_manifest.get("baselineId"),
            "packageDigest": active_manifest.get("packageDigest"),
            "releaseDigest": (
                ((active_manifest.get("release") or {}).get("candidate") or {}).get(
                    "releaseDigest"
                )
            ),
        }
        if active_manifest is not None
        else None
    )
    receipt_root = _stackctl.env_runs_root(environment) / "nonprod-data"
    if not receipt_root.is_dir():
        return report
    if environment == "prod":
        report["issues"].append(
            "Prod run root contains forbidden nonprod acceptance dataset receipts"
        )
        return report
    retired_schema_receipts = sorted(receipt_root.glob("*/*.json"))
    for path in retired_schema_receipts:
        report["issues"].append(
            "retired nonprod-data receipt must be explicitly cleaned before "
            f"typed test-data verification: {_stackctl.relpath(path)}"
        )
        report["nonprodAcceptanceDatasets"].append(
            {
                "status": "retired_schema",
                "receiptRef": _stackctl.relpath(path),
            }
        )
    return report


def _metrics_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    checks = _stackctl._health_checks_for_target(topology, target_name, "full")
    report: dict[str, Any] = {
        "probes": [
            {"name": item["name"], "url": item["url"]}
            for item in checks
        ],
        "scriptProbes": _stackctl._script_probe_plan_for_target(topology, target_name),
    }
    # 指标面实查：有 PROMETHEUS_URL（与 deploy SLO readback 同一配置源）时
    # 读回 scrape target 健康与核心 series 存在性；缺配置显式 unavailable，
    # 不合成健康态。
    prometheus_url = os.environ.get("PROMETHEUS_URL", "").strip()
    if not prometheus_url:
        report["prometheus"] = {
            "status": "unavailable",
            "reason": "PROMETHEUS_URL is not configured",
        }
    else:
        report["prometheus"] = _stackctl._prometheus_scrape_inspection(prometheus_url)
    return report


def _prometheus_scrape_inspection(prometheus_url: str) -> dict[str, Any]:
    """读回 Prometheus targets 健康分布与核心观测 series 的样本存在性。"""
    base = prometheus_url.rstrip("/")
    inspection: dict[str, Any] = {"status": "ok", "url": base}
    try:
        with urllib.request.urlopen(f"{base}/api/v1/targets", timeout=5) as response:
            targets_payload = json.loads(response.read().decode("utf-8"))
        active = targets_payload.get("data", {}).get("activeTargets", [])
        down = [
            {
                "job": str(item.get("labels", {}).get("job", "")),
                "instance": str(item.get("labels", {}).get("instance", "")),
                "lastError": str(item.get("lastError", ""))[:160],
            }
            for item in active
            if str(item.get("health", "")) != "up"
        ]
        inspection["targets"] = {
            "active": len(active),
            "down": down,
        }
        if down:
            inspection["status"] = "degraded"
    except (OSError, ValueError, TimeoutError) as error:
        return {"status": "error", "url": base, "reason": str(error)[:200]}
    core_series = (
        "http_server_requests_total",
        "recommendation_feed_impressed_total",
        "ops_telemetry_ingest_events_total",
    )
    series_presence: dict[str, Any] = {}
    for series in core_series:
        query = urllib.parse.urlencode({"query": f"count({series})"})
        try:
            with urllib.request.urlopen(
                f"{base}/api/v1/query?{query}", timeout=5
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            results = payload.get("data", {}).get("result", [])
            series_presence[series] = bool(results)
        except (OSError, ValueError, TimeoutError) as error:
            series_presence[series] = f"error: {str(error)[:120]}"
    inspection["coreSeriesPresent"] = series_presence
    if any(present is False for present in series_presence.values()):
        inspection["status"] = "degraded"
    return inspection


def _security_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = _stackctl.get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    return {
        "hostAllowlist": env_cfg.get("hostAllowlist", []),
        "forbiddenHostTokens": env_cfg.get("forbiddenHostTokens", []),
        "artifactPolicy": env_cfg.get("artifactPolicy", {}),
    }

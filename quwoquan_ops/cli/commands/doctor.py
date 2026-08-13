"""stackctl `doctor` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与诊断编排胶水。健康探针
（`command_health`）、网络/发布状态/prod runtime 报告与 legal-static
校验仍由 stackctl 命名空间拥有（多域共用，且测试经
``mock.patch`` patch 这些符号），命令函数体内一律经函数内延迟导入
`_stackctl` 属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    doctor_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    doctor_parser.add_argument(
        "--ssh-host",
        default="",
        help="SSH-only host for prod-hosted runtime diagnosis; never an App public base",
    )
    doctor_parser.add_argument("--host-id", default="")
    doctor_parser.add_argument(
        "--deployment-instance",
        choices=("prevalidate", "gray", "prod"),
        default="prod",
    )


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    findings: list[str] = []
    advisories: list[str] = []
    deployment_prerequisite_failed = False
    if args.target in {"alpha-local", "beta-local", "gamma-local"}:
        try:
            _stackctl._load_active_product_telemetry_log_sink(env_name, args.target)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            deployment_prerequisite_failed = True
            findings.append(f"deployment prerequisite failed: {exc}")
    if args.target in {"prod-sim", "prod-hosted"}:
        legal_result, legal_payload = _stackctl._legal_static_command("validate", env_name)
        if legal_result.returncode != 0:
            deployment_prerequisite_failed = True
            findings.append("deployment prerequisite failed: prod legal-static source is invalid")
            legal_issues = legal_payload.get("issues")
            if isinstance(legal_issues, list):
                findings.extend(
                    f"legal-static validation: {issue}"
                    for issue in legal_issues
                    if isinstance(issue, str) and issue.strip()
                )
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope="full",
        output_format="json",
        report_dir=str(report_dir / "health"),
    )
    health = _stackctl.command_health(health_args)
    if health["exitCode"] != 0:
        findings.append("health checks are failing")
    if target.get("portProfile"):
        try:
            network = _stackctl._network_report(args.target)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            network = {"ports": []}
            findings.append(f"network inspection blocked: {error}")
        closed = [item["name"] for item in network["ports"] if not item["open"]]
        if closed:
            findings.append(f"ports not listening: {', '.join(closed)}")
    elif args.target == "prod-hosted":
        public_bases = target.get("publicBases") or {}
        if not public_bases.get("api"):
            findings.append("public api base url is missing")
        if not public_bases.get("productOps"):
            findings.append("product-ops base url is missing")
        if args.target == "prod-hosted":
            state = _stackctl._load_release_state(_stackctl.PROD_RELEASE_UNIT)
            if not state:
                advisories.append(
                    "prod rollout release-state is missing (local cache empty; hosted deploy workflow can resolve current state via service-plane SSH)"
                )
            elif not all(
                state.get(field)
                for field in (
                    "to_candidate_digest",
                    "to_release_evidence_ref",
                    "to_image_transport_tag",
                )
            ):
                findings.append(
                    "prod release-state missing canonical candidate authority metadata"
                )
            runtimes = _stackctl._prod_instance_runtime_reports(
                report_dir,
                instance=str(getattr(args, "deployment_instance", "prod") or "prod"),
                host=str(getattr(args, "ssh_host", "") or ""),
                host_id=str(getattr(args, "host_id", "") or ""),
            )
            for runtime in runtimes:
                findings.extend(
                    _stackctl._prod_plane_runtime_findings(
                        runtime,
                        plane=str(runtime.get("plane") or "unknown"),
                    )
                )
    try:
        packages = [
            _stackctl.app_deployment_package_dir(env_name, target=args.target) / "report.json"
        ]
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        packages = []
        deployment_prerequisite_failed = True
        findings.append(f"package inspection blocked: {error}")
    require_package_artifacts = bool(target.get("portProfile"))
    if (
        require_package_artifacts
        and packages
        and not all(path.exists() for path in packages)
    ):
        findings.append("packaged app artifact is missing")
    repair_plan = []
    if findings:
        if deployment_prerequisite_failed:
            repair_plan.append(
                "ensure the declared local Provider topology and any required "
                "QWQ_DEPLOY_WORK_ROOT material are available, then rerun `stackctl doctor`"
            )
            if args.target in {"prod-sim", "prod-hosted"}:
                repair_plan.append(
                    "replace prod legal-static placeholder identity fields with approved legal facts and rerun `stackctl doctor`"
                )
        if any("health checks" in item for item in findings):
            repair_plan.append("run `stackctl health --target <target> --scope full` to confirm failing probes")
        if not deployment_prerequisite_failed and any(
            "ports not listening" in item for item in findings
        ):
            repair_plan.append("run `stackctl repair --target <target> --fix restart-stack` for local targets")
        if any("artifact" in item for item in findings):
            repair_plan.append("run `stackctl repair --target <target> --fix rebuild-packages`")
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "doctor",
            "target": args.target,
            "findings": findings,
            "advisories": advisories,
            "repairPlan": repair_plan,
            "timestamp": _stackctl.utc_now(),
            **timing,
        },
    )
    _stackctl.write_json(
        report_dir / "findings.json",
        {"target": args.target, "issues": findings, "advisories": advisories},
    )
    _stackctl.write_json(report_dir / "repair_plan.json", {"target": args.target, "actions": repair_plan})
    _stackctl._write_summary_bundle(
        report_dir,
        command="doctor",
        target=args.target,
        status="ok" if not findings else "failed",
        summary="stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        details=findings + advisories or ["no issues found"],
        timing=timing,
    )
    return {
        "exitCode": 0 if not findings else 1,
        "summary": "stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        "details": findings + advisories or ["no issues found"],
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }

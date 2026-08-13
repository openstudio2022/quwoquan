"""stackctl prod hosted plane 运行时巡检报告域。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_prod_plane_runtime_report` / `_prod_instance_runtime_reports` /
`_prod_hosted_placement_coverage_checks` / `_prod_plane_runtime_findings`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import json

from pathlib import Path
from typing import Any


def _prod_plane_runtime_report(
    plane: str,
    report_path: Path | None = None,
    *,
    instance: str = "prod",
    host: str = "",
    host_id: str = "",
    replica_id: str = "",
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    argv = ["python3", "quwoquan_ops/cli/prod/inspect_prod_plane_runtime.py", "--plane", plane]
    argv.extend(["--instance", instance])
    if host:
        argv.extend(["--host", host])
    if host_id:
        argv.extend(["--host-id", host_id])
    if replica_id:
        argv.extend(["--replica-id", replica_id])
    if report_path is not None:
        argv.extend(["--output", str(report_path)])
    result = _stackctl.run(argv)
    if result.returncode != 0:
        return {
            "plane": plane,
            "error": "inspect command failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.returncode,
        }
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "plane": plane,
            "error": "inspect output is not valid json",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.returncode,
        }


def _prod_instance_runtime_reports(
    report_dir: Path,
    *,
    instance: str,
    host: str = "",
    host_id: str = "",
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    plan_argv = [
        "python3",
        "quwoquan_ops/cli/prod/prod_hosted_topology.py",
        "--instance",
        instance,
    ]
    if host:
        plan_argv.extend(["--ssh-host", host])
    if host_id:
        plan_argv.extend(["--host-id", host_id])
    plan_result = _stackctl.run(plan_argv)
    if plan_result.returncode != 0:
        return [
            {
                "error": "deployment plan resolution failed",
                "stdout": plan_result.stdout,
                "stderr": plan_result.stderr,
                "exitCode": plan_result.returncode,
            }
        ]
    try:
        placements = json.loads(plan_result.stdout).get("placements") or []
    except json.JSONDecodeError:
        return [
            {
                "error": "deployment plan output is not valid json",
                "stdout": plan_result.stdout,
                "stderr": plan_result.stderr,
                "exitCode": 2,
            }
        ]
    reports: list[dict[str, Any]] = []
    for placement in placements:
        plane = str(placement.get("plane") or "")
        placement_host_id = str(placement.get("hostId") or "")
        replica_id = str(placement.get("replicaId") or "")
        report_path = (
            report_dir
            / f"prod_rootless_{plane}_{instance}_{placement_host_id}_{replica_id}.json"
        )
        reports.append(
            _stackctl._prod_plane_runtime_report(
                plane,
                report_path,
                instance=instance,
                host=host,
                host_id=placement_host_id,
                replica_id=replica_id,
            )
        )
    return reports


def _prod_hosted_placement_coverage_checks(
    report_dir: Path,
    *,
    stage: str,
    host: str = "",
    host_id: str = "",
) -> list[dict[str, Any]]:
    """Build one digest-bound postCheck per host/plane/replica placement."""
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        instance = _stackctl.prod_hosted_instance_for_stage(stage)
        plan = _stackctl.resolve_prod_hosted_plan(
            _stackctl.load_prod_hosted_access_manifest(),
            instance=instance,
            host_ids=[host_id] if host_id else None,
            ssh_host_override=host,
        )
    except _stackctl.ProdHostedTopologyError as error:
        return [
            {
                "command": "prod-hosted-placement-coverage",
                "exitCode": 2,
                "summary": f"prod-hosted placement plan resolution failed: {error}",
                "details": [str(error)],
            }
        ]
    runtimes = _stackctl._prod_instance_runtime_reports(
        report_dir / "placement-coverage",
        instance=instance,
        host=host,
        host_id=host_id,
    )
    runtime_by_key = {
        (
            str(item.get("plane") or ""),
            str(item.get("hostId") or ""),
            str(item.get("replicaId") or ""),
        ): item
        for item in runtimes
        if isinstance(item, dict)
    }
    checks: list[dict[str, Any]] = []
    for placement in plan:
        key = (placement.plane, placement.host_id, placement.replica_id)
        runtime = runtime_by_key.get(key)
        if runtime is None:
            # Fall back to plane-only match for older inspect payloads.
            runtime = next(
                (
                    item
                    for item in runtimes
                    if isinstance(item, dict)
                    and item.get("plane") == placement.plane
                    and (
                        not item.get("hostId")
                        or item.get("hostId") == placement.host_id
                    )
                    and (
                        not item.get("replicaId")
                        or item.get("replicaId") == placement.replica_id
                    )
                ),
                None,
            )
        findings = (
            _stackctl._prod_plane_runtime_findings(runtime, plane=placement.plane)
            if isinstance(runtime, dict)
            else [f"missing runtime inspect for {placement.plane}/{placement.replica_id}"]
        )
        if runtime is None:
            findings = [
                f"missing runtime inspect for {placement.plane}/{placement.replica_id}"
            ]
        receipt = {
            "schema": "prod-hosted-placement-receipt",
            "target": "prod-hosted",
            "stage": stage,
            "instance": placement.instance,
            "plane": placement.plane,
            "hostId": placement.host_id,
            "replicaId": placement.replica_id,
            "sshHost": placement.ssh_host,
            "remoteRoot": placement.remote_root,
            "project": placement.project,
            "systemdUnit": placement.systemd_unit,
            "findings": findings,
            "runtime": runtime or {},
        }
        receipt_path = (
            report_dir
            / "placement-receipts"
            / f"{placement.host_id}_{placement.plane}_{placement.replica_id}.json"
        )
        _stackctl.write_json(receipt_path, receipt)
        checks.append(
            {
                "command": "prod-hosted-placement-coverage",
                "name": _stackctl.prod_hosted_placement_check_name(placement),
                "exitCode": 0 if not findings else 1,
                "summary": (
                    f"placement {placement.host_id}/{placement.plane}/{placement.replica_id} ready"
                    if not findings
                    else f"placement {placement.host_id}/{placement.plane}/{placement.replica_id} blocked"
                ),
                "details": findings,
                "placementReceiptPath": _stackctl.relpath(receipt_path),
                "placementReceipt": receipt,
            }
        )
    coverage_issues = _stackctl.validate_prod_hosted_host_coverage(
        [
            {
                "name": item["name"],
                "status": "passed" if item["exitCode"] == 0 else "failed",
                "receiptDigest": "sha256:" + ("0" * 64),
            }
            for item in checks
            if item.get("name")
        ],
        plan,
    )
    if coverage_issues:
        checks.append(
            {
                "command": "prod-hosted-placement-coverage",
                "exitCode": 2,
                "summary": "prod-hosted host coverage aggregate CAS blocked",
                "details": coverage_issues,
            }
        )
    return checks


def _prod_plane_runtime_findings(
    runtime: dict[str, Any],
    *,
    plane: str,
) -> list[str]:
    prefix = f"prod {plane} plane rootless runtime"
    if runtime.get("error") or int(runtime.get("exitCode", 0) or 0) != 0:
        return [f"{prefix} inspect failed"]
    findings: list[str] = []
    if not runtime.get("composeFileExists"):
        findings.append(f"{prefix} compose file is missing")
    if not runtime.get("envFileExists"):
        findings.append(f"{prefix} env file is missing")
    unit = runtime.get("unit") or {}
    if unit.get("enabled") is not True:
        findings.append(f"{prefix} systemd unit is not enabled")
    if unit.get("active") is not True:
        findings.append(f"{prefix} systemd unit is not active")
    containers = runtime.get("containers") or []
    if not containers:
        findings.append(f"{prefix} has no project containers")
    for container in containers:
        name = str(container.get("name") or "unknown")
        if container.get("running") is not True:
            findings.append(f"{prefix} container is not running: {name}")
        if container.get("health") in {"starting", "unhealthy"}:
            findings.append(
                f"{prefix} container health is {container.get('health')}: {name}"
            )
    return findings

"""stackctl prod hosted plane 运行时巡检报告域。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_prod_plane_runtime_report` / `_prod_instance_runtime_reports` /
`_prod_hosted_placement_coverage_checks` / `_prod_plane_runtime_findings`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import hashlib
import json

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir

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


def _placement_identity_findings(runtime: dict, placement: Any, candidate: str) -> list[str]:
    """读回必须匹配本次已验证渲染物；不由健康状态推导配置身份。"""
    expected = {
        "instance": placement.instance, "plane": placement.plane,
        "hostId": placement.host_id, "replicaId": placement.replica_id,
        "host": placement.ssh_host, "account": placement.account,
        "composeRoot": placement.remote_root, "project": placement.project,
        "candidateDigest": candidate, "configDigest": candidate,
    }
    issues = [f"placement identity mismatch: {key}" for key, value in expected.items()
              if not value or runtime.get(key) != value]
    if (runtime.get("unit") or {}).get("name") != placement.systemd_unit:
        issues.append("placement systemd unit identity mismatch")
    try:
        root = deployment_render_dir("prod", target="prod-hosted", name=placement.render_name)
        provenance_path = root / "provenance.json"
        raw = provenance_path.read_bytes()
        provenance = json.loads(raw)
        if provenance.get("candidateDigest") != candidate:
            issues.append("local render candidate digest mismatch")
        if runtime.get("provenanceDigest") != hashlib.sha256(raw).hexdigest():
            issues.append("remote provenance digest mismatch")
        config_services = provenance["configServices"]
        if not config_services or len(config_services) != len(set(config_services)):
            raise ValueError("invalid config services")
        digests = {service: provenance["configSources"][service]["effectiveConfigDigest"]
                   for service in config_services}
        if runtime.get("configFileDigests") != digests:
            issues.append("remote config bytes digest mismatch")
    except (OSError, ValueError, KeyError, TypeError):
        issues.append("verified render config identity unavailable")
    if placement.plane == "service" and runtime.get("configAck") != {"status": "ready"}:
        issues.append("service replica config ACK not ready")
    services = [item.get("composeService") for item in runtime.get("containers", [])]
    for service in placement.governed_services + placement.support_services:
        if services.count(service) != 1:
            issues.append(f"missing or duplicate governed runtime: {service}")
    return issues


def _prod_hosted_placement_coverage_checks(
    report_dir: Path,
    *,
    stage: str,
    candidate_digest: str,
    expected_plan: list,
    host: str = "",
    host_id: str = "",
) -> list[dict[str, Any]]:
    """逐一读取正式 inventory 的当前身份，缺项或重复一律阻断。"""
    import quwoquan_ops.cli.stackctl as _stackctl


    try:
        instance = _stackctl.prod_hosted_instance_for_stage(stage)
        access = _stackctl.load_prod_hosted_access_manifest()
        _stackctl.require_prod_hosted_release_inventory(expected_plan, access)
        plan = _stackctl.resolve_prod_hosted_plan(
            access, instance=instance, host_ids=[host_id] if host_id else None,
            ssh_host_override=host,
        )
        _stackctl.require_prod_hosted_release_inventory(plan, access)
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
    runtime_by_key: dict[tuple, list] = {}
    for runtime in runtimes:
        if isinstance(runtime, dict):
            key = (runtime.get("plane"), runtime.get("hostId"), runtime.get("replicaId"))
            runtime_by_key.setdefault(key, []).append(runtime)
    expected_keys = {(item.plane, item.host_id, item.replica_id) for item in plan}
    unexpected = set(runtime_by_key) - expected_keys
    checks: list[dict[str, Any]] = []
    for placement in plan:
        key = (placement.plane, placement.host_id, placement.replica_id)
        matches = runtime_by_key.get(key, [])
        runtime = matches[0] if len(matches) == 1 else None
        findings = (
            _stackctl._prod_plane_runtime_findings(runtime, plane=placement.plane)
            + _placement_identity_findings(runtime, placement, candidate_digest)
            if runtime is not None
            else [f"missing or duplicate runtime inspect for {key}"]
        )
        if unexpected:
            findings.append("unexpected runtime placement identity")
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
                "receiptDigest": "sha256:" + hashlib.sha256(
                    json.dumps(item["placementReceipt"], sort_keys=True).encode()
                ).hexdigest(),
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

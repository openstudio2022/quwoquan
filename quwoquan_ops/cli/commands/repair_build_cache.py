"""stackctl repair 构建缓存与输出布局修复域: 启动收据/租约/构建缓存审计、
builder 回收与 output layout reconciliation。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- 审计: `_startup_receipt_cache_audit` / `_consumer_lease_receipt_audit` /
  `_local_build_cache_runtime_audit` / `_command_result_evidence`;
- 构建缓存回收: `_run_build_cache_command` / `_parse_docker_size_bytes` /
  `_builder_prune_reclaimed_evidence` / `_finish_build_cache_reclaim` /
  `_repair_reclaim_build_cache`;
- 输出布局: `_output_layout_canonical_truth` / `_finish_output_layout_reconciliation` /
  `_canonical_output_layout_plan_ref` / `_repair_output_layout`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Mapping


def _startup_receipt_cache_audit(
    target_name: str,
    *,
    workload: str,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if workload == "aggregate":
        path = _stackctl.startup_attempt_path(target_name)
        payload = _stackctl.load_startup_attempt(target_name)
    else:
        path = _stackctl.startup_attempt_path_for_workload(target_name, workload)
        payload = _stackctl.load_workload_startup_attempt(target_name, workload)
    evidence: dict[str, Any] = {
        "workload": workload,
        "path": _stackctl.relpath(path),
        "state": "missing" if payload is None else "present",
        "sha256": _stackctl._sha256_file(path) if payload is not None else "",
        "status": "absent" if payload is None else str(payload.get("status") or ""),
        "attemptId": "" if payload is None else str(payload.get("attemptId") or ""),
        "candidateDigest": (
            "" if payload is None else str(payload.get("candidateDigest") or "")
        ),
        "failure": None if payload is None else payload.get("failure"),
        "cleanupFailure": None if payload is None else payload.get("cleanupFailure"),
    }
    return evidence


def _consumer_lease_receipt_audit() -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    directory = _stackctl.consumer_lease_dir()
    if not directory.exists():
        return []
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(
            f"consumer lease receipt root is unreadable: {directory}"
        )
    receipts: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"consumer lease receipt is unsafe: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"consumer lease receipt is unreadable: {path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"consumer lease receipt must be an object: {path}")
        target_name = str(payload.get("target") or "").strip()
        if target_name not in _stackctl.LOCAL_BUILD_CACHE_TARGETS:
            continue
        receipts.append(
            {
                "path": _stackctl.relpath(path),
                "sha256": _stackctl._sha256_file(path),
                "target": target_name,
                "leaseId": str(payload.get("leaseId") or ""),
                "consumer": str(payload.get("consumer") or ""),
                "device": str(payload.get("device") or ""),
            }
        )
    return receipts


def _local_build_cache_runtime_audit() -> dict[str, Any]:
    """Snapshot runtime facts under the global exclusive cache lock.

    Running attempts and ordinary App leases are deliberately report-only:
    BuildKit unused-cache GC does not delete containers, images, volumes, or
    runtime data. Unreadable canonical evidence still fails closed because the
    repair report would otherwise assert a snapshot that it could not prove.
    """
    import quwoquan_ops.cli.stackctl as _stackctl


    targets: list[dict[str, Any]] = []
    evidence_issues: list[str] = []
    runtime_anomalies: list[str] = []
    lease_receipts = _stackctl._consumer_lease_receipt_audit()
    for target_name in _stackctl.LOCAL_BUILD_CACHE_TARGETS:
        try:
            receipts = [
                _stackctl._startup_receipt_cache_audit(
                    target_name,
                    workload=workload,
                )
                for workload in (
                    "aggregate",
                    "full",
                    "content-release",
                    "content-commercial",
                )
            ]
            leases = _stackctl.active_consumer_leases(target_name)
            # BuildKit GC only removes unused build cache. Its runtime audit
            # must describe canonical port occupancy without requiring the
            # currently active Provider composition to match the workspace.
            # A stale candidate is precisely one reason a new package may be
            # needed, so coupling cache recovery to that identity deadlocks
            # package recovery after a no-space failure.
            ports = _stackctl._canonical_port_occupancy_report(target_name)
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"{target_name} runtime audit evidence is unreadable: {exc}"
            ) from exc
        for receipt in receipts:
            cleanup_failure = str(receipt.get("cleanupFailure") or "").strip()
            if cleanup_failure:
                issue = (
                    f"{target_name}/{receipt['workload']} "
                    f"cleanupFailure={cleanup_failure}"
                )
                runtime_anomalies.append(issue)
                evidence_issues.append(issue)
        targets.append(
            {
                "target": target_name,
                "startupReceipts": receipts,
                "consumerLeaseReceipts": [
                    item
                    for item in lease_receipts
                    if item["target"] == target_name
                ],
                "activeConsumerLeases": leases,
                "ports": ports,
            }
        )
    return {
        "targets": targets,
        "evidenceIssues": evidence_issues,
        "runtimeAnomalies": runtime_anomalies,
        "runningRuntimeBlocksCacheReclaim": False,
        "activeConsumerLeaseBlocksCacheReclaim": False,
    }


def _command_result_evidence(
    *,
    name: str,
    argv: list[str],
    result: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    stdout = str(result.stdout or "")
    stderr = str(result.stderr or "")
    return {
        "name": name,
        "argv": argv,
        "exitCode": int(result.returncode),
        "stdout": stdout,
        "stderr": stderr,
        "stdoutSha256": "sha256:" + hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "stderrSha256": "sha256:" + hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
    }


def _run_build_cache_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        return _stackctl.run(argv)
    except OSError as exc:
        return subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"Docker command could not start: {exc}",
        )


def _parse_docker_size_bytes(raw_value: str) -> int | None:
    match = re.fullmatch(
        r"\s*([0-9]+(?:\.[0-9]+)?)\s*(B|KB|MB|GB|TB)\s*",
        raw_value,
        re.IGNORECASE,
    )
    if match is None:
        return None
    multiplier = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
    }[match.group(2).upper()]
    return int(float(match.group(1)) * multiplier)


def _builder_prune_reclaimed_evidence(stdout: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    deleted_cache_ids: list[str] = []
    reclaimed_display = ""
    for raw_line in str(stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        total = re.match(r"^Total reclaimed space:\s*(.+)$", line, re.IGNORECASE)
        if total:
            reclaimed_display = total.group(1).strip()
            continue
        if line.lower().startswith(("cache id", "id ", "total")):
            continue
        candidate = line.split()[0]
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{5,}", candidate):
            deleted_cache_ids.append(candidate)
    reclaimed_bytes = _stackctl._parse_docker_size_bytes(reclaimed_display)
    return {
        "deletedCacheIds": sorted(set(deleted_cache_ids)),
        "deletedCacheIdentityEnumerable": bool(deleted_cache_ids),
        "reclaimedDisplay": reclaimed_display,
        "reclaimedBytes": reclaimed_bytes,
        "outcome": (
            "noop"
            if reclaimed_bytes == 0
            else "reclaimed"
            if reclaimed_display
            else "aggregate-not-reported"
        ),
    }


def _finish_build_cache_reclaim(
    *,
    report_dir: Path,
    report: dict[str, Any],
    status: str,
    summary: str,
    exit_code: int,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report["status"] = status
    _stackctl.write_json(report_dir / "report.json", report)
    _stackctl.write_json(
        report_dir / "repair_plan.json",
        {
            "fix": "reclaim-build-cache",
            "resourceScope": "docker_daemon_global",
            "targetScoped": False,
            "selection": "unused_build_cache_all",
            "affectedTargets": list(_stackctl.LOCAL_BUILD_CACHE_TARGETS),
            "actions": [
                {
                    "argv": ["docker", "builder", "prune", "--all", "--force"],
                    "deletes": "unused Docker builder cache only",
                    "preserves": ["containers", "images", "volumes", "runtime-data"],
                }
            ],
        },
    )
    details = list(report.get("resourceReleaseIssues") or []) or [
        "unused Docker builder cache is daemon-global; containers, images, "
        "volumes, and runtime data are preserved"
    ]
    _stackctl._write_summary_bundle(
        report_dir,
        command="repair",
        target=str(report["requestedTarget"]),
        status="ok" if exit_code == 0 else "failed",
        summary=summary,
        details=details,
    )
    return {
        "exitCode": exit_code,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
    }


def _repair_reclaim_build_cache(
    args: argparse.Namespace,
    *,
    report_dir: Path,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report: dict[str, Any] = {
        "schema": "stackctl-global-local-build-cache-reclaim",
        "command": "repair",
        "fix": "reclaim-build-cache",
        "requestedTarget": str(args.target),
        "affectedTargets": list(_stackctl.LOCAL_BUILD_CACHE_TARGETS),
        "resourceScope": "docker_daemon_global",
        "targetScoped": False,
        "selection": "unused_build_cache_all",
        "confirmation": bool(
            getattr(args, "confirm_global_build_cache_reclaim", False)
        ),
        "globalLock": None,
        "runtimeAudit": None,
        "dockerIdentity": None,
        "cacheInventory": {"before": None, "after": None},
        "prune": {
            "argv": ["docker", "builder", "prune", "--all", "--force"],
            "status": "not-run",
        },
        "cacheReclaimed": {
            "deletedCacheIds": [],
            "deletedCacheIdentityEnumerable": False,
            "reclaimedDisplay": "",
            "reclaimedBytes": None,
            "outcome": "not-run",
        },
        "preservedResourceClasses": [
            "containers",
            "images",
            "volumes",
            "runtime-data",
        ],
        "destructiveRepairPerformed": False,
        "destructiveActions": [],
        "resourceReleaseIssues": [],
    }
    if not report["confirmation"]:
        report["resourceReleaseIssues"].append(
            "--confirm-global-build-cache-reclaim is required before any Docker access"
        )
        return _stackctl._finish_build_cache_reclaim(
            report_dir=report_dir,
            report=report,
            status="gate_block",
            summary="global local Docker build cache reclaim is GATE_BLOCK",
            exit_code=2,
        )
    try:
        with _stackctl._global_local_build_cache_lock() as lock_evidence:
            report["globalLock"] = lock_evidence
            try:
                report["runtimeAudit"] = _stackctl._local_build_cache_runtime_audit()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                report["resourceReleaseIssues"].append(str(exc))
                return _stackctl._finish_build_cache_reclaim(
                    report_dir=report_dir,
                    report=report,
                    status="gate_block",
                    summary="global local Docker build cache audit is GATE_BLOCK",
                    exit_code=2,
                )

            identity_specs = (
                ("docker-context", ["docker", "context", "show"]),
                ("docker-daemon", ["docker", "info", "--format", "{{json .}}"]),
                ("docker-builders", ["docker", "builder", "ls", "--format", "json"]),
            )
            identity_steps: list[dict[str, Any]] = []
            for name, argv in identity_specs:
                result = _stackctl._run_build_cache_command(argv)
                evidence = _stackctl._command_result_evidence(
                    name=name,
                    argv=argv,
                    result=result,
                )
                identity_steps.append(evidence)
                if result.returncode != 0:
                    report["dockerIdentity"] = identity_steps
                    report["resourceReleaseIssues"].append(
                        result.stderr.strip()
                        or result.stdout.strip()
                        or f"{name} failed"
                    )
                    return _stackctl._finish_build_cache_reclaim(
                        report_dir=report_dir,
                        report=report,
                        status="gate_block",
                        summary="global local Docker build cache identity is GATE_BLOCK",
                        exit_code=2,
                    )
            report["dockerIdentity"] = identity_steps

            inventory_argv = ["docker", "system", "df"]
            before = _stackctl._run_build_cache_command(inventory_argv)
            report["cacheInventory"]["before"] = _stackctl._command_result_evidence(
                name="docker-build-cache-before",
                argv=inventory_argv,
                result=before,
            )
            # 容量耗尽有 typed 表达：清点失败但确认是容量耗尽时不能反过来
            # 阻断回收本身，否则唯一的恢复路径会在最需要它的时刻被关掉。
            preinventory_no_space = before.returncode != 0 and _stackctl.is_disk_exhausted(
                before.stderr, before.stdout
            )
            report["cacheInventory"]["preInventoryNoSpaceRecovery"] = (
                preinventory_no_space
            )
            report["cacheInventory"]["preInventoryBlocker"] = (
                _stackctl.CAPACITY_BLOCKER if preinventory_no_space else ""
            )
            if before.returncode != 0 and not preinventory_no_space:
                report["resourceReleaseIssues"].append(
                    before.stderr.strip()
                    or before.stdout.strip()
                    or "Docker build cache pre-inventory failed"
                )
                return _stackctl._finish_build_cache_reclaim(
                    report_dir=report_dir,
                    report=report,
                    status="gate_block",
                    summary="global local Docker build cache inventory is GATE_BLOCK",
                    exit_code=2,
                )

            prune_argv = ["docker", "builder", "prune", "--all", "--force"]
            report["destructiveRepairPerformed"] = True
            report["destructiveActions"] = [
                {
                    "argv": prune_argv,
                    "selection": "unused_build_cache_all",
                    "preservedResourceClasses": report["preservedResourceClasses"],
                }
            ]
            reclaim = _stackctl._run_build_cache_command(prune_argv)
            report["prune"] = _stackctl._command_result_evidence(
                name="docker-unused-build-cache-prune",
                argv=prune_argv,
                result=reclaim,
            )
            report["prune"]["status"] = (
                "passed" if reclaim.returncode == 0 else "failed"
            )
            report["cacheReclaimed"] = _stackctl._builder_prune_reclaimed_evidence(
                reclaim.stdout
            )

            after = _stackctl._run_build_cache_command(inventory_argv)
            report["cacheInventory"]["after"] = _stackctl._command_result_evidence(
                name="docker-build-cache-after",
                argv=inventory_argv,
                result=after,
            )
            if reclaim.returncode != 0:
                report["resourceReleaseIssues"].append(
                    reclaim.stderr.strip()
                    or reclaim.stdout.strip()
                    or "Docker builder prune failed"
                )
            if after.returncode != 0:
                report["resourceReleaseIssues"].append(
                    after.stderr.strip()
                    or after.stdout.strip()
                    or "Docker build cache post-inventory failed"
                )
            succeeded = reclaim.returncode == 0 and after.returncode == 0
            return _stackctl._finish_build_cache_reclaim(
                report_dir=report_dir,
                report=report,
                status="ok" if succeeded else "failed",
                summary=(
                    "global unused Docker build cache reclaimed"
                    if succeeded
                    else "global Docker build cache reclaim failed"
                ),
                exit_code=0 if succeeded else 1,
            )
    except RuntimeError as exc:
        report["resourceReleaseIssues"].append(str(exc))
        return _stackctl._finish_build_cache_reclaim(
            report_dir=report_dir,
            report=report,
            status="gate_block",
            summary="global local Docker build cache lock is GATE_BLOCK",
            exit_code=2,
        )


def _output_layout_canonical_truth() -> dict[str, dict[str, str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    paths = {
        "outputLayoutVerifier": _stackctl.ROOT / "quwoquan_ops/gate/verify_output_layout.py",
        "rootLayoutVerifier": _stackctl.ROOT / "quwoquan_ops/gate/verify_root_layout.py",
        "outputLayoutManifest": _stackctl.ROOT / "quwoquan_ops/environments/output_layout_manifest.yaml",
        "reconciliationPlanSchema": (
            _stackctl.ROOT
            / "quwoquan_ops/environments/output_layout_reconciliation_plan.schema.json"
        ),
    }
    return {
        name: {"path": _stackctl.relpath(path), "sha256": _stackctl._sha256_file(path)}
        for name, path in paths.items()
    }


def _finish_output_layout_reconciliation(
    *,
    report_dir: Path,
    status: str,
    summary: str,
    details: Sequence[str],
    report: Mapping[str, Any],
    exit_code: int,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    _stackctl.write_json(report_dir / "report.json", dict(report))
    _stackctl._write_summary_bundle(
        report_dir,
        command="repair",
        target="repo",
        status="ok" if exit_code == 0 else "failed",
        summary=summary,
        details=list(details),
    )
    return {
        "exitCode": exit_code,
        "summary": summary,
        "details": list(details),
        "reportDir": _stackctl.relpath(report_dir),
        "status": status,
    }


def _canonical_output_layout_plan_ref(value: str) -> Path:
    import quwoquan_ops.cli.stackctl as _stackctl

    requested = Path(value).expanduser()
    if not requested.is_absolute():
        requested = _stackctl.ROOT / requested
    requested = requested.absolute()
    try:
        resolved = requested.resolve(strict=True)
    except OSError as exc:
        raise _stackctl.output_layout_reconciliation.OutputLayoutReconciliationError(
            f"output reconciliation plan is unreadable: {exc}"
        ) from exc
    if requested != resolved:
        raise _stackctl.output_layout_reconciliation.OutputLayoutReconciliationError(
            "output reconciliation plan path must not contain symlinks or aliases"
        )
    allowed_root = _stackctl.repo_runs_root().resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise _stackctl.output_layout_reconciliation.OutputLayoutReconciliationError(
            "output reconciliation plan must remain below the canonical repo runs root"
        ) from exc
    return resolved


def _repair_output_layout(
    args: argparse.Namespace,
    *,
    report_dir: Path,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    action = str(getattr(args, "output_layout_action", "plan") or "plan")
    confirmation = bool(
        getattr(args, "confirm_output_layout_reconciliation", False)
    )
    plan_ref = str(getattr(args, "output_layout_plan_ref", "") or "").strip()
    base_report: dict[str, Any] = {
        "schema": "stackctl-output-layout-reconciliation",
        "command": "repair",
        "target": "repo",
        "fix": "reconcile-output-layout",
        "action": action,
        "status": "gate_block",
        "confirmation": confirmation,
        "globalLock": None,
        "planRef": plan_ref,
        "planDigest": "",
        "destructiveRepairPerformed": False,
        "destructiveActions": [],
        "excludedResourceClasses": _stackctl.output_layout_reconciliation.EXCLUDED_RESOURCE_CLASSES,
        "resourceReleaseIssues": [],
    }
    if action == "apply" and not confirmation:
        details = [
            "--confirm-output-layout-reconciliation is required before reading or applying a plan"
        ]
        base_report["resourceReleaseIssues"] = details
        return _stackctl._finish_output_layout_reconciliation(
            report_dir=report_dir,
            status="gate_block",
            summary="output layout reconciliation apply is GATE_BLOCK",
            details=details,
            report=base_report,
            exit_code=2,
        )
    if action == "apply" and not plan_ref:
        details = [
            "--output-layout-plan-ref is required for output layout apply"
        ]
        base_report["resourceReleaseIssues"] = details
        return _stackctl._finish_output_layout_reconciliation(
            report_dir=report_dir,
            status="gate_block",
            summary="output layout reconciliation apply is GATE_BLOCK",
            details=details,
            report=base_report,
            exit_code=2,
        )
    if action == "plan" and (plan_ref or confirmation):
        details = [
            "plan mode does not accept an existing plan ref or apply confirmation"
        ]
        base_report["resourceReleaseIssues"] = details
        return _stackctl._finish_output_layout_reconciliation(
            report_dir=report_dir,
            status="gate_block",
            summary="output layout reconciliation plan is GATE_BLOCK",
            details=details,
            report=base_report,
            exit_code=2,
        )

    try:
        with _stackctl._global_output_layout_reconciliation_lock() as lock_evidence:
            base_report["globalLock"] = lock_evidence
            truth = _stackctl._output_layout_canonical_truth()
            from quwoquan_ops.gate.verify_root_layout import root_layout_issues

            issues = root_layout_issues(_stackctl.ROOT)
            if action == "plan":
                plan = _stackctl.output_layout_reconciliation.build_plan(
                    repository_root=_stackctl.ROOT,
                    output_root=_stackctl.output_root(),
                    canonical_issues=issues,
                    truth=truth,
                )
                plan_path = report_dir / _stackctl.output_layout_reconciliation.PLAN_FILENAME
                _stackctl.output_layout_reconciliation.write_create_once(plan_path, plan)
                blocked = plan["status"] != "ready"
                details = [
                    f"immutablePlan={_stackctl.relpath(plan_path)}",
                    f"planDigest={plan['planDigest']}",
                    f"canonicalIssues={plan['canonicalIssueCount']}",
                    f"records={len(plan['records'])}",
                    f"actions={plan['actionCount']}",
                ]
                if blocked:
                    details.append(f"blockers={len(plan['blockers'])}")
                base_report.update(
                    {
                        "status": "gate_block" if blocked else "passed",
                        "planRef": _stackctl.relpath(plan_path),
                        "planDigest": plan["planDigest"],
                        "planStatus": plan["status"],
                        "canonicalIssueCount": plan["canonicalIssueCount"],
                        "recordCount": len(plan["records"]),
                        "actionCount": plan["actionCount"],
                        "resourceReleaseIssues": plan["blockers"],
                    }
                )
                return _stackctl._finish_output_layout_reconciliation(
                    report_dir=report_dir,
                    status=str(base_report["status"]),
                    summary=(
                        "output layout reconciliation plan is GATE_BLOCK"
                        if blocked
                        else "output layout reconciliation plan is ready"
                    ),
                    details=details,
                    report=base_report,
                    exit_code=2 if blocked else 0,
                )

            canonical_plan_path = _stackctl._canonical_output_layout_plan_ref(plan_ref)
            plan = _stackctl.output_layout_reconciliation.load_plan(canonical_plan_path)
            current_issue_digest = _stackctl.output_layout_reconciliation.canonical_digest(
                sorted(str(issue) for issue in issues)
            )
            same_findings = (
                int(plan.get("canonicalIssueCount") or -1) == len(issues)
                and plan.get("canonicalIssueDigest") == current_issue_digest
            )
            current_fingerprints = (
                _stackctl.output_layout_reconciliation.canonical_issue_fingerprints(
                    issues,
                    repository_root=_stackctl.ROOT,
                )
            )
            planned_fingerprints = (
                _stackctl.output_layout_reconciliation.plan_issue_fingerprints(plan)
            )
            if not same_findings and not current_fingerprints.issubset(
                planned_fingerprints
            ):
                raise _stackctl.output_layout_reconciliation.OutputLayoutReconciliationError(
                    "canonical root/output findings added facts outside immutable plan"
                )
            journal = {
                "schema": "stackctl-output-layout-reconciliation-journal",
                "createdAt": _stackctl.utc_now(),
                "status": "prepared",
                "planRef": _stackctl.relpath(canonical_plan_path),
                "planDigest": plan["planDigest"],
                "actions": [
                    {
                        "from": record["path"],
                        "to": record["canonicalDestination"],
                    }
                    for record in plan["records"]
                    if record.get("action") is True
                ],
            }
            _stackctl.output_layout_reconciliation.write_create_once(
                report_dir / "output-layout-reconciliation-journal.json",
                journal,
            )
            result = _stackctl.output_layout_reconciliation.apply_plan(
                plan,
                repository_root=_stackctl.ROOT,
                output_root=_stackctl.output_root(),
                truth=truth,
            )
            details = [
                f"planDigest={plan['planDigest']}",
                f"moved={len(result['moved'])}",
                f"noOp={str(result['noOp']).lower()}",
                "all moves passed source/destination readback; rollback remains path-exact",
            ]
            base_report.update(
                {
                    "status": "passed",
                    "planRef": _stackctl.relpath(canonical_plan_path),
                    "planDigest": plan["planDigest"],
                "noOp": result["noOp"],
                "replayed": result["replayed"],
                "moved": result["moved"],
                "readBack": result["readBack"],
                    "rollbackAvailable": result["rollbackAvailable"],
                    "destructiveRepairPerformed": bool(result["moved"]),
                    "destructiveActions": result["moved"],
                }
            )
            return _stackctl._finish_output_layout_reconciliation(
                report_dir=report_dir,
                status="passed",
                summary="output layout reconciliation apply passed",
                details=details,
                report=base_report,
                exit_code=0,
            )
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        details = [str(exc)]
        base_report["resourceReleaseIssues"] = details
        return _stackctl._finish_output_layout_reconciliation(
            report_dir=report_dir,
            status="gate_block",
            summary=f"output layout reconciliation {action} is GATE_BLOCK",
            details=details,
            report=base_report,
            exit_code=2,
        )

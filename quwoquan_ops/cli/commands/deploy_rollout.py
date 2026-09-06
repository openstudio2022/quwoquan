"""stackctl deploy rollout 执行域: `_command_deploy_with_lock` 主体。

从 stackctl.py 逐字迁出: prod-hosted 准入/镜像传输/嵌套命令执行/
post-deploy checks 与报告聚合; prod-hosted 收尾委托
`commands/deploy_prod_finalize.py` 的 `_deploy_prod_hosted_finalize`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time

from pathlib import Path
from typing import Any


def _command_deploy_with_lock(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, "prod" if args.target == "prod-hosted" else "gamma", args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    post_deploy_checks: list[dict[str, Any]] = []
    rollback_post_checks: list[dict[str, Any]] = []
    deploy_result: Any | None = None
    rollback_result: Any | None = None
    rollback_started_at = ""
    rollback_ended_at = ""
    rollback_duration_ms = 0
    rollback_deadline_epoch = 0
    rollback_reason = ""
    rollback_state: dict[str, str] | None = None
    force_deadline_rollback = False
    error: Exception | None = None
    item: dict[str, Any] = {}
    nested_args: argparse.Namespace | None = None
    nested_command = ""
    nested_dir = report_dir
    nested_scope = ""
    rollout_decision = "continue"
    rollout_stage = ""
    dry_run_requested = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    slo_readback: dict[str, Any] | None = None
    prometheus_url = ""
    service_factory_material_path: Path | None = None
    candidate_material_id = ""
    deploy_material: dict[str, Any] = {}
    expected_generation = 0
    transition_action = "advance"
    release_receipt_id = ""
    committed_release_state: dict[str, str] | None = None
    release_receipt_path: Path | None = None
    release_state_snapshot: dict[str, str] = {}
    release_candidate_digests: dict[str, str] = {}
    prod_activation_admission: dict[str, str] = {}
    from_service_factory_oci_digest = ""
    to_service_factory_oci_digest = ""
    from_app_factory_oci_digest = ""
    to_app_factory_oci_digest = ""
    last_good_candidate_digest = ""
    rollout_canary_contract: dict[str, Any] | None = None
    rollout_canary_traffic: dict[str, Any] | None = None
    promotion_observation: dict[str, Any] | None = None
    promotion_evidence: dict[str, Any] | None = None
    provider_readiness: dict[str, Any] = {}
    promotion_deadline_epoch = int(
        getattr(args, "promotion_deadline_epoch", 0) or 0
    )
    hard_deadline_epoch = int(getattr(args, "hard_deadline_epoch", 0) or 0)
    rollback_budget_seconds = int(
        getattr(args, "rollback_budget_seconds", 300) or 0
    )
    if args.target == "prod-hosted":
        try:
            rollout_stage = _stackctl._resolve_prod_rollout_stage(args.step, args.stage)
        except ValueError as error:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": f"stackctl deploy rollout stage invalid: {error}",
                "details": [],
                **timing,
            }
        try:
            release_plan = _stackctl.resolve_prod_hosted_plan(
                _stackctl.load_prod_hosted_access_manifest(),
                instance=_stackctl.prod_hosted_instance_for_stage(rollout_stage),
                host_ids=getattr(args, "host_id", None) or None,
                ssh_host_override=str(getattr(args, "ssh_host", "") or ""),
            )
            _stackctl.require_prod_hosted_release_redundancy(release_plan)
        except _stackctl.ProdHostedTopologyError as error:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: prod-hosted inventory is not release-ready",
                "details": [str(error)],
                **timing,
            }
        if rollout_stage == "canary":
            provider_preflight = _stackctl._run_provider_readiness_preflight("prod", report_dir)
            provider_readiness = provider_preflight["report"]
            if provider_preflight["exitCode"] != 0:
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                payload = {
                    "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
                    "command": "deploy",
                    "target": args.target,
                    "rolloutStage": rollout_stage,
                    "providerReadiness": provider_readiness,
                    "steps": [
                        {
                            "kind": provider_preflight["kind"],
                            "environment": "prod",
                            "argv": provider_preflight["argv"],
                            "exitCode": provider_preflight["exitCode"],
                            "reportPath": provider_preflight["reportPath"],
                            "details": provider_preflight["details"],
                        }
                    ],
                    **timing,
                }
                _stackctl.write_json(report_dir / "report.json", payload)
                _stackctl.write_json(
                    report_dir / "findings.json",
                    {"target": args.target, "issues": provider_preflight["details"]},
                )
                _stackctl._write_summary_bundle(
                    report_dir,
                    command="deploy",
                    target=args.target,
                    status="blocked",
                    summary="stackctl deploy is GATE_BLOCK by Provider readiness",
                    details=provider_preflight["details"],
                    timing=timing,
                )
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy is GATE_BLOCK by Provider readiness",
                    "details": provider_preflight["details"],
                    "reportDir": _stackctl.relpath(report_dir),
                    **timing,
                }
        prometheus_url = str(
            getattr(args, "prometheus_url", "")
            or os.environ.get("PROMETHEUS_URL", "")
        ).strip()
        if not dry_run_requested and (
            promotion_deadline_epoch <= 0
            or hard_deadline_epoch <= promotion_deadline_epoch
            or rollback_budget_seconds <= 0
            or hard_deadline_epoch - promotion_deadline_epoch
            < rollback_budget_seconds
        ):
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: canonical Prod deadlines are required",
                "details": [],
                **timing,
            }
        if not dry_run_requested and not prometheus_url:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: non-dry-run prod rollout requires PROMETHEUS_URL readback",
                "details": [],
                **timing,
            }
        if not dry_run_requested:
            try:
                rollout_canary_contract = _stackctl._prod_rollout_contract(
                    rollout_stage,
                    expected_candidate_digest=str(args.to_candidate_digest or "").strip(),
                )
            except RuntimeError as error:
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: rollout contract is invalid",
                    "details": [str(error)],
                    **timing,
                }
        prod_activation_input = str(
            getattr(args, "prod_activation_admission", "") or ""
        ).strip()
        if not dry_run_requested and not prod_activation_input:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: canonical ProdActivationAdmissionFact input is required",
                "details": ["provide exact materialized --prod-activation-admission envelope"],
                **timing,
            }
        required = [args.service, args.step, prod_activation_input]
        if not all(required):
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy prod-hosted requires service, step and exact activation authority",
                "details": [],
                **timing,
            }
        try:
            (
                prod_activation_admission,
                service_factory_material_path,
                candidate_material_id,
                deploy_material,
            ) = _stackctl._load_prod_activation_admission(prod_activation_input)
            args.from_candidate_digest = prod_activation_admission["previousCandidateDigest"]
            args.to_candidate_digest = prod_activation_admission["candidateDigest"]
            for label, value in (
                ("previous candidate", args.from_candidate_digest),
                ("candidate", args.to_candidate_digest),
            ):
                if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                    raise RuntimeError(f"{label} digest is invalid")
            if not dry_run_requested:
                evidence_path_value = str(
                    getattr(args, "promotion_evidence", "") or ""
                ).strip()
                evidence_root_value = str(
                    os.environ.get("QWQ_PROD_ROLLOUT_EVIDENCE_ROOT", "")
                ).strip()
                if not evidence_path_value or not evidence_root_value:
                    raise RuntimeError(
                        "protected rollout promotion evidence path/root is required"
                    )
                if rollout_canary_contract is None:
                    raise RuntimeError("production rollout contract was not loaded")
                promotion_observation = (
                    _stackctl.rollout_stage_promotion_evidence.load_protected_observation(
                        Path(evidence_path_value),
                        trusted_root=Path(evidence_root_value),
                    )
                )
                promotion_evidence = (
                    _stackctl.rollout_stage_promotion_evidence.validate_observation(
                        promotion_observation,
                        candidate_id=str(
                            deploy_material.get("candidateId") or ""
                        ),
                        artifact_digest=candidate_material_id,
                        campaign_id=str(rollout_canary_contract["campaignId"]),
                        routing_policy_digest=str(
                            rollout_canary_contract["routingPolicyDigest"]
                        ),
                        stage=rollout_stage,
                        stage_policy=rollout_canary_contract,
                        actual_synthetic_requests=(
                            None if rollout_stage == "canary" else 0
                        ),
                    )
                )
            if not dry_run_requested:
                release_candidate_digests = _stackctl._required_release_candidate_digests(
                    args,
                    deploy_material,
                )
            release_state_snapshot, _ = _stackctl._fetch_hosted_release_ledger_projection(
                args.service,
                allow_uninitialized=False,
                deadline_epoch=promotion_deadline_epoch,
            )
            to_service_factory_oci_digest = prod_activation_admission[
                "serviceFactoryOciDigest"
            ]
            to_app_factory_oci_digest = prod_activation_admission[
                "appFactoryOciDigest"
            ]
            if release_state_snapshot.get("to_candidate_digest") == args.to_candidate_digest:
                restored_candidate_noop = (
                    release_state_snapshot.get("decision") == "rolled_back"
                    and args.from_candidate_digest == args.to_candidate_digest
                )
                from_service_factory_oci_digest = release_state_snapshot.get(
                    "to_service_factory_oci_digest"
                    if restored_candidate_noop
                    else "from_service_factory_oci_digest",
                    "",
                )
                from_app_factory_oci_digest = release_state_snapshot.get(
                    "to_app_factory_oci_digest"
                    if restored_candidate_noop
                    else "from_app_factory_oci_digest",
                    "",
                )
                if (
                    release_state_snapshot.get("to_service_factory_oci_digest")
                    != to_service_factory_oci_digest
                    or release_state_snapshot.get("to_app_factory_oci_digest")
                    != to_app_factory_oci_digest
                ):
                    raise RuntimeError(
                        "hosted ledger target factory closure does not match resume candidate"
                    )
            else:
                from_service_factory_oci_digest = release_state_snapshot.get(
                    "to_service_factory_oci_digest", ""
                )
                from_app_factory_oci_digest = release_state_snapshot.get(
                    "to_app_factory_oci_digest", ""
                )
            for label, value in (
                ("source service factory OCI", from_service_factory_oci_digest),
                ("source app factory OCI", from_app_factory_oci_digest),
            ):
                if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                    raise RuntimeError(
                        f"hosted ledger lacks exact {label} digest; historical cutover is required"
                    )
            last_good_candidate_digest = release_state_snapshot.get(
                "last_good_candidate_digest",
                args.from_candidate_digest,
            )
            transition_action, expected_generation = _stackctl._validate_release_transition(
                release_state_snapshot,
                from_candidate_digest=args.from_candidate_digest,
                to_candidate_digest=args.to_candidate_digest,
                stage=rollout_stage,
                prod_activation_admission_payload_digest=prod_activation_admission.get(
                    "prodActivationAdmissionPayloadDigest", ""
                ),
            )

        except RuntimeError as error:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: activation authority or ledger validation failed",
                "details": [str(error)],
                **timing,
            }
        release_receipt_id = hashlib.sha256(
            (
                f"{args.service}\0{candidate_material_id}\0{rollout_stage}\0"
                f"{prod_activation_admission.get('prodActivationAdmissionPayloadDigest', '')}\0"
                f"{prod_activation_admission.get('releaseTagAdmissionDigest', '')}\0"
                f"{prod_activation_admission.get('qualificationDigest', '')}\0"
                f"{prod_activation_admission.get('previousReleasedPayloadDigest', '')}\0"
                f"{expected_generation + (0 if transition_action == 'replay' else 1)}"
            ).encode("utf-8")
        ).hexdigest()
        if transition_action == "replay" and not dry_run_requested:
            release_receipt_id = release_state_snapshot.get("receipt_id", "")
            if not release_receipt_id:
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: hosted ledger receipt identity is missing",
                    "details": [],
                    **timing,
                }
            try:
                # Recovery must be reconstructable from the hosted authority.
                # A disposable local receipt from an earlier runner is never a
                # prerequisite for replay.
                release_receipt_path = _stackctl._sync_release_ledger_projection(
                    args.service,
                    release_receipt_id,
                    deadline_epoch=promotion_deadline_epoch,
                )
            except RuntimeError as error:
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy replay could not sync release projection",
                    "details": [str(error)],
                    **timing,
                }
            hosted_receipt = _stackctl._read_json_object(str(release_receipt_path))
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            replay_payload = {
                "command": "deploy",
                "target": args.target,
                "argv": [],
                "exitCode": 0,
                "stdout": "hosted release ledger replay matched",
                "stderr": "",
                "rolloutStage": rollout_stage,
                "rolloutDecision": hosted_receipt.get("decision"),
                "candidateMaterialId": candidate_material_id,
                "candidateId": deploy_material.get("candidateId"),
                "releaseReceiptId": release_receipt_id,
                "releaseReceiptRef": f"receipt:hosted:{release_receipt_id}",
                "releaseReceiptAuthority": "prod-hosted-service-plane",
                "hostedReceipt": hosted_receipt,
                "hostedStageReceipt": {
                    "ref": f"receipt:hosted:{release_receipt_id}",
                    "receiptId": release_receipt_id,
                    "authority": "prod-hosted-service-plane",
                },
                "releaseState": release_state_snapshot,
                "prodActivationAdmission": prod_activation_admission,
                "releaseEligibility": "eligible",
                "wiredWorkloads": _stackctl._prod_rollout_workloads(),
                "providerReadiness": provider_readiness,
                "postDeployChecks": [],
                "postDeployFailures": [],
                "rollbackPostChecks": [],
                "sloReadback": hosted_receipt.get("sloReadback") or {},
                "dryRun": False,
                "replayed": True,
                "rollback": {"triggered": False, "reason": "", "result": {}, "releaseState": {}},
                **timing,
            }
            _stackctl.write_json(report_dir / "report.json", replay_payload)
            return {
                "exitCode": 0,
                "summary": "stackctl deploy replay matched committed release ledger",
                "details": [f"receipt: {release_receipt_id}"],
                "releaseReceiptId": release_receipt_id,
                **timing,
            }
        if not dry_run_requested:
            try:
                _stackctl._remaining_deadline_seconds(
                    promotion_deadline_epoch, "Prod promotion cutoff"
                )
            except RuntimeError as error:
                active_candidate = (
                    release_state_snapshot.get("to_candidate_digest")
                    == args.to_candidate_digest
                    and release_state_snapshot.get("last_good_candidate_digest")
                    == args.from_candidate_digest
                    and release_state_snapshot.get("stage")
                    in {"canary", "5", "20", "50"}
                )
                if active_candidate:
                    force_deadline_rollback = True
                else:
                    timing = _stackctl._finish_timing(started_monotonic, started_at)
                    return {
                        "exitCode": 2,
                        "summary": "stackctl deploy blocked: promotion cutoff reached before mutation",
                        "details": [str(error)],
                        **timing,
                    }
        try:
            package_binding = _stackctl._materialize_release_evidence_configuration(
                "prod", target=args.target
            )
            if package_binding.get("candidateId") != args.to_candidate_digest:
                raise ValueError(
                    "fixed prod package does not bind the rollout candidate"
                )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: fixed prod package is invalid",
                "details": [str(error)],
                **timing,
            }
        cmd: list[str] = []
        if force_deadline_rollback:
            deploy_result = subprocess.CompletedProcess(
                ["prod-apply"],
                0,
                stdout="promotion cutoff reached while a candidate stage is active",
                stderr="",
            )
            result = subprocess.CompletedProcess(
                ["promotion-deadline"],
                12,
                stdout="decision=rollback",
                stderr="promotion cutoff reached; reserved time is now rollback-only",
            )
        elif transition_action == "reevaluate" and not dry_run_requested:
            deploy_result = subprocess.CompletedProcess(
                ["prod-apply"],
                0,
                stdout="paused hosted stage re-evaluation reused the existing apply",
                stderr="",
            )
        else:
            try:
                apply_timeout = (
                    _stackctl._remaining_deadline_seconds(
                        promotion_deadline_epoch, "Prod promotion cutoff"
                    )
                    if not dry_run_requested
                    else None
                )
            except RuntimeError as error:
                apply_timeout = 0.001
            deploy_result = _stackctl.run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                env={
                    # PROD_SSH_HOST identifies the hosted ledger authority for
                    # surrounding calls. Deployment placement must remain
                    # access-isolation policy driven across every host/replica.
                    "PROD_SSH_HOST": "",
                    "CLOUD_PROVIDER": args.cloud_provider,
                    "SERVICE": args.service,
                    "CANDIDATE_DIGEST": args.to_candidate_digest,
                    "PREVIOUS_CANDIDATE_DIGEST": args.from_candidate_digest,
                    "ROLLOUT_STAGE": rollout_stage,
                    "DRY_RUN": args.dry_run,
                    "SERVICE_FACTORY_MATERIAL": str(service_factory_material_path),
                    "CANDIDATE_MATERIAL_ID": candidate_material_id,
                    "PROD_ACTIVATION_ADMISSION_DIGEST": prod_activation_admission[
                        "prodActivationAdmissionPayloadDigest"
                    ],
                },
                timeout_seconds=apply_timeout,
            )
        if force_deadline_rollback:
            pass
        elif deploy_result.returncode != 0:
            result = subprocess.CompletedProcess(
                ["prod-apply"],
                deploy_result.returncode,
                stdout="decision=rollback",
                stderr=(
                    "production apply failed; stackctl will rollback every plane: "
                    + (deploy_result.stderr.strip() or deploy_result.stdout.strip())
                ),
            )
        elif dry_run_requested:
            result = subprocess.CompletedProcess(
                cmd,
                0,
                stdout="prod dry-run skipped config_release_apply_stage.sh and remained read-only",
                stderr="",
            )
        else:
            try:
                if rollout_canary_contract is None:
                    raise RuntimeError("Prod rollout canary contract was not loaded")
                rollout_canary_traffic = _stackctl._emit_prod_rollout_canary_traffic(
                    rollout_canary_contract,
                    deadline_epoch=promotion_deadline_epoch,
                )
                if rollout_stage == "canary":
                    if promotion_observation is None:
                        raise RuntimeError(
                            "protected rollout promotion observation was not loaded"
                        )
                    promotion_evidence = (
                        _stackctl.rollout_stage_promotion_evidence.validate_observation(
                            promotion_observation,
                            candidate_id=str(
                                deploy_material.get("candidateId") or ""
                            ),
                            artifact_digest=candidate_material_id,
                            campaign_id=str(rollout_canary_contract["campaignId"]),
                            routing_policy_digest=str(
                                rollout_canary_contract["routingPolicyDigest"]
                            ),
                            stage=rollout_stage,
                            stage_policy=rollout_canary_contract,
                            actual_synthetic_requests=int(
                                rollout_canary_traffic.get("requests") or 0
                            ),
                        )
                    )
                settle_seconds = _stackctl._slo_settle_seconds(rollout_stage)
                if settle_seconds:
                    remaining = _stackctl._remaining_deadline_seconds(
                        promotion_deadline_epoch, "Prod promotion cutoff"
                    )
                    if settle_seconds >= remaining:
                        raise RuntimeError(
                            "SLO settle interval would cross the Prod promotion cutoff"
                        )
                    time.sleep(settle_seconds)
                slo_service = (
                    "content-service"
                    if args.service == _stackctl.PROD_RELEASE_UNIT
                    else args.service
                )
                slo_readback = _stackctl._read_prometheus_slo(
                    prometheus_url,
                    slo_service,
                    deadline_epoch=promotion_deadline_epoch,
                )
                slo_readback["canaryTraffic"] = rollout_canary_traffic
            except _stackctl._SloSamplesInsufficient as error:
                slo_readback = {
                    "canaryTraffic": rollout_canary_traffic or {},
                    "status": "insufficient_samples",
                    "error": str(error),
                }
                result = subprocess.CompletedProcess(
                    ["prometheus-slo-readback"],
                    10,
                    stdout="decision=pause reason=insufficient_samples",
                    stderr=str(error),
                )
            except RuntimeError as error:
                slo_readback = {
                    "canaryTraffic": rollout_canary_traffic or {},
                    "error": str(error),
                }
                result = subprocess.CompletedProcess(
                    ["prometheus-slo-readback"],
                    11,
                    stdout="decision=rollback",
                    stderr=str(error),
                )
            else:
                args.error_rate = str(slo_readback["values"]["errorRate"])
                args.p95_ms = str(slo_readback["values"]["p95Ms"])
                args.redis_error_rate = str(slo_readback["values"]["redisErrorRate"])
                cmd = [
                    "bash",
                    "quwoquan_ops/cli/prod/config_release_apply_stage.sh",
                    "--service",
                    args.service,
                    "--step",
                    args.step,
                    "--error-rate",
                    args.error_rate,
                    "--p95-ms",
                    args.p95_ms,
                    "--redis-error-rate",
                    args.redis_error_rate,
                ]
                try:
                    gate_timeout = _stackctl._remaining_deadline_seconds(
                        promotion_deadline_epoch, "Prod promotion cutoff"
                    )
                except RuntimeError as error:
                    result = subprocess.CompletedProcess(
                        cmd,
                        12,
                        stdout="decision=rollback",
                        stderr=str(error),
                    )
                else:
                    gate_result = _stackctl.run(cmd, timeout_seconds=gate_timeout)
                    result = (
                        gate_result
                        if gate_result.returncode == 0
                        else subprocess.CompletedProcess(
                            gate_result.args,
                            gate_result.returncode,
                            stdout="decision=rollback\n" + gate_result.stdout,
                            stderr=gate_result.stderr,
                        )
                    )
            if slo_readback is not None and promotion_evidence is not None:
                slo_readback["promotionEvidence"] = promotion_evidence
    run_post_deploy_checks = result.returncode == 0 and not (
        args.target == "prod-hosted" and dry_run_requested
    )
    if run_post_deploy_checks:
        def _deploy_health_args(
            target_name: str,
            scope_name: str,
            out_dir: Path,
            *,
            deadline_epoch: int,
        ) -> argparse.Namespace:
            return argparse.Namespace(
                command="health",
                target=target_name,
                scope=scope_name,
                output_format="json",
                report_dir=str(out_dir),
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
                deadline_epoch=deadline_epoch,
            )

        for nested_command, nested_scope in (("health", "full"),):
            nested_dir = report_dir / nested_command
            if nested_command == "health":
                nested_args = _deploy_health_args(
                    args.target,
                    nested_scope,
                    nested_dir,
                    deadline_epoch=promotion_deadline_epoch,
                )
                post_deploy_checks.append(_stackctl.command_health(nested_args))
        if args.target == "prod-hosted" and rollout_stage == "canary":
            nested_dir = report_dir / "environment-page-smoke"
            verify_command = [
                "python3",
                "quwoquan_ops/cli/stackctl.py",
                "verify",
                "--target",
                args.target,
                "--kind",
                "topology",
                "--profile",
                "release",
                "--report-dir",
                str(nested_dir),
                "--output-format",
                "json",
            ]
            verify_result = _stackctl.run(
                verify_command,
                timeout_seconds=_stackctl._remaining_deadline_seconds(
                    promotion_deadline_epoch,
                    "Prod release environment verification",
                ),
            )
            try:
                verify_payload = json.loads(verify_result.stdout)
            except json.JSONDecodeError:
                verify_payload = {
                    "exitCode": verify_result.returncode,
                    "summary": "bounded Prod release environment verification failed",
                    "details": _stackctl._command_details(verify_result),
                }
            post_deploy_checks.append(verify_payload)
        if args.target == "prod-hosted":
            post_deploy_checks.extend(
                _stackctl._prod_hosted_placement_coverage_checks(
                    report_dir,
                    stage=rollout_stage,
                    host=str(getattr(args, "ssh_host", "") or ""),
                    host_id=(
                        str((getattr(args, "host_id", None) or [""])[0])
                        if isinstance(getattr(args, "host_id", None), list)
                        else str(getattr(args, "host_id", "") or "")
                    ),
                )
            )
    post_deploy_failures = [
        item["summary"]
        for item in post_deploy_checks
        if not _stackctl._check_exit_passed(item)
    ]
    final_exit_code = result.returncode
    findings = list(post_deploy_failures)
    if final_exit_code == 0 and post_deploy_failures:
        final_exit_code = 1
    if (
        args.target == "prod-hosted"
        and not dry_run_requested
        and final_exit_code == 0
    ):
        try:
            _stackctl._remaining_deadline_seconds(
                promotion_deadline_epoch, "Prod promotion cutoff"
            )
        except RuntimeError as error:
            result = subprocess.CompletedProcess(
                result.args,
                12,
                stdout="decision=rollback\n" + (result.stdout or ""),
                stderr="\n".join(filter(None, [result.stderr, str(error)])),
            )
            final_exit_code = 12
    if args.target == "prod-hosted":
        _finalize_scope = {
            "args": args,
            "committed_release_state": committed_release_state,
            "dry_run_requested": dry_run_requested,
            "error": error,
            "expected_generation": expected_generation,
            "final_exit_code": final_exit_code,
            "findings": findings,
            "from_service_factory_oci_digest": from_service_factory_oci_digest,
            "from_app_factory_oci_digest": from_app_factory_oci_digest,
            "hard_deadline_epoch": hard_deadline_epoch,
            "item": item,
            "last_good_candidate_digest": last_good_candidate_digest,
            "nested_args": nested_args,
            "nested_command": nested_command,
            "nested_dir": nested_dir,
            "nested_scope": nested_scope,
            "post_deploy_checks": post_deploy_checks,
            "post_deploy_failures": post_deploy_failures,
            "promotion_deadline_epoch": promotion_deadline_epoch,
            "candidate_material_id": candidate_material_id,
            "release_candidate_digests": release_candidate_digests,
            "prod_activation_admission": prod_activation_admission,
            "release_receipt_id": release_receipt_id,
            "release_receipt_path": release_receipt_path,
            "report_dir": report_dir,
            "result": result,
            "rollback_budget_seconds": rollback_budget_seconds,
            "rollback_deadline_epoch": rollback_deadline_epoch,
            "rollback_duration_ms": rollback_duration_ms,
            "rollback_ended_at": rollback_ended_at,
            "rollback_post_checks": rollback_post_checks,
            "rollback_reason": rollback_reason,
            "rollback_result": rollback_result,
            "rollback_started_at": rollback_started_at,
            "rollback_state": rollback_state,
            "rollout_decision": rollout_decision,
            "rollout_stage": rollout_stage,
            "slo_readback": slo_readback,
            "to_service_factory_oci_digest": to_service_factory_oci_digest,
            "to_app_factory_oci_digest": to_app_factory_oci_digest,
        }
        _finalize_outputs = _stackctl._deploy_prod_hosted_finalize(_finalize_scope)
        committed_release_state = _finalize_outputs["committed_release_state"]
        final_exit_code = _finalize_outputs["final_exit_code"]
        item = _finalize_outputs["item"]
        release_receipt_id = _finalize_outputs["release_receipt_id"]
        release_receipt_path = _finalize_outputs["release_receipt_path"]
        rollback_duration_ms = _finalize_outputs["rollback_duration_ms"]
        rollback_ended_at = _finalize_outputs["rollback_ended_at"]
        rollback_reason = _finalize_outputs["rollback_reason"]
        rollback_result = _finalize_outputs["rollback_result"]
        rollback_started_at = _finalize_outputs["rollback_started_at"]
        rollback_state = _finalize_outputs["rollback_state"]
        rollout_decision = _finalize_outputs["rollout_decision"]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "deploy",
            "target": args.target,
            "argv": cmd,
            "exitCode": final_exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "rolloutStage": rollout_stage,
            "triggerStage": (
                (committed_release_state or {}).get("trigger_stage")
                or rollout_stage
            ),
            "terminalStage": (
                (committed_release_state or {}).get("stage")
                or rollout_stage
            ),
            "rolloutDecision": rollout_decision,
            "candidateMaterialId": candidate_material_id,
            "candidateId": (
                deploy_material.get("candidateId")
                if deploy_material
                else ""
            ),
            "releaseReceiptId": release_receipt_id,
            "releaseReceiptRef": (
                f"receipt:hosted:{release_receipt_id}"
                if release_receipt_path is not None and release_receipt_id
                else ""
            ),
            "releaseReceiptAuthority": (
                "prod-hosted-service-plane"
                if release_receipt_path is not None
                else ""
            ),
            "hostedReceipt": (
                _stackctl.load_json_yaml(release_receipt_path)
                if release_receipt_path is not None
                else {}
            ),
            "hostedStageReceipt": (
                {
                    "ref": f"receipt:hosted:{release_receipt_id}",
                    "receiptId": release_receipt_id,
                    "authority": "prod-hosted-service-plane",
                }
                if release_receipt_path is not None and release_receipt_id
                else {}
            ),
            "releaseState": committed_release_state or {},
            "prodActivationAdmission": prod_activation_admission,
            "releaseEligibility": (
                "non-eligible"
                if dry_run_requested
                else ("eligible" if prod_activation_admission else "blocked")
            ),
            "wiredWorkloads": _stackctl._prod_rollout_workloads() if args.target == "prod-hosted" else [],
            "providerReadiness": provider_readiness,
            "postDeployChecks": post_deploy_checks,
            "postDeployFailures": post_deploy_failures,
            "rollbackPostChecks": rollback_post_checks,
            "sloReadback": slo_readback or {},
            "dryRun": dry_run_requested,
            "rollback": {
                "triggered": bool(rollback_reason),
                "reason": rollback_reason,
                "startedAt": rollback_started_at,
                "endedAt": rollback_ended_at,
                "durationMs": rollback_duration_ms,
                "result": (
                    {
                        "exitCode": rollback_result.returncode,
                        "stdout": rollback_result.stdout,
                        "stderr": rollback_result.stderr,
                    }
                    if rollback_result is not None
                    else {}
                ),
                "releaseState": rollback_state or {},
            },
            **timing,
        },
    )
    _stackctl.write_json(report_dir / "findings.json", {"target": args.target, "issues": findings})
    _stackctl._write_summary_bundle(
        report_dir,
        command="deploy",
        target=args.target,
        status="ok" if final_exit_code == 0 else "failed",
        summary=f"stackctl deploy {'completed' if final_exit_code == 0 else 'failed'} for {args.target}",
        details=(_stackctl._command_details(deploy_result) if args.target == "prod-hosted" else []) + _stackctl._command_details(result) + ([f"rollout stage: {rollout_stage}"] if args.target == "prod-hosted" else []) + [
            f"post-deploy {item['summary']}"
            for item in post_deploy_checks
        ] + [
            f"rollback-check {item['summary']}"
            for item in rollback_post_checks
        ] + ([f"wired workloads: {', '.join(w['rolloutRef'] for w in _stackctl._prod_rollout_workloads()) or 'none'}"] if args.target == "prod-hosted" else []) + ([f"rollout decision: {rollout_decision}"] if args.target == "prod-hosted" else []) + ([f"rollback triggered: {rollback_reason}"] if rollback_reason else []) + (["dry-run remained read-only"] if dry_run_requested and args.target == "prod-hosted" else []),
        timing=timing,
    )
    _stackctl._write_stdout_markdown(
        report_dir,
        [
            ("deploy", "\n".join(filter(None, [result.stdout, result.stderr]))),
            *(
                [("prod-apply", "\n".join(filter(None, [deploy_result.stdout, deploy_result.stderr])))]
                if args.target == "prod-hosted"
                else []
            ),
            *(
                [("prod-rollback", "\n".join(filter(None, [rollback_result.stdout, rollback_result.stderr])))]
                if rollback_result is not None
                else []
            ),
        ],
    )
    return {
        "exitCode": final_exit_code,
        "summary": f"stackctl deploy {'completed' if final_exit_code == 0 else 'failed'} for {args.target}",
        "details": (_stackctl._command_details(deploy_result) if args.target == "prod-hosted" else []) + _stackctl._command_details(result) + findings + [
            f"rollback-check {item['summary']}"
            for item in rollback_post_checks
        ] + ([f"rollout decision: {rollout_decision}"] if args.target == "prod-hosted" else []) + ([f"rollback triggered: {rollback_reason}"] if rollback_reason else []) + (["dry-run remained read-only"] if dry_run_requested and args.target == "prod-hosted" else []),
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }

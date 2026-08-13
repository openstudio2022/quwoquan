"""stackctl deploy prod-hosted 收尾域: SLO 决策、回滚收敛与 release receipt 提交。

`_deploy_prod_hosted_finalize` 从 `_command_deploy_with_lock` 尾段逐字提取
（scope dict 携带主函数局部状态, 返回续用的输出变量）, 再迁出 stackctl.py。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import subprocess
import time

from typing import Any


def _deploy_prod_hosted_finalize(scope: dict[str, Any]) -> dict[str, Any]:
    """prod-hosted 部署收尾: SLO 决策、回滚收敛与 release receipt 提交。

    从 `_command_deploy_with_lock` 尾段逐字提取; scope 携带主函数局部状态,
    返回主函数继续使用的输出局部变量。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    args = scope["args"]
    committed_release_state = scope["committed_release_state"]
    dry_run_requested = scope["dry_run_requested"]
    error = scope["error"]
    expected_generation = scope["expected_generation"]
    final_exit_code = scope["final_exit_code"]
    findings = scope["findings"]
    from_image_transport_tag = scope["from_image_transport_tag"]
    from_release_evidence_ref = scope["from_release_evidence_ref"]
    hard_deadline_epoch = scope["hard_deadline_epoch"]
    item = scope["item"]
    last_good_candidate_digest = scope["last_good_candidate_digest"]
    nested_args = scope["nested_args"]
    nested_command = scope["nested_command"]
    nested_dir = scope["nested_dir"]
    nested_scope = scope["nested_scope"]
    post_deploy_checks = scope["post_deploy_checks"]
    post_deploy_failures = scope["post_deploy_failures"]
    promotion_deadline_epoch = scope["promotion_deadline_epoch"]
    release_artifact_digest = scope["release_artifact_digest"]
    release_candidate_digests = scope["release_candidate_digests"]
    release_receipt_id = scope["release_receipt_id"]
    release_receipt_path = scope["release_receipt_path"]
    report_dir = scope["report_dir"]
    result = scope["result"]
    rollback_budget_seconds = scope["rollback_budget_seconds"]
    rollback_deadline_epoch = scope["rollback_deadline_epoch"]
    rollback_duration_ms = scope["rollback_duration_ms"]
    rollback_ended_at = scope["rollback_ended_at"]
    rollback_post_checks = scope["rollback_post_checks"]
    rollback_reason = scope["rollback_reason"]
    rollback_result = scope["rollback_result"]
    rollback_started_at = scope["rollback_started_at"]
    rollback_state = scope["rollback_state"]
    rollout_decision = scope["rollout_decision"]
    rollout_stage = scope["rollout_stage"]
    slo_readback = scope["slo_readback"]
    to_image_transport_tag = scope["to_image_transport_tag"]
    to_release_evidence_ref = scope["to_release_evidence_ref"]

    stdout_combined = "\n".join(filter(None, [result.stdout, result.stderr]))
    slo_decision, slo_reason = _stackctl._decision_from_slo_output(
        stdout_combined,
        rollout_stage,
    )
    if slo_decision != "continue":
        rollout_decision = slo_decision
        rollback_reason = slo_reason if slo_decision == "rollback" else ""
        findings.append(slo_reason)
    elif final_exit_code != 0 and post_deploy_failures:
        rollback_reason = "post-deploy checks failed"
        findings.append(rollback_reason)
    if dry_run_requested and result.returncode == 0:
        findings.append("prod dry-run: skipped hosted post-deploy health/inspect/doctor and rollback")
    if rollback_reason and not dry_run_requested:
        rollback_started_at = _stackctl.utc_now()
        rollback_started_monotonic = time.monotonic()
        rollback_deadline_epoch = min(
            hard_deadline_epoch,
            int(time.time()) + rollback_budget_seconds,
        )
        rollback_env = {
            # Re-resolve the complete rollback placement plan from policy;
            # never collapse rollback onto the ledger authority host.
            "PROD_SSH_HOST": "",
            "CLOUD_PROVIDER": args.cloud_provider,
            "SERVICE": args.service,
            "IMAGE_TRANSPORT_TAG": from_image_transport_tag,
            "CANDIDATE_DIGEST": args.from_candidate_digest,
            "PREVIOUS_IMAGE_TRANSPORT_TAG": to_image_transport_tag,
            "ROLLOUT_STAGE": "100",
            "DRY_RUN": "false",
            "PROD_IMAGE_DELIVERY_MODE": "skip",
        }
        try:
            rollback_timeout = min(
                float(rollback_budget_seconds),
                _stackctl._remaining_deadline_seconds(
                    rollback_deadline_epoch, "Prod rollback recovery"
                ),
            )
        except RuntimeError as error:
            rollback_result = subprocess.CompletedProcess(
                ["prod-rollback"], 124, stdout="", stderr=str(error)
            )
        else:
            rollback_result = _stackctl.run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                env=rollback_env,
                timeout_seconds=rollback_timeout,
            )
        if rollback_result.returncode == 0:
            for nested_command, nested_scope in (("health", "full"),):
                nested_dir = report_dir / "rollback" / nested_command
                if nested_command == "health":
                    nested_args = argparse.Namespace(
                        command="health",
                        target=args.target,
                        scope=nested_scope,
                        output_format="json",
                        report_dir=str(nested_dir),
                        request_timeout_seconds=0,
                        retry_attempts=0,
                        retry_sleep_seconds=-1.0,
                        deadline_epoch=rollback_deadline_epoch,
                    )
                    rollback_post_checks.append(_stackctl.command_health(nested_args))
            rollback_failures = [
                item["summary"]
                for item in rollback_post_checks
                if not _stackctl._check_exit_passed(item)
            ]
            findings.extend(f"rollback {item}" for item in rollback_failures)
            if rollback_failures and final_exit_code == 0:
                final_exit_code = 1
            rollback_duration_ms = int(
                (time.monotonic() - rollback_started_monotonic) * 1000
            )
            rollback_ended_at = _stackctl.utc_now()
            rollback_evidence = {
                "triggered": True,
                "startedAt": rollback_started_at,
                "endedAt": rollback_ended_at,
                "durationMs": rollback_duration_ms,
                "postChecks": _stackctl._release_check_receipts(rollback_post_checks),
            }
            rollback_decision = (
                "rollback_failed" if rollback_failures else "rolled_back"
            )
            rollback_succeeded = rollback_decision == "rolled_back"
            rollback_state, release_receipt_path = _stackctl._commit_hosted_release_transition(
                service=args.service,
                from_candidate_digest=(
                    args.to_candidate_digest
                    if rollback_succeeded
                    else args.from_candidate_digest
                ),
                to_candidate_digest=(
                    args.from_candidate_digest
                    if rollback_succeeded
                    else args.to_candidate_digest
                ),
                step="100" if rollback_succeeded else args.step,
                stage="100" if rollback_succeeded else rollout_stage,
                decision=rollback_decision,
                artifact_digest=release_artifact_digest,
                expected_generation=expected_generation,
                receipt_id=release_receipt_id,
                slo_readback=slo_readback,
                candidate_digests=release_candidate_digests,
                last_good_candidate_digest=args.from_candidate_digest,
                post_deploy_checks=post_deploy_checks + rollback_post_checks,
                rollback_outcome=rollback_decision,
                rollback_evidence=rollback_evidence,
                from_release_evidence_ref=(
                    to_release_evidence_ref
                    if rollback_succeeded
                    else from_release_evidence_ref
                ),
                to_release_evidence_ref=(
                    from_release_evidence_ref
                    if rollback_succeeded
                    else to_release_evidence_ref
                ),
                from_image_transport_tag=(
                    to_image_transport_tag
                    if rollback_succeeded
                    else from_image_transport_tag
                ),
                to_image_transport_tag=(
                    from_image_transport_tag
                    if rollback_succeeded
                    else to_image_transport_tag
                ),
                deadline_epoch=rollback_deadline_epoch,
                trigger_stage=rollout_stage,
            )
            committed_release_state = rollback_state
            # The execution/readiness interval is sealed before commit;
            # hosted verifiedAt separately proves durable authority writeback.
            if rollback_duration_ms > rollback_budget_seconds * 1000:
                findings.append(
                    "rollback exceeded the deterministic recovery budget"
                )
                final_exit_code = 1
            if time.time() > hard_deadline_epoch:
                findings.append(
                    "rollback authority readback completed after the hard release deadline"
                )
                final_exit_code = 1
        else:
            findings.append("live rollback apply failed")
            final_exit_code = rollback_result.returncode
            rollback_duration_ms = int(
                (time.monotonic() - rollback_started_monotonic) * 1000
            )
            rollback_ended_at = _stackctl.utc_now()
            committed_release_state, release_receipt_path = _stackctl._commit_hosted_release_transition(
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                to_candidate_digest=args.to_candidate_digest,
                step=args.step,
                stage=rollout_stage,
                decision="rollback_failed",
                artifact_digest=release_artifact_digest,
                expected_generation=expected_generation,
                receipt_id=release_receipt_id,
                slo_readback=slo_readback,
                candidate_digests=release_candidate_digests,
                last_good_candidate_digest=last_good_candidate_digest,
                post_deploy_checks=post_deploy_checks + rollback_post_checks,
                rollback_outcome="rollback_failed",
                rollback_evidence={
                    "triggered": True,
                    "startedAt": rollback_started_at,
                    "endedAt": rollback_ended_at,
                    "durationMs": rollback_duration_ms,
                    "postChecks": _stackctl._release_check_receipts(rollback_post_checks),
                },
                from_release_evidence_ref=from_release_evidence_ref,
                to_release_evidence_ref=to_release_evidence_ref,
                from_image_transport_tag=from_image_transport_tag,
                to_image_transport_tag=to_image_transport_tag,
                deadline_epoch=rollback_deadline_epoch,
                trigger_stage=rollout_stage,
            )
    elif rollout_decision == "pause" and final_exit_code == 10:
        final_exit_code = 10
        if not dry_run_requested:
            committed_release_state, release_receipt_path = _stackctl._commit_hosted_release_transition(
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                to_candidate_digest=args.to_candidate_digest,
                step=args.step,
                stage=rollout_stage,
                decision="pause",
                artifact_digest=release_artifact_digest,
                expected_generation=expected_generation,
                receipt_id=release_receipt_id,
                slo_readback=slo_readback,
                candidate_digests=release_candidate_digests,
                last_good_candidate_digest=last_good_candidate_digest,
                post_deploy_checks=post_deploy_checks,
                rollback_outcome="not_triggered",
                rollback_evidence={"triggered": False},
                from_release_evidence_ref=from_release_evidence_ref,
                to_release_evidence_ref=to_release_evidence_ref,
                from_image_transport_tag=from_image_transport_tag,
                to_image_transport_tag=to_image_transport_tag,
                deadline_epoch=promotion_deadline_epoch,
            )
    elif final_exit_code == 0 and not dry_run_requested:
        committed_last_good_candidate_digest = (
            args.to_candidate_digest
            if rollout_stage == "100"
            else last_good_candidate_digest
        )
        committed_release_state, release_receipt_path = _stackctl._commit_hosted_release_transition(
            service=args.service,
            from_candidate_digest=args.from_candidate_digest,
            to_candidate_digest=args.to_candidate_digest,
            step=args.step,
            stage=rollout_stage,
            decision="continue",
            artifact_digest=release_artifact_digest,
            expected_generation=expected_generation,
            receipt_id=release_receipt_id,
            slo_readback=slo_readback,
            candidate_digests=release_candidate_digests,
            last_good_candidate_digest=committed_last_good_candidate_digest,
            post_deploy_checks=post_deploy_checks,
            rollback_outcome="not_triggered",
            rollback_evidence={"triggered": False},
            from_release_evidence_ref=from_release_evidence_ref,
            to_release_evidence_ref=to_release_evidence_ref,
            from_image_transport_tag=from_image_transport_tag,
            to_image_transport_tag=to_image_transport_tag,
            deadline_epoch=promotion_deadline_epoch,
        )
    if committed_release_state is not None:
        release_receipt_id = committed_release_state["receipt_id"]
        if release_receipt_path is None:
            release_receipt_path = _stackctl._sync_release_ledger_projection(
                args.service,
                release_receipt_id,
                deadline_epoch=(
                    rollback_deadline_epoch
                    if rollback_reason
                    else promotion_deadline_epoch
                ),
            )
    return {
        "committed_release_state": committed_release_state,
        "final_exit_code": final_exit_code,
        "item": item,
        "release_receipt_id": release_receipt_id,
        "release_receipt_path": release_receipt_path,
        "rollback_duration_ms": rollback_duration_ms,
        "rollback_ended_at": rollback_ended_at,
        "rollback_reason": rollback_reason,
        "rollback_result": rollback_result,
        "rollback_started_at": rollback_started_at,
        "rollback_state": rollback_state,
        "rollout_decision": rollout_decision,
    }

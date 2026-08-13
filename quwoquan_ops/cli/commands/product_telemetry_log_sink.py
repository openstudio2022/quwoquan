"""stackctl `product-telemetry-log-sink` 子命令域。

从 stackctl.py 逐字迁出:

- `register_parser`:`product-telemetry-log-sink` 子命令的 argparse 表面
  (帮助文案与参数集合逐字节保持不变);
- `command_product_telemetry_log_sink`:alpha/beta/gamma 本地目标受控
  Elasticsearch 产品遥测日志端口验证的主编排;
- `_run_product_telemetry_log_sink_control_action` /
  `_log_sink_control_query_session` / `_log_sink_control_actions` /
  `_local_managed_ca_environment`:cold-start / health / send-query /
  permission-failure 动作执行与查询会话;
- `_load_active_product_telemetry_log_sink` /
  `_optional_product_telemetry_environment`:active/candidate 观测 log sink
  组合装载(up / repair / doctor 留守与已迁域经 stackctl 命名空间共用);
- `_log_sink_gate_block_receipt` / `_write_full_workload_log_sink_gate_block` /
  `_write_product_telemetry_log_sink_control_report` /
  `_product_telemetry_log_sink_failure_reason`:GATE_BLOCK 回执与控制报告。

`_fixed_candidate_identity` / `_candidate_observability_log_sink` /
`_active_observability_log_sink` / `_reuse_running_full_for_bounded_workload`
等协作符号仍由 stackctl 命名空间拥有或位于兄弟域模块。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    log_sink_control_parser = subparsers.add_parser(
        "product-telemetry-log-sink",
        help="在 alpha/beta/gamma 本地目标受控执行 Elasticsearch 产品遥测日志端口验证。",
    )
    log_sink_control_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    log_sink_control_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    log_sink_control_parser.add_argument(
        "--action",
        choices=("all", "cold-start", "health", "send-query", "permission-failure"),
        default="all",
    )


def _load_active_product_telemetry_log_sink(
    environment: str,
    target_name: str,
    *,
    candidate_snapshot: Mapping[str, Any] | None = None,
):
    import quwoquan_ops.cli.stackctl as _stackctl

    if candidate_snapshot is None:
        runtime = _stackctl._active_observability_log_sink(environment, target_name)
    else:
        baseline_id, candidate_root, manifest = _stackctl._fixed_candidate_identity(
            candidate_snapshot,
            environment_name=environment,
            target_name=target_name,
        )
        runtime = _stackctl._candidate_observability_log_sink(
            environment,
            target_name,
            baseline_id,
            candidate_manifest=manifest,
            candidate_root=candidate_root,
        )
    return _stackctl.load_product_telemetry_log_sink(
        environment,
        target_name,
        runtime_composition=runtime["composition"],
        process_environment=os.environ,
    )


def _optional_product_telemetry_environment(
    environment: str,
    target_name: str,
    *,
    candidate_snapshot: Mapping[str, Any] | None = None,
) -> tuple[dict[str, str], str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        bundle = _stackctl._load_active_product_telemetry_log_sink(
            environment,
            target_name,
            candidate_snapshot=candidate_snapshot,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {"QWQ_PRODUCT_TELEMETRY_AVAILABLE": "0"}, str(exc)
    return {
        **bundle.environment,
        "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "1",
    }, ""


def _log_sink_gate_block_receipt() -> dict[str, str]:
    return {
        "adapterId": "ext.obs.elasticsearch",
        "source": "unavailable",
        "status": "gate_block",
        "redactedDigest": "",
    }


def _write_full_workload_log_sink_gate_block(
    *,
    report_dir: Path,
    report_target: str,
    resolved_target: str,
    formal_release: bool,
    release_input_classification: str,
    contract_graph_digest: str,
    timing: dict[str, Any],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    receipt = _stackctl._log_sink_gate_block_receipt()
    details = [
        "full workload requires product telemetry log-sink binding",
        "ensure the selected local topology exposes the declared log-sink endpoint",
        "use --workload content-release only for import/API/media validation",
    ]
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": resolved_target,
            "workload": "full",
            "formalRelease": formal_release,
            "releaseInputClassification": release_input_classification,
            "contractGraphDigest": contract_graph_digest,
            "status": "gate_block",
            "logSink": receipt,
            "steps": [],
            **timing,
        },
    )
    _stackctl.write_json(report_dir / "findings.json", {"issues": details})
    _stackctl._write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="gate_block",
        summary=f"stackctl up is GATE_BLOCK for {report_target}",
        details=details,
        extra={
            "workload": "full",
            "formalRelease": formal_release,
            "releaseInputClassification": release_input_classification,
            "contractGraphDigest": contract_graph_digest,
            "logSink": receipt,
        },
        timing=timing,
    )
    return {
        "exitCode": 2,
        "summary": f"stackctl up is GATE_BLOCK for {report_target}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "status": "gate_block",
        "workload": "full",
        "formalRelease": formal_release,
        "releaseInputClassification": release_input_classification,
        "contractGraphDigest": contract_graph_digest,
        "logSink": receipt,
        **timing,
    }


def _write_product_telemetry_log_sink_control_report(
    *,
    report_dir: Path,
    target_name: str,
    action: str,
    receipt: dict[str, str],
    action_statuses: list[dict[str, str]],
    gate_blocked: bool,
    failure_reason: str = "",
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Persist only redacted log-sink binding evidence and outcome names."""
    import quwoquan_ops.cli.stackctl as _stackctl

    status = "gate_block" if gate_blocked else "ok"
    summary = (
        f"product telemetry log-sink control is GATE_BLOCK for {target_name}"
        if gate_blocked
        else f"product telemetry log-sink control completed for {target_name}"
    )
    details = (
        [
            failure_reason
            or "full workload requires product telemetry log-sink binding",
        ]
        if gate_blocked
        else [f"{item['action']}: {item['status']}" for item in action_statuses]
    )
    payload = {
        "command": "product-telemetry-log-sink",
        "target": target_name,
        "workload": "full",
        "action": action,
        "status": status,
        "logSink": receipt,
        "actions": action_statuses,
        "executed": len(action_statuses),
        "skipped": 0,
        "failureReason": failure_reason if gate_blocked else "",
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json",
        {"issues": details if gate_blocked else []},
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="product-telemetry-log-sink",
        target=target_name,
        status=status,
        summary=summary,
        details=details,
        extra={
            "workload": "full",
            "logSink": receipt,
        },
        timing=timing,
    )
    return {
        "exitCode": 2 if gate_blocked else 0,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "workload": "full",
        "logSink": receipt,
        "actions": action_statuses,
        "executed": len(action_statuses),
        "skipped": 0,
        **timing,
    }


def _product_telemetry_log_sink_failure_reason(
    action: str,
    error: Exception,
) -> str:
    """Expose only operator-actionable, credential-free failure context."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if isinstance(error, _stackctl.LocalEnvironmentHTTPError):
        return f"{action}: product-ops request failed with HTTP {error.status}"
    message = str(error).strip()
    safe_messages = {
        "GATE_BLOCK: exactly one active candidate-bound identity receipt is required",
        "product telemetry query authorization is unavailable",
        "product-ops public base is unavailable",
        "cold-start failed",
        "health failed",
        "permission probe returned unexpected status",
        "permission probe unexpectedly succeeded",
    }
    if message in safe_messages:
        return message
    return f"{action}: failed; inspect redacted stackctl evidence"


def _log_sink_control_actions(action: str) -> tuple[str, ...]:
    if action == "all":
        return ("cold-start", "health", "send-query", "permission-failure")
    return (action,)


@contextlib.contextmanager
def _local_managed_ca_environment(target_name: str):
    """Scope canonical local CA trust to one in-process control action."""
    import quwoquan_ops.cli.stackctl as _stackctl

    previous = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(_stackctl.root_certificate_path(target_name))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous


def _log_sink_control_query_session(
    *,
    api_base: str,
    environment: str,
    target_name: str,
) -> LocalAcceptanceSession:
    """Resolve a query session without serializing a bearer token into evidence."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if environment in {"alpha", "beta", "gamma"}:
        token = _stackctl.mint_local_product_ops_operator_token(environment, target_name)
        return _stackctl.LocalAcceptanceSession(
            owner_id=f"operator:content-commercial:{environment}",
            persona_id="",
            access_token=token,
        )
    query_token = os.environ.get("PRODUCT_TELEMETRY_QUERY_TOKEN", "").strip()
    if query_token:
        return _stackctl.LocalAcceptanceSession(
            owner_id="log-sink-control",
            persona_id="log-sink-control",
            access_token=query_token,
        )
    raise RuntimeError("product telemetry query authorization is unavailable")


def _run_product_telemetry_log_sink_control_action(
    *,
    action: str,
    target_name: str,
    environment: str,
    report_dir: Path,
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    if action == "cold-start":
        # The preceding package/up step has already produced provenance-bound
        # images. Cold-start verifies their restart path without silently
        # replacing that artifact with a new, unverified build.
        # When a full runtime receipt is already running, re-entering `up`
        # is rejected as leftover-attempt; treat that as an already-warmed
        # cold-start rather than forcing a destructive down/up cycle.
        try:
            active_attempt = _stackctl.load_startup_attempt(target_name)
        except (OSError, ValueError):
            active_attempt = None
        if (
            isinstance(active_attempt, dict)
            and active_attempt.get("status") == "running"
            and active_attempt.get("workload") == "full"
            and active_attempt.get("target") == target_name
            and active_attempt.get("env") == environment
        ):
            try:
                candidate_snapshot = _stackctl.active_deployment_candidate_snapshot(
                    target_name
                )
                if candidate_snapshot is None:
                    raise ValueError(
                        "active immutable candidate snapshot is missing"
                    )
                package_ok, package_detail = _stackctl.can_reuse_package(
                    environment,
                    target_name,
                    include_services=True,
                    purpose="self_verify",
                    candidate_root=Path(
                        str(candidate_snapshot["candidateDir"])
                    ),
                )
                if not package_ok:
                    raise ValueError(
                        "candidate package fingerprint is invalid: "
                        + package_detail
                    )
                expected_identity = _stackctl._fixed_candidate_runtime_identity(
                    candidate_snapshot,
                    environment_name=environment,
                    target_name=target_name,
                )
                mismatches = _stackctl._runtime_identity_mismatches(
                    active_attempt,
                    expected_identity,
                )
                if mismatches:
                    raise ValueError(
                        "running full startup receipt differs from the fixed candidate: "
                        + ", ".join(mismatches)
                    )
                _stackctl.assert_active_deployment_candidate_snapshot(
                    candidate_snapshot
                )
            except (KeyError, OSError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"cold-start running-full reuse is GATE_BLOCK: {exc}"
                ) from exc
            _stackctl.write_json(
                report_dir / "cold-start" / "already-running.json",
                {
                    "schema": "stackctl-product-telemetry-cold-start-reuse",
                    "target": target_name,
                    "environment": environment,
                    "startupAttemptId": active_attempt.get("attemptId"),
                    "workload": "full",
                    "candidateDigest": expected_identity["candidateDigest"],
                    "packageDigest": str(
                        candidate_snapshot["manifest"]["packageDigest"]
                    ),
                    "status": "reused_running_full",
                },
            )
            return
        result = _stackctl.command_up(
            argparse.Namespace(
                command="up",
                env="",
                target=target_name,
                device_id="",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                workload="full",
                rollout_mode="",
                output_format="json",
                report_dir=str(report_dir / "cold-start"),
            )
        )
        if int(result.get("exitCode", 1)) != 0:
            raise RuntimeError("cold-start failed")
        return

    if action == "health":
        # Log-sink health proves product-ops + ES telemetry path.
        # Do not require scope=full commercial probes (e.g. global_search).
        result = _stackctl.command_health(
            argparse.Namespace(
                command="health",
                target=target_name,
                scope="content-commercial",
                output_format="json",
                report_dir=str(report_dir / "health"),
            )
        )
        if int(result.get("exitCode", 1)) != 0:
            raise RuntimeError("health failed")
        return

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base = str(public_bases.get("api") or "").strip()
    product_ops_base = str(public_bases.get("productOps") or "").strip()
    if not api_base or not product_ops_base:
        raise RuntimeError("product-ops public base is unavailable")
    instance_id = "log-sink-" + uuid4().hex
    actor = _stackctl.open_test_data_acceptance_session(
        api_base,
        environment=environment,
        target_name=target_name,
        test_data_instance_id=instance_id,
        actor_role="primary",
        actor_index=0,
    )
    try:
        session = actor.session
        if action == "permission-failure":
            try:
                _stackctl.request_local_environment_json(
                    product_ops_base,
                    path="/ops/events/summary",
                    session=session,
                )
            except _stackctl.LocalEnvironmentHTTPError as exc:
                if exc.status == 403:
                    return
                raise RuntimeError(
                    "permission probe returned unexpected status"
                ) from exc
            raise RuntimeError("permission probe unexpectedly succeeded")

        if action != "send-query":
            raise ValueError(
                f"unsupported product telemetry log-sink action: {action}"
            )

        probe_record = {
            "logType": "event",
            "eventType": "chat_interaction_outcome",
            "sessionId": "s.c2xzX2NvbnRyb2w.1",
            "pageName": "chat_detail",
            "occurredAt": _stackctl.utc_now(),
            "deviceManufacturer": "LogSinkControl",
            "deviceModel": "LogSinkControl",
            "appVersion": "0.0.0-log-sink-control",
            "networkClass": "other",
            "devicePlatform": "web",
            "chatAction": "mention_send",
            "chatOutcome": "succeeded",
            "mentionScope": "member",
        }
        body = {"events": [probe_record]}
        canonical_body = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        idempotency_key = hashlib.sha256(canonical_body).hexdigest()
        _stackctl.request_local_environment_json(
            product_ops_base,
            path="/ops/events",
            session=session,
            method="POST",
            body=body,
            headers={"Idempotency-Key": idempotency_key},
        )
        query_session = _stackctl._log_sink_control_query_session(
            api_base=api_base,
            environment=environment,
            target_name=target_name,
        )
        _stackctl.request_local_environment_json(
            product_ops_base,
            path="/ops/events/summary",
            session=query_session,
        )
    finally:
        _stackctl.close_test_data_acceptance_actor(
            api_base,
            actor=actor,
            test_data_instance_id=instance_id,
        )


def command_product_telemetry_log_sink(args: argparse.Namespace) -> dict[str, Any]:
    """Execute product telemetry probes through product-ops, never direct Provider."""
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    environment = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, environment, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    actions = _stackctl._log_sink_control_actions(args.action)
    try:
        bundle = _stackctl._load_active_product_telemetry_log_sink(
            environment,
            args.target,
        )
        receipt = bundle.redacted_receipt()
    except (OSError, RuntimeError, TypeError, ValueError):
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return _stackctl._write_product_telemetry_log_sink_control_report(
            report_dir=report_dir,
            target_name=args.target,
            action=args.action,
            receipt=_stackctl._log_sink_gate_block_receipt(),
            action_statuses=[],
            gate_blocked=True,
            timing=timing,
        )

    action_statuses: list[dict[str, str]] = []
    with _stackctl._local_managed_ca_environment(args.target):
        for action in actions:
            try:
                _stackctl._run_product_telemetry_log_sink_control_action(
                    action=action,
                    target_name=args.target,
                    environment=environment,
                    report_dir=report_dir,
                )
            except (RuntimeError, ValueError, _stackctl.LocalEnvironmentHTTPError) as exc:
                action_statuses.append({"action": action, "status": "failed"})
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                return _stackctl._write_product_telemetry_log_sink_control_report(
                    report_dir=report_dir,
                    target_name=args.target,
                    action=args.action,
                    receipt=receipt,
                    action_statuses=action_statuses,
                    gate_blocked=True,
                    failure_reason=_stackctl._product_telemetry_log_sink_failure_reason(
                        action,
                        exc,
                    ),
                    timing=timing,
                )
            action_statuses.append({"action": action, "status": "passed"})

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    return _stackctl._write_product_telemetry_log_sink_control_report(
        report_dir=report_dir,
        target_name=args.target,
        action=args.action,
        receipt=receipt,
        action_statuses=action_statuses,
        gate_blocked=False,
        timing=timing,
    )


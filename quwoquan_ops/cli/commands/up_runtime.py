"""stackctl `up` 域锁内启动编排主干。

从 commands/up_domain.py 逐字迁出:

- `_command_up_impl`:锁内的全量启动编排(build/preflight/compose/
  provider runtime/observability log sink/App 启动与 startup receipt)。

prod-sim / prod-hosted 的 App 启动分支体与 `tail_*_background_logs`
家族已迁往 `commands/up_app_launch.py`,经函数内延迟导入
`_up_app_launch` 属性访问委托;`register_parser` / `command_up` /
`_reuse_running_full_for_bounded_workload` /
`_fixed_candidate_runtime_identity` / `_runtime_identity_mismatches`
在 `commands/up_domain.py`(该模块 re-export 本模块的
`_command_up_impl` 供 stackctl 命名空间装配)。
`_bind_formal_local_release_provider_environment` / `_gamma_start_command` /
`_run_with_live_output` / `_tail_file_for_startup` / `_write_summary_bundle` /
`_optional_product_telemetry_environment` 等协作符号仍由 stackctl
命名空间拥有。测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块
消费的协作符号,因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问,
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping


def _command_up_impl(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.commands import up_app_launch as _up_app_launch

    topology = _stackctl.load_environment_topology()
    started_monotonic, started_at = _stackctl._start_timing()
    if not args.env and not args.target:
        try:
            args.env = _stackctl.pick_dev_up_env(label="[stackctl up]")
        except RuntimeError as exc:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl up failed",
                "details": [str(exc)],
                **timing,
            }

    if bool(args.env) == bool(args.target):
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["provide exactly one of --env or --target"],
            **timing,
        }

    requested_target = args.target
    if args.env:
        requested_target = _stackctl.DEV_UP_STACK_TARGETS[args.env]
        if not requested_target:
            requested_target = _stackctl.app_target_for_env(args.env)

    build_only = bool(getattr(args, "build_only", False))
    release_composition: dict[str, Any] = {}
    runtime_images: dict[str, dict[str, str]] = {}
    destructive_actions: list[str] = []
    build_services = str(getattr(args, "build_services", "")).strip()
    if build_services and not build_only:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["--build-services requires --build-only"],
            **timing,
        }
    if build_only and getattr(args, "skip_build", False):
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["--build-only cannot be combined with --skip-build"],
            **timing,
        }
    if build_only and requested_target != "gamma-local":
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["--build-only is supported only for gamma-local"],
            **timing,
        }

    target = _stackctl.get_target(topology, requested_target)
    env_name = str(target["env"])
    report_target = args.env or requested_target
    try:
        report_dir = _stackctl.validate_up_report_dir(
            _stackctl.resolve_report_dir(args, env_name, report_target),
            env_name=env_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {report_target}",
            "details": [f"unsafe up report directory: {exc}"],
            **timing,
        }
    # 容量先于一切：数据盘写满时构建、启动与 healthcheck 都会以互不相干的
    # 形态失败，先判容量才能让失败消息指向真正的原因。
    capacity = _stackctl.local_runtime_capacity_evidence(target)
    if capacity["issues"]:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {report_target}",
            "details": capacity["issues"],
            "firstBlocker": capacity["blocker"],
            "capacity": capacity["evidence"],
            "reportDir": str(report_dir.resolve()),
            **timing,
        }
    fixed_candidate_snapshot: dict[str, Any] | None = None
    if requested_target in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        if build_only:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl up build-only is retired",
                "details": [
                    "up only consumes a fixed candidate; run stackctl package explicitly"
                ],
                "reportDir": str(report_dir.resolve()),
                **timing,
            }
        try:
            fixed_candidate_snapshot = _stackctl.active_deployment_candidate_snapshot(
                requested_target
            )
        except (OSError, TypeError, ValueError) as exc:
            fixed_candidate_snapshot = None
            package_ok = False
            package_detail = f"active candidate rejected: {exc}"
        else:
            if fixed_candidate_snapshot is None:
                package_ok = False
                package_detail = f"missing active candidate: {requested_target}"
            else:
                package_ok, package_detail = _stackctl.can_reuse_package(
                    env_name,
                    requested_target,
                    include_services=True,
                    purpose="self_verify",
                    candidate_root=Path(
                        str(fixed_candidate_snapshot["candidateDir"])
                    ),
                )
        if not package_ok:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": f"stackctl up GATE_BLOCK: fixed package missing for {requested_target}",
                "details": [package_detail, "run stackctl package explicitly"],
                "reportDir": str(report_dir.resolve()),
                **timing,
            }
        # Local start scripts must never compile or re-package the workspace.
        args.skip_build = True
    bounded_reuse = _stackctl._reuse_running_full_for_bounded_workload(
        args,
        candidate_snapshot=fixed_candidate_snapshot,
        target_name=requested_target,
        env_name=env_name,
        report_target=report_target,
        report_dir=report_dir,
        started_monotonic=started_monotonic,
        started_at=started_at,
    )
    if bounded_reuse is not None:
        return bounded_reuse
    # Migration drift is diagnostic input only. Destructive repair is never implicit.
    if requested_target in {"alpha-local", "beta-local"} and not build_only:
        drift = _stackctl.probe_migration_drift(requested_target)
        if drift.has_drift:
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            details = [
                _stackctl.format_drift_gate_block(drift),
                "use an explicitly approved stackctl repair action; up never wipes data",
            ]
            _stackctl.write_json(
                report_dir / "report.json",
                {
                    "command": "up",
                    "target": report_target,
                    "resolvedTarget": requested_target,
                    "status": "gate_block",
                    "migrationDrift": drift.detail,
                    "details": details,
                    **timing,
                },
            )
            return {
                "exitCode": 2,
                "summary": (
                    f"stackctl up GATE_BLOCK: migration drift on {requested_target}"
                ),
                "details": details,
                "reportDir": str(report_dir.resolve()),
                **timing,
            }
    # A content release starts only the import/consumer data plane. Device
    # selection belongs to a separate App UAT command, never to server startup.
    if args.workload in {"content-release", "content-commercial"}:
        args.skip_app = True
    release_input_classification = ""
    contract_graph_digest = ""
    if fixed_candidate_snapshot is not None:
        candidate_manifest = fixed_candidate_snapshot.get("manifest")
        if not isinstance(candidate_manifest, Mapping):
            raise ValueError("fixed deployment candidate manifest is missing")
        derived_classification = _stackctl.classify_release_inputs(
            candidate_manifest.get("release")
        )
        release_input_classification = str(
            candidate_manifest.get("releaseInputClassification") or ""
        )
        if release_input_classification != derived_classification:
            raise ValueError(
                "fixed deployment candidate release input classification drifted"
            )
        contract_graph_digest = str(
            candidate_manifest.get("contractGraphDigest") or ""
        )
        if re.fullmatch(r"sha256:[0-9a-f]{64}", contract_graph_digest) is None:
            raise ValueError(
                "fixed deployment candidate ContractGraph digest is invalid"
            )
    release_input_report = (
        {
            "releaseInputClassification": release_input_classification,
            "contractGraphDigest": contract_graph_digest,
        }
        if release_input_classification
        else {}
    )

    def assert_fixed_candidate_selected() -> None:
        if requested_target not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
            return
        if fixed_candidate_snapshot is None:
            raise ValueError("fixed immutable candidate snapshot is missing")
        _stackctl.assert_active_deployment_candidate_snapshot(fixed_candidate_snapshot)

    log_sink_receipt = {
        "source": "not-required",
        "status": "not-claimed",
        "redactedDigest": "",
    }
    log_sink_redaction_values: tuple[str, ...] = ()
    if args.workload == "full" and requested_target in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        try:
            log_sink_bundle = _stackctl._load_active_product_telemetry_log_sink(
                env_name,
                requested_target,
                candidate_snapshot=fixed_candidate_snapshot,
            )
            log_sink_receipt = log_sink_bundle.redacted_receipt()
            log_sink_redaction_values = tuple(log_sink_bundle.environment.values())
        except (OSError, RuntimeError, TypeError, ValueError):
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return _stackctl._write_full_workload_log_sink_gate_block(
                report_dir=report_dir,
                report_target=report_target,
                resolved_target=requested_target,
                formal_release=False,
                release_input_classification=release_input_classification,
                contract_graph_digest=contract_graph_digest,
                timing=timing,
            )
    steps: list[dict[str, Any]] = []
    interactive = _stackctl._is_interactive_terminal()
    stage_index = 0
    expected_stage_total = (
        3
        if requested_target in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
        and not args.skip_app
        else 2
    )
    if requested_target in {"prod-sim", "prod-hosted"} and not args.skip_app:
        expected_stage_total = 2
    elif requested_target == "prod-hosted" and args.skip_app:
        expected_stage_total = 1

    def announce(stage: str, message: str, *, numbered: bool = False) -> None:
        if interactive:
            if numbered:
                _stackctl._progress_print(f"{stage} {message}")
            else:
                _stackctl._progress_print(f"[stackctl up] {stage} {message}")

    def run_stage(
        stage: str,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        live_prefix: str = "",
    ) -> subprocess.CompletedProcess[str]:
        nonlocal stage_index
        stage_index += 1
        stage_header = _stackctl._format_stage_header(stage_index, expected_stage_total, stage)
        announce(stage_header, "started", numbered=True)
        stage_started = time.monotonic()
        result = _stackctl._run_with_live_output(
            argv,
            env=env,
            prefix=live_prefix,
            redaction_values=log_sink_redaction_values,
        )
        duration = _stackctl._format_duration_ms(int((time.monotonic() - stage_started) * 1000))
        status = "completed" if result.returncode == 0 else f"failed (exit={result.returncode})"
        announce(stage_header, f"{status} in {duration}", numbered=True)
        return result

    def maybe_resolve_device_id(*, include_web: bool) -> str:
        if args.skip_app:
            return ""
        if args.device_id:
            return args.device_id
        return _stackctl.resolve_device_id(
            include_mobile=True,
            include_web=include_web,
            include_desktop=False,
            label="[stackctl up]",
        )

    def start_app_process(
        env_key: str,
        device_id: str,
        *,
        launch_bundle: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        nonlocal stage_index
        launch_log = report_dir / f"app-launch-{device_id.replace('/', '_')}.log"
        stage_index += 1
        stage_header = _stackctl._format_stage_header(stage_index, expected_stage_total, "app-launch")
        announce(stage_header, f"starting for {env_key}/{device_id}", numbered=True)
        try:
            bundle = dict(launch_bundle or {})
            process = _stackctl.launch_app(
                env_key,
                device_id,
                topology=topology,
                rollout_mode=args.rollout_mode,
                log_path=launch_log,
                artifact_manifest=(
                    Path(str(bundle["artifactManifestPath"])) if bundle else None
                ),
                launcher_handoff=(
                    Path(str(bundle["launcherHandoffPath"])) if bundle else None
                ),
                candidate_digest=str(bundle.get("candidateDigest") or ""),
                artifact_manifest_digest=str(
                    bundle.get("artifactManifestDigest") or ""
                ),
                launcher_handoff_digest=str(
                    bundle.get("launcherHandoffDigest") or ""
                ),
            )
        except RuntimeError as exc:
            raise RuntimeError(f"app launch failed for {env_key}/{device_id}: {exc}") from exc
        return {
            "process": process,
            "command": _stackctl.build_start_app_command(
                env_key,
                device_id,
                topology=topology,
                rollout_mode=args.rollout_mode,
                app_mode=("release-artifact" if bundle else "content-live"),
                artifact_manifest=(
                    Path(str(bundle["artifactManifestPath"])) if bundle else None
                ),
                launcher_handoff=(
                    Path(str(bundle["launcherHandoffPath"])) if bundle else None
                ),
                candidate_digest=str(bundle.get("candidateDigest") or ""),
                artifact_manifest_digest=str(
                    bundle.get("artifactManifestDigest") or ""
                ),
                launcher_handoff_digest=str(
                    bundle.get("launcherHandoffDigest") or ""
                ),
            ),
            "log_path": launch_log,
            "stageHeader": stage_header,
        }

    cmd = ["stackctl", "up", "--target", requested_target]
    if requested_target in {"alpha-local", "beta-local", "gamma-local"}:
        try:
            profile_name, profile_kind, _ = _stackctl.tls_profile(requested_target)
            if profile_kind != "local-managed":
                raise _stackctl.PublicDomainTlsError(
                    f"GATE_BLOCK: {requested_target} must use local-managed TLS"
                )
            try:
                tls_evidence = _stackctl.verify_certificate(requested_target)
            except _stackctl.PublicDomainTlsError:
                tls_evidence = _stackctl.issue_certificate(requested_target)
            resolver_handoff = _stackctl.materialize_handoff(requested_target)
            steps.extend(
                (
                    {
                        "name": "local-managed-tls",
                        "exitCode": 0,
                        "stdout": json.dumps(tls_evidence, ensure_ascii=False),
                        "stderr": "",
                    },
                    {
                        "name": "canonical-local-resolver-handoff",
                        "exitCode": 0,
                        "stdout": json.dumps(resolver_handoff, ensure_ascii=False),
                        "stderr": "",
                    },
                )
            )
        except (_stackctl.PublicDomainTlsError, _stackctl.LocalTargetHandoffError, OSError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=str(exc),
            )
            steps.append(
                {
                    "name": "local-managed-tls-and-resolver",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )
        else:
            result = None
    else:
        result = None

    if result is not None:
        pass
    elif requested_target in {"alpha-local", "beta-local", "gamma-local"}:
        # Every supported local workload consumes the same packaged OCI
        # composition.  content-release only narrows runtime probes; it never
        # selects the retired Alpha/Beta build-from-worktree implementations.
        env = _stackctl._gamma_env_from_port_manifest(topology, requested_target)
        env[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = ""
        env[_stackctl.RUNTIME_CANDIDATE_ROOT_ENV] = str(
            (fixed_candidate_snapshot or {}).get("candidateDir") or ""
        )
        # Skill package trust must come from the capsule that this candidate
        # sealed; re-issuing keys at up time would rebind a frozen release.
        env["QWQ_FIXED_CANDIDATE_ROOT"] = env[_stackctl.RUNTIME_CANDIDATE_ROOT_ENV]
        env["QWQ_RUN_ROOT"] = str(report_dir.resolve())
        env["QWQ_OBSERVABILITY_RUN_ROOT"] = str(
            _stackctl.env_observability_run_dir(env_name, report_dir.name).resolve()
        )
        env["QWQ_WORKLOAD"] = args.workload
        telemetry_advisory = ""
        if args.workload == "full":
            telemetry_env, telemetry_advisory = (
                _stackctl._optional_product_telemetry_environment(
                    env_name,
                    requested_target,
                    candidate_snapshot=fixed_candidate_snapshot,
                )
            )
            env.update(telemetry_env)
        elif args.workload == "content-commercial":
            # Product Ops must bind the local Elasticsearch endpoint to start,
            # but full commercial observability remains a separate workload gate.
            try:
                commercial_log_sink = _stackctl._load_active_product_telemetry_log_sink(
                    env_name,
                    requested_target,
                    candidate_snapshot=fixed_candidate_snapshot,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                telemetry_advisory = str(exc)
                env["QWQ_PRODUCT_TELEMETRY_AVAILABLE"] = "0"
            else:
                env.update(commercial_log_sink.environment)
                env["QWQ_PRODUCT_TELEMETRY_AVAILABLE"] = "0"
                log_sink_receipt = commercial_log_sink.redacted_receipt()
                log_sink_redaction_values = tuple(
                    commercial_log_sink.environment.values()
                )
        else:
            env["QWQ_PRODUCT_TELEMETRY_AVAILABLE"] = "0"
        cmd = _stackctl._gamma_start_command(args)
        syntax_cmd = [
            "bash",
            "-n",
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        ]
        syntax_result = _stackctl.run(syntax_cmd, env=env)
        provider_error = None
        if syntax_result.returncode == 0:
            try:
                if fixed_candidate_snapshot is None:
                    raise ValueError("fixed immutable candidate snapshot is missing")
                (
                    provider_runtime_binding,
                    observability_runtime_binding,
                ) = _stackctl._candidate_bindings_from_snapshot(
                    fixed_candidate_snapshot,
                    environment_name=env_name,
                    target_name=requested_target,
                )
                env.update(
                    _stackctl._provider_runtime_launch_environment(
                        provider_runtime_binding["providerRuntime"],
                        candidate_root=provider_runtime_binding["candidateRoot"],
                        workload=args.workload,
                    )
                )
                env.update(
                    _stackctl._observability_log_sink_launch_environment(
                        observability_runtime_binding["composition"],
                        environment_name=env_name,
                        target_name=requested_target,
                        candidate_root=observability_runtime_binding[
                            "candidateRoot"
                        ],
                        workload=args.workload,
                    )
                )
            except (OSError, TypeError, ValueError) as exc:
                provider_error = (
                    f"{requested_target} package-bound Provider runtime failed: {exc}"
                )
            else:
                provider_error = _stackctl._bind_formal_local_release_provider_environment(
                    env,
                    environment_name=env_name,
                    target_name=requested_target,
                    workload=args.workload,
                    runtime_composition=provider_runtime_binding["composition"],
                )
        steps.append(
            {
                "name": "shared-local-runtime-script-syntax",
                "argv": syntax_cmd,
                "exitCode": syntax_result.returncode,
                "stdout": syntax_result.stdout,
                "stderr": syntax_result.stderr,
            }
        )
        if provider_error is not None or telemetry_advisory or syntax_result.returncode:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=provider_error or telemetry_advisory or syntax_result.stderr,
            )
        else:
            try:
                assert_fixed_candidate_selected()
                release_composition = _stackctl._bind_gamma_packaged_service_image_refs(
                    env_name,
                    env,
                    candidate_snapshot=fixed_candidate_snapshot,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result = subprocess.CompletedProcess(
                    cmd,
                    2,
                    stdout="",
                    stderr=str(exc),
                )
            else:
                steps.append(
                    {
                        "name": "package-bound-runtime-composition",
                        "exitCode": 0,
                        "stdout": release_composition["imageVersion"],
                        "stderr": "",
                    }
                )
                result = run_stage(
                    requested_target,
                    cmd,
                    env=env,
                    live_prefix=f"[{requested_target}] ",
                )
    elif requested_target == "prod-sim":
        result, cmd = _up_app_launch._launch_prod_sim_stack(
            args,
            steps=steps,
            run_stage=run_stage,
            announce=announce,
            maybe_resolve_device_id=maybe_resolve_device_id,
            start_app_process=start_app_process,
            candidate_snapshot=fixed_candidate_snapshot,
            assert_fixed_candidate_selected=assert_fixed_candidate_selected,
        )
    elif requested_target == "prod-hosted":
        early_result, hosted_result, cmd = _up_app_launch._launch_prod_hosted_session(
            args,
            cmd=cmd,
            report_dir=report_dir,
            started_monotonic=started_monotonic,
            started_at=started_at,
            steps=steps,
            announce=announce,
            maybe_resolve_device_id=maybe_resolve_device_id,
            start_app_process=start_app_process,
        )
        if early_result is not None:
            return early_result
        result = hosted_result
    else:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": f"stackctl up is not implemented for {requested_target}",
            "details": ["use deploy for hosted gamma/prod targets"],
            **timing,
        }

    if requested_target in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        try:
            assert_fixed_candidate_selected()
        except (OSError, TypeError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout=str(result.stdout or ""),
                stderr=f"active candidate changed during startup: {exc}",
            )

    if (
        result.returncode == 0
        and requested_target in {"alpha-local", "beta-local", "gamma-local"}
        and args.workload in {"full", "content-commercial"}
    ):
        product_ops_base_url = str(
            (_stackctl.get_target(topology, requested_target).get("publicBases") or {}).get(
                "productOps"
            )
            or ""
        ).strip()
        try:
            if not product_ops_base_url:
                raise _stackctl.ExperimentPolicyActivationError(
                    "target topology lacks Product Ops public base"
                )
            policy_receipt = _stackctl.activate_search_experiment_policy(
                environment=env_name,
                target=requested_target,
                product_ops_base_url=product_ops_base_url,
            )
            policy_receipt_path = report_dir / "experiment-policy-activation.json"
            _stackctl.write_json(policy_receipt_path, policy_receipt)
            steps.append(
                {
                    "name": "package-bound-experiment-policy-activation",
                    "exitCode": 0,
                    "stdout": _stackctl.relpath(policy_receipt_path),
                    "stderr": "",
                }
            )
        except (_stackctl.ExperimentPolicyActivationError, OSError, RuntimeError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout=str(result.stdout or ""),
                stderr=str(exc),
            )
            steps.append(
                {
                    "name": "package-bound-experiment-policy-activation",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )

    if requested_target in {"alpha-local", "beta-local", "gamma-local"}:
        try:
            assert_fixed_candidate_selected()
        except (OSError, TypeError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout=str(result.stdout or ""),
                stderr=f"active candidate changed before completion: {exc}",
            )

    startup_health_failure: dict[str, Any] = {}
    if (
        requested_target in {"alpha-local", "beta-local", "gamma-local"}
        and fixed_candidate_snapshot is not None
    ):
        startup_health_failure, health_failure_issue = (
            _stackctl._startup_health_failure_for_report(
                report_dir,
                target=requested_target,
                candidate_digest=str(
                    fixed_candidate_snapshot.get("baselineId") or ""
                ),
                startup_exit_code=result.returncode,
            )
        )
        if health_failure_issue:
            steps.append(
                {
                    "name": "managed-startup-health-failure-evidence",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": health_failure_issue,
                }
            )

    if log_sink_redaction_values:
        steps = _stackctl._redact_controlled_payload(steps, log_sink_redaction_values)
        if startup_health_failure:
            startup_health_failure = _stackctl._redact_controlled_payload(
                [startup_health_failure],
                log_sink_redaction_values,
            )[0]
        result = subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=_stackctl._redact_controlled_values(
                str(result.stdout or ""),
                log_sink_redaction_values,
            ),
            stderr=_stackctl._redact_controlled_values(
                str(result.stderr or ""),
                log_sink_redaction_values,
            ),
        )
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    steps.append(
        {
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": requested_target,
            "workload": args.workload,
            **release_input_report,
            "releaseComposition": release_composition,
            "runtimeMode": "immutable-local" if release_composition else "",
            "runtimeCandidateDigest": "",
            "runtimeImages": runtime_images,
            "destructiveRepairPerformed": bool(destructive_actions),
            "destructiveActions": destructive_actions,
            "logSink": log_sink_receipt,
            "startupHealthFailure": startup_health_failure,
            "steps": steps,
            **timing,
        },
    )
    terminal_status = (
        "ok" if result.returncode == 0 else "gate_block" if result.returncode == 2 else "failed"
    )
    terminal_summary = (
        f"stackctl up completed for {report_target}"
        if result.returncode == 0
        else f"stackctl up is GATE_BLOCK for {report_target}"
        if result.returncode == 2
        else f"stackctl up failed for {report_target}"
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status=terminal_status,
        summary=terminal_summary,
        details=_stackctl._command_details(result),
        extra={
            "workload": args.workload,
            **release_input_report,
            "releaseComposition": release_composition,
            "runtimeMode": "immutable-local" if release_composition else "",
            "runtimeCandidateDigest": "",
            "runtimeImages": runtime_images,
            "destructiveRepairPerformed": bool(destructive_actions),
            "destructiveActions": destructive_actions,
            "logSink": log_sink_receipt,
            "startupHealthFailure": startup_health_failure,
        },
        timing=timing,
    )
    payload = {
        "exitCode": result.returncode,
        "summary": terminal_summary,
        "details": _stackctl._command_details(result),
        "reportDir": str(report_dir.resolve()),
        **release_input_report,
        "logSink": log_sink_receipt,
        "startupHealthFailure": startup_health_failure,
        **timing,
    }
    return payload

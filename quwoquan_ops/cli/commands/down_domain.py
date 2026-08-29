"""stackctl `down` 子命令域。

从 stackctl.py 逐字迁出:

- `register_parser`:`down` 子命令的 argparse 表面(帮助文案与参数集合
  逐字节保持不变);
- `command_down`:bounded workload no-op 决策、consumer lease 门与
  operation lock 编排的 down 入口;
- `_consumer_lease_down_gate`:活跃 App consumer lease 的 teardown 拒绝门;
- `_bounded_workload_down_decision`:bounded workload 复用 full 栈时的
  无损 no-op 决策;
- `_bind_local_teardown_runtime`:teardown 所需 runtime receipt 环境绑定;
- `_command_down_unlocked`:锁内的 compose teardown、端口释放与
  purge-rebuildable-state 执行体。

mutable test-live teardown 家族在 `commands/down_shared.py`;
`_wait_for_network_ports_released` / `_bind_gamma_down_parse_environment` /
`_orphan_compose_runtime_gate` 等协作符号仍由 stackctl 命名空间拥有
(repair 留守域共用)。测试经 ``mock.patch.object(stackctl, ...)`` patch
本模块符号与协作符号,因此函数体内一律经函数内延迟导入 `_stackctl`
属性访问(含本模块符号互调),保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    down_parser = subparsers.add_parser("down")
    down_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    down_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    down_parser.add_argument(
        "--workload",
        choices=["content-release", "content-commercial", "full"],
        default="",
        help="只停止匹配的 active workload；bounded workload 复用 full 时为无损 no-op。",
    )
    down_parser.add_argument(
        "--formal-release",
        action="store_true",
        help="Stop only the candidate-scoped immutable Compose project.",
    )
    down_parser.add_argument(
        "--release-manifest",
        default="",
        help="Canonical ReleaseEvidenceManifest required by formal teardown.",
    )
    down_parser.add_argument(
        "--purge-rebuildable-state",
        action="store_true",
        help=(
            "Delete only the runtime-receipt-bound Alpha/Beta/Gamma Compose "
            "volumes and target cache after stopping the target."
        ),
    )


def _consumer_lease_down_gate(
    args: argparse.Namespace,
    leases: list[dict[str, Any]],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    report_dir = _stackctl.resolve_report_dir(args, str(target["env"]), args.target)
    details = [
        (
            f"active consumer lease: device={lease.get('device')} "
            f"consumer={lease.get('consumer')} state={lease.get('state')} "
            f"startedAt={lease.get('startedAt')}"
        )
        for lease in leases
    ]
    details.append(
        "release the app session with stackctl consumer-lease release before down"
    )
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "status": "gate_block",
            "reason": "active_consumer_lease",
            "details": details,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="gate_block",
        summary=f"stackctl down is blocked for {args.target}",
        details=details,
    )
    return {
        "exitCode": 2,
        "summary": f"stackctl down is GATE_BLOCK for {args.target}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
    }


def _bounded_workload_down_decision(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    import quwoquan_ops.cli.stackctl as _stackctl

    requested_workload = str(getattr(args, "workload", "") or "").strip()
    if requested_workload not in {"content-release", "content-commercial"}:
        return None
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    try:
        active_attempt = _stackctl.load_startup_attempt(args.target)
    except (OSError, ValueError) as exc:
        details = [f"active runtime receipt is unreadable: {exc}"]
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
            "blockerKind": "runtime_receipt_unreadable",
        }

    active_status = str((active_attempt or {}).get("status") or "")
    active_workload = str((active_attempt or {}).get("workload") or "")
    if not active_attempt or active_status == "stopped":
        details = [f"no active {requested_workload} runtime requires teardown"]
    elif active_status == "running" and active_workload == "full":
        details = [
            f"{requested_workload} reused the full runtime; bounded teardown is a no-op",
            "the full startup receipt remains running",
        ]
    elif active_workload != requested_workload:
        details = [
            f"requested workload {requested_workload} does not own active runtime "
            + f"{active_workload or '<unknown>'}/{active_status or '<unknown>'}"
        ]
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "down",
                "target": args.target,
                "workload": requested_workload,
                "status": "gate_block",
                "blockerKind": "runtime_workload_mismatch",
                "startupAttempt": active_attempt,
                "details": details,
            },
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
            "blockerKind": "runtime_workload_mismatch",
        }
    else:
        return None

    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "workload": requested_workload,
            "status": "ok",
            "runtimeReused": active_workload == "full",
            "startupAttempt": active_attempt,
            "details": details,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="ok",
        summary=f"stackctl down completed for {args.target}",
        details=details,
        extra={
            "workload": requested_workload,
            "runtimeReused": active_workload == "full",
        },
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl down completed for {args.target}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "runtimeReused": active_workload == "full",
    }


def command_down(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    bounded_decision = _stackctl._bounded_workload_down_decision(args)
    if bounded_decision is not None:
        return bounded_decision
    if args.target not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        return _stackctl._command_down_unlocked(args)
    try:
        with _stackctl._local_stack_operation_lock(args.target):
            leases = _stackctl.active_consumer_leases(args.target)
            if leases:
                return _stackctl._consumer_lease_down_gate(args, leases)
            return _stackctl._command_down_unlocked(args)
    except RuntimeError as exc:
        topology = _stackctl.load_environment_topology()
        target = _stackctl.get_target(topology, args.target)
        report_dir = _stackctl.resolve_report_dir(
            args,
            str(target["env"]),
            args.target,
        )
        # 恢复动作必须与真实阻断同源：锁内操作自身失败（端口所有权投影、published
        # endpoint 释放探测等）与「锁被别的持有者占用」是两回事，混报成等待 lease
        # 会把操作员引向一个并不存在的持有者。
        lock_busy = isinstance(exc, _stackctl.LocalOperationLockBusyError)
        details = [
            str(exc),
            "wait for the active Patrol/UAT runtime lease to finish"
            if lock_busy
            else "resolve the reported failure before retrying stackctl down; "
            "no other operation holds the local runtime lock",
        ]
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "down",
                "target": args.target,
                "status": "gate_block",
                "blockerKind": "local_operation_lock_busy"
                if lock_busy
                else "down_operation_failed",
                "details": details,
            },
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="down",
            target=args.target,
            status="gate_block",
            summary=f"stackctl down is blocked for {args.target}",
            details=details,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }


def _bind_local_teardown_runtime(
    *,
    env_name: str,
    target_name: str,
    environment: dict[str, str],
    purge_rebuildable_state: bool,
) -> tuple[dict[str, Any], str, str, bool]:
    """Bind teardown to the exact startup receipt, without rebuilding identity."""
    import quwoquan_ops.cli.stackctl as _stackctl

    current_attempt = _stackctl.load_startup_attempt(target_name)
    if current_attempt is None:
        raise ValueError(
            "local teardown requires a canonical startup receipt; "
            "use an explicit repair action for orphaned resources"
        )
    if current_attempt.get("status") == "stopped" and not purge_rebuildable_state:
        # 停止一个已停止的运行时无事可做，所以普通 teardown 仍然要求非 stopped。
        #
        # 清理可重建状态不同：一次启动失败会自己回滚并把回执写成 stopped，而挡住
        # 下一次启动的数据卷仍留在原处（例如 pre-alias 物理索引占了读别名名）。
        # 把 stopped 一并拒掉，等于让唯一受支持的清理入口只在不需要它的时候可用，
        # 运营者只剩手工删卷一条路。stopped 回执携带的正是刚被拆掉那次运行的
        # composeProject/candidate/workload，清理因此依然是绑定的而非盲删。
        raise ValueError(
            "local teardown requires a non-stopped canonical startup receipt; "
            "use an explicit repair action for orphaned resources"
        )
    runtime_workload = str(
        current_attempt.get("workload") or "full"
    ).strip()
    if runtime_workload not in {
        "full",
        "content-release",
        "content-commercial",
    }:
        raise ValueError("runtime receipt workload is invalid")
    if current_attempt.get("status") == "prepared":
        if purge_rebuildable_state:
            raise ValueError(
                "prepared startup attempt has no rebuildable runtime state to purge"
            )
        environment["QWQ_WORKLOAD"] = runtime_workload
        environment["QWQ_PREPARED_ATTEMPT_ONLY"] = "1"
        return {}, "prepared-startup-receipt", "", True

    receipt_candidate = str(current_attempt.get("candidateDigest") or "").strip()
    candidate_root = _stackctl.deployment_candidate_dir(
        target_name,
        receipt_candidate,
    ).resolve()
    candidate_manifest = _stackctl.load_candidate_manifest(
        env_name,
        target_name,
        receipt_candidate,
        require_full=True,
        purpose="self_verify",
    )
    provider_runtime_binding = _stackctl._candidate_provider_runtime(
        env_name,
        target_name,
        receipt_candidate,
        candidate_manifest=candidate_manifest,
        candidate_root=candidate_root,
    )
    provider_runtime_environment = _stackctl._provider_runtime_launch_environment(
        provider_runtime_binding["providerRuntime"],
        candidate_root=provider_runtime_binding["candidateRoot"],
        workload=runtime_workload,
    )
    receipt_provider_digest = str(
        current_attempt.get("providerRuntimeDigest") or ""
    ).strip()
    if (
        receipt_provider_digest
        != provider_runtime_environment["QWQ_PROVIDER_RUNTIME_DIGEST"]
    ):
        raise ValueError(
            "runtime receipt Provider composition differs from active candidate"
        )
    environment.update(provider_runtime_environment)
    environment[_stackctl.RUNTIME_CANDIDATE_ROOT_ENV] = str(
        provider_runtime_binding["candidateRoot"]
    )
    environment["QWQ_RELEASE_CANDIDATE_DIGEST"] = receipt_candidate
    observability_runtime_binding = _stackctl._candidate_observability_log_sink(
        env_name,
        target_name,
        receipt_candidate,
        candidate_manifest=candidate_manifest,
        candidate_root=candidate_root,
    )
    environment.update(
        _stackctl._observability_log_sink_launch_environment(
            observability_runtime_binding["composition"],
            environment_name=env_name,
            target_name=target_name,
            candidate_root=observability_runtime_binding["candidateRoot"],
            workload=runtime_workload,
        )
    )
    receipt_log_sink_digest = str(
        current_attempt.get("observabilityLogSinkDigest") or ""
    ).strip()
    expected_log_sink_digest = str(
        environment.get("QWQ_OBSERVABILITY_LOG_SINK_DIGEST") or ""
    ).strip()
    if (
        receipt_log_sink_digest != expected_log_sink_digest
    ):
        raise ValueError(
            "runtime receipt observability composition differs from active candidate"
        )
    environment["QWQ_WORKLOAD"] = runtime_workload
    runtime_receipt = _stackctl._load_gamma_runtime_image_composition(
        target_name,
        include_stopped=purge_rebuildable_state,
    )
    if runtime_receipt is None:
        raise ValueError("local teardown requires an exact runtime receipt")

    release_composition, compose_project = runtime_receipt
    environment["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"] = compose_project
    _stackctl._apply_gamma_image_composition(release_composition, environment)
    return release_composition, "runtime-receipt", compose_project, False


def _receipt_bound_local_compose_model(
    *,
    environment_name: str,
    target_name: str,
    workload: str,
    compose_project: str,
    environment: dict[str, str],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    candidate_value = str(
        environment.get(_stackctl.RUNTIME_CANDIDATE_ROOT_ENV) or ""
    ).strip()
    candidate_path = Path(candidate_value).expanduser()
    if (
        not candidate_value
        or not candidate_path.is_absolute()
        or candidate_path.is_symlink()
        or not candidate_path.is_dir()
    ):
        raise ValueError("receipt-bound runtime candidate root is unavailable")
    candidate_root = candidate_path.resolve()
    shared_root = candidate_root / "packages/runtime-shared"
    candidate_sources = {
        "LOCAL_GAMMA_CADDYFILE": shared_root / "Caddyfile",
        "LOCAL_GAMMA_LIVEKIT_CONFIG_FILE": shared_root / "livekit.yaml",
        "LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE": (
            shared_root / "object-storage-lifecycle.json"
        ),
        "QWQ_COMPOSE_REC_POLICY_SOURCE": (
            shared_root / "runtime-topology/policies/recommendation_policy.yaml"
        ),
    }
    legal_root = candidate_root / "packages/legal-static/current/public"
    for name, source in candidate_sources.items():
        if not source.is_file() or source.is_symlink():
            raise ValueError(
                f"receipt-bound candidate Compose source is unavailable: {name}"
            )
        environment[name] = str(source)
    if not legal_root.is_dir() or legal_root.is_symlink():
        raise ValueError(
            "receipt-bound candidate Compose source is unavailable: "
            "LOCAL_GAMMA_LEGAL_STATIC_ROOT"
        )
    environment["LOCAL_GAMMA_RUNTIME_SHARED_ROOT"] = str(shared_root)
    environment["LOCAL_GAMMA_LEGAL_STATIC_ROOT"] = str(legal_root)

    # These sources are required only so `docker compose config` can project
    # published ports.  They are not candidate identity and are never mounted
    # or started by teardown, so use explicit deterministic non-existent paths.
    placeholder_root = Path(
        f"/nonexistent/quwoquan-teardown-port-projection/{target_name}"
    )
    environment.update(
        {
            "LOCAL_GAMMA_MEDIA_ROOT": str(placeholder_root / "media"),
            "LOCAL_GAMMA_PORTAL_ROOT": str(placeholder_root / "portal"),
            "LOCAL_GAMMA_PUBLIC_WEB_ROOT": str(placeholder_root / "public-web"),
            "QWQ_COMPOSE_CONFIG_ROOT": str(placeholder_root / "config-root"),
            "QWQ_PUBLIC_TLS_CERT_FILE": str(placeholder_root / "tls.crt"),
            "QWQ_PUBLIC_TLS_KEY_FILE": str(placeholder_root / "tls.key"),
            "QWQ_PUBLIC_WEB_CONTENT_DIGEST": f"sha256:{'0' * 64}",
        }
    )
    topology = _stackctl.load_runtime_topology_package(
        candidate_root,
        environment=environment_name,
        target=target_name,
        workload=workload,
    )
    compose_files = list(topology["composeFiles"])
    profiles: list[str] = []
    if workload == "full":
        provider_files = [
            Path(value)
            for value in str(
                environment.get("QWQ_PROVIDER_RUNTIME_COMPOSE_FILES") or ""
            ).splitlines()
            if value.strip()
        ]
        provider_profiles = [
            value.strip()
            for value in str(
                environment.get("QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES") or ""
            ).split(",")
            if value.strip()
        ]
        if not provider_files or not provider_profiles:
            raise ValueError(
                "receipt-bound full runtime Provider Compose closure is incomplete"
            )
        compose_files.extend(provider_files)
        profiles.extend(
            (
                *sorted(_stackctl.FULL_WORKLOAD_COMPOSE_PROFILES),
                *provider_profiles,
            )
        )
    elif workload == "content-commercial":
        profiles.extend(sorted(_stackctl.CONTENT_COMMERCIAL_COMPOSE_PROFILES))
    elif workload != "content-release":
        raise ValueError("receipt-bound runtime workload is unsupported")

    if workload in {"full", "content-commercial"}:
        observability_file = str(
            environment.get("QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE") or ""
        ).strip()
        if not observability_file:
            raise ValueError(
                "receipt-bound observability Compose artifact is unavailable"
            )
        compose_files.append(Path(observability_file))

    # CONFIG_VERSION keys come from the exact candidate Compose closure, never
    # the current workspace or mutable active pointer.  Values are irrelevant
    # to published-port projection and therefore deterministic placeholders.
    for compose_file in compose_files:
        body = compose_file.read_text(encoding="utf-8")
        for key in set(re.findall(r"QWQ_COMPOSE_[A-Z_]+_CONFIG_VERSION", body)):
            environment.setdefault(key, "down-not-used")

    for source_name, value in tuple(environment.items()):
        if source_name.startswith("LOCAL_GAMMA_"):
            environment[
                "QWQ_COMPOSE_" + source_name.removeprefix("LOCAL_GAMMA_")
            ] = value
    environment["QWQ_COMPOSE_ENV"] = environment_name
    environment["COMPOSE_PROFILES"] = ""
    command = [
        "docker",
        "compose",
        "-p",
        compose_project,
        *_stackctl.compose_file_args(compose_files),
    ]
    for profile in profiles:
        command.extend(("--profile", profile))
    result = _stackctl.run(
        [*command, "config", "--format", "json"],
        env=environment,
        timeout_seconds=90,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or (
            f"exit={result.returncode}"
        )
        raise RuntimeError(f"receipt-bound Compose model rendering failed: {detail}")
    try:
        compose_model = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("receipt-bound Compose model is not valid JSON") from exc
    if not isinstance(compose_model, Mapping):
        raise ValueError("receipt-bound Compose model must be a JSON object")
    return dict(compose_model)


def _command_down_unlocked(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    formal_release = bool(getattr(args, "formal_release", False))
    purge_rebuildable_state = bool(
        getattr(args, "purge_rebuildable_state", False)
    )
    release_composition: dict[str, Any] = {}
    runtime_composition_source = ""
    runtime_compose_project = ""
    prepared_attempt_only = False
    runtime_owned_port_report: dict[str, Any] | None = None

    if (
        not formal_release
        and args.target in {"alpha-local", "beta-local", "gamma-local"}
    ):
        try:
            mutable_attempt = _stackctl.load_test_live_startup_attempt(args.target)
            immutable_attempt = _stackctl.load_startup_attempt(args.target)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            mutable_attempt = None
            immutable_attempt = None
            selection_issue = f"runtime receipt is unreadable: {exc}"
        else:
            selection_issue = ""
        mutable_status = str((mutable_attempt or {}).get("status") or "")
        immutable_status = str((immutable_attempt or {}).get("status") or "")
        if mutable_attempt and mutable_status != "stopped":
            if selection_issue:
                pass
            elif immutable_attempt and immutable_status != "stopped":
                if mutable_status == "partial" and not purge_rebuildable_state:
                    return _stackctl._command_mutable_test_live_down(
                        args,
                        env_name=env_name,
                        report_dir=report_dir,
                        receipt=mutable_attempt,
                        allow_active_immutable_ports=True,
                    )
                selection_issue = (
                    "mutable and immutable runtime receipts are both active; "
                    "teardown identity is ambiguous"
                )
            elif purge_rebuildable_state:
                selection_issue = (
                    "mutable test-live teardown never permits rebuildable-state purge"
                )
            elif mutable_status not in {"partial", "running"}:
                selection_issue = (
                    "mutable test-live teardown requires a canonical partial or running receipt; "
                    f"current status is {mutable_status or '<unknown>'}"
                )
            else:
                return _stackctl._command_mutable_test_live_down(
                    args,
                    env_name=env_name,
                    report_dir=report_dir,
                    receipt=mutable_attempt,
                )
        if selection_issue:
            details = [selection_issue]
            _stackctl.write_json(
                report_dir / "report.json",
                {
                    "command": "down",
                    "target": args.target,
                    "workload": str(getattr(args, "workload", "") or "full"),
                    "status": "gate_block",
                    "exitCode": 2,
                    "blockerKind": "runtime_teardown_identity_ambiguous",
                    "mutableStartupAttempt": mutable_attempt,
                    "immutableStartupAttempt": immutable_attempt,
                    "details": details,
                },
            )
            _stackctl._write_summary_bundle(
                report_dir,
                command="down",
                target=args.target,
                status="gate_block",
                summary=f"stackctl down is GATE_BLOCK for {args.target}",
                details=details,
                extra={"blockerKind": "runtime_teardown_identity_ambiguous"},
            )
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": details,
                "reportDir": _stackctl.relpath(report_dir),
                "blockerKind": "runtime_teardown_identity_ambiguous",
            }

    if purge_rebuildable_state and (
        formal_release
        or args.target not in {"alpha-local", "beta-local", "gamma-local"}
    ):
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": [
                "rebuildable-state purge is only available for non-formal Alpha/Beta/Gamma local teardown"
            ],
        }

    if formal_release:
        manifest_value = str(getattr(args, "release_manifest", "") or "").strip()
        if args.target not in {"alpha-local", "beta-local", "gamma-local"}:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": ["formal teardown supports only Alpha/Beta/Gamma local targets"],
            }
        if not manifest_value:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": ["formal teardown requires --release-manifest"],
            }
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": [
                (
                    "formal local teardown is blocked until the release artifact owns "
                    "one complete first-party and Provider OCI composition plus the "
                    "exact startup receipt/Compose project identity"
                )
            ],
        }
    elif args.target in {"alpha-local", "beta-local", "gamma-local"}:
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh", "--down"]
        port_manifest = _stackctl.load_port_manifest()
        env = _stackctl._gamma_env_from_port_manifest(
            topology,
            args.target,
            manifest=port_manifest,
        )
        env[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = ""
        try:
            (
                release_composition,
                runtime_composition_source,
                runtime_compose_project,
                prepared_attempt_only,
            ) = _stackctl._bind_local_teardown_runtime(
                env_name=env_name,
                target_name=args.target,
                environment=env,
                purge_rebuildable_state=purge_rebuildable_state,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": [
                    f"{args.target} teardown requires a canonical non-stopped runtime receipt",
                    str(exc),
                ],
            }
        _stackctl._bind_gamma_down_parse_environment(env, receipt_bound=True)
        if not prepared_attempt_only:
            try:
                runtime_workload = str(env.get("QWQ_WORKLOAD") or "").strip()
                compose_model = _stackctl._receipt_bound_local_compose_model(
                    environment_name=env_name,
                    target_name=args.target,
                    workload=runtime_workload,
                    compose_project=runtime_compose_project,
                    environment=env,
                )
                declared_port_profile = str(
                    _stackctl.get_target(topology, args.target).get("portProfile") or ""
                ).strip()
                if not declared_port_profile:
                    raise ValueError(
                        f"{args.target} declares no portProfile in the environment topology"
                    )
                published_endpoints = _stackctl.project_compose_published_endpoints(
                    port_profile=declared_port_profile,
                    compose_model=compose_model,
                    manifest=port_manifest,
                )
                runtime_owned_port_report = (
                    _stackctl._runtime_owned_port_occupancy_report(
                        args.target,
                        published_ports=published_endpoints,
                        topology=topology,
                        manifest=port_manifest,
                    )
                )
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                details = [
                    f"{args.target} runtime port ownership is invalid: {exc}"
                ]
                _stackctl.write_json(
                    report_dir / "report.json",
                    {
                        "command": "down",
                        "target": args.target,
                        "status": "gate_block",
                        "exitCode": 2,
                        "blockerKind": "runtime_port_ownership_invalid",
                        "details": details,
                    },
                )
                _stackctl._write_summary_bundle(
                    report_dir,
                    command="down",
                    target=args.target,
                    status="gate_block",
                    summary=f"stackctl down is GATE_BLOCK for {args.target}",
                    details=details,
                    extra={"blockerKind": "runtime_port_ownership_invalid"},
                )
                return {
                    "exitCode": 2,
                    "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                    "details": details,
                    "reportDir": _stackctl.relpath(report_dir),
                    "blockerKind": "runtime_port_ownership_invalid",
                }
        if purge_rebuildable_state:
            cmd.append("--purge-rebuildable-state")
        runtime_result = _stackctl.run(cmd, env=env)
        if runtime_result.returncode == 0 and purge_rebuildable_state:
            shutil.rmtree(_stackctl.target_cache_dir(args.target), ignore_errors=True)
        app_cmd: list[str] = []
        if prepared_attempt_only:
            app_result = subprocess.CompletedProcess(
                [],
                0,
                stdout="prepared attempt had no App/runtime resources",
                stderr="",
            )
        else:
            app_cmd = [
                "bash",
                "quwoquan_app/scripts/device/run_stop_app_instance.sh",
                "--env",
                env_name,
                "--quiet",
            ]
            app_result = _stackctl.run(app_cmd)
            cmd = [*cmd, "&&", *app_cmd]
        result = next(
            (
                candidate
                for candidate in (runtime_result, app_result)
                if candidate.returncode != 0
            ),
            runtime_result,
        )
    elif args.target == "prod-sim":
        app_cmd = [
            "bash",
            "quwoquan_app/scripts/device/run_stop_app_instance.sh",
            "--env",
            "prod",
        ]
        app_result = _stackctl.run(app_cmd)
        stack_cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "down"]
        stack_result = _stackctl.run(stack_cmd)
        cmd = [*app_cmd, "&&", *stack_cmd]
        result = stack_result if stack_result.returncode != 0 else app_result
    else:
        return {
            "exitCode": 2,
            "summary": f"stackctl down is not implemented for {args.target}",
            "details": ["hosted targets should be rolled back or redeployed via deploy commands"],
        }

    resource_release_issues: list[str] = []
    startup_receipt: dict[str, Any] | None = None
    if result.returncode == 0 and not prepared_attempt_only:
        if args.target in {"alpha-local", "beta-local", "gamma-local"}:
            if runtime_owned_port_report is None:
                raise RuntimeError(
                    f"GATE_BLOCK: {args.target} runtime port ownership was not projected"
                )
            runtime_owned_endpoints = [
                {
                    "role": str(item["role"]),
                    "hostPort": int(item["hostPort"]),
                    "protocol": str(item["protocol"]),
                }
                for item in runtime_owned_port_report["publishedEndpoints"]
            ]
            occupied_endpoints = (
                _stackctl._wait_for_published_endpoints_released(
                    runtime_owned_endpoints
                )
            )
            resource_release_issues = [
                "runtime-owned endpoint remains occupied after down: "
                f"{endpoint['role']}:{endpoint['hostPort']}/{endpoint['protocol']}"
                for endpoint in occupied_endpoints
            ]
        else:
            occupied = _stackctl._wait_for_network_ports_released(
                args.target,
                port_reporter=_stackctl._canonical_port_occupancy_report,
            )
            resource_release_issues = [
                f"canonical port remains occupied after down: {item['name']}:{item['port']}"
                for item in occupied
            ]
        if resource_release_issues:
            result = subprocess.CompletedProcess(
                result.args,
                2,
                stdout=result.stdout,
                stderr="\n".join(resource_release_issues),
            )
    if result.returncode == 0 and args.target in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        try:
            current_attempt = _stackctl.load_startup_attempt(args.target)
            if current_attempt and current_attempt.get("status") != "stopped":
                startup_receipt = _stackctl.transition_startup_attempt(
                    env=env_name,
                    target=args.target,
                    attempt_id=str(current_attempt.get("attemptId") or ""),
                    status="stopped",
                    failure="",
                    cleanup_failure="",
                )
            else:
                startup_receipt = current_attempt
        except ValueError as exc:
            resource_release_issues.append(
                f"startup attempt stopped receipt failed: {exc}"
            )
            result = subprocess.CompletedProcess(
                result.args,
                2,
                stdout=result.stdout,
                stderr="\n".join(resource_release_issues),
            )

    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "formalRelease": formal_release,
            "releaseComposition": release_composition,
            "runtimeMode": "immutable-oci" if formal_release else (
                "immutable-local" if release_composition else ""
            ),
            "runtimeCompositionSource": runtime_composition_source,
            "destructiveRepairPerformed": (
                purge_rebuildable_state and result.returncode == 0
            ),
            "destructiveActions": (
                [
                    f"purge-compose-volumes:{runtime_compose_project}",
                    f"purge-target-cache:{args.target}",
                ]
                if purge_rebuildable_state and result.returncode == 0
                else []
            ),
            "resourceReleaseIssues": resource_release_issues,
            "startupAttempt": startup_receipt,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        details=_stackctl._command_details(result),
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        "details": _stackctl._command_details(result),
        "reportDir": _stackctl.relpath(report_dir),
    }

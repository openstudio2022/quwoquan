"""stackctl dev-session 运行时输入域: mutable workspace 快照、compose 物化
与 runtime 输入渲染。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- 会话状态: `_dev_session_child_args` / `_dev_session_phase` /
  `_dev_session_active_receipts` / `_dev_session_runtime_preflight` /
  `_dev_session_workload_conflict` / `_dev_session_compose_project`;
- workspace 与身份: `_mutable_workspace_snapshot` /
  `_mutable_test_live_operation_identity_environment`;
- compose 与输入: `_materialize_local_portal_root` /
  `_dev_session_target_media_root` / `_dev_session_render_runtime_inputs`
  （Compose 闭包解析与物化归 `dev_session_compose.py`）。

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
import shlex
import shutil
import subprocess

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Mapping
from uuid import uuid4


def _dev_session_child_args(
    command: str,
    *,
    report_dir: Path,
    argv: list[str],
) -> argparse.Namespace:
    import quwoquan_ops.cli.stackctl as _stackctl

    return _stackctl.build_parser().parse_args(
        [
            "--output-format",
            "json",
            "--report-dir",
            str(report_dir),
            command,
            *argv,
        ]
    )


def _dev_session_phase(
    name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "exitCode": int(payload.get("exitCode", 1)),
        "summary": str(payload.get("summary") or ""),
        "details": list(payload.get("details") or []),
        "reportDir": str(payload.get("reportDir") or ""),
    }


class InadmissibleCurrentTestLiveReceipt(ValueError):
    """当前 mutable target 持有可界定、但已不再可接纳的旧代际 receipt。"""

    def __init__(self, target: str, detail: str) -> None:
        super().__init__(
            f"{target} current test-live startup receipt is inadmissible: {detail}"
        )
        self.target = target
        self.detail = detail


def _mutable_test_live_target(topology: Mapping[str, Any], target: str) -> bool:
    """仅 Alpha/Beta/Gamma canonical local target 拥有 test-live receipt。"""

    targets = topology.get("targets")
    if not isinstance(targets, Mapping):
        raise RuntimeError("environment topology targets must be a mapping")
    contract = targets.get(target)
    if not isinstance(contract, Mapping):
        raise RuntimeError(f"unknown local runtime target: {target}")
    environment = str(contract.get("env") or "").strip()
    return (
        environment in {"alpha", "beta", "gamma"}
        and target == f"{environment}-local"
        and str(contract.get("backend") or "").strip() == "local"
        and str(contract.get("portProfile") or "").strip() == target
    )


def _load_test_live_attempt_for_preflight(
    target: str,
    *,
    current_target: bool,
) -> dict[str, Any] | None:
    """读取 mutable receipt；仅把当前 target 的 bounded 旧代际标成可替换。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        return _stackctl.load_test_live_startup_attempt(target)
    except ValueError as original:
        if not current_target:
            raise
        try:
            stale = _stackctl.read_stale_test_live_startup_attempt(target)
            if stale is None:
                raise original
            _stackctl.require_bounded_stale_test_live_startup_attempt(target, stale)
        except (OSError, RuntimeError, TypeError, ValueError):
            raise original
        raise InadmissibleCurrentTestLiveReceipt(target, str(original)) from original


def _dev_session_active_receipts(
    topology: Mapping[str, Any],
    target: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """按 target 的 canonical authority 返回当前 active 共享资源冲突。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    if not _mutable_test_live_target(topology, target):
        raise ValueError(f"mutable dev-session target is not admissible: {target}")

    requested_attempt: dict[str, Any] | None = None
    active: list[dict[str, Any]] = []
    mutable_targets: list[str] = [target]
    for candidate in _stackctl.local_runtime_peer_targets(topology, target):
        if _mutable_test_live_target(topology, candidate):
            mutable_targets.append(candidate)
    for candidate in mutable_targets:
        target_attempt = _stackctl.load_startup_attempt(candidate)
        test_live_attempt = _load_test_live_attempt_for_preflight(
            candidate,
            current_target=candidate == target,
        )
        if candidate == target:
            requested_attempt = target_attempt
            if (
                test_live_attempt is not None
                and (
                    requested_attempt is None
                    or requested_attempt.get("status") == "stopped"
                )
            ):
                requested_attempt = test_live_attempt
        candidate_attempts: list[tuple[str, dict[str, Any]]] = []
        if target_attempt and target_attempt.get("status") != "stopped":
            candidate_attempts.append(("target", target_attempt))
        if test_live_attempt and test_live_attempt.get("status") != "stopped":
            candidate_attempts.append(("test-live", test_live_attempt))
        for workload in _stackctl._DEV_SESSION_WORKLOADS:
            scoped_attempt = _stackctl.load_workload_startup_attempt(candidate, workload)
            if not scoped_attempt or scoped_attempt.get("status") == "stopped":
                continue
            candidate_attempts.append((f"workload:{workload}", scoped_attempt))

        seen: set[tuple[str, str, str]] = set()
        for receipt_scope, attempt in candidate_attempts:
            workload = str(attempt.get("workload") or "").strip()
            attempt_id = str(attempt.get("attemptId") or "").strip()
            status = str(attempt.get("status") or "").strip()
            identity = (attempt_id, workload, status)
            if identity in seen:
                continue
            seen.add(identity)
            active.append(
                {
                    "target": candidate,
                    "workload": workload,
                    "attemptId": attempt_id,
                    "status": status,
                    "receiptScope": receipt_scope,
                }
            )

    occupied_peers = _stackctl.active_conflicting_local_targets(topology, target)
    for candidate in occupied_peers:
        if _mutable_test_live_target(topology, candidate):
            continue
        active.append(
            {
                "target": candidate,
                "workload": "canonical-occupancy",
                "attemptId": f"{candidate}-canonical-occupancy",
                "status": "running",
                "receiptScope": "canonical-occupancy",
            }
        )
    return requested_attempt, active


def _bounded_replace_stale_managed_receipt(
    *,
    target: str,
) -> dict[str, Any]:
    """Retire one stale process receipt only after proving no live runtime.

    A retired test-live field set cannot authorize normal down, but managed
    startup still needs one bounded path forward. The process receipt is
    replaceable only when no consumer, container, network, or canonical target
    endpoint remains; otherwise the governed down/orphan repair path keeps
    ownership and startup stays fail-closed.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    leases = _stackctl.active_consumer_leases(target)
    if leases:
        raise ValueError("stale mutable startup receipt still has live consumer leases")
    environment = target.removesuffix("-local")
    compose_project = _stackctl._dev_session_compose_project(environment, target)
    containers = _stackctl._mutable_test_live_container_ids(compose_project)
    networks = _stackctl._mutable_test_live_resource_names(
        "network", compose_project=compose_project
    )
    topology = _stackctl.load_environment_topology()
    manifest = _stackctl.load_port_manifest()
    occupancy = _stackctl._runtime_owned_port_occupancy_report(
        target,
        published_ports=_stackctl.project_canonical_runtime_owned_ports(
            port_profile=target,
            manifest=manifest,
        ),
        topology=topology,
        manifest=manifest,
    )
    occupied = [
        endpoint
        for endpoint in occupancy.get("publishedEndpoints") or []
        if endpoint.get("open") is True
    ]
    if containers or networks or occupied:
        raise ValueError(
            "stale mutable startup receipt still describes live runtime residue"
        )
    return _stackctl.bounded_replace_stale_test_live_startup_attempt(target)


def _dev_session_runtime_preflight(
    *,
    topology: Mapping[str, Any],
    target: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    import quwoquan_ops.cli.stackctl as _stackctl

    requested_attempt, active = _stackctl._dev_session_active_receipts(topology, target)
    allowed_full = (
        requested_attempt
        if requested_attempt
        and requested_attempt.get("status") == "running"
        and requested_attempt.get("workload") == "full"
        else None
    )
    for attempt in active:
        if (
            allowed_full is not None
            and attempt["target"] == target
            and attempt["workload"] == "full"
            and attempt["status"] == "running"
            and attempt["attemptId"] == str(allowed_full.get("attemptId") or "").strip()
        ):
            continue
        return allowed_full, attempt
    return allowed_full, None


def _dev_session_workload_conflict(
    conflict: Mapping[str, Any],
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    active_target = str(conflict.get("target") or "<unknown>")
    active_workload = str(conflict.get("workload") or "<unknown>")
    active_attempt = str(conflict.get("attemptId") or "<unknown>")
    active_status = str(conflict.get("status") or "<unknown>")
    recovery = [
        "python3",
        "quwoquan_ops/cli/stackctl.py",
        "down",
        "--target",
        active_target,
    ]
    if active_workload in _stackctl._DEV_SESSION_WORKLOADS:
        recovery.extend(("--workload", active_workload))
    recovery_command = " ".join(shlex.quote(item) for item in recovery)
    active_runtime = {
        "target": active_target,
        "workload": active_workload,
        "attemptId": active_attempt,
        "status": active_status,
        "receiptScope": str(conflict.get("receiptScope") or ""),
    }
    return {
        "exitCode": 2,
        "sessionKind": "cold",
        "blockerKind": "runtime_workload_conflict",
        "activeRuntime": active_runtime,
        "fullRuntimeSelected": False,
        "details": [
            f"activeTarget={active_target}",
            f"activeWorkload={active_workload}",
            f"activeAttemptId={active_attempt}",
            f"activeStatus={active_status}",
            f"recoveryCommand={recovery_command}",
        ],
        "phases": [],
    }


def _mutable_workspace_snapshot() -> dict[str, Any]:
    """Return a fast warning-only identity for a mutable test session.

    Immutable package hashing intentionally walks every deployment input.  A
    test-live launch must not inherit that cost, so this identity binds HEAD,
    porcelain status, and the size/mtime of every currently dirty path.  It is
    sufficient to detect an in-session mutation and is never accepted as a
    production package identity.
    """
    import quwoquan_ops.cli.stackctl as _stackctl


    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_stackctl.ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            "quwoquan_app",
            "quwoquan_service",
            "quwoquan_ops",
        ],
        cwd=_stackctl.ROOT,
        text=False,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if revision.returncode != 0 or status.returncode != 0:
        raise RuntimeError(
            revision.stderr.strip()
            or os.fsdecode(status.stderr).strip()
            or "mutable workspace identity command failed"
        )
    state_digest = hashlib.sha256(status.stdout)
    for raw_record in status.stdout.split(b"\0"):
        if len(raw_record) < 4:
            continue
        relative = os.fsdecode(raw_record[3:])
        path = _stackctl.ROOT / relative
        try:
            metadata = path.stat()
        except OSError:
            continue
        state_digest.update(relative.encode("utf-8"))
        state_digest.update(str(metadata.st_size).encode("ascii"))
        state_digest.update(str(metadata.st_mtime_ns).encode("ascii"))
    return {
        "sourceRevision": revision.stdout.strip(),
        "workspaceStatusDigest": "sha256:" + hashlib.sha256(status.stdout).hexdigest(),
        "mutableStateDigest": "sha256:" + state_digest.hexdigest(),
    }


def _dev_session_compose_project(environment: str, target: str) -> str:
    """Return the one mutable project identity owned by a nonprod target."""

    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError("mutable test_live only supports Alpha, Beta, and Gamma")
    if target != f"{environment}-local":
        raise ValueError("mutable test_live target does not belong to environment")
    project = f"quwoquan_{environment}_test_live"
    if re.fullmatch(r"quwoquan_(?:alpha|beta|gamma)_test_live", project) is None:
        raise ValueError("mutable test_live Compose project is not canonical")
    return project


def _mutable_test_live_operation_identity_environment(
    *,
    environment: str,
    target: str,
    mutable_state_digest: str,
    api_edge_config_version: str,
) -> dict[str, str]:
    """Materialize the target-bound non-promotable API operation identity."""
    import quwoquan_ops.cli.stackctl as _stackctl


    _stackctl._dev_session_compose_project(environment, target)
    for label, digest in (
        ("mutable state", mutable_state_digest),
        ("api-edge config", api_edge_config_version),
    ):
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest or "")) is None:
            raise ValueError(f"mutable test_live {label} digest is invalid")
    return {
        # Compose fragments that consume release-scoped caches still require a
        # candidate identity.  test_live has no immutable release candidate,
        # so bind those caches to the exact non-promotable mutable snapshot.
        "QWQ_RELEASE_CANDIDATE_DIGEST": mutable_state_digest,
        "QWQ_RUNTIME_IDENTITY_SCHEMA": "stackctl.mutable_test_live_runtime",
        "QWQ_RUNTIME_LAUNCH_POLICY": "test_live",
        "QWQ_RUNTIME_NON_PROMOTABLE": "true",
        "QWQ_RUNTIME_ENVIRONMENT": environment,
        "QWQ_RUNTIME_TARGET": target,
        "QWQ_RUNTIME_MUTABLE_STATE_DIGEST": mutable_state_digest,
        "QWQ_RUNTIME_CONFIGURATION_DIGEST": api_edge_config_version,
    }


def _dev_session_target_media_root(
    *,
    target: str,
    target_contract: Mapping[str, Any],
) -> tuple[str, Path]:
    import quwoquan_ops.cli.stackctl as _stackctl

    data_release = target_contract.get("dataRelease")
    if not isinstance(data_release, Mapping) or data_release.get("mode") != "local-import":
        raise ValueError("mutable test_live target must declare local-import dataRelease")
    media_local_ref = str(data_release.get("mediaLocalRef") or "").strip()
    media_relative = Path(media_local_ref)
    if (
        not media_local_ref
        or media_relative.is_absolute()
        or media_relative == Path(".")
        or any(part in {"", ".", ".."} for part in media_relative.parts)
    ):
        raise ValueError(
            "mutable test_live dataRelease.mediaLocalRef must be a safe target-local path"
        )
    target_local_root = _stackctl.target_local_dir(target).expanduser()
    target_local_root.mkdir(parents=True, exist_ok=True)
    canonical_target_root = target_local_root.resolve()
    candidate_media_root = target_local_root / media_relative
    current_path = target_local_root
    for part in media_relative.parts:
        current_path /= part
        if current_path.is_symlink():
            raise ValueError(
                "mutable test_live dataRelease.mediaLocalRef contains a symlink"
            )
    candidate_media_root.mkdir(parents=True, exist_ok=True)
    media_root = candidate_media_root.resolve()
    try:
        media_root.relative_to(canonical_target_root)
    except ValueError as exc:
        raise ValueError(
            "mutable test_live dataRelease.mediaLocalRef escapes target-local root"
        ) from exc
    return media_local_ref, media_root


def _dev_session_finalize_runtime_plan(
    *,
    runtime_plan: Mapping[str, Any],
    compose_model: Mapping[str, object],
    report_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    plan = dict(runtime_plan)
    if plan.get("schema") != "stackctl.mutable_test_live_runtime":
        raise ValueError("mutable test_live runtime plan schema mismatch")
    port_profile = str(plan.get("portProfile") or "").strip()
    if not port_profile:
        raise ValueError("mutable test_live runtime port profile is required")
    if "publishedPorts" in plan:
        raise ValueError(
            "mutable test_live published ports must come from the Compose model"
        )
    resolved_manifest = manifest if manifest is not None else _stackctl.load_port_manifest()
    published_endpoints = _stackctl.project_compose_published_endpoints(
        port_profile=port_profile,
        compose_model=compose_model,
        manifest=resolved_manifest,
    )
    _stackctl.project_runtime_owned_ports(
        port_profile=port_profile,
        published_ports=published_endpoints,
        manifest=resolved_manifest,
    )
    plan["publishedPorts"] = published_endpoints
    plan_path = report_dir / "mutable-runtime-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = plan_path.with_name(f".{plan_path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, plan_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return plan


def _mutable_observability_log_sink_launch_environment(
    *,
    execution_path: Path,
    composition: Mapping[str, Any],
) -> dict[str, str]:
    """Bind mutable launch identity to the exact rendered Compose bytes."""

    expected_bytes = composition.get("composeBytes")
    if not isinstance(expected_bytes, bytes):
        raise ValueError("mutable observability log-sink composition bytes are missing")
    execution_bytes = execution_path.read_bytes()
    if execution_bytes != expected_bytes:
        raise ValueError(
            "mutable observability log-sink source/execution composition drifted"
        )
    digest = "sha256:" + hashlib.sha256(execution_bytes).hexdigest()
    return {
        "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE": str(execution_path),
        "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": digest,
    }


def _dev_session_render_runtime_inputs(
    *,
    environment: str,
    target: str,
    report_dir: Path,
    workspace_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Render current source/config and target-owned secret material for test_live."""
    import quwoquan_ops.cli.stackctl as _stackctl


    from quwoquan_ops.cli.render_runtime_config import render_workload

    topology = _stackctl.load_environment_topology()
    target_contract = _stackctl.get_target(topology, target)
    if str(target_contract.get("env") or "") != environment:
        raise ValueError("mutable test_live topology target/environment mismatch")
    profile_name = str(target_contract.get("portProfile") or "")
    if profile_name != target:
        raise ValueError("mutable test_live target must own its canonical port profile")
    public_web_package, public_web_artifact_root = (
        _stackctl._resolve_dev_session_public_web_package(
            environment=environment,
            target=target,
            target_contract=target_contract,
        )
    )
    manifest = _stackctl.load_port_manifest()
    profile = manifest.get("profiles", {}).get(profile_name)
    if not isinstance(profile, dict):
        raise ValueError("mutable test_live canonical port block is missing")
    block_start = int(profile.get("blockStart", -1))
    block_end = int(profile.get("blockEnd", -1))
    ports = _stackctl.profile_ports(manifest, profile_name)
    if (
        block_start < 1
        or block_end <= block_start
        or any(port < block_start or port > block_end for port in ports.values())
    ):
        raise ValueError("mutable test_live port projection escapes target block")

    media_local_ref, media_root = _stackctl._dev_session_target_media_root(
        target=target,
        target_contract=target_contract,
    )

    provider_composition = _stackctl.compile_provider_runtime_composition(
        environment=environment,
        target=target,
    )
    compose_files, compose_profiles = _stackctl._dev_session_source_compose_files(
        environment=environment,
        target=target,
        provider_composition=provider_composition,
    )
    local_elasticsearch_source = next(
        (
            path
            for path in compose_files
            if path.relative_to(_stackctl.ROOT).as_posix()
            == (
                "quwoquan_service/services/product-ops-service/deploy/"
                "local-elasticsearch.compose.yaml"
            )
        ),
        None,
    )
    if local_elasticsearch_source is None:
        raise ValueError("mutable observability log-sink Compose source is missing")
    observability_composition = (
        _stackctl.canonical_local_observability_log_sink_composition(
            local_elasticsearch_source
        )
    )
    selection = observability_composition["selection"]
    compose_digest = "sha256:" + hashlib.sha256(
        b"".join(
            len(path.relative_to(_stackctl.ROOT).as_posix().encode("utf-8")).to_bytes(8, "big")
            + path.relative_to(_stackctl.ROOT).as_posix().encode("utf-8")
            + len(path.read_bytes()).to_bytes(8, "big")
            + path.read_bytes()
            for path in compose_files
        )
    ).hexdigest()

    render_root = report_dir / "mutable-runtime"
    execution_compose_root = render_root / "compose"
    config_root = render_root / "config-root"
    shared_root = render_root / "runtime-shared"
    legal_root = render_root / "legal"
    portal_root = render_root / "portal"
    for directory in (
        execution_compose_root,
        config_root / "quwoquan_service/runtime/reliabletask/resources",
        shared_root,
        legal_root,
        portal_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    from quwoquan_ops.cli.lib.dev_session_web_runtime_config import (
        materialize_dev_session_web_runtime_config,
    )

    public_web_root = render_root / "public-web-hosting"
    runtime_config_digests = materialize_dev_session_web_runtime_config(
        repo_root=_stackctl.ROOT,
        environment=environment,
        target=target,
        artifact_root=public_web_artifact_root,
        hosting_root=public_web_root,
        source_revision=str(workspace_snapshot.get("sourceRevision") or ""),
        run_command=_stackctl.run,
    )

    # mutable test-live 镜像由 compose build 从当前工作树构建，Dockerfile 依赖
    # named build context `qwq_provider_bindings`（与 immutable package 同一
    # 编译产物形态），因此 render 时从源码编译并物化 run-scoped overlay。
    provider_binding_overlay_root, provider_binding_manifest_digest = (
        _stackctl.materialize_mutable_provider_binding_overlay(
            environment,
            target,
            source_root=_stackctl.ROOT,
            output_root=render_root / "provider-binding-overlay",
        )
    )

    execution_compose_files = _stackctl._dev_session_materialize_compose_files(
        compose_files,
        destination_root=execution_compose_root,
        provider_binding_overlay_context=provider_binding_overlay_root,
        provider_binding_manifest_digest=provider_binding_manifest_digest,
    )
    observability_execution_path = execution_compose_files[
        compose_files.index(local_elasticsearch_source)
    ]
    observability_launch_environment = (
        _stackctl._mutable_observability_log_sink_launch_environment(
            execution_path=observability_execution_path,
            composition=observability_composition,
        )
    )
    observability_execution_digest = observability_launch_environment[
        "QWQ_OBSERVABILITY_LOG_SINK_DIGEST"
    ]
    portal_materialization = _stackctl._materialize_local_portal_root(
        topology, target, portal_root
    )

    mutable_digest = str(workspace_snapshot.get("mutableStateDigest") or "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", mutable_digest) is None:
        mutable_digest = compose_digest

    config_versions: dict[str, str] = {}
    for service in _stackctl.first_party_service_names(_stackctl.ROOT):
        output = render_workload(
            _stackctl.ROOT,
            environment,
            service,
            config_root / f"{service}.yaml",
        )
        payload = _stackctl.load_json_yaml(output)
        version = str((payload.get("config") or {}).get("version") or "")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", version) is None:
            raise ValueError(f"mutable rendered config has no digest: {service}")
        config_versions[service] = version
    graphql_read_registry = _stackctl.materialize_graphql_read_runtime_config(
        repo_root=_stackctl.ROOT,
        runtime_config_path=config_root / "api-edge.yaml",
        environment=environment,
        target=target,
        candidate_digest=mutable_digest,
        signing=_stackctl._resolve_graphql_read_signing_for_local_target(
            environment, target
        ),
    )
    config_versions["api-edge"] = str(graphql_read_registry["configVersion"])

    shared_sources = {
        "module_catalog.yaml": _stackctl.ROOT
        / "quwoquan_service/runtime/reliabletask/resources/module_catalog.yaml",
        "retention_policy.yaml": _stackctl.ROOT
        / "quwoquan_service/runtime/reliabletask/resources/retention_policy.yaml",
        "object-storage-lifecycle.json": _stackctl.ROOT
        / "quwoquan_ops/environments/compose/object-storage-lifecycle.json",
        "livekit.yaml": _stackctl.ROOT / "quwoquan_ops/external/livekit/base/livekit.yaml",
        "Caddyfile": _stackctl.ROOT
        / "quwoquan_ops/environments/gamma/local/Caddyfile",
    }
    for name, source in shared_sources.items():
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"mutable runtime shared source is unsafe: {source}")
        shutil.copy2(source, shared_root / name)
    for name in ("module_catalog.yaml", "retention_policy.yaml"):
        shutil.copy2(
            shared_root / name,
            config_root
            / "quwoquan_service/runtime/reliabletask/resources"
            / name,
        )

    # service-core 镜像不再内嵌 skill release 资产;mutable test_live 与
    # immutable package 走同一条 skill-package-build 签名链路,把官方
    # publication 物化进 config-root 供 assistant asset-reader 消费。
    from quwoquan_ops.cli.lib.assistant_skill_package_artifact import (
        build_official_skill_package_publication,
    )

    source_revision_result = _stackctl.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_stackctl.ROOT,
    )
    source_revision = source_revision_result.stdout.strip()
    if source_revision_result.returncode != 0 or re.fullmatch(
        r"[0-9a-f]{40}",
        source_revision,
    ) is None:
        raise ValueError("mutable official Skill package source revision is invalid")
    skill_publication = build_official_skill_package_publication(
        environment,
        target,
        package_source_root=_stackctl.ROOT,
        package_environment={
            "QWQ_PACKAGE_SOURCE_REVISION": source_revision,
        },
        output_root=config_root / "skill-packages" / "official",
    )
    if int(skill_publication.get("exitCode") or 0) != 0:
        raise ValueError(
            "mutable official Skill package publication failed: "
            + str(skill_publication.get("stderr") or "")[:500]
        )

    try:
        tls_profile_name, profile_kind, _ = _stackctl.tls_profile(target)
        if profile_kind != "local-managed":
            raise _stackctl.PublicDomainTlsError(
                f"GATE_BLOCK: {target} must use local-managed TLS"
            )
        try:
            tls_evidence = _stackctl.verify_certificate(target)
        except _stackctl.PublicDomainTlsError:
            tls_evidence = _stackctl.issue_certificate(target)
        resolver_handoff = _stackctl.materialize_handoff(target)
    except (_stackctl.PublicDomainTlsError, _stackctl.LocalTargetHandoffError, OSError, ValueError) as exc:
        raise ValueError(f"mutable test_live TLS/resolver materialization failed: {exc}") from exc

    environment_values = _stackctl._gamma_env_from_port_manifest(topology, target)
    environment_values.update(
        {
            "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": _stackctl._dev_session_compose_project(
                environment, target
            ),
            "LOCAL_GAMMA_CADDYFILE": str(shared_root / "Caddyfile"),
            "LOCAL_GAMMA_LIVEKIT_CONFIG_FILE": str(shared_root / "livekit.yaml"),
            "LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE": str(
                shared_root / "object-storage-lifecycle.json"
            ),
            "LOCAL_GAMMA_MEDIA_ROOT": str(media_root),
            "LOCAL_GAMMA_LEGAL_STATIC_ROOT": str(legal_root),
            "LOCAL_GAMMA_PORTAL_ROOT": str(portal_root),
            "LOCAL_GAMMA_PUBLIC_WEB_ROOT": str(public_web_root),
            "QWQ_PUBLIC_WEB_CONTENT_DIGEST": public_web_package[
                "contentDigest"
            ],
            "QWQ_COMPOSE_CONFIG_ROOT": str(config_root),
            "QWQ_COMPOSE_ENV": environment,
            "QWQ_WORKLOAD": "full",
            "QWQ_PROVIDER_RUNTIME_DIGEST": str(
                provider_composition["runtimeCompositionDigest"]
            ),
            **observability_launch_environment,
            "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "1",
            "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
            "QWQ_COMPOSE_REC_POLICY_SOURCE": str(
                _stackctl.ROOT
                / "quwoquan_service/services/content-service/resources/policies/content/post/recommendation_policy.yaml"
            ),
            "QWQ_PUBLIC_TLS_CERT_FILE": str(tls_evidence["certificate"]),
            "QWQ_PUBLIC_TLS_KEY_FILE": str(tls_evidence["privateKey"]),
            "QWQ_LOCAL_MANAGED_CA_FILE": str(tls_evidence["rootCertificate"]),
        }
    )
    configuration_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            config_versions,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    environment_values["LOCAL_GAMMA_CONFIG_VERSION"] = configuration_digest
    environment_values["QWQ_COMPOSE_CONFIG_VERSION"] = configuration_digest
    environment_values["QWQ_COMPOSE_IMAGE_VERSION"] = mutable_digest
    environment_values["QWQ_COMPOSE_IMAGE_TAG"] = (
        f"{environment}-test-live-{mutable_digest.removeprefix('sha256:')[:16]}"
    )
    environment_values.update(
        _stackctl._mutable_test_live_operation_identity_environment(
            environment=environment,
            target=target,
            mutable_state_digest=mutable_digest,
            api_edge_config_version=config_versions["api-edge"],
        )
    )
    for service, version in config_versions.items():
        key = service.upper().replace("-", "_")
        environment_values[f"QWQ_COMPOSE_{key}_CONFIG_VERSION"] = version
        environment_values[_stackctl.compose_image_environment_key(service)] = (
            f"quwoquan/test-live-{target}-{service}:"
            f"{mutable_digest.removeprefix('sha256:')[:16]}"
        )
    environment_values[_stackctl.SERVICE_CORE_IMAGE_ENV] = (
        f"quwoquan/test-live-{target}-{_stackctl.SERVICE_CORE_WORKLOAD}:"
        f"{mutable_digest.removeprefix('sha256:')[:16]}"
    )

    environment_values.update(
        {
            "QWQ_COMPOSE_ELASTICSEARCH_IMAGE": str(selection["image"]),
            "QWQ_COMPOSE_ELASTICSEARCH_CLI_JAVA_OPTS": str(
                selection.get("cliJavaOpts") or ""
            ),
            "QWQ_COMPOSE_ELASTICSEARCH_JAVA_OPTS": str(
                selection.get("esJavaOpts") or ""
            ),
        }
    )

    provider_error = _stackctl._bind_formal_local_release_provider_environment(
        environment_values,
        environment_name=environment,
        target_name=target,
        workload="full",
        runtime_composition=provider_composition,
    )
    if provider_error is not None:
        raise ValueError(provider_error)
    # The base Compose still owns LOCAL_GAMMA_* interpolation names while
    # service fragments consume QWQ_COMPOSE_* aliases. They must describe the
    # same target and may never fall back to another environment's defaults.
    for key, value in tuple(environment_values.items()):
        if key.startswith("LOCAL_GAMMA_"):
            environment_values[f"QWQ_COMPOSE_{key.removeprefix('LOCAL_GAMMA_')}"] = value

    # 服务 Compose 片段由 immutable 候选与 mutable test_live 共用，且把部署期
    # 环境身份与 platform-ops facts 声明为必需挂载。两条装配必须绑定同一份材料，
    # 否则本路径的 Compose render 会在缺少插值变量时直接失败。
    environment_values["QWQ_LOCAL_RELEASE_ENV"] = environment
    environment_values["QWQ_RUN_ROOT"] = str(report_dir)
    _stackctl._bind_artifact_identity_mount_material(environment_values)

    plan = {
        "schema": "stackctl.mutable_test_live_runtime",
        "environment": environment,
        "target": target,
        "composeProject": environment_values["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"],
        "portProfile": profile_name,
        "portBlock": {"start": block_start, "end": block_end},
        "composeFiles": [_stackctl.relpath(path) for path in compose_files],
        "executionComposeFiles": [_stackctl.relpath(path) for path in execution_compose_files],
        "composeProfiles": compose_profiles,
        "composeDigest": compose_digest,
        "configurationDigest": configuration_digest,
        "providerRuntimeDigest": provider_composition["runtimeCompositionDigest"],
        "observabilityLogSinkDigest": observability_execution_digest,
        "mediaLocalRef": media_local_ref,
        "mediaRoot": _stackctl.relpath(media_root),
        "tlsProfile": tls_profile_name,
        "resolverHandoffDigest": resolver_handoff["handoffDigest"],
        "workspaceIdentity": dict(workspace_snapshot),
        "graphqlReadRegistry": dict(graphql_read_registry),
        "publicWebPackage": dict(public_web_package),
        "serviceCoreModules": sorted(_stackctl.SERVICE_CORE_MODULE_SET),
    }
    return {
        "plan": plan,
        "environment": environment_values,
        "composeFiles": execution_compose_files,
        "composeProfiles": compose_profiles,
        "portalMaterialization": portal_materialization,
        "publicWebRuntimeConfig": dict(runtime_config_digests),
    }

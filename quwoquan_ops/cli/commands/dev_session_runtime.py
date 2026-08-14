"""stackctl dev-session 运行时输入域: mutable workspace 快照、compose 物化
与 runtime 输入渲染。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- 会话状态: `_dev_session_child_args` / `_dev_session_phase` /
  `_dev_session_active_receipts` / `_dev_session_runtime_preflight` /
  `_dev_session_workload_conflict` / `_dev_session_compose_project`;
- workspace 与身份: `_mutable_workspace_snapshot` /
  `_mutable_test_live_operation_identity_environment`;
- compose 与输入: `_dev_session_source_compose_files` /
  `_materialize_local_portal_root` / `_dev_session_materialize_compose_files` /
  `_dev_session_target_media_root` / `_dev_session_render_runtime_inputs`。

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


def _dev_session_active_receipts(
    topology: Mapping[str, Any],
    target: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """读取 target 与 workload-scoped receipt，并返回当前 active 冲突。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    requested_attempt: dict[str, Any] | None = None
    active: list[dict[str, Any]] = []
    targets = (target, *_stackctl.local_runtime_peer_targets(topology, target))
    for candidate in targets:
        target_attempt = _stackctl.load_startup_attempt(candidate)
        if candidate == target:
            requested_attempt = target_attempt
        candidate_attempts: list[tuple[str, dict[str, Any]]] = []
        if target_attempt and target_attempt.get("status") != "stopped":
            candidate_attempts.append(("target", target_attempt))
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
    return requested_attempt, active


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


def _dev_session_source_compose_files(
    *,
    environment: str,
    target: str,
    provider_composition: Mapping[str, Any],
) -> tuple[list[Path], list[str]]:
    """Resolve the complete current-worktree Compose closure without packaging."""
    import quwoquan_ops.cli.stackctl as _stackctl


    _stackctl._dev_session_compose_project(environment, target)
    services_root = _stackctl.ROOT / "quwoquan_service" / "services"
    active_services = set(_stackctl.first_party_service_names(_stackctl.ROOT))
    files = [
        _stackctl.ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
    ]
    files.extend(
        sorted(
            path
            for path in services_root.glob("*/deploy/compose.yaml")
            if path.parents[1].name in active_services
        )
    )
    files.extend(
        sorted(
            path
            for path in services_root.glob(
                f"*/environments/{environment}/deploy/compose.yaml"
            )
            if path.parents[3].name in active_services
        )
    )
    files.extend(
        (
            _stackctl.ROOT
            / "quwoquan_service/services/product-ops-service/deploy/local-elasticsearch.compose.yaml",
            _stackctl.ROOT
            / "quwoquan_service/control-plane/platform-ops/deploy/compose.yaml",
        )
    )
    profiles = {"assistant-runtime", "commercial-observability", "edge-media"}
    validated_provider = _stackctl.validate_provider_runtime_composition(
        dict(provider_composition),
        expected_environment=environment,
        expected_target=target,
    )
    for workload in validated_provider["workloads"]:
        compose_ref = Path(str(workload["composeRef"]))
        if compose_ref.is_absolute() or ".." in compose_ref.parts:
            raise ValueError("mutable Provider Compose reference is unsafe")
        compose_path = (_stackctl.ROOT / compose_ref).resolve()
        if (
            not compose_path.is_relative_to(_stackctl.ROOT)
            or not compose_path.is_file()
            or compose_path.is_symlink()
            or _stackctl._sha256_file(compose_path) != str(workload["composeDigest"])
        ):
            raise ValueError(
                f"mutable Provider Compose identity drifted: {workload['role']}"
            )
        files.append(compose_path)
        profiles.update(str(item) for item in workload["composeProfiles"])

    canonical_files: list[Path] = []
    seen: set[Path] = set()
    for raw_path in files:
        path = raw_path.resolve()
        if (
            path in seen
            or not path.is_relative_to(_stackctl.ROOT)
            or not path.is_file()
            or path.is_symlink()
        ):
            if path in seen:
                continue
            raise ValueError(f"mutable test_live Compose source is unsafe: {path}")
        seen.add(path)
        canonical_files.append(path)
    if not canonical_files:
        raise ValueError("mutable test_live Compose closure is empty")
    return canonical_files, sorted(profiles)


def _materialize_local_portal_root(
    topology: dict[str, Any],
    target_name: str,
    portal_root: Path,
) -> str:
    """物化本地 Portal 静态站点到 Caddy /srv/portal 挂载根。

    具备仓内 node 工具链（portal/node_modules/.bin）与 QWQ_DEPLOY_WORK_ROOT
    时现场 vite build（base URL 从目标 publicBases 派生，不手写域名）；
    工具链缺失时写显式「未构建」提示页——本地开发环境不因前端缺构建阻塞
    服务栈启动，但绝不留下静默空 404 根目录。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    portal_dir = _stackctl.ROOT / "quwoquan_ops/portal"
    vite_binary = portal_dir / "node_modules/.bin/vite"
    deploy_work_root = os.environ.get("QWQ_DEPLOY_WORK_ROOT", "").strip()
    bases = _stackctl.get_target(topology, target_name).get("publicBases") or {}

    def _base(role: str) -> str:
        # 本地 target 的 publicBases 是渲染后的 URL 字符串（含端口）。
        return str(bases.get(role) or "")

    if vite_binary.is_file() and deploy_work_root:
        build_env = {
            **os.environ,
            "QWQ_DEPLOY_TARGET": target_name,
            "VITE_PRODUCT_OPS_BASE_URL": _base("productOps"),
            "VITE_PLATFORM_OPS_BASE_URL": _base("productOps"),
            "VITE_CONTENT_SERVICE_BASE_URL": _base("api"),
            "VITE_ENTITY_SERVICE_BASE_URL": _base("api"),
        }
        try:
            result = subprocess.run(
                [str(vite_binary), "build"],
                cwd=portal_dir,
                env=build_env,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            build_output = (
                Path(deploy_work_root) / target_name / "build" / "ops-portal"
            )
            if result.returncode == 0 and (build_output / "index.html").is_file():
                shutil.copytree(build_output, portal_root, dirs_exist_ok=True)
                return "built"
        except (OSError, subprocess.TimeoutExpired):
            pass
    (portal_root / "index.html").write_text(
        "<!doctype html><html lang=\"zh\"><meta charset=\"utf-8\">"
        "<title>ops-portal 未构建</title><body>"
        "<h1>ops-portal 尚未构建</h1>"
        "<p>本地 Portal 静态产物缺失：请在 quwoquan_ops/portal 安装 node "
        "依赖后重新执行 stackctl dev-session / up，或运行 "
        "stackctl package --kind ops-portal。本页面是显式占位，"
        "不承载任何业务数据。</p></body></html>\n",
        encoding="utf-8",
    )
    return "placeholder"


def _dev_session_materialize_compose_files(
    source_files: Sequence[Path],
    *,
    destination_root: Path,
) -> list[Path]:
    """Create execution-only Compose copies with source-relative build contexts."""
    import quwoquan_ops.cli.stackctl as _stackctl


    def contains_symlink(path: Path) -> bool:
        current = _stackctl.ROOT
        for part in path.relative_to(_stackctl.ROOT).parts:
            current /= part
            if current.is_symlink():
                return True
        return False

    destination_root.mkdir(parents=True, exist_ok=True)
    execution_files: list[Path] = []
    compose_base = (
        Path(os.path.abspath(source_files[0].parent)) if source_files else _stackctl.ROOT
    )
    for index, source in enumerate(source_files):
        payload = _stackctl.load_json_yaml(source)
        services = payload.get("services")
        if services is not None and not isinstance(services, dict):
            raise ValueError(f"mutable Compose services must be an object: {source}")
        try:
            source_ref = source.relative_to(_stackctl.ROOT).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"mutable test_live Compose source escapes repository: {source}"
            ) from exc
        if source_ref == "quwoquan_service/services/content-service/deploy/compose.yaml":
            content_service = (services or {}).get("content-service")
            if not isinstance(content_service, dict):
                raise ValueError(
                    "mutable content-service Compose source has no service definition"
                )
            dependencies = content_service.get("depends_on")
            if not isinstance(dependencies, dict):
                raise ValueError(
                    "mutable content-service Compose dependencies must be an object"
                )
            # Full test-live always enables the canonical Elasticsearch-backed
            # feed/search projection.  Formal environment overlays retain their
            # existing ownership; this execution-only copy closes the cold
            # Alpha/Beta race without changing package/deploy semantics.
            dependencies["elasticsearch"] = {"condition": "service_healthy"}
            dependencies["postgres"] = {"condition": "service_healthy"}
        if source_ref == "quwoquan_service/services/recommendation-service/deploy/compose.yaml":
            recommendation_service = (services or {}).get("recommendation-service")
            if not isinstance(recommendation_service, dict):
                raise ValueError(
                    "mutable recommendation-service Compose source has no service definition"
                )
            dependencies = recommendation_service.get("depends_on")
            if dependencies is None:
                dependencies = {}
                recommendation_service["depends_on"] = dependencies
            if not isinstance(dependencies, dict):
                raise ValueError(
                    "mutable recommendation-service Compose dependencies must be an object"
                )
            dependencies["redis"] = {"condition": "service_healthy"}
        for service_name, service in (services or {}).items():
            if not isinstance(service, dict):
                raise ValueError(
                    f"mutable Compose service must be an object: {source}:{service_name}"
                )
            volumes = service.get("volumes")
            if volumes is not None:
                if not isinstance(volumes, list):
                    raise ValueError(
                        f"mutable Compose volumes must be a list: {source}:{service_name}"
                    )
                rewritten_volumes: list[object] = []
                for volume in volumes:
                    if isinstance(volume, str) and volume.startswith("."):
                        host_ref, separator, container_ref = volume.partition(":")
                        host_path = Path(
                            os.path.abspath(source.parent / Path(host_ref))
                        )
                        if (
                            not separator
                            or not host_path.is_relative_to(_stackctl.ROOT)
                            or not host_path.exists()
                            or contains_symlink(host_path)
                        ):
                            raise ValueError(
                                "mutable Compose bind source is unsafe: "
                                f"{source}:{service_name}:{host_ref}"
                            )
                        rewritten_volumes.append(
                            str(host_path) + separator + container_ref
                        )
                        continue
                    if (
                        isinstance(volume, dict)
                        and volume.get("type") == "bind"
                        and str(volume.get("source") or "").startswith(".")
                    ):
                        host_ref = str(volume["source"])
                        host_path = Path(
                            os.path.abspath(source.parent / Path(host_ref))
                        )
                        if (
                            not host_path.is_relative_to(_stackctl.ROOT)
                            or not host_path.exists()
                            or contains_symlink(host_path)
                        ):
                            raise ValueError(
                                "mutable Compose bind source is unsafe: "
                                f"{source}:{service_name}:{host_ref}"
                            )
                        rewritten_volumes.append(
                            {**volume, "source": str(host_path)}
                        )
                        continue
                    rewritten_volumes.append(volume)
                service["volumes"] = rewritten_volumes
            build = service.get("build")
            if isinstance(build, str):
                build = {"context": build}
                service["build"] = build
            elif build is None:
                continue
            elif not isinstance(build, dict):
                raise ValueError(
                    f"mutable Compose build must be a string or object: "
                    f"{source}:{service_name}"
                )
            context_value = str(build.get("context") or "").strip()
            if not context_value:
                raise ValueError(
                    f"mutable Compose build context is empty: {source}:{service_name}"
                )
            context_path = Path(context_value)
            dockerfile_value = str(build.get("dockerfile") or "Dockerfile").strip()
            dockerfile_path = Path(dockerfile_value)
            if not dockerfile_value or dockerfile_path.is_absolute():
                raise ValueError(
                    f"mutable Compose Dockerfile is unsafe: {source}:{service_name}"
                )
            raw_candidates = (
                [Path(os.path.abspath(context_path))]
                if context_path.is_absolute()
                else [
                    Path(os.path.abspath(source.parent / context_path)),
                    Path(os.path.abspath(compose_base / context_path)),
                ]
            )
            candidates: list[Path] = []
            for candidate in raw_candidates:
                if candidate in candidates:
                    continue
                dockerfile = Path(os.path.abspath(candidate / dockerfile_path))
                if (
                    candidate.is_relative_to(_stackctl.ROOT)
                    and candidate.is_dir()
                    and not contains_symlink(candidate)
                    and dockerfile.is_relative_to(candidate)
                    and dockerfile.is_file()
                    and not contains_symlink(dockerfile)
                ):
                    candidates.append(candidate)
            if len(candidates) != 1:
                raise ValueError(
                    f"mutable Compose build context must resolve exactly once: "
                    f"{source}:{service_name}:{context_value}"
                )
            resolved_context = candidates[0]
            build["context"] = str(resolved_context)
        payload = _stackctl.project_compose_document(payload)
        destination = destination_root / f"{index:02d}-{source.stem}.json"
        _stackctl.write_json(destination, payload)
        execution_files.append(destination)
    return execution_files


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

    execution_compose_files = _stackctl._dev_session_materialize_compose_files(
        compose_files,
        destination_root=execution_compose_root,
    )
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
    from quwoquan_ops.cli.commands.package_runtime import (
        _build_official_skill_package_publication,
    )

    skill_publication = _build_official_skill_package_publication(
        environment,
        target,
        package_source_root=_stackctl.ROOT,
        package_environment={},
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
            "LOCAL_GAMMA_ADMIN_PORT": str(block_end),
            "LOCAL_GAMMA_CADDYFILE": str(shared_root / "Caddyfile"),
            "LOCAL_GAMMA_LIVEKIT_CONFIG_FILE": str(shared_root / "livekit.yaml"),
            "LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE": str(
                shared_root / "object-storage-lifecycle.json"
            ),
            "LOCAL_GAMMA_MEDIA_ROOT": str(media_root),
            "LOCAL_GAMMA_LEGAL_STATIC_ROOT": str(legal_root),
            "LOCAL_GAMMA_PORTAL_ROOT": str(portal_root),
            "QWQ_COMPOSE_CONFIG_ROOT": str(config_root),
            "QWQ_COMPOSE_ENV": environment,
            "QWQ_WORKLOAD": "full",
            "QWQ_PROVIDER_RUNTIME_DIGEST": str(
                provider_composition["runtimeCompositionDigest"]
            ),
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

    elasticsearch = _stackctl.load_json_yaml(
        _stackctl.ROOT
        / "quwoquan_service/services/product-ops-service/deploy/local-elasticsearch.compose.yaml"
    )
    platforms = ((elasticsearch.get("x-qwq-package-elasticsearch") or {}).get("platforms") or {})
    machine = os.uname().machine.lower()
    selected_platform = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
    selection = platforms.get(selected_platform)
    if not isinstance(selection, dict) or not str(selection.get("image") or ""):
        raise ValueError("mutable Elasticsearch platform selection is invalid")
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

    plan = {
        "schema": "stackctl.mutable_test_live_runtime",
        "environment": environment,
        "target": target,
        "composeProject": environment_values["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"],
        "portProfile": profile_name,
        "portBlock": {"start": block_start, "end": block_end},
        "publishedPorts": dict(sorted(ports.items())),
        "composeFiles": [_stackctl.relpath(path) for path in compose_files],
        "executionComposeFiles": [_stackctl.relpath(path) for path in execution_compose_files],
        "composeProfiles": compose_profiles,
        "composeDigest": compose_digest,
        "configurationDigest": configuration_digest,
        "providerRuntimeDigest": provider_composition["runtimeCompositionDigest"],
        "mediaLocalRef": media_local_ref,
        "mediaRoot": _stackctl.relpath(media_root),
        "tlsProfile": tls_profile_name,
        "resolverHandoffDigest": resolver_handoff["handoffDigest"],
        "workspaceIdentity": dict(workspace_snapshot),
        "graphqlReadRegistry": dict(graphql_read_registry),
        "serviceCoreModules": sorted(_stackctl.SERVICE_CORE_MODULE_SET),
    }
    _stackctl.write_json(report_dir / "mutable-runtime-plan.json", plan)
    return {
        "plan": plan,
        "environment": environment_values,
        "composeFiles": execution_compose_files,
        "composeProfiles": compose_profiles,
        "portalMaterialization": portal_materialization,
    }

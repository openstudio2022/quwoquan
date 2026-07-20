#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import contextlib
import fcntl
import hashlib
import json
import os
import re
import selectors
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.common import (
    artifact_run_dir,
    ensure_list,
    load_json_yaml,
    relpath,
    run,
    utc_now,
    write_json,
    write_markdown,
)
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    TARGETS,
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.media_delivery_manifest import (
    build_media_delivery_url,
    load_media_delivery_manifest,
)
from quwoquan_ops.cli.lib.local_environment_auth import (
    open_local_acceptance_session,
    prepare_local_environment_auth,
)
from quwoquan_ops.cli.lib.local_gamma_object_storage import prepare_local_gamma_object_storage
from quwoquan_ops.cli.lib.product_telemetry_sls import load_product_telemetry_sls
from quwoquan_ops.cli.lib.video_playback_evidence import (
    read_native_video_playback_evidence,
)
from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome,
    ProbeSource,
    ReadinessPhase,
    ShipReadinessReceipt,
    VerificationProfile,
    load_content_release_readiness_policy,
)
from quwoquan_ops.cli.lib.local_gamma_media import (
    LocalGammaMediaError,
    materialize_local_gamma_media,
)
from quwoquan_ops.cli.lib.dev_up import (
    DEV_UP_ENVS,
    DEV_UP_STACK_TARGETS,
    app_target_for_env,
    build_start_app_command,
    launch_app,
    pick_dev_up_env,
    resolve_device_id,
)
from quwoquan_ops.cli.lib.port_manifest import canonical_port, load_port_manifest, profile_ports
from quwoquan_ops.cli.lib.observability import (
    append_log_line,
    env_from_report_dir,
    parse_log_records,
    run_dir as observability_run_dir,
    run_id_from_report_dir,
    write_run_manifest,
    write_stackctl_links,
)
from quwoquan_ops.cli.lib.output_paths import (
    app_release_dir,
    env_observability_run_dir,
    env_release_root,
    env_runs_root,
    repo_local_dir,
    repo_run_dir,
    service_release_dir,
    target_cache_dir,
    target_process_dir,
)


VERIFY_COMMAND_GROUPS = {
    "topology": [
        ["python3", "quwoquan_ops/gate/verify_stackctl_args_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_environment_topology_manifest.py"],
        ["python3", "quwoquan_ops/gate/verify_local_env_port_manifest.py"],
        ["bash", "quwoquan_ops/environments/verify/verify_deployment_domain_mapping.sh"],
    ],
    "config": [
        ["python3", "quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_media_delivery_contract.py"],
        # N2-2：gamma-local 推荐 policy overlay 与 metadata 单真相源一致性
        # （objectCards 环境开关是唯一允许差异）。
        ["python3", "quwoquan_ops/gate/verify_gamma_policy_overlay.py"],
    ],
    "packaging": [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"],
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ],
}

PROD_RELEASE_UNIT = "prod-stack"

DEFAULT_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}

# CLI summaries should retain every concise prerequisite failure while keeping
# the terminal surface bounded. Full child-process output remains in report.json.
COMMAND_SUMMARY_DETAIL_LIMIT = 12


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _packaged_service_source_image_ref(env_name: str, service: str) -> str:
    report_path = service_release_dir(env_name, service) / "report.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"service package report missing: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    try:
        source = report["provenance"]["source"]
        source_digest = str(source["sourceTreeSha256"])
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"service source provenance missing: {report_path}"
        ) from exc
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_digest):
        raise ValueError(f"invalid service source digest: {report_path}")
    repository = service.replace("-", "_")
    return f"localhost/quwoquan_service_{repository}:{source_digest[7:19]}"


def _build_runtime_shared_package(env_name: str) -> Path:
    """将运行栈共享静态配置封装为环境 package，禁止启动期直读仓内源文件。"""
    package_dir = env_release_root(env_name) / "runtime-shared"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    sources = (
        ROOT / "quwoquan_ops" / "environments" / "reliable_task_module_catalog.yaml",
        ROOT / "quwoquan_ops" / "environments" / "reliable_task_retention_policy.yaml",
    )
    files: dict[str, dict[str, str]] = {}
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(f"missing runtime shared package source: {source}")
        destination = package_dir / source.name
        shutil.copy2(source, destination)
        files[source.name] = {
            "source": relpath(source),
            "sha256": _sha256_file(destination),
        }
    write_json(
        package_dir / "manifest.json",
        {
            "schema": "qwq.runtime_shared_package",
            "environment": env_name,
            "createdAt": utc_now(),
            "files": files,
        },
    )
    return package_dir


def _materialize_prod_release_artifact() -> str:
    """把 CI 已验证的不可变 release artifact 物化进 prod 环境包。"""
    artifact_root_value = os.environ.get("QWQ_PROD_RELEASE_ARTIFACT_ROOT", "").strip()
    if not artifact_root_value:
        return ""
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = ROOT / artifact_root
    manifest_path = artifact_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prod release artifact manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config_version = str((manifest.get("versions") or {}).get("configVersion") or "").strip()
    release_files = manifest.get("releaseFiles")
    if not config_version or not isinstance(release_files, dict):
        raise ValueError(f"invalid prod release artifact manifest: {manifest_path}")
    package_root = env_release_root("prod") / "service"
    artifact_digest = _sha256_file(manifest_path)
    for service, relative_path in release_files.items():
        source = artifact_root / str(relative_path)
        if not source.is_file():
            raise FileNotFoundError(f"prod release artifact file missing: {source}")
        destinations = [package_root / str(service)]
        if service == "recommendation-service":
            destinations.append(package_root / "rec-model-service")
        for destination_dir in destinations:
            report_path = destination_dir / "report.json"
            if not report_path.is_file():
                raise FileNotFoundError(f"prod service package missing: {destination_dir}")
            release_dir = destination_dir / "releases"
            release_dir.mkdir(parents=True, exist_ok=True)
            destination = release_dir / f"{config_version}.yaml"
            shutil.copy2(source, destination)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            provenance = report.get("provenance")
            if not isinstance(provenance, dict):
                raise ValueError(f"service package provenance missing: {report_path}")
            release_digests = provenance.setdefault("releaseFiles", {})
            if not isinstance(release_digests, dict):
                raise ValueError(f"service package release provenance invalid: {report_path}")
            release_digests[destination.name] = _sha256_file(destination)
            provenance["releaseArtifact"] = {
                "manifest": relpath(manifest_path),
                "manifestSha256": artifact_digest,
                "configVersion": config_version,
            }
            write_json(report_path, report)
    return config_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified environment packaging, startup, verification, inspection, and rollout control.",
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--report-dir", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    package_parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    package_parser.add_argument("--kind", choices=["runtime", "legal-static"], default="runtime")
    package_parser.add_argument("--service", default="")
    package_parser.add_argument("--include-services", action="store_true")
    package_parser.add_argument("--target", choices=TARGETS, default="")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    verify_parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    verify_parser.add_argument("--target", choices=TARGETS, default="")
    verify_parser.add_argument(
        "--kind",
        choices=["topology", "config", "packaging", "legal-static", "all"],
        default="all",
    )
    verify_parser.add_argument(
        "--profile",
        choices=[profile.value for profile in VerificationProfile],
        required=True,
    )

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    up_parser.add_argument("--target", choices=TARGETS, default="")
    up_parser.add_argument("--env", choices=DEV_UP_ENVS, default="")
    up_parser.add_argument("--device-id", default="")
    up_parser.add_argument("--skip-app", action="store_true")
    up_parser.add_argument("--skip-build", action="store_true")
    up_parser.add_argument(
        "--workload",
        choices=["content-release", "full"],
        default="full",
    )
    up_parser.add_argument("--rollout-mode", choices=["gray-initial", "carry-on", "full"], default="")

    down_parser = subparsers.add_parser("down")
    down_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    down_parser.add_argument("--target", choices=TARGETS, required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    status_parser.add_argument("--target", choices=TARGETS, required=True)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    health_parser.add_argument("--target", choices=TARGETS, required=True)
    health_parser.add_argument(
        "--scope",
        choices=["edge", "media", "service", "content-import", "content-consumer", "full"],
        default="full",
    )
    health_parser.add_argument("--request-timeout-seconds", type=int, default=0)
    health_parser.add_argument("--retry-attempts", type=int, default=0)
    health_parser.add_argument("--retry-sleep-seconds", type=float, default=-1.0)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    inspect_parser.add_argument("--target", choices=TARGETS, required=True)
    inspect_parser.add_argument(
        "--scope",
        choices=["logs", "network", "data", "metrics", "config", "security", "all"],
        default="all",
    )
    inspect_parser.add_argument(
        "--kind",
        dest="scope",
        choices=["logs", "network", "data", "metrics", "config", "security", "all"],
    )

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    doctor_parser.add_argument("--target", choices=TARGETS, required=True)

    content_readiness_parser = subparsers.add_parser(
        "content-readiness",
        help="验证指定内容发布 phase 的环境能力，不创建内容工作包",
    )
    content_readiness_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    content_readiness_parser.add_argument(
        "--phase",
        choices=[phase.value for phase in ReadinessPhase],
        required=True,
    )
    content_readiness_parser.add_argument("--env", choices=ENVIRONMENTS, required=True)

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    repair_parser.add_argument("--target", choices=TARGETS, required=True)
    repair_parser.add_argument(
        "--fix",
        choices=[
            "rebuild-packages",
            "restart-stack",
            "reclaim-ports",
            "materialize-media",
        ],
        required=True,
    )

    roll_parser = subparsers.add_parser("roll")
    roll_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    roll_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    roll_parser.add_argument("--mode", choices=("restart", "rollout"), default="restart")
    roll_parser.add_argument("--stage", default="")
    roll_parser.add_argument("--image-version", default="")
    roll_parser.add_argument("--previous-image-version", default="")
    roll_parser.add_argument("--base-url", default="")
    roll_parser.add_argument("--product-ops-base-url", default="")
    roll_parser.add_argument("--media-base-url", default="")
    roll_parser.add_argument("--media-origin-base-url", default="")
    roll_parser.add_argument("--image-repository-root", default="")
    roll_parser.add_argument("--image-registry", default="")
    roll_parser.add_argument("--registry-username", default="")
    roll_parser.add_argument("--registry-password", default="")

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    deploy_parser.add_argument("--target", choices=("prod-hosted",), required=True)
    deploy_parser.add_argument("--mode", choices=("restart", "rollout", "cold-build"), default="")
    deploy_parser.add_argument(
        "--stage",
        choices=("gray-initial", "carry-on", "full"),
        default="",
        help="显式 rollout stage；未指定时按 step 映射为 5=gray-initial、25/50=carry-on、100=full",
    )
    deploy_parser.add_argument("--image-version", default="")
    deploy_parser.add_argument("--previous-image-version", default="")
    deploy_parser.add_argument("--base-url", default="")
    deploy_parser.add_argument("--product-ops-base-url", default="")
    deploy_parser.add_argument("--media-base-url", default="")
    deploy_parser.add_argument("--media-origin-base-url", default="")
    deploy_parser.add_argument("--image-repository-root", default="")
    deploy_parser.add_argument("--image-registry", default="")
    deploy_parser.add_argument("--registry-username", default="")
    deploy_parser.add_argument("--registry-password", default="")
    deploy_parser.add_argument("--service", default="")
    deploy_parser.add_argument("--from-image", default="")
    deploy_parser.add_argument("--to-image", default="")
    deploy_parser.add_argument("--from-config", default="")
    deploy_parser.add_argument("--to-config", default="")
    deploy_parser.add_argument("--step", default="")
    deploy_parser.add_argument("--cloud-provider", choices=["aliyun", "volcengine", "huaweicloud"], default="aliyun")
    deploy_parser.add_argument("--dry-run", choices=["true", "false"], default="false")
    deploy_parser.add_argument(
        "--release-manifest",
        default="",
        help="Service Pipeline 产出的 deployable manifest.json；真实生产发布必须提供",
    )
    deploy_parser.add_argument(
        "--prometheus-url",
        default="",
        help="生产 SLO readback 的 Prometheus base URL；非 dry-run 必须提供",
    )
    return parser


def resolve_report_dir(args: argparse.Namespace, env_name: str, target: str) -> Path:
    if args.report_dir:
        return Path(args.report_dir)
    return artifact_run_dir(env_name, args.command, target=target or "local")


def _start_timing() -> tuple[float, str]:
    return time.monotonic(), utc_now()


def _finish_timing(started_monotonic: float, started_at: str) -> dict[str, Any]:
    return {
        "startedAt": started_at,
        "endedAt": utc_now(),
        "durationMs": int((time.monotonic() - started_monotonic) * 1000),
    }


def _format_duration_ms(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "0ms"
    seconds = max(int(duration_ms), 0) / 1000.0
    if seconds < 1:
        return f"{int(duration_ms)}ms"
    return f"{seconds:.2f}s"


def _is_interactive_terminal() -> bool:
    return sys.stdout.isatty() and sys.stderr.isatty()


def _progress_print(message: str) -> None:
    if _is_interactive_terminal():
        print(message, flush=True)


def _format_stage_header(index: int, total: int, name: str) -> str:
    return f"[step {index}/{total}] {name}"


def _run_with_live_output(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    prefix: str = "",
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)
    process = subprocess.Popen(
        argv,
        cwd=str(cwd or ROOT),
        env=merged_env,
        text=False,
        bufsize=0,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    chunks: list[bytes] = []
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    interactive = _is_interactive_terminal()
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    exit_observed_at: float | None = None

    def emit_available_text(text: str, *, flush_partial: bool = False) -> None:
        nonlocal pending
        pending += text
        if not interactive:
            if flush_partial:
                pending = ""
            return
        while True:
            newline_index = pending.find("\n")
            if newline_index < 0:
                break
            line = pending[: newline_index + 1]
            pending = pending[newline_index + 1 :]
            if prefix:
                print(f"{prefix}{line}", end="", flush=True)
            else:
                print(line, end="", flush=True)
        if flush_partial and pending:
            if prefix:
                print(f"{prefix}{pending}", end="", flush=True)
            else:
                print(pending, end="", flush=True)
            pending = ""

    try:
        while True:
            events = selector.select(timeout=0.2)
            saw_output = False
            for _key, _mask in events:
                try:
                    data = os.read(process.stdout.fileno(), 4096)
                except BlockingIOError:
                    continue
                if not data:
                    exit_observed_at = 0.0
                    continue
                saw_output = True
                chunks.append(data)
                emit_available_text(decoder.decode(data))
            if saw_output:
                exit_observed_at = None
                continue
            if process.poll() is None:
                continue
            if exit_observed_at is None:
                exit_observed_at = time.monotonic()
                continue
            if exit_observed_at == 0.0 or time.monotonic() - exit_observed_at >= 0.5:
                break
    finally:
        selector.close()
        emit_available_text(decoder.decode(b"", final=True), flush_partial=True)
        process.stdout.close()
        if process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
    stdout = b"".join(chunks).decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(
        argv,
        process.returncode,
        stdout=stdout,
        stderr="",
    )


def _tail_file_for_startup(
    log_path: Path,
    *,
    process: subprocess.Popen[str] | None = None,
    prefix: str = "[app] ",
    idle_timeout_seconds: float = 2.5,
    max_follow_seconds: float = 20.0,
    ready_patterns: tuple[str, ...] = (),
    failure_patterns: tuple[str, ...] = (),
    ready_idle_timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    emit_output = _is_interactive_terminal()
    deadline = time.monotonic() + max_follow_seconds
    while time.monotonic() < deadline:
        if log_path.exists():
            break
        if process is not None and process.poll() is not None:
            return {"followed": False, "lines": 0, "reason": "process-exited-before-log"}
        time.sleep(0.1)
    if not log_path.exists():
        return {"followed": False, "lines": 0, "reason": "log-not-created"}

    if emit_output:
        print(f"{prefix}tailing startup log: {relpath(log_path)}", flush=True)
    line_count = 0
    last_activity = time.monotonic()
    ready_seen = False
    failure_seen = False
    failure_line = ""
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        while True:
            line = handle.readline()
            if line:
                line_count += 1
                last_activity = time.monotonic()
                if emit_output:
                    print(f"{prefix}{line}", end="", flush=True)
                if ready_patterns and any(pattern in line for pattern in ready_patterns):
                    ready_seen = True
                if failure_patterns and any(pattern in line for pattern in failure_patterns):
                    failure_seen = True
                    if not failure_line:
                        failure_line = line.strip()
                continue
            if process is not None and process.poll() is not None:
                break
            now = time.monotonic()
            if now >= deadline:
                break
            effective_idle_timeout = ready_idle_timeout_seconds if ready_seen else None
            if effective_idle_timeout is not None and line_count > 0 and now - last_activity >= effective_idle_timeout:
                break
            time.sleep(0.15)
    reason = "idle"
    if process is not None and process.poll() is not None:
        reason = "process-exited"
    elif time.monotonic() >= deadline:
        reason = "timeout"
    if emit_output:
        print(f"{prefix}startup log tail finished ({reason})", flush=True)
    return {
        "followed": True,
        "lines": line_count,
        "reason": reason,
        "readySeen": ready_seen,
        "readyPatterns": list(ready_patterns),
        "failureSeen": failure_seen,
        "failureLine": failure_line,
        "failurePatterns": list(failure_patterns),
        "processExitCode": process.poll() if process is not None else None,
    }


def _prod_plane_runtime_report(plane: str, report_path: Path | None = None) -> dict[str, Any]:
    argv = ["python3", "quwoquan_ops/cli/prod/inspect_prod_plane_runtime.py", "--plane", plane]
    if report_path is not None:
        argv.extend(["--output", str(report_path)])
    result = run(argv)
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


def _app_launch_failure_detail(
    tail_result: dict[str, Any],
    *,
    default_message: str,
    require_ready: bool = True,
    process_exit_code: int | None = None,
) -> str | None:
    if bool(tail_result.get("failureSeen")):
        return str(tail_result.get("failureLine") or default_message)
    if process_exit_code not in (None, 0):
        return f"{default_message}: process exited with code {process_exit_code}"
    if require_ready and not bool(tail_result.get("readySeen")):
        reason = str(tail_result.get("reason") or "idle")
        return f"{default_message}: app did not reach Flutter ready state before {reason}"
    return None


def _tail_multiple_logs_for_startup(
    log_specs: list[tuple[str, Path]],
    *,
    idle_timeout_seconds: float = 2.5,
    max_follow_seconds: float = 20.0,
) -> dict[str, Any]:
    if not _is_interactive_terminal():
        return {"followed": False, "logs": [], "reason": "non-interactive"}
    existing_specs = [(label, path) for label, path in log_specs if path.exists()]
    if not existing_specs:
        return {"followed": False, "logs": [], "reason": "log-not-created"}

    for label, path in existing_specs:
        print(f"[{label}] tailing startup log: {relpath(path)}", flush=True)

    handles = {
        label: path.open("r", encoding="utf-8", errors="replace")
        for label, path in existing_specs
    }
    line_counts = {label: 0 for label, _ in existing_specs}
    last_activity = time.monotonic()
    deadline = time.monotonic() + max_follow_seconds
    try:
        while True:
            saw_output = False
            for label, _path in existing_specs:
                line = handles[label].readline()
                if not line:
                    continue
                saw_output = True
                line_counts[label] += 1
                last_activity = time.monotonic()
                print(f"[{label}] {line}", end="", flush=True)
            now = time.monotonic()
            if now >= deadline:
                reason = "timeout"
                break
            if saw_output:
                continue
            if sum(line_counts.values()) > 0 and now - last_activity >= idle_timeout_seconds:
                reason = "idle"
                break
            time.sleep(0.15)
    finally:
        for handle in handles.values():
            handle.close()

    for label, _path in existing_specs:
        print(f"[{label}] startup log tail finished ({reason})", flush=True)
    return {
        "followed": True,
        "logs": [
            {
                "label": label,
                "path": relpath(path),
                "lines": line_counts[label],
            }
            for label, path in existing_specs
        ],
        "reason": reason,
    }


def _tail_gamma_container_logs() -> dict[str, Any]:
    if not _is_interactive_terminal():
        return {"followed": False, "reason": "non-interactive", "backend": ""}

    compose_file = ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.gamma-local.yaml"
    if not compose_file.exists():
        return {"followed": False, "reason": "compose-file-missing", "backend": ""}

    docker_result = subprocess.run(
        ["docker", "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    use_podman = docker_result.returncode == 0 and "podman" in (docker_result.stdout + docker_result.stderr).lower()
    if use_podman:
        if subprocess.run(["podman", "--version"], text=True, capture_output=True, check=False).returncode != 0:
            return {"followed": False, "reason": "podman-missing", "backend": "podman"}
        containers = {
            "gamma-proxy": "quwoquan_service_gamma-proxy_1",
            "content-service": "quwoquan_service_content-service_1",
            "assistant-service": "quwoquan_service_assistant-service_1",
            "user-service": "quwoquan_service_user-service_1",
            "chat-service": "quwoquan_service_chat-service_1",
            "integration-service": "quwoquan_service_integration-service_1",
            "notification-service": "quwoquan_service_notification-service_1",
        }
        log_paths: list[tuple[str, Path]] = []
        with tempfile.TemporaryDirectory(prefix="gamma-tail-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            spawned: list[subprocess.Popen[str]] = []
            try:
                for label, container_name in containers.items():
                    inspect = subprocess.run(
                        ["podman", "inspect", container_name],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if inspect.returncode != 0:
                        continue
                    log_path = tmp_root / f"{label}.log"
                    handle = log_path.open("w", encoding="utf-8")
                    proc = subprocess.Popen(
                        ["podman", "logs", "-f", "--tail", "40", container_name],
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    handle.close()
                    spawned.append(proc)
                    log_paths.append((f"gamma-{label}", log_path))
                result = _tail_multiple_logs_for_startup(
                    log_paths,
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=45.0,
                )
                result["backend"] = "podman"
                return result
            finally:
                for proc in spawned:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
        return {"followed": False, "reason": "no-podman-containers", "backend": "podman"}

    if subprocess.run(["docker", "compose", "version"], text=True, capture_output=True, check=False).returncode != 0:
        return {"followed": False, "reason": "docker-compose-missing", "backend": "docker"}

    services = [
        "gamma-proxy",
        "content-service",
        "assistant-service",
        "user-service",
        "chat-service",
        "integration-service",
        "notification-service",
    ]
    with tempfile.TemporaryDirectory(prefix="gamma-tail-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        log_paths = [(f"gamma-{service}", tmp_root / f"{service}.log") for service in services]
        handles = {label: path.open("w", encoding="utf-8") for label, path in log_paths}
        process = subprocess.Popen(
            ["docker", "compose", "-f", str(compose_file), "logs", "-f", "--tail", "40", *services],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        try:
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                for label, handle in handles.items():
                    service_name = label.removeprefix("gamma-")
                    if line.startswith(f"{service_name}"):
                        handle.write(line)
                        handle.flush()
            result = _tail_multiple_logs_for_startup(
                log_paths,
                idle_timeout_seconds=6.0,
                max_follow_seconds=45.0,
            )
            result["backend"] = "docker"
            return result
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            for handle in handles.values():
                handle.close()


def _local_runtime_log_root(target: str) -> Path:
    state_path = target_process_dir(target) / "local_run.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"local run state unavailable for {target}: {state_path}: {exc}") from exc
    observability_root = Path(str(payload.get("observabilityRoot") or ""))
    if not observability_root.is_absolute():
        raise RuntimeError(f"local run observabilityRoot must be absolute: {state_path}")
    return observability_root / "logs" / "service"


def _write_summary_bundle(
    report_dir: Path,
    *,
    command: str,
    target: str,
    status: str,
    summary: str,
    details: list[str],
    extra: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
) -> None:
    payload = {
        "command": command,
        "target": target,
        "status": status,
        "summary": summary,
        "details": details,
        "generatedAt": utc_now(),
    }
    if timing:
        payload.update(timing)
    if extra:
        payload.update(extra)
    write_json(report_dir / "summary.json", payload)
    env_name = env_from_report_dir(report_dir, target)
    run_id = run_id_from_report_dir(report_dir)
    obs_dir = observability_run_dir(env_name, run_id)
    write_run_manifest(
        obs_dir,
        env_name=env_name,
        run_id=run_id,
        command=command,
        target=target,
        report_dir=report_dir,
    )
    append_log_line(
        obs_dir / "logs" / "ci" / "stackctl" / "deploy.log",
        {
            "ts": payload["generatedAt"],
            "level": "ERROR" if status in {"failed", "gate_block"} else "INFO",
            "step": command,
            "result": status,
            "msg": summary,
        },
    )
    write_stackctl_links(
        report_dir,
        env_name=env_name,
        run_id=run_id,
        obs_dir=obs_dir,
    )
    summary_lines = [
        f"# stackctl {command}",
        "",
        f"- target: `{target}`",
        f"- status: `{status}`",
        f"- summary: {summary}",
    ]
    if timing:
        summary_lines.extend(
            [
                f"- startedAt: `{timing.get('startedAt', '')}`",
                f"- endedAt: `{timing.get('endedAt', '')}`",
                f"- duration: `{_format_duration_ms(int(timing.get('durationMs', 0) or 0))}`",
            ]
        )
    write_markdown(
        report_dir / "summary.md",
        "\n".join(summary_lines + [*[f"- {line}" for line in details]]),
    )


def _write_stdout_markdown(report_dir: Path, sections: list[tuple[str, str]]) -> None:
    lines: list[str] = ["# stackctl stdout", ""]
    for title, content in sections:
        if not content.strip():
            continue
        lines.extend([f"## {title}", "", "```text", content.rstrip(), "```", ""])
    write_markdown(report_dir / "stdout.md", "\n".join(lines))


def _selected_verify_commands(
    kind: str,
    env_name: str = "",
    *,
    profile: VerificationProfile,
) -> list[list[str]]:
    packaging_commands = [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"]
        + (["--env", env_name] if env_name in ENVIRONMENTS else []),
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"]
        + (["--env", env_name] if env_name in ENVIRONMENTS else []),
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ]
    if kind == "all":
        commands: list[list[str]] = []
        group_names = ("topology", "config")
        if profile is not VerificationProfile.BASELINE:
            group_names = (*group_names, "packaging")
        for group_name in group_names:
            if group_name == "packaging":
                commands.extend(packaging_commands)
                continue
            commands.extend(VERIFY_COMMAND_GROUPS[group_name])
        return commands
    if kind == "packaging":
        return packaging_commands
    return list(VERIFY_COMMAND_GROUPS[kind])


def _local_target_edge_ready(target_name: str) -> bool:
    try:
        manifest = load_port_manifest()
    except Exception:
        return False
    for plane in ("api-edge", "product-ops-edge", "media-edge"):
        try:
            port = canonical_port(manifest, target_name, plane)
        except Exception:
            return False
        if not socket_probe(port):
            return False
    return True


def _local_target_runtime_ready(target_name: str) -> bool:
    try:
        topology = load_environment_topology()
        target = get_target(topology, target_name)
        profile_name = str(target.get("portProfile") or "")
        manifest = load_port_manifest()
    except Exception:
        return False
    if not profile_name:
        return _local_target_edge_ready(target_name)
    for role_name in _expected_local_roles(target_name):
        if role_name not in manifest.get("roles", {}):
            return False
        try:
            port = canonical_port(manifest, profile_name, role_name)
        except Exception:
            return False
        if not socket_probe(port):
            return False
    return True


def _selected_profile_commands(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None = None,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if profile.requires_environment and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
    }:
        if _local_target_runtime_ready(target_name):
            commands.append(
                {
                    "name": f"{target_name}-health-preflight",
                    "argv": [
                        "python3",
                        "-c",
                        (
                            "print('local runtime ports already listening; "
                            f"skip stackctl up for {target_name}')"
                        ),
                    ],
                    "cwd": ROOT,
                }
            )
        else:
            commands.append(
                {
                    "name": f"{target_name}-up",
                    "argv": [
                        "python3",
                        "quwoquan_ops/cli/stackctl.py",
                        "up",
                        "--target",
                        target_name,
                        "--workload",
                        "content-release"
                        if profile in {
                            VerificationProfile.SMOKE,
                            VerificationProfile.INTEGRATION,
                        }
                        else "full",
                        "--skip-app",
                    ],
                    "cwd": ROOT,
                }
            )
    if profile is VerificationProfile.SMOKE:
        commands.extend(
            [
                {
                    "name": "content-media-url-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "test/local_contract/core/media/content_media_url__local_contract_test.dart",
                        "test/local_contract/cloud/chat/chat_avatar_url_resolution__local_contract_test.dart",
                    ],
                    "cwd": ROOT,
                },
                {
                    "name": "contract-seeded-mock-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "--dart-define=CONTRACT_FIXTURE_PROFILE=full",
                        "test/local_contract/cloud/services/contract_seeded_mock_repository__local_contract_test.dart",
                    ],
                    "cwd": ROOT,
                },
            ]
        )
    if profile is VerificationProfile.INTEGRATION:
        if env_name == "beta":
            commands.append(
                {
                    "name": "alpha-beta-seed-matrix",
                    "argv": ["python3", "quwoquan_app/scripts/env/run_app_alpha_beta_seed_matrix.py"],
                }
            )
        if target_name == "gamma-local":
            commands.append(
                {
                    "name": "gamma-local-t3",
                    "argv": ["python3", "quwoquan_app/scripts/gamma/run_local_gamma_t3.py"],
                }
            )
    if profile is VerificationProfile.RELEASE:
        if target_name == "prod-hosted":
            target = get_target(load_environment_topology(), target_name)
            public_bases = target.get("publicBases") or {}
            commands.append(
                {
                    "name": "prod-public-health",
                    "argv": [
                        "python3",
                        "quwoquan_ops/cli/stackctl.py",
                        "--output-format",
                        "json",
                        "health",
                        "--target",
                        "prod-hosted",
                        "--scope",
                        "full",
                    ],
                    "env": {"CLOUD_GATEWAY_BASE_URL": str(public_bases["api"])},
                }
            )
        media_preflight_command = _target_media_preflight_profile_command(
            target_name,
            report_dir,
        )
        if media_preflight_command is not None:
            commands.append(media_preflight_command)
        media_surface_command = _seeded_media_surface_profile_command(env_name, target_name)
        if media_surface_command is not None:
            media_surface_command["stopOnFailure"] = True
            commands.append(media_surface_command)
        smoke_command = _environment_page_smoke_profile_command(
            env_name,
            target_name,
            report_dir,
        )
        if smoke_command is not None:
            commands.append(smoke_command)
        commands.append(
            {
                "name": "prod-rollout-stackctl-contract",
                "argv": ["python3", "quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py"],
            }
        )
    return commands


def _target_media_preflight_profile_command(
    target_name: str,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """在设备 Patrol 之前验证 canonical media 的 Range/MIME。"""

    if target_name == "prod-hosted":
        health_report_path = (
            report_dir / "video-range-mime-preflight" / "report.json"
            if report_dir is not None
            else env_runs_root("prod")
            / "device-matrix"
            / "video-range-mime-preflight"
            / target_name
            / "report.json"
        )
        return {
            "name": "prod-hosted-release-video-canary-preflight",
            "argv": [
                "python3",
                "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
                "--target",
                "prod-hosted",
                "--report",
                str(health_report_path),
            ],
            "stopOnFailure": True,
            "reportPath": relpath(health_report_path),
        }
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        return None
    health_report_dir = (
        report_dir / "video-range-mime-preflight"
        if report_dir is not None
        else env_runs_root(get_target(load_environment_topology(), target_name)["env"])
        / "device-matrix"
        / "video-range-mime-preflight"
        / target_name
    )
    return {
        "name": f"{target_name}-video-range-mime-preflight",
        "argv": [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "--output-format",
            "json",
            "--report-dir",
            str(health_report_dir),
            "health",
            "--target",
            target_name,
            "--scope",
            "media",
        ],
        "stopOnFailure": True,
        "reportPath": relpath(health_report_dir / "report.json"),
    }


def _read_json_object(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _current_commit_sha() -> str:
    configured = os.environ.get("GITHUB_SHA", "").strip()
    if configured:
        return configured
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _runtime_media_config_hash(target_name: str) -> str:
    """将当前 target 的 topology 与 App runtime 配置绑定到 T4 证据。"""

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target.get("env") or "").strip()
    config_path = ROOT / "quwoquan_app" / "configs" / env_name / "app_runtime.yaml"
    digest = hashlib.sha256()
    digest.update(
        json.dumps(target, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    )
    if config_path.is_file():
        digest.update(config_path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _local_video_canary_slice_key() -> str:
    try:
        assets = load_media_delivery_manifest()
    except ValueError:
        return ""
    for asset in assets:
        if (
            str(asset.get("logicalAssetId") or "").strip()
            == "media-canary-seek-125s-video"
        ):
            return str(asset.get("publicSliceKey") or "").strip().lstrip("/")
    return ""


def _video_canary_identity(target_name: str) -> dict[str, Any]:
    if target_name == "prod-hosted":
        try:
            asset_version = int(
                os.environ.get("VIDEO_PLAYBACK_CANARY_ASSET_VERSION", "0").strip(),
            )
        except ValueError:
            asset_version = 0
        return {
            "assetId": os.environ.get(
                "VIDEO_PLAYBACK_CANARY_ASSET_ID",
                "",
            ).strip(),
            "assetVersion": asset_version,
            "probeHash": os.environ.get(
                "VIDEO_PLAYBACK_CANARY_PROBE_HASH",
                "",
            ).strip(),
        }
    descriptor_path = (
        ROOT
        / "quwoquan_service"
        / "contracts"
        / "metadata"
        / "_shared"
        / "test_fixtures"
        / "media"
        / "media"
        / "video"
        / "s"
        / "media-canary-seek-125s"
        / "v1"
        / "descriptor.json"
    )
    descriptor = _read_json_object(str(descriptor_path))
    return {
        "assetId": str(
            descriptor.get("assetId") or "media-canary-seek-125s",
        ).strip(),
        "assetVersion": int(descriptor.get("assetVersion") or 1),
        "probeHash": str(descriptor.get("probeHash") or "").strip(),
    }


def _video_canary_post_id(target_name: str) -> str:
    target = get_target(load_environment_topology(), target_name)
    playback_canary = target.get("playbackCanary")
    if not isinstance(playback_canary, dict):
        return ""
    configured = str(playback_canary.get("workId") or "").strip()
    if configured:
        return configured
    env_name = str(playback_canary.get("workIdEnv") or "").strip()
    return os.environ.get(env_name or "VIDEO_PLAYBACK_CANARY_WORK_ID", "").strip()


def _profile_step(steps: list[dict[str, Any]], name_fragment: str) -> dict[str, Any]:
    for step in steps:
        if name_fragment in str(step.get("name") or ""):
            return step
    return {}


def _video_range_evidence_from_preflight(
    steps: list[dict[str, Any]],
    target_name: str,
) -> dict[str, Any]:
    """从同一次 T4 preflight 的结构化 health/report 取 Range 与 MIME。"""

    if target_name == "prod-hosted":
        step = _profile_step(steps, "release-video-canary-preflight")
        try:
            payload = json.loads(str(step.get("stdout") or ""))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            return {
                "statusCode": payload.get("rangeStatus"),
                "mimeType": payload.get("contentType"),
                "reportPath": str(step.get("reportPath") or ""),
            }
        return {}

    step = _profile_step(steps, "video-range-mime-preflight")
    report = _read_json_object(str(step.get("reportPath") or ""))
    checks = report.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name") or "") != "media-public-content-video-primary":
            continue
        return {
            "statusCode": check.get("statusCode"),
            "mimeType": check.get("contentType"),
            "reportPath": str(step.get("reportPath") or ""),
        }
    return {}


def _video_ui_evidence_from_smoke(steps: list[dict[str, Any]]) -> dict[str, Any]:
    step = _profile_step(steps, "environment-page-smoke")
    report_path = str(step.get("reportPath") or "")
    report = _read_json_object(report_path)
    runs = report.get("runs")
    if not isinstance(runs, list):
        runs = []
    successful_runs = [
        item
        for item in runs
        if isinstance(item, dict) and item.get("exitCode") == 0
    ]
    native_evidence_run: dict[str, Any] | None = None
    physical_ios_run: dict[str, Any] | None = None
    for run_item in successful_runs:
        device = run_item.get("device")
        evidence = run_item.get("evidence")
        if not isinstance(device, dict) or not isinstance(evidence, dict):
            continue
        platform = str(device.get("targetPlatform") or "").lower()
        if (
            platform.startswith("ios")
            and device.get("emulator") is False
            and physical_ios_run is None
        ):
            physical_ios_run = run_item
        if not platform.startswith("android"):
            continue
        playback = evidence.get("videoPlayback")
        if not isinstance(playback, dict):
            continue
        if (
            native_evidence_run is None
            and device.get("emulator") is False
            and playback.get("nativeFirstFrame") is True
            and playback.get("nativeSeekSettled") is True
        ):
            native_evidence_run = run_item
    selected_run = native_evidence_run or (
        successful_runs[0] if successful_runs else None
    )
    screenshot_path = ""
    selected_evidence = (
        selected_run.get("evidence") if isinstance(selected_run, dict) else None
    )
    if isinstance(selected_evidence, dict):
        evidence = selected_evidence
        screenshot = evidence.get("afterScreenshot")
        if isinstance(screenshot, dict):
            screenshot_path = str(screenshot.get("path") or "").strip()
    native_playback_raw_log_path = (
        str(selected_evidence.get("rawLogPath") or "").strip()
        if native_evidence_run is not None and isinstance(selected_evidence, dict)
        else ""
    )
    native_playback_log = Path(native_playback_raw_log_path)
    if native_playback_raw_log_path and not native_playback_log.is_absolute():
        native_playback_log = ROOT / native_playback_log
    native_playback = read_native_video_playback_evidence(native_playback_log)
    physical_android_native_evidence = (
        native_evidence_run is not None
        and native_playback.get("nativeFirstFrame") is True
        and native_playback.get("nativeSeekSettled") is True
    )
    passed = (
        str(report.get("status") or "").strip().lower() == "passed"
        and bool(successful_runs)
    )
    output_summaries = "\n".join(
        str(item.get("outputSummary") or "")
        for item in runs
        if isinstance(item, dict)
    )
    if passed:
        stage_rendered: bool | None = True
        player_ready = True
        player_error: bool | None = False
        player_state = "ready"
    elif "configured video canary stage should render" in output_summaries:
        stage_rendered = False
        player_ready = False
        player_error = None
        player_state = "stage-not-rendered"
    elif "native video player entered its explicit error state" in output_summaries:
        stage_rendered = True
        player_ready = False
        player_error = True
        player_state = "explicit-error"
    elif "native video player must reach ready state" in output_summaries:
        stage_rendered = True
        player_ready = False
        player_error = None
        player_state = "ready-timeout"
    else:
        stage_rendered = None
        player_ready = False
        player_error = None
        player_state = "unverified"
    return {
        "stageRendered": stage_rendered,
        "playerReady": player_ready,
        "playerError": player_error,
        "playerState": player_state,
        "reportPath": report_path,
        "screenshotPath": screenshot_path,
        "recordingPath": os.environ.get(
            "VIDEO_PLAYBACK_CANARY_RECORDING_PATH",
            "",
        ).strip(),
        "seekTargetsVerified": passed,
        "nativeFirstFrame": physical_android_native_evidence,
        "nativeSeekSettled": physical_android_native_evidence,
        "nativeEvidenceFromPhysicalAndroidDevice": physical_android_native_evidence,
        "nativeEvidenceDevicePlatform": (
            "android" if physical_android_native_evidence else ""
        ),
        "nativeEvidenceDeviceEmulator": (
            False if physical_android_native_evidence else None
        ),
        "nativePlaybackRawLogPath": native_playback_raw_log_path,
        "physicalIosPatrolPassed": physical_ios_run is not None,
        "seekEvidenceSource": (
            "native_settled"
            if physical_android_native_evidence
            else "unverified"
        ),
        "qoeReadbackPath": os.environ.get(
            "VIDEO_PLAYBACK_QOE_READBACK_PATH",
            "",
        ).strip(),
        "perfettoTracePath": os.environ.get(
            "VIDEO_PLAYBACK_PERFETTO_TRACE_PATH",
            "",
        ).strip(),
        "perfettoSummaryPath": os.environ.get(
            "VIDEO_PLAYBACK_PERFETTO_SUMMARY_PATH",
            "",
        ).strip(),
    }


def _runtime_media_t4_evidence(
    *,
    target_name: str,
    steps: list[dict[str, Any]],
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target.get("env") or "").strip()
    public_bases = target.get("publicBases")
    public_bases = public_bases if isinstance(public_bases, dict) else {}
    public_slice_key = (
        os.environ.get("VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY", "").strip().lstrip("/")
        if target_name == "prod-hosted"
        else _local_video_canary_slice_key()
    )
    service_evidence = {
        "videoRange": _video_range_evidence_from_preflight(steps, target_name),
    }
    ui_evidence = _video_ui_evidence_from_smoke(steps)
    media_identity = _video_canary_identity(target_name)
    post_id = _video_canary_post_id(target_name)
    video_range = service_evidence["videoRange"]
    dry_run = os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    is_passed = (
        bool(public_slice_key)
        and bool(post_id)
        and not dry_run
        and video_range.get("statusCode") == 206
        and str(video_range.get("mimeType") or "").lower().startswith("video/")
        and ui_evidence["playerReady"] is True
        and ui_evidence["playerError"] is False
        and ui_evidence["nativeFirstFrame"] is True
        and ui_evidence["nativeSeekSettled"] is True
        and ui_evidence["nativeEvidenceFromPhysicalAndroidDevice"] is True
        and ui_evidence["physicalIosPatrolPassed"] is True
        and bool(ui_evidence["qoeReadbackPath"])
        and bool(ui_evidence["perfettoTracePath"])
        and bool(ui_evidence["perfettoSummaryPath"])
    )
    return {
        "schema": "runtime-media-video-playback-t4-report",
        "scenario": "runtime_media.video_playback_t4",
        "status": "passed" if is_passed else "failed",
        "dryRun": dry_run,
        "startedAt": started_at,
        "endedAt": ended_at,
        "environment": {
            "env": env_name,
            "target": target_name,
            "rolloutStage": (
                os.environ.get("PROD_ROLLOUT_STAGE", "").strip()
                if target_name == "prod-hosted"
                else "local"
            ),
            "mediaVideoBaseUrl": str(public_bases.get("mediaVideo") or "").rstrip("/"),
            "commitSha": _current_commit_sha(),
            "configHash": _runtime_media_config_hash(target_name),
        },
        "media": {
            "publicSliceKey": public_slice_key,
            **media_identity,
        },
        "post": {
            "postId": post_id,
        },
        "serviceEvidence": service_evidence,
        "uiEvidence": ui_evidence,
    }


def _seeded_media_surface_profile_command(
    env_name: str,
    target_name: str,
) -> dict[str, Any] | None:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        return None
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    runtime_env = str(target.get("env") or env_name or "")
    if runtime_env not in {"alpha", "beta", "gamma", "prod"}:
        return None
    public_bases = target.get("publicBases") or {}
    required = {"mediaAvatar", "mediaImage", "mediaVideo"}
    if not required.issubset(public_bases):
        return None
    return {
        "name": "seeded-media-surface",
        "argv": [
            "python3",
            "quwoquan_ops/gate/verify_alpha_media_fixture_surface.py",
            "--env",
            runtime_env,
            "--target",
            target_name,
            "--avatar-base-url",
            str(public_bases["mediaAvatar"]),
            "--media-base-url",
            str(public_bases["mediaImage"]),
            "--video-base-url",
            str(public_bases["mediaVideo"]),
        ],
    }


def _environment_page_smoke_profile_command(
    env_name: str,
    target_name: str,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        return None
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    required_bases = {
        "api",
        "productOps",
        "mediaAvatar",
        "mediaImage",
        "mediaVideo",
        "mediaUpload",
    }
    if not required_bases.issubset(public_bases):
        return None
    runtime_env = str(target.get("env") or env_name or "alpha")
    if target_name in {"prod-sim", "prod-hosted"}:
        runtime_env = "prod"
    data_source = "mock" if target_name == "alpha-local" else "remote"
    playback_canary = target.get("playbackCanary")
    configured_canary_work_id = (
        str(playback_canary.get("workId") or "").strip()
        if isinstance(playback_canary, dict)
        else ""
    )
    canary_work_id_env = (
        str(playback_canary.get("workIdEnv") or "").strip()
        if isinstance(playback_canary, dict)
        else ""
    ) or "VIDEO_PLAYBACK_CANARY_WORK_ID"
    video_playback_canary_work_id = (
        configured_canary_work_id
        or os.environ.get(canary_work_id_env, "").strip()
    )
    token = "" if target_name == "gamma-local" else _resolve_test_auth_token(runtime_env)
    smoke_report = (
        report_dir / "environment-page-smoke" / "report.json"
        if report_dir is not None
        else env_runs_root(env_name) / "device-matrix" / "environment-smoke" / f"{target_name}.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--report",
        str(smoke_report),
        "--env-name",
        "local-gamma" if target_name == "gamma-local" else target_name,
        "--runtime-env",
        runtime_env,
        "--api-contract-env",
        runtime_env,
        "--data-source",
        data_source,
        "--gateway-base-url",
        str(public_bases["api"]),
        "--product-ops-base-url",
        str(public_bases["productOps"]),
        "--media-avatar-base-url",
        str(public_bases["mediaAvatar"]),
        "--media-image-base-url",
        str(public_bases["mediaImage"]),
        "--media-video-base-url",
        str(public_bases["mediaVideo"]),
        "--media-upload-base-url",
        str(public_bases["mediaUpload"]),
        "--video-playback-canary-work-id",
        video_playback_canary_work_id,
        "--target",
        "test/user_acceptance/patrol/environment/video_playback_canary__user_acceptance_test.dart",
    ]
    platform = os.environ.get("STACKCTL_PAGE_SMOKE_PLATFORM", "").strip()
    if platform:
        argv.extend(["--platform", platform])
    device_id = os.environ.get("STACKCTL_PAGE_SMOKE_DEVICE_ID", "").strip()
    if device_id:
        argv.extend(["--device-id", device_id])
    if os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip() in {"1", "true", "yes"}:
        argv.append("--dry-run")
    command_env: dict[str, str] = {}
    if target_name != "gamma-local":
        if token:
            command_env["TEST_AUTH_TOKEN"] = token
        for key in (
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_SUB_ACCOUNT_ID",
        ):
            value = os.environ.get(key, "").strip()
            if value:
                command_env[key] = value
    command = {
        "name": f"{target_name}-environment-page-smoke",
        "argv": argv,
        "cwd": ROOT,
        "blocking": target_name != "alpha-local",
        "reportPath": relpath(smoke_report),
    }
    if command_env:
        command["env"] = command_env
    return command


def fetch_url(
    url: str,
    timeout: float = 6.0,
    *,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
    headers: dict[str, str] | None = None,
    resolve_host: str = "",
) -> tuple[bool, int | None, str, str]:
    retry_markers = (
        "timed out",
        "Remote end closed connection without response",
        "Connection reset",
        "Connection closed",
    )
    total_attempts = max(1, retry_attempts)
    for attempt in range(1, total_attempts + 1):
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with _temporary_host_resolution(url, resolve_host):
                if resolve_host:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}),
                        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
                    )
                    response = opener.open(request, timeout=timeout)
                else:
                    response = urllib.request.urlopen(
                        request,
                        timeout=timeout,
                        context=ssl._create_unverified_context(),
                    )
            with response:
                body = response.read().decode("utf-8", errors="replace")
                return (
                    True,
                    int(response.status),
                    body[:500],
                    str(response.headers.get("Content-Type") or ""),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), body[:500], str(exc.headers.get("Content-Type") or "")
        except Exception as exc:
            message = str(exc)
            if attempt >= total_attempts or not any(marker in message for marker in retry_markers):
                return False, None, message, ""
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown fetch failure", ""


@contextlib.contextmanager
def _temporary_host_resolution(url: str, resolve_host: str):
    """Connect a local public host to loopback while retaining its TLS SNI name."""
    expected_host = urllib.parse.urlparse(url).hostname or ""
    if not resolve_host or not expected_host:
        yield
        return

    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        if host == expected_host:
            return original_getaddrinfo(resolve_host, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _local_public_connect_host(
    topology: dict[str, Any],
    target_name: str,
    url: str,
) -> str:
    target = get_target(topology, target_name)
    if str(target.get("backend") or "").strip() != "local":
        return ""
    hostname = urllib.parse.urlparse(url).hostname or ""
    public_bases = target.get("publicBases") or {}
    public_hosts = {
        urllib.parse.urlparse(str(base)).hostname
        for base in public_bases.values()
        if urllib.parse.urlparse(str(base)).hostname
    }
    return "127.0.0.1" if hostname in public_hosts else ""


def _read_json_payload(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return load_json_yaml(path)
    except Exception:  # noqa: BLE001
        return None


def _resolve_test_auth_token(env_name: str) -> str:
    token_envs = {
        "alpha": ("ALPHA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "gamma": ("GAMMA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "prod": ("PROD_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
    }
    for key in token_envs.get(env_name, ("TEST_AUTH_TOKEN",)):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _run_script_probe(
    *,
    name: str,
    scope: str,
    argv: list[str],
    report_file: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    result = run(argv, env=env)
    output = "\n".join(filter(None, [result.stdout, result.stderr])).strip()
    report_payload = _read_json_payload(report_file) if report_file else None
    report_status = ""
    report_findings: list[str] = []
    preview = output[:500]
    if isinstance(report_payload, dict):
        report_status = str(report_payload.get("status", "")).strip().lower()
        preview = str(
            report_payload.get("blockingReason")
            or report_payload.get("summary")
            or report_payload.get("status")
            or preview
        )[:500]
        for item in ensure_list(report_payload.get("findings")):
            if isinstance(item, str) and item.strip():
                report_findings.append(item.strip())
        blocking_reason = str(report_payload.get("blockingReason", "")).strip()
        if blocking_reason:
            report_findings.append(blocking_reason)
    ok = result.returncode == 0 and report_status not in {"failed", "gate_block", "error"}
    if not ok and not report_findings:
        report_findings.append(
            f"{scope}/{name} failed: exit={result.returncode} {argv[-1] if argv else name}"
        )
    payload = {
        "name": name,
        "scope": scope,
        "type": "script",
        "argv": argv,
        "ok": ok,
        "statusCode": result.returncode,
        "bodyPreview": preview,
        "skipped": False,
        "reportPath": relpath(report_file) if report_file else "",
    }
    return payload, output, report_findings


def _run_environment_integration_probe(
    topology: dict[str, Any],
    target_name: str,
    report_dir: Path,
) -> tuple[dict[str, Any], str, list[str]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    public_bases = target.get("publicBases") or {}
    report_file = report_dir / "integration-probe.json"
    argv = [
        "python3",
        "quwoquan_ops/cli/probes/run_environment_integration_probe.py",
        "--env",
        env_name,
        "--base-url",
        str(public_bases["api"]),
        "--report",
        str(report_file),
    ]
    if target_name == "prod-hosted":
        argv.extend(
            [
                "--mode",
                "post-deploy",
                "--request-timeout-seconds",
                "20",
                "--retry-attempts",
                "3",
                "--retry-sleep-seconds",
                "3",
            ]
        )
    product_ops = str(public_bases.get("productOps") or "").strip()
    if product_ops:
        argv.extend(["--product-ops-base-url", product_ops])
    resolve_host = _local_public_connect_host(
        topology,
        target_name,
        str(public_bases["api"]),
    )
    if resolve_host:
        argv.extend(["--resolve-host", resolve_host])
    token = _resolve_test_auth_token(env_name)
    if env_name in {"beta", "gamma"} and not token:
        try:
            token = open_local_acceptance_session(
                str(public_bases["api"]),
                environment=env_name,
                target_name=target_name,
                resolve_host=resolve_host,
            ).access_token
        except (RuntimeError, ValueError) as exc:
            finding = f"{target_name} integration auth failed: {exc}"
            return (
                {
                    "name": "integration-readonly",
                    "scope": "full",
                    "type": "script",
                    "argv": argv,
                    "ok": False,
                    "statusCode": 1,
                    "bodyPreview": finding,
                    "skipped": False,
                    "reportPath": relpath(report_file),
                },
                finding,
                [finding],
            )
    probe_env: dict[str, str] | None = None
    if token:
        probe_env = {"TEST_AUTH_TOKEN": token}
        if env_name == "gamma":
            probe_env["GAMMA_TEST_AUTH_TOKEN"] = token
        elif env_name == "beta":
            probe_env["BETA_TEST_AUTH_TOKEN"] = token
        elif env_name == "prod":
            probe_env["PROD_TEST_AUTH_TOKEN"] = token
    return _run_script_probe(
        name="integration-readonly",
        scope="full",
        argv=argv,
        report_file=report_file,
        env=probe_env,
    )


def _script_probe_plan_for_target(
    topology: dict[str, Any],
    target_name: str,
) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    if target_name == "alpha-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "beta-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "prod-sim":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "prod-hosted":
        return [
            {"name": "integration-readonly", "kind": "readonly-http"},
            {"name": "release-state", "kind": "rollout-state"},
        ]
    if str(target.get("env")) == "gamma" and target_name == "gamma-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    return []


def _health_request_policy(target_name: str, scope: str) -> dict[str, float | int]:
    policy: dict[str, float | int] = {
        "timeoutSeconds": 6.0,
        "retryAttempts": 2,
        "retrySleepSeconds": 2.0,
    }
    if target_name == "prod-hosted":
        policy.update(
            {
                "timeoutSeconds": 15.0 if scope == "edge" else 20.0,
                "retryAttempts": 3,
                "retrySleepSeconds": 3.0,
            }
        )
    return policy


def _script_probes_for_target(
    topology: dict[str, Any],
    target_name: str,
    scope: str,
    report_dir: Path,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[str]]:
    if scope != "full":
        return [], [], []
    statuses: list[dict[str, Any]] = []
    stdout_sections: list[tuple[str, str]] = []
    findings: list[str] = []

    if target_name in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        status, output, probe_findings = _run_environment_integration_probe(
            topology,
            target_name,
            report_dir,
        )
        statuses.append(status)
        stdout_sections.append((status["name"], output))
        findings.extend(probe_findings)
    return statuses, stdout_sections, findings


def _release_state_dir() -> Path:
    # release-state 唯一真相源：stackctl CAS ledger 与 platform-ops 只读投影共用。
    configured = os.environ.get("QWQ_PROD_RELEASE_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return target_process_dir("prod-hosted") / "release-state"


def _load_release_state(service: str = PROD_RELEASE_UNIT) -> dict[str, str]:
    state_path = _release_state_dir() / f"{service}.state"
    payload: dict[str, str] = {}
    if not state_path.exists():
        return payload
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def _update_release_state(
    service: str,
    *,
    from_image: str,
    to_image: str,
    from_config: str,
    to_config: str,
    step: str,
    stage: str,
    decision: str,
    manifest_digest: str,
    expected_generation: int,
    receipt_id: str,
) -> dict[str, str]:
    state_dir = _release_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{service}.state"
    current = _load_release_state(service)
    current_generation = int(current.get("generation") or 0)
    if current_generation != expected_generation:
        raise RuntimeError(
            "release ledger CAS conflict: "
            f"expected generation {expected_generation}, found {current_generation}"
        )
    payload = {
        "schema": "prod-release-ledger",
        "service": service,
        "from_image": from_image,
        "to_image": to_image,
        "from_config": from_config,
        "to_config": to_config,
        "step": step,
        "stage": stage,
        "decision": decision,
        "manifest_digest": manifest_digest,
        "generation": str(expected_generation + 1),
        "receipt_id": receipt_id,
        "updated_at": utc_now(),
    }
    lines = [f"{key}={value}" for key, value in payload.items()]
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=state_dir,
        prefix=f".{service}.",
        suffix=".state.tmp",
        delete=False,
    ) as handle:
        handle.write("\n".join(lines) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary_path = Path(handle.name)
    os.replace(temporary_path, state_path)
    directory_fd = os.open(state_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return payload


def _release_stage_from_state(state: dict[str, str]) -> str:
    if state.get("schema") != "prod-release-ledger":
        raise RuntimeError("release ledger schema is not canonical")
    stage = state.get("stage", "").strip()
    if stage:
        return stage
    raise RuntimeError("release ledger missing canonical stage")


def _validate_release_transition(
    state: dict[str, str],
    *,
    from_image: str,
    to_image: str,
    from_config: str,
    to_config: str,
    stage: str,
    manifest_digest: str,
) -> tuple[str, int]:
    if not state:
        if stage != "gray-initial":
            raise RuntimeError("release ledger must start at gray-initial")
        return "advance", 0

    generation = int(state.get("generation") or 0)
    current_stage = _release_stage_from_state(state)
    same_target = (
        state.get("from_image") == from_image
        and state.get("to_image") == to_image
        and state.get("from_config") == from_config
        and state.get("to_config") == to_config
    )
    if same_target:
        if state.get("manifest_digest") and state.get("manifest_digest") != manifest_digest:
            raise RuntimeError("release ledger manifest digest drift")
        if current_stage == stage:
            decision = state.get("decision", "continue")
            if decision == "continue":
                return "replay", generation
            if decision in {"pause", "rollback_failed"}:
                return "reevaluate", generation
            raise RuntimeError(
                f"release ledger stage is not replayable with decision={decision}"
            )
        if state.get("decision", "continue") != "continue":
            raise RuntimeError("paused or failed release cannot advance to the next stage")
        expected_next = {"gray-initial": "carry-on", "carry-on": "full"}.get(current_stage)
        if expected_next != stage:
            raise RuntimeError(
                f"release ledger stage CAS conflict: {current_stage} cannot advance to {stage}"
            )
        return "advance", generation

    if stage != "gray-initial":
        raise RuntimeError("new release target must start at gray-initial")
    if state.get("to_image") != from_image or state.get("to_config") != from_config:
        raise RuntimeError(
            "release ledger base CAS conflict: requested from image/config do not match current stable target"
        )
    if current_stage != "full" or state.get("decision", "continue") not in {
        "continue",
        "rolled_back",
    }:
        raise RuntimeError("previous release is not in a stable full state")
    return "advance", generation


@contextlib.contextmanager
def _prod_release_lock() -> Any:
    lock_path = _release_state_dir() / ".global-deploy.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = f"{os.getpid()}-{time.time_ns()}"
    if lock_path.is_dir():
        raise RuntimeError(
            "legacy release lock directory must be removed after operator inspection: "
            f"{lock_path}"
        )
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            raise RuntimeError(
                f"prod release lock is held by {holder}: {lock_path}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _commit_release_transition(
    *,
    service: str,
    from_image: str,
    to_image: str,
    from_config: str,
    to_config: str,
    step: str,
    stage: str,
    decision: str,
    manifest_digest: str,
    expected_generation: int,
    receipt_id: str,
    slo_readback: dict[str, Any] | None,
) -> tuple[dict[str, str], Path]:
    receipt_dir = _release_state_dir() / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    attempt_id = receipt_id
    receipt = {
        "schema": "prod-release-receipt",
        "attemptId": attempt_id,
        "service": service,
        "fromImage": from_image,
        "toImage": to_image,
        "fromConfig": from_config,
        "toConfig": to_config,
        "step": step,
        "stage": stage,
        "decision": decision,
        "manifestDigest": manifest_digest,
        "expectedGeneration": expected_generation,
        "committedGeneration": expected_generation + 1,
        "sloReadback": slo_readback or {},
    }
    receipt_id = hashlib.sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    receipt["receiptId"] = receipt_id
    receipt_path = receipt_dir / f"{receipt_id}.json"
    encoded = json.dumps(
        receipt,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        with receipt_path.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if receipt_path.read_text(encoding="utf-8") != encoded:
            raise RuntimeError(f"release receipt collision: {receipt_path}")
    directory_fd = os.open(receipt_dir, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    state = _update_release_state(
        service,
        from_image=from_image,
        to_image=to_image,
        from_config=from_config,
        to_config=to_config,
        step=step,
        stage=stage,
        decision=decision,
        manifest_digest=manifest_digest,
        expected_generation=expected_generation,
        receipt_id=receipt_id,
    )
    return state, receipt_path


def _archive_release_artifact(manifest_path: Path, manifest_digest: str) -> Path:
    archive_root = _release_state_dir() / "artifacts"
    archive_root.mkdir(parents=True, exist_ok=True)
    digest_id = manifest_digest.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", digest_id) is None:
        raise RuntimeError("release artifact digest is invalid")
    target = archive_root / digest_id
    source = manifest_path.parent
    if target.exists():
        archived_manifest = target / "manifest.json"
        if not archived_manifest.is_file():
            raise RuntimeError(f"release artifact archive is incomplete: {target}")
        archived = json.loads(archived_manifest.read_text(encoding="utf-8"))
        declared = str(archived.get("manifestDigest") or "") if isinstance(archived, dict) else ""
        if declared != manifest_digest:
            raise RuntimeError(f"release artifact archive digest collision: {target}")
        return target
    temporary = archive_root / f".{digest_id}.{os.getpid()}.tmp"
    shutil.copytree(source, temporary)
    os.replace(temporary, target)
    archives = sorted(
        (path for path in archive_root.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in archives[2:]:
        shutil.rmtree(stale)
    return target


def _sync_release_ledger_projection(
    service: str,
    receipt_id: str,
) -> None:
    state_path = _release_state_dir() / f"{service}.state"
    receipt_path = _release_state_dir() / "receipts" / f"{receipt_id}.json"
    if not state_path.is_file() or not receipt_path.is_file():
        raise RuntimeError("release ledger projection source is incomplete")
    with tempfile.TemporaryDirectory(prefix="quwoquan-release-ledger-") as temporary:
        root = Path(temporary)
        projection = root / "release-ledger"
        (projection / "receipts").mkdir(parents=True)
        shutil.copy2(state_path, projection / state_path.name)
        shutil.copy2(receipt_path, projection / "receipts" / receipt_path.name)
        result = run(
            [
                "bash",
                "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh",
                "--plane",
                "service",
                "--source-dir",
                str(root),
            ]
        )
    if result.returncode != 0:
        raise RuntimeError(
            "release ledger projection sync failed: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def socket_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def print_result(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    if args.output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload["summary"])
        report_dir = payload.get("reportDir")
        if report_dir:
            print(f"report: {report_dir}")
        for line in payload.get("details", []):
            print(f"- {line}")
    return int(payload.get("exitCode", 0))


def _legal_static_command(
    subcommand: str,
    env_name: str,
    *,
    output_root: str = ".qwq_output/env",
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    cmd = [
        "python3",
        "quwoquan_ops/cli/legal_static.py",
        subcommand,
        "--env",
        env_name,
        "--output-root",
        output_root,
    ]
    result = run(cmd)
    payload: dict[str, Any] = {}
    if result.stdout.strip():
        try:
            loaded = json.loads(result.stdout)
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = {}
    payload.setdefault("argv", cmd)
    payload.setdefault("exitCode", result.returncode)
    return result, payload


def _command_package_legal_static(args: argparse.Namespace) -> dict[str, Any]:
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    if args.service or args.include_services:
        timing = _finish_timing(started_monotonic, started_at)
        details = ["legal-static packages cannot include service packages"]
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl legal-static package failed for {env_name}",
            details=details,
            extra={"env": env_name, "kind": "legal-static"},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl legal-static package failed for {env_name}",
            "details": details,
            "reportDir": relpath(report_dir),
            **timing,
        }

    result, legal_payload = _legal_static_command("package", env_name)
    timing = _finish_timing(started_monotonic, started_at)
    status = "ok" if result.returncode == 0 else "failed"
    details = []
    if result.returncode == 0:
        details.append(f"legal-static package ready: {legal_payload.get('packageDir', '')}")
        if legal_payload.get("currentPointer"):
            details.append(f"legal-static current pointer: {legal_payload['currentPointer']}")
    else:
        issues = legal_payload.get("issues") if isinstance(legal_payload.get("issues"), list) else []
        details.extend(str(issue) for issue in issues)
        if not details:
            details.append(result.stderr.strip() or result.stdout.strip() or "legal-static package failed")
    report = {
        "status": status,
        "command": "package",
        "kind": "legal-static",
        "env": env_name,
        "target": target_name,
        "timestamp": utc_now(),
        "step": {
            "name": "legal-static-package",
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "payload": legal_payload,
        },
        **timing,
    }
    write_json(report_dir / "report.json", report)
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status=status,
        summary=(
            f"stackctl legal-static package completed for {env_name}"
            if status == "ok"
            else f"stackctl legal-static package failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "kind": "legal-static"},
        timing=timing,
    )
    _write_stdout_markdown(
        report_dir,
        [("legal-static-package", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl legal-static package completed for {env_name}"
            if status == "ok"
            else f"stackctl legal-static package failed for {env_name}"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_package(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "kind", "runtime") == "legal-static":
        return _command_package_legal_static(args)

    topology = load_environment_topology()
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    details: list[str] = []
    reports: list[dict[str, Any]] = []

    app_cmd = ["bash", "quwoquan_app/scripts/env/build_app_env_package.sh", "--env", env_name]
    app_result = run(app_cmd)
    reports.append(
        {
            "name": "app-package",
            "argv": app_cmd,
            "exitCode": app_result.returncode,
            "stdout": app_result.stdout,
            "stderr": app_result.stderr,
        }
    )
    if app_result.returncode != 0:
        timing = _finish_timing(started_monotonic, started_at)
        write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl package failed for {env_name}",
            details=[app_result.stderr.strip() or app_result.stdout.strip()],
            extra={"env": env_name},
            timing=timing,
        )
        _write_stdout_markdown(report_dir, [("app-package", "\n".join(filter(None, [app_result.stdout, app_result.stderr])))])
        return {
            "exitCode": app_result.returncode,
            "summary": f"stackctl package failed for {env_name}",
            "details": [app_result.stderr.strip() or app_result.stdout.strip()],
            "reportDir": relpath(report_dir),
            **timing,
        }
    details.append(f"app package ready: {relpath(app_release_dir(env_name))}")

    if args.include_services or args.service:
        services = [args.service] if args.service else _all_services()
        for service in services:
            svc_cmd = [
                "bash",
                "quwoquan_service/scripts/runtime/build_service_env_package.sh",
                "--service",
                service,
                "--env",
                env_name,
            ]
            svc_result = run(svc_cmd)
            reports.append(
                {
                    "name": f"service-package:{service}",
                    "argv": svc_cmd,
                    "exitCode": svc_result.returncode,
                    "stdout": svc_result.stdout,
                    "stderr": svc_result.stderr,
                }
            )
            if svc_result.returncode != 0:
                timing = _finish_timing(started_monotonic, started_at)
                write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
                _write_summary_bundle(
                    report_dir,
                    command="package",
                    target=target_name,
                    status="failed",
                    summary=f"stackctl package failed for {service}/{env_name}",
                    details=[svc_result.stderr.strip() or svc_result.stdout.strip()],
                    extra={"env": env_name},
                    timing=timing,
                )
                _write_stdout_markdown(
                    report_dir,
                    [(f"service-package:{service}", "\n".join(filter(None, [svc_result.stdout, svc_result.stderr])))],
                )
                return {
                    "exitCode": svc_result.returncode,
                    "summary": f"stackctl package failed for {service}/{env_name}",
                    "details": [svc_result.stderr.strip() or svc_result.stdout.strip()],
                    "reportDir": relpath(report_dir),
                    **timing,
                }
            details.append(f"service package ready: {relpath(service_release_dir(env_name, service))}")

    if env_name == "prod":
        try:
            materialized_config_version = _materialize_prod_release_artifact()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            timing = _finish_timing(started_monotonic, started_at)
            write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary="stackctl package failed while materializing prod release artifact",
                details=[str(exc)],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": 1,
                "summary": "stackctl package failed while materializing prod release artifact",
                "details": [str(exc)],
                "reportDir": relpath(report_dir),
                **timing,
            }
        if materialized_config_version:
            details.append(
                f"prod release artifact materialized: configVersion={materialized_config_version}"
            )

    try:
        shared_package_dir = _build_runtime_shared_package(env_name)
    except (OSError, FileNotFoundError) as exc:
        timing = _finish_timing(started_monotonic, started_at)
        write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl package failed while building shared runtime package for {env_name}",
            details=[str(exc)],
            extra={"env": env_name},
            timing=timing,
        )
        return {
            "exitCode": 1,
            "summary": f"stackctl package failed while building shared runtime package for {env_name}",
            "details": [str(exc)],
            "reportDir": relpath(report_dir),
            **timing,
        }
    details.append(f"runtime shared package ready: {relpath(shared_package_dir)}")

    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok",
        "command": "package",
        "env": env_name,
        "target": target_name,
        "timestamp": utc_now(),
        "reportDir": relpath(report_dir),
        "topologyTarget": get_target(topology, target_name),
        "steps": reports,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status="ok",
        summary=f"stackctl package completed for {env_name}",
        details=details,
        extra={"env": env_name},
        timing=timing,
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl package completed for {env_name}",
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_verify_legal_static(
    args: argparse.Namespace,
    profile: VerificationProfile,
) -> dict[str, Any]:
    env_name = args.env or (get_target(load_environment_topology(), args.target).get("env") if args.target else "all")
    target_name = args.target or (DEFAULT_TARGET_BY_ENV[env_name] if env_name in ENVIRONMENTS else "repo")
    report_dir = resolve_report_dir(args, env_name if env_name in ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _start_timing()
    package_envs = [env_name] if env_name in ENVIRONMENTS else list(ENVIRONMENTS)
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    stdout_sections: list[tuple[str, str]] = []

    for package_env in package_envs:
        package_args = argparse.Namespace(
            command="package",
            kind="legal-static",
            env=package_env,
            service="",
            include_services=False,
            target=args.target or DEFAULT_TARGET_BY_ENV[package_env],
            output_format="json",
            report_dir=str(report_dir / f"package-{package_env}"),
        )
        package_payload = command_package(package_args)
        steps.append(
            {
                "kind": "package",
                "packageKind": "legal-static",
                "env": package_env,
                "exitCode": package_payload["exitCode"],
                "details": package_payload.get("details", []),
                "reportDir": package_payload.get("reportDir", ""),
            }
        )
        if package_payload["exitCode"] != 0:
            issues.append(
                f"legal-static package failed for {package_env}: "
                + "; ".join(package_payload.get("details", []))
            )
            continue

        verify_result, verify_payload = _legal_static_command("verify-package", package_env)
        steps.append(
            {
                "kind": "verify",
                "packageKind": "legal-static",
                "env": package_env,
                "exitCode": verify_result.returncode,
                "stdout": verify_result.stdout,
                "stderr": verify_result.stderr,
                "payload": verify_payload,
            }
        )
        stdout_sections.append(
            (
                f"legal-static-verify:{package_env}",
                "\n".join(filter(None, [verify_result.stdout, verify_result.stderr])),
            )
        )
        if verify_result.returncode != 0:
            verify_issues = verify_payload.get("issues") if isinstance(verify_payload.get("issues"), list) else []
            detail = "; ".join(str(issue) for issue in verify_issues)
            issues.append(
                f"legal-static verify failed for {package_env}: "
                + (detail or verify_result.stderr.strip() or verify_result.stdout.strip())
            )

    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "kind": "legal-static",
        "profile": profile.value,
        "timestamp": utc_now(),
        "steps": steps,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    _write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary="stackctl legal-static verify passed" if not issues else "stackctl legal-static verify failed",
        details=issues or [f"ran {len(steps)} legal-static checks"],
        extra={"kind": "legal-static", "profile": profile.value},
        timing=timing,
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": "stackctl legal-static verify passed" if not issues else "stackctl legal-static verify failed",
        "details": issues or [f"ran {len(steps)} legal-static checks"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    profile = VerificationProfile(args.profile)
    if args.kind == "legal-static":
        if profile is VerificationProfile.BASELINE:
            return {
                "exitCode": 2,
                "summary": "stackctl verify baseline does not verify legal-static",
                "details": [
                    "baseline must not create or read disposable release output; "
                    "use smoke, integration, or release"
                ],
            }
        return _command_verify_legal_static(args, profile)

    env_name = args.env or (get_target(load_environment_topology(), args.target).get("env") if args.target else "")
    if profile is VerificationProfile.BASELINE and env_name:
        return {
            "exitCode": 2,
            "summary": "stackctl verify baseline does not accept an environment",
            "details": ["baseline must run without --env or --target"],
        }
    if profile.requires_environment and env_name not in ENVIRONMENTS:
        return {
            "exitCode": 2,
            "summary": f"stackctl verify {profile.value} requires --env or --target",
            "details": ["environment-scoped profiles must name one environment"],
        }
    if profile is VerificationProfile.BASELINE and args.kind == "packaging":
        return {
            "exitCode": 2,
            "summary": "stackctl verify baseline does not verify packaging",
            "details": [
                "baseline must not read disposable release output; use an environment profile"
            ],
        }
    target_name = args.target or (DEFAULT_TARGET_BY_ENV[env_name] if env_name in ENVIRONMENTS else "repo")
    report_dir = resolve_report_dir(args, env_name if env_name in ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _start_timing()
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    package_envs = [env_name] if env_name in ENVIRONMENTS and profile.requires_environment else []
    for package_env in package_envs:
        package_args = argparse.Namespace(
            command="package",
            kind="runtime",
            env=package_env,
            service="",
            include_services=True,
            target=args.target or DEFAULT_TARGET_BY_ENV[package_env],
            output_format="json",
            report_dir=str(report_dir / f"package-{package_env}"),
        )
        package_payload = command_package(package_args)
        steps.append(
            {
                "kind": "package",
                "env": package_env,
                "exitCode": package_payload["exitCode"],
                "details": package_payload.get("details", []),
                "reportDir": package_payload.get("reportDir", ""),
            }
        )
        if package_payload["exitCode"] != 0:
            issues.append(f"package failed for {package_env}: {'; '.join(package_payload.get('details', []))}")
    stdout_sections: list[tuple[str, str]] = []
    commands = _selected_verify_commands(
        args.kind,
        env_name if env_name in ENVIRONMENTS else "",
        profile=profile,
    )
    for command in commands:
        result = run(command)
        command_key = " ".join(command)
        steps.append(
            {
                "kind": "verify",
                "group": args.kind,
                "argv": command,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((command_key, "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0:
            issues.append(result.stderr.strip() or result.stdout.strip() or "unknown verify failure")
    if (phase := profile.readiness_phase) is not None:
        readiness_payload = command_content_readiness(
            argparse.Namespace(
                command="content-readiness",
                phase=phase.value,
                env=env_name,
                output_format="json",
                report_dir=str(report_dir / "content-readiness"),
            )
        )
        steps.append(
            {
                "kind": "readiness",
                "phase": phase.value,
                "exitCode": readiness_payload["exitCode"],
                "reportDir": readiness_payload.get("reportDir", ""),
                "details": readiness_payload.get("details", []),
            }
        )
        if readiness_payload["exitCode"] != 0:
            timing = _finish_timing(started_monotonic, started_at)
            payload = {
                "status": ProbeOutcome.GATE_BLOCK.value,
                "command": "verify",
                "timestamp": utc_now(),
                "kind": args.kind,
                "profile": profile.value,
                "steps": steps,
                **timing,
            }
            write_json(report_dir / "report.json", payload)
            write_json(report_dir / "findings.json", {"issues": readiness_payload.get("details", [])})
            _write_summary_bundle(
                report_dir,
                command="verify",
                target=target_name,
                status="blocked",
                summary=f"stackctl verify {profile.value} is GATE_BLOCK",
                details=readiness_payload.get("details", []),
                extra={"kind": args.kind, "profile": profile.value},
                timing=timing,
            )
            return {
                "exitCode": 2,
                "summary": f"stackctl verify {profile.value} is GATE_BLOCK",
                "details": readiness_payload.get("details", []),
                "reportDir": relpath(report_dir),
                **timing,
            }
    for profile_command in _selected_profile_commands(
        env_name,
        target_name,
        profile,
        report_dir,
    ):
        result = run(
            profile_command["argv"],
            cwd=profile_command.get("cwd"),
            env=profile_command.get("env"),
        )
        blocking = bool(profile_command.get("blocking", True))
        steps.append(
            {
                "kind": "profile",
                "profile": profile.value,
                "name": profile_command["name"],
                "argv": profile_command["argv"],
                "exitCode": result.returncode,
                "blocking": blocking,
                "reportPath": profile_command.get("reportPath", ""),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((profile_command["name"], "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0 and blocking:
            issues.append(
                f"{profile_command['name']} failed: "
                + (result.stderr.strip() or result.stdout.strip() or "unknown profile failure")
            )
            if profile_command.get("stopOnFailure"):
                break
    timing = _finish_timing(started_monotonic, started_at)
    t4_evidence_path = ""
    if (
        profile is VerificationProfile.RELEASE
        and target_name
        in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}
    ):
        t4_evidence = _runtime_media_t4_evidence(
            target_name=target_name,
            steps=steps,
            started_at=timing["startedAt"],
            ended_at=timing["endedAt"],
        )
        t4_evidence_file = report_dir / "runtime_media_t4_evidence.json"
        write_json(t4_evidence_file, t4_evidence)
        t4_evidence_path = relpath(t4_evidence_file)
        if t4_evidence["status"] != "passed":
            issues.append(
                "runtime media T4 evidence is incomplete; "
                f"inspect {t4_evidence_path}",
            )
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "timestamp": utc_now(),
        "kind": args.kind,
        "profile": profile.value,
        "steps": steps,
        "runtimeMediaT4EvidencePath": t4_evidence_path,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    _write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary="stackctl verify passed" if not issues else "stackctl verify failed",
        details=issues or [f"ran {len(steps)} checks"],
        extra={"kind": args.kind, "profile": profile.value},
        timing=timing,
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": "stackctl verify passed" if not issues else "stackctl verify failed",
        "details": issues or [f"ran {len(steps)} checks"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def _optional_product_telemetry_environment(
    environment: str,
    target_name: str,
) -> tuple[dict[str, str], str]:
    try:
        bundle = load_product_telemetry_sls(environment, target_name)
    except RuntimeError as exc:
        return {"QWQ_PRODUCT_TELEMETRY_AVAILABLE": "0"}, str(exc)
    return {
        **bundle.environment,
        "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "1",
    }, ""


def command_up(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    started_monotonic, started_at = _start_timing()
    if not args.env and not args.target:
        try:
            args.env = pick_dev_up_env(label="[stackctl up]")
        except RuntimeError as exc:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl up failed",
                "details": [str(exc)],
                **timing,
            }

    if bool(args.env) == bool(args.target):
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["provide exactly one of --env or --target"],
            **timing,
        }

    requested_target = args.target
    if args.env:
        requested_target = DEV_UP_STACK_TARGETS[args.env]
        if not requested_target:
            requested_target = app_target_for_env(args.env)

    target = get_target(topology, requested_target)
    env_name = str(target["env"])
    report_target = args.env or requested_target
    report_dir = resolve_report_dir(args, env_name, report_target)
    if args.workload == "full" and requested_target in {"beta-local", "gamma-local"}:
        try:
            load_product_telemetry_sls(env_name, requested_target)
        except (RuntimeError, ValueError) as exc:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": f"stackctl up {requested_target} is GATE_BLOCK",
                "details": [
                    "full workload requires commercial telemetry",
                    str(exc),
                    "use --workload content-release for import/API/media validation",
                ],
                "reportDir": relpath(report_dir),
                **timing,
            }
    steps: list[dict[str, Any]] = []
    interactive = _is_interactive_terminal()
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
                _progress_print(f"{stage} {message}")
            else:
                _progress_print(f"[stackctl up] {stage} {message}")

    def run_stage(
        stage: str,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        live_prefix: str = "",
    ) -> subprocess.CompletedProcess[str]:
        nonlocal stage_index
        stage_index += 1
        stage_header = _format_stage_header(stage_index, expected_stage_total, stage)
        announce(stage_header, "started", numbered=True)
        stage_started = time.monotonic()
        result = _run_with_live_output(argv, env=env, prefix=live_prefix)
        duration = _format_duration_ms(int((time.monotonic() - stage_started) * 1000))
        status = "completed" if result.returncode == 0 else f"failed (exit={result.returncode})"
        announce(stage_header, f"{status} in {duration}", numbered=True)
        return result

    def maybe_resolve_device_id(*, include_web: bool) -> str:
        if args.skip_app:
            return ""
        if args.device_id:
            return args.device_id
        return resolve_device_id(
            include_mobile=True,
            include_web=include_web,
            include_desktop=False,
            label="[stackctl up]",
        )

    def start_app_process(env_key: str, device_id: str) -> dict[str, Any]:
        nonlocal stage_index
        launch_log = report_dir / f"app-launch-{device_id.replace('/', '_')}.log"
        stage_index += 1
        stage_header = _format_stage_header(stage_index, expected_stage_total, "app-launch")
        announce(stage_header, f"starting for {env_key}/{device_id}", numbered=True)
        try:
            process = launch_app(
                env_key,
                device_id,
                topology=topology,
                rollout_mode=args.rollout_mode,
                log_path=launch_log,
            )
        except RuntimeError as exc:
            raise RuntimeError(f"app launch failed for {env_key}/{device_id}: {exc}") from exc
        return {
            "process": process,
            "command": build_start_app_command(
                env_key,
                device_id,
                topology=topology,
                rollout_mode=args.rollout_mode,
            ),
            "log_path": launch_log,
            "stageHeader": stage_header,
        }

    def tail_beta_background_logs() -> dict[str, Any]:
        beta_log_dir = _local_runtime_log_root("beta-local")
        return _tail_multiple_logs_for_startup(
            [
                ("beta-app", beta_log_dir / "app-beta" / "local" / "runtime.log"),
                ("beta-product-ops", beta_log_dir / "product-ops" / "local" / "runtime.log"),
                ("beta-platform-ops", beta_log_dir / "platform-ops" / "local" / "runtime.log"),
                ("beta-ops-portal", beta_log_dir / "ops-portal" / "local" / "runtime.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=35.0,
        )

    def tail_alpha_background_logs() -> dict[str, Any]:
        alpha_log_dir = _local_runtime_log_root("alpha-local")
        return _tail_multiple_logs_for_startup(
            [
                ("alpha-api-edge", alpha_log_dir / "api-edge" / "local" / "runtime.log"),
                ("alpha-product-ops", alpha_log_dir / "product-ops" / "local" / "runtime.log"),
                ("alpha-media-edge", alpha_log_dir / "media-edge" / "local" / "runtime.log"),
                ("alpha-media-origin", alpha_log_dir / "media-origin" / "local" / "runtime.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=20.0,
        )

    def tail_prod_sim_background_logs() -> dict[str, Any]:
        prod_sim_log_dir = _local_runtime_log_root("prod-sim")
        return _tail_multiple_logs_for_startup(
            [
                ("prod-sim-api-edge", prod_sim_log_dir / "api-edge" / "local" / "runtime.log"),
                ("prod-sim-product-ops", prod_sim_log_dir / "product-ops" / "local" / "runtime.log"),
                ("prod-sim-media-edge", prod_sim_log_dir / "media-edge" / "local" / "runtime.log"),
                ("prod-sim-media-origin", prod_sim_log_dir / "media-origin" / "local" / "runtime.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=20.0,
        )

    if requested_target == "beta-local":
        app_launch = None
        if not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
        cmd = ["bash", "quwoquan_ops/cli/beta/start_beta_stack.sh", "up"]
        env = _beta_env_from_port_manifest()
        env["START_APP"] = "0"
        telemetry_env, telemetry_advisory = _optional_product_telemetry_environment(
            "beta", "beta-local"
        )
        env.update(telemetry_env)
        env["QWQ_WORKLOAD"] = args.workload
        if telemetry_advisory:
            steps.append(
                {
                    "kind": "observability-prerequisite",
                    "exitCode": 0,
                    "blocking": False,
                    "stdout": "product telemetry unavailable; App startup continues",
                    "stderr": telemetry_advisory,
                }
            )
        result = run_stage("beta-local", cmd, env=env, live_prefix="[beta] ")
        background_tail = tail_beta_background_logs()
        steps.append(
            {
                "kind": "beta-background-tail",
                "exitCode": 0,
                "stdout": "tailed beta background logs",
                "stderr": "",
                "tail": background_tail,
            }
        )
        if result.returncode == 0:
            beta_content_port = canonical_port(
                load_port_manifest(),
                str(target["portProfile"]),
                "content-service",
            )
            beta_health_url = f"http://127.0.0.1:{beta_content_port}/healthz"
            beta_ready, beta_status, beta_body, beta_content_type = fetch_url(
                beta_health_url,
                retry_attempts=5,
                retry_sleep_seconds=1.0,
            )
            steps.append(
                {
                    "kind": "beta-backend-health-check",
                    "exitCode": 0 if beta_ready else 1,
                    "stdout": "checked beta backend health endpoint",
                    "stderr": "" if beta_ready else beta_body,
                    "url": beta_health_url,
                    "statusCode": beta_status,
                    "contentType": beta_content_type,
                }
            )
            if not beta_ready:
                result = subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=f"beta backend health check failed: {beta_health_url}",
                )
        if result.returncode == 0 and not args.skip_app:
            try:
                app_launch = start_app_process("beta", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
            else:
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=90.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "BUILD FAILED",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="beta app launch failed",
                    process_exit_code=app_exit_code,
                )
                app_failed = failure_detail is not None
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
                if app_failed:
                    result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(failure_detail))
                else:
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
    elif requested_target == "gamma-local":
        env = _gamma_env_from_port_manifest(topology, requested_target)
        # All Gamma child reports share stackctl's explicit run identity.  Static
        # deployment inputs remain in source/deploy work roots, never in output.
        gamma_run_id = report_dir.name
        env["QWQ_RUN_ROOT"] = str(report_dir.resolve())
        env["QWQ_OBSERVABILITY_RUN_ROOT"] = str(
            env_observability_run_dir(env_name, gamma_run_id).resolve()
        )
        package_cmd = [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "package",
            "--env",
            "gamma",
            "--include-services",
        ]
        telemetry_env, telemetry_advisory = _optional_product_telemetry_environment(
            "gamma", "gamma-local"
        )
        env.update(telemetry_env)
        env["QWQ_WORKLOAD"] = args.workload
        if telemetry_advisory:
            steps.append(
                {
                    "kind": "observability-prerequisite",
                    "exitCode": 0,
                    "blocking": False,
                    "stdout": "product telemetry unavailable; App startup continues",
                    "stderr": telemetry_advisory,
                }
            )
        package_result = run(package_cmd, env=env)
        steps.append(
            {
                "name": "gamma-package",
                "argv": package_cmd,
                "exitCode": package_result.returncode,
                "stdout": package_result.stdout,
                "stderr": package_result.stderr,
            }
        )
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]
        if getattr(args, "skip_build", False):
            cmd.append("--skip-build")
        if package_result.returncode != 0:
            result = subprocess.CompletedProcess(
                cmd,
                package_result.returncode,
                stdout=package_result.stdout,
                stderr=package_result.stderr,
            )
        else:
            try:
                env["LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE"] = (
                    _packaged_service_source_image_ref(
                        "gamma",
                        "realtime-gateway",
                    )
                )
                env["LOCAL_GAMMA_RTC_SERVICE_IMAGE"] = (
                    _packaged_service_source_image_ref(
                        "gamma",
                        "rtc-service",
                    )
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result = subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=str(exc),
                )
            else:
                result = run_stage(
                    "gamma-local",
                    cmd,
                    env=env,
                    live_prefix="[gamma-local] ",
                )
        if result.returncode == 0 and not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
            try:
                app_launch = start_app_process("gamma", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
                app_launch = None
            if app_launch is not None:
                gamma_tail = _tail_gamma_container_logs()
                steps.append(
                    {
                        "kind": "gamma-background-tail",
                        "exitCode": 0,
                        "stdout": "tailed gamma container logs",
                        "stderr": "",
                        "tail": gamma_tail,
                    }
                )
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=90.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "BUILD FAILED",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="gamma app launch failed",
                    process_exit_code=app_exit_code,
                )
                app_failed = failure_detail is not None
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
                if app_failed:
                    result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(failure_detail))
                else:
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
    elif requested_target == "alpha-local":
        cmd = ["bash", "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh", "up"]
        result = run_stage("alpha-local", cmd, live_prefix="[alpha] ")
        background_tail = tail_alpha_background_logs()
        steps.append(
            {
                "kind": "alpha-background-tail",
                "exitCode": 0,
                "stdout": "tailed alpha background logs",
                "stderr": "",
                "tail": background_tail,
            }
        )
        if result.returncode == 0 and not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
            try:
                app_launch = start_app_process("alpha", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
                app_launch = None
            if app_launch is not None:
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=60.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "BUILD FAILED",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="alpha app launch failed",
                    process_exit_code=app_exit_code,
                )
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
                if failure_detail is not None:
                    result = subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr=str(failure_detail),
                    )
                else:
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
    elif requested_target == "prod-sim":
        cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "up"]
        result = run_stage("prod-sim", cmd, live_prefix="[prod-sim] ")
        background_tail = tail_prod_sim_background_logs()
        steps.append(
            {
                "kind": "prod-sim-background-tail",
                "exitCode": 0,
                "stdout": "tailed prod-sim background logs",
                "stderr": "",
                "tail": background_tail,
            }
        )
        if result.returncode == 0 and not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
            try:
                app_launch = start_app_process("prod-sim", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
                app_launch = None
            if app_launch is not None:
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=8.0,
                    max_follow_seconds=120.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="prod-sim app launch failed",
                    process_exit_code=app_exit_code,
                )
                if failure_detail is not None:
                    result = subprocess.CompletedProcess(
                        app_launch["command"],
                        1,
                        stdout="",
                        stderr=str(failure_detail),
                    )
                else:
                    announce("prod-sim", "app launch reached steady state")
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
    elif requested_target == "prod-hosted":
        announce("prod-hosted", "running edge health check")
        health_args = argparse.Namespace(
            command="health",
            target="prod-hosted",
            scope="edge",
            output_format="json",
            report_dir=str(report_dir / "health"),
        )
        health = command_health(health_args)
        steps.append(
            {
                "argv": ["python3", "quwoquan_ops/cli/stackctl.py", "health", "--target", "prod-hosted", "--scope", "edge"],
                "exitCode": int(health.get("exitCode", 1)),
                "stdout": health.get("summary", ""),
                "stderr": "\n".join(health.get("details", [])),
            }
        )
        if int(health.get("exitCode", 1)) != 0:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 1,
                "summary": "stackctl up failed for prod-hosted",
                "details": ["prod-hosted health failed; run `stackctl deploy --target prod-hosted ...` first", *health.get("details", [])],
                "reportDir": relpath(report_dir),
                **timing,
            }
        if args.skip_app:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 0,
                "summary": "stackctl up completed for prod",
                "details": ["prod-hosted edge health passed; app launch skipped"],
                "reportDir": relpath(report_dir),
                **timing,
            }
        args.device_id = maybe_resolve_device_id(include_web=True)
        try:
            app_launch = start_app_process("prod", args.device_id)
        except RuntimeError as exc:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 1,
                "summary": "stackctl up failed for prod-hosted",
                "details": [str(exc)],
                "reportDir": relpath(report_dir),
                **timing,
            }
        tail_result = _tail_file_for_startup(
            app_launch["log_path"],
            process=app_launch["process"],
            prefix=f"[{app_launch['stageHeader']} app] ",
            idle_timeout_seconds=6.0,
            max_follow_seconds=60.0,
            ready_patterns=(
                "Syncing files to device",
                "Flutter run key commands",
                "A Dart VM Service",
                "The Flutter DevTools debugger",
            ),
            failure_patterns=(
                "Failed to build",
                "Error launching application on",
                "Lost connection to device.",
                "Target kernel_snapshot_program failed",
                "app launch exited before reaching steady state",
            ),
            ready_idle_timeout_seconds=3.0,
        )
        app_exit_code = app_launch["process"].poll()
        failure_detail = _app_launch_failure_detail(
            tail_result,
            default_message="prod app launch failed",
            process_exit_code=app_exit_code,
        )
        app_failed = failure_detail is not None
        if not app_failed:
            announce("prod-hosted", "app launch reached steady state")
            cmd = app_launch["command"]
            result = subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"pid={app_launch['process'].pid}",
                stderr=f"log={relpath(app_launch['log_path'])}",
            )
        else:
            result = subprocess.CompletedProcess(
                app_launch["command"],
                1,
                stdout="",
                stderr=str(failure_detail),
            )
        steps.append(
            {
                "argv": app_launch["command"],
                "exitCode": app_exit_code or 0,
                "stdout": f"pid={app_launch['process'].pid}",
                "stderr": f"log={relpath(app_launch['log_path'])}",
                "tail": tail_result,
            }
        )
    else:
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": f"stackctl up is not implemented for {requested_target}",
            "details": ["use deploy for hosted gamma/prod targets"],
            **timing,
        }

    timing = _finish_timing(started_monotonic, started_at)
    steps.append(
        {
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": requested_target,
            "workload": args.workload,
            "steps": steps,
            **timing,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl up {'completed' if result.returncode == 0 else 'failed'} for {report_target}",
        details=_command_details(result),
        timing=timing,
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl up {'completed' if result.returncode == 0 else 'failed'} for {report_target}",
        "details": _command_details(result),
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_down(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)

    if args.target == "beta-local":
        cmd = ["bash", "quwoquan_ops/cli/beta/start_beta_stack.sh", "down"]
        result = run(cmd)
    elif args.target == "gamma-local":
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh", "--down"]
        result = run(cmd, env=_gamma_env_from_port_manifest(topology, args.target))
    elif args.target == "alpha-local":
        cmd = ["bash", "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh", "down"]
        result = run(cmd)
        app_result = run(
            [
                "bash",
                "quwoquan_app/scripts/device/stop_app_instance.sh",
                "--env",
                "alpha",
                "--quiet",
            ]
        )
        if app_result.returncode != 0 and result.returncode == 0:
            result = app_result
    elif args.target == "prod-sim":
        app_cmd = [
            "bash",
            "quwoquan_app/scripts/device/stop_app_instance.sh",
            "--env",
            "prod",
        ]
        app_result = run(app_cmd)
        stack_cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "down"]
        stack_result = run(stack_cmd)
        cmd = [*app_cmd, "&&", *stack_cmd]
        result = stack_result if stack_result.returncode != 0 else app_result
    else:
        return {
            "exitCode": 2,
            "summary": f"stackctl down is not implemented for {args.target}",
            "details": ["hosted targets should be rolled back or redeployed via deploy commands"],
        }

    write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        details=_command_details(result),
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        "details": _command_details(result),
        "reportDir": relpath(report_dir),
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope="full",
        output_format=getattr(args, "output_format", "text"),
        report_dir=str(resolve_report_dir(args, str(get_target(load_environment_topology(), args.target)["env"]), args.target)),
    )
    return command_health(health_args)


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    checks = _health_checks_for_target(topology, args.target, args.scope)
    policy = _health_request_policy(args.target, args.scope)
    timeout_seconds = (
        max(1.0, float(args.request_timeout_seconds))
        if getattr(args, "request_timeout_seconds", 0)
        else float(policy["timeoutSeconds"])
    )
    retry_attempts = (
        max(1, int(args.retry_attempts))
        if getattr(args, "retry_attempts", 0)
        else int(policy["retryAttempts"])
    )
    retry_sleep_seconds = (
        max(0.0, float(args.retry_sleep_seconds))
        if getattr(args, "retry_sleep_seconds", -1.0) >= 0
        else float(policy["retrySleepSeconds"])
    )
    statuses: list[dict[str, Any]] = []
    findings: list[str] = []
    stdout_sections: list[tuple[str, str]] = []
    for item in checks:
        if item.get("skip"):
            statuses.append(
                {
                    "name": item["name"],
                    "scope": item["scope"],
                    "url": item["url"],
                    "ok": True,
                    "statusCode": None,
                    "bodyPreview": str(item.get("reason", "skipped")),
                    "skipped": True,
                }
            )
            continue
        ok, status_code, body, content_type = fetch_url(
            item["url"],
            timeout=timeout_seconds,
            retry_attempts=retry_attempts,
            retry_sleep_seconds=retry_sleep_seconds,
            headers=item.get("headers"),
            resolve_host=_local_public_connect_host(topology, args.target, item["url"]),
        )
        expected_status = item.get("expectedStatus")
        if ok and expected_status is not None and status_code != int(expected_status):
            ok = False
            body = f"expected HTTP {expected_status}, got {status_code}"
        expected_content_type_prefix = str(item.get("expectedContentTypePrefix") or "")
        if (
            ok
            and expected_content_type_prefix
            and not content_type.lower().startswith(expected_content_type_prefix.lower())
        ):
            ok = False
            body = (
                f"expected Content-Type {expected_content_type_prefix}*, "
                f"got {content_type or '<empty>'}"
            )
        if not ok:
            findings.append(f"{item['scope']}/{item['name']} failed: {status_code or 'ERR'} {item['url']}")
        statuses.append(
            {
                "name": item["name"],
                "scope": item["scope"],
                "url": item["url"],
                "ok": ok,
                "statusCode": status_code,
                "contentType": content_type,
                "bodyPreview": body,
                "skipped": False,
            }
        )
        stdout_sections.append((item["name"], f"{status_code or 'ERR'} {item['url']}\n{body}"))
    script_statuses, script_stdout_sections, script_findings = _script_probes_for_target(
        topology,
        args.target,
        args.scope,
        report_dir,
    )
    statuses.extend(script_statuses)
    stdout_sections.extend(script_stdout_sections)
    findings.extend(script_findings)
    ok_count = sum(1 for item in statuses if item["ok"])
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "command": "health",
        "target": args.target,
        "scope": args.scope,
        "requestTimeoutSeconds": timeout_seconds,
        "retryAttempts": retry_attempts,
        "retrySleepSeconds": retry_sleep_seconds,
        "checks": statuses,
        "findings": findings,
        "timestamp": utc_now(),
        "scriptProbes": _script_probe_plan_for_target(topology, args.target),
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "health.json", {"target": args.target, "scope": args.scope, "checks": statuses})
    write_json(report_dir / "findings.json", {"target": args.target, "scope": args.scope, "issues": findings})
    _write_summary_bundle(
        report_dir,
        command="health",
        target=args.target,
        status="ok" if not findings else "failed",
        summary=f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        details=findings or [f"scope={args.scope}", f"healthy checks={ok_count}/{len(statuses)}"],
        extra={"scope": args.scope},
        timing=timing,
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not findings else 1,
        "summary": f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        "details": findings
        or [
            "{name} -> {status} {target}".format(
                name=item["name"],
                status=item.get("statusCode") or "OK",
                target=item.get("url") or item.get("reportPath") or item.get("bodyPreview", ""),
            ).strip()
            for item in statuses
        ],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    scopes = (
        ["logs", "network", "data", "metrics", "config", "security"]
        if args.scope == "all"
        else [args.scope]
    )
    inspection: dict[str, Any] = {}
    findings: list[str] = []
    if "network" in scopes:
        inspection["network"] = _network_report(args.target)
    if "config" in scopes:
        inspection["config"] = {
            "target": target,
            "portProfile": target.get("portProfile"),
            "publicBases": target.get("publicBases", {}),
            "origins": target.get("origins", {}),
            "releaseState": (
                _load_release_state(PROD_RELEASE_UNIT)
                if args.target == "prod-hosted"
                else {}
            ),
        }
        if args.target == "prod-hosted":
            runtime = _prod_plane_runtime_report(
                "service",
                report_dir / "prod_rootless_service_runtime.json",
            )
            inspection["config"]["rootlessRuntime"] = runtime
            if runtime.get("error") or int(runtime.get("exitCode", 0) or 0) != 0:
                findings.append("prod service plane rootless runtime inspect failed")
    if "logs" in scopes:
        inspection["logs"] = _local_log_report(args.target)
    if "data" in scopes:
        inspection["data"] = _data_report(args.target)
    if "metrics" in scopes:
        inspection["metrics"] = _metrics_report(topology, args.target)
    if "security" in scopes:
        inspection["security"] = _security_report(topology, args.target)
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "inspect",
            "inspection": inspection,
            "findings": findings,
            **timing,
        },
    )
    for key, value in inspection.items():
        write_json(report_dir / f"{key}.json", value)
    write_json(
        report_dir / "findings.json",
        {"target": args.target, "scope": args.scope, "issues": findings},
    )
    details = findings or [f"{key}: collected" for key in inspection]
    status = "failed" if findings else "ok"
    summary = (
        f"stackctl inspect failed for {args.target}"
        if findings
        else f"stackctl inspect completed for {args.target}"
    )
    _write_summary_bundle(
        report_dir,
        command="inspect",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        extra={"scope": args.scope},
        timing=timing,
    )
    return {
        "exitCode": 1 if findings else 0,
        "summary": summary,
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    findings: list[str] = []
    advisories: list[str] = []
    deployment_prerequisite_failed = False
    if args.target in {"beta-local", "gamma-local"}:
        try:
            load_product_telemetry_sls(env_name, args.target)
        except (RuntimeError, ValueError) as exc:
            deployment_prerequisite_failed = True
            findings.append(f"deployment prerequisite failed: {exc}")
    if args.target in {"prod-sim", "prod-hosted"}:
        legal_result, legal_payload = _legal_static_command("validate", env_name)
        if legal_result.returncode != 0:
            deployment_prerequisite_failed = True
            findings.append("deployment prerequisite failed: prod legal-static source is invalid")
            legal_issues = legal_payload.get("issues")
            if isinstance(legal_issues, list):
                findings.extend(
                    f"legal-static validation: {issue}"
                    for issue in legal_issues
                    if isinstance(issue, str) and issue.strip()
                )
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope="full",
        output_format="json",
        report_dir=str(report_dir / "health"),
    )
    health = command_health(health_args)
    if health["exitCode"] != 0:
        findings.append("health checks are failing")
    if target.get("portProfile"):
        network = _network_report(args.target)
        closed = [item["name"] for item in network["ports"] if not item["open"]]
        if closed:
            findings.append(f"ports not listening: {', '.join(closed)}")
    elif args.target == "prod-hosted":
        public_bases = target.get("publicBases") or {}
        if not public_bases.get("api"):
            findings.append("public api base url is missing")
        if not public_bases.get("productOps"):
            findings.append("product-ops base url is missing")
        if args.target == "prod-hosted":
            state = _load_release_state(PROD_RELEASE_UNIT)
            if not state:
                advisories.append(
                    "prod rollout release-state is missing (local cache empty; hosted deploy workflow can resolve current state via service-plane SSH)"
                )
            elif not state.get("to_image") or not state.get("to_config"):
                findings.append("prod release-state missing image/config target")
            runtime = _prod_plane_runtime_report(
                "service",
                report_dir / "prod_rootless_service_runtime.json",
            )
            if runtime.get("error"):
                findings.append("prod service plane rootless runtime inspect failed")
            else:
                if not runtime.get("composeFileExists"):
                    findings.append("prod service plane rootless compose file is missing")
                if not runtime.get("envFileExists"):
                    findings.append("prod service plane rootless env file is missing")
                if int(runtime.get("containerCount", 0) or 0) == 0:
                    findings.append("prod service plane rootless runtime has no running containers")
    packages = [app_release_dir(env_name) / "report.json"]
    require_package_artifacts = bool(target.get("portProfile"))
    if require_package_artifacts and not all(path.exists() for path in packages):
        findings.append("packaged app artifact is missing")
    repair_plan = []
    if findings:
        if deployment_prerequisite_failed:
            repair_plan.append(
                "provision the external product telemetry SLS deployment secret and rerun `stackctl doctor`"
            )
            if args.target in {"prod-sim", "prod-hosted"}:
                repair_plan.append(
                    "replace prod legal-static placeholder identity fields with approved legal facts and rerun `stackctl doctor`"
                )
        if any("health checks" in item for item in findings):
            repair_plan.append("run `stackctl health --target <target> --scope full` to confirm failing probes")
        if not deployment_prerequisite_failed and any(
            "ports not listening" in item for item in findings
        ):
            repair_plan.append("run `stackctl repair --target <target> --fix restart-stack` for local targets")
        if any("artifact" in item for item in findings):
            repair_plan.append("run `stackctl repair --target <target> --fix rebuild-packages`")
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "doctor",
            "target": args.target,
            "findings": findings,
            "advisories": advisories,
            "repairPlan": repair_plan,
            "timestamp": utc_now(),
            **timing,
        },
    )
    write_json(
        report_dir / "findings.json",
        {"target": args.target, "issues": findings, "advisories": advisories},
    )
    write_json(report_dir / "repair_plan.json", {"target": args.target, "actions": repair_plan})
    _write_summary_bundle(
        report_dir,
        command="doctor",
        target=args.target,
        status="ok" if not findings else "failed",
        summary="stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        details=findings + advisories or ["no issues found"],
        timing=timing,
    )
    return {
        "exitCode": 0 if not findings else 1,
        "summary": "stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        "details": findings + advisories or ["no issues found"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_content_readiness(args: argparse.Namespace) -> dict[str, Any]:
    """Assess one release phase against its minimal, typed capability set.

    This is deliberately not a global doctor and is never an execution-create
    precondition.  It is called when an environment is actually about to import,
    serve consumers, or claim commercial observability.
    """
    phase = ReadinessPhase(args.phase)
    policy = load_content_release_readiness_policy()
    requirement = policy.requirement_for(phase=phase, environment=args.env)
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else repo_run_dir("content-readiness", target=f"{args.env}-{phase.value}")
    )
    started_monotonic, started_at = _start_timing()
    health = command_health(
        argparse.Namespace(
            command="health",
            target=requirement.target,
            scope=requirement.health_scope,
            output_format="json",
            report_dir=str(report_dir / "health"),
        )
    )
    details = list(health.get("details", [])) if int(health["exitCode"]) != 0 else []
    executed_checks = [
        item
        for item in _read_json_object(str(report_dir / "health" / "report.json")).get("checks", [])
        if isinstance(item, dict) and str(item.get("name") or "") and not item.get("skipped")
    ]
    probes = tuple(str(item["name"]) for item in executed_checks)
    executed_scopes = {str(item.get("scope") or "") for item in executed_checks}
    for capability in requirement.capabilities:
        binding = policy.probe_binding_for(capability)
        if binding.source is ProbeSource.HEALTH_SCOPE and binding.health_scope not in executed_scopes:
            details.append(
                f"capability {capability.value} declares probe scope "
                f"{binding.health_scope} but no probe executed for {requirement.target}"
            )
    if phase is ReadinessPhase.COMMERCIAL:
        doctor = command_doctor(
            argparse.Namespace(
                command="doctor",
                target=requirement.target,
                output_format="json",
                report_dir=str(report_dir / "commercial-prerequisites"),
            )
        )
        if int(doctor["exitCode"]) != 0:
            details.extend(str(item) for item in doctor.get("details", []))
    outcome = ProbeOutcome.PASS if not details else ProbeOutcome.GATE_BLOCK
    timing = _finish_timing(started_monotonic, started_at)
    receipt = ShipReadinessReceipt(
        policy_id=policy.policy_id,
        phase=phase,
        environment=requirement.environment,
        target=requirement.target,
        workload=requirement.workload,
        outcome=outcome,
        capabilities=requirement.capabilities,
        probes=probes,
        report_dir=relpath(report_dir),
    )
    payload = {
        "schema": "quwoquan_ops.ship_readiness_receipt",
        "policyId": receipt.policy_id,
        "phase": receipt.phase.value,
        "environment": receipt.environment,
        "target": receipt.target,
        "workload": receipt.workload,
        "outcome": receipt.outcome.value,
        "capabilities": [item.value for item in receipt.capabilities],
        "probes": list(receipt.probes),
        "reportDir": receipt.report_dir,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": details})
    _write_summary_bundle(
        report_dir,
        command="content-readiness",
        target=requirement.target,
        status="ok" if outcome is ProbeOutcome.PASS else "blocked",
        summary=(
            f"content readiness {phase.value}/{args.env} passed"
            if outcome is ProbeOutcome.PASS
            else f"content readiness {phase.value}/{args.env} is GATE_BLOCK"
        ),
        details=details or ["all required capabilities are available"],
        extra={"policyId": policy.policy_id, "phase": phase.value, "outcome": outcome.value},
        timing=timing,
    )
    return {
        **payload,
        "exitCode": 0 if outcome is ProbeOutcome.PASS else 2,
        "summary": (
            f"content readiness {phase.value}/{args.env} passed"
            if outcome is ProbeOutcome.PASS
            else f"content readiness {phase.value}/{args.env} is GATE_BLOCK"
        ),
        "details": details or ["all required capabilities are available"],
    }


def command_repair(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    steps: list[dict[str, Any]] = []
    if args.fix == "rebuild-packages":
        package_args = argparse.Namespace(
            command="package",
            env=env_name,
            service="",
            include_services=True,
            target=args.target,
            output_format="json",
            report_dir=str(report_dir / "rebuild-packages"),
        )
        payload = command_package(package_args)
        write_json(report_dir / "report.json", {"command": "repair", "nested": payload})
        write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["rebuild environment packages"]},
        )
        return payload
    if args.fix == "materialize-media":
        if args.target != "gamma-local":
            summary = (
                "materialize-media is only available for gamma-local curated "
                "media; prod uses a published release canary"
            )
            write_json(
                report_dir / "repair_plan.json",
                {"target": args.target, "fix": args.fix, "actions": [], "error": summary},
            )
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": [summary],
                "reportDir": relpath(report_dir),
            }
        try:
            materialized = materialize_local_gamma_media(
                target_cache_dir(args.target) / "media",
            )
        except (LocalGammaMediaError, OSError) as exc:
            summary = f"gamma local media materialization failed: {exc}"
            write_json(
                report_dir / "repair_plan.json",
                {"target": args.target, "fix": args.fix, "actions": [], "error": summary},
            )
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 1,
                "summary": summary,
                "details": [summary],
                "reportDir": relpath(report_dir),
            }
        write_json(report_dir / "media_materialization.json", materialized)
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": ["materialize canonical local-gamma media cache"],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary="gamma local canonical media materialized",
            details=[
                f"copied files: {materialized['copiedFiles']}",
                f"canonical video: {materialized['publicSliceKey']}",
            ],
        )
        return {
            "exitCode": 0,
            "summary": "gamma local canonical media materialized",
            "details": [
                f"copied files: {materialized['copiedFiles']}",
                f"canonical video: {materialized['publicSliceKey']}",
            ],
            "reportDir": relpath(report_dir),
        }
    if args.fix == "restart-stack":
        # Restart is destructive for local state. Validate every external
        # deployment prerequisite before stopping a currently running stack;
        # otherwise a failed `up` would turn a partial outage into a full one.
        if args.target in {"beta-local", "gamma-local"}:
            try:
                load_product_telemetry_sls(env_name, args.target)
            except (RuntimeError, ValueError) as exc:
                summary = (
                    "stackctl repair restart-stack blocked before stop: "
                    f"deployment prerequisite failed: {exc}"
                )
                write_json(
                    report_dir / "report.json",
                    {
                        "command": "repair",
                        "target": args.target,
                        "fix": args.fix,
                        "steps": [],
                        "blockedBeforeStop": True,
                        "reason": str(exc),
                    },
                )
                write_json(
                    report_dir / "repair_plan.json",
                    {
                        "target": args.target,
                        "fix": args.fix,
                        "actions": [
                            "provision the external product telemetry SLS deployment secret",
                            "rerun stackctl doctor before restart-stack",
                        ],
                    },
                )
                _write_summary_bundle(
                    report_dir,
                    command="repair",
                    target=args.target,
                    status="failed",
                    summary=summary,
                    details=[str(exc)],
                )
                return {
                    "exitCode": 2,
                    "summary": summary,
                    "details": [str(exc)],
                    "reportDir": relpath(report_dir),
                }
        down_args = argparse.Namespace(command="down", target=args.target, output_format="json", report_dir=str(report_dir / "down"))
        up_args = argparse.Namespace(
            command="up",
            env="",
            target=args.target,
            device_id="",
            skip_app=True,
            skip_build=False,
            workload="full",
            rollout_mode="",
            output_format="json",
            report_dir=str(report_dir / "up"),
        )
        down_payload = command_down(down_args)
        up_payload = command_up(up_args)
        steps = [down_payload, up_payload]
        write_json(report_dir / "report.json", {"command": "repair", "steps": steps})
        write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["stop stack", "start stack"]},
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok" if up_payload["exitCode"] == 0 else "failed",
            summary=f"stackctl repair restart-stack completed for {args.target}",
            details=[down_payload["summary"], up_payload["summary"]],
        )
        return {
            "exitCode": 0 if up_payload["exitCode"] == 0 else up_payload["exitCode"],
            "summary": f"stackctl repair restart-stack completed for {args.target}",
            "details": [down_payload["summary"], up_payload["summary"]],
            "reportDir": relpath(report_dir),
        }
    if args.fix == "reclaim-ports":
        ports = _network_report(args.target)["ports"]
        occupied = [item for item in ports if item["open"]]
        write_json(report_dir / "report.json", {"command": "repair", "target": args.target, "occupied": occupied})
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": [f"inspect listener on {item['name']}:{item['port']}" for item in occupied],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary=f"stackctl repair reclaim-ports inspected {args.target}",
            details=[f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
        )
        return {
            "exitCode": 0,
            "summary": f"stackctl repair reclaim-ports inspected {args.target}",
            "details": [f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
            "reportDir": relpath(report_dir),
        }
    return {
        "exitCode": 2,
        "summary": f"unsupported repair fix: {args.fix}",
        "details": [],
    }


def _deployable_release_manifest(
    path_value: str,
    *,
    image_version: str,
    config_version: str,
) -> tuple[Path, str, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release manifest unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("release manifest must be an object")
    if (
        manifest.get("schema") != "mainline-release-artifact"
        or manifest.get("status") != "deployable"
    ):
        raise RuntimeError("release manifest is not deployable")
    declared_digest = str(manifest.get("manifestDigest") or "")
    unsigned = dict(manifest)
    unsigned.pop("manifestDigest", None)
    actual_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if declared_digest != actual_digest:
        raise RuntimeError("release manifest digest mismatch")
    versions = manifest.get("versions")
    if not isinstance(versions, dict):
        raise RuntimeError("release manifest versions are missing")
    if versions.get("imageVersion") != image_version:
        raise RuntimeError("release manifest image version mismatch")
    if versions.get("configVersion") != config_version:
        raise RuntimeError("release manifest config version mismatch")
    source = manifest.get("source")
    source_sha = str(source.get("gitSha") or "") if isinstance(source, dict) else ""
    head = run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0 or source_sha != head.stdout.strip():
        raise RuntimeError(
            "release manifest source SHA does not match checked-out deployment code"
        )
    governance_path = path.parent / "governance-receipt.json"
    try:
        governance = json.loads(governance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release governance receipt is missing or invalid: {error}") from error
    if (
        not isinstance(governance, dict)
        or governance.get("schema") != "prod-release-governance-receipt"
        or governance.get("repository") != (manifest.get("source") or {}).get("repository")
        or governance.get("gitSha") != source_sha
        or governance.get("manifestDigest") != declared_digest
        or not governance.get("approvers")
        or len(set(governance.get("distinctPrincipals") or [])) < 2
    ):
        raise RuntimeError("release governance receipt does not bind this reviewed artifact")
    required_images = manifest.get("requiredImages")
    images = manifest.get("images")
    if (
        not isinstance(required_images, list)
        or not required_images
        or not isinstance(images, dict)
        or set(required_images) != set(images)
    ):
        raise RuntimeError("release manifest image set is incomplete")
    for service in required_images:
        image = images.get(service)
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        digest = str(image.get("digest") or "")
        repository = str(image.get("repository") or "")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise RuntimeError(f"release manifest image digest is invalid: {service}")
        if image.get("ref") != f"{repository}@{digest}":
            raise RuntimeError(f"release manifest image ref is not digest-pinned: {service}")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or not all(
            attestations.get(kind) == f"oci://{repository}@{digest}#{kind}"
            for kind in ("spdxSbom", "slsaProvenance")
        ):
            raise RuntimeError(f"release manifest attestations are incomplete: {service}")
    release_files = manifest.get("releaseFiles")
    release_digests = manifest.get("releaseFileDigests")
    if not isinstance(release_files, dict) or not isinstance(release_digests, dict):
        raise RuntimeError("release manifest config digests are missing")
    for service, relative in release_files.items():
        config_path = path.parent / str(relative)
        if not config_path.is_file():
            raise RuntimeError(f"release manifest config file is missing: {service}")
        digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
        if release_digests.get(service) != f"sha256:{digest}":
            raise RuntimeError(f"release manifest config digest mismatch: {service}")
    return path, declared_digest, manifest


def _verify_release_registry_attestations(manifest: dict[str, Any]) -> None:
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise RuntimeError("release manifest images are missing")
    for service, image in images.items():
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        ref = str(image.get("ref") or "")
        result = run(["docker", "buildx", "imagetools", "inspect", ref])
        if result.returncode != 0:
            raise RuntimeError(
                f"OCI digest/attestation lookup failed for {service}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        evidence = f"{result.stdout}\n{result.stderr}".lower()
        if "provenance" not in evidence or "sbom" not in evidence:
            raise RuntimeError(
                f"OCI registry does not expose both provenance and SBOM for {service}"
            )


def _prod_gray_canary_contract() -> dict[str, Any]:
    policy_path = ROOT / "quwoquan_ops" / "environments" / "gray_routing_policy.yaml"
    payload = load_json_yaml(policy_path)
    policy = payload.get("policy") if isinstance(payload, dict) else None
    if not isinstance(policy, dict) or not policy.get("enabled"):
        raise RuntimeError("production gray routing policy must be enabled")
    canary = policy.get("syntheticCanary")
    if not isinstance(canary, dict):
        raise RuntimeError("production gray routing policy requires syntheticCanary")
    headers = canary.get("headers")
    requests = int(canary.get("requests") or 0)
    path = str(canary.get("path") or "").strip()
    if (
        not isinstance(headers, dict)
        or requests < 100
        or not path.startswith("/")
    ):
        raise RuntimeError("production gray synthetic canary contract is incomplete")
    dimensions = policy.get("dimensions")
    if not isinstance(dimensions, dict):
        raise RuntimeError("production gray routing dimensions are missing")
    header_dimensions = {
        "X-Client-App-Version": "appVersions",
        "X-Client-User-Id": "userIds",
        "X-Client-Region-Code": "provinces",
        "X-Client-Carrier": "carriers",
    }
    if not any(
        str(headers.get(header) or "") in {
            str(value) for value in dimensions.get(dimension) or []
        }
        for header, dimension in header_dimensions.items()
    ):
        raise RuntimeError("synthetic canary headers do not match any enabled gray dimension")
    return canary


def _emit_prod_gray_canary_traffic(canary: dict[str, Any]) -> dict[str, Any]:
    topology = load_json_yaml(
        ROOT / "quwoquan_ops" / "environments" / "environment_topology_manifest.yaml"
    )
    api_base = str(
        ((((topology or {}).get("targets") or {}).get("prod-hosted") or {}).get("publicBases") or {}).get("api")
        or ""
    ).rstrip("/")
    if not api_base.startswith("https://"):
        raise RuntimeError("prod synthetic canary requires HTTPS api public base")
    path = str(canary["path"])
    requests = int(canary["requests"])
    interval_ms = int(canary.get("intervalMs") or 0)
    headers = {str(key): str(value) for key, value in canary["headers"].items()}
    started = time.monotonic()
    for index in range(requests):
        request = urllib.request.Request(
            f"{api_base}{path}",
            headers={**headers, "User-Agent": "quwoquan-release-canary/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(
                        f"synthetic canary request {index + 1} returned {response.status}"
                    )
        except OSError as error:
            raise RuntimeError(
                f"synthetic canary request {index + 1}/{requests} failed: {error}"
            ) from error
        if interval_ms > 0 and index + 1 < requests:
            time.sleep(interval_ms / 1000)
    return {
        "source": "prod-public-api",
        "path": path,
        "requests": requests,
        "headers": sorted(headers),
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def _prometheus_query_value(base_url: str, expression: str) -> float:
    request_url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Prometheus SLO readback request failed: {error}") from error
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus SLO readback returned non-success: {payload.get('error', 'unknown error')}")
    results = ((payload.get("data") or {}).get("result") or [])
    if len(results) != 1:
        raise RuntimeError(f"Prometheus SLO readback expected one sample, got {len(results)}")
    value = (results[0].get("value") or [])
    if len(value) != 2:
        raise RuntimeError("Prometheus SLO readback sample is malformed")
    try:
        return float(value[1])
    except (TypeError, ValueError) as error:
        raise RuntimeError("Prometheus SLO readback value is not numeric") from error


def _read_prometheus_slo(base_url: str, service: str) -> dict[str, Any]:
    policy_path = ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = load_json_yaml(policy_path)
    if not isinstance(policy, dict) or not isinstance(policy.get("readback"), dict):
        raise RuntimeError(f"invalid SLO readback policy: {policy_path}")
    readback_policy = policy["readback"]
    window = str(readback_policy.get("window") or "").strip()
    minimum_samples = int(readback_policy.get("minimum_samples") or 0)
    if not window or minimum_samples <= 0:
        raise RuntimeError(f"SLO readback policy requires window/minimum_samples: {policy_path}")
    labels: list[str] = []
    if service.strip():
        labels.append(f'service="{service.strip()}"')
    service_label = "{" + ",".join(labels) + "}"
    error_labels = [*labels, 'status=~"5.."']
    error_selector = "{" + ",".join(error_labels) + "}"
    queries = {
        "errorRate": (
            f"sum(rate(http_server_requests_total{error_selector}[{window}]))"
            f" / (sum(rate(http_server_requests_total{service_label}[{window}])) + 0.001)"
        ),
        "p95Ms": (
            f"histogram_quantile(0.95, sum(rate(http_server_duration_seconds_bucket"
            f"{service_label}[{window}])) by (le)) * 1000"
        ),
        "redisErrorRate": (
            f'sum(rate(redis_operations_total{{status="error"}}[{window}]))'
            f" / (sum(rate(redis_operations_total[{window}])) + 0.001)"
        ),
        "sampleCount": f"sum(increase(http_server_requests_total{service_label}[{window}]))",
    }
    values = {name: _prometheus_query_value(base_url, expression) for name, expression in queries.items()}
    if values["sampleCount"] < minimum_samples:
        raise RuntimeError(
            f"Prometheus SLO readback has insufficient samples: "
            f"{values['sampleCount']} < {minimum_samples}"
        )
    result: dict[str, Any] = {
        "source": "prometheus",
        "baseUrl": base_url.rstrip("/"),
        "queriedAt": utc_now(),
        "window": window,
        "minimumSamples": minimum_samples,
        "queries": queries,
        "values": values,
    }
    recommendation = _read_recommendation_slo(
        base_url, service, window, readback_policy.get("recommendation")
    )
    if recommendation is not None:
        result["recommendation"] = recommendation
    return result


def _slo_settle_seconds(stage: str) -> int:
    policy_path = ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = load_json_yaml(policy_path)
    readback = policy.get("readback") if isinstance(policy, dict) else None
    settle = readback.get("settle_seconds") if isinstance(readback, dict) else None
    if not isinstance(settle, dict):
        raise RuntimeError(f"SLO readback policy requires settle_seconds: {policy_path}")
    seconds = int(settle.get(stage) or 0)
    if seconds < 0:
        raise RuntimeError(f"SLO settle seconds cannot be negative for {stage}")
    return seconds


def _read_recommendation_slo(
    base_url: str,
    service: str,
    window: str,
    rec_policy: Any,
) -> dict[str, Any] | None:
    """N2-5：prod gray readback 纳入推荐业务指标（空 feed 率 / 负反馈率 / CTR）。

    仅对策略声明的推荐服务（content-service）生效；空 feed 率与负反馈率超
    critical 抛错阻断放量，CTR 在 impression 样本不足时诚实跳过（只观察不拦截）。
    """
    if not isinstance(rec_policy, dict):
        return None
    if service.strip() != str(rec_policy.get("service") or "").strip():
        return None
    # 指标名与 runtime/recommendation/observability.go 的真实 emitter 对齐
    # （recommendation_alert_metric_existence 契约同源）；杜绝死查询。
    queries = {
        "emptyFeedRate": (
            f"sum(increase(rec_pipeline_empty_results_total[{window}]))"
            f" / (sum(increase(rec_pipeline_requests_total[{window}])) + 0.001)"
        ),
        "negativeFeedbackRate": (
            f"sum(increase(recommendation_feed_negative_feedback_total[{window}]))"
            f" / (sum(increase(recommendation_feed_impressed_total[{window}])) + 0.001)"
        ),
        "impressionCount": f"sum(increase(recommendation_feed_impressed_total[{window}]))",
        "ctr": (
            f'sum(increase(recommendation_feed_engagement_total{{action="click"}}[{window}]))'
            f" / (sum(increase(recommendation_feed_impressed_total[{window}])) + 0.001)"
        ),
    }
    values = {
        name: _prometheus_query_value(base_url, expression)
        for name, expression in queries.items()
    }
    breaches: list[str] = []
    warnings: list[str] = []
    for metric, value_key in (
        ("empty_feed_rate", "emptyFeedRate"),
        ("negative_feedback_rate", "negativeFeedbackRate"),
    ):
        thresholds = rec_policy.get(metric)
        if not isinstance(thresholds, dict):
            continue
        critical = float(thresholds.get("critical") or 0)
        warn = float(thresholds.get("warn") or 0)
        value = values[value_key]
        if critical > 0 and value >= critical:
            breaches.append(f"{metric}={value:.4f} >= critical {critical}")
        elif warn > 0 and value >= warn:
            warnings.append(f"{metric}={value:.4f} >= warn {warn}")
    min_impressions = int(rec_policy.get("min_impressions") or 0)
    ctr_evaluated = values["impressionCount"] >= min_impressions > 0
    if ctr_evaluated:
        ctr_floor = float(rec_policy.get("ctr_floor_warn") or 0)
        if ctr_floor > 0 and values["ctr"] < ctr_floor:
            warnings.append(f"ctr={values['ctr']:.4f} < floor {ctr_floor}")
    if breaches:
        raise RuntimeError(
            "recommendation SLO readback breached critical thresholds: "
            + "; ".join(breaches)
        )
    return {
        "queries": queries,
        "values": values,
        "ctrEvaluated": ctr_evaluated,
        "warnings": warnings,
    }


def _decision_from_slo_output(output: str, rollout_stage: str) -> tuple[str, str]:
    if "decision=pause" in output:
        if rollout_stage == "full":
            return "rollback", "full rollout cannot remain paused on warning SLO"
        return "pause", "slo gate decision=pause"
    if "decision=rollback" in output:
        return "rollback", "slo gate decision=rollback"
    return "continue", ""


def _command_deploy_with_lock(args: argparse.Namespace) -> dict[str, Any]:
    report_dir = resolve_report_dir(args, "prod" if args.target == "prod-hosted" else "gamma", args.target)
    started_monotonic, started_at = _start_timing()
    post_deploy_checks: list[dict[str, Any]] = []
    rollback_post_checks: list[dict[str, Any]] = []
    deploy_result: Any | None = None
    rollback_result: Any | None = None
    rollback_reason = ""
    rollback_state: dict[str, str] | None = None
    rollout_decision = "continue"
    rollout_stage = ""
    dry_run_requested = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    slo_readback: dict[str, Any] | None = None
    prometheus_url = ""
    release_manifest_path: Path | None = None
    release_manifest_digest = ""
    release_manifest_payload: dict[str, Any] = {}
    expected_generation = 0
    transition_action = "advance"
    release_receipt_id = ""
    committed_release_state: dict[str, str] | None = None
    release_receipt_path: Path | None = None
    release_state_snapshot: dict[str, str] = {}
    gray_canary_contract: dict[str, Any] | None = None
    gray_canary_traffic: dict[str, Any] | None = None
    if args.target == "prod-hosted":
        try:
            rollout_stage = _resolve_prod_rollout_stage(args.step, args.stage)
        except ValueError as error:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": f"stackctl deploy rollout stage invalid: {error}",
                "details": [],
                **timing,
            }
        prometheus_url = str(
            getattr(args, "prometheus_url", "")
            or os.environ.get("PROMETHEUS_URL", "")
        ).strip()
        if not dry_run_requested and not prometheus_url:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: non-dry-run prod rollout requires PROMETHEUS_URL readback",
                "details": [],
                **timing,
            }
        shared_state_dir = os.environ.get("QWQ_PROD_RELEASE_STATE_DIR", "").strip()
        if not dry_run_requested and (
            not shared_state_dir or not Path(shared_state_dir).expanduser().is_absolute()
        ):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: shared production release ledger is required",
                "details": ["QWQ_PROD_RELEASE_STATE_DIR must be an absolute durable path"],
                **timing,
            }
        if not dry_run_requested:
            try:
                gray_canary_contract = _prod_gray_canary_contract()
            except RuntimeError as error:
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: gray canary contract is invalid",
                    "details": [str(error)],
                    **timing,
                }
        required = [
            args.service,
            args.from_image,
            args.to_image,
            args.from_config,
            args.to_config,
            args.step,
        ]
        if not all(required):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy prod-hosted requires service/image/config/step arguments",
                "details": [],
                **timing,
            }
        manifest_value = str(
            getattr(args, "release_manifest", "")
            or os.environ.get("RELEASE_MANIFEST", "")
        ).strip()
        if not manifest_value:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: immutable release manifest is required",
                "details": [],
                **timing,
            }
        try:
            (
                release_manifest_path,
                release_manifest_digest,
                release_manifest_payload,
            ) = _deployable_release_manifest(
                manifest_value,
                image_version=args.to_image,
                config_version=args.to_config,
            )
            release_state_snapshot = _load_release_state(args.service)
            transition_action, expected_generation = _validate_release_transition(
                release_state_snapshot,
                from_image=args.from_image,
                to_image=args.to_image,
                from_config=args.from_config,
                to_config=args.to_config,
                stage=rollout_stage,
                manifest_digest=release_manifest_digest,
            )
            if not dry_run_requested:
                _verify_release_registry_attestations(release_manifest_payload)
                _archive_release_artifact(
                    release_manifest_path,
                    release_manifest_digest,
                )
        except RuntimeError as error:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: release manifest or ledger validation failed",
                "details": [str(error)],
                **timing,
            }
        release_receipt_id = hashlib.sha256(
            (
                f"{args.service}\0{release_manifest_digest}\0{rollout_stage}\0"
                f"{expected_generation + (0 if transition_action == 'replay' else 1)}"
            ).encode("utf-8")
        ).hexdigest()
        if transition_action == "replay" and not dry_run_requested:
            release_receipt_id = release_state_snapshot.get("receipt_id", "")
            receipt_path = (
                _release_state_dir() / "receipts" / f"{release_receipt_id}.json"
            )
            if not release_receipt_id or not receipt_path.is_file():
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: committed ledger receipt is missing",
                    "details": [str(receipt_path)],
                    **timing,
                }
            try:
                _sync_release_ledger_projection(
                    args.service,
                    release_receipt_id,
                )
            except RuntimeError as error:
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy replay could not sync release projection",
                    "details": [str(error)],
                    **timing,
                }
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 0,
                "summary": "stackctl deploy replay matched committed release ledger",
                "details": [f"receipt: {release_receipt_id}"],
                "releaseReceiptId": release_receipt_id,
                **timing,
            }
        package_cmd = [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "package",
            "--env",
            "prod",
            "--include-services",
        ]
        package_result = run(package_cmd)
        if package_result.returncode != 0:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": package_result.returncode,
                "summary": "stackctl deploy blocked: prod environment package failed",
                "details": [package_result.stderr.strip() or package_result.stdout.strip()],
                **timing,
            }
        cmd: list[str] = []
        deploy_result = run(
            ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
            env={
                "CLOUD_PROVIDER": args.cloud_provider,
                "SERVICE": args.service,
                "IMAGE_VERSION": args.to_image,
                "CONFIG_VERSION": args.to_config,
                "PREVIOUS_IMAGE_VERSION": args.from_image,
                "ROLLOUT_STAGE": rollout_stage,
                "DRY_RUN": args.dry_run,
                "RELEASE_MANIFEST": str(release_manifest_path),
            },
        )
        if deploy_result.returncode != 0:
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
                if gray_canary_contract is None:
                    raise RuntimeError("gray canary contract was not loaded")
                gray_canary_traffic = _emit_prod_gray_canary_traffic(
                    gray_canary_contract
                )
                settle_seconds = _slo_settle_seconds(rollout_stage)
                if settle_seconds:
                    time.sleep(settle_seconds)
                slo_service = (
                    "content-service"
                    if args.service == PROD_RELEASE_UNIT
                    else args.service
                )
                slo_readback = _read_prometheus_slo(prometheus_url, slo_service)
                slo_readback["canaryTraffic"] = gray_canary_traffic
            except RuntimeError as error:
                slo_readback = {
                    "canaryTraffic": gray_canary_traffic or {},
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
                    "--from-image",
                    args.from_image,
                    "--to-image",
                    args.to_image,
                    "--from-config",
                    args.from_config,
                    "--to-config",
                    args.to_config,
                    "--step",
                    args.step,
                    "--error-rate",
                    args.error_rate,
                    "--p95-ms",
                    args.p95_ms,
                    "--redis-error-rate",
                    args.redis_error_rate,
                ]
                result = run(cmd)
    run_post_deploy_checks = result.returncode == 0 and not (
        args.target == "prod-hosted" and dry_run_requested
    )
    if run_post_deploy_checks:
        def _deploy_health_args(target_name: str, scope_name: str, out_dir: Path) -> argparse.Namespace:
            return argparse.Namespace(
                command="health",
                target=target_name,
                scope=scope_name,
                output_format="json",
                report_dir=str(out_dir),
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
            )

        for nested_command, nested_scope in (
            ("health", "full"),
            ("inspect", "all"),
            ("doctor", ""),
        ):
            nested_dir = report_dir / nested_command
            if nested_command == "health":
                nested_args = _deploy_health_args(args.target, nested_scope, nested_dir)
                post_deploy_checks.append(command_health(nested_args))
            elif nested_command == "inspect":
                nested_args = argparse.Namespace(
                    command="inspect",
                    target=args.target,
                    scope=nested_scope,
                    output_format="json",
                    report_dir=str(nested_dir),
                )
                post_deploy_checks.append(command_inspect(nested_args))
            else:
                nested_args = argparse.Namespace(
                    command="doctor",
                    target=args.target,
                    output_format="json",
                    report_dir=str(nested_dir),
                )
                post_deploy_checks.append(command_doctor(nested_args))
        if args.target == "prod-hosted" and rollout_stage == "gray-initial":
            nested_dir = report_dir / "environment-page-smoke"
            nested_args = argparse.Namespace(
                command="verify",
                env="",
                target=args.target,
                kind="topology",
                profile="release",
                output_format="json",
                report_dir=str(nested_dir),
            )
            post_deploy_checks.append(command_verify(nested_args))
    post_deploy_failures = [
        item["summary"]
        for item in post_deploy_checks
        if int(item.get("exitCode", 0) or 0) != 0
    ]
    final_exit_code = result.returncode
    findings = list(post_deploy_failures)
    if final_exit_code == 0 and post_deploy_failures:
        final_exit_code = 1
    if args.target == "prod-hosted":
        stdout_combined = "\n".join(filter(None, [result.stdout, result.stderr]))
        slo_decision, slo_reason = _decision_from_slo_output(
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
            rollback_env = {
                "CLOUD_PROVIDER": args.cloud_provider,
                "SERVICE": args.service,
                "IMAGE_VERSION": args.from_image,
                "CONFIG_VERSION": args.from_config,
                "PREVIOUS_IMAGE_VERSION": args.to_image,
                "ROLLOUT_STAGE": "full",
                "DRY_RUN": "false",
                "PROD_IMAGE_DELIVERY_MODE": "skip",
            }
            rollback_result = run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                env=rollback_env,
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
                        )
                        rollback_post_checks.append(command_health(nested_args))
                rollback_failures = [
                    item["summary"]
                    for item in rollback_post_checks
                    if int(item.get("exitCode", 0) or 0) != 0
                ]
                findings.extend(f"rollback {item}" for item in rollback_failures)
                if rollback_failures and final_exit_code == 0:
                    final_exit_code = 1
                rollback_decision = (
                    "rollback_failed" if rollback_failures else "rolled_back"
                )
                rollback_state, release_receipt_path = _commit_release_transition(
                    service=args.service,
                    from_image=args.to_image,
                    to_image=args.from_image,
                    from_config=args.to_config,
                    to_config=args.from_config,
                    step="100",
                    stage="full",
                    decision=rollback_decision,
                    manifest_digest=release_manifest_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                )
                committed_release_state = rollback_state
            else:
                findings.append("live rollback apply failed")
                final_exit_code = rollback_result.returncode
                committed_release_state, release_receipt_path = _commit_release_transition(
                    service=args.service,
                    from_image=args.from_image,
                    to_image=args.to_image,
                    from_config=args.from_config,
                    to_config=args.to_config,
                    step=args.step,
                    stage=rollout_stage,
                    decision="rollback_failed",
                    manifest_digest=release_manifest_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                )
        elif rollout_decision == "pause" and final_exit_code == 10:
            final_exit_code = 10
            if not dry_run_requested:
                committed_release_state, release_receipt_path = _commit_release_transition(
                    service=args.service,
                    from_image=args.from_image,
                    to_image=args.to_image,
                    from_config=args.from_config,
                    to_config=args.to_config,
                    step=args.step,
                    stage=rollout_stage,
                    decision="pause",
                    manifest_digest=release_manifest_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                )
        elif final_exit_code == 0 and not dry_run_requested:
            committed_release_state, release_receipt_path = _commit_release_transition(
                service=args.service,
                from_image=args.from_image,
                to_image=args.to_image,
                from_config=args.from_config,
                to_config=args.to_config,
                step=args.step,
                stage=rollout_stage,
                decision="continue",
                manifest_digest=release_manifest_digest,
                expected_generation=expected_generation,
                receipt_id=release_receipt_id,
                slo_readback=slo_readback,
            )
        if committed_release_state is not None:
            release_receipt_id = committed_release_state["receipt_id"]
            _sync_release_ledger_projection(
                args.service,
                release_receipt_id,
            )
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "deploy",
            "target": args.target,
            "argv": cmd,
            "exitCode": final_exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "rolloutStage": rollout_stage,
            "rolloutDecision": rollout_decision,
            "releaseManifestDigest": release_manifest_digest,
            "releaseReceiptId": release_receipt_id,
            "releaseReceiptPath": (
                str(release_receipt_path) if release_receipt_path is not None else ""
            ),
            "releaseState": committed_release_state or {},
            "wiredWorkloads": _prod_rollout_workloads() if args.target == "prod-hosted" else [],
            "postDeployChecks": post_deploy_checks,
            "postDeployFailures": post_deploy_failures,
            "rollbackPostChecks": rollback_post_checks,
            "sloReadback": slo_readback or {},
            "dryRun": dry_run_requested,
            "rollback": {
                "triggered": bool(rollback_reason),
                "reason": rollback_reason,
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
    write_json(report_dir / "findings.json", {"target": args.target, "issues": findings})
    _write_summary_bundle(
        report_dir,
        command="deploy",
        target=args.target,
        status="ok" if final_exit_code == 0 else "failed",
        summary=f"stackctl deploy {'completed' if final_exit_code == 0 else 'failed'} for {args.target}",
        details=(_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result) + ([f"rollout stage: {rollout_stage}"] if args.target == "prod-hosted" else []) + [
            f"post-deploy {item['summary']}"
            for item in post_deploy_checks
        ] + [
            f"rollback-check {item['summary']}"
            for item in rollback_post_checks
        ] + ([f"wired workloads: {', '.join(w['rolloutRef'] for w in _prod_rollout_workloads()) or 'none'}"] if args.target == "prod-hosted" else []) + ([f"rollout decision: {rollout_decision}"] if args.target == "prod-hosted" else []) + ([f"rollback triggered: {rollback_reason}"] if rollback_reason else []) + (["dry-run remained read-only"] if dry_run_requested and args.target == "prod-hosted" else []),
        timing=timing,
    )
    _write_stdout_markdown(
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
        "details": (_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result) + findings + [
            f"rollback-check {item['summary']}"
            for item in rollback_post_checks
        ] + ([f"rollout decision: {rollout_decision}"] if args.target == "prod-hosted" else []) + ([f"rollback triggered: {rollback_reason}"] if rollback_reason else []) + (["dry-run remained read-only"] if dry_run_requested and args.target == "prod-hosted" else []),
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_deploy(args: argparse.Namespace) -> dict[str, Any]:
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    if args.target != "prod-hosted" or dry_run:
        return _command_deploy_with_lock(args)
    try:
        with _prod_release_lock():
            return _command_deploy_with_lock(args)
    except RuntimeError as error:
        return {
            "exitCode": 2,
            "summary": "stackctl deploy blocked by prod release transaction",
            "details": [str(error)],
        }


def command_roll(args: argparse.Namespace) -> dict[str, Any]:
    started_monotonic, started_at = _start_timing()

    if args.target in {"alpha-local", "beta-local", "gamma-local"}:
        env_map = {
            "alpha-local": "alpha",
            "beta-local": "beta",
            "gamma-local": "gamma",
        }
        nested_args = argparse.Namespace(
            command="up",
            env=env_map[args.target],
            target=args.target,
            device_id="",
            skip_app=True,
            skip_build=False,
            workload="full",
            rollout_mode="",
            output_format="json",
            report_dir=getattr(args, "report_dir", ""),
        )
        payload = command_up(nested_args)
        payload["summary"] = f"stackctl roll {args.mode} completed for {args.target}"
        return payload

    timing = _finish_timing(started_monotonic, started_at)
    return {
        "exitCode": 2,
        "summary": f"stackctl roll does not support target {args.target}",
        "details": [],
        **timing,
    }


def _all_services() -> list[str]:
    services: list[str] = []
    for path in ROOT.glob("quwoquan_service/services/*/configs/default/config.yaml"):
        services.append(path.parents[2].name)
    return sorted(set(services))


def _beta_env_from_port_manifest() -> dict[str, str]:
    manifest = load_port_manifest()
    ports = profile_ports(manifest, "beta-local")
    return {
        "GATEWAY_PORT": str(ports["api-edge"]),
        "PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "OPS_PORTAL_PORT": str(ports["ops-portal"]),
        "MEDIA_PORT": str(ports["media-edge"]),
        "ASSISTANT_PORT": str(ports["assistant-service"]),
        "CHAT_PORT": str(ports["chat-service"]),
    }


def _gamma_env_from_port_manifest(topology: dict[str, Any], target_name: str) -> dict[str, str]:
    manifest = load_port_manifest()
    profile_name = str(get_target(topology, target_name).get("portProfile"))
    ports = profile_ports(manifest, profile_name)
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    environment = {
        "LOCAL_GAMMA_HTTP_PORT": str(ports["api-edge"]),
        "LOCAL_GAMMA_PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "LOCAL_GAMMA_PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "LOCAL_GAMMA_MEDIA_EDGE_PORT": str(ports["media-edge"]),
        "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": str(ports["object-storage-edge"]),
        "LOCAL_GAMMA_MEDIA_PUBLIC_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
        "LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL": str(public_bases["mediaVideo"]),
        "LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "LOCAL_GAMMA_LIVEKIT_PUBLIC_URL": str(public_bases["rtc"]),
        "LOCAL_GAMMA_LIVEKIT_HTTP_PORT": str(ports["livekit-http"]),
        "LOCAL_GAMMA_LIVEKIT_RTC_TCP_PORT": str(ports["livekit-rtc-tcp"]),
        "LOCAL_GAMMA_LIVEKIT_RTC_UDP_PORT": str(ports["livekit-rtc-udp"]),
        "LOCAL_GAMMA_LIVEKIT_METRICS_PORT": str(ports["livekit-metrics"]),
        "LOCAL_GAMMA_TURN_TCP_PORT": str(ports["coturn"]),
        "LOCAL_GAMMA_TURN_UDP_PORT": str(ports["coturn"]),
        "LOCAL_GAMMA_CONTENT_PORT": str(ports["content-service"]),
        "LOCAL_GAMMA_CHAT_PORT": str(ports["chat-service"]),
        "LOCAL_GAMMA_USER_PORT": str(ports["user-service"]),
        "LOCAL_GAMMA_ASSISTANT_PORT": str(ports["assistant-service"]),
        "LOCAL_GAMMA_INTEGRATION_PORT": str(ports["integration-service"]),
        "LOCAL_GAMMA_NOTIFICATION_PORT": str(ports["notification-service"]),
        "LOCAL_GAMMA_REALTIME_PORT": str(ports["realtime-gateway"]),
        "LOCAL_GAMMA_RTC_PORT": str(ports["rtc-service"]),
        "LOCAL_GAMMA_REC_MODEL_PORT": str(ports["rec-model-service"]),
        "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT": str(ports["product-ops-service"]),
        "LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT": str(ports["platform-ops-service"]),
        "LOCAL_GAMMA_TAG_PORT": str(ports["tag-service"]),
        "LOCAL_GAMMA_SEARCH_PORT": str(ports["search-service"]),
        "LOCAL_GAMMA_MONGO_PORT": str(ports["mongodb"]),
        "LOCAL_GAMMA_REDIS_PORT": str(ports["redis"]),
        "LOCAL_GAMMA_POSTGRES_PORT": str(ports["postgres"]),
        "LOCAL_GAMMA_ES_PORT": str(ports["elasticsearch"]),
    }
    environment.update(
        prepare_local_environment_auth("gamma", "gamma-local").environment
    )
    environment.update(
        prepare_local_gamma_object_storage(
            edge_port=ports["object-storage-edge"],
        ).environment
    )
    return environment


def _health_checks_for_target(topology: dict[str, Any], target_name: str, scope: str) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    public_bases = target.get("publicBases") or {}
    origins = target.get("origins") or {}
    service_policy = ((env_cfg.get("artifactPolicy") or {}).get("service") or {})
    allow_fixture_refs = bool(service_policy.get("allowFixtureRefs")) or target_name == "prod-sim"
    checks: list[dict[str, Any]] = []
    if scope in {"edge", "full", "content-import", "content-consumer"}:
        checks.append(
            {
                "name": "api-health",
                "scope": "edge",
                "url": f"{str(public_bases['api']).rstrip('/')}/healthz",
            }
        )
    if scope in {"edge", "full"}:
        checks.append(
            {
                "name": "product-ops-health",
                "scope": "edge",
                "url": f"{str(public_bases['productOps']).rstrip('/')}/healthz",
            }
        )
    if scope in {"media", "full", "content-import", "content-consumer"} and "mediaImage" in public_bases:
        checks.append(
            {
                "name": "media-edge-health",
                "scope": "media",
                "url": f"{str(public_bases['mediaImage']).rstrip('/')}/healthz",
            }
        )
        if allow_fixture_refs:
            for asset in load_media_delivery_manifest():
                url = build_media_delivery_url(public_bases, asset)
                check = {
                    "name": f"media-public-{asset['logicalAssetId']}",
                    "scope": "media",
                    "url": url,
                }
                mime_type = str(asset.get("mimeType") or "").strip().lower()
                if mime_type.startswith("video/"):
                    check["headers"] = {"Range": "bytes=0-1"}
                    check["expectedStatus"] = 206
                    check["expectedContentTypePrefix"] = "video/"
                elif mime_type:
                    check["expectedContentTypePrefix"] = mime_type
                checks.append(check)
        media_origin = str(origins.get("mediaOrigin") or "").rstrip("/")
        if media_origin and allow_fixture_refs:
            origin_bases = {
                "mediaAvatar": media_origin,
                "mediaImage": media_origin,
                "mediaVideo": media_origin,
            }
            for asset in load_media_delivery_manifest():
                url = build_media_delivery_url(
                    origin_bases,
                    asset,
                    require_https=False,
                )
                check = {
                    "name": f"media-origin-{asset['logicalAssetId']}",
                    "scope": "media",
                    "url": url,
                }
                mime_type = str(asset.get("mimeType") or "").strip().lower()
                if mime_type.startswith("video/"):
                    check["headers"] = {"Range": "bytes=0-1"}
                    check["expectedStatus"] = 206
                    check["expectedContentTypePrefix"] = "video/"
                elif mime_type:
                    check["expectedContentTypePrefix"] = mime_type
                checks.append(check)
    if scope in {"service", "full"}:
        checks.extend(_service_health_checks_for_target(target_name))
    if scope in {"content-import", "content-consumer", "full"}:
        checks.extend(_content_data_plane_health_checks(target_name))
    if scope in {"content-consumer", "full"}:
        checks.extend(_content_consumer_health_checks(target_name, public_bases))
    if scope == "full":
        checks.extend(_full_scope_health_checks(target_name, public_bases, env_cfg))
    return checks


_CONTENT_DATA_PLANE_ROLES = frozenset(
    {"content-service", "entity-service", "tag-service", "search-service"}
)


def _content_data_plane_health_checks(target_name: str) -> list[dict[str, Any]]:
    """Only probes required by immutable content import and API consumption."""
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return []
    manifest = load_port_manifest()
    role_names = [
        role_name
        for role_name in _expected_local_roles(target_name)
        if role_name in _CONTENT_DATA_PLANE_ROLES
    ]
    # ship apply 依赖 topology 声明的 entity reload 角色；即使目标（如 beta）不运行完整
    # 内容数据面，该角色也属于内容导入平面，必须纳入 content-import 探针。
    reload_role = str(((target.get("dataRelease") or {}).get("entityReloadPortRole")) or "")
    if reload_role and reload_role not in role_names:
        role_names.append(reload_role)
    checks: list[dict[str, Any]] = []
    for role_name in role_names:
        port = canonical_port(manifest, str(profile_name), role_name)
        checks.append(
            {
                "name": role_name,
                "scope": "content-import",
                "url": f"http://127.0.0.1:{port}/healthz",
            }
        )
    return checks


def _content_consumer_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
) -> list[dict[str, Any]]:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-hosted"}:
        return []
    api_base = str(public_bases.get("api") or "").rstrip("/")
    if not api_base:
        return []
    return [
        {"name": "app-config", "scope": "content-consumer", "url": f"{api_base}/config/app"},
        {"name": "content-feed", "scope": "content-consumer", "url": f"{api_base}/content/feed?limit=1"},
    ]


def _service_health_checks_for_target(target_name: str) -> list[dict[str, Any]]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    mock_flags = (topology["environments"][env_name].get("mockBoundaryFlags") or {})
    if mock_flags.get("servicePlane"):
        return [
            {
                "name": "service-plane-mocked",
                "scope": "service",
                "url": "",
                "skip": True,
                "reason": "service plane is mocked in this target",
            }
        ]
    profile_name = target.get("portProfile")
    if not profile_name:
        return []
    manifest = load_port_manifest()
    checks: list[dict[str, Any]] = []
    non_service_paths = {
        "realtime-gateway": "/healthz",
        "livekit-http": "/",
        "livekit-metrics": "/metrics",
    }
    for role_name in _expected_local_roles(target_name):
        if not role_name.endswith("-service") and role_name not in non_service_paths:
            continue
        port = canonical_port(manifest, str(profile_name), role_name)
        path = non_service_paths.get(role_name, "/healthz")
        if role_name == "rec-model-service":
            path = "/health"
        checks.append(
            {
                "name": role_name,
                "scope": "service",
                "url": f"http://127.0.0.1:{port}{path}",
            }
        )
    return checks


def _full_scope_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
    env_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    env_name = str(env_cfg.get("artifactPolicy", {}).get("app", {}).get("runtimeEnv", ""))
    if target_name == "beta-local":
        checks.append(
            {
                "name": "app-config",
                "scope": "full",
                "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
            }
        )
        checks.extend(
            [
                {
                    "name": "content-feed",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/content/feed",
                },
                {
                    "name": "chat-contacts",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/chat/contacts",
                },
                {
                    "name": "app-messages-unread-count",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/app-messages/unread-count",
                },
                {
                    "name": "feed-intersections",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/content/feed/intersections?limit=4&channel=recommend"
                    ),
                },
            ]
        )
    elif target_name == "gamma-local":
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
                },
                {
                    "name": "gamma-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1",
                },
                {
                    "name": "tag-shared-tags-smoke",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/tag/shared-tags?objectAId=u1&objectAType=user&objectBId=u2&objectBType=user"
                    ),
                },
            ]
        )
    elif target_name == "prod-sim":
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
                },
                {
                    "name": "prod-sim-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1",
                },
            ]
        )
    return checks


def _network_report(target_name: str) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        public_bases = target.get("publicBases") or {}
        endpoints = [
            {"name": name, "url": value}
            for name, value in public_bases.items()
            if isinstance(value, str) and value.strip()
        ]
        return {
            "profile": "",
            "ports": [],
            "publicEndpoints": endpoints,
        }
    manifest = load_port_manifest()
    ports = []
    for role in _expected_local_roles(target_name):
        if role not in manifest["roles"]:
            continue
        port = canonical_port(manifest, profile_name, role)
        ports.append({"name": role, "port": port, "open": socket_probe(port)})
    return {
        "profile": profile_name,
        "ports": ports,
        "publicEndpoints": [],
    }


def _expected_local_roles(target_name: str) -> list[str]:
    role_map = {
        "alpha-local": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
        ],
        "beta-local": [
            "api-edge",
            "product-ops-edge",
            "platform-ops-edge",
            "ops-portal",
            "media-edge",
            "media-origin",
            "assistant-service",
            "chat-service",
        ],
        "gamma-local": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "chat-service",
            "user-service",
            "content-service",
            "assistant-service",
            "rec-model-service",
            "product-ops-service",
            "platform-ops-service",
            "tag-service",
            "search-service",
            "entity-service",
            "circle-service",
            "integration-service",
            "notification-service",
            "realtime-gateway",
            "rtc-service",
            "livekit-http",
            "livekit-rtc-tcp",
            "livekit-metrics",
            "coturn",
            "postgres",
            "mongodb",
            "redis",
            "elasticsearch",
        ],
        "prod-sim": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
        ],
    }
    return role_map.get(target_name, [])


def _resolve_prod_rollout_stage(step: str, requested_stage: str = "") -> str:
    normalized_step = str(step).strip()
    try:
        percentage = int(normalized_step)
    except ValueError as error:
        raise ValueError(f"step 必须是 1..100 的整数，实际 {step!r}") from error
    if percentage < 1 or percentage > 100:
        raise ValueError(f"step 必须在 1..100，实际 {percentage}")

    explicit_stage = str(requested_stage).strip()
    if explicit_stage:
        if explicit_stage == "full" and percentage != 100:
            raise ValueError("full 必须与 step=100 同时使用")
        if explicit_stage != "full" and percentage == 100:
            raise ValueError("step=100 只能使用 full")
        return explicit_stage
    if percentage == 100:
        return "full"
    if percentage <= 5:
        return "gray-initial"
    return "carry-on"


def _prod_rollout_workloads() -> list[dict[str, Any]]:
    """读三态 inventory 中已 wired 进 prod root 的 workload。

    与 deploy_to_prod.sh 同源（quwoquan_ops/environments/workload_topology_inventory.yaml），
    Modular Monolith 单元（seed-box）与按 Strangler Fig 拆分后新增的独立 workload
    一旦 wired_to_prod_root=true 即自动出现，无需改 stackctl。
    """
    try:
        inv = load_json_yaml(ROOT / "quwoquan_ops" / "environments" / "workload_topology_inventory.yaml")
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for w in (inv or {}).get("workloads", []) or []:
        if not w.get("wired_to_prod_root"):
            continue
        kind = str(w.get("workload_resource", "Deployment")).lower()
        out.append(
            {
                "name": w.get("name"),
                "deployKind": w.get("deploy_kind"),
                "workloadResource": w.get("workload_resource", "Deployment"),
                "rolloutRef": f"{kind}/{w.get('name')}",
            }
        )
    return out


def _local_log_report(target_name: str) -> dict[str, Any]:
    candidates: dict[str, Path] = {
        "alpha-state": target_process_dir("alpha-local"),
        "beta-state": target_process_dir("beta-local"),
        "beta-manual": target_process_dir("beta-local") / "app-beta-manual",
        "app-instances": repo_local_dir("app-instances"),
        "local-gamma": target_process_dir("gamma-local"),
        "release-state": _release_state_dir(),
    }
    hits = []
    for name, path in candidates.items():
        if path.exists():
            hits.append({"name": name, "path": relpath(path)})
    extra: dict[str, Any] = {}
    try:
        runtime_root = _local_runtime_log_root(target_name)
    except RuntimeError:
        runtime_root = None
    if runtime_root is not None:
        extra["runtimeDiagnostics"] = _runtime_log_evidence_report(runtime_root)
    else:
        extra["runtimeDiagnostics"] = {
            "availability": "not_started",
            "recordCount": 0,
            "reason": "local runtime observability root is unavailable",
        }
    if target_name == "prod-hosted":
        extra["prodReleaseState"] = _load_release_state(PROD_RELEASE_UNIT)
    return {"paths": hits, **extra}


def _runtime_log_evidence_report(log_root: Path) -> dict[str, Any]:
    """Summarize canonical records without copying raw messages into reports."""
    severity_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    parse_issues: list[str] = []
    record_count = 0
    files = sorted(path for path in log_root.rglob("*.log") if path.is_file())
    for path in files:
        kind = path.stem
        try:
            records, issues = parse_log_records(
                kind,
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
            )
        except ValueError:
            continue
        record_count += len(records)
        parse_issues.extend(
            f"{relpath(path)}: {issue}" for issue in issues[:5]
        )
        for record in records:
            severity = str(record.get("severity") or "UNKNOWN")
            signal = str(record.get("signal") or "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
    return {
        "availability": "available" if log_root.exists() else "not_started",
        "root": relpath(log_root),
        "files": [relpath(path) for path in files],
        "recordCount": record_count,
        "severityCounts": dict(sorted(severity_counts.items())),
        "topSignals": [
            {"signal": signal, "count": count}
            for signal, count in sorted(
                signal_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:10]
        ],
        "parseIssues": parse_issues[:20],
    }


def _data_report(target_name: str) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return {"ports": []}
    manifest = load_port_manifest()
    return {
        "ports": {
            "postgres": canonical_port(manifest, profile_name, "postgres"),
            "mongodb": canonical_port(manifest, profile_name, "mongodb"),
            "redis": canonical_port(manifest, profile_name, "redis"),
        }
    }


def _metrics_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    checks = _health_checks_for_target(topology, target_name, "full")
    return {
        "probes": [
            {"name": item["name"], "url": item["url"]}
            for item in checks
        ],
        "scriptProbes": _script_probe_plan_for_target(topology, target_name),
    }


def _security_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    return {
        "hostAllowlist": env_cfg.get("hostAllowlist", []),
        "forbiddenHostTokens": env_cfg.get("forbiddenHostTokens", []),
        "artifactPolicy": env_cfg.get("artifactPolicy", {}),
    }


def _command_details(result: Any) -> list[str]:
    details: list[str] = []
    for output in (str(result.stdout or ""), str(result.stderr or "")):
        for line in output.splitlines():
            normalized = line.strip()
            if normalized and normalized not in details:
                details.append(normalized)
    if not details:
        return [f"exit={result.returncode}"]
    if len(details) <= COMMAND_SUMMARY_DETAIL_LIMIT:
        return details
    retained = details[:COMMAND_SUMMARY_DETAIL_LIMIT]
    retained.append("additional command output retained in report.json")
    return retained


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "package": command_package,
        "verify": command_verify,
        "up": command_up,
        "down": command_down,
        "status": command_status,
        "health": command_health,
        "inspect": command_inspect,
        "doctor": command_doctor,
        "content-readiness": command_content_readiness,
        "repair": command_repair,
        "roll": command_roll,
        "deploy": command_deploy,
    }
    payload = dispatch[args.command](args)
    return print_result(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())

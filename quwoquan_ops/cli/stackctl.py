#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import json
import os
import selectors
import shlex
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

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
    run_dir as observability_run_dir,
    run_id_from_report_dir,
    write_run_manifest,
    write_stackctl_links,
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
    ],
    "packaging": [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"],
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ],
}

DEFAULT_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified environment packaging, startup, verification, inspection, and rollout control.",
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--report-dir", default="")
    report_dir_compat_parser = argparse.ArgumentParser(add_help=False)
    report_dir_compat_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package", parents=[report_dir_compat_parser])
    package_parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    package_parser.add_argument("--kind", choices=["runtime", "legal-static"], default="runtime")
    package_parser.add_argument("--service", default="")
    package_parser.add_argument("--include-services", action="store_true")
    package_parser.add_argument("--target", choices=TARGETS, default="")

    verify_parser = subparsers.add_parser("verify", parents=[report_dir_compat_parser])
    verify_parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    verify_parser.add_argument("--target", choices=TARGETS, default="")
    verify_parser.add_argument(
        "--kind",
        choices=["topology", "config", "packaging", "legal-static", "all"],
        default="all",
    )
    verify_parser.add_argument(
        "--tier",
        choices=["t1", "t2", "t3", "t4", "all"],
        default="t1",
    )

    up_parser = subparsers.add_parser("up", parents=[report_dir_compat_parser])
    up_parser.add_argument("--target", choices=TARGETS, default="")
    up_parser.add_argument("--env", choices=DEV_UP_ENVS, default="")
    up_parser.add_argument("--device-id", default="")
    up_parser.add_argument("--skip-app", action="store_true")
    up_parser.add_argument("--rollout-mode", choices=["gray-initial", "carry-on", "full"], default="")

    down_parser = subparsers.add_parser("down", parents=[report_dir_compat_parser])
    down_parser.add_argument("--target", choices=TARGETS, required=True)

    status_parser = subparsers.add_parser("status", parents=[report_dir_compat_parser])
    status_parser.add_argument("--target", choices=TARGETS, required=True)

    health_parser = subparsers.add_parser("health", parents=[report_dir_compat_parser])
    health_parser.add_argument("--target", choices=TARGETS, required=True)
    health_parser.add_argument(
        "--scope",
        choices=["edge", "media", "service", "full"],
        default="full",
    )
    health_parser.add_argument("--request-timeout-seconds", type=int, default=0)
    health_parser.add_argument("--retry-attempts", type=int, default=0)
    health_parser.add_argument("--retry-sleep-seconds", type=float, default=-1.0)

    inspect_parser = subparsers.add_parser("inspect", parents=[report_dir_compat_parser])
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

    doctor_parser = subparsers.add_parser("doctor", parents=[report_dir_compat_parser])
    doctor_parser.add_argument("--target", choices=TARGETS, required=True)

    repair_parser = subparsers.add_parser("repair", parents=[report_dir_compat_parser])
    repair_parser.add_argument("--target", choices=TARGETS, required=True)
    repair_parser.add_argument(
        "--fix",
        choices=["rebuild-packages", "restart-stack", "reclaim-ports"],
        required=True,
    )

    roll_parser = subparsers.add_parser("roll", parents=[report_dir_compat_parser])
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

    deploy_parser = subparsers.add_parser("deploy", parents=[report_dir_compat_parser])
    deploy_parser.add_argument("--target", choices=("prod-hosted",), required=True)
    deploy_parser.add_argument("--mode", choices=("restart", "rollout", "cold-build"), default="")
    deploy_parser.add_argument("--stage", default="")
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
    deploy_parser.add_argument("--error-rate", default="")
    deploy_parser.add_argument("--p95-ms", default="")
    deploy_parser.add_argument("--redis-error-rate", default="")
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

    services = ["gamma-proxy", "content-service", "assistant-service", "user-service", "chat-service"]
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
        release_id=str((extra or {}).get("releaseId") or ""),
        data_release_id=str((extra or {}).get("dataReleaseId") or ""),
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


def _selected_verify_commands(kind: str, env_name: str = "") -> list[list[str]]:
    packaging_commands = [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"]
        + (["--env", env_name] if env_name in ENVIRONMENTS else []),
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"]
        + (["--env", env_name] if env_name in ENVIRONMENTS else []),
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ]
    if kind == "all":
        commands: list[list[str]] = []
        for group_name in ("topology", "config", "packaging"):
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


def _selected_tier_commands(
    env_name: str,
    target_name: str,
    tier: str,
    report_dir: Path | None = None,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if tier in {"t3", "t4", "all"} and target_name in {
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
                        "--skip-app",
                    ],
                    "cwd": ROOT,
                }
            )
    if tier in {"t2", "all"}:
        commands.extend(
            [
                {
                    "name": "content-media-url-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "test/core/media/content_media_url_test.dart",
                        "test/cloud/chat/chat_avatar_url_resolution_test.dart",
                    ],
                    "cwd": ROOT,
                },
                {
                    "name": "contract-seeded-mock-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "--dart-define=CONTRACT_FIXTURE_PROFILE=full",
                        "test/cloud/services/contract_seeded_mock_repository_test.dart",
                    ],
                    "cwd": ROOT,
                },
            ]
        )
    if tier in {"t3", "all"}:
        if env_name in {"alpha", "beta", "all"}:
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
                    "env": {
                        "CLOUD_GATEWAY_BASE_URL": str(public_bases["api"]),
                    },
                }
            )
    if tier in {"t4", "all"}:
        smoke_command = _environment_page_smoke_tier_command(
            env_name,
            target_name,
            report_dir,
        )
        if smoke_command is not None:
            commands.append(smoke_command)
        media_surface_command = _seeded_media_surface_tier_command(env_name, target_name)
        if media_surface_command is not None:
            commands.append(media_surface_command)
        commands.append(
            {
                "name": "prod-rollout-stackctl-contract",
                "argv": ["python3", "quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py"],
            }
        )
    return commands


def _seeded_media_surface_tier_command(
    env_name: str,
    target_name: str,
) -> dict[str, Any] | None:
    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        return None
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    runtime_env = str(target.get("env") or env_name or "")
    if runtime_env not in {"alpha", "beta", "gamma"}:
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


def _environment_page_smoke_tier_command(
    env_name: str,
    target_name: str,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        return None
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    if not {"api", "productOps", "mediaImage"}.issubset(public_bases):
        return None
    runtime_env = str(target.get("env") or env_name or "alpha")
    if target_name in {"prod-sim", "prod-hosted"}:
        runtime_env = "prod"
    data_source = "mock" if target_name in {"alpha-local", "prod-sim"} else "remote"
    token = _resolve_test_auth_token(runtime_env)
    if not token and target_name != "prod-hosted":
        token = f"local-{target_name}-token"
    smoke_report = (
        report_dir / "environment-page-smoke" / "report.json"
        if report_dir is not None
        else ROOT / ".qwq_output" / "runs" / env_name / "device-matrix" / "environment-smoke" / f"{target_name}.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--report",
        str(smoke_report),
        "--env-name",
        target_name,
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
        "--media-base-url",
        str(public_bases["mediaImage"]),
        "--test-auth-token",
        token,
        "--target",
        "test/patrol/environment/basic_viability_test.dart",
    ]
    platform = os.environ.get("STACKCTL_PAGE_SMOKE_PLATFORM", "").strip()
    if platform:
        argv.extend(["--platform", platform])
    device_id = os.environ.get("STACKCTL_PAGE_SMOKE_DEVICE_ID", "").strip()
    if device_id:
        argv.extend(["--device-id", device_id])
    if os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip() in {"1", "true", "yes"}:
        argv.append("--dry-run")
    return {
        "name": f"{target_name}-environment-page-smoke",
        "argv": argv,
        "cwd": ROOT,
        "blocking": target_name != "alpha-local",
        "reportPath": relpath(smoke_report),
    }


def fetch_url(
    url: str,
    timeout: float = 6.0,
    *,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
    headers: dict[str, str] | None = None,
) -> tuple[bool, int | None, str]:
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
            with urllib.request.urlopen(
                request,
                timeout=timeout,
                context=ssl._create_unverified_context(),
            ) as response:
                body = response.read().decode("utf-8", errors="replace")
                return True, int(response.status), body[:500]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), body[:500]
        except Exception as exc:
            message = str(exc)
            if attempt >= total_attempts or not any(marker in message for marker in retry_markers):
                return False, None, message
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown fetch failure"


def _read_json_payload(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return load_json_yaml(path)
    except Exception:  # noqa: BLE001
        return None


def _resolve_test_auth_token(env_name: str) -> str:
    token_envs = {
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN", "GAMMA_TEST_AUTH_TOKEN"),
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
    token = _resolve_test_auth_token(env_name)
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


def _load_release_state(service: str = "seed-box") -> dict[str, str]:
    state_path = ROOT / ".qwq_output" / "local" / "release-state" / f"{service}.state"
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
) -> dict[str, str]:
    state_dir = ROOT / ".qwq_output" / "local" / "release-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{service}.state"
    payload = {
        "service": service,
        "from_image": from_image,
        "to_image": to_image,
        "from_config": from_config,
        "to_config": to_config,
        "step": step,
        "updated_at": utc_now(),
    }
    lines = [f"{key}={value}" for key, value in payload.items()]
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


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
    output_root: str = ".qwq_output/release/legal-static",
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
    details.append(f"app package ready: .qwq_output/release/app/{env_name}")

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
            details.append(f"service package ready: .qwq_output/release/service/{service}/{env_name}")

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


def _command_verify_legal_static(args: argparse.Namespace) -> dict[str, Any]:
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
        "tier": args.tier,
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
        extra={"kind": "legal-static", "tier": args.tier},
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
    if args.kind == "legal-static":
        return _command_verify_legal_static(args)

    env_name = args.env or (get_target(load_environment_topology(), args.target).get("env") if args.target else "all")
    target_name = args.target or (DEFAULT_TARGET_BY_ENV[env_name] if env_name in ENVIRONMENTS else "repo")
    report_dir = resolve_report_dir(args, env_name if env_name in ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _start_timing()
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    package_envs = [env_name] if env_name in ENVIRONMENTS else list(ENVIRONMENTS)
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
    commands = _selected_verify_commands(args.kind, env_name if env_name in ENVIRONMENTS else "")
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
    for tier_command in _selected_tier_commands(
        env_name if env_name in ENVIRONMENTS else "all",
        target_name,
        args.tier,
        report_dir,
    ):
        result = run(
            tier_command["argv"],
            cwd=tier_command.get("cwd"),
            env=tier_command.get("env"),
        )
        blocking = bool(tier_command.get("blocking", True))
        steps.append(
            {
                "kind": "tier",
                "tier": args.tier,
                "name": tier_command["name"],
                "argv": tier_command["argv"],
                "exitCode": result.returncode,
                "blocking": blocking,
                "reportPath": tier_command.get("reportPath", ""),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((tier_command["name"], "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0 and blocking:
            issues.append(
                f"{tier_command['name']} failed: "
                + (result.stderr.strip() or result.stdout.strip() or "unknown tier failure")
            )
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "timestamp": utc_now(),
        "kind": args.kind,
        "tier": args.tier,
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
        summary="stackctl verify passed" if not issues else "stackctl verify failed",
        details=issues or [f"ran {len(steps)} checks"],
        extra={"kind": args.kind, "tier": args.tier},
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
        beta_log_dir = ROOT / ".qwq_output" / "local" / "beta-local"
        return _tail_multiple_logs_for_startup(
            [
                ("beta-app", beta_log_dir / "app-beta.log"),
                ("beta-product-ops", beta_log_dir / "product-ops.log"),
                ("beta-platform-ops", beta_log_dir / "platform-ops.log"),
                ("beta-ops-portal", beta_log_dir / "ops-portal.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=35.0,
        )

    def tail_alpha_background_logs() -> dict[str, Any]:
        alpha_log_dir = ROOT / ".qwq_output" / "local" / "alpha-local"
        return _tail_multiple_logs_for_startup(
            [
                ("alpha-api-edge", alpha_log_dir / "api-edge.log"),
                ("alpha-product-ops", alpha_log_dir / "product-ops.log"),
                ("alpha-media-edge", alpha_log_dir / "media-edge.log"),
                ("alpha-media-origin", alpha_log_dir / "media-origin.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=20.0,
        )

    def tail_prod_sim_background_logs() -> dict[str, Any]:
        prod_sim_log_dir = ROOT / ".qwq_output" / "local" / "prod-sim"
        return _tail_multiple_logs_for_startup(
            [
                ("prod-sim-api-edge", prod_sim_log_dir / "api-edge.log"),
                ("prod-sim-product-ops", prod_sim_log_dir / "product-ops.log"),
                ("prod-sim-media-edge", prod_sim_log_dir / "media-edge.log"),
                ("prod-sim-media-origin", prod_sim_log_dir / "media-origin.log"),
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
            beta_ready_tail = _tail_file_for_startup(
                ROOT / ".qwq_output" / "local" / "beta-local" / "app-beta.log",
                prefix="[beta app-beta] ",
                idle_timeout_seconds=8.0,
                max_follow_seconds=180.0,
                ready_patterns=(
                    "[app-beta-manual] beta environment is ready.",
                    "[app-beta-manual] --skip-app set; beta cloud stack keeps running until Ctrl-C.",
                ),
                failure_patterns=(
                    "GATE_BLOCK:",
                    " unavailable:",
                    "colima start failed",
                    "docker daemon still unavailable",
                    "docker daemon unavailable and colima is not installed",
                    "assistant log:",
                    "chat log:",
                    "chat seed log:",
                    "gateway log:",
                    "media edge log:",
                    "media origin log:",
                ),
                ready_idle_timeout_seconds=3.0,
            )
            steps.append(
                {
                    "kind": "beta-backend-ready-wait",
                    "exitCode": 0,
                    "stdout": "waited for beta backend ready sentinel",
                    "stderr": "",
                    "tail": beta_ready_tail,
                }
            )
            beta_ready_failure = None
            if bool(beta_ready_tail.get("failureSeen")):
                beta_ready_failure = str(
                    beta_ready_tail.get("failureLine") or "beta backend startup failed"
                )
            elif not bool(beta_ready_tail.get("readySeen")):
                beta_ready_failure = "beta backend did not reach ready state before timeout"
            if beta_ready_failure is not None:
                result = subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=beta_ready_failure,
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
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]
        env = _gamma_env_from_port_manifest(topology, requested_target)
        result = run_stage("gamma-local", cmd, env=env, live_prefix="[gamma-local] ")
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
        result = run(cmd)
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
        ok, status_code, body = fetch_url(
            item["url"],
            timeout=timeout_seconds,
            retry_attempts=retry_attempts,
            retry_sleep_seconds=retry_sleep_seconds,
            headers=item.get("headers"),
        )
        expected_status = item.get("expectedStatus")
        if ok and expected_status is not None and status_code != int(expected_status):
            ok = False
            body = f"expected HTTP {expected_status}, got {status_code}"
        if not ok:
            findings.append(f"{item['scope']}/{item['name']} failed: {status_code or 'ERR'} {item['url']}")
        statuses.append(
            {
                "name": item["name"],
                "scope": item["scope"],
                "url": item["url"],
                "ok": ok,
                "statusCode": status_code,
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
    if "network" in scopes:
        inspection["network"] = _network_report(args.target)
    if "config" in scopes:
        inspection["config"] = {
            "target": target,
            "portProfile": target.get("portProfile"),
            "publicBases": target.get("publicBases", {}),
            "origins": target.get("origins", {}),
            "releaseState": (
                _load_release_state("seed-box")
                if args.target == "prod-hosted"
                else {}
            ),
        }
        if args.target == "prod-hosted":
            inspection["config"]["rootlessRuntime"] = _prod_plane_runtime_report(
                "service",
                report_dir / "prod_rootless_service_runtime.json",
            )
    if "logs" in scopes:
        inspection["logs"] = _local_log_report(args.target)
    if "data" in scopes:
        inspection["data"] = _data_report(args.target)
    if "metrics" in scopes:
        inspection["metrics"] = _metrics_report(topology, args.target)
    if "security" in scopes:
        inspection["security"] = _security_report(topology, args.target)
    timing = _finish_timing(started_monotonic, started_at)
    write_json(report_dir / "report.json", {"command": "inspect", "inspection": inspection, **timing})
    for key, value in inspection.items():
        write_json(report_dir / f"{key}.json", value)
    details = [f"{key}: collected" for key in inspection]
    _write_summary_bundle(
        report_dir,
        command="inspect",
        target=args.target,
        status="ok",
        summary=f"stackctl inspect completed for {args.target}",
        details=details,
        extra={"scope": args.scope},
        timing=timing,
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl inspect completed for {args.target}",
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
            state = _load_release_state("seed-box")
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
    packages = [
        ROOT / ".qwq_output" / "release" / "app" / env_name / "report.json",
    ]
    require_package_artifacts = bool(target.get("portProfile"))
    if require_package_artifacts and not all(path.exists() for path in packages):
        findings.append("packaged app artifact is missing")
    repair_plan = []
    if findings:
        if any("health checks" in item for item in findings):
            repair_plan.append("run `stackctl health --target <target> --scope full` to confirm failing probes")
        if any("ports not listening" in item for item in findings):
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
    if args.fix == "restart-stack":
        down_args = argparse.Namespace(command="down", target=args.target, output_format="json", report_dir=str(report_dir / "down"))
        up_args = argparse.Namespace(command="up", target=args.target, device_id="", skip_app=False, output_format="json", report_dir=str(report_dir / "up"))
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


def command_deploy(args: argparse.Namespace) -> dict[str, Any]:
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
    if args.target == "prod-hosted":
        required = [
            args.service,
            args.from_image,
            args.to_image,
            args.from_config,
            args.to_config,
            args.step,
            args.error_rate,
            args.p95_ms,
            args.redis_error_rate,
        ]
        if not all(required):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy prod-hosted requires service/image/config/step/SLO arguments",
                "details": [],
                **timing,
            }
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
        replicas = str(_replicas_for_step(args.step))
        # 灰度 stage 映射：未到 100% 走 gray-initial 灰度实例（承接原远端 gamma 验证），100% 放量 full。
        rollout_stage = "full" if str(args.step).strip() == "100" else "gray-initial"
        deploy_result = run(
            ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
            env={
                "CLOUD_PROVIDER": args.cloud_provider,
                "SERVICE": args.service,
                "IMAGE_VERSION": args.to_image,
                "CONFIG_VERSION": args.to_config,
                "ROLLOUT_STAGE": rollout_stage,
                "REPLICAS": replicas,
                "DRY_RUN": args.dry_run,
                "SEED_BOX_IMAGE_REPOSITORY": os.environ.get(
                    "SEED_BOX_IMAGE_REPOSITORY",
                    "ghcr.io/openstudio2022/quwoquan/seed-box",
                ),
                "RECOMMENDATION_SERVICE_IMAGE_REPOSITORY": os.environ.get(
                    "RECOMMENDATION_SERVICE_IMAGE_REPOSITORY",
                    "ghcr.io/openstudio2022/quwoquan/recommendation-service",
                ),
            },
        )
        if deploy_result.returncode != 0:
            timing = _finish_timing(started_monotonic, started_at)
            write_json(
                report_dir / "report.json",
                {
                    "command": "deploy",
                    "target": args.target,
                    "stage": "apply",
                    "argv": ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                    "exitCode": deploy_result.returncode,
                    "stdout": deploy_result.stdout,
                    "stderr": deploy_result.stderr,
                    **timing,
                },
            )
            _write_summary_bundle(
                report_dir,
                command="deploy",
                target=args.target,
                status="failed",
                summary="stackctl deploy failed during prod apply",
                details=_command_details(deploy_result),
                timing=timing,
            )
            _write_stdout_markdown(
                report_dir,
                [("prod-apply", "\n".join(filter(None, [deploy_result.stdout, deploy_result.stderr])))],
            )
            return {
                "exitCode": deploy_result.returncode,
                "summary": "stackctl deploy failed during prod apply",
                "details": _command_details(deploy_result),
                "reportDir": relpath(report_dir),
                **timing,
            }
        if dry_run_requested:
            result = subprocess.CompletedProcess(
                cmd,
                0,
                stdout="prod dry-run skipped config_release_apply_stage.sh and remained read-only",
                stderr="",
            )
        else:
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
                tier="t4",
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
        if "decision=pause" in stdout_combined:
            rollout_decision = "pause"
            findings.append("slo gate decision=pause")
        elif "decision=rollback" in stdout_combined:
            rollout_decision = "rollback"
            rollback_reason = "slo gate decision=rollback"
            findings.append(rollback_reason)
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
                "REPLICAS": str(_replicas_for_step("100")),
                "DRY_RUN": "false",
                "SEED_BOX_IMAGE_REPOSITORY": os.environ.get(
                    "SEED_BOX_IMAGE_REPOSITORY",
                    "ghcr.io/openstudio2022/quwoquan/seed-box",
                ),
                "RECOMMENDATION_SERVICE_IMAGE_REPOSITORY": os.environ.get(
                    "RECOMMENDATION_SERVICE_IMAGE_REPOSITORY",
                    "ghcr.io/openstudio2022/quwoquan/recommendation-service",
                ),
            }
            rollback_result = run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                env=rollback_env,
            )
            if rollback_result.returncode == 0:
                rollback_state = _update_release_state(
                    args.service,
                    from_image=args.to_image,
                    to_image=args.from_image,
                    from_config=args.to_config,
                    to_config=args.from_config,
                    step="100",
                )
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
            else:
                findings.append("live rollback apply failed")
                final_exit_code = rollback_result.returncode
        elif rollout_decision == "pause" and final_exit_code == 10:
            final_exit_code = 10
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
            "rolloutDecision": rollout_decision,
            "wiredWorkloads": _prod_rollout_workloads() if args.target == "prod-hosted" else [],
            "postDeployChecks": post_deploy_checks,
            "postDeployFailures": post_deploy_failures,
            "rollbackPostChecks": rollback_post_checks,
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
        details=(_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result) + [
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
    return {
        "LOCAL_GAMMA_HTTP_PORT": str(ports["api-edge"]),
        "LOCAL_GAMMA_PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "LOCAL_GAMMA_PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "LOCAL_GAMMA_MEDIA_EDGE_PORT": str(ports["media-edge"]),
        "LOCAL_GAMMA_MEDIA_ORIGIN_PORT": str(ports["media-origin"]),
        "LOCAL_GAMMA_MEDIA_PUBLIC_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_BASE_URL": str(public_bases["mediaImage"]),
        # local-gamma 默认直接服务挂载的 curated media bundle；不要把容器内回源指向宿主 loopback。
        "LOCAL_GAMMA_MEDIA_ORIGIN_BASE_URL": "",
        "LOCAL_GAMMA_CONTENT_PORT": str(ports["content-service"]),
        "LOCAL_GAMMA_CHAT_PORT": str(ports["chat-service"]),
        "LOCAL_GAMMA_USER_PORT": str(ports["user-service"]),
        "LOCAL_GAMMA_ASSISTANT_PORT": str(ports["assistant-service"]),
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


def _health_checks_for_target(topology: dict[str, Any], target_name: str, scope: str) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    public_bases = target.get("publicBases") or {}
    origins = target.get("origins") or {}
    service_policy = ((env_cfg.get("artifactPolicy") or {}).get("service") or {})
    allow_fixture_refs = bool(service_policy.get("allowFixtureRefs")) or target_name == "prod-sim"
    checks: list[dict[str, Any]] = []
    if scope in {"edge", "full"}:
        checks.extend(
            {
                "name": item_name,
                "scope": "edge",
                "url": item_url,
            }
            for item_name, item_url in (
                ("api-health", f"{str(public_bases['api']).rstrip('/')}/healthz"),
                ("product-ops-health", f"{str(public_bases['productOps']).rstrip('/')}/healthz"),
            )
        )
    if scope in {"media", "full"} and "mediaImage" in public_bases:
        checks.append(
            {
                "name": "media-edge-health",
                "scope": "media",
                "url": f"{str(public_bases['mediaImage']).rstrip('/')}/healthz",
            }
        )
        if allow_fixture_refs:
            checks.append(
                {
                    "name": "media-public-sample",
                    "scope": "media",
                    "url": f"{str(public_bases['mediaImage']).rstrip('/')}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
                }
            )
            checks.append(
                {
                    "name": "media-video-range-sample",
                    "scope": "media",
                    "url": f"{str(public_bases.get('mediaVideo', public_bases['mediaImage'])).rstrip('/')}/media/video/s/archived-video/beta-sample.mp4",
                    "headers": {"Range": "bytes=0-1"},
                    "expectedStatus": 206,
                }
            )
        media_origin = str(origins.get("mediaOrigin") or "").rstrip("/")
        if media_origin and allow_fixture_refs:
            checks.append(
                {
                    "name": "media-origin-sample",
                    "scope": "media",
                    "url": f"{media_origin}/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
                }
            )
            checks.append(
                {
                    "name": "media-origin-video-range-sample",
                    "scope": "media",
                    "url": f"{media_origin}/media/video/s/archived-video/beta-sample.mp4",
                    "headers": {"Range": "bytes=0-1"},
                    "expectedStatus": 206,
                }
            )
    if scope in {"service", "full"}:
        checks.extend(_service_health_checks_for_target(target_name))
    if scope == "full":
        checks.extend(_full_scope_health_checks(target_name, public_bases, env_cfg))
    return checks


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
    for role_name in _expected_local_roles(target_name):
        if not role_name.endswith("-service"):
            continue
        port = canonical_port(manifest, str(profile_name), role_name)
        path = "/healthz"
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
                "url": f"{str(public_bases['api']).rstrip('/')}/v1/config/app",
            }
        )
        checks.extend(
            [
                {
                    "name": "content-feed",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/content/feed",
                },
                {
                    "name": "chat-contacts",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/chat/contacts",
                },
                {
                    "name": "app-messages-unread-count",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/app-messages/unread-count",
                },
                {
                    "name": "feed-intersections",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/v1/content/feed/intersections?limit=4&channel=recommend"
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
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/config/app",
                },
                {
                    "name": "gamma-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/content/feed?limit=1",
                },
                {
                    "name": "tag-shared-tags-smoke",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/v1/tag/shared-tags?objectAId=u1&objectAType=user&objectBId=u2&objectBType=user"
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
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/config/app",
                },
                {
                    "name": "prod-sim-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/content/feed?limit=1",
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
            "platform-ops-edge",
            "ops-portal",
            "media-edge",
            "media-origin",
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


def _replicas_for_step(step: str) -> int:
    stages = load_json_yaml(ROOT / "quwoquan_ops" / "environments" / "gray_rollout_stages.yaml")
    total = int((stages or {}).get("total_replicas", 2))
    try:
        numeric = int(step)
    except ValueError:
        return total
    replicas = max(1, numeric * total // 100)
    return min(replicas, total)


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
        "alpha-state": ROOT / ".qwq_output" / "local" / "alpha-local",
        "beta-state": ROOT / ".qwq_output" / "local" / "beta-local",
        "beta-manual": ROOT / ".qwq_output" / "local" / "app-beta-manual",
        "app-instances": ROOT / ".qwq_output" / "local" / "app-instances",
        "local-gamma": ROOT / ".qwq_output" / "local" / "gamma-local",
        "release-state": ROOT / ".qwq_output" / "local" / "release-state",
    }
    hits = []
    for name, path in candidates.items():
        if path.exists():
            hits.append({"name": name, "path": relpath(path)})
    extra: dict[str, Any] = {}
    if target_name == "prod-hosted":
        extra["prodReleaseState"] = _load_release_state("seed-box")
    return {"paths": hits, **extra}


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
    details = []
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        details.append(stdout.splitlines()[-1])
    if stderr:
        details.append(stderr.splitlines()[-1])
    if not details:
        details.append(f"exit={result.returncode}")
    return details


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
        "repair": command_repair,
        "roll": command_roll,
        "deploy": command_deploy,
    }
    payload = dispatch[args.command](args)
    return print_result(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())

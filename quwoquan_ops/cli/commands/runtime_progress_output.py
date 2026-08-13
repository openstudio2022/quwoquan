"""stackctl 运行时进度与输出基础设施: timing、受控值脱敏、live output、
启动日志 tail 与 summary bundle 写出。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
timing 家族、`_redact_controlled_values` / `_redact_controlled_payload`、
`_run_with_live_output`、`_tail_file_for_startup` /
`_tail_multiple_logs_for_startup` / `_tail_gamma_container_logs`、
`_app_launch_failure_detail`、`_local_runtime_log_root`、
`_write_summary_bundle` / `_write_stdout_markdown`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import codecs
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time

from pathlib import Path
from typing import Any


def _start_timing() -> tuple[float, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    return time.monotonic(), _stackctl.utc_now()


def _finish_timing(started_monotonic: float, started_at: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    return {
        "startedAt": started_at,
        "endedAt": _stackctl.utc_now(),
        "durationMs": int((time.monotonic() - started_monotonic) * 1000),
    }


def _remaining_deadline_seconds(deadline_epoch: int, label: str) -> float:
    remaining = float(deadline_epoch) - time.time()
    if remaining <= 0:
        raise RuntimeError(f"{label} deadline has been reached")
    return remaining


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
    import quwoquan_ops.cli.stackctl as _stackctl

    if _stackctl._is_interactive_terminal():
        print(message, flush=True)


def _format_stage_header(index: int, total: int, name: str) -> str:
    return f"[step {index}/{total}] {name}"


def _redact_controlled_values(text: str, values: tuple[str, ...]) -> str:
    redacted = text
    for value in sorted({item for item in values if len(item) >= 4}, key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


def _redact_controlled_payload(value: Any, values: tuple[str, ...]) -> Any:
    import quwoquan_ops.cli.stackctl as _stackctl

    if isinstance(value, str):
        return _stackctl._redact_controlled_values(value, values)
    if isinstance(value, list):
        return [_redact_controlled_payload(item, values) for item in value]
    if isinstance(value, dict):
        return {
            key: _redact_controlled_payload(item, values)
            for key, item in value.items()
        }
    return value


def _run_with_live_output(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    prefix: str = "",
    redaction_values: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    merged_env = os.environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)
    process = subprocess.Popen(
        argv,
        cwd=str(cwd or _stackctl.ROOT),
        env=merged_env,
        text=False,
        bufsize=0,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    chunks: list[bytes] = []
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    interactive = _stackctl._is_interactive_terminal()
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
            line = _stackctl._redact_controlled_values(line, redaction_values)
            if prefix:
                print(f"{prefix}{line}", end="", flush=True)
            else:
                print(line, end="", flush=True)
        if flush_partial and pending:
            pending = _stackctl._redact_controlled_values(pending, redaction_values)
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
    stdout = _stackctl._redact_controlled_values(
        b"".join(chunks).decode("utf-8", errors="replace"),
        redaction_values,
    )
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
    import quwoquan_ops.cli.stackctl as _stackctl

    emit_output = _stackctl._is_interactive_terminal()
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
        print(f"{prefix}tailing startup log: {_stackctl.relpath(log_path)}", flush=True)
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
    import quwoquan_ops.cli.stackctl as _stackctl

    if not _stackctl._is_interactive_terminal():
        return {"followed": False, "logs": [], "reason": "non-interactive"}
    existing_specs = [(label, path) for label, path in log_specs if path.exists()]
    if not existing_specs:
        return {"followed": False, "logs": [], "reason": "log-not-created"}

    for label, path in existing_specs:
        print(f"[{label}] tailing startup log: {_stackctl.relpath(path)}", flush=True)

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
                "path": _stackctl.relpath(path),
                "lines": line_counts[label],
            }
            for label, path in existing_specs
        ],
        "reason": reason,
    }


def _tail_gamma_container_logs() -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if not _stackctl._is_interactive_terminal():
        return {"followed": False, "reason": "non-interactive", "backend": ""}

    compose_files = _stackctl.gamma_compose_files(_stackctl.ROOT)
    if any(not compose_file.exists() for compose_file in compose_files):
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
                result = _stackctl._tail_multiple_logs_for_startup(
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

    # candidate topology 投影后一方服务收敛为 service-core;`docker compose logs`
    # 对任一未知服务名整体拒绝执行,必须先以 config --services 过滤实际存在的服务。
    desired_services = [
        "gamma-proxy",
        "service-core",
        "recommendation-service",
        "product-ops-service",
        "platform-ops-service",
        "realtime-gateway",
        "rtc-service",
        "content-service",
        "assistant-service",
        "user-service",
        "chat-service",
        "integration-service",
        "notification-service",
    ]
    config_result = subprocess.run(
        ["docker", "compose", *_stackctl.compose_file_args(compose_files), "config", "--services"],
        cwd=str(_stackctl.ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    available_services = {
        line.strip()
        for line in (config_result.stdout or "").splitlines()
        if line.strip()
    }
    if available_services:
        services = [service for service in desired_services if service in available_services]
    else:
        services = desired_services
    if not services:
        return {"followed": False, "reason": "no-compose-services", "backend": "docker"}
    with tempfile.TemporaryDirectory(prefix="gamma-tail-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        log_paths = [(f"gamma-{service}", tmp_root / f"{service}.log") for service in services]
        handles = {label: path.open("w", encoding="utf-8") for label, path in log_paths}
        process = subprocess.Popen(
            [
                "docker",
                "compose",
                *_stackctl.compose_file_args(compose_files),
                "logs",
                "-f",
                "--tail",
                "40",
                *services,
            ],
            cwd=str(_stackctl.ROOT),
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
            result = _stackctl._tail_multiple_logs_for_startup(
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
    import quwoquan_ops.cli.stackctl as _stackctl

    state_name = "content-release.json" if target == "alpha-local" else "local_run.json"
    state_path = _stackctl.target_process_dir(target) / state_name
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
    import quwoquan_ops.cli.stackctl as _stackctl

    payload = {
        "command": command,
        "target": target,
        "status": status,
        "summary": summary,
        "details": details,
        "generatedAt": _stackctl.utc_now(),
    }
    if timing:
        payload.update(timing)
    if extra:
        payload.update(extra)
    _stackctl.write_json(report_dir / "summary.json", payload)
    env_name = _stackctl.env_from_report_dir(report_dir, target)
    run_id = _stackctl.run_id_from_report_dir(report_dir)
    obs_dir = _stackctl.observability_run_dir(env_name, run_id)
    _stackctl.write_run_manifest(
        obs_dir,
        env_name=env_name,
        run_id=run_id,
        command=command,
        target=target,
        report_dir=report_dir,
    )
    _stackctl.append_log_line(
        obs_dir / "logs" / "ci" / "stackctl" / "deploy.log",
        {
            "occurredAt": payload["generatedAt"],
            "severity": "ERROR" if status in {"failed", "gate_block"} else "INFO",
            "step": command,
            "result": status,
            "message": summary,
        },
    )
    _stackctl.write_stackctl_links(
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
                f"- duration: `{_stackctl._format_duration_ms(int(timing.get('durationMs', 0) or 0))}`",
            ]
        )
    _stackctl.write_markdown(
        report_dir / "summary.md",
        "\n".join(summary_lines + [*[f"- {line}" for line in details]]),
    )


def _write_stdout_markdown(report_dir: Path, sections: list[tuple[str, str]]) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    lines: list[str] = ["# stackctl stdout", ""]
    for title, content in sections:
        if not content.strip():
            continue
        lines.extend([f"## {title}", "", "```text", content.rstrip(), "```", ""])
    _stackctl.write_markdown(report_dir / "stdout.md", "\n".join(lines))

"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from core.cursor_credentials import cursor_safe_subprocess_env
from core.cursor_model import CursorModelSelection
from core.runtime_policy import active_runtime_policy

from content.execution.support import (
    _MANAGED_AGENT_SUBPROCESS_LOCK,
    _MANAGED_AGENT_SUBPROCESS_PIDS,
    MANAGED_AGENT_TIMEOUT_SECONDS,
    Callable,
    ExecutionContext,
    Path,
    _normalize_managed_agent_provider,
    _resolve_managed_model,
    json,
    os,
    signal,
    subprocess,
    sys,
    tempfile,
    time,
)

if TYPE_CHECKING:
    from content.execution.agent.outcome import AgentRunOutcome

_PROCESS_TERMINATION_TIMEOUT_SECONDS = active_runtime_policy().process_termination_timeout_seconds

def _managed_agent_worker_main() -> None:
    """Subprocess entrypoint for one real semantic-agent job.
    Parent orchestration cannot cancel a thread blocked inside Agent.prompt, so
    production managed runs execute each SDK call in a short-lived subprocess.
    Fake test runners still bypass this path through ctx.agent_runner.
    """
    from content.execution.agent.agent_runner import _managed_agent_runner_for_provider
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    ctx_payload = payload.get("ctx") or {}
    raw_provider = str(ctx_payload.get("agentProvider") or "").strip()
    if not raw_provider:
        raise ValueError("agent_worker.ctx.agentProvider is required")
    semantic_role = str(ctx_payload.get("semanticRole") or "").strip()
    if not semantic_role:
        raise ValueError("agent_worker.ctx.semanticRole is required")
    agent_provider = _normalize_managed_agent_provider(raw_provider)
    model_selection = CursorModelSelection.from_config(
        ctx_payload.get("model"),
        ctx_payload.get("modelParameters"),
        label="agent_worker.ctx",
    )
    ctx = ExecutionContext(
        execution_id=str(ctx_payload.get("executionId") or ""),
        entity_ids=[str(item) for item in (ctx_payload.get("entityIds") or [])],
        spec=ctx_payload.get("spec") or {},
        managed=True,
        runtime=str(ctx_payload.get("runtime") or "local"),
        max_workers=(
            int(ctx_payload["maxWorkers"])
            if ctx_payload.get("maxWorkers") is not None
            else None
        ),
        model=_resolve_managed_model(agent_provider, model_selection.model_id),
        model_parameters=model_selection.parameters,
        agent_provider=agent_provider,
        semantic_role=semantic_role,
        semantic_max_attempts=(
            int(ctx_payload["semanticMaxAttempts"])
            if ctx_payload.get("semanticMaxAttempts") is not None
            else None
        ),
        release_only=bool(ctx_payload.get("releaseOnly")),
    )
    outcome = _managed_agent_runner_for_provider(ctx, str(payload.get("prompt") or ""))
    output_path.write_text(
        json.dumps(outcome.to_document(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _source_review_agent_worker_main() -> None:
    """Subprocess entrypoint for a source-scoped review without an execution ID."""
    from content.execution.agent.agent_runner import _default_managed_agent_runner

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    model_selection = CursorModelSelection.from_config(
        payload.get("model"),
        payload.get("modelParameters"),
        label="source_review_agent_worker",
    )
    context = SimpleNamespace(
        runtime=str(payload.get("runtime") or "local"),
        model_selection=model_selection,
        agent_provider="cursor_sdk",
    )
    outcome = _default_managed_agent_runner(
        context,
        str(payload.get("prompt") or ""),
    )
    output_path.write_text(
        json.dumps(outcome.to_document(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_source_review_agent_isolated(
    *,
    runtime: object,
    model_selection: CursorModelSelection,
    prompt: str,
    timeout_seconds: float | None = None,
) -> "AgentRunOutcome":
    """Run one source review with visible progress and a killable hard deadline."""
    from core.control_types import AgentFailureKind, AgentProvider

    from content.execution.agent.agent_runner import _redact_managed_secret
    from content.execution.agent.outcome import AgentRunOutcome

    timeout = float(
        active_runtime_policy().agent_timeout_seconds
        if timeout_seconds is None
        else timeout_seconds
    )
    if timeout <= 0:
        raise ValueError("source review timeout must be positive")
    heartbeat_seconds = min(15.0, max(1.0, timeout / 4.0))
    with tempfile.TemporaryDirectory(prefix="qwq-source-review-") as tmp:
        temp_root = Path(tmp)
        input_path = temp_root / "input.json"
        output_path = temp_root / "output.json"
        input_path.write_text(
            json.dumps(
                {
                    "runtime": str(runtime),
                    "model": model_selection.model_id,
                    "modelParameters": model_selection.parameters_document(),
                    "prompt": prompt,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        scripts_dir = str(Path(__file__).resolve().parents[3])
        env = cursor_safe_subprocess_env(os.environ)
        env["PYTHONPATH"] = (
            scripts_dir
            if not env.get("PYTHONPATH")
            else scripts_dir + os.pathsep + str(env.get("PYTHONPATH"))
        )
        try:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "from content.execution.agent.agent_worker import "
                        "_source_review_agent_worker_main; _source_review_agent_worker_main()"
                    ),
                    str(input_path),
                    str(output_path),
                ],
                cwd=str(Path.cwd()),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as exc:
            return AgentRunOutcome.failed(
                AgentFailureKind.SUBPROCESS_EXITED,
                provider=AgentProvider.CURSOR_SDK,
                message=f"source review subprocess failed to start: {type(exc).__name__}",
                retryable=True,
                error_code="semantic_provider_startup_failed",
            )
        _register_managed_agent_subprocess(proc.pid)
        print(
            f"[source-review] started pid={proc.pid} deadlineSeconds={timeout:g}",
            file=sys.stderr,
            flush=True,
        )
        try:
            started_at = time.monotonic()
            next_heartbeat = started_at + heartbeat_seconds
            while proc.poll() is None:
                now = time.monotonic()
                elapsed = now - started_at
                if elapsed >= timeout:
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except OSError:
                        pass
                    try:
                        stdout, stderr = proc.communicate(
                            timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS
                        )
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except OSError:
                            pass
                        stdout, stderr = proc.communicate()
                    print(
                        f"[source-review] timed out after {timeout:g}s; bridge cleanup requested",
                        file=sys.stderr,
                        flush=True,
                    )
                    return AgentRunOutcome.failed(
                        AgentFailureKind.SUBPROCESS_TIMEOUT,
                        provider=AgentProvider.CURSOR_SDK,
                        message=f"source review subprocess timed out after {timeout:g}s",
                        started=True,
                        retryable=True,
                        error_code="semantic_provider_transport_timeout",
                        duration_ms=int(elapsed * 1000),
                        stdout_tail=_redact_managed_secret(stdout)[-1200:],
                        stderr_tail=_redact_managed_secret(stderr)[-1200:],
                    )
                if now >= next_heartbeat:
                    print(
                        f"[source-review] heartbeat elapsedSeconds={int(elapsed)}",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_heartbeat = now + heartbeat_seconds
                time.sleep(min(1.0, max(0.05, timeout - elapsed)))
            stdout, stderr = proc.communicate()
            if not output_path.is_file():
                return AgentRunOutcome.failed(
                    AgentFailureKind.SUBPROCESS_EXITED,
                    provider=AgentProvider.CURSOR_SDK,
                    message=(
                        f"source review subprocess exited {proc.returncode} without outcome; "
                        f"stderr={_redact_managed_secret(stderr)[-1200:]}"
                    ),
                    started=True,
                    retryable=proc.returncode != 0,
                    stdout_tail=_redact_managed_secret(stdout)[-1200:],
                    stderr_tail=_redact_managed_secret(stderr)[-1200:],
                )
            try:
                return AgentRunOutcome.from_document(
                    json.loads(output_path.read_text(encoding="utf-8")),
                    label="source review subprocess outcome",
                )
            except (OSError, TypeError, ValueError) as exc:
                return AgentRunOutcome.failed(
                    AgentFailureKind.SUBPROCESS_OUTPUT_INVALID,
                    provider=AgentProvider.CURSOR_SDK,
                    message=f"source review subprocess wrote invalid output: {type(exc).__name__}",
                    started=True,
                    retryable=True,
                    stdout_tail=_redact_managed_secret(stdout)[-1200:],
                    stderr_tail=_redact_managed_secret(stderr)[-1200:],
                )
        finally:
            _unregister_managed_agent_subprocess(proc.pid)


def _register_managed_agent_subprocess(pid: int) -> None:
    if pid <= 0:
        return
    with _MANAGED_AGENT_SUBPROCESS_LOCK:
        _MANAGED_AGENT_SUBPROCESS_PIDS.add(pid)

def _unregister_managed_agent_subprocess(pid: int) -> None:
    if pid <= 0:
        return
    with _MANAGED_AGENT_SUBPROCESS_LOCK:
        _MANAGED_AGENT_SUBPROCESS_PIDS.discard(pid)

def _terminate_managed_agent_subprocesses() -> list[int]:
    with _MANAGED_AGENT_SUBPROCESS_LOCK:
        pids = sorted(_MANAGED_AGENT_SUBPROCESS_PIDS)
        _MANAGED_AGENT_SUBPROCESS_PIDS.clear()
    for pid in pids:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + 3.0
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        for pid in list(remaining):
            try:
                os.kill(pid, 0)
            except OSError:
                remaining.discard(pid)
        if remaining:
            time.sleep(0.2)
    for pid in list(remaining):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    return pids

def _default_managed_agent_runner_isolated(
    ctx: ExecutionContext,
    prompt: str,
    *,
    completion_probe: Callable[[], bool] | None = None,
    completion_grace_seconds: float = 0,
) -> "AgentRunOutcome":
    """Run one provider adapter in a killable subprocess with a hard deadline."""
    from core.control_types import AgentFailureKind, AgentProvider

    from content.execution.agent.agent_runner import _redact_managed_secret
    from content.execution.agent.outcome import AgentRunOutcome
    from content.execution.workspace import execution_root

    provider = ctx.agent_provider
    if not isinstance(provider, AgentProvider):
        provider = AgentProvider(str(provider))

    agent_workspace = execution_root(ctx.execution_id)
    agent_workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qwq-managed-agent-") as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.json"
        output_path = tmp_path / "output.json"
        input_path.write_text(
            json.dumps(
                {
                    "ctx": {
                        "executionId": ctx.execution_id,
                        "entityIds": ctx.entity_ids,
                        "spec": ctx.spec.to_dict(),
                        "runtime": ctx.runtime,
                        "maxWorkers": ctx.max_workers,
                        "model": ctx.model,
                        "modelParameters": ctx.model_selection.parameters_document(),
                        "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
                        "semanticRole": ctx.semantic_role,
                        "semanticMaxAttempts": ctx.semantic_max_attempts,
                        "releaseOnly": ctx.release_only,
                    },
                    "prompt": prompt,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        scripts_dir = str(Path(__file__).resolve().parents[3])
        env = cursor_safe_subprocess_env(os.environ)
        env["PYTHONPATH"] = (
            scripts_dir
            if not env.get("PYTHONPATH")
            else scripts_dir + os.pathsep + str(env.get("PYTHONPATH"))
        )
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "from content.execution.agent.agent_worker import _managed_agent_worker_main; "
                    "_managed_agent_worker_main()"
                ),
                str(input_path),
                str(output_path),
                "--execution-id",
                str(ctx.execution_id),
            ],
            # Agent 的工具视野只落在本 execution 工作包；源码 clone 只负责
            # 运行受版本控制的控制器，绝不能成为 Agent 可写 workspace。
            cwd=str(agent_workspace),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        _register_managed_agent_subprocess(proc.pid)
        try:
            started_at = time.monotonic()
            completion_seen_at: float | None = None
            while proc.poll() is None:
                now = time.monotonic()
                if completion_probe is not None and completion_probe():
                    completion_seen_at = completion_seen_at or now
                    if now - completion_seen_at >= max(0.0, completion_grace_seconds):
                        try:
                            os.killpg(proc.pid, signal.SIGTERM)
                        except OSError:
                            pass
                        try:
                            stdout, stderr = proc.communicate(
                                timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS
                            )
                        except subprocess.TimeoutExpired:
                            try:
                                os.killpg(proc.pid, signal.SIGKILL)
                            except OSError:
                                pass
                            stdout, stderr = proc.communicate()
                        return AgentRunOutcome.finished(
                            provider=provider,
                            run_id=f"contract-output:{ctx.execution_id}",
                            completion_mode="contract_output",
                            stdout_tail=_redact_managed_secret(stdout)[-1200:],
                            stderr_tail=_redact_managed_secret(stderr)[-1200:],
                        )
                else:
                    completion_seen_at = None
                if now - started_at >= MANAGED_AGENT_TIMEOUT_SECONDS:
                    break
                time.sleep(1)
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
                try:
                    stdout, stderr = proc.communicate(
                        timeout=_PROCESS_TERMINATION_TIMEOUT_SECONDS
                    )
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except OSError:
                        pass
                    stdout, stderr = proc.communicate()
                return AgentRunOutcome.failed(
                    AgentFailureKind.SUBPROCESS_TIMEOUT,
                    provider=provider,
                    message=f"agent subprocess timed out after {MANAGED_AGENT_TIMEOUT_SECONDS}s",
                    retryable=True,
                    stdout_tail=_redact_managed_secret(stdout)[-1200:],
                    stderr_tail=_redact_managed_secret(stderr)[-1200:],
                )
            else:
                stdout, stderr = proc.communicate()
            if output_path.is_file():
                try:
                    outcome = json.loads(output_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError) as exc:
                    return AgentRunOutcome.failed(
                        AgentFailureKind.SUBPROCESS_OUTPUT_INVALID,
                        provider=provider,
                        message=f"agent subprocess wrote unreadable output: {type(exc).__name__}",
                        retryable=True,
                    )
                try:
                    decoded = AgentRunOutcome.from_document(outcome)
                except ValueError as exc:
                    return AgentRunOutcome.failed(
                        AgentFailureKind.SUBPROCESS_OUTPUT_INVALID,
                        provider=provider,
                        message=f"agent subprocess wrote invalid output: {exc}",
                        retryable=True,
                    )
                return decoded
            return AgentRunOutcome.failed(
                AgentFailureKind.SUBPROCESS_EXITED,
                provider=provider,
                message=(
                    f"agent subprocess exited {proc.returncode} without outcome; "
                    f"stderr={_redact_managed_secret(stderr)[-1200:]}"
                ),
                retryable=proc.returncode != 0,
                stdout_tail=_redact_managed_secret(stdout)[-1200:],
            )
        finally:
            _unregister_managed_agent_subprocess(proc.pid)

def _child_pids(pid: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "ppid="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return []
    children: list[int] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            child_pid = int(parts[0])
            parent_pid = int(parts[1])
        except ValueError:
            continue
        if parent_pid == pid:
            children.append(child_pid)
    return children

def _terminate_pid_tree_if_alive(pid: int) -> None:
    """Best-effort cleanup for Cursor bridge shell/node children."""
    seen: set[int] = set()
    def _walk(target: int) -> list[int]:
        if target in seen:
            return []
        seen.add(target)
        descendants: list[int] = []
        for child in _child_pids(target):
            descendants.extend(_walk(child))
            descendants.append(child)
        return descendants
    for child_pid in _walk(pid):
        _terminate_pid_if_alive(child_pid)
    _terminate_pid_if_alive(pid)

def _terminate_pid_if_alive(pid: int) -> None:
    """Best-effort cleanup for one process."""
    if pid <= 0:
        return
    try:
        os.kill(pid, 0)
    except OSError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except OSError:
            return
        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except OSError:
            return

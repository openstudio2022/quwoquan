"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
from content.execution.support import Any, Callable, ExecutionContext, MANAGED_AGENT_TIMEOUT_SECONDS, Path, _MANAGED_AGENT_SUBPROCESS_LOCK, _MANAGED_AGENT_SUBPROCESS_PIDS, _normalize_managed_agent_provider, _resolve_managed_model, json, os, signal, subprocess, sys, tempfile, time

_PROCESS_TERMINATION_TIMEOUT_SECONDS = active_runtime_policy().process_termination_timeout_seconds

def _managed_agent_worker_main() -> None:
    """Subprocess entrypoint for one real Cursor job.
    Parent orchestration cannot cancel a thread blocked inside Agent.prompt, so
    production managed runs execute each SDK call in a short-lived subprocess.
    Fake test runners still bypass this path through ctx.agent_runner.
    """
    from content.execution.agent.agent_runner import _managed_agent_runner_for_provider
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    ctx_payload = payload.get("ctx") or {}
    agent_provider = _normalize_managed_agent_provider(
        str(ctx_payload.get("agentProvider") or "cursor_sdk")
    )
    ctx = ExecutionContext(
        execution_id=str(ctx_payload.get("executionId") or ""),
        entity_ids=[str(item) for item in (ctx_payload.get("entityIds") or [])],
        spec=ctx_payload.get("spec") or {},
        managed=True,
        runtime=str(ctx_payload.get("runtime") or "local"),
        max_workers=int(ctx_payload.get("maxWorkers") or 1),
        model=_resolve_managed_model(agent_provider, str(ctx_payload.get("model") or "")),
        agent_provider=agent_provider,
        release_only=bool(ctx_payload.get("releaseOnly")),
    )
    outcome = _managed_agent_runner_for_provider(ctx, str(payload.get("prompt") or ""))
    output_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")

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
) -> dict[str, Any]:
    """Run the real Cursor SDK worker in a killable subprocess with a hard deadline."""
    from content.execution.agent.agent_runner import _redact_managed_secret
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
                        "spec": ctx.spec,
                        "runtime": ctx.runtime,
                        "maxWorkers": ctx.max_workers,
                        "model": ctx.model,
                        "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
                        "releaseOnly": ctx.release_only,
                    },
                    "prompt": prompt,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        scripts_dir = str(Path(__file__).resolve().parents[3])
        env = os.environ.copy()
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
            cwd=str(Path.cwd()),
            env=env,
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
                        return {
                            "started": True,
                            "status": "finished",
                            "runId": f"contract-output:{ctx.execution_id}",
                            "completionMode": "contract_output",
                            "usedTokens": 0,
                            "costUsd": 0.0,
                            "stdoutTail": _redact_managed_secret(stdout)[-1200:],
                            "stderrTail": _redact_managed_secret(stderr)[-1200:],
                        }
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
                return {
                    "started": False,
                    "status": "error",
                    "error": f"agent subprocess timed out after {MANAGED_AGENT_TIMEOUT_SECONDS}s",
                    "retryable": True,
                    "errorType": "timeout",
                    "stdoutTail": _redact_managed_secret(stdout)[-1200:],
                    "stderrTail": _redact_managed_secret(stderr)[-1200:],
                }
            else:
                stdout, stderr = proc.communicate()
            if output_path.is_file():
                try:
                    outcome = json.loads(output_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError) as exc:
                    return {
                        "started": False,
                        "status": "error",
                        "error": f"agent subprocess wrote unreadable output: {exc}",
                        "retryable": True,
                    }
                if isinstance(outcome, dict):
                    if outcome.get("error"):
                        outcome["error"] = _redact_managed_secret(str(outcome.get("error") or ""))
                    return outcome
            return {
                "started": False,
                "status": "error",
                "error": (
                    f"agent subprocess exited {proc.returncode} without outcome; "
                    f"stderr={_redact_managed_secret(stderr)[-1200:]}"
                ),
                "retryable": proc.returncode not in (0,),
                "stdoutTail": _redact_managed_secret(stdout)[-1200:],
            }
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

"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
import sys
from content.execution.support import Any, ExecutionContext, MANAGED_AGENT_TIMEOUT_SECONDS, Path, _CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, _CURSOR_BRIDGE_READY_DELAY_SECONDS, _normalize_managed_agent_provider, aggregate_turn_usage, contextmanager, extract_cursor_usage, hashlib, is_cursor_auth_error, json, load_workflow_state, os, re, resolve_cursor_api_key, save_workflow_state, shutil, signal, store, subprocess, tempfile, time

_CURSOR_BRIDGE_MAX_RETRIES = active_runtime_policy().cursor_bridge_max_retries
_PROCESS_TERMINATION_TIMEOUT_SECONDS = active_runtime_policy().process_termination_timeout_seconds

def _managed_local_workspace_lock_path(workspace: str) -> Path:
    digest = hashlib.sha256(workspace.encode("utf-8")).hexdigest()[:16]
    root = Path(os.environ.get("QWQ_MANAGED_LOCAL_LOCK_DIR", tempfile.gettempdir()))
    return root / f"qwq-managed-local-{digest}.lock"

@contextmanager
def _managed_local_workspace_guard(ctx: ExecutionContext):
    from content.execution.agent.agent_conflicts import _cleanup_managed_local_workspace_conflicts, _cross_task_managed_data_cli_conflicts, _managed_local_workspace_conflicts, _managed_workspace_conflicts_for_provider
    if not ctx.managed or str(ctx.runtime) != "local":
        yield
        return
    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        yield
        return
    workspace = str(Path.cwd())
    lock_path = _managed_local_workspace_lock_path(workspace)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.seek(0)
            owner = lock_file.read().strip()
            raise RuntimeError(
                "another managed-local workflow is already running in this workspace"
                + (f" ({owner})" if owner else "")
            ) from exc
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "executionId": ctx.execution_id,
                    "startedAt": store.now_iso(),
                },
                ensure_ascii=False,
            )
        )
        lock_file.flush()
        try:
            conflicts = _managed_workspace_conflicts_for_provider(
                _managed_local_workspace_conflicts(Path.cwd()),
                ctx.agent_provider,
            )
            if conflicts and ctx.force_clean_workspace_agent_state:
                cross_task_conflicts = _cross_task_managed_data_cli_conflicts(
                    conflicts,
                    execution_id=ctx.execution_id,
                )
                cleanup_reports: list[dict[str, Any]] = []
                if cross_task_conflicts:
                    observed_report = {
                        "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
                        "mode": "force_clean_workspace_agent_state_observed_cross_task_after_lock",
                        "requestedConflictCount": len(conflicts),
                        "crossTaskConflictCount": len(cross_task_conflicts),
                        "conflicts": cross_task_conflicts[:20],
                    }
                    cleanup_reports.append(observed_report)
                    cross_task_pids = {
                        int(item.get("pid") or 0) for item in cross_task_conflicts
                    }
                    conflicts = [
                        item for item in conflicts
                        if int(item.get("pid") or 0) not in cross_task_pids
                    ]
                if conflicts:
                    cleanup_report = _cleanup_managed_local_workspace_conflicts(conflicts)
                    cleanup_reports.append(cleanup_report)
                    conflicts = _managed_workspace_conflicts_for_provider(
                        _managed_local_workspace_conflicts(Path.cwd()),
                        ctx.agent_provider,
                    )
                    if cross_task_conflicts:
                        cross_task_pids = {
                            int(item.get("pid") or 0) for item in cross_task_conflicts
                        }
                        conflicts = [
                            item for item in conflicts
                            if int(item.get("pid") or 0) not in cross_task_pids
                        ]
                state = load_workflow_state(ctx.execution_id)
                reports = state.setdefault("workspaceCleanupReports", [])
                if isinstance(reports, list):
                    reports.extend(cleanup_reports)
                    state["workspaceCleanupReports"] = reports[-20:]
                    state["heartbeatAt"] = store.now_iso()
                    save_workflow_state(state)
            if conflicts:
                rendered = "; ".join(
                    f"{item.get('kind')} pid={item.get('pid')} pgid={item.get('pgid')} "
                    f"cmd={_redact_managed_secret(str(item.get('command') or ''))[:220]}"
                    for item in conflicts[:8]
                )
                raise RuntimeError(
                    "managed local workspace conflicts appeared after acquiring lock: "
                    + rendered
                )
            yield
        finally:
            lock_file.seek(0)
            lock_file.truncate()
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

def _terminate_workspace_cursor_bridges(workspace: Path) -> None:
    """Best-effort cleanup for half-started Cursor SDK bridges in this workspace."""
    from content.execution.agent.agent_worker import _terminate_pid_tree_if_alive
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return
    workspace_text = str(workspace)
    current_pid = os.getpid()
    for line in proc.stdout.splitlines():
        if "cursor-sdk-bridge" not in line or workspace_text not in line:
            continue
        parts = line.strip().split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid <= 0 or pid == current_pid:
            continue
        _terminate_pid_tree_if_alive(pid)

def _prompt_cursor_agent_capturing_usage(
    agent_cls: Any,
    prompt: str,
    agent_options: Any,
    *,
    client: Any,
) -> tuple[Any, list[dict[str, Any]]]:
    """`Agent.prompt` 等价实现，同时消费事件流捕获 `turn-ended` usage。
    本地 bridge 不会把 usage 回填到终态 ``RunResult``；authoritative token
    用量只出现在流式 ``turn-ended`` interaction update 上。这里在等待终态的
    同时收集全部 turn usage，供 TokenLedger 使用 authoritative 计量。
    """
    agent = agent_cls.create(agent_options, client=client)
    try:
        run = agent.send(prompt)
        turn_usages: list[dict[str, Any]] = []
        for event in run.events():
            update = getattr(event, "interaction_update", None)
            if update is not None and getattr(update, "type", "") == "turn-ended":
                usage = getattr(update, "usage", None)
                if usage:
                    turn_usages.append(dict(usage))
        result = run.wait()
        return result, turn_usages
    finally:
        agent.close()

def _default_managed_agent_runner(ctx: ExecutionContext, prompt: str) -> dict[str, Any]:
    """在当前 workspace 启动 Cursor Agent；只返回终态，推进由父进程校验。"""
    from content.execution.agent.agent_worker import _terminate_pid_tree_if_alive
    from content.execution.pipeline.preflight import _cursor_bridge_error_is_retryable, _cursor_bridge_launch_guard, _patch_cursor_sdk_tool_callback_token
    from content.execution.recovery.stage_reset import _managed_uses_serial_local_cursor
    try:
        from cursor_sdk import (  # type: ignore
            Agent,
            AgentOptions,
            CloudAgentOptions,
            Client,
            CursorAgentError,
            LocalAgentOptions,
        )
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "status": "error", "error": f"cursor_sdk unavailable: {exc}"}
    # 每次 agent 调用前只从受限 key file reload；SDK 所需环境变量仅作
    # 当前进程内传递，不是配置来源，也不得写入运行证据。
    key = resolve_cursor_api_key()
    if not key:
        return {
            "started": False,
            "status": "error",
            "error": "cursor API key file missing or invalid",
        }
    _patch_cursor_sdk_tool_callback_token()
    result = None
    turn_usages: list[dict[str, Any]] = []
    last_error: dict[str, Any] | None = None
    workspace = Path.cwd()
    auth_reload_used = False
    for attempt in range(3):
        client = None
        bridge_pids: list[int] = []
        bridge_retry_requested = False
        try:
            if attempt > 0 and _managed_uses_serial_local_cursor(ctx):
                _terminate_workspace_cursor_bridges(workspace)
            with _cursor_bridge_launch_guard():
                client = Client.launch_bridge(
                    workspace=str(workspace),
                    max_retries=_CURSOR_BRIDGE_MAX_RETRIES,
                    # resolve_cursor_api_key 已从唯一 key file 写入当前进程；
                    # bridge 只能继承该瞬时值，不能读取第二配置源。
                    allow_api_key_env_fallback=True,
                )
            owned_bridge = getattr(client, "_owned_bridge", None)
            endpoint = getattr(owned_bridge, "endpoint", None)
            process = getattr(owned_bridge, "process", None)
            for pid in (
                getattr(process, "pid", None),
                getattr(endpoint, "pid", None),
            ):
                if isinstance(pid, int) and pid > 0 and pid not in bridge_pids:
                    bridge_pids.append(pid)
            if _CURSOR_BRIDGE_READY_DELAY_SECONDS:
                time.sleep(_CURSOR_BRIDGE_READY_DELAY_SECONDS)
            if str(ctx.runtime) == "cloud":
                agent_options = AgentOptions(
                    api_key=key,
                    model=ctx.model,
                    cloud=CloudAgentOptions(repos=[]),
                )
            else:
                agent_options = AgentOptions(
                    api_key=key,
                    model=ctx.model,
                    local=LocalAgentOptions(cwd=str(Path.cwd())),
                )
            warm_attempts = active_runtime_policy().cursor_warm_attempts
            for warm_attempt in range(warm_attempts):
                try:
                    result, turn_usages = _prompt_cursor_agent_capturing_usage(
                        Agent, prompt, agent_options, client=client
                    )
                    break
                except CursorAgentError as exc:
                    message = getattr(exc, "message", str(exc))
                    if is_cursor_auth_error(
                        message,
                        code=str(getattr(exc, "code", "") or ""),
                        status=getattr(exc, "status", None),
                    ):
                        reloaded = resolve_cursor_api_key()
                        if not auth_reload_used and reloaded and reloaded != key:
                            auth_reload_used = True
                            key = reloaded
                            bridge_retry_requested = True
                            break
                        return {
                            "started": False,
                            "status": "error",
                            "error": f"cursor credential invalid (auth): {message}",
                            "retryable": False,
                            "authFailure": True,
                            "errorCode": getattr(exc, "code", None),
                            "requestId": getattr(exc, "request_id", None),
                            "attempts": attempt + 1,
                        }
                    retryable_bridge = _cursor_bridge_error_is_retryable(
                        message,
                        code=str(getattr(exc, "code", "") or ""),
                        explicit_retryable=bool(getattr(exc, "is_retryable", False)),
                    )
                    last_error = {
                        "started": False,
                        "status": "error",
                        "error": message,
                        "retryable": retryable_bridge,
                        "errorCode": getattr(exc, "code", None),
                        "requestId": getattr(exc, "request_id", None),
                        "attempts": attempt + 1,
                        "warmAttempts": warm_attempt + 1,
                    }
                    if retryable_bridge and warm_attempt + 1 < warm_attempts:
                        time.sleep(2)
                        continue
                    if attempt < 2 and retryable_bridge:
                        bridge_retry_requested = True
                        break
                    return last_error
                except RuntimeError as exc:
                    message = f"{type(exc).__name__}: {exc}"
                    lowered = message.casefold()
                    retryable_bridge = (
                        "client has been closed" in lowered
                        or _cursor_bridge_error_is_retryable(message)
                    )
                    last_error = {
                        "started": False,
                        "status": "error",
                        "error": message,
                        "retryable": retryable_bridge,
                        "attempts": attempt + 1,
                        "warmAttempts": warm_attempt + 1,
                    }
                    if retryable_bridge and warm_attempt + 1 < warm_attempts:
                        time.sleep(2)
                        continue
                    if attempt < 2 and retryable_bridge:
                        bridge_retry_requested = True
                        break
                    return last_error
                except Exception as exc:  # noqa: BLE001
                    message = f"{type(exc).__name__}: {exc}"
                    retryable_bridge = _cursor_bridge_error_is_retryable(message)
                    last_error = {
                        "started": False,
                        "status": "error",
                        "error": message,
                        "retryable": retryable_bridge,
                        "attempts": attempt + 1,
                        "warmAttempts": warm_attempt + 1,
                    }
                    if retryable_bridge and warm_attempt + 1 < warm_attempts:
                        time.sleep(2)
                        continue
                    if attempt < 2 and retryable_bridge:
                        bridge_retry_requested = True
                        break
                    return last_error
            if result is not None:
                break
            if bridge_retry_requested:
                if _managed_uses_serial_local_cursor(ctx):
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error or {
                "started": False,
                "status": "error",
                "error": "Cursor SDK returned no result",
                "retryable": False,
                "attempts": attempt + 1,
            }
        except CursorAgentError as exc:
            message = getattr(exc, "message", str(exc))
            # 凭据失效（轮换/过期/plan_required/401/403）单独分流：不计 retryable bridge 预算，
            # 而是 reload key + 重建 bridge 重试一次；reload 后仍失败才上报"凭据失效"。
            if is_cursor_auth_error(
                message,
                code=str(getattr(exc, "code", "") or ""),
                status=getattr(exc, "status", None),
            ):
                reloaded = resolve_cursor_api_key()
                if not auth_reload_used and reloaded and reloaded != key:
                    auth_reload_used = True
                    key = reloaded
                    _terminate_workspace_cursor_bridges(workspace)
                    time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0))
                    continue
                return {
                    "started": False,
                    "status": "error",
                    "error": f"cursor credential invalid (auth): {message}",
                    "retryable": False,
                    "authFailure": True,
                    "errorCode": getattr(exc, "code", None),
                    "requestId": getattr(exc, "request_id", None),
                    "attempts": attempt + 1,
                }
            retryable_bridge = _cursor_bridge_error_is_retryable(
                message,
                code=str(getattr(exc, "code", "") or ""),
                explicit_retryable=bool(getattr(exc, "is_retryable", False)),
            )
            last_error = {
                "started": False,
                "status": "error",
                "error": message,
                "retryable": retryable_bridge,
                "errorCode": getattr(exc, "code", None),
                "requestId": getattr(exc, "request_id", None),
                    "attempts": attempt + 1,
                }
            if attempt < 2 and retryable_bridge:
                if _managed_uses_serial_local_cursor(ctx):
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error
        except RuntimeError as exc:
            message = f"{type(exc).__name__}: {exc}"
            lowered = message.casefold()
            retryable_bridge = (
                "client has been closed" in lowered
                or _cursor_bridge_error_is_retryable(message)
            )
            last_error = {
                "started": False,
                "status": "error",
                "error": message,
                "retryable": retryable_bridge,
                "attempts": attempt + 1,
            }
            if attempt < 2 and retryable_bridge:
                if _managed_uses_serial_local_cursor(ctx):
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error
        except Exception as exc:  # noqa: BLE001
            last_error = {
                "started": False,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "retryable": False,
                "attempts": attempt + 1,
            }
            return last_error
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"[cursor-agent] client close failed: {type(exc).__name__}",
                        file=sys.stderr,
                    )
            for pid in bridge_pids:
                _terminate_pid_tree_if_alive(pid)
    if result is None:
        return last_error or {
            "started": False,
            "status": "error",
            "error": "Cursor isolated bridge retry exhausted without a run result",
            "retryable": True,
        }
    status = str(getattr(result, "status", "error"))
    result_text = str(getattr(result, "result", "") or "").strip()
    usage = extract_cursor_usage(result)
    if not usage.get("available"):
        usage = aggregate_turn_usage(turn_usages)
    return {
        "started": True,
        "status": status,
        "error": None if status == "finished" else (
            f"agent status={status}: {result_text[:1600]}" if result_text else f"agent status={status}"
        ),
        "result": result_text[:4000],
        "agentId": getattr(result, "agent_id", None),
        "runId": getattr(result, "id", None),
        "durationMs": int(getattr(result, "duration_ms", 0) or 0),
        "usedTokens": int(usage.get("usedTokens") or 0),
        "costUsd": float(usage.get("costUsd") or 0.0),
        "usageMeasurementMode": str(usage.get("source") or "") if usage.get("available") else "",
    }

def _default_codex_cli_agent_runner(ctx: ExecutionContext, prompt: str) -> dict[str, Any]:
    """Run a real Codex CLI agent through the same managed checkpoint contract."""
    from content.execution.agent.agent_worker import _terminate_pid_tree_if_alive
    codex = shutil.which("codex")
    if not codex:
        return {
            "started": False,
            "status": "error",
            "error": "codex CLI unavailable on PATH",
            "retryable": False,
            "agentProvider": "codex_cli",
        }
    started_at = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="qwq-codex-agent-") as tmp:
        output_path = Path(tmp) / "last_message.txt"
        cmd = [
            codex,
            "exec",
            "-C",
            str(Path.cwd()),
            "--dangerously-bypass-approvals-and-sandbox",
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
        ]
        if str(ctx.model or "").strip():
            cmd.extend(["--model", str(ctx.model).strip()])
        cmd.append("-")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(Path.cwd()),
            env=os.environ.copy(),
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(
                input=prompt,
                timeout=MANAGED_AGENT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _terminate_pid_tree_if_alive(proc.pid)
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
                "error": f"codex exec timed out after {MANAGED_AGENT_TIMEOUT_SECONDS}s",
                "retryable": True,
                "errorType": "timeout",
                "agentProvider": "codex_cli",
                "stdoutTail": _redact_managed_secret(stdout or "")[-1200:],
                "stderrTail": _redact_managed_secret(stderr or "")[-1200:],
            }
        result_text = ""
        if output_path.is_file():
            try:
                result_text = output_path.read_text(encoding="utf-8").strip()
            except OSError:
                result_text = ""
        if proc.returncode != 0:
            return {
                "started": False,
                "status": "error",
                "error": (
                    f"codex exec exited {proc.returncode}; "
                    f"stderr={_redact_managed_secret(stderr)[-1200:]}"
                ),
                "retryable": True,
                "agentProvider": "codex_cli",
                "stdoutTail": _redact_managed_secret(stdout)[-1200:],
                "stderrTail": _redact_managed_secret(stderr)[-1200:],
            }
        run_digest = hashlib.sha256((prompt + str(started_at)).encode("utf-8")).hexdigest()[:16]
        return {
            "started": True,
            "status": "finished",
            "error": None,
            "result": result_text[:4000],
            "agentId": "codex-cli",
            "runId": f"codex-cli-{run_digest}",
            "durationMs": int(max(0.0, time.monotonic() - started_at) * 1000),
            "agentProvider": "codex_cli",
        }

def _managed_agent_runner_for_provider(ctx: ExecutionContext, prompt: str) -> dict[str, Any]:
    provider = _normalize_managed_agent_provider(ctx.agent_provider)
    if provider == "codex_cli":
        return _default_codex_cli_agent_runner(ctx, prompt)
    outcome = _default_managed_agent_runner(ctx, prompt)
    outcome.setdefault("agentProvider", "cursor_sdk")
    return outcome

def _redact_managed_secret(text: str) -> str:
    text = re.sub(r"crsr_[A-Za-z0-9_-]+", "<redacted-cursor-key>", str(text or ""))
    text = re.sub(
        r"(--tool-callback-auth-token\s+)[^\s]+",
        r"\1<redacted-token>",
        text,
    )
    return text

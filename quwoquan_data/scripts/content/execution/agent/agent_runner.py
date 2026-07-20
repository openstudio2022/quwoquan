"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
import sys
from content.execution.support import Any, ExecutionContext, MANAGED_AGENT_TIMEOUT_SECONDS, Path, _CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, _CURSOR_BRIDGE_READY_DELAY_SECONDS, _normalize_managed_agent_provider, aggregate_turn_usage, extract_cursor_usage, hashlib, is_cursor_auth_error, os, resolve_cursor_api_key, store, subprocess, time
from content.execution.agent.managed_workspace import (
    managed_local_workspace_guard as _managed_local_workspace_guard,
    redact_managed_secret as _redact_managed_secret,
    terminate_workspace_cursor_bridges as _terminate_workspace_cursor_bridges,
)

_CURSOR_BRIDGE_MAX_RETRIES = active_runtime_policy().cursor_bridge_max_retries
_PROCESS_TERMINATION_TIMEOUT_SECONDS = active_runtime_policy().process_termination_timeout_seconds

def _prompt_cursor_agent_capturing_usage(
    agent_cls: Any,
    prompt: str,
    agent_options: Any,
    *,
    client: Any,
    on_turn_usage: Any = None,
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
                    usage_document = dict(usage)
                    turn_usages.append(usage_document)
                    if on_turn_usage is not None:
                        on_turn_usage(usage_document)
        result = run.wait()
        return result, turn_usages
    finally:
        agent.close()

def _default_managed_agent_runner(ctx: ExecutionContext, prompt: str):
    """Run Cursor SDK and return the sole typed managed-agent result."""
    from content.execution.agent.agent_worker import _terminate_pid_tree_if_alive
    from content.execution.agent.outcome import AgentRunOutcome
    from content.execution.controller.preflight import _cursor_bridge_error_is_retryable, _cursor_bridge_launch_guard, _patch_cursor_sdk_tool_callback_token
    from content.execution.context import _managed_uses_serial_local_cursor
    from content.execution.spend_reservation import (
        SpendBudgetExceeded,
        SpendReservation,
        reserve_cursor_spend,
        settle_cursor_spend,
    )
    from content.execution.controller.token_ledger_journal import (
        persist_cursor_usage_journal,
    )
    from content.execution.workspace import execution_root
    from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus
    from core.cursor_pricing import load_cursor_pricing, price_cursor_usage
    from core.io import write_json

    provider = AgentProvider.CURSOR_SDK
    turn_usages: list[dict[str, Any]] = []
    settled_attempt_costs: list[float | None] = []
    invocation_id = hashlib.sha256(
        f"{ctx.execution_id}:{ctx.model}:{time.time_ns()}".encode("utf-8")
    ).hexdigest()[:24]
    usage_event_path = (
        execution_root(ctx.execution_id)
        / "_shared"
        / "cursor_usage_events"
        / f"{invocation_id}.json"
    )

    def usage_fields(usage_override: dict[str, Any] | None = None) -> dict[str, Any]:
        usage = usage_override or aggregate_turn_usage(turn_usages)
        resolved_model_id = str(usage.get("resolvedModelId") or ctx.model).strip()
        if not usage.get("available"):
            return {
                "used_tokens": 0,
                "cost_usd": 0.0,
                "retry_cost_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cost_known": False,
                "cost_source": "",
                "cost_issue": "GATE_BLOCK_USAGE_UNKNOWN",
                "resolved_model_id": resolved_model_id,
                "pricing_revision": load_cursor_pricing().revision,
                "usage_measurement_mode": "",
            }
        priced = price_cursor_usage(
            model_id=resolved_model_id,
            usage=usage,
        )
        cost = priced.get("costUsd")
        retry_cost_known = all(
            value is not None for value in settled_attempt_costs[1:]
        )
        retry_cost = sum(
            float(value or 0.0) for value in settled_attempt_costs[1:]
        )
        return {
            "used_tokens": int(usage.get("usedTokens") or 0),
            "cost_usd": float(cost or 0.0),
            "retry_cost_usd": retry_cost,
            "input_tokens": int(usage.get("inputTokens") or 0),
            "output_tokens": int(usage.get("outputTokens") or 0),
            "cache_read_tokens": int(usage.get("cacheReadTokens") or 0),
            "cache_write_tokens": int(usage.get("cacheWriteTokens") or 0),
            "cost_known": cost is not None and retry_cost_known,
            "cost_source": str(priced.get("costSource") or ""),
            "cost_issue": (
                str(priced.get("costIssue") or "")
                if retry_cost_known
                else "GATE_BLOCK_RETRY_COST_UNKNOWN"
            ),
            "resolved_model_id": resolved_model_id,
            "pricing_revision": str(priced.get("pricingRevision") or ""),
            "usage_measurement_mode": str(usage.get("source") or ""),
        }

    def aggregate_document(fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "usedTokens": fields["used_tokens"],
            "inputTokens": fields["input_tokens"],
            "outputTokens": fields["output_tokens"],
            "cacheReadTokens": fields["cache_read_tokens"],
            "cacheWriteTokens": fields["cache_write_tokens"],
            "costUsd": (
                fields["cost_usd"] if fields["cost_known"] else None
            ),
            "retryCostUsd": (
                fields["retry_cost_usd"] if fields["cost_known"] else None
            ),
            "costKnown": fields["cost_known"],
            "costSource": fields["cost_source"] or None,
            "costIssue": fields["cost_issue"] or None,
            "measurementMode": fields["usage_measurement_mode"] or None,
        }

    def persist_usage_journal(
        *,
        status: str,
        fields: dict[str, Any],
        updated_at: str,
    ) -> None:
        persist_cursor_usage_journal(
            execution_id=ctx.execution_id,
            invocation_id=invocation_id,
            scope=ctx.agent_usage_scope,
            content_object_ref=ctx.agent_content_object_ref,
            execution_stage=ctx.agent_execution_stage,
            resolved_model_id=str(fields["resolved_model_id"]),
            pricing_revision=str(fields["pricing_revision"]),
            status=status,
            turn_count=len(turn_usages),
            aggregate=aggregate_document(fields),
            updated_at=updated_at,
        )

    def persist_turn_usage(usage: dict[str, Any]) -> None:
        turn_usages.append(dict(usage))
        fields = usage_fields(aggregate_turn_usage(turn_usages))
        updated_at = store.now_iso()
        write_json(
            usage_event_path,
            {
                "schema": "quwoquan.cursor_usage_event",
                "executionId": ctx.execution_id,
                "invocationId": invocation_id,
                "scope": ctx.agent_usage_scope,
                "contentObjectRef": ctx.agent_content_object_ref or None,
                "executionStage": ctx.agent_execution_stage or None,
                "resolvedModelId": fields["resolved_model_id"],
                "pricingRevision": fields["pricing_revision"],
                "status": "running",
                "turnCount": len(turn_usages),
                "turns": turn_usages,
                "aggregate": aggregate_document(fields),
                "updatedAt": updated_at,
            },
        )
        persist_usage_journal(
            status="running",
            fields=fields,
            updated_at=updated_at,
        )

    def persist_terminal_usage(
        status: str,
        *,
        usage_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fields = usage_fields(usage_override)
        updated_at = store.now_iso()
        aggregate = aggregate_document(fields)
        write_json(
            usage_event_path,
            {
                "schema": "quwoquan.cursor_usage_event",
                "executionId": ctx.execution_id,
                "invocationId": invocation_id,
                "scope": ctx.agent_usage_scope,
                "contentObjectRef": ctx.agent_content_object_ref or None,
                "executionStage": ctx.agent_execution_stage or None,
                "resolvedModelId": fields["resolved_model_id"],
                "pricingRevision": fields["pricing_revision"],
                "status": status,
                "turnCount": len(turn_usages),
                "turns": turn_usages,
                "aggregate": aggregate,
                "updatedAt": updated_at,
            },
        )
        persist_usage_journal(
            status=status,
            fields=fields,
            updated_at=updated_at,
        )
        return fields

    def settle_attempt(
        reservation: SpendReservation,
        usage: dict[str, Any],
    ) -> None:
        fields = usage_fields(usage)
        settle_cursor_spend(
            reservation,
            actual_cost_usd=(
                float(fields["cost_usd"])
                if fields["cost_known"]
                else None
            ),
            cost_issue=str(fields["cost_issue"] or ""),
        )
        settled_attempt_costs.append(
            float(fields["cost_usd"])
            if fields["cost_known"]
            else None
        )

    def failure(
        kind: AgentFailureKind,
        message: str,
        *,
        started: bool = False,
        retryable: bool = False,
        error_code: str = "",
        request_id: str = "",
        attempts: int = 0,
        warm_attempts: int = 0,
        duration_ms: int = 0,
        usage_override: dict[str, Any] | None = None,
    ) -> AgentRunOutcome:
        fields = persist_terminal_usage(
            "failed",
            usage_override=usage_override,
        )
        return AgentRunOutcome.failed(
            kind,
            provider=provider,
            message=_redact_managed_secret(message),
            started=started,
            retryable=retryable,
            error_code=error_code,
            request_id=request_id,
            attempts=attempts,
            warm_attempts=warm_attempts,
            duration_ms=duration_ms,
            **fields,
        )

    try:
        from cursor_sdk import (  # type: ignore
            Agent,
            AgentOptions,
            CloudAgentOptions,
            Client,
            CursorAgentError,
            LocalAgentOptions,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return failure(
            AgentFailureKind.SDK_UNAVAILABLE,
            f"cursor_sdk unavailable: {type(exc).__name__}",
        )
    # 每次 agent 调用前只从受限 key file reload；SDK 所需环境变量仅作
    # 当前进程内传递，不是配置来源，也不得写入运行证据。
    key = resolve_cursor_api_key()
    if not key:
        return failure(
            AgentFailureKind.CREDENTIAL_INVALID,
            "cursor API key file missing or invalid",
        )
    _patch_cursor_sdk_tool_callback_token()
    result = None
    last_error: AgentRunOutcome | None = None
    workspace = Path.cwd()
    auth_reload_used = False
    for attempt in range(_CURSOR_BRIDGE_MAX_RETRIES):
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
                    spend_reservation = reserve_cursor_spend(
                        execution_id=ctx.execution_id,
                        reservation_id=(
                            f"{invocation_id}:{attempt + 1}:{warm_attempt + 1}"
                        ),
                    )
                except SpendBudgetExceeded as exc:
                    return failure(
                        AgentFailureKind.BUDGET_EXCEEDED,
                        str(exc),
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
                turn_start = len(turn_usages)
                try:
                    result, attempt_turn_usages = _prompt_cursor_agent_capturing_usage(
                        Agent,
                        prompt,
                        agent_options,
                        client=client,
                        on_turn_usage=persist_turn_usage,
                    )
                    attempt_usage = extract_cursor_usage(result)
                    if not attempt_usage.get("available"):
                        attempt_usage = aggregate_turn_usage(attempt_turn_usages)
                    settle_attempt(spend_reservation, attempt_usage)
                    break
                except CursorAgentError as exc:
                    settle_attempt(
                        spend_reservation,
                        aggregate_turn_usage(turn_usages[turn_start:]),
                    )
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
                        return failure(
                            AgentFailureKind.CREDENTIAL_INVALID,
                            f"cursor credential invalid (auth): {message}",
                            error_code=str(getattr(exc, "code", "") or ""),
                            request_id=str(getattr(exc, "request_id", "") or ""),
                            attempts=attempt + 1,
                        )
                    retryable_bridge = _cursor_bridge_error_is_retryable(
                        message,
                        code=str(getattr(exc, "code", "") or ""),
                        explicit_retryable=bool(getattr(exc, "is_retryable", False)),
                    )
                    last_error = failure(
                        AgentFailureKind.BRIDGE_UNAVAILABLE,
                        message,
                        retryable=retryable_bridge,
                        error_code=str(getattr(exc, "code", "") or ""),
                        request_id=str(getattr(exc, "request_id", "") or ""),
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
                    if retryable_bridge and warm_attempt + 1 < warm_attempts:
                        time.sleep(2)
                        continue
                    if attempt + 1 < _CURSOR_BRIDGE_MAX_RETRIES and retryable_bridge:
                        bridge_retry_requested = True
                        break
                    return last_error
                except RuntimeError as exc:
                    settle_attempt(
                        spend_reservation,
                        aggregate_turn_usage(turn_usages[turn_start:]),
                    )
                    message = f"{type(exc).__name__}: {exc}"
                    retryable_bridge = _cursor_bridge_error_is_retryable(message)
                    last_error = failure(
                        AgentFailureKind.BRIDGE_UNAVAILABLE,
                        message,
                        retryable=retryable_bridge,
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
                    if retryable_bridge and warm_attempt + 1 < warm_attempts:
                        time.sleep(2)
                        continue
                    if attempt + 1 < _CURSOR_BRIDGE_MAX_RETRIES and retryable_bridge:
                        bridge_retry_requested = True
                        break
                    return last_error
                except Exception as exc:  # noqa: BLE001
                    settle_attempt(
                        spend_reservation,
                        aggregate_turn_usage(turn_usages[turn_start:]),
                    )
                    message = f"{type(exc).__name__}: {exc}"
                    retryable_bridge = _cursor_bridge_error_is_retryable(message)
                    last_error = failure(
                        AgentFailureKind.SDK_EXECUTION_FAILED,
                        message,
                        retryable=retryable_bridge,
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
                    if retryable_bridge and warm_attempt + 1 < warm_attempts:
                        time.sleep(2)
                        continue
                    if attempt + 1 < _CURSOR_BRIDGE_MAX_RETRIES and retryable_bridge:
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
            return last_error or failure(
                AgentFailureKind.NO_RESULT,
                "Cursor SDK returned no result",
                attempts=attempt + 1,
            )
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
                return failure(
                    AgentFailureKind.CREDENTIAL_INVALID,
                    f"cursor credential invalid (auth): {message}",
                    error_code=str(getattr(exc, "code", "") or ""),
                    request_id=str(getattr(exc, "request_id", "") or ""),
                    attempts=attempt + 1,
                )
            retryable_bridge = _cursor_bridge_error_is_retryable(
                message,
                code=str(getattr(exc, "code", "") or ""),
                explicit_retryable=bool(getattr(exc, "is_retryable", False)),
            )
            last_error = failure(
                AgentFailureKind.BRIDGE_UNAVAILABLE,
                message,
                retryable=retryable_bridge,
                error_code=str(getattr(exc, "code", "") or ""),
                request_id=str(getattr(exc, "request_id", "") or ""),
                attempts=attempt + 1,
            )
            if attempt + 1 < _CURSOR_BRIDGE_MAX_RETRIES and retryable_bridge:
                if _managed_uses_serial_local_cursor(ctx):
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error
        except RuntimeError as exc:
            message = f"{type(exc).__name__}: {exc}"
            retryable_bridge = _cursor_bridge_error_is_retryable(message)
            last_error = failure(
                AgentFailureKind.BRIDGE_UNAVAILABLE,
                message,
                retryable=retryable_bridge,
                attempts=attempt + 1,
            )
            if attempt + 1 < _CURSOR_BRIDGE_MAX_RETRIES and retryable_bridge:
                if _managed_uses_serial_local_cursor(ctx):
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error
        except Exception as exc:  # noqa: BLE001
            last_error = failure(
                AgentFailureKind.SDK_EXECUTION_FAILED,
                f"{type(exc).__name__}: {exc}",
                attempts=attempt + 1,
            )
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
        return last_error or failure(
            AgentFailureKind.NO_RESULT,
            "Cursor isolated bridge retry exhausted without a run result",
            retryable=True,
        )
    raw_status = str(getattr(result, "status", AgentRunStatus.ERROR.value))
    result_text = str(getattr(result, "result", "") or "").strip()
    usage = extract_cursor_usage(result)
    stream_usage = aggregate_turn_usage(turn_usages)
    if (
        not usage.get("available")
        or (
            len(settled_attempt_costs) > 1
            and stream_usage.get("available")
        )
    ):
        usage = stream_usage
    if raw_status != AgentRunStatus.FINISHED.value:
        return failure(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            f"agent status={raw_status}: {result_text[:1600]}" if result_text else f"agent status={raw_status}",
            started=True,
            duration_ms=int(getattr(result, "duration_ms", 0) or 0),
            usage_override=usage,
        )
    fields = persist_terminal_usage(
        "finished",
        usage_override=usage,
    )
    return AgentRunOutcome.finished(
        provider=provider,
        result_text=result_text[:4000],
        agent_id=str(getattr(result, "agent_id", "") or ""),
        run_id=str(getattr(result, "id", "") or ""),
        duration_ms=int(getattr(result, "duration_ms", 0) or 0),
        attempts=attempt + 1,
        warm_attempts=warm_attempt + 1,
        **fields,
    )

def _managed_agent_runner_for_provider(ctx: ExecutionContext, prompt: str):
    _normalize_managed_agent_provider(ctx.agent_provider)
    outcome = _default_managed_agent_runner(ctx, prompt)
    return outcome

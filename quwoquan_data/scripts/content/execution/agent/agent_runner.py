"""Cursor SDK boundary for one managed execution checkpoint.

The SDK event stream must be drained for completion, but data execution does not
persist provider billing telemetry.  Evidence is limited to the typed run
outcome: provider, run ID, result, timing and stable failure semantics.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus
from core.cursor_credentials import is_cursor_auth_error, resolve_cursor_api_key
from core.runtime_policy import active_runtime_policy
from content.execution.agent.managed_workspace import (
    managed_local_workspace_guard as _managed_local_workspace_guard,
    redact_managed_secret as _redact_managed_secret,
    terminate_workspace_cursor_bridges as _terminate_workspace_cursor_bridges,
)
from content.execution.context import ExecutionContext, _managed_uses_serial_local_cursor


_CURSOR_BRIDGE_MAX_RETRIES = active_runtime_policy().cursor_bridge_max_retries
_PROCESS_TERMINATION_TIMEOUT_SECONDS = active_runtime_policy().process_termination_timeout_seconds
_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS = active_runtime_policy().bridge_launch_cooldown_seconds
_CURSOR_BRIDGE_READY_DELAY_SECONDS = active_runtime_policy().bridge_ready_delay_seconds


def _cursor_provider_rejection(message: str, *, code: str = "") -> bool:
    """Identify non-retryable account/quota rejection from the public SDK."""
    lowered = str(message or "").casefold()
    code_lower = str(code or "").casefold()
    return code_lower in {
        "billing_limit_reached",
        "insufficient_credits",
        "quota_exceeded",
        "usage_limit",
    } or any(
        marker in lowered
        for marker in (
            "you've hit your usage limit",
            "usage limit",
            "spend limit",
            "monthly cycle ends",
            "insufficient credits",
        )
    )


def _prompt_cursor_agent(
    agent_cls: Any,
    prompt: str,
    agent_options: Any,
    *,
    client: Any,
) -> tuple[Any, str]:
    """Run one prompt and preserve the SDK terminal status explanation."""
    agent = agent_cls.create(agent_options, client=client)
    try:
        run = agent.send(prompt)
        terminal_message = ""
        for event in run.events():
            message = getattr(event, "sdk_message", None)
            if (
                getattr(message, "type", "") == "status"
                and str(getattr(message, "status", "")).casefold() == "error"
            ):
                terminal_message = str(getattr(message, "message", "") or "").strip()
        return run.wait(), terminal_message
    finally:
        agent.close()


def _default_managed_agent_runner(ctx: ExecutionContext, prompt: str):
    """Run Cursor SDK and return the sole typed managed-agent result."""
    from content.execution.agent.outcome import AgentRunOutcome
    from content.execution.controller.preflight import (
        _cursor_bridge_error_is_retryable,
        _cursor_bridge_launch_guard,
    )

    provider = AgentProvider.CURSOR_SDK
    key: str | None = None

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
    ) -> AgentRunOutcome:
        return AgentRunOutcome.failed(
            kind,
            provider=provider,
            message=_redact_managed_secret(message, api_key=key),
            started=started,
            retryable=retryable,
            error_code=error_code,
            request_id=request_id,
            attempts=attempts,
            warm_attempts=warm_attempts,
            duration_ms=duration_ms,
        )

    try:
        from cursor_sdk import (  # type: ignore
            Agent,
            AgentOptions,
            CloudAgentOptions,
            Client,
            CursorAgentError,
            LocalAgentOptions,
            ModelParameterValue,
            ModelSelection,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return failure(
            AgentFailureKind.SDK_UNAVAILABLE,
            f"cursor_sdk unavailable: {type(exc).__name__}",
        )

    key = resolve_cursor_api_key()
    if not key:
        return failure(
            AgentFailureKind.CREDENTIAL_INVALID,
            "cursor API key file missing or invalid",
        )
    sdk_model = ModelSelection(
        id=ctx.model_selection.model_id,
        params=tuple(
            ModelParameterValue(id=parameter.id, value=parameter.value)
            for parameter in ctx.model_selection.parameters
        ),
    )

    workspace = Path.cwd()
    last_error: AgentRunOutcome | None = None
    result: Any | None = None
    terminal_status_message = ""
    completed_attempt = 0
    completed_warm_attempt = 0
    auth_reload_used = False

    for attempt in range(_CURSOR_BRIDGE_MAX_RETRIES):
        client: Any | None = None
        request_bridge_retry = False
        try:
            if attempt and _managed_uses_serial_local_cursor(ctx):
                _terminate_workspace_cursor_bridges(workspace)
            with _cursor_bridge_launch_guard():
                client = Client.launch_bridge(
                    workspace=str(workspace),
                    max_retries=_CURSOR_BRIDGE_MAX_RETRIES,
                    allow_api_key_env_fallback=False,
                )
            if _CURSOR_BRIDGE_READY_DELAY_SECONDS:
                time.sleep(_CURSOR_BRIDGE_READY_DELAY_SECONDS)
            if str(ctx.runtime) == "cloud":
                options = AgentOptions(
                    api_key=key,
                    model=sdk_model,
                    cloud=CloudAgentOptions(repos=[]),
                )
            else:
                options = AgentOptions(
                    api_key=key,
                    model=sdk_model,
                    local=LocalAgentOptions(cwd=str(workspace)),
                )

            for warm_attempt in range(active_runtime_policy().cursor_warm_attempts):
                try:
                    result, terminal_status_message = _prompt_cursor_agent(
                        Agent,
                        prompt,
                        options,
                        client=client,
                    )
                    completed_attempt = attempt + 1
                    completed_warm_attempt = warm_attempt + 1
                    break
                except CursorAgentError as exc:
                    message = getattr(exc, "message", str(exc))
                    error_code = str(getattr(exc, "code", "") or "")
                    request_id = str(getattr(exc, "request_id", "") or "")
                    if is_cursor_auth_error(
                        message,
                        code=error_code,
                        status=getattr(exc, "status", None),
                    ):
                        reloaded = resolve_cursor_api_key()
                        if not auth_reload_used and reloaded and reloaded != key:
                            auth_reload_used = True
                            key = reloaded
                            request_bridge_retry = True
                            break
                        return failure(
                            AgentFailureKind.CREDENTIAL_INVALID,
                            f"cursor credential invalid (auth): {message}",
                            error_code=error_code,
                            request_id=request_id,
                            attempts=attempt + 1,
                            warm_attempts=warm_attempt + 1,
                        )
                    if _cursor_provider_rejection(message, code=error_code):
                        return failure(
                            AgentFailureKind.PROVIDER_REJECTED,
                            message,
                            started=True,
                            error_code=(
                                error_code or AgentFailureKind.PROVIDER_REJECTED.value
                            ),
                            request_id=request_id,
                            attempts=attempt + 1,
                            warm_attempts=warm_attempt + 1,
                        )
                    retryable = _cursor_bridge_error_is_retryable(
                        message,
                        code=error_code,
                        explicit_retryable=bool(getattr(exc, "is_retryable", False)),
                    )
                    last_error = failure(
                        AgentFailureKind.BRIDGE_UNAVAILABLE,
                        message,
                        retryable=retryable,
                        error_code=error_code,
                        request_id=request_id,
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
                    if retryable and warm_attempt + 1 < active_runtime_policy().cursor_warm_attempts:
                        time.sleep(2)
                        continue
                    request_bridge_retry = retryable
                    break
                except RuntimeError as exc:
                    message = f"{type(exc).__name__}: {exc}"
                    retryable = _cursor_bridge_error_is_retryable(message)
                    last_error = failure(
                        AgentFailureKind.BRIDGE_UNAVAILABLE,
                        message,
                        retryable=retryable,
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
                    if retryable and warm_attempt + 1 < active_runtime_policy().cursor_warm_attempts:
                        time.sleep(2)
                        continue
                    request_bridge_retry = retryable
                    break
                except Exception as exc:  # noqa: BLE001
                    return failure(
                        AgentFailureKind.SDK_EXECUTION_FAILED,
                        f"{type(exc).__name__}: {exc}",
                        attempts=attempt + 1,
                        warm_attempts=warm_attempt + 1,
                    )
        except CursorAgentError as exc:
            message = getattr(exc, "message", str(exc))
            error_code = str(getattr(exc, "code", "") or "")
            request_id = str(getattr(exc, "request_id", "") or "")
            if is_cursor_auth_error(
                message,
                code=error_code,
                status=getattr(exc, "status", None),
            ):
                reloaded = resolve_cursor_api_key()
                if not auth_reload_used and reloaded and reloaded != key:
                    auth_reload_used = True
                    key = reloaded
                    request_bridge_retry = True
                else:
                    return failure(
                        AgentFailureKind.CREDENTIAL_INVALID,
                        f"cursor credential invalid (auth): {message}",
                        error_code=error_code,
                        request_id=request_id,
                        attempts=attempt + 1,
                    )
            else:
                if _cursor_provider_rejection(message, code=error_code):
                    return failure(
                        AgentFailureKind.PROVIDER_REJECTED,
                        message,
                        error_code=(
                            error_code or AgentFailureKind.PROVIDER_REJECTED.value
                        ),
                        request_id=request_id,
                        attempts=attempt + 1,
                    )
                retryable = _cursor_bridge_error_is_retryable(
                    message,
                    code=error_code,
                    explicit_retryable=bool(getattr(exc, "is_retryable", False)),
                )
                last_error = failure(
                    AgentFailureKind.BRIDGE_UNAVAILABLE,
                    message,
                    retryable=retryable,
                    error_code=error_code,
                    request_id=request_id,
                    attempts=attempt + 1,
                )
                request_bridge_retry = retryable
        except RuntimeError as exc:
            message = f"{type(exc).__name__}: {exc}"
            retryable = _cursor_bridge_error_is_retryable(message)
            last_error = failure(
                AgentFailureKind.BRIDGE_UNAVAILABLE,
                message,
                retryable=retryable,
                attempts=attempt + 1,
            )
            request_bridge_retry = retryable
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"[cursor-agent] client close failed: {type(exc).__name__}",
                        file=sys.stderr,
                    )

        if result is not None:
            break
        if not request_bridge_retry or attempt + 1 >= _CURSOR_BRIDGE_MAX_RETRIES:
            return last_error or failure(
                AgentFailureKind.NO_RESULT,
                "Cursor bridge returned no run result",
                retryable=True,
                attempts=attempt + 1,
            )
        if _managed_uses_serial_local_cursor(ctx):
            _terminate_workspace_cursor_bridges(workspace)
        time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))

    if result is None:
        return last_error or failure(
            AgentFailureKind.NO_RESULT,
            "Cursor isolated bridge retry exhausted without a run result",
            retryable=True,
        )
    raw_status = str(getattr(result, "status", AgentRunStatus.ERROR.value))
    result_text = str(getattr(result, "result", "") or "").strip()
    duration_ms = int(getattr(result, "duration_ms", 0) or 0)
    if raw_status != AgentRunStatus.FINISHED.value:
        return failure(
            (
                AgentFailureKind.PROVIDER_REJECTED
                if terminal_status_message
                else AgentFailureKind.SDK_EXECUTION_FAILED
            ),
            terminal_status_message
            or (
                f"agent status={raw_status}: {result_text[:1600]}"
                if result_text
                else f"agent status={raw_status}"
            ),
            started=True,
            error_code=(
                AgentFailureKind.PROVIDER_REJECTED.value
                if terminal_status_message
                else AgentFailureKind.SDK_EXECUTION_FAILED.value
            ),
            duration_ms=duration_ms,
            attempts=completed_attempt,
            warm_attempts=completed_warm_attempt,
        )
    return AgentRunOutcome.finished(
        provider=provider,
        result_text=result_text[:4000],
        agent_id=str(getattr(result, "agent_id", "") or ""),
        run_id=str(getattr(result, "id", "") or ""),
        duration_ms=duration_ms,
        attempts=completed_attempt,
        warm_attempts=completed_warm_attempt,
    )


def _managed_agent_runner_for_provider(ctx: ExecutionContext, prompt: str):
    return _default_managed_agent_runner(ctx, prompt)

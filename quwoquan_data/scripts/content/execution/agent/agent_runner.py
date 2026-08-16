"""Explicit provider dispatch for one managed semantic-agent checkpoint.

Provider event streams must be drained for completion, but data execution does
not persist billing telemetry. Evidence is limited to provider, run ID, result,
timing and stable failure semantics. Provider fallback is forbidden.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import Any

from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus
from core.cursor_bridge_transport import protected_cursor_client
from core.cursor_credentials import is_cursor_auth_error, resolve_cursor_api_key
from core.paths import OUTPUT_ROOT
from core.runtime_policy import active_runtime_policy

from content.execution.agent.managed_workspace import (
    redact_managed_secret as _redact_managed_secret,
)
from content.execution.agent.managed_workspace import (
    terminate_workspace_cursor_bridges as _terminate_workspace_cursor_bridges,
)
from content.execution.agent.provider_failure import classify_provider_failure
from content.execution.context import (
    ExecutionContext,
    _managed_uses_serial_local_cursor,
)

_EXTRACTED_DEPENDENCIES = (sys,)

_CURSOR_BRIDGE_MAX_RETRIES = active_runtime_policy().cursor_bridge_max_retries
_PROCESS_TERMINATION_TIMEOUT_SECONDS = (
    active_runtime_policy().process_termination_timeout_seconds
)
_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS = (
    active_runtime_policy().bridge_launch_cooldown_seconds
)
_CURSOR_BRIDGE_READY_DELAY_SECONDS = active_runtime_policy().bridge_ready_delay_seconds


def _cursor_provider_rejection(*args: Any, **kwargs: Any) -> bool:
    from content.execution.agent.agent_runner_support import (
        _cursor_provider_rejection as implementation,
    )

    return implementation(*args, **kwargs)


def _prompt_cursor_agent(*args: Any, **kwargs: Any) -> tuple[Any, str]:
    from content.execution.agent.agent_runner_support import (
        _prompt_cursor_agent as implementation,
    )

    return implementation(*args, **kwargs)


def _close_cursor_client(*args: Any, **kwargs: Any) -> None:
    from content.execution.agent.agent_runner_support import (
        _close_cursor_client as implementation,
    )

    return implementation(*args, **kwargs)


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
        retry_after_seconds: int = 0,
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
            retry_after_seconds=retry_after_seconds,
            request_id=request_id,
            attempts=attempts,
            warm_attempts=warm_attempts,
            duration_ms=duration_ms,
        )

    cursor_selections = {
        selection.binding.selection
        for selection in active_runtime_policy().explicit_semantic_selections
        if selection.binding.provider is AgentProvider.CURSOR_SDK
    }
    if ctx.model_selection not in cursor_selections:
        return failure(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            "cursor_sdk requires one governed explicit model selection",
            error_code="semantic_provider_selection_not_governed",
        )

    try:
        from cursor_sdk import (  # type: ignore
            Agent,
            AgentOptions,
            CloudAgentOptions,
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
        client_context: Any | None = None
        request_bridge_retry = False
        try:
            if attempt and _managed_uses_serial_local_cursor(ctx):
                _terminate_workspace_cursor_bridges(workspace)
            with _cursor_bridge_launch_guard():
                launch_context = protected_cursor_client(
                    workspace=str(workspace),
                    max_retries=_CURSOR_BRIDGE_MAX_RETRIES,
                )
                client = launch_context.__enter__()
                client_context = launch_context
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
                    classified = classify_provider_failure(
                        message,
                        code=error_code,
                        status=getattr(exc, "status", None),
                        explicit_retryable=bool(getattr(exc, "is_retryable", False)),
                    )
                    if classified.error_code != "semantic_provider_execution_failed":
                        return failure(
                            classified.kind,
                            message,
                            started=True,
                            retryable=classified.retryable,
                            error_code=classified.error_code,
                            retry_after_seconds=classified.retry_after_seconds,
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
                    if (
                        retryable
                        and warm_attempt + 1
                        < active_runtime_policy().cursor_warm_attempts
                    ):
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
                    if (
                        retryable
                        and warm_attempt + 1
                        < active_runtime_policy().cursor_warm_attempts
                    ):
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
                classified = classify_provider_failure(
                    message,
                    code=error_code,
                    status=getattr(exc, "status", None),
                    explicit_retryable=bool(getattr(exc, "is_retryable", False)),
                )
                if classified.error_code != "semantic_provider_execution_failed":
                    return failure(
                        classified.kind,
                        message,
                        retryable=classified.retryable,
                        error_code=classified.error_code,
                        retry_after_seconds=classified.retry_after_seconds,
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
            if client_context is not None:
                _close_cursor_client(
                    client_context,
                    workspace=workspace,
                    terminate_bridges=_managed_uses_serial_local_cursor(ctx),
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
        time.sleep(
            max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1)
        )

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
        message = terminal_status_message or (
            f"agent status={raw_status}: {result_text[:1600]}"
            if result_text
            else f"agent status={raw_status}"
        )
        classified = classify_provider_failure(message)
        return failure(
            classified.kind,
            message,
            started=True,
            retryable=classified.retryable,
            error_code=classified.error_code,
            retry_after_seconds=classified.retry_after_seconds,
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


def _managed_agent_runner_for_provider_unjournaled(
    ctx: ExecutionContext,
    prompt: str,
):
    from content.execution.agent.capacity_broker import (
        SemanticCapacityBroker,
        SemanticCapacityTimeout,
        SemanticProviderCircuitOpen,
        semantic_provider_capacity,
        semantic_provider_lane,
    )
    from content.execution.agent.outcome import AgentRunOutcome

    provider = ctx.agent_provider
    if not isinstance(provider, AgentProvider):
        provider = AgentProvider(str(provider))
    policy = active_runtime_policy()
    role = str(ctx.semantic_role or "").strip()
    role_bindings = {
        "author": policy.semantic_author,
        "reviewer": policy.semantic_reviewer,
        "calibration": policy.semantic_calibration.binding,
    }
    binding = role_bindings.get(role)
    cursor_selections = {
        selection.binding.selection
        for selection in policy.explicit_semantic_selections
        if selection.binding.provider is AgentProvider.CURSOR_SDK
    }
    if provider is AgentProvider.CODEX_SDK:
        role_binding_valid = (
            binding is not None
            and binding.provider is provider
            and binding.selection == ctx.model_selection
        )
    else:
        role_binding_valid = (
            provider is AgentProvider.CURSOR_SDK
            and role in {"author", "reviewer"}
            and ctx.model_selection in cursor_selections
        )
    if not role_binding_valid:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=(
                "semantic provider/model is not governed for role: "
                f"{role or '<missing>'}"
            ),
            error_code="semantic_provider_role_binding_mismatch",
        )
    broker = SemanticCapacityBroker(
        account_scope_id=policy.semantic_capacity.account_scope_id,
        host_scope_id=policy.semantic_capacity.host_scope_id,
    )
    circuit = broker.check_circuit(provider)
    if circuit is not None:
        try:
            failure_kind = AgentFailureKind(str(circuit.get("failureKind") or ""))
        except ValueError:
            failure_kind = AgentFailureKind.PROVIDER_REJECTED
        return AgentRunOutcome.failed(
            failure_kind,
            provider=provider,
            message=(
                "semantic provider circuit is open: "
                + str(circuit.get("message") or failure_kind.value)
            ),
            retryable=bool(circuit.get("retryable")),
            retry_after_seconds=int(circuit.get("retryAfterSeconds") or 0),
            error_code="provider_circuit_open",
        )
    try:
        lease = broker.acquire(
            provider,
            lane=semantic_provider_lane(ctx),
            capacity=semantic_provider_capacity(policy),
            lane_capacity=policy.semantic_capacity.lane_concurrency_limit,
            requests_per_minute=policy.semantic_capacity.requests_per_minute,
            burst_limit=policy.semantic_capacity.burst_limit,
            wait_timeout_seconds=float(policy.assignment_deadline_seconds),
            lease_ttl_seconds=float(
                policy.agent_timeout_seconds
                + policy.managed_future_grace_seconds
                + policy.process_termination_timeout_seconds
            ),
        )
    except SemanticProviderCircuitOpen as exc:
        raw_kind = str(exc.circuit.get("failureKind") or "")
        try:
            kind = AgentFailureKind(raw_kind)
        except ValueError:
            kind = AgentFailureKind.PROVIDER_REJECTED
        return AgentRunOutcome.failed(
            kind,
            provider=provider,
            message=f"semantic provider circuit is open: {exc}",
            retryable=bool(exc.circuit.get("retryable")),
            retry_after_seconds=int(exc.circuit.get("retryAfterSeconds") or 0),
            error_code="provider_circuit_open",
        )
    except SemanticCapacityTimeout as exc:
        return AgentRunOutcome.failed(
            AgentFailureKind.CAPACITY_UNPROVEN,
            provider=provider,
            message=str(exc),
            retryable=True,
            error_code="semantic_provider_capacity_wait_timeout",
        )
    with lease:
        if provider is AgentProvider.CURSOR_SDK:
            outcome = _default_managed_agent_runner(ctx, prompt)
        elif provider is AgentProvider.CODEX_SDK:
            from content.execution.agent.codex_adapter import run_codex_agent

            outcome = run_codex_agent(ctx, prompt)
        else:  # pragma: no cover - AgentProvider is a closed enum
            return AgentRunOutcome.failed(
                AgentFailureKind.SDK_UNAVAILABLE,
                provider=provider,
                message=f"unsupported semantic agent provider: {provider.value}",
            )
        try:
            _receipt, receipt_path = broker.write_capacity_receipt(
                lease,
                execution_id=ctx.execution_id,
                model=ctx.model,
                role=role,
                prompt=prompt,
                outcome=outcome,
                runtime_profile_id=policy.profile_id,
            )
            receipt_ref = (
                receipt_path.resolve().relative_to(OUTPUT_ROOT.resolve()).as_posix()
            )
            receipt_digest = (
                "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            )
            outcome = outcome.with_capacity_receipt(
                receipt_ref=receipt_ref,
                receipt_digest=receipt_digest,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return AgentRunOutcome.failed(
                AgentFailureKind.CAPACITY_UNPROVEN,
                provider=provider,
                message=f"semantic capacity receipt failed: {type(exc).__name__}",
                started=outcome.started,
                retryable=False,
                error_code="semantic_capacity_receipt_failed",
            )
    if outcome.failure_kind in {
        AgentFailureKind.CREDENTIAL_INVALID,
        AgentFailureKind.AUTHENTICATION_REJECTED,
        AgentFailureKind.PROVIDER_REJECTED,
    } and (not outcome.retryable or outcome.retry_after_seconds > 0):
        broker.open_circuit(
            provider,
            model=ctx.model,
            failure_kind=outcome.failure_kind,
            message=_redact_managed_secret(outcome.message),
            cooldown_seconds=float(
                outcome.retry_after_seconds or min(policy.agent_timeout_seconds, 300)
            ),
            retryable=outcome.retryable,
            retry_after_seconds=outcome.retry_after_seconds,
        )
    return outcome


def _managed_agent_runner_for_provider(ctx: ExecutionContext, prompt: str):
    from content.execution.agent import semantic_task_journal

    return semantic_task_journal.run_journaled_semantic_task(
        ctx, prompt, _managed_agent_runner_for_provider_unjournaled
    )

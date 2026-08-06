"""Governed official Codex Python SDK adapter for semantic-agent invocations.

``codex_sdk`` is the stable Data provider ID.  Its only implementation is the
official ``openai-codex`` Python package, which controls its pinned Codex
runtime over JSON-RPC.  Prompts and JSON Schema are passed through SDK method
arguments; this adapter never shells out to ``codex exec`` and never falls back
to another provider.

The generic managed-agent worker still runs this function in its own killable
process.  That process boundary owns the hard wall-clock deadline and process
group cleanup; the SDK owns the provider transport and workspace sandbox.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from core.control_types import AgentFailureKind, AgentProvider, RuntimeEnvironment
from core.cursor_model import CursorModelSelection
from core.runtime_policy import active_runtime_policy

from content.execution.agent.managed_workspace import redact_managed_secret
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.agent.provider_failure import classify_provider_failure

_ALLOWED_MODEL_PARAMETER_IDS = frozenset({"effort", "reasoning_effort"})
_FINAL_RESPONSE_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary"],
    "properties": {
        "status": {"type": "string", "const": "completed"},
        "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
    },
}


@dataclass(frozen=True, slots=True)
class _CodexSdkBindings:
    codex_class: type[Any]
    sandbox_class: Any
    approval_mode_class: Any
    is_retryable_error: Callable[[BaseException], bool]


@dataclass(frozen=True, slots=True)
class _CodexSdkResult:
    thread_id: str
    turn_id: str
    final_response: str | None
    status: str
    duration_ms: int


class _CodexSdkInvocationError(RuntimeError):
    def __init__(self, cause: BaseException, *, started: bool, retryable: bool) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.started = started
        self.retryable = retryable


@lru_cache(maxsize=1)
def _load_codex_sdk() -> _CodexSdkBindings:
    from openai_codex import ApprovalMode, Codex, Sandbox, is_retryable_error

    return _CodexSdkBindings(
        codex_class=Codex,
        sandbox_class=Sandbox,
        approval_mode_class=ApprovalMode,
        is_retryable_error=is_retryable_error,
    )


@lru_cache(maxsize=1)
def codex_sdk_version() -> str:
    try:
        return f"openai-codex {metadata.version('openai-codex')}"
    except metadata.PackageNotFoundError:
        return "openai-codex-version-unavailable"


def _model_config(selection: CursorModelSelection) -> tuple[dict[str, str], str]:
    config: dict[str, str] = {}
    for parameter in selection.parameters:
        if parameter.id not in _ALLOWED_MODEL_PARAMETER_IDS:
            return {}, f"unsupported codex model parameter: {parameter.id}"
        if config:
            return {}, "codex reasoning effort must be specified once"
        config["model_reasoning_effort"] = parameter.value
    return config, ""


def _selection_is_governed(selection: CursorModelSelection) -> bool:
    policy = active_runtime_policy()
    allowed = {
        policy.semantic_author.selection,
        policy.semantic_reviewer.selection,
        policy.semantic_calibration.binding.selection,
    }
    return selection in allowed


def _sandbox_preset(bindings: _CodexSdkBindings, sandbox: str) -> object:
    presets = {
        "read-only": bindings.sandbox_class.read_only,
        "workspace-write": bindings.sandbox_class.workspace_write,
    }
    try:
        return presets[sandbox]
    except KeyError:
        raise ValueError(f"unsupported governed Codex sandbox: {sandbox}") from None


def _retryable_sdk_error(bindings: _CodexSdkBindings, exc: BaseException) -> bool:
    return bool(bindings.is_retryable_error(exc))


def _invoke_codex_sdk(
    bindings: _CodexSdkBindings,
    *,
    selection: CursorModelSelection,
    model_config: dict[str, str],
    workspace: Path,
    prompt: str,
    sandbox: str,
) -> _CodexSdkResult:
    """Run one ephemeral SDK thread; the caller classifies all SDK failures."""
    started = False
    started_at = time.monotonic()
    try:
        sandbox_preset = _sandbox_preset(bindings, sandbox)
        approval_mode = bindings.approval_mode_class.deny_all
        with bindings.codex_class() as codex:
            thread = codex.thread_start(
                approval_mode=approval_mode,
                config=dict(model_config) or None,
                cwd=str(workspace),
                ephemeral=True,
                model=selection.model_id,
                sandbox=sandbox_preset,
                service_name="quwoquan_data",
            )
            started = True
            result = thread.run(
                prompt,
                approval_mode=approval_mode,
                cwd=str(workspace),
                output_schema=_FINAL_RESPONSE_SCHEMA,
                sandbox=sandbox_preset,
            )
    except Exception as exc:
        raise _CodexSdkInvocationError(
            exc,
            started=started,
            retryable=_retryable_sdk_error(bindings, exc),
        ) from exc
    status_value = getattr(getattr(result, "status", ""), "value", None)
    status = str(status_value or getattr(result, "status", "") or "").strip()
    measured_ms = int(max(0.0, time.monotonic() - started_at) * 1000)
    sdk_duration = getattr(result, "duration_ms", None)
    duration_ms = (
        int(sdk_duration)
        if isinstance(sdk_duration, int) and not isinstance(sdk_duration, bool) and sdk_duration >= 0
        else measured_ms
    )
    return _CodexSdkResult(
        thread_id=str(getattr(thread, "id", "") or "").strip(),
        turn_id=str(getattr(result, "id", "") or "").strip(),
        final_response=getattr(result, "final_response", None),
        status=status,
        duration_ms=duration_ms,
    )


def _structured_result_text(value: object) -> tuple[dict[str, str] | None, str]:
    if not isinstance(value, str) or not value.strip():
        return None, "Codex SDK completed without a structured final response"
    try:
        raw = json.loads(value)
    except (TypeError, ValueError) as exc:
        return None, f"Codex SDK structured result unreadable: {type(exc).__name__}"
    if not isinstance(raw, dict) or set(raw) != {"status", "summary"}:
        return None, "Codex SDK structured result must contain status and summary only"
    status = raw.get("status")
    summary = raw.get("summary")
    if status != "completed" or not isinstance(summary, str) or not summary.strip():
        return None, "Codex SDK structured result did not report completed with a summary"
    return {"status": status, "summary": summary.strip()}, ""


def _sdk_unavailable(exc: BaseException) -> AgentRunOutcome:
    return AgentRunOutcome.failed(
        AgentFailureKind.SDK_UNAVAILABLE,
        provider=AgentProvider.CODEX_SDK,
        message=f"official openai-codex SDK is unavailable: {type(exc).__name__}",
        error_code="semantic_provider_sdk_unavailable",
    )


def _run_codex(
    *,
    selection: CursorModelSelection,
    runtime: RuntimeEnvironment,
    workspace: Path,
    prompt: str,
    timeout_seconds: float,
    sandbox: str,
) -> AgentRunOutcome:
    provider = AgentProvider.CODEX_SDK
    if runtime is not RuntimeEnvironment.LOCAL:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_UNAVAILABLE,
            provider=provider,
            message="codex_sdk adapter supports governed local runtime only",
            error_code="semantic_provider_runtime_unsupported",
        )
    if timeout_seconds <= 0:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message="Codex SDK timeout must be positive",
            error_code="semantic_provider_timeout_invalid",
        )
    model_config, parameter_issue = _model_config(selection)
    if parameter_issue:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=parameter_issue,
            error_code="semantic_provider_model_parameter_invalid",
        )
    if not _selection_is_governed(selection):
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=f"codex model selection is not governed: {selection.model_id}",
            error_code="semantic_provider_selection_not_governed",
        )
    try:
        bindings = _load_codex_sdk()
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        return _sdk_unavailable(exc)
    started_at = time.monotonic()
    try:
        result = _invoke_codex_sdk(
            bindings,
            selection=selection,
            model_config=model_config,
            workspace=workspace.resolve(),
            prompt=prompt,
            sandbox=sandbox,
        )
    except _CodexSdkInvocationError as exc:
        duration_ms = int(max(0.0, time.monotonic() - started_at) * 1000)
        detail = redact_managed_secret(str(exc.cause) or type(exc.cause).__name__)
        if isinstance(exc.cause, (ImportError, ModuleNotFoundError, FileNotFoundError)):
            return _sdk_unavailable(exc.cause)
        classified = classify_provider_failure(
            detail,
            code=type(exc.cause).__name__,
            explicit_retryable=exc.retryable,
        )
        return AgentRunOutcome.failed(
            classified.kind,
            provider=provider,
            message=detail[:1600],
            started=exc.started,
            retryable=classified.retryable,
            error_code=classified.error_code,
            retry_after_seconds=classified.retry_after_seconds,
            duration_ms=duration_ms,
            stderr_tail=detail[-1200:],
        )
    measured_ms = int(max(0.0, time.monotonic() - started_at) * 1000)
    if measured_ms > int(timeout_seconds * 1000):
        return AgentRunOutcome.failed(
            AgentFailureKind.FUTURE_TIMEOUT,
            provider=provider,
            message=f"Codex SDK exceeded the governed {timeout_seconds:g}s deadline",
            started=True,
            retryable=True,
            error_code="semantic_provider_transport_timeout",
            duration_ms=measured_ms,
        )
    if result.status != "completed":
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=f"Codex SDK returned non-completed turn status: {result.status or '<missing>'}",
            started=True,
            retryable=False,
            error_code="semantic_provider_turn_not_completed",
            request_id=result.turn_id,
            duration_ms=result.duration_ms,
        )
    payload, result_issue = _structured_result_text(result.final_response)
    if result_issue:
        return AgentRunOutcome.failed(
            AgentFailureKind.SUBPROCESS_OUTPUT_INVALID,
            provider=provider,
            message=result_issue,
            started=True,
            retryable=False,
            error_code="semantic_provider_structured_output_invalid",
            request_id=result.turn_id,
            duration_ms=result.duration_ms,
        )
    if not result.thread_id or not result.turn_id:
        return AgentRunOutcome.failed(
            AgentFailureKind.NO_RESULT,
            provider=provider,
            message="Codex SDK completed without thread and turn identities",
            started=True,
            retryable=False,
            error_code="semantic_provider_run_identity_missing",
            request_id=result.turn_id,
            duration_ms=result.duration_ms,
        )
    return AgentRunOutcome.finished(
        provider=provider,
        result_text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        agent_id="openai-codex-python-sdk",
        run_id=result.thread_id,
        request_id=result.turn_id,
        duration_ms=result.duration_ms,
        attempts=1,
        warm_attempts=1,
        completion_mode="structured_output",
    )


def run_codex_agent(ctx: object, prompt: str) -> AgentRunOutcome:
    runtime = getattr(ctx, "runtime", RuntimeEnvironment.LOCAL)
    if not isinstance(runtime, RuntimeEnvironment):
        runtime = RuntimeEnvironment(str(runtime))
    return _run_codex(
        selection=ctx.model_selection,
        runtime=runtime,
        workspace=Path.cwd(),
        prompt=prompt,
        timeout_seconds=float(active_runtime_policy().agent_timeout_seconds),
        sandbox="workspace-write",
    )


def _codex_credential_probe_in_process(
    *,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    # The generic preflight child owns the process deadline.  Retain the public
    # parameter so provider dispatch remains uniform and reject malformed input.
    if timeout_seconds is not None and float(timeout_seconds) <= 0:
        raise ValueError("Codex SDK credential timeout must be positive")
    try:
        bindings = _load_codex_sdk()
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        return {
            "source": "openai_codex_sdk",
            "present": False,
            "valid": False,
            "issues": [f"official openai-codex SDK unavailable: {type(exc).__name__}"],
        }
    try:
        with bindings.codex_class() as codex:
            account = codex.account(refresh_token=False)
    except Exception as exc:  # noqa: BLE001 -- SDK errors are classified at this boundary.
        detail = redact_managed_secret(str(exc) or type(exc).__name__)
        return {
            "source": "openai_codex_sdk",
            "present": False,
            "valid": False,
            "issues": [f"Codex SDK account probe failed: {detail[:400]}"],
        }
    valid = getattr(account, "account", None) is not None
    return {
        "source": "openai_codex_sdk",
        "present": valid,
        "valid": valid,
        "issues": [] if valid else ["Codex SDK has no authenticated account"],
    }


def codex_credential_probe(
    *,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    # Kept as the in-process SDK primitive for the isolated preflight worker and
    # unit-level adapter checks. Production preflight dispatch calls the
    # killable boundary in ``codex_probe_process``.
    return _codex_credential_probe_in_process(timeout_seconds=timeout_seconds)


def codex_startup_probe(
    *,
    model: str | CursorModelSelection,
    runtime: str,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> dict[str, object]:
    from content.execution.agent.codex_probe import codex_startup_probe as probe

    return probe(
        model=model,
        runtime=runtime,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
    )


def codex_startup_probe_suite(
    *,
    model: str | CursorModelSelection,
    runtime: str,
    attempts: int,
    timeout_seconds: float,
    cwd: Path | None = None,
    concurrency: int | None = None,
) -> dict[str, object]:
    from content.execution.agent.codex_probe import (
        codex_startup_probe_suite as probe_suite,
    )

    return probe_suite(
        model=model,
        runtime=runtime,
        attempts=attempts,
        timeout_seconds=timeout_seconds,
        cwd=cwd,
        concurrency=(
            concurrency
            if concurrency is not None
            else active_runtime_policy().cursor_bridge_instances
        ),
    )


__all__ = [
    "codex_credential_probe",
    "codex_sdk_version",
    "codex_startup_probe",
    "codex_startup_probe_suite",
    "run_codex_agent",
]

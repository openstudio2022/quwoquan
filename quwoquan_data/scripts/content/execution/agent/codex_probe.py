"""Codex credential-free startup and capacity probes."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.control_types import AgentProvider, RuntimeEnvironment
from core.cursor_model import CursorModelSelection
from core.runtime_policy import active_runtime_policy

from content.execution.agent.codex_adapter import _run_codex


def _codex_startup_probe_in_process(
    *,
    model: str | CursorModelSelection,
    runtime: str,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> dict[str, object]:
    selection = CursorModelSelection.from_value(model)
    outcome = _run_codex(
        selection=selection,
        runtime=RuntimeEnvironment(runtime),
        workspace=(cwd or Path.cwd()).resolve(),
        prompt=(
            "This is a governed startup probe. Do not modify files or call tools. "
            "Return the required structured completion response with a short summary."
        ),
        timeout_seconds=timeout_seconds,
        sandbox="read-only",
    )
    return {
        "checked": True,
        "ready": outcome.succeeded,
        "started": outcome.started,
        "provider": AgentProvider.CODEX_SDK.value,
        "runtime": runtime,
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "status": outcome.status.value,
        "errorClass": outcome.failure_kind.value if outcome.failure_kind else "",
        "errorCode": outcome.error_code,
        "retryAfterSeconds": outcome.retry_after_seconds,
        "httpStatus": None,
        "retryable": outcome.retryable,
        "cacheHit": False,
        "agentId": outcome.agent_id or None,
        "runId": outcome.run_id or None,
        "durationMs": outcome.duration_ms,
        "issues": [] if outcome.succeeded else [outcome.message],
    }


def codex_startup_probe(
    *,
    model: str | CursorModelSelection,
    runtime: str,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> dict[str, object]:
    # In-process primitive used by the dedicated killable worker and adapter
    # unit tests. Production preflight dispatch uses ``codex_probe_process``.
    return _codex_startup_probe_in_process(
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
    from content.execution.agent.codex_probe_process import run_codex_startup_probe

    resolved_concurrency = (
        concurrency
        if concurrency is not None
        else active_runtime_policy().cursor_bridge_instances
    )
    if attempts < 1 or resolved_concurrency < 1:
        raise ValueError("Codex startup suite attempts and concurrency must be positive")
    started_at = time.monotonic()
    workers = min(attempts, resolved_concurrency)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                lambda attempt: {
                    "attempt": attempt,
                    **run_codex_startup_probe(
                        model=model,
                        runtime=runtime,
                        timeout_seconds=timeout_seconds,
                        cwd=cwd,
                    ),
                },
                range(1, attempts + 1),
            )
        )
    success_count = sum(bool(row.get("ready")) for row in results)
    issues = [
        f"attempt {row['attempt']}: {issue}"
        for row in results
        for issue in row.get("issues") or []
    ]
    elapsed = max(0.001, time.monotonic() - started_at)
    return {
        "schema": "quwoquan_data.semantic_agent_startup_probe_suite",
        "provider": AgentProvider.CODEX_SDK.value,
        "attempts": attempts,
        "successCount": success_count,
        "effectiveConcurrency": workers,
        "elapsedSeconds": round(elapsed, 3),
        "probeJobsPerHour": round(success_count * 3600 / elapsed, 3),
        "bridgeDisconnectCount": 0,
        "startupLatencyP95": max(
            (float(row.get("durationMs") or 0) / 1000 for row in results),
            default=0,
        ),
        "modelCatalog": {
            "checked": False,
            "ready": True,
            "modelCount": 0,
            "modelIds": [],
            "issues": [],
        },
        "results": results,
        "issues": issues,
        "ready": success_count == attempts and not issues,
    }


__all__ = ["codex_startup_probe", "codex_startup_probe_suite"]

"""Repeated Cursor startup probe suite for admission classification."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.cursor_model import CursorModelSelection
from core.cursor_probe_classification import (
    cursor_probe_attempt_has_5xx as _cursor_probe_attempt_has_5xx,
)
from core.cursor_probe_classification import (
    cursor_probe_attempt_is_auth as _cursor_probe_attempt_is_auth,
)
from core.cursor_probe_classification import (
    cursor_probe_attempt_is_bridge_disconnect as _cursor_probe_attempt_is_bridge_disconnect,
)
from core.cursor_probe_classification import (
    cursor_probe_is_startup_timeout as _cursor_probe_is_startup_timeout,
)
from core.cursor_probe_classification import (
    p95 as _p95,
)
from core.cursor_startup_probe import cursor_startup_probe
from core.python_environment import (
    DEFAULT_SEMANTIC_AGENT_MODEL,
    DEFAULT_SEMANTIC_AGENT_RUNTIME,
    _redact_secret_text,
    _redact_secret_value,
)
from core.runtime_policy import active_runtime_policy


def cursor_startup_probe_suite(
    *,
    model: str | CursorModelSelection = DEFAULT_SEMANTIC_AGENT_MODEL,
    runtime: str = DEFAULT_SEMANTIC_AGENT_RUNTIME,
    attempts: int | None = None,
    timeout_seconds: float | None = None,
    cwd: Path | None = None,
    include_catalog: bool = False,
) -> dict:
    """Run repeated Cursor startup probes and classify admission blockers.

    This is the formal P0 report used before scaled authoring.  A single
    preflight can hide intermittent startup failures; the suite assigns each
    attempt exactly one *primary* class with precedence
    ``ready > auth > startupTimeout > true5xx > bridgeDisconnect > other`` so
    that a probe whose final verdict is a subprocess timeout is bucketed as
    ``startupTimeout`` and is **never** counted as ``true5xx`` (cold-start 5xx
    sub-attempts under a timeout are not a stable backend 5xx verdict).
    """
    runtime_policy = active_runtime_policy()
    selection = CursorModelSelection.from_value(model)
    total = int(
        attempts
        if attempts is not None
        else runtime_policy.startup_probe_suite_attempts
    )
    effective_timeout_seconds = float(
        timeout_seconds
        if timeout_seconds is not None
        else runtime_policy.startup_timeout_seconds
    )
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    suite_started = time.monotonic()
    if include_catalog:
        from core.cursor_workspace_probe import cursor_model_catalog

        # The catalog must prove this exact model/parameter binding, not merely
        # that some model list came back: a reasoning tier such as effort=xhigh
        # exists only on some model versions.
        catalog = cursor_model_catalog(selection)
    else:
        catalog = None
    rows: list[dict] = []
    latencies: list[float] = []
    success_count = 0
    auth_failures = 0
    true_5xx_count = 0
    startup_timeout_count = 0
    bridge_disconnect_count = 0
    cold_start_5xx_observed = 0
    # 探针按调用方明确请求的 attempt 数全部发起。这里观测真实 Provider/主机
    # 行为，不再用 runtime profile 中未经实测证明的 bridge 数预先限流。
    worker_limit = total
    active_workers = 0
    maximum_active_workers = 0
    active_lock = threading.Lock()

    def run_probe(index: int) -> tuple[int, dict, float]:
        nonlocal active_workers, maximum_active_workers
        with active_lock:
            active_workers += 1
            maximum_active_workers = max(maximum_active_workers, active_workers)
        begin = time.monotonic()
        try:
            payload = cursor_startup_probe(
                model=selection,
                runtime=runtime,
                timeout_seconds=effective_timeout_seconds,
                cwd=cwd,
            )
        except Exception as exc:  # noqa: BLE001 - external SDK boundary
            payload = {
                "ready": False,
                "status": "error",
                "errorClass": type(exc).__name__,
                "error": _redact_secret_text(str(exc)),
            }
        finally:
            with active_lock:
                active_workers -= 1
        return index, payload, round(time.monotonic() - begin, 4)

    with ThreadPoolExecutor(max_workers=worker_limit) as executor:
        futures = [executor.submit(run_probe, index) for index in range(1, total + 1)]
        outcomes = [future.result() for future in as_completed(futures)]

    for index, payload, elapsed in outcomes:
        latencies.append(elapsed)
        ready = bool(payload.get("ready"))
        has_auth = _cursor_probe_attempt_is_auth(payload)
        is_startup_timeout = _cursor_probe_is_startup_timeout(payload)
        raw_5xx = _cursor_probe_attempt_has_5xx(payload)
        has_bridge_disconnect = _cursor_probe_attempt_is_bridge_disconnect(payload)
        # 单一 primary 归类（互斥），timeout 优先于 5xx：终态超时不计 5xx。
        if ready:
            primary = "ready"
        elif has_auth:
            primary = "auth"
        elif is_startup_timeout:
            primary = "startupTimeout"
        elif raw_5xx:
            primary = "true5xx"
        elif has_bridge_disconnect:
            primary = "bridgeDisconnect"
        else:
            primary = "other"
        if primary == "ready":
            success_count += 1
        elif primary == "auth":
            auth_failures += 1
        elif primary == "startupTimeout":
            startup_timeout_count += 1
        elif primary == "true5xx":
            true_5xx_count += 1
        elif primary == "bridgeDisconnect":
            bridge_disconnect_count += 1
        if raw_5xx:
            cold_start_5xx_observed += 1
        rows.append(
            {
                "attempt": index,
                "ready": ready,
                "latencySeconds": elapsed,
                "status": payload.get("status"),
                "errorClass": _redact_secret_value(payload.get("errorClass")),
                "errorCode": payload.get("errorCode"),
                "httpStatus": payload.get("httpStatus"),
                "agentId": payload.get("agentId"),
                "runId": payload.get("runId"),
                "sdkVersion": payload.get("sdkVersion"),
                "primaryClass": primary,
                "authFailure": primary == "auth",
                "startupTimeout": primary == "startupTimeout",
                "true5xx": primary == "true5xx",
                "bridgeDisconnect": primary == "bridgeDisconnect",
                "coldStart5xxObserved": raw_5xx,
                "attemptCount": payload.get("attemptCount"),
            }
        )
    rows.sort(key=lambda row: int(row["attempt"]))
    elapsed_seconds = round(time.monotonic() - suite_started, 4)
    probe_jobs_per_hour = (
        round((success_count / elapsed_seconds) * 3600, 4)
        if elapsed_seconds > 0
        else 0.0
    )
    true_5xx_rate = round(true_5xx_count / total, 4)
    startup_timeout_rate = round(startup_timeout_count / total, 4)
    bridge_disconnect_rate = round(bridge_disconnect_count / total, 4)
    issues: list[str] = []
    if auth_failures:
        issues.append(f"Cursor auth failures observed: {auth_failures}/{total}")
    if true_5xx_rate >= runtime_policy.cursor_true_5xx_rate_limit:
        issues.append(
            f"Cursor true 5xx rate {true_5xx_rate:.2%} >= "
            f"{runtime_policy.cursor_true_5xx_rate_limit:.0%}"
        )
    if startup_timeout_rate >= runtime_policy.cursor_startup_timeout_rate_limit:
        issues.append(
            f"Cursor startup timeout rate {startup_timeout_rate:.2%} >= "
            f"{runtime_policy.cursor_startup_timeout_rate_limit:.0%} "
            f"(raise --startup-timeout-seconds / warm bridge reuse; not a backend 5xx)"
        )
    if success_count == 0:
        issues.append("Cursor startup probe never succeeded")
    if catalog is not None and not catalog.get("ready"):
        issues.extend(str(issue) for issue in catalog.get("issues") or [])
    return {
        "schema": "quwoquan_data.cursor_startup_probe_suite",
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "modelCatalog": catalog,
        "runtime": runtime,
        "attempts": total,
        "timeoutSeconds": round(effective_timeout_seconds, 4),
        "successCount": success_count,
        "authFailures": auth_failures,
        "true5xxCount": true_5xx_count,
        "true5xxRate": true_5xx_rate,
        "startupTimeoutCount": startup_timeout_count,
        "startupTimeoutRate": startup_timeout_rate,
        "coldStart5xxObservedCount": cold_start_5xx_observed,
        "bridgeDisconnectCount": bridge_disconnect_count,
        "bridgeDisconnectRate": bridge_disconnect_rate,
        "startupLatencyP95": _p95(latencies),
        "elapsedSeconds": elapsed_seconds,
        "configuredConcurrency": worker_limit,
        "effectiveConcurrency": maximum_active_workers,
        "probeJobsPerHour": probe_jobs_per_hour,
        "unrecoveredFailures": total - success_count,
        "ready": not issues,
        "issues": issues,
        "startedAt": started_at,
        "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": rows,
    }

"""Compose data-runtime, credential, network, and Cursor startup admission checks."""
from __future__ import annotations

from typing import Iterable

from core.cursor_startup_cache import cached_cursor_startup_probe
from core.python_environment import (
    DEFAULT_CURSOR_STARTUP_MODEL,
    DEFAULT_CURSOR_STARTUP_RUNTIME,
    runtime_report,
)
from core.python_network import check_network_endpoints
from core.runtime_policy import active_runtime_policy

def environment_preflight(
    *,
    require_cursor_key: bool = True,
    check_network: bool = True,
    endpoints: Iterable[str] | None = None,
    timeout_seconds: float | None = None,
    check_cursor_startup: bool = False,
    cursor_startup_model: str | None = None,
    cursor_startup_runtime: str | None = None,
    cursor_startup_timeout_seconds: float | None = None,
) -> dict:
    """Single pre-run readiness gate for managed data workflows."""
    policy = active_runtime_policy()
    effective_timeout_seconds = float(
        timeout_seconds
        if timeout_seconds is not None
        else policy.preflight_network_timeout_seconds
    )
    effective_startup_model = cursor_startup_model or policy.cursor_model
    effective_startup_runtime = cursor_startup_runtime or policy.cursor_runtime.value
    effective_startup_timeout_seconds = float(
        cursor_startup_timeout_seconds
        if cursor_startup_timeout_seconds is not None
        else policy.startup_timeout_seconds
    )
    credential_issues: list[str] = []
    if require_cursor_key:
        try:
            from core.cursor_credentials import cursor_key_file_issues, resolve_cursor_api_key
        except Exception:  # noqa: BLE001
            from cursor_credentials import cursor_key_file_issues, resolve_cursor_api_key  # type: ignore
        credential_issues = cursor_key_file_issues()
        if not credential_issues:
            resolve_cursor_api_key()
    runtime = runtime_report()
    cursor_key = (
        {
            "source": "key_file" if not credential_issues else "missing",
            "present": not credential_issues,
            "valid": not credential_issues,
            "issues": credential_issues,
        }
        if require_cursor_key
        else {"source": "not_checked", "present": False, "valid": False, "issues": []}
    )
    issues: list[str] = []
    if not runtime.get("ready"):
        issues.append(
            "agent runtime missing: run `python3 quwoquan_data/scripts/cli.py task preflight`"
        )
    if require_cursor_key:
        issues.extend(credential_issues)
    local_blocked = bool(issues)
    if check_network and not local_blocked:
        network = check_network_endpoints(
            endpoints=endpoints,
            timeout_seconds=effective_timeout_seconds,
        )
        issues.extend(network.get("issues") or [])
    else:
        network = {
            "checked": False,
            "skipped": True,
            "skipReason": "disabled" if not check_network else "local_preflight_failed",
            "ready": True,
            "endpoints": [],
            "issues": [],
        }
    if check_cursor_startup and not issues and require_cursor_key:
        cursor_startup = cached_cursor_startup_probe(
            model=effective_startup_model,
            runtime=effective_startup_runtime,
            timeout_seconds=effective_startup_timeout_seconds,
        )
        issues.extend(cursor_startup.get("issues") or [])
    else:
        cursor_startup = {
            "checked": False,
            "ready": True,
            "started": False,
            "runtime": effective_startup_runtime,
            "model": effective_startup_model,
            "issues": [],
            "skipReason": (
                "disabled"
                if not check_cursor_startup
                else "local_preflight_failed_or_cursor_key_not_required"
            ),
        }
    return {
        "schema": "quwoquan_data.environment_preflight",
        "runtime": runtime,
        "cursorApiKey": cursor_key,
        "network": network,
        "cursorStartup": cursor_startup,
        "ready": not issues,
        "issues": issues,
    }

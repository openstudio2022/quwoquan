"""Provider-neutral credential, startup, soak and workspace preflight dispatch."""
from __future__ import annotations

import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.control_types import AgentProvider
from core.cursor_model import CursorModelSelection
from core.python_environment import (
    agent_requirements_path,
    agent_runtime_modules,
    resolve_python_for_modules,
    runtime_report,
)
from core.python_network import check_network_endpoints
from core.runtime_policy import active_runtime_policy

_CODEX_NETWORK_ENDPOINTS = (
    "https://chatgpt.com/",
    "https://www.wikipedia.org/",
    "https://commons.wikimedia.org/",
)


def _provider(value: AgentProvider | str | None) -> AgentProvider:
    if isinstance(value, AgentProvider):
        return value
    if value is None:
        return active_runtime_policy().semantic_agent_provider
    return AgentProvider(str(value))


def semantic_agent_credential_probe(
    provider: AgentProvider | str | None = None,
) -> dict[str, object]:
    resolved = _provider(provider)
    if resolved is AgentProvider.CURSOR_SDK:
        from core.cursor_credentials import cursor_key_file_issues

        issues = cursor_key_file_issues()
        return {
            "provider": resolved.value,
            "source": "key_file" if not issues else "missing",
            "present": not issues,
            "valid": not issues,
            "issues": issues,
        }
    if resolved is AgentProvider.CODEX_SDK:
        from content.execution.agent.codex_probe_process import (
            run_codex_credential_probe,
        )

        return {
            "provider": resolved.value,
            **run_codex_credential_probe(
                timeout_seconds=float(active_runtime_policy().startup_timeout_seconds)
            ),
        }
    raise ValueError(f"unsupported semantic agent provider: {resolved.value}")


def semantic_agent_startup_probe(
    *,
    provider: AgentProvider | str | None,
    model: str | CursorModelSelection,
    runtime: str,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> dict[str, object]:
    resolved = _provider(provider)
    selection = CursorModelSelection.from_value(model)
    if resolved is AgentProvider.CURSOR_SDK:
        if cwd is None:
            from core.cursor_startup_cache import cached_cursor_startup_probe

            report = cached_cursor_startup_probe(
                model=selection,
                runtime=runtime,
                timeout_seconds=timeout_seconds,
            )
        else:
            from core.cursor_startup_probe import cursor_startup_probe

            report = cursor_startup_probe(
                model=selection,
                runtime=runtime,
                timeout_seconds=timeout_seconds,
                cwd=cwd,
            )
    elif resolved is AgentProvider.CODEX_SDK:
        from content.execution.agent.codex_probe_process import (
            run_codex_startup_probe,
        )

        report = run_codex_startup_probe(
            model=selection,
            runtime=runtime,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
        )
    else:  # pragma: no cover - AgentProvider is closed
        raise ValueError(f"unsupported semantic agent provider: {resolved.value}")
    result = {"provider": resolved.value, **dict(report)}
    if bool(result.get("ready")):
        from content.execution.agent.capacity_broker import SemanticCapacityBroker

        SemanticCapacityBroker().close_circuit(resolved)
    return result


def semantic_agent_environment_preflight(
    *,
    provider: AgentProvider | str | None = None,
    require_credential: bool = True,
    check_network: bool = True,
    endpoints: Iterable[str] | None = None,
    timeout_seconds: float | None = None,
    check_startup: bool = False,
    startup_model: str | CursorModelSelection | None = None,
    startup_runtime: str | None = None,
    startup_timeout_seconds: float | None = None,
) -> dict[str, object]:
    policy = active_runtime_policy()
    resolved = _provider(provider)
    selection = CursorModelSelection.from_value(
        startup_model or policy.semantic_agent_model_selection
    )
    runtime = str(startup_runtime or policy.semantic_agent_runtime.value)
    network_timeout = float(
        timeout_seconds
        if timeout_seconds is not None
        else policy.preflight_network_timeout_seconds
    )
    startup_timeout = float(
        startup_timeout_seconds
        if startup_timeout_seconds is not None
        else policy.startup_timeout_seconds
    )
    runtime_status = runtime_report()
    provider_modules = agent_runtime_modules(resolved)
    provider_python = resolve_python_for_modules(provider_modules)
    runtime_status.update(
        {
            "requirements": str(agent_requirements_path(resolved)),
            "agentModules": list(provider_modules),
            "resolvedPython": str(provider_python) if provider_python else None,
            "provider": resolved.value,
            "providerModulesReady": provider_python is not None,
        }
    )
    runtime_status["ready"] = bool(runtime_status.get("ready")) and provider_python is not None
    credential = (
        semantic_agent_credential_probe(resolved)
        if require_credential
        else {
            "provider": resolved.value,
            "source": "not_checked",
            "present": False,
            "valid": False,
            "issues": [],
        }
    )
    issues: list[str] = []
    if not runtime_status.get("ready"):
        issues.append(
            "agent runtime missing: run `python3 quwoquan_data/scripts/cli.py task preflight`"
        )
    if require_credential:
        issues.extend(str(item) for item in credential.get("issues") or [])
    if check_network and not issues:
        effective_endpoints = endpoints
        if effective_endpoints is None and resolved is AgentProvider.CODEX_SDK:
            effective_endpoints = _CODEX_NETWORK_ENDPOINTS
        network = check_network_endpoints(
            endpoints=effective_endpoints,
            timeout_seconds=network_timeout,
        )
        issues.extend(str(item) for item in network.get("issues") or [])
    else:
        network = {
            "checked": False,
            "skipped": True,
            "skipReason": "disabled" if not check_network else "local_preflight_failed",
            "ready": True,
            "endpoints": [],
            "issues": [],
        }
    if check_startup and not issues and require_credential:
        startup = semantic_agent_startup_probe(
            provider=resolved,
            model=selection,
            runtime=runtime,
            timeout_seconds=startup_timeout,
        )
        issues.extend(str(item) for item in startup.get("issues") or [])
    else:
        startup = {
            "checked": False,
            "ready": True,
            "started": False,
            "provider": resolved.value,
            "runtime": runtime,
            "model": selection.model_id,
            "modelParameters": selection.parameters_document(),
            "issues": [],
            "skipReason": (
                "disabled"
                if not check_startup
                else "local_preflight_failed_or_credential_not_required"
            ),
        }
    return {
        "schema": "quwoquan_data.environment_preflight",
        "provider": resolved.value,
        "runtime": runtime_status,
        "semanticAgentCredential": credential,
        "network": network,
        "semanticAgentStartup": startup,
        "ready": not issues,
        "issues": issues,
    }


def semantic_agent_probe_suite(
    *,
    provider: AgentProvider | str | None,
    model: str | CursorModelSelection,
    runtime: str,
    attempts: int,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> dict[str, object]:
    resolved = _provider(provider)
    policy = active_runtime_policy()
    if resolved is AgentProvider.CURSOR_SDK:
        from core.cursor_startup_probe_suite import cursor_startup_probe_suite

        report = cursor_startup_probe_suite(
            model=model,
            runtime=runtime,
            attempts=attempts,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            include_catalog=True,
        )
    elif resolved is AgentProvider.CODEX_SDK:
        from content.execution.agent.codex_adapter import codex_startup_probe_suite

        report = codex_startup_probe_suite(
            model=model,
            runtime=runtime,
            attempts=attempts,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            concurrency=min(attempts, policy.campaign_lane_workers),
        )
    else:  # pragma: no cover
        raise ValueError(f"unsupported semantic agent provider: {resolved.value}")
    return {"provider": resolved.value, **dict(report)}


def semantic_agent_workspace_probe_suite(
    *,
    provider: AgentProvider | str | None,
    workspaces: list[Path],
    model: str | CursorModelSelection,
    runtime: str,
    timeout_seconds: float,
) -> dict[str, object]:
    resolved = _provider(provider)
    if resolved is AgentProvider.CURSOR_SDK:
        from core.cursor_workspace_probe import cursor_workspace_probe_suite

        return {
            "provider": resolved.value,
            **cursor_workspace_probe_suite(
                workspaces=workspaces,
                model=model,
                runtime=runtime,
                timeout_seconds=timeout_seconds,
            ),
        }
    started_at = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, len(workspaces))) as pool:
        rows = list(
            pool.map(
                lambda item: {
                    "lane": item.name,
                    "workspace": str(item),
                    **semantic_agent_startup_probe(
                        provider=resolved,
                        model=model,
                        runtime=runtime,
                        timeout_seconds=timeout_seconds,
                        cwd=item,
                    ),
                },
                workspaces,
            )
        )
    success_count = sum(bool(row.get("ready")) for row in rows)
    issues = [
        f"{row['lane']}: {issue}"
        for row in rows
        for issue in row.get("issues") or []
    ]
    return {
        "schema": "quwoquan_data.semantic_agent_workspace_probe_suite",
        "provider": resolved.value,
        "workspaceCount": len(workspaces),
        "successCount": success_count,
        "configuredConcurrency": len(workspaces),
        "effectiveConcurrency": len(workspaces),
        "elapsedSeconds": round(max(0.0, time.monotonic() - started_at), 3),
        "runs": rows,
        "issues": issues,
        "ready": success_count == len(workspaces) and not issues,
    }


__all__ = [
    "semantic_agent_credential_probe",
    "semantic_agent_environment_preflight",
    "semantic_agent_probe_suite",
    "semantic_agent_startup_probe",
    "semantic_agent_workspace_probe_suite",
]

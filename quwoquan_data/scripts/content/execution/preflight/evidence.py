"""Redacted, compact preflight evidence projection."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def compact_ready_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project runtime readiness without credentials or verbose probe payloads."""

    prepare = _mapping(report.get("prepare"))
    preflight = _mapping(report.get("preflight"))
    runtime = _mapping(preflight.get("runtime"))
    credential = _mapping(report.get("semanticAgentCredential"))
    network = _mapping(preflight.get("network"))
    startup = _mapping(report.get("semanticAgentStartup"))
    capacity = _mapping(report.get("capacitySoak"))
    workspace_smoke = _mapping(report.get("workspaceSmoke"))
    catalog = _mapping(capacity.get("modelCatalog"))
    startup_catalog = _mapping(preflight.get("modelCatalog"))
    capacity_runs = [
        {
            "attempt": row.get("attempt"),
            "status": row.get("status"),
            "agentId": row.get("agentId"),
            "runId": row.get("runId"),
            "sdkVersion": row.get("sdkVersion"),
        }
        for row in capacity.get("results") or []
        if isinstance(row, Mapping)
    ]
    return {
        "ready": bool(report.get("ready")),
        "semanticSelectionId": report.get("semanticSelectionId"),
        "selectionDigest": report.get("selectionDigest"),
        "provider": report.get("provider") or preflight.get("provider"),
        "model": report.get("model"),
        "modelParameters": list(report.get("modelParameters") or []),
        "semanticRuntime": report.get("semanticRuntime"),
        "runtimeProfileId": report.get("runtimeProfileId"),
        "runtimeProfileDigest": report.get("runtimeProfileDigest"),
        "requiresNewRetryOf": bool(report.get("requiresNewRetryOf")),
        "fallbackPolicy": report.get("fallbackPolicy"),
        "runtime": {
            "ready": bool(prepare.get("ready")) and bool(runtime.get("ready")),
            "python": runtime.get("resolvedPython") or prepare.get("python"),
            "missing": list(runtime.get("missing") or prepare.get("missing") or []),
        },
        "credential": {
            "provider": credential.get("provider"),
            "source": credential.get("source") or "missing",
            "present": bool(credential.get("present")),
            "valid": bool(credential.get("valid")),
            "issues": list(credential.get("issues") or []),
        },
        "network": {
            "checked": bool(network.get("checked")),
            "ready": bool(network.get("checked")) and bool(network.get("ready")),
            "skipped": bool(network.get("skipped")),
            "issues": list(network.get("issues") or []),
        },
        "semanticAgentStartup": {
            "provider": startup.get("provider"),
            "checked": bool(startup.get("checked")),
            "ready": bool(startup.get("checked")) and bool(startup.get("ready")),
            "runtime": startup.get("runtime"),
            "model": startup.get("model"),
            "agentId": startup.get("agentId"),
            "runId": startup.get("runId"),
            "sdkVersion": startup.get("sdkVersion"),
            "issues": list(startup.get("issues") or []),
        },
        "modelCatalog": {
            "checked": bool(startup_catalog.get("checked")),
            "ready": bool(startup_catalog.get("ready")),
            "modelCount": startup_catalog.get("modelCount"),
            "selectionSupport": _mapping(startup_catalog.get("selectionSupport"))
            or {"checked": False, "supported": True, "issues": []},
            "issues": list(startup_catalog.get("issues") or []),
        },
        "capacitySoak": {
            "semanticSelectionId": capacity.get("semanticSelectionId"),
            "selectionDigest": capacity.get("selectionDigest"),
            "provider": capacity.get("provider"),
            "model": capacity.get("model"),
            "modelParameters": list(capacity.get("modelParameters") or []),
            "runtimeProfileDigest": capacity.get("runtimeProfileDigest"),
            "ready": bool(capacity.get("ready")),
            "attempts": capacity.get("attempts"),
            "successCount": capacity.get("successCount"),
            "effectiveConcurrency": capacity.get("effectiveConcurrency"),
            "bridgeDisconnectCount": capacity.get("bridgeDisconnectCount"),
            "probeJobsPerHour": capacity.get("probeJobsPerHour"),
            "startupLatencyP95": capacity.get("startupLatencyP95"),
            "modelCatalog": {
                "ready": bool(catalog.get("ready")),
                "sdkVersion": catalog.get("sdkVersion"),
                "modelCount": catalog.get("modelCount"),
                "modelIds": list(catalog.get("modelIds") or []),
                "autoSelection": catalog.get("autoSelection") or {},
                "selectionSupport": catalog.get("selectionSupport") or {},
                "issues": list(catalog.get("issues") or []),
            },
            "runs": capacity_runs,
            "issues": list(capacity.get("issues") or []),
        },
        "workspaceSmoke": {
            "ready": bool(workspace_smoke.get("ready")),
            "workspaceCount": workspace_smoke.get("workspaceCount"),
            "successCount": workspace_smoke.get("successCount"),
            "configuredConcurrency": workspace_smoke.get("configuredConcurrency"),
            "effectiveConcurrency": workspace_smoke.get("effectiveConcurrency"),
            "elapsedSeconds": workspace_smoke.get("elapsedSeconds"),
            "cleanupStatus": workspace_smoke.get("cleanupStatus"),
            "runs": [
                {
                    "lane": row.get("lane"),
                    "workspace": row.get("workspace"),
                    "status": row.get("status"),
                    "agentId": row.get("agentId"),
                    "runId": row.get("runId"),
                    "sdkVersion": row.get("sdkVersion"),
                    "startedAt": row.get("startedAt"),
                    "finishedAt": row.get("finishedAt"),
                }
                for row in workspace_smoke.get("runs") or []
                if isinstance(row, Mapping)
            ],
            "issues": list(workspace_smoke.get("issues") or []),
        },
        "issues": list(preflight.get("issues") or []),
    }


__all__ = ["compact_ready_evidence"]

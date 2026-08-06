"""Human-readable printers for task preflight CLI reports."""
from __future__ import annotations

import json
import sys


def _print_preflight(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    runtime = report.get("runtime") or {}
    credential = report.get("semanticAgentCredential") or {}
    network = report.get("network") or {}
    print(f"[env preflight] runtime={'ready' if runtime.get('ready') else 'missing'}")
    print(f"[env preflight] resolvedPython={runtime.get('resolvedPython') or '<missing>'}")
    credential_status = "present" if credential.get("present") else "missing"
    if credential.get("present") and not credential.get("valid"):
        credential_status = "invalid"
    print(
        f"[env preflight] semanticSelectionId="
        f"{report.get('semanticSelectionId') or '<missing>'} "
        f"provider={report.get('provider') or '<missing>'} "
        f"credentialSource={credential.get('source') or 'missing'} "
        f"status={credential_status}"
    )
    if network.get("skipped"):
        print(f"[env preflight] network=skipped ({network.get('skipReason')})")
    else:
        print(f"[env preflight] network={'ready' if network.get('ready') else 'failed'}")
        for row in network.get("endpoints") or []:
            status = row.get("status") or row.get("error") or ""
            marker = "ok" if row.get("reachable") else "fail"
            print(f"  - {marker}: {row.get('url')} {status}")
    startup = report.get("semanticAgentStartup") or {}
    if startup.get("checked"):
        print(
            "[env preflight] semanticAgentStartup="
            + ("ready" if startup.get("ready") else "failed")
            + f" model={startup.get('model')} runtime={startup.get('runtime')}"
        )
    elif startup:
        print(
            "[env preflight] semanticAgentStartup=skipped "
            f"({startup.get('skipReason')})"
        )
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def _print_semantic_agent_probe(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(
        "[env semantic-agent-probe] "
        f"attempts={report.get('attempts')} success={report.get('successCount')} "
        f"authFailures={report.get('authFailures')} "
        f"true5xxRate={report.get('true5xxRate')} "
        f"startupTimeoutRate={report.get('startupTimeoutRate')} "
        f"coldStart5xxObserved={report.get('coldStart5xxObservedCount')} "
        f"bridgeDisconnectRate={report.get('bridgeDisconnectRate')} "
        f"startupLatencyP95={report.get('startupLatencyP95')}"
    )
    catalog = report.get("modelCatalog") or {}
    if catalog.get("checked"):
        print(
            "[env semantic-agent-probe] "
            f"sdkVersion={catalog.get('sdkVersion') or '<unknown>'} "
            f"accountModels={catalog.get('modelCount') or 0} "
            "autoSelection=auto"
        )
    print(
        "[env semantic-agent-probe] READY"
        if report.get("ready")
        else "[env semantic-agent-probe] FAILED"
    )
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def _print_semantic_agent_workspace_smoke(report: dict) -> None:
    print(
        "[env semantic-agent-workspace-smoke] "
        f"workspaces={report.get('workspaceCount')} "
        f"success={report.get('successCount')} "
        f"effectiveConcurrency={report.get('effectiveConcurrency')} "
        f"cleanup={report.get('cleanupStatus')}"
    )
    print(
        "[env semantic-agent-workspace-smoke] READY"
        if report.get("ready")
        else "[env semantic-agent-workspace-smoke] FAILED"
    )
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)



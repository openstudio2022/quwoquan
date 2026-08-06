"""`qwq-data task preflight` — data runtime preparation and diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from core.control_types import AgentProvider
from core.paths import DATA_EXECUTIONS_ROOT, DATA_LOCAL_ROOT
from core.python_environment import prepare_data_runtime_cache
from core.runtime_policy import active_runtime_policy

from content.execution.preflight.evidence import compact_ready_evidence
from content.execution.preflight.receipt import (
    build_semantic_preflight_receipt,
    write_semantic_preflight_receipt,
)
from content.execution.preflight.runtime import prepare_selected_runtime
from content.execution.preflight.selection import (
    CALIBRATION_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    SemanticPreflightSelection,
    bind_semantic_preflight_selection,
    resolve_semantic_preflight_selection,
)
from content.execution.preflight.semantic_provider import (
    semantic_agent_environment_preflight,
    semantic_agent_probe_suite,
    semantic_agent_workspace_probe_suite,
)

_RUNTIME_CHILD_ENV = "QWQ_DATA_PREFLIGHT_RUNTIME_CHILD"


def _network_timeout_seconds(args: argparse.Namespace) -> float:
    return float(active_runtime_policy().preflight_network_timeout_seconds)


def _report_output_path(value: object) -> Path:
    """Allow preflight evidence only in its execution or disposable cache owner."""
    output = Path(str(value)).expanduser().resolve()
    data_output = DATA_EXECUTIONS_ROOT.parent.resolve()
    try:
        output.relative_to(data_output)
    except ValueError:
        return output
    allowed_roots = (DATA_EXECUTIONS_ROOT.resolve(), (DATA_LOCAL_ROOT / "cache").resolve())
    if any(output.is_relative_to(root) for root in allowed_roots):
        return output
    raise SystemExit(
        "[task preflight] GATE_BLOCK: data runtime evidence must be under "
        "tasks/<executionId>/... or data/local/cache/..."
    )


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


def _resolved_selection(args: argparse.Namespace) -> SemanticPreflightSelection:
    return resolve_semantic_preflight_selection(
        getattr(args, "semantic_selection_id", DEFAULT_SEMANTIC_SELECTION_ID)
    )


def _capacity_soak_report(
    selection: SemanticPreflightSelection | None = None,
) -> dict:
    """Run the active provider capacity probe from the runtime policy."""
    policy = active_runtime_policy()
    resolved = selection or resolve_semantic_preflight_selection(
        DEFAULT_SEMANTIC_SELECTION_ID,
        policy=policy,
    )
    provider = resolved.provider
    report = semantic_agent_probe_suite(
        provider=provider,
        model=resolved.model_selection,
        runtime=resolved.runtime.value,
        attempts=policy.startup_probe_suite_attempts,
        timeout_seconds=policy.startup_timeout_seconds,
        cwd=Path.cwd(),
    )
    issues = list(report.get("issues") or [])
    if int(report.get("successCount") or 0) != policy.startup_probe_suite_attempts:
        issues.append(
            "capacity probe requires every semantic-agent job to finish: "
            f"{report.get('successCount')}/{policy.startup_probe_suite_attempts}"
        )
    required_concurrency = (
        policy.cursor_bridge_instances
        if provider is AgentProvider.CURSOR_SDK
        else policy.campaign_lane_workers
    )
    if int(report.get("effectiveConcurrency") or 0) < required_concurrency:
        issues.append(
            "capacity probe effective concurrency is below runtime policy: "
            f"{report.get('effectiveConcurrency')}<{required_concurrency}"
        )
    if int(report.get("bridgeDisconnectCount") or 0):
        issues.append(
            "capacity probe observed unrecovered provider disconnects"
        )
    report["capacityContract"] = {
        "attempts": policy.startup_probe_suite_attempts,
        "semanticSelectionId": resolved.selection_id,
        "selectionDigest": resolved.selection_digest,
        "provider": provider.value,
        "model": resolved.model_selection.model_id,
        "modelParameters": resolved.model_selection.parameters_document(),
        "runtime": resolved.runtime.value,
        "runtimeProfileId": resolved.runtime_profile_id,
        "runtimeProfileDigest": resolved.runtime_profile_digest,
        "requiredConcurrency": required_concurrency,
        "startupTimeoutSeconds": policy.startup_timeout_seconds,
    }
    report["issues"] = list(dict.fromkeys(str(issue) for issue in issues if str(issue)))
    report["ready"] = not report["issues"]
    return bind_semantic_preflight_selection(report, resolved)


def _workspace_smoke_report(
    selection: SemanticPreflightSelection | None = None,
) -> dict:
    """Exercise four independent campaign-lane workspaces concurrently."""
    from content.execution.campaign_process import CAMPAIGN_CARRIERS

    policy = active_runtime_policy()
    resolved = selection or resolve_semantic_preflight_selection(
        DEFAULT_SEMANTIC_SELECTION_ID,
        policy=policy,
    )
    smoke_parent = DATA_LOCAL_ROOT / "cache/semantic-agent/workspace-smoke"
    smoke_parent.mkdir(parents=True, exist_ok=True)
    smoke_path: Path | None = None
    with tempfile.TemporaryDirectory(
        prefix="semantic-agent-",
        dir=smoke_parent,
    ) as temporary:
        smoke_path = Path(temporary)
        workspaces: list[Path] = []
        for carrier in CAMPAIGN_CARRIERS:
            workspace = smoke_path / carrier
            workspace.mkdir()
            workspaces.append(workspace)
        report = semantic_agent_workspace_probe_suite(
            provider=resolved.provider,
            workspaces=workspaces,
            model=resolved.model_selection,
            runtime=resolved.runtime.value,
            timeout_seconds=policy.startup_timeout_seconds,
        )
    cleanup_status = (
        "cleaned"
        if smoke_path is not None and not smoke_path.exists()
        else "failed"
    )
    report["cleanupStatus"] = cleanup_status
    if cleanup_status != "cleaned":
        report["ready"] = False
        report.setdefault("issues", []).append(
            "semantic-agent workspace smoke temporary workspaces were not cleaned"
        )
    return bind_semantic_preflight_selection(report, resolved)


def _semantic_agent_startup_enabled(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "no_semantic_agent_startup", False)):
        return False
    return bool(getattr(args, "semantic_agent_startup", False))


def _startup_timeout_seconds(args: argparse.Namespace) -> float:
    return float(active_runtime_policy().startup_timeout_seconds)


def _reliabletask_fleet_report() -> dict:
    from content.execution.reliabletask_fleet import reliabletask_fleet_preflight

    try:
        report = reliabletask_fleet_preflight()
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "checked": True,
            "ready": False,
            "issues": [f"ReliableTask fleet preflight failed: {type(exc).__name__}"],
        }
    return {
        "checked": True,
        "ready": bool(report.get("ready")),
        "target": report.get("target"),
        "mongo": bool(report.get("mongo")),
        "redis": bool(report.get("redis")),
        "owned": bool(report.get("owned")),
        "issues": list(report.get("issues") or []),
    }


def _apply_reliabletask_fleet_gate(
    report: dict,
    _args: argparse.Namespace | None = None,
) -> dict:
    existing = report.get("reliableTaskFleet")
    fleet = (
        dict(existing)
        if isinstance(existing, dict) and existing.get("checked") is True
        else _reliabletask_fleet_report()
    )
    report["reliableTaskFleet"] = fleet
    fleet_ready = all(
        fleet.get(field) is True
        for field in ("checked", "ready", "mongo", "redis", "owned")
    )
    if not fleet_ready:
        report["ready"] = False
        issues = report.setdefault("issues", [])
        if isinstance(issues, list):
            issues.extend(str(item) for item in fleet.get("issues") or [])
    return report


def handle_preflight(args: argparse.Namespace) -> None:
    selection = _resolved_selection(args)
    report = semantic_agent_environment_preflight(
        provider=selection.provider,
        require_credential=not bool(getattr(args, "no_semantic_agent_credential", False)),
        check_network=not bool(getattr(args, "no_network", False)),
        endpoints=getattr(args, "endpoint", None),
        timeout_seconds=_network_timeout_seconds(args),
        check_startup=_semantic_agent_startup_enabled(args),
        startup_model=selection.model_selection,
        startup_runtime=selection.runtime.value,
        startup_timeout_seconds=_startup_timeout_seconds(args),
    )
    bind_semantic_preflight_selection(report, selection)
    _apply_reliabletask_fleet_gate(report, args)
    _print_preflight(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def handle_semantic_agent_probe(args: argparse.Namespace) -> None:
    selection = _resolved_selection(args)
    report = semantic_agent_probe_suite(
        provider=selection.provider,
        model=selection.model_selection,
        runtime=selection.runtime.value,
        attempts=int(
            getattr(args, "attempts", None)
            or active_runtime_policy().startup_probe_suite_attempts
        ),
        timeout_seconds=_startup_timeout_seconds(args),
        cwd=Path(str(getattr(args, "cwd", "") or ".")).expanduser().resolve()
        if getattr(args, "cwd", None)
        else None,
    )
    bind_semantic_preflight_selection(report, selection)
    report_out = getattr(args, "report_out", None)
    if report_out:
        out = _report_output_path(report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_semantic_agent_probe(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def _preflight_in_python(args: argparse.Namespace, python: Path) -> dict:
    """Run final preflight in the prepared data runtime.

    `task preflight` is often launched by `/usr/bin/python3`, while managed execution
    may re-exec into a disposable cache rebuilt from repository requirements. Running
    the final preflight in that interpreter avoids falsely diagnosing a missing
    provider adapter; the cache itself is never a source of truth.
    """
    selection = _resolved_selection(args)
    if Path(sys.executable).absolute() == python.absolute():
        report = _apply_reliabletask_fleet_gate(semantic_agent_environment_preflight(
            provider=selection.provider,
            require_credential=not bool(getattr(args, "no_semantic_agent_credential", False)),
            check_network=not bool(getattr(args, "no_network", False)),
            endpoints=getattr(args, "endpoint", None),
            timeout_seconds=_network_timeout_seconds(args),
            check_startup=_semantic_agent_startup_enabled(args),
            startup_model=selection.model_selection,
            startup_runtime=selection.runtime.value,
            startup_timeout_seconds=_startup_timeout_seconds(args),
        ), args)
        return bind_semantic_preflight_selection(report, selection)
    cmd = [
        str(python),
        str(Path(__file__).resolve().parents[3] / "cli.py"),
        "task",
        "preflight",
        "--json",
        "--semantic-selection-id",
        selection.selection_id,
    ]
    if _semantic_agent_startup_enabled(args):
        cmd.append("--semantic-agent-startup")
    else:
        cmd.append("--no-semantic-agent-startup")
    if bool(getattr(args, "no_semantic_agent_credential", False)):
        cmd.append("--no-semantic-agent-credential")
    if bool(getattr(args, "no_network", False)):
        cmd.append("--no-network")
    for endpoint in getattr(args, "endpoint", None) or []:
        cmd.extend(["--endpoint", str(endpoint)])
    child_env = os.environ.copy()
    child_env[_RUNTIME_CHILD_ENV] = "1"
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )
    try:
        report = json.loads((proc.stdout or "{}").strip() or "{}")
    except json.JSONDecodeError:
        report = {
            "schema": "quwoquan_data.environment_preflight",
            "ready": False,
            "issues": [proc.stderr.strip() or "env preflight subprocess did not return JSON"],
        }
    if not report:
        report = {
            "schema": "quwoquan_data.environment_preflight",
            "ready": False,
            "issues": [proc.stderr.strip() or "task preflight subprocess returned an empty report"],
        }
    if proc.returncode != 0:
        report["ready"] = False
        if not report.get("issues"):
            report.setdefault("issues", []).append(f"preflight subprocess exited {proc.returncode}")
    elif isinstance(report, dict):
        required_identity = {
            *selection.document(),
            "selectionDigest",
            "fallbackPolicy",
        }
        missing_identity = sorted(required_identity.difference(report))
        if missing_identity:
            report["ready"] = False
            report.setdefault("issues", []).append(
                "preflight runtime child omitted governed semantic identity: "
                + ",".join(missing_identity)
            )
    return report if isinstance(report, dict) else {"ready": False, "issues": ["invalid preflight report"]}


def handle_ready(args: argparse.Namespace) -> None:
    if os.environ.get(_RUNTIME_CHILD_ENV) == "1":
        handle_preflight(args)
        return
    selection = _resolved_selection(args)
    prepare = prepare_selected_runtime(
        selection,
        prepare=prepare_data_runtime_cache,
    )
    preflight_python = Path(str(prepare.get("python") or "")).expanduser()
    delegated_to_runtime_child = bool(
        prepare.get("ready") and preflight_python.is_file()
    )
    preflight = (
        _preflight_in_python(args, preflight_python)
        if delegated_to_runtime_child
        else semantic_agent_environment_preflight(
            provider=selection.provider,
            require_credential=not bool(getattr(args, "no_semantic_agent_credential", False)),
            check_network=not bool(getattr(args, "no_network", False)),
            endpoints=getattr(args, "endpoint", None),
            timeout_seconds=_network_timeout_seconds(args),
            check_startup=_semantic_agent_startup_enabled(args),
            startup_model=selection.model_selection,
            startup_runtime=selection.runtime.value,
            startup_timeout_seconds=_startup_timeout_seconds(args),
        )
    )
    bind_semantic_preflight_selection(preflight, selection)
    # The verified runtime child already returned the canonical read-only fleet
    # status. Reusing it here avoids a duplicate probe while preserving the
    # fail-closed receipt binding.
    if not delegated_to_runtime_child:
        _apply_reliabletask_fleet_gate(preflight, args)
    startup_timeout_seconds = _startup_timeout_seconds(args)
    semantic_agent_startup = (
        dict(preflight.get("semanticAgentStartup") or {})
        if isinstance(preflight.get("semanticAgentStartup"), dict)
        else {}
    )
    if semantic_agent_startup and "timeoutSeconds" not in semantic_agent_startup:
        semantic_agent_startup["timeoutSeconds"] = startup_timeout_seconds
    run_soak = bool(getattr(args, "soak", False))
    capacity_soak = (
        _capacity_soak_report(selection)
        if run_soak and bool(prepare.get("ready")) and bool(preflight.get("ready"))
        else {}
    )
    run_workspace_smoke = bool(getattr(args, "workspace_smoke", False))
    workspace_smoke = (
        _workspace_smoke_report(selection)
        if run_workspace_smoke
        and bool(prepare.get("ready"))
        and bool(preflight.get("ready"))
        and (not run_soak or bool(capacity_soak.get("ready")))
        else {}
    )
    report = {
        "schema": "quwoquan_data.task_preflight",
        **selection.document(),
        "selectionDigest": selection.selection_digest,
        "fallbackPolicy": "forbidden",
        "prepare": prepare,
        "preflight": preflight,
        "provider": preflight.get("provider"),
        "semanticAgentCredential": preflight.get("semanticAgentCredential") or {},
        "semanticAgentStartup": semantic_agent_startup,
        "capacitySoak": capacity_soak,
        "workspaceSmoke": workspace_smoke,
        "startupRequested": _semantic_agent_startup_enabled(args),
        "soakRequested": run_soak,
        "workspaceSmokeRequested": run_workspace_smoke,
        "startupTimeoutSeconds": startup_timeout_seconds,
        "ready": (
            bool(prepare.get("ready"))
            and bool(preflight.get("ready"))
            and (not run_soak or bool(capacity_soak.get("ready")))
            and (
                not run_workspace_smoke
                or bool(workspace_smoke.get("ready"))
            )
        ),
    }
    report_out = getattr(args, "report_out", None)
    if report_out:
        out = _report_output_path(report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(compact_ready_evidence(report), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    receipt_out = getattr(args, "receipt_out", None)
    if receipt_out:
        receipt_path = _report_output_path(receipt_out)
        receipt = build_semantic_preflight_receipt(
            selection=selection,
            report=report,
        )
        write_semantic_preflight_receipt(receipt_path, receipt)
    if bool(getattr(args, "json", False)):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[task preflight] prepare={'ready' if prepare.get('ready') else 'failed'}")
        if prepare.get("missing"):
            for item in prepare["missing"]:
                print(f"  - {item}", file=sys.stderr)
        _print_preflight(preflight, as_json=False)
        if run_soak:
            _print_semantic_agent_probe(capacity_soak, as_json=False)
        if run_workspace_smoke:
            _print_semantic_agent_workspace_smoke(workspace_smoke)
        print("[task preflight] READY" if report.get("ready") else "[task preflight] FAILED")
    if not report.get("ready"):
        raise SystemExit(1)


def register_task_preflight_parser(subparsers: argparse._SubParsersAction) -> None:
    pr = subparsers.add_parser(
        "preflight",
        help="准备数据运行时并验证凭证、网络和受治理语义 Agent",
    )
    pr.add_argument("--json", action="store_true")
    pr.add_argument(
        "--semantic-selection-id",
        choices=(
            DEFAULT_SEMANTIC_SELECTION_ID,
            CALIBRATION_SEMANTIC_SELECTION_ID,
            "cursor_auto",
        ),
        default=DEFAULT_SEMANTIC_SELECTION_ID,
        help="显式选择受 runtime policy 治理的语义 Provider 绑定",
    )
    pr.add_argument("--no-network", action="store_true", help="跳过网络探测（仅限本地诊断）")
    pr.add_argument(
        "--no-semantic-agent-credential",
        action="store_true",
        help="跳过语义 Agent 凭证检查（仅限单测/离线）",
    )
    pr.add_argument("--endpoint", action="append", help="覆盖网络探测端点，可重复")
    pr.add_argument(
        "--no-semantic-agent-startup",
        action="store_true",
        help="跳过真实语义 Agent 启动探针（仅限单测/离线）",
    )
    pr.add_argument("--semantic-agent-startup", action="store_true", help=argparse.SUPPRESS)
    pr.add_argument(
        "--soak",
        action="store_true",
        help="运行 runtime policy 定义的语义 Agent 并发容量探针",
    )
    pr.add_argument(
        "--workspace-smoke",
        action="store_true",
        help="并发验证四个隔离 campaign workspace 的语义 Agent 启动边界",
    )
    pr.add_argument("--report-out", dest="report_out", help="写出精简、脱敏的运行准入证据")
    pr.add_argument(
        "--receipt-out",
        dest="receipt_out",
        help="写出 create-once、digest-bound 的语义 preflight/soak receipt",
    )
    pr.set_defaults(semantic_agent_startup=True)
    pr.set_defaults(handler=handle_ready)

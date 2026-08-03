"""`qwq-data task preflight` — data runtime preparation and diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from core.cursor_startup_probe import cursor_startup_probe_suite
from core.cursor_workspace_probe import cursor_workspace_probe_suite
from core.paths import DATA_EXECUTIONS_ROOT, DATA_LOCAL_ROOT
from core.python_environment import prepare_data_runtime_cache
from core.python_runtime import environment_preflight
from core.runtime_policy import active_runtime_policy

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
    key = report.get("cursorApiKey") or {}
    network = report.get("network") or {}
    print(f"[env preflight] runtime={'ready' if runtime.get('ready') else 'missing'}")
    print(f"[env preflight] resolvedPython={runtime.get('resolvedPython') or '<missing>'}")
    key_status = "present" if key.get("present") else "missing"
    if key.get("present") and not key.get("valid"):
        key_status = "invalid"
    print(f"[env preflight] credentialSource={key.get('source') or 'missing'} status={key_status}")
    if network.get("skipped"):
        print(f"[env preflight] network=skipped ({network.get('skipReason')})")
    else:
        print(f"[env preflight] network={'ready' if network.get('ready') else 'failed'}")
        for row in network.get("endpoints") or []:
            status = row.get("status") or row.get("error") or ""
            marker = "ok" if row.get("reachable") else "fail"
            print(f"  - {marker}: {row.get('url')} {status}")
    startup = report.get("cursorStartup") or {}
    if startup.get("checked"):
        print(
            "[env preflight] cursorStartup="
            + ("ready" if startup.get("ready") else "failed")
            + f" model={startup.get('model')} runtime={startup.get('runtime')}"
        )
    elif startup:
        print(f"[env preflight] cursorStartup=skipped ({startup.get('skipReason')})")
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def _print_cursor_probe(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(
        "[env cursor-probe] "
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
            "[env cursor-probe] "
            f"sdkVersion={catalog.get('sdkVersion') or '<unknown>'} "
            f"accountModels={catalog.get('modelCount') or 0} "
            "autoSelection=auto"
        )
    print("[env cursor-probe] READY" if report.get("ready") else "[env cursor-probe] FAILED")
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def _print_cursor_workspace_smoke(report: dict) -> None:
    print(
        "[env cursor-workspace-smoke] "
        f"workspaces={report.get('workspaceCount')} "
        f"success={report.get('successCount')} "
        f"effectiveConcurrency={report.get('effectiveConcurrency')} "
        f"cleanup={report.get('cleanupStatus')}"
    )
    print(
        "[env cursor-workspace-smoke] READY"
        if report.get("ready")
        else "[env cursor-workspace-smoke] FAILED"
    )
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def _capacity_soak_report() -> dict:
    """Run a reusable Cursor bridge capacity probe from the runtime policy."""
    policy = active_runtime_policy()
    report = cursor_startup_probe_suite(
        model=policy.cursor_model_selection,
        runtime=policy.cursor_runtime.value,
        attempts=policy.startup_probe_suite_attempts,
        timeout_seconds=policy.startup_timeout_seconds,
        cwd=Path.cwd(),
        include_catalog=True,
    )
    issues = list(report.get("issues") or [])
    if int(report.get("successCount") or 0) != policy.startup_probe_suite_attempts:
        issues.append(
            "capacity probe requires every Cursor SDK job to finish: "
            f"{report.get('successCount')}/{policy.startup_probe_suite_attempts}"
        )
    if int(report.get("effectiveConcurrency") or 0) < policy.cursor_bridge_instances:
        issues.append(
            "capacity probe effective concurrency is below runtime policy: "
            f"{report.get('effectiveConcurrency')}<{policy.cursor_bridge_instances}"
        )
    if int(report.get("bridgeDisconnectCount") or 0):
        issues.append(
            "capacity probe observed unrecovered Cursor bridge disconnects"
        )
    report["capacityContract"] = {
        "attempts": policy.startup_probe_suite_attempts,
        "bridgeInstances": policy.cursor_bridge_instances,
        "startupTimeoutSeconds": policy.startup_timeout_seconds,
    }
    report["issues"] = list(dict.fromkeys(str(issue) for issue in issues if str(issue)))
    report["ready"] = not report["issues"]
    return report


def _workspace_smoke_report() -> dict:
    """Exercise four independent campaign-lane workspaces concurrently."""
    from content.execution.campaign_process import CAMPAIGN_CARRIERS

    policy = active_runtime_policy()
    smoke_parent = DATA_LOCAL_ROOT / "cache/cursor/workspace-smoke"
    smoke_parent.mkdir(parents=True, exist_ok=True)
    smoke_path: Path | None = None
    with tempfile.TemporaryDirectory(
        prefix="cursor-auto-",
        dir=smoke_parent,
    ) as temporary:
        smoke_path = Path(temporary)
        workspaces: list[Path] = []
        for carrier in CAMPAIGN_CARRIERS:
            workspace = smoke_path / carrier
            workspace.mkdir()
            workspaces.append(workspace)
        report = cursor_workspace_probe_suite(
            workspaces=workspaces,
            model=policy.cursor_model_selection,
            runtime=policy.cursor_runtime.value,
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
            "Cursor workspace smoke temporary workspaces were not cleaned"
        )
    return report


def _cursor_startup_enabled(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "no_cursor_startup", False)):
        return False
    return bool(getattr(args, "cursor_startup", False))


def _startup_timeout_seconds(args: argparse.Namespace) -> float:
    return float(active_runtime_policy().startup_timeout_seconds)


def _reliabletask_fleet_report(required: bool) -> dict:
    if not required:
        return {"checked": False, "ready": False, "issues": []}
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
        "issues": list(report.get("issues") or []),
    }


def _apply_reliabletask_fleet_gate(report: dict, args: argparse.Namespace) -> dict:
    fleet = _reliabletask_fleet_report(
        bool(getattr(args, "require_reliabletask_fleet", False))
    )
    report["reliableTaskFleet"] = fleet
    if fleet.get("checked") and not fleet.get("ready"):
        report["ready"] = False
        issues = report.setdefault("issues", [])
        if isinstance(issues, list):
            issues.extend(str(item) for item in fleet.get("issues") or [])
    return report


def handle_preflight(args: argparse.Namespace) -> None:
    policy = active_runtime_policy()
    report = environment_preflight(
        require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
        check_network=not bool(getattr(args, "no_network", False)),
        endpoints=getattr(args, "endpoint", None),
        timeout_seconds=_network_timeout_seconds(args),
        check_cursor_startup=_cursor_startup_enabled(args),
        cursor_startup_model=policy.cursor_model_selection,
        cursor_startup_runtime=policy.cursor_runtime.value,
        cursor_startup_timeout_seconds=_startup_timeout_seconds(args),
    )
    _apply_reliabletask_fleet_gate(report, args)
    _print_preflight(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def handle_cursor_probe(args: argparse.Namespace) -> None:
    policy = active_runtime_policy()
    report = cursor_startup_probe_suite(
        model=policy.cursor_model_selection,
        runtime=policy.cursor_runtime.value,
        attempts=int(
            getattr(args, "attempts", None)
            or active_runtime_policy().startup_probe_suite_attempts
        ),
        timeout_seconds=_startup_timeout_seconds(args),
        cwd=Path(str(getattr(args, "cwd", "") or ".")).expanduser().resolve()
        if getattr(args, "cwd", None)
        else None,
        include_catalog=True,
    )
    report_out = getattr(args, "report_out", None)
    if report_out:
        out = _report_output_path(report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_cursor_probe(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def _preflight_in_python(args: argparse.Namespace, python: Path) -> dict:
    """Run final preflight in the prepared data runtime.

    `task preflight` is often launched by `/usr/bin/python3`, while managed execution
    may re-exec into a disposable cache rebuilt from repository requirements. Running
    the final preflight in that interpreter avoids falsely diagnosing missing
    `cursor_sdk`; the cache itself is never a source of truth.
    """
    if Path(sys.executable).absolute() == python.absolute():
        policy = active_runtime_policy()
        return _apply_reliabletask_fleet_gate(environment_preflight(
            require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
            check_network=not bool(getattr(args, "no_network", False)),
            endpoints=getattr(args, "endpoint", None),
            timeout_seconds=_network_timeout_seconds(args),
            check_cursor_startup=_cursor_startup_enabled(args),
            cursor_startup_model=policy.cursor_model_selection,
            cursor_startup_runtime=policy.cursor_runtime.value,
            cursor_startup_timeout_seconds=_startup_timeout_seconds(args),
        ), args)
    cmd = [
        str(python),
        str(Path(__file__).resolve().parents[3] / "cli.py"),
        "task",
        "preflight",
        "--json",
    ]
    if _cursor_startup_enabled(args):
        cmd.append("--cursor-startup")
    else:
        cmd.append("--no-cursor-startup")
    if bool(getattr(args, "no_cursor_key", False)):
        cmd.append("--no-cursor-key")
    if bool(getattr(args, "no_network", False)):
        cmd.append("--no-network")
    if bool(getattr(args, "require_reliabletask_fleet", False)):
        cmd.append("--require-reliabletask-fleet")
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
    return report if isinstance(report, dict) else {"ready": False, "issues": ["invalid preflight report"]}


def handle_ready(args: argparse.Namespace) -> None:
    if os.environ.get(_RUNTIME_CHILD_ENV) == "1":
        handle_preflight(args)
        return
    prepare = prepare_data_runtime_cache()
    preflight_python = Path(str(prepare.get("python") or "")).expanduser()
    delegated_to_runtime_child = bool(
        prepare.get("ready") and preflight_python.is_file()
    )
    preflight = (
        _preflight_in_python(args, preflight_python)
        if delegated_to_runtime_child
        else environment_preflight(
            require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
            check_network=not bool(getattr(args, "no_network", False)),
            endpoints=getattr(args, "endpoint", None),
            timeout_seconds=_network_timeout_seconds(args),
            check_cursor_startup=_cursor_startup_enabled(args),
            cursor_startup_model=active_runtime_policy().cursor_model_selection,
            cursor_startup_runtime=active_runtime_policy().cursor_runtime.value,
            cursor_startup_timeout_seconds=_startup_timeout_seconds(args),
        )
    )
    # `_preflight_in_python` forwards the fleet requirement to the verified
    # runtime child. Running the same side-effecting topology reconciliation
    # again in this parent races sibling campaign lanes during cold start.
    if not delegated_to_runtime_child:
        _apply_reliabletask_fleet_gate(preflight, args)
    startup_timeout_seconds = _startup_timeout_seconds(args)
    cursor_startup = (
        dict(preflight.get("cursorStartup") or {})
        if isinstance(preflight.get("cursorStartup"), dict)
        else {}
    )
    if cursor_startup and "timeoutSeconds" not in cursor_startup:
        cursor_startup["timeoutSeconds"] = startup_timeout_seconds
    run_soak = bool(getattr(args, "soak", False))
    capacity_soak = (
        _capacity_soak_report()
        if run_soak and bool(prepare.get("ready")) and bool(preflight.get("ready"))
        else {}
    )
    run_workspace_smoke = bool(getattr(args, "workspace_smoke", False))
    workspace_smoke = (
        _workspace_smoke_report()
        if run_workspace_smoke
        and bool(prepare.get("ready"))
        and bool(preflight.get("ready"))
        and (not run_soak or bool(capacity_soak.get("ready")))
        else {}
    )
    report = {
        "schema": "quwoquan_data.task_preflight",
        "prepare": prepare,
        "preflight": preflight,
        "cursorApiKey": preflight.get("cursorApiKey") or {},
        "cursorStartup": cursor_startup,
        "capacitySoak": capacity_soak,
        "workspaceSmoke": workspace_smoke,
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
            json.dumps(_compact_ready_evidence(report), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if bool(getattr(args, "json", False)):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[task preflight] prepare={'ready' if prepare.get('ready') else 'failed'}")
        if prepare.get("missing"):
            for item in prepare["missing"]:
                print(f"  - {item}", file=sys.stderr)
        _print_preflight(preflight, as_json=False)
        if run_soak:
            _print_cursor_probe(capacity_soak, as_json=False)
        if run_workspace_smoke:
            _print_cursor_workspace_smoke(workspace_smoke)
        print("[task preflight] READY" if report.get("ready") else "[task preflight] FAILED")
    if not report.get("ready"):
        raise SystemExit(1)


def _compact_ready_evidence(report: dict) -> dict:
    prepare = report.get("prepare") if isinstance(report.get("prepare"), dict) else {}
    preflight = report.get("preflight") if isinstance(report.get("preflight"), dict) else {}
    runtime = preflight.get("runtime") if isinstance(preflight.get("runtime"), dict) else {}
    credential = report.get("cursorApiKey") if isinstance(report.get("cursorApiKey"), dict) else {}
    network = preflight.get("network") if isinstance(preflight.get("network"), dict) else {}
    startup = report.get("cursorStartup") if isinstance(report.get("cursorStartup"), dict) else {}
    capacity = report.get("capacitySoak") if isinstance(report.get("capacitySoak"), dict) else {}
    workspace_smoke = (
        report.get("workspaceSmoke")
        if isinstance(report.get("workspaceSmoke"), dict)
        else {}
    )
    catalog = (
        capacity.get("modelCatalog")
        if isinstance(capacity.get("modelCatalog"), dict)
        else {}
    )
    capacity_runs = [
        {
            "attempt": row.get("attempt"),
            "status": row.get("status"),
            "agentId": row.get("agentId"),
            "runId": row.get("runId"),
            "sdkVersion": row.get("sdkVersion"),
        }
        for row in capacity.get("results") or []
        if isinstance(row, dict)
    ]
    fleet = (
        preflight.get("reliableTaskFleet")
        if isinstance(preflight.get("reliableTaskFleet"), dict)
        else {}
    )
    return {
        "ready": bool(report.get("ready")),
        "runtime": {
            "ready": bool(prepare.get("ready")) and bool(runtime.get("ready")),
            "python": runtime.get("resolvedPython") or prepare.get("python"),
            "missing": list(runtime.get("missing") or prepare.get("missing") or []),
        },
        "credential": {
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
        "reliableTaskFleet": {
            "checked": bool(fleet.get("checked")),
            "ready": bool(fleet.get("ready")),
            "target": fleet.get("target"),
            "mongo": bool(fleet.get("mongo")),
            "redis": bool(fleet.get("redis")),
            "issues": list(fleet.get("issues") or []),
        },
        "cursorStartup": {
            "checked": bool(startup.get("checked")),
            "ready": bool(startup.get("checked")) and bool(startup.get("ready")),
            "runtime": startup.get("runtime"),
            "model": startup.get("model"),
            "agentId": startup.get("agentId"),
            "runId": startup.get("runId"),
            "sdkVersion": startup.get("sdkVersion"),
            "issues": list(startup.get("issues") or []),
        },
        "capacitySoak": {
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
                if isinstance(row, dict)
            ],
            "issues": list(workspace_smoke.get("issues") or []),
        },
        "issues": list(preflight.get("issues") or []),
    }


def register_task_preflight_parser(subparsers: argparse._SubParsersAction) -> None:
    pr = subparsers.add_parser("preflight", help="准备数据运行时并验证凭证、网络和 Cursor SDK")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--no-network", action="store_true", help="跳过网络探测（仅限本地诊断）")
    pr.add_argument("--no-cursor-key", action="store_true", help="跳过 key file 凭证检查（仅限单测/离线）")
    pr.add_argument("--endpoint", action="append", help="覆盖网络探测端点，可重复")
    pr.add_argument("--no-cursor-startup", action="store_true", help="跳过真实 Cursor SDK Agent.prompt 启动探针（仅限单测/离线）")
    pr.add_argument("--cursor-startup", action="store_true", help=argparse.SUPPRESS)
    pr.add_argument("--require-reliabletask-fleet", action="store_true", help=argparse.SUPPRESS)
    pr.add_argument("--soak", action="store_true", help="运行 runtime policy 定义的 Cursor SDK 并发容量探针")
    pr.add_argument(
        "--workspace-smoke",
        action="store_true",
        help="并发验证四个隔离 campaign workspace 的 Cursor Auto 启动边界",
    )
    pr.add_argument("--report-out", dest="report_out", help="写出精简、脱敏的运行准入证据")
    pr.set_defaults(cursor_startup=True)
    pr.set_defaults(handler=handle_ready)

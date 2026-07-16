"""`qwq-data task preflight` — data runtime preparation and diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from core.cursor_startup_probe import cursor_startup_probe_suite
from core.paths import DATA_EXECUTIONS_ROOT, DATA_LOCAL_ROOT
from core.python_environment import (
    DEFAULT_CURSOR_STARTUP_MODEL,
    prepare_data_runtime_cache,
    resolve_cursor_startup_timeout_seconds,
    runtime_report,
)
from core.python_runtime import environment_preflight
from core.runtime_policy import active_runtime_policy

_RUNTIME_CHILD_ENV = "QWQ_DATA_PREFLIGHT_RUNTIME_CHILD"


def _network_timeout_seconds(args: argparse.Namespace) -> float:
    value = getattr(args, "timeout_seconds", None)
    return float(
        value
        if value is not None
        else active_runtime_policy().preflight_network_timeout_seconds
    )


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


def _print_report(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"[env] currentPython={report['currentPython']}")
    print(f"[env] requirements={report['requirements']}")
    print(f"[env] resolvedPython={report.get('resolvedPython') or '<missing>'}")
    for row in report.get("candidates") or []:
        status = "ready" if row.get("ready") else "missing"
        print(f"  - {status}: {row.get('python')}")
        for item in row.get("missing") or []:
            print(f"      {item}")


def _print_preflight(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    runtime = report.get("runtime") or {}
    key = report.get("cursorApiKey") or {}
    network = report.get("network") or {}
    cloud_api = report.get("cursorCloudApi") or {}
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
    if cloud_api.get("checked"):
        status = "ready" if cloud_api.get("ready") else "failed"
        key_type = cloud_api.get("keyType") or "unknown"
        code = cloud_api.get("errorCode")
        suffix = f" keyType={key_type}"
        if code:
            suffix += f" errorCode={code}"
        print(f"[env preflight] cursorCloudApi={status}{suffix}")
    elif cloud_api:
        print(f"[env preflight] cursorCloudApi=skipped ({cloud_api.get('skipReason')})")
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
    print("[env cursor-probe] READY" if report.get("ready") else "[env cursor-probe] FAILED")
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def _cursor_startup_enabled(args: argparse.Namespace) -> bool:
    if bool(getattr(args, "no_cursor_startup", False)):
        return False
    return bool(getattr(args, "cursor_startup", False))


def _startup_timeout_seconds(args: argparse.Namespace) -> float:
    return resolve_cursor_startup_timeout_seconds(
        getattr(args, "startup_timeout_seconds", None)
    )


def _check_cursor_cloud_api(args: argparse.Namespace) -> bool:
    # 即使 runtime=local，cursor_sdk 仍依赖账号资格；否则 403/plan_required
    # 会在本地桥里被折叠成 InternalServerError 500，误导 H100/H1000 准入判断。
    return not bool(getattr(args, "no_cursor_key", False))


def handle_doctor(args: argparse.Namespace) -> None:
    report = runtime_report()
    _print_report(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def handle_prepare(args: argparse.Namespace) -> None:
    report = prepare_data_runtime_cache(
        python=Path(args.python).expanduser() if getattr(args, "python", None) else None,
        requirements=Path(args.requirements).expanduser() if getattr(args, "requirements", None) else None,
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[env prepare] python={report['python']}")
        print(f"[env prepare] requirements={report['requirements']}")
        print(f"[env prepare] installReturnCode={report['installReturnCode']}")
        if report.get("stdoutTail"):
            print(report["stdoutTail"].rstrip())
        if report.get("stderrTail"):
            print(report["stderrTail"].rstrip(), file=sys.stderr)
        print("[env prepare] READY" if report.get("ready") else "[env prepare] FAILED")
        if report.get("missing"):
            for item in report["missing"]:
                print(f"  - {item}", file=sys.stderr)
    if not report.get("ready"):
        raise SystemExit(1)


def handle_preflight(args: argparse.Namespace) -> None:
    runtime = str(getattr(args, "runtime", "local") or "local")
    report = environment_preflight(
        require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
        check_network=not bool(getattr(args, "no_network", False)),
        check_cursor_cloud_api=_check_cursor_cloud_api(args),
        endpoints=getattr(args, "endpoint", None),
        timeout_seconds=_network_timeout_seconds(args),
        check_cursor_startup=_cursor_startup_enabled(args),
        cursor_startup_model=str(getattr(args, "model", DEFAULT_CURSOR_STARTUP_MODEL) or DEFAULT_CURSOR_STARTUP_MODEL),
        cursor_startup_runtime=runtime,
        cursor_startup_timeout_seconds=_startup_timeout_seconds(args),
    )
    _print_preflight(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def handle_cursor_probe(args: argparse.Namespace) -> None:
    report = cursor_startup_probe_suite(
        model=str(getattr(args, "model", DEFAULT_CURSOR_STARTUP_MODEL) or DEFAULT_CURSOR_STARTUP_MODEL),
        runtime=str(getattr(args, "runtime", "local") or "local"),
        attempts=int(
            getattr(args, "attempts", None)
            or active_runtime_policy().startup_probe_suite_attempts
        ),
        timeout_seconds=_startup_timeout_seconds(args),
        cwd=Path(str(getattr(args, "cwd", "") or ".")).expanduser().resolve()
        if getattr(args, "cwd", None)
        else None,
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

    `task preflight` is often launched by `/usr/bin/python3`, while managed workflow
    may re-exec into a disposable cache rebuilt from repository requirements. Running
    the final preflight in that interpreter avoids falsely diagnosing missing
    `cursor_sdk`; the cache itself is never a source of truth.
    """
    if Path(sys.executable).absolute() == python.absolute():
        runtime = str(getattr(args, "runtime", "local") or "local")
        return environment_preflight(
            require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
            check_network=not bool(getattr(args, "no_network", False)),
            check_cursor_cloud_api=_check_cursor_cloud_api(args),
            endpoints=getattr(args, "endpoint", None),
            timeout_seconds=_network_timeout_seconds(args),
            check_cursor_startup=_cursor_startup_enabled(args),
            cursor_startup_model=str(getattr(args, "model", DEFAULT_CURSOR_STARTUP_MODEL) or DEFAULT_CURSOR_STARTUP_MODEL),
            cursor_startup_runtime=runtime,
            cursor_startup_timeout_seconds=_startup_timeout_seconds(args),
        )
    cmd = [
        str(python),
        str(Path(__file__).resolve().parents[3] / "cli.py"),
        "task",
        "preflight",
        "--json",
        "--timeout-seconds",
        str(_network_timeout_seconds(args)),
        "--runtime",
        str(getattr(args, "runtime", "local") or "local"),
    ]
    if _cursor_startup_enabled(args):
        cmd.extend(
            [
                "--model",
                str(
                    getattr(args, "model", None)
                    or active_runtime_policy().cursor_model
                ),
            ]
        )
        cmd.extend(["--startup-timeout-seconds", str(_startup_timeout_seconds(args))])
    else:
        cmd.append("--no-cursor-startup")
    if bool(getattr(args, "no_cursor_key", False)):
        cmd.append("--no-cursor-key")
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
            "schemaVersion": "quwoquan_data.environment_preflight",
            "ready": False,
            "issues": [proc.stderr.strip() or "env preflight subprocess did not return JSON"],
        }
    if not report:
        report = {
            "schemaVersion": "quwoquan_data.environment_preflight",
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
    prepare = prepare_data_runtime_cache(
        python=Path(args.python).expanduser() if getattr(args, "python", None) else None,
        requirements=Path(args.requirements).expanduser() if getattr(args, "requirements", None) else None,
    )
    preflight_python = Path(str(prepare.get("python") or "")).expanduser()
    preflight = (
        _preflight_in_python(args, preflight_python)
        if prepare.get("ready") and preflight_python.is_file()
        else environment_preflight(
            require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
            check_network=not bool(getattr(args, "no_network", False)),
            check_cursor_cloud_api=_check_cursor_cloud_api(args),
            endpoints=getattr(args, "endpoint", None),
            timeout_seconds=_network_timeout_seconds(args),
            check_cursor_startup=_cursor_startup_enabled(args),
            cursor_startup_model=str(getattr(args, "model", DEFAULT_CURSOR_STARTUP_MODEL) or DEFAULT_CURSOR_STARTUP_MODEL),
            cursor_startup_runtime=str(getattr(args, "runtime", "local") or "local"),
            cursor_startup_timeout_seconds=_startup_timeout_seconds(args),
        )
    )
    startup_timeout_seconds = _startup_timeout_seconds(args)
    cursor_startup = (
        dict(preflight.get("cursorStartup") or {})
        if isinstance(preflight.get("cursorStartup"), dict)
        else {}
    )
    if cursor_startup and "timeoutSeconds" not in cursor_startup:
        cursor_startup["timeoutSeconds"] = startup_timeout_seconds
    report = {
        "schemaVersion": "quwoquan_data.task_preflight",
        "prepare": prepare,
        "preflight": preflight,
        "cursorApiKey": preflight.get("cursorApiKey") or {},
        "cursorStartup": cursor_startup,
        "startupTimeoutSeconds": startup_timeout_seconds,
        "ready": bool(prepare.get("ready")) and bool(preflight.get("ready")),
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
        "cursorStartup": {
            "checked": bool(startup.get("checked")),
            "ready": bool(startup.get("checked")) and bool(startup.get("ready")),
            "runtime": startup.get("runtime"),
            "model": startup.get("model"),
            "issues": list(startup.get("issues") or []),
        },
        "issues": list(preflight.get("issues") or []),
    }


def register_task_preflight_parser(subparsers: argparse._SubParsersAction) -> None:
    pr = subparsers.add_parser("preflight", help="准备数据运行时并验证凭证、网络和 Cursor SDK")
    pr.add_argument(
        "--python",
        help="目标 Python；默认 .qwq_output/env/repo/local/python-envs/cache/quwoquan-data/bin/python",
    )
    pr.add_argument("--requirements", help="依赖清单；默认 quwoquan_data/requirements.txt")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--no-network", action="store_true", help="跳过网络探测（仅限本地诊断）")
    pr.add_argument("--no-cursor-key", action="store_true", help="跳过 key file 凭证检查（仅限单测/离线）")
    pr.add_argument("--endpoint", action="append", help="覆盖网络探测端点，可重复")
    pr.add_argument(
        "--timeout-seconds",
        type=float,
        help="显式覆盖 preflight 网络超时；缺省读取 runtime profile",
    )
    pr.add_argument("--no-cursor-startup", action="store_true", help="跳过真实 Cursor SDK Agent.prompt 启动探针（仅限单测/离线）")
    pr.add_argument("--model", default=DEFAULT_CURSOR_STARTUP_MODEL, help="Cursor startup probe model")
    pr.add_argument("--runtime", choices=["local", "cloud"], default="local", help="Cursor startup probe runtime")
    pr.add_argument(
        "--startup-timeout-seconds",
        type=float,
        help="显式覆盖 Cursor 启动超时；缺省读取 runtime profile",
    )
    pr.add_argument("--report-out", dest="report_out", help="写出精简、脱敏的运行准入证据")
    pr.set_defaults(cursor_startup=True)
    pr.set_defaults(handler=handle_ready)

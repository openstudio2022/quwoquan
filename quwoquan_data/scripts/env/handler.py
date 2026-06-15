"""qwq-data env — data runtime preparation and diagnostics."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common.python_runtime import environment_preflight, prepare_data_runtime, runtime_report


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
    print(f"[env preflight] runtime={'ready' if runtime.get('ready') else 'missing'}")
    print(f"[env preflight] resolvedPython={runtime.get('resolvedPython') or '<missing>'}")
    key_status = "present" if key.get("present") else "missing"
    if key.get("present") and not key.get("valid"):
        key_status = "invalid"
    print(f"[env preflight] CURSOR_API_KEY={key_status}")
    if network.get("skipped"):
        print(f"[env preflight] network=skipped ({network.get('skipReason')})")
    else:
        print(f"[env preflight] network={'ready' if network.get('ready') else 'failed'}")
        for row in network.get("endpoints") or []:
            status = row.get("status") or row.get("error") or ""
            marker = "ok" if row.get("reachable") else "fail"
            print(f"  - {marker}: {row.get('url')} {status}")
    for item in report.get("issues") or []:
        print(f"  - {item}", file=sys.stderr)


def handle_doctor(args: argparse.Namespace) -> None:
    report = runtime_report()
    _print_report(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def handle_prepare(args: argparse.Namespace) -> None:
    report = prepare_data_runtime(
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
    report = environment_preflight(
        require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
        check_network=not bool(getattr(args, "no_network", False)),
        endpoints=getattr(args, "endpoint", None),
        timeout_seconds=float(getattr(args, "timeout_seconds", 5.0)),
    )
    _print_preflight(report, as_json=bool(getattr(args, "json", False)))
    if not report.get("ready"):
        raise SystemExit(1)


def handle_ready(args: argparse.Namespace) -> None:
    prepare = prepare_data_runtime(
        python=Path(args.python).expanduser() if getattr(args, "python", None) else None,
        requirements=Path(args.requirements).expanduser() if getattr(args, "requirements", None) else None,
    )
    preflight = environment_preflight(
        require_cursor_key=not bool(getattr(args, "no_cursor_key", False)),
        check_network=not bool(getattr(args, "no_network", False)),
        endpoints=getattr(args, "endpoint", None),
        timeout_seconds=float(getattr(args, "timeout_seconds", 5.0)),
    )
    report = {
        "schemaVersion": "quwoquan_data.env_ready",
        "prepare": prepare,
        "preflight": preflight,
        "ready": bool(prepare.get("ready")) and bool(preflight.get("ready")),
    }
    if bool(getattr(args, "json", False)):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[env ready] prepare={'ready' if prepare.get('ready') else 'failed'}")
        if prepare.get("missing"):
            for item in prepare["missing"]:
                print(f"  - {item}", file=sys.stderr)
        _print_preflight(preflight, as_json=False)
        print("[env ready] READY" if report.get("ready") else "[env ready] FAILED")
    if not report.get("ready"):
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("env", help="准备和诊断数据工程 Python 运行时")
    sub = p.add_subparsers(dest="env_command")

    pd = sub.add_parser("doctor", help="检查 agent/runtime 依赖是否可用")
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(handler=handle_doctor)

    pp = sub.add_parser("prepare", help="创建/更新 quwoquan_data/.venv 并安装固定依赖")
    pp.add_argument("--python", help="目标 Python；默认 quwoquan_data/.venv/bin/python")
    pp.add_argument("--requirements", help="依赖清单；默认 quwoquan_data/requirements.txt")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(handler=handle_prepare)

    ppf = sub.add_parser("preflight", help="检查运行时、CURSOR_API_KEY 和网络可达性")
    ppf.add_argument("--json", action="store_true")
    ppf.add_argument("--no-network", action="store_true", help="跳过网络探测（仅限本地诊断）")
    ppf.add_argument("--no-cursor-key", action="store_true", help="跳过 CURSOR_API_KEY 检查（仅限单测/离线）")
    ppf.add_argument("--endpoint", action="append", help="覆盖网络探测端点，可重复")
    ppf.add_argument("--timeout-seconds", type=float, default=5.0)
    ppf.set_defaults(handler=handle_preflight)

    pr = sub.add_parser("ready", help="一键准备 data venv，并执行运行前环境验收")
    pr.add_argument("--python", help="目标 Python；默认 quwoquan_data/.venv/bin/python")
    pr.add_argument("--requirements", help="依赖清单；默认 quwoquan_data/requirements.txt")
    pr.add_argument("--json", action="store_true")
    pr.add_argument("--no-network", action="store_true", help="跳过网络探测（仅限本地诊断）")
    pr.add_argument("--no-cursor-key", action="store_true", help="跳过 CURSOR_API_KEY 检查（仅限单测/离线）")
    pr.add_argument("--endpoint", action="append", help="覆盖网络探测端点，可重复")
    pr.add_argument("--timeout-seconds", type=float, default=5.0)
    pr.set_defaults(handler=handle_ready)

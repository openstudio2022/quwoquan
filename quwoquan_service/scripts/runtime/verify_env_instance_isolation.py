#!/usr/bin/env python3
"""Verify app-instance records plus beta/gamma single-stack semantics."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-root",
        default=str(ROOT / "tmp/app-instances"),
        help="App instance state root.",
    )
    parser.add_argument(
        "--beta-report",
        default=str(ROOT / "tmp/app_beta_manual/app-beta-manual-report.json"),
        help="Beta manual report path.",
    )
    parser.add_argument(
        "--gamma-stack-report",
        default=str(ROOT / "artifacts/local-gamma/stack_state.json"),
        help="local-gamma stack report path.",
    )
    parser.add_argument(
        "--beta-ports",
        default="18080,18087,18088",
        help="Comma-separated beta single-stack listener ports.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def listener_pids(port: int) -> list[int]:
    result = subprocess.run(
        ["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for raw in result.stdout.splitlines():
        raw = raw.strip()
        if raw.isdigit():
            pids.append(int(raw))
    return sorted(set(pids))


def is_local_host(value: str) -> bool:
    return value in {"127.0.0.1", "localhost", ""}


def local_port_from_url(url: str) -> int | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not is_local_host(parsed.hostname or ""):
        return None
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


def collect_app_instances(state_root: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    instances: list[dict[str, Any]] = []
    gate_blocks: list[str] = []
    failures: list[str] = []
    seen: dict[tuple[str, str], list[dict[str, Any]]] = {}

    if not state_root.exists():
        return instances, gate_blocks, failures

    for path in sorted(state_root.glob("*/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            gate_blocks.append(f"invalid state file: {path}")
            continue
        pid = int(payload.get("pid") or 0)
        alive = pid_alive(pid) if pid > 0 else False
        payload["alive"] = alive
        payload["stateFile"] = str(path)
        instances.append(payload)
        if not alive:
            gate_blocks.append(f"stale app instance state: {path}")
            continue
        key = (str(payload.get("env") or "").strip(), str(payload.get("deviceId") or "").strip())
        seen.setdefault(key, []).append(payload)

    for (env_name, device_id), records in seen.items():
        if len(records) > 1:
            failures.append(
                f"duplicate live app instances for env={env_name} device={device_id}: {len(records)}"
            )
    return instances, gate_blocks, failures


def main() -> int:
    args = parse_args()
    state_root = Path(args.state_root)
    beta_report = load_json(Path(args.beta_report))
    gamma_stack_report = load_json(Path(args.gamma_stack_report))
    beta_ports = [int(item) for item in args.beta_ports.split(",") if item.strip()]

    report: dict[str, Any] = {
        "status": "passed",
        "appInstances": [],
        "betaSingleStack": {"status": "passed", "listeners": {}},
        "gammaSingleStack": {"status": "passed"},
        "failures": [],
        "gateBlocks": [],
    }

    app_instances, gate_blocks, failures = collect_app_instances(state_root)
    report["appInstances"] = app_instances
    report["gateBlocks"].extend(gate_blocks)
    report["failures"].extend(failures)

    beta_listener_map: dict[str, list[int]] = {}
    for port in beta_ports:
        beta_listener_map[str(port)] = listener_pids(port)
    report["betaSingleStack"]["listeners"] = beta_listener_map
    report["betaSingleStack"]["report"] = beta_report

    if beta_report is not None:
        beta_service_mode = str(beta_report.get("serviceMode") or "").strip()
        if not beta_service_mode and str(beta_report.get("mode") or "").strip() == "manual-beta":
            beta_service_mode = "single-stack"
        if beta_service_mode and beta_service_mode != "single-stack":
            report["failures"].append("beta report serviceMode must be single-stack")
            report["betaSingleStack"]["status"] = "failed"
        active_beta = any(beta_listener_map[str(port)] for port in beta_ports)
        if active_beta and not beta_service_mode:
            report["gateBlocks"].append("beta listeners are active but beta report is missing serviceMode")
            report["betaSingleStack"]["status"] = "gate_block"

    report["gammaSingleStack"]["report"] = gamma_stack_report
    if gamma_stack_report is not None:
        gamma_service_mode = str(gamma_stack_report.get("serviceMode") or "").strip()
        if gamma_service_mode and gamma_service_mode != "single-stack":
            report["failures"].append("gamma stack report serviceMode must be single-stack")
            report["gammaSingleStack"]["status"] = "failed"
        local_ports: dict[str, int] = {}
        for key in ("gatewayBaseUrl", "productOpsBaseUrl"):
            port = local_port_from_url(str(gamma_stack_report.get(key) or ""))
            if port is not None:
                local_ports[key] = port
        listeners = {name: listener_pids(port) for name, port in local_ports.items()}
        report["gammaSingleStack"]["listeners"] = listeners
        active_gamma = bool(local_ports) and any(listeners.values())
        if active_gamma and not gamma_service_mode:
            report["gateBlocks"].append("gamma listeners are active but stack report is missing serviceMode")
            report["gammaSingleStack"]["status"] = "gate_block"

    if report["failures"]:
        report["status"] = "failed"
    elif report["gateBlocks"]:
        report["status"] = "gate_block"

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[env-instance] status: {report['status']}")
        print(f"[env-instance] app instances: {len(app_instances)}")
        if report["failures"]:
            for item in report["failures"]:
                print(f"[env-instance] FAIL: {item}")
        if report["gateBlocks"]:
            for item in report["gateBlocks"]:
                print(f"[env-instance] GATE_BLOCK: {item}")

    if report["status"] == "passed":
        return 0
    if report["status"] == "gate_block":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

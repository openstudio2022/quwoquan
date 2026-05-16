#!/usr/bin/env python3
"""商用群头像端到端矩阵前置检查（诚实门禁辅助）。

不访问 ECS；仅检查本机工具链与（可选）Flutter 设备、网关可达性。
缺省时打印 GATE_BLOCK 说明并退出非零。

用法:
  python3 agent_ops/avatar/check_avatar_commercial_matrix_prereqs.py [--strict] [--json]

退出码:
  0 — 非 strict；或 strict 且本机前置项均满足（商用声明仍须四条 JSON）
  2 — strict 且存在 gate_blocks（如缺少 patrol、网关未配置、缺 Android/iOS 设备等）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run_json(cmd: list[str], timeout_sec: float = 60.0) -> tuple[bool, Any, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, None, err or out or f"exit {proc.returncode}"
        try:
            return True, json.loads(out), ""
        except json.JSONDecodeError as e:
            return False, None, f"invalid json: {e}: {out[:500]}"
    except FileNotFoundError:
        return False, None, "command not found"
    except subprocess.TimeoutExpired:
        return False, None, "timeout"


def _http_ok(url: str, timeout_sec: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            return 200 <= int(code) < 400, f"http {code}"
    except urllib.error.HTTPError as e:
        return False, f"http {e.code}"
    except Exception as e:
        return False, str(e)


def _flutter_devices() -> tuple[bool, list[dict[str, Any]], str]:
    flutter = _which("flutter")
    if not flutter:
        return False, [], "flutter not in PATH"
    ok, data, err = _run_json([flutter, "devices", "--machine"])
    if not ok or not isinstance(data, list):
        return False, [], err or "no device list"
    devices: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            devices.append(item)
    return True, devices, ""


def _has_platform(devices: list[dict[str, Any]], platform_id: str) -> bool:
    for d in devices:
        pid = str(d.get("targetPlatform") or d.get("platform") or "").lower()
        if platform_id in pid:
            return True
        # machine output uses category sometimes
        cat = str(d.get("category") or "").lower()
        if platform_id == "android" and cat == "mobile":
            # ambiguous; still require explicit platform below
            pass
    # Prefer explicit targetPlatform
    for d in devices:
        pid = str(d.get("targetPlatform") or "").lower()
        if platform_id == "android" and "android" in pid:
            return True
        if platform_id == "ios" and "ios" in pid:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="要求 PATH 内 flutter + patrol，且 devices 同时含 Android 与 iOS",
    )
    ap.add_argument("--json", action="store_true", help="stdout 打印检查结果 JSON")
    args = ap.parse_args()

    checks: dict[str, Any] = {}
    gate_blocks: list[str] = []

    py_ok = sys.version_info >= (3, 10)
    checks["python"] = {"ok": py_ok, "version": sys.version.split()[0]}
    if not py_ok:
        gate_blocks.append("python<3.10")

    flutter_path = _which("flutter")
    checks["flutter"] = {"ok": bool(flutter_path), "path": flutter_path}
    if args.strict and not flutter_path:
        gate_blocks.append("flutter_missing")

    patrol_path = _which("patrol")
    checks["patrol_cli"] = {"ok": bool(patrol_path), "path": patrol_path}
    if args.strict and not patrol_path:
        gate_blocks.append("patrol_missing")

    docker_path = _which("docker")
    checks["docker"] = {"ok": bool(docker_path), "path": docker_path}

    gw = os.environ.get("LOCAL_GAMMA_GATEWAY_BASE_URL", "").strip()
    if not gw:
        gw = os.environ.get("CHAT_AVATAR_GATEWAY_BASE_URL", "").strip()
    health_url = ""
    if gw:
        base = gw.rstrip("/")
        health_url = f"{base}/healthz"
    checks["gateway_health_check"] = {"configured": bool(gw), "url": health_url or None}
    if gw:
        ok, detail = _http_ok(health_url)
        checks["gateway_health_check"]["reachable"] = ok
        checks["gateway_health_check"]["detail"] = detail
        if not ok:
            gate_blocks.append("gateway_healthz_unreachable")
    else:
        checks["gateway_health_check"]["reachable"] = None
        if args.strict:
            gate_blocks.append("gateway_base_url_unset")

    dev_ok, devices, dev_err = _flutter_devices()
    checks["flutter_devices"] = {
        "ok": dev_ok,
        "count": len(devices),
        "error": dev_err or None,
    }
    if dev_ok:
        checks["flutter_devices"]["has_android"] = _has_platform(devices, "android")
        checks["flutter_devices"]["has_ios"] = _has_platform(devices, "ios")
        if args.strict:
            if not checks["flutter_devices"]["has_android"]:
                gate_blocks.append("no_android_device")
            if not checks["flutter_devices"]["has_ios"]:
                gate_blocks.append("no_ios_device")
    elif args.strict:
        gate_blocks.append("flutter_devices_failed")

    # Cloud / ECS：本地脚本无法核验 artifact；商用声明仍须 CI/运维侧四条 JSON
    warnings: list[str] = []
    checks["github_ecs_self_hosted"] = {
        "note": "须在有 secrets、vars、self-hosted runner 与 ECS 的环境中由 CI 或运维产出 E3/E4 证据",
        "verified_here": False,
    }
    warnings.append("cloud_gamma_pre_and_prod_smoke_evidence_not_verifiable_locally")

    strict_local_prereqs_met = bool(args.strict) and len(gate_blocks) == 0

    result = {
        "strict": args.strict,
        "strict_local_prereqs_met": strict_local_prereqs_met,
        # 本脚本从不单独授权「商用端到端全矩阵完成」——须四条环境非 dry-run JSON。
        "commercial_declaration_allowed": False,
        "commercial_declaration_note": (
            "须归档 beta、local-gamma、cloud-gamma-pre、cloud-gamma-prod-smoke 各一份 "
            "schemaVersion=1 且 status=passed 的报告；dry-run / synthetic device 不算"
        ),
        "checks": checks,
        "gate_blocks": gate_blocks,
        "warnings": warnings,
        "message": (
            "GATE_BLOCK: " + "; ".join(gate_blocks)
            if gate_blocks
            else (
                "strict 模式：本机矩阵前置项已通过；商用声明仍须四条环境 JSON（commercial_declaration_allowed=false）"
                if args.strict
                else "非 strict：仅作信息收集；加 --strict 校验 flutter/patrol/双端设备/网关 healthz"
            )
        ),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["message"])
        for item in gate_blocks:
            print(f"  - {item}")

    return 2 if (args.strict and gate_blocks) else 0


if __name__ == "__main__":
    raise SystemExit(main())

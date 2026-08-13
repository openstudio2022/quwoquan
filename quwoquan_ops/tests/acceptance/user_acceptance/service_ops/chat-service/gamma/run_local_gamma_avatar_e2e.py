#!/usr/bin/env python3
"""Run local-gamma chat avatar E2E probe and simulator matrix."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")
from typing import Any


ROOT = _find_repo_root()
sys.path.insert(0, str(ROOT))
CHAT_AVATAR_SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support"
if str(CHAT_AVATAR_SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(CHAT_AVATAR_SUPPORT_DIR))

from quwoquan_ops.cli.lib.output_paths import env_run_dir  # noqa: E402
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from managed_chat_avatar_handoff import (  # noqa: E402
    ManagedChatAvatarHandoff,
    load_managed_handoff_from_environment,
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    public_bases = get_target(
        load_environment_topology(),
        "gamma-local",
    )["publicBases"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=public_bases["api"],
    )
    parser.add_argument(
        "--media-avatar-base-url",
        default=public_bases["mediaAvatar"],
    )
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--device-id", action="append", default=[])
    parser.add_argument(
        "--report",
        default=str(
            Path(os.environ.get("QWQ_RUN_ROOT") or env_run_dir(
                "gamma", "chat-avatar-e2e", target="gamma-local"
            ))
            / "avatar_e2e_report.json"
        ),
    )
    parser.add_argument("--skip-device-matrix", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "command": command,
        "exitCode": result.returncode,
        "outputSummary": "\n".join((result.stdout or "").splitlines()[-80:]),
    }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_probe_command(
    args: argparse.Namespace,
    probe_report_path: Path,
    handoff: ManagedChatAvatarHandoff,
) -> list[str]:
    command = [
        sys.executable,
        str(
            ROOT
            / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/smoke/run_chat_avatar_e2e_probe.py"
        ),
        "--env",
        "gamma",
        "--base-url",
        args.base_url,
        "--media-avatar-base-url",
        args.media_avatar_base_url,
        "--report",
        str(probe_report_path),
        "--compose-mongo",
        *handoff.command_arguments(),
    ]
    if args.dry_run:
        command.append("--dry-run")
    return command


def build_matrix_command(
    args: argparse.Namespace,
    matrix_report_path: Path,
    handoff: ManagedChatAvatarHandoff,
) -> list[str]:
    command = [
        sys.executable,
        str(
            ROOT
            / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
            "chat-service/ci/run_chat_avatar_device_matrix.py"
        ),
        "--env",
        "gamma",
        "--platform",
        args.platform,
        "--gateway-base-url",
        args.base_url,
        "--media-avatar-base-url",
        args.media_avatar_base_url,
        "--report",
        str(matrix_report_path),
        *handoff.command_arguments(),
    ]
    for device_id in args.device_id:
        command.extend(["--device-id", device_id])
    if args.dry_run:
        command.append("--dry-run")
    return command


def main() -> int:
    args = parse_args()
    try:
        handoff = load_managed_handoff_from_environment()
        if handoff.environment != "gamma":
            raise ValueError(
                "local-gamma chat avatar requires a gamma ActorLease handoff"
            )
    except ValueError as exc:
        print(f"GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    report_path = ROOT / args.report
    probe_report_path = report_path.parent / "avatar_probe_report.json"
    matrix_report_path = report_path.parent / "avatar_device_matrix_report.json"
    report: dict[str, Any] = {
        "schema": "chat-avatar-local-gamma-e2e-report",
        "suiteId": "chat_avatar_sync",
        "scenario": "chat.group_avatar.sync_display_e2e.local_gamma",
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "rerunRecommended": False,
        "startedAt": utc_now(),
        "endedAt": "",
        "testDataLifecycle": handoff.public_document(),
        "baseUrl": args.base_url,
        "mediaAvatarBaseUrl": args.media_avatar_base_url,
        "probe": {},
        "deviceMatrix": {},
    }
    probe_cmd = build_probe_command(args, probe_report_path, handoff)
    probe_result = run(probe_cmd)
    report["probe"] = {"commandResult": probe_result, "report": read_json(probe_report_path)}
    matrix_result: dict[str, Any] = {"status": "skipped"}
    if not args.skip_device_matrix and (report["probe"].get("report") or {}).get("status") == "passed":
        matrix_cmd = build_matrix_command(args, matrix_report_path, handoff)
        matrix_command_result = run(matrix_cmd)
        matrix_result = {
            "commandResult": matrix_command_result,
            "report": read_json(matrix_report_path),
        }
    report["deviceMatrix"] = matrix_result
    probe_passed = (report["probe"].get("report") or {}).get("status") == "passed"
    matrix_passed = args.skip_device_matrix or (matrix_result.get("report") or {}).get("status") == "passed"
    report["status"] = "passed" if probe_passed and matrix_passed else "failed"
    if not probe_passed:
        report["failureCategory"] = (report["probe"].get("report") or {}).get("failureCategory") or "avatar_task_timeout"
        report["blockingReason"] = (report["probe"].get("report") or {}).get("blockingReason") or ""
        report["rerunRecommended"] = True
    elif not matrix_passed:
        report["failureCategory"] = (matrix_result.get("report") or {}).get("failureCategory") or "ui_avatar_not_visible"
        report["blockingReason"] = (matrix_result.get("report") or {}).get("blockingReason") or ""
        report["rerunRecommended"] = True
    report["endedAt"] = utc_now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[local-gamma:avatar] report: {report_path}")
    print(f"[local-gamma:avatar] status: {report['status']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

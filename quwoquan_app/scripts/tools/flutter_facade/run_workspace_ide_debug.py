#!/usr/bin/env python3
"""Start one controlled IDE launch and publish its attempt-scoped VM service file."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = REPO_ROOT / "quwoquan_app"
DEVICE_SCRIPTS_ROOT = APP_ROOT / "scripts/device"
if str(DEVICE_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_SCRIPTS_ROOT))

from canonical_app_instance.vm_service_info_file import (
    VmServiceInfoSecurityError,
    create_private_vm_service_info_file,
    ensure_private_directory,
    validate_private_vm_service_info_file,
)


LAUNCHER = APP_ROOT / "run.sh"
RUNS_ROOT = REPO_ROOT / ".qwq_output/env/repo/runs"
IDE_LOCAL_ROOT = REPO_ROOT / ".qwq_output/env/repo/local/ide"
CURRENT_SERVICE_INFO = IDE_LOCAL_ROOT / "current-vm-service-info.json"
CURRENT_ATTEMPT = IDE_LOCAL_ROOT / "current-attempt.json"


class WorkspaceIdeProjectionError(RuntimeError):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("alpha", "beta", "gamma"), required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--mode", choices=("content-live", "ui-only"), default="content-live")
    return parser


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    ensure_private_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
    os.replace(temporary, path)


def _active_attempt() -> dict[str, object] | None:
    try:
        mode = CURRENT_ATTEMPT.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as error:
        raise WorkspaceIdeProjectionError(
            f"current IDE attempt cannot be inspected: {error}"
        ) from error
    if not stat.S_ISREG(mode) or CURRENT_ATTEMPT.is_symlink():
        raise WorkspaceIdeProjectionError(
            "current IDE attempt projection is not a regular file"
        )
    try:
        payload = json.loads(CURRENT_ATTEMPT.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("projection must be an object")
        required = {
            "schema",
            "environment",
            "deviceId",
            "attemptRoot",
            "vmServiceInfoFile",
            "launchReceipt",
            "launchLog",
            "processId",
        }
        if set(payload) != required:
            raise ValueError("projection fields do not match the canonical schema")
        if payload.get("schema") != "quwoquan.workspace_ide_attempt_projection":
            raise ValueError("projection schema is invalid")
        process_id = int(payload.get("processId") or 0)
        attempt_root = str(payload.get("attemptRoot") or "")
        attempt_path = Path(attempt_root)
        if process_id <= 0 or not attempt_path.is_absolute():
            raise ValueError("projection owner identity is invalid")
        resolved_attempt = attempt_path.resolve()
        resolved_attempt.relative_to(RUNS_ROOT.resolve())
        expected_paths = {
            "vmServiceInfoFile": resolved_attempt / "vm-service-info.json",
            "launchReceipt": resolved_attempt / "attempt.json",
            "launchLog": resolved_attempt / "launch.log",
        }
        if any(
            Path(str(payload[field])).resolve() != expected
            for field, expected in expected_paths.items()
        ):
            raise ValueError("projection attempt paths are inconsistent")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise WorkspaceIdeProjectionError(
            f"current IDE attempt projection is malformed: {error}"
        ) from error
    if process_id <= 0 or not attempt_root:
        raise WorkspaceIdeProjectionError(
            "current IDE attempt projection owner identity is empty"
        )
    try:
        observed = subprocess.run(
            ["ps", "-p", str(process_id), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise WorkspaceIdeProjectionError(
            f"current IDE attempt owner probe failed: {error}"
        ) from error
    # ps(1) returns one only when the exact PID is absent.  That is the sole
    # probe failure that proves the previous owner exited; every other failure
    # must preserve the projection and block a replacement launch.
    if observed.returncode == 1 and not observed.stdout.strip():
        return None
    if observed.returncode != 0:
        raise WorkspaceIdeProjectionError(
            "current IDE attempt owner probe returned an indeterminate error"
        )
    if attempt_root not in observed.stdout:
        # A live but non-matching command proves PID reuse after the old owner
        # exited; the fully validated old projection can now be replaced.
        return None
    return payload


def _publish_service_info_projection(target: Path) -> None:
    ensure_private_directory(IDE_LOCAL_ROOT)
    validate_private_vm_service_info_file(target, allowed_root=RUNS_ROOT)
    temporary = CURRENT_SERVICE_INFO.with_name(
        f".{CURRENT_SERVICE_INFO.name}.{os.getpid()}.tmp"
    )
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, CURRENT_SERVICE_INFO)


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    device = args.device.strip()
    if not device:
        raise SystemExit("APP.LAUNCH.device_unavailable: IDE device id is empty")
    if not LAUNCHER.is_file() or not os.access(LAUNCHER, os.X_OK):
        raise SystemExit(
            "APP.LAUNCH.workspace_entrypoint_inactive: canonical launcher is unavailable"
        )
    try:
        ensure_private_directory(IDE_LOCAL_ROOT)
    except VmServiceInfoSecurityError as error:
        raise SystemExit(str(error)) from error
    try:
        active_attempt = _active_attempt()
    except WorkspaceIdeProjectionError as error:
        raise SystemExit(
            "APP.LAUNCH.workspace_entrypoint_inactive: " + str(error)
        ) from error
    if active_attempt is not None:
        raise SystemExit(
            "APP.LAUNCH.workspace_entrypoint_inactive: an IDE launch is already "
            f"active at {active_attempt['attemptRoot']}"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    attempt_root = RUNS_ROOT / f"{stamp}-{uuid4().hex[:12]}-workspace-ide-launch"
    attempt_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    ensure_private_directory(attempt_root)
    vm_service_info = attempt_root / "vm-service-info.json"
    receipt = attempt_root / "attempt.json"
    launch_log = attempt_root / "launch.log"
    try:
        create_private_vm_service_info_file(vm_service_info)
        _publish_service_info_projection(vm_service_info)
        _atomic_json(
            CURRENT_ATTEMPT,
            {
                "schema": "quwoquan.workspace_ide_attempt_projection",
                "environment": args.env,
                "deviceId": device,
                "attemptRoot": str(attempt_root),
                "vmServiceInfoFile": str(vm_service_info),
                "launchReceipt": str(receipt),
                "launchLog": str(launch_log),
                "processId": os.getpid(),
            },
        )
    except VmServiceInfoSecurityError as error:
        raise SystemExit(str(error)) from error

    environment = dict(os.environ)
    environment["QWQ_APP_LAUNCH_PROVENANCE"] = "workspace_ide_debug"
    environment["QWQ_ENVIRONMENT"] = args.env
    print(
        "[workspace-ide] START "
        f"environment={args.env} device={device} attemptRoot={attempt_root}",
        flush=True,
    )
    command = [
        str(LAUNCHER),
        "--env",
        args.env,
        "--mode",
        args.mode,
        "--launch-receipt",
        str(receipt),
        "--launch-log-ref",
        str(launch_log),
        "--ide-vm-service-info",
        str(vm_service_info),
        "-d",
        device,
    ]
    os.chdir(APP_ROOT)
    os.execve(str(LAUNCHER), command, environment)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

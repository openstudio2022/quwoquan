#!/usr/bin/env python3
"""Grok Bot 受控多 profile 生命周期；不保存凭证，不拥有 producer authority。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "quwoquan_ops.grok_bot_instance.v1"
INSTANCE_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
DEFAULT_APP = Path("/Applications/Grok Bot.app")
DEFAULT_STATE_ROOT = Path.home() / "Library/Application Support/Grok Bot Instance Manager"
PROFILE_MARKER = ".qwq-grok-profile-v1"


class InstanceError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _canonical(path: Path) -> Path:
    return path.expanduser().absolute()


def _validate_instance_id(value: str) -> str:
    if not value or len(value) > 48 or value[0] == "-" or value[-1] == "-" or any(c not in INSTANCE_ID_CHARS for c in value):
        raise InstanceError("GROK_INSTANCE.INVALID_ID", value)
    return value


def _assert_plain_directory(path: Path, *, create: bool, mode: int = 0o700) -> Path:
    target = _canonical(path)
    if target.is_symlink():
        raise InstanceError("GROK_INSTANCE.SYMLINK_FORBIDDEN", str(target))
    if create:
        target.mkdir(parents=True, exist_ok=True, mode=mode)
    if not target.is_dir() or target.is_symlink():
        raise InstanceError("GROK_INSTANCE.DIRECTORY_REQUIRED", str(target))
    os.chmod(target, mode)
    return target.resolve()


def _assert_existing_directory(path: Path) -> Path:
    target = _canonical(path)
    if target.is_symlink() or not target.is_dir():
        raise InstanceError("GROK_INSTANCE.DIRECTORY_REQUIRED", str(target))
    return target.resolve()


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _assert_disjoint(paths: Mapping[str, Path]) -> None:
    items = list(paths.items())
    for index, (left_name, left) in enumerate(items):
        for right_name, right in items[index + 1 :]:
            if _overlaps(left, right):
                raise InstanceError("GROK_INSTANCE.PATH_OVERLAP", f"{left_name}={left} {right_name}={right}")


def _app_identity(app: Path) -> dict[str, str]:
    app = _canonical(app)
    plist = app / "Contents/Info.plist"
    executable = app / "Contents/MacOS/Grok Bot"
    asar = app / "Contents/Resources/app.asar"
    if not plist.is_file() or not executable.is_file() or not asar.is_file():
        raise InstanceError("GROK_INSTANCE.APP_INVALID", str(app))
    with plist.open("rb") as handle:
        info = plistlib.load(handle)
    if info.get("CFBundleIdentifier") != "com.anysphere.sand":
        raise InstanceError("GROK_INSTANCE.BUNDLE_ID_MISMATCH", str(info.get("CFBundleIdentifier")))
    digest = hashlib.sha256(asar.read_bytes()).hexdigest()
    return {
        "app": str(app.resolve()),
        "executable": str(executable.resolve()),
        "bundleId": "com.anysphere.sand",
        "version": str(info.get("CFBundleShortVersionString") or ""),
        "asarSha256": f"sha256:{digest}",
    }


def _volume_uuid(volume_root: Path) -> str:
    completed = subprocess.run(
        ["diskutil", "info", "-plist", str(volume_root)], check=False, capture_output=True
    )
    if completed.returncode != 0:
        raise InstanceError("GROK_INSTANCE.VOLUME_UNAVAILABLE", str(volume_root))
    try:
        info = plistlib.loads(completed.stdout)
    except Exception as exc:
        raise InstanceError("GROK_INSTANCE.VOLUME_INFO_INVALID", str(volume_root)) from exc
    value = info.get("VolumeUUID")
    if not isinstance(value, str) or not value:
        raise InstanceError("GROK_INSTANCE.VOLUME_UUID_MISSING", str(volume_root))
    return value


def _manifest_path(state_root: Path, instance_id: str) -> Path:
    return _canonical(state_root) / instance_id / "manifest.json"


def _write_create_or_same(path: Path, document: Mapping[str, Any]) -> str:
    data = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise InstanceError("GROK_INSTANCE.MANIFEST_UNSAFE", str(path))
        if path.read_bytes() == data:
            return "replayed"
        raise InstanceError("GROK_INSTANCE.MANIFEST_CONFLICT", str(path))
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return "created"


def _read_manifest(state_root: Path, instance_id: str) -> tuple[Path, dict[str, Any]]:
    path = _manifest_path(state_root, _validate_instance_id(instance_id))
    if path.is_symlink() or not path.is_file():
        raise InstanceError("GROK_INSTANCE.NOT_PREPARED", instance_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("instanceId") != instance_id:
        raise InstanceError("GROK_INSTANCE.MANIFEST_INVALID", str(path))
    return path, document


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    instance_id = _validate_instance_id(args.instance_id)
    app = _app_identity(Path(args.app))
    paths = {
        "profileRoot": _assert_plain_directory(Path(args.profile_root), create=True),
        "dataRoot": _assert_plain_directory(Path(args.data_root), create=True),
        "outputRoot": _assert_plain_directory(Path(args.output_root), create=True),
        "workspaceRoot": _assert_plain_directory(Path(args.workspace_root), create=True),
        "libraryRoot": _assert_plain_directory(Path(args.library_root), create=True),
        "carriedMediaRoot": _assert_plain_directory(Path(args.carried_media_root), create=True),
    }
    _assert_disjoint(paths)
    profile_entries = [entry.name for entry in paths["profileRoot"].iterdir()]
    if profile_entries and profile_entries != [PROFILE_MARKER]:
        raise InstanceError("GROK_INSTANCE.PROFILE_NOT_EMPTY", str(paths["profileRoot"]))
    marker = paths["profileRoot"] / PROFILE_MARKER
    marker.touch(exist_ok=True, mode=0o600)
    volume_root = _assert_existing_directory(Path(args.volume_root))
    actual_uuid = _volume_uuid(volume_root)
    if actual_uuid.lower() != args.expected_volume_uuid.lower():
        raise InstanceError("GROK_INSTANCE.VOLUME_UUID_MISMATCH", f"expected={args.expected_volume_uuid} actual={actual_uuid}")
    for name in ("outputRoot", "workspaceRoot", "libraryRoot", "carriedMediaRoot"):
        if volume_root != paths[name] and volume_root not in paths[name].parents:
            raise InstanceError("GROK_INSTANCE.EXTERNAL_ROOT_REQUIRED", name)
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "instanceId": instance_id,
        "appIdentity": app,
        "paths": {name: str(path) for name, path in paths.items()},
        "volume": {"root": str(volume_root), "uuid": actual_uuid},
        "publishRoot": str(_canonical(Path(args.publish_root)).resolve()),
        "coordinationDb": str(_canonical(Path(args.coordination_db)).resolve()),
        "lifecycle": {"state": "prepared"},
    }
    manifest = _manifest_path(Path(args.state_root), instance_id)
    status = _write_create_or_same(manifest, document)
    return {"status": status, "manifest": str(manifest), "instance": document}


def _pid_command(pid: int) -> str | None:
    completed = subprocess.run(["ps", "-p", str(pid), "-o", "command="], check=False, capture_output=True, text=True)
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _descendants(pid: int) -> set[int]:
    completed = subprocess.run(["ps", "ax", "-o", "pid=,ppid="], check=False, capture_output=True, text=True)
    children: dict[int, set[int]] = {}
    for line in completed.stdout.splitlines():
        try:
            child, parent = (int(value) for value in line.split())
        except (TypeError, ValueError):
            continue
        children.setdefault(parent, set()).add(child)
    result: set[int] = set()
    pending = list(children.get(pid, ()))
    while pending:
        child = pending.pop()
        if child not in result:
            result.add(child); pending.extend(children.get(child, ()))
    return result


def _terminate_exact_process_tree(document: Mapping[str, Any], pid: int, timeout: float) -> None:
    descendants = _descendants(pid)
    # 后代身份由当下 parent tree 确定；在父进程退出前先终止，防止 daemon reparent 后失去归属。
    for process_id in sorted(descendants, reverse=True):
        try: os.kill(process_id, signal.SIGTERM)
        except ProcessLookupError: pass
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    process_ids = descendants | {pid}
    while time.monotonic() < deadline:
        if all(_pid_command(process_id) is None for process_id in process_ids):
            return
        time.sleep(0.1)
    alive = sorted(process_id for process_id in process_ids if _pid_command(process_id) is not None)
    raise InstanceError("GROK_INSTANCE.STOP_TIMEOUT", ",".join(str(value) for value in alive))


def _expected_process(document: Mapping[str, Any], pid: int) -> bool:
    command = _pid_command(pid)
    if command is None:
        return False
    executable = str(document["appIdentity"]["executable"])
    profile = str(document["paths"]["profileRoot"])
    return executable in command and (f"--user-data-dir={profile}" in command or f"--user-data-dir {profile}" in command)


def _replace_manifest(path: Path, document: Mapping[str, Any]) -> None:
    data = (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data); os.chmod(temporary, 0o600); os.replace(temporary, path)


def start(args: argparse.Namespace) -> dict[str, Any]:
    path, document = _read_manifest(Path(args.state_root), args.instance_id)
    current = _app_identity(Path(document["appIdentity"]["app"]))
    if current != document["appIdentity"]:
        raise InstanceError("GROK_INSTANCE.PROFILE_REVALIDATION_REQUIRED", args.instance_id)
    previous_pid = document.get("lifecycle", {}).get("pid")
    if isinstance(previous_pid, int) and _expected_process(document, previous_pid):
        return {"status": "already-running", "instanceId": args.instance_id, "pid": previous_pid}
    paths = document["paths"]
    env = dict(os.environ)
    env.update({
        "SAND_USER_DATA_DIR": paths["profileRoot"],
        "SAND_DATA_ROOT": paths["dataRoot"],
        "QWQ_OUTPUT_ROOT": paths["outputRoot"],
        "QWQ_LIBRARY_ROOT": paths["libraryRoot"],
        "QWQ_CARRIED_MEDIA_ROOT": paths["carriedMediaRoot"],
        "QWQ_PUBLISH_ROOT": document["publishRoot"],
        "QWQ_CONTENT_COORDINATION_DB": document["coordinationDb"],
        "QWQ_CONTENT_WORKSPACE_ROOT": paths["workspaceRoot"],
    })
    command = [document["appIdentity"]["executable"], f"--user-data-dir={paths['profileRoot']}"]
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    updated = dict(document); updated["lifecycle"] = {"state": "running", "pid": process.pid, "startedAtMs": int(time.time() * 1000)}
    _replace_manifest(path, updated)
    return {"status": "started", "instanceId": args.instance_id, "pid": process.pid}


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    _path, document = _read_manifest(Path(args.state_root), args.instance_id)
    current = _app_identity(Path(document["appIdentity"]["app"]))
    lifecycle = document.get("lifecycle", {})
    pid = lifecycle.get("pid")
    running = isinstance(pid, int) and _expected_process(document, pid)
    status_path = Path(document["paths"]["profileRoot"]) / "desktop-status.json"
    signed_in: bool | None = None
    if running and status_path.is_file() and not status_path.is_symlink():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            signed_in = status.get("signedIn") if isinstance(status.get("signedIn"), bool) else None
        except (OSError, json.JSONDecodeError):
            pass
    singleton = Path(document["paths"]["profileRoot"]) / "SingletonLock"
    return {
        "schema": "quwoquan_ops.grok_bot_instance_inspection.v1",
        "instanceId": args.instance_id,
        "state": "PROFILE_REVALIDATION_REQUIRED" if current != document["appIdentity"] else ("running" if running else "stopped"),
        "pid": pid if running else None,
        "profileRoot": document["paths"]["profileRoot"],
        "dataRoot": document["paths"]["dataRoot"],
        "appIdentity": current,
        "singletonLockPresent": singleton.is_symlink() or singleton.is_file(),
        "signedIn": signed_in,
    }


def stop(args: argparse.Namespace) -> dict[str, Any]:
    path, document = _read_manifest(Path(args.state_root), args.instance_id)
    pid = document.get("lifecycle", {}).get("pid")
    if not isinstance(pid, int) or not _expected_process(document, pid):
        return {"status": "already-stopped", "instanceId": args.instance_id}
    _terminate_exact_process_tree(document, pid, args.timeout)
    updated = dict(document); updated["lifecycle"] = {"state": "stopped", "stoppedAtMs": int(time.time() * 1000)}
    _replace_manifest(path, updated)
    return {"status": "stopped", "instanceId": args.instance_id, "pid": pid}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="grok-bot-instances")
    root.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    commands = root.add_subparsers(dest="command", required=True)
    prepared = commands.add_parser("prepare")
    prepared.add_argument("--instance-id", required=True); prepared.add_argument("--app", default=str(DEFAULT_APP))
    for name in ("profile-root", "data-root", "output-root", "workspace-root", "library-root", "carried-media-root", "volume-root", "expected-volume-uuid", "publish-root", "coordination-db"):
        prepared.add_argument(f"--{name}", required=True)
    prepared.set_defaults(handler=prepare)
    for name, handler in (("start", start), ("inspect", inspect), ("stop", stop)):
        item = commands.add_parser(name); item.add_argument("--instance-id", required=True); item.set_defaults(handler=handler)
        if name == "stop": item.add_argument("--timeout", type=float, default=10.0)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (InstanceError, OSError, ValueError, json.JSONDecodeError) as exc:
        code = exc.code if isinstance(exc, InstanceError) else "GROK_INSTANCE.UNEXPECTED"
        print(json.dumps({"terminal": "GATE_BLOCK", "error": {"code": code, "detail": str(exc)}}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

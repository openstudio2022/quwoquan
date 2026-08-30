#!/usr/bin/env python3
"""为 Cursor workspace terminal surface 写入并校验最小、脱敏回执。"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "qwq.flutter-facade-terminal-receipt.v1"
SURFACES = frozenset({"unknown", "folder-new-terminal", "agents-window"})
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
FACADE_DIR = Path(__file__).resolve().parent
REPO_ROOT = FACADE_DIR.parents[3]
FACADE_EXECUTABLE = FACADE_DIR / "bin/flutter"
RECEIPT_ROOT = (
    REPO_ROOT / ".qwq_output/env/repo/local/flutter-facade-terminal-receipts"
)
REQUIRED_KEYS = frozenset(
    {
        "schema",
        "surface",
        "workspaceUri",
        "workspaceLogicalRoot",
        "workspacePhysicalRoot",
        "shellPid",
        "shellStart",
        "writtenAtEpochMs",
        "finalStateValidated",
        "facadeRealpath",
        "qwqIdentity",
        "projectionSeal",
        "projectionGeneration",
    }
)
IDENTITY_KEYS = frozenset(
    {
        "facadeBinRealpath",
        "realFlutterRealpath",
        "realFlutterVersion",
        "commandResolutionDigest",
    }
)


class ReceiptError(ValueError):
    pass


def process_start(pid: int) -> str:
    if pid <= 1:
        raise ReceiptError("shell PID is invalid")
    completed = subprocess.run(
        ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise ReceiptError("shell PID is not alive")
    return " ".join(value.split())


def _literal_absolute(path: str, *, field: str) -> Path:
    candidate = Path(path)
    if (
        not path
        or not candidate.is_absolute()
        or str(candidate) != path
        or any(part in {"", ".", ".."} for part in candidate.parts[1:])
    ):
        raise ReceiptError(f"{field} must be a literal absolute path")
    return candidate


def _private_receipt_root(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_resolved = path.parent.resolve(strict=True)
    expected = parent_resolved / path.name
    resolved = path.resolve(strict=True)
    if resolved != expected:
        raise ReceiptError("receipt root leaf contains a symlink")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(resolved, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ReceiptError("receipt root is not a directory")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise ReceiptError("receipt root owner differs from current user")
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    return resolved


def _identity(environ: dict[str, str]) -> dict[str, str]:
    facade_bin = Path(environ.get("QWQ_WORKSPACE_FLUTTER_FACADE_BIN", ""))
    real_flutter = Path(environ.get("QWQ_REAL_FLUTTER", ""))
    version = environ.get("QWQ_REAL_FLUTTER_VERSION", "").strip()
    digest = environ.get(
        "QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST", ""
    ).strip()
    try:
        facade_bin_realpath = str(facade_bin.resolve(strict=True))
        real_flutter_realpath = str(real_flutter.resolve(strict=True))
    except OSError as error:
        raise ReceiptError("QWQ terminal identity paths are unavailable") from error
    if facade_bin_realpath != str(FACADE_EXECUTABLE.parent.resolve(strict=True)):
        raise ReceiptError("QWQ facade bin identity differs from launcher")
    if not version or not DIGEST_PATTERN.fullmatch(digest):
        raise ReceiptError("QWQ Flutter identity is incomplete")
    return {
        "facadeBinRealpath": facade_bin_realpath,
        "realFlutterRealpath": real_flutter_realpath,
        "realFlutterVersion": version,
        "commandResolutionDigest": digest,
    }



def _final_command_realpath(
    environ: dict[str, str], *, key: str, executable: Path, field: str
) -> str:
    value = environ.get(key, "").strip()
    candidate = _literal_absolute(value, field=field)
    try:
        resolved = candidate.resolve(strict=True)
        expected = executable.resolve(strict=True)
    except OSError as error:
        raise ReceiptError(f"{field} is unavailable") from error
    if resolved != expected:
        raise ReceiptError(f"{field} differs from projected executable")
    return str(resolved)


def _validate_final_state(environ: dict[str, str]) -> None:
    _final_command_realpath(
        environ,
        key="QWQ_TERMINAL_FINAL_FLUTTER_COMMAND_REALPATH",
        executable=FACADE_EXECUTABLE,
        field="finalFlutterCommandRealpath",
    )
    pod_value = environ.get("QWQ_COCOAPODS_EXECUTABLE", "").strip()
    pod = _literal_absolute(pod_value, field="QWQ_COCOAPODS_EXECUTABLE")
    _final_command_realpath(
        environ,
        key="QWQ_TERMINAL_FINAL_POD_COMMAND_REALPATH",
        executable=pod,
        field="finalPodCommandRealpath",
    )
    try:
        repo_root_value = str(REPO_ROOT)
        if repo_root_value not in sys.path:
            sys.path.insert(0, repo_root_value)
        from quwoquan_ops.cli.lib.app_dependency_toolchain import (
            validate_cocoapods_child_environment,
        )

        validate_cocoapods_child_environment(environ)
    except (ImportError, RuntimeError, ValueError) as error:
        raise ReceiptError("final CocoaPods child environment validation failed") from error


def write_receipt(
    *,
    surface: str,
    shell_pid: int,
    workspace_uri: str,
    logical_root: str,
    physical_root: str,
    environ: dict[str, str],
    receipt_root: Path = RECEIPT_ROOT,
) -> Path:
    if surface not in SURFACES:
        raise ReceiptError("terminal surface is outside the closed set")
    logical = _literal_absolute(logical_root, field="workspaceLogicalRoot")
    physical = _literal_absolute(physical_root, field="workspacePhysicalRoot")
    try:
        if logical.resolve(strict=True) != physical.resolve(strict=True):
            raise ReceiptError("logical and physical workspace roots disagree")
        if physical.resolve(strict=True) != REPO_ROOT.resolve(strict=True):
            raise ReceiptError("workspace root differs from launcher repository")
    except OSError as error:
        raise ReceiptError("workspace root cannot be resolved") from error
    if workspace_uri not in {str(logical), logical.as_uri()}:
        raise ReceiptError("workspace URI differs from logical root")
    projection_seal = environ.get("QWQ_TERMINAL_PROJECTION_SEAL", "").strip()
    generation = environ.get("QWQ_TERMINAL_PROJECTION_GENERATION", "").strip()
    if not DIGEST_PATTERN.fullmatch(projection_seal):
        raise ReceiptError("projection seal is invalid")
    if not DIGEST_PATTERN.fullmatch(generation):
        raise ReceiptError("projection generation is invalid")
    shell_start = process_start(shell_pid)
    _validate_final_state(environ)
    payload = {
        "schema": SCHEMA,
        "surface": surface,
        "workspaceUri": workspace_uri,
        "workspaceLogicalRoot": str(logical),
        "workspacePhysicalRoot": str(physical),
        "shellPid": shell_pid,
        "shellStart": shell_start,
        "writtenAtEpochMs": time.time_ns() // 1_000_000,
        "finalStateValidated": True,
        "facadeRealpath": str(FACADE_EXECUTABLE.resolve(strict=True)),
        "qwqIdentity": _identity(environ),
        "projectionSeal": projection_seal,
        "projectionGeneration": generation,
    }
    root = _private_receipt_root(receipt_root)
    name = f"{surface}--{shell_pid}--{generation.removeprefix('sha256:')}.json"
    destination = root / name
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError:
        existing = destination.read_bytes()
        if existing != encoded:
            raise ReceiptError("create-once terminal receipt already differs")
        return destination
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def load_receipt(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ReceiptError("receipt is not a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ReceiptError("receipt permissions are not private")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise ReceiptError("receipt owner differs from current user")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != REQUIRED_KEYS:
        raise ReceiptError("receipt fields differ from schema")
    if payload.get("schema") != SCHEMA:
        raise ReceiptError("receipt schema is unsupported")
    if payload.get("finalStateValidated") is not True:
        raise ReceiptError("receipt final state was not validated")
    identity = payload.get("qwqIdentity")
    if not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS:
        raise ReceiptError("receipt QWQ identity fields differ from schema")
    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=sorted(SURFACES), required=True)
    parser.add_argument("--shell-pid", type=int, required=True)
    parser.add_argument("--workspace-uri", required=True)
    parser.add_argument("--logical-root", required=True)
    parser.add_argument("--physical-root", required=True)
    parser.add_argument("--receipt-root", type=Path, default=RECEIPT_ROOT)
    args = parser.parse_args(argv)
    try:
        path = write_receipt(
            surface=args.surface,
            shell_pid=args.shell_pid,
            workspace_uri=args.workspace_uri,
            logical_root=args.logical_root,
            physical_root=args.physical_root,
            environ=dict(os.environ),
            receipt_root=args.receipt_root,
        )
    except (OSError, ReceiptError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; {error}", file=os.sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))

"""Filesystem identity and activity probes for output-layout reconciliation."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class OutputLayoutReconciliationError(ValueError):
    """A planned filesystem identity cannot be proven safe."""


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_digest(payload: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _tree_snapshot(path: Path) -> tuple[int, int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    entry_count = 0
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(path).as_posix()
        metadata = candidate.lstat()
        entry_count += 1
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.S_IFMT(metadata.st_mode)).encode("ascii"))
        digest.update(b"\0")
        if candidate.is_symlink():
            raise OutputLayoutReconciliationError(
                f"planned directory contains a symlink: {candidate}"
            )
        if candidate.is_file():
            byte_count += metadata.st_size
            digest.update(file_digest(candidate).encode("ascii"))
        elif not candidate.is_dir():
            raise OutputLayoutReconciliationError(
                f"planned directory contains a special file: {candidate}"
            )
        digest.update(b"\0")
    return byte_count, entry_count, "sha256:" + digest.hexdigest()


def snapshot_path(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise OutputLayoutReconciliationError(f"planned path is missing: {path}") from exc
    kind = (
        "symlink"
        if stat.S_ISLNK(metadata.st_mode)
        else "directory"
        if stat.S_ISDIR(metadata.st_mode)
        else "file"
        if stat.S_ISREG(metadata.st_mode)
        else "other"
    )
    if kind == "file":
        byte_count, entry_count, digest = metadata.st_size, 1, file_digest(path)
    elif kind == "directory":
        byte_count, entry_count, digest = _tree_snapshot(path)
    elif kind == "symlink":
        target = os.readlink(path)
        encoded_target = target.encode("utf-8")
        byte_count, entry_count = len(encoded_target), 1
        digest = "sha256:" + hashlib.sha256(encoded_target).hexdigest()
    else:
        byte_count, entry_count = metadata.st_size, 1
        digest = "sha256:" + hashlib.sha256(b"").hexdigest()
    return {
        "kind": kind,
        "mode": stat.S_IMODE(metadata.st_mode),
        "pathByteLength": len(str(path).encode("utf-8")),
        "byteCount": byte_count,
        "entryCount": entry_count,
        "mtimeNs": metadata.st_mtime_ns,
        "sha256": digest,
    }


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def lsof_records(
    roots: Sequence[Path],
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    issues: list[str] = []
    for root in sorted(set(roots), key=lambda item: item.as_posix()):
        if not root.exists():
            continue
        argv = (
            ["lsof", "-F", "pfn", "+D", str(root)]
            if root.is_dir()
            else ["lsof", "-F", "pfn", "--", str(root)]
        )
        try:
            result = subprocess.run(
                argv,
                check=False,
                text=True,
                capture_output=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except FileNotFoundError:
            return {}, ["open-fd probe unavailable: lsof is not installed"]
        if result.returncode not in {0, 1}:
            detail = result.stderr.strip() or f"exit={result.returncode}"
            issues.append(f"open-fd probe failed for {root}: {detail}")
            continue
        pid: int | None = None
        descriptor = ""
        for raw_line in result.stdout.splitlines():
            if not raw_line:
                continue
            field, value = raw_line[0], raw_line[1:]
            if field == "p":
                pid = int(value) if value.isdigit() else None
            elif field == "f":
                descriptor = value
            elif field == "n" and pid is not None:
                records[str(Path(value).absolute())].append(
                    {"pid": pid, "descriptor": descriptor or "unknown"}
                )
    return dict(records), issues


def activity_for_path(
    path: Path,
    open_files: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[int], list[int]]:
    process_pids: set[int] = set()
    open_fd_pids: set[int] = set()
    for open_path_value, entries in open_files.items():
        open_path = Path(open_path_value).absolute()
        if open_path != path and not is_within(open_path, path):
            continue
        for entry in entries:
            pid = int(entry.get("pid") or 0)
            if pid <= 0:
                continue
            if str(entry.get("descriptor") or "") in {"cwd", "rtd", "txt"}:
                process_pids.add(pid)
            else:
                open_fd_pids.add(pid)
    return sorted(process_pids), sorted(open_fd_pids)

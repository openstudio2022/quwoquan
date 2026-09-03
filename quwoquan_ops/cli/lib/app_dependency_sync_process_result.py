"""Private, non-publication result for one App dependency sync process."""

from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

PROCESS_RESULT_SCHEMA = "stackctl-app-dependency-sync-process-result.v1"


def _private_directory_fd(path: Path, *, label: str) -> int:
    absolute = path.expanduser().absolute()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise RuntimeError("App dependency process result requires no-follow IO")
    descriptor = os.open(absolute.anchor, os.O_RDONLY | directory)
    try:
        for segment in absolute.parts[1:]:
            next_descriptor = os.open(
                segment,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"App dependency {label} is not a real directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def atomic_process_result(path: Path, value: dict[str, Any]) -> None:
    encoded = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    parent = _private_directory_fd(path.parent, label="process result parent")
    temporary_name = f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent,
        )
        os.fchmod(descriptor, 0o600)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("App dependency process result write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
        )
        os.fsync(parent)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent)
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(parent)


def _process_log_refs(*, output: Path, process_root: Path | None) -> list[str]:
    if process_root is None:
        return []
    try:
        descriptor = _private_directory_fd(process_root, label="process log root")
    except (OSError, RuntimeError, ValueError):
        return []
    os.close(descriptor)
    refs: list[str] = []
    for child in sorted(process_root.iterdir(), key=lambda item: item.name):
        try:
            metadata = child.stat(follow_symlinks=False)
        except OSError:
            continue
        if (
            child.name != "result.json"
            and stat.S_ISREG(metadata.st_mode)
            and metadata.st_nlink == 1
            and stat.S_IMODE(metadata.st_mode) == 0o600
        ):
            refs.append(child.relative_to(output).as_posix())
    return refs


def process_result_payload(
    *,
    attempt_id: str,
    outcome: Mapping[str, Any],
    failed_phase: str,
    cause: str,
    output: Path,
    process_root: Path | None,
    sensitive_values: tuple[str, ...],
    redact: Callable[..., str],
) -> dict[str, Any]:
    exit_code = int(outcome.get("exitCode", 2))
    summary = redact(
        str(outcome.get("summary") or "App dependency sync blocked"),
        sensitive_values=sensitive_values,
    )
    output_prefix = str(output) + os.sep
    details = [
        redact(
            str(item).replace(output_prefix, ""),
            sensitive_values=sensitive_values,
        )
        or "APP.DEPENDENCY.diagnostic_empty"
        for item in list(outcome.get("details") or [])
    ]
    return {
        "schema": PROCESS_RESULT_SCHEMA,
        "attemptId": attempt_id,
        "exitCode": exit_code,
        "summary": summary,
        "details": details,
        "failedPhase": failed_phase if exit_code != 0 else "",
        "cause": cause if exit_code != 0 else "",
        "logRefs": _process_log_refs(output=output, process_root=process_root),
    }

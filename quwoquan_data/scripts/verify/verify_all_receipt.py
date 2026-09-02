"""Create-once exact receipt for the canonical public ``verify all`` command."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TypeVar

from content.execution.operational_fingerprint import operational_fingerprint
from core import paths
from core.schema import assert_valid

SCHEMA = "quwoquan_data.verify_all_receipt"
COMMAND_ID = "data.verify.all"
ENTRYPOINT = "quwoquan_data/scripts/cli.py"
COMMAND_ARGUMENTS = ["verify", "all"]

_Result = TypeVar("_Result")


class VerifyAllReceiptError(ValueError):
    """The requested receipt cannot be produced without weakening evidence."""


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _reject_existing_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise VerifyAllReceiptError(
                f"verify-all receipt path contains symbolic link: {current}"
            )


def validate_output_path(output: Path) -> Path:
    destination = _absolute(Path(output))
    allowed_root = _absolute(paths.DATA_LOCAL_ROOT / "runs")
    try:
        relative = destination.relative_to(allowed_root)
    except ValueError as exc:
        raise VerifyAllReceiptError(
            f"--output must be under local run evidence root {allowed_root}"
        ) from exc
    if not relative.parts:
        raise VerifyAllReceiptError("--output must name a receipt file")
    _reject_existing_symlink_components(destination)
    return destination


def _open_directory_chain(path: Path) -> int:
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(
                part,
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_at(parent_fd: int, name: str) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise VerifyAllReceiptError("verify-all receipt destination is not regular")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def write_create_once(output: Path, document: Mapping[str, object]) -> Path:
    destination = validate_output_path(output)
    body = _canonical_bytes(document)
    parent_fd = _open_directory_chain(destination.parent)
    try:
        try:
            descriptor = os.open(
                destination.name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            if _read_regular_at(parent_fd, destination.name) != body:
                raise VerifyAllReceiptError(
                    f"verify-all receipt create-once collision: {destination}"
                ) from None
            return destination
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise VerifyAllReceiptError(
                    "verify-all receipt destination must be a regular file"
                )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                os.unlink(destination.name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
    finally:
        os.close(parent_fd)
    return destination


def _flush_standard_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, OSError):
            pass


class _BinaryFdWriter:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def write(self, value: bytes | bytearray) -> int:
        body = bytes(value)
        view = memoryview(body)
        while view:
            view = view[os.write(self._fd, view) :]
        return len(body)

    def flush(self) -> None:
        return None


class _TextFdWriter:
    def __init__(self, fd: int, original: object) -> None:
        self._fd = fd
        self.encoding = str(getattr(original, "encoding", None) or "utf-8")
        self.errors = str(getattr(original, "errors", None) or "strict")
        self.buffer = _BinaryFdWriter(fd)

    def write(self, value: str) -> int:
        self.buffer.write(value.encode(self.encoding, errors=self.errors))
        return len(value)

    def flush(self) -> None:
        return None

    def fileno(self) -> int:
        return self._fd

    def isatty(self) -> bool:
        return False


class _FdTeeCapture:
    """Capture exact process output bytes while teeing them to the caller."""

    def __init__(self) -> None:
        self._saved: dict[int, int] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._buffers: dict[int, bytearray] = {1: bytearray(), 2: bytearray()}
        self._original_streams: dict[int, object] = {}

    def _drain(self, fd: int, read_fd: int, visible_fd: int) -> None:
        try:
            while True:
                chunk = os.read(read_fd, 64 * 1024)
                if not chunk:
                    return
                self._buffers[fd].extend(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(visible_fd, view)
                    view = view[written:]
        finally:
            os.close(read_fd)

    def __enter__(self) -> "_FdTeeCapture":
        _flush_standard_streams()
        try:
            for fd in (1, 2):
                saved = os.dup(fd)
                read_fd, write_fd = os.pipe()
                os.dup2(write_fd, fd)
                os.close(write_fd)
                self._saved[fd] = saved
                thread = threading.Thread(
                    target=self._drain,
                    args=(fd, read_fd, saved),
                    name=f"verify-all-output-{fd}",
                    daemon=True,
                )
                self._threads[fd] = thread
                thread.start()
            for fd, stream_name in ((1, "stdout"), (2, "stderr")):
                stream = getattr(sys, stream_name)
                try:
                    stream_fd = stream.fileno()
                except (AttributeError, OSError):
                    stream_fd = None
                if stream_fd != fd:
                    self._original_streams[fd] = stream
                    setattr(sys, stream_name, _TextFdWriter(fd, stream))
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        _flush_standard_streams()
        for fd, stream in self._original_streams.items():
            setattr(sys, "stdout" if fd == 1 else "stderr", stream)
        for fd, saved in self._saved.items():
            os.dup2(saved, fd)
        for thread in self._threads.values():
            thread.join()
        for saved in self._saved.values():
            os.close(saved)
        self._saved.clear()
        self._threads.clear()
        self._original_streams.clear()

    def bytes_for(self, fd: int) -> bytes:
        return bytes(self._buffers[fd])


def capture_and_tee(run: Callable[[], _Result]) -> tuple[_Result, bytes, bytes]:
    capture = _FdTeeCapture()
    with capture:
        result = run()
    return result, capture.bytes_for(1), capture.bytes_for(2)


def build_receipt(
    *, source_fingerprint: str, stdout: bytes, stderr: bytes, closed_modules: Sequence[str]
) -> dict[str, object]:
    modules = list(map(str, closed_modules))
    if not modules or len(set(modules)) != len(modules):
        raise VerifyAllReceiptError("verify-all closed module list is invalid")
    receipt: dict[str, object] = {
        "schema": SCHEMA,
        "sourceFingerprint": source_fingerprint,
        "command": {
            "commandId": COMMAND_ID,
            "entrypoint": ENTRYPOINT,
            "arguments": list(COMMAND_ARGUMENTS),
        },
        "exitCode": 0,
        "verdict": "pass",
        "capturedOutput": {
            "stdoutDigest": _digest_bytes(stdout),
            "stderrDigest": _digest_bytes(stderr),
        },
        "closedModules": modules,
    }
    assert_valid(receipt, "execution", "verify_all_receipt")
    return receipt


def run_with_receipt(
    *, output: Path, run: Callable[[], Sequence[str]]
) -> tuple[dict[str, object], Path]:
    destination = validate_output_path(output)
    before = operational_fingerprint(repo_root=paths.REPO_ROOT)
    closed_modules, stdout, stderr = capture_and_tee(run)
    after = operational_fingerprint(repo_root=paths.REPO_ROOT)
    if after != before:
        raise VerifyAllReceiptError(
            "operational fingerprint changed while verify all was running"
        )
    receipt = build_receipt(
        source_fingerprint=after,
        stdout=stdout,
        stderr=stderr,
        closed_modules=closed_modules,
    )
    return receipt, write_create_once(destination, receipt)


__all__ = [
    "COMMAND_ARGUMENTS",
    "COMMAND_ID",
    "ENTRYPOINT",
    "SCHEMA",
    "VerifyAllReceiptError",
    "build_receipt",
    "capture_and_tee",
    "run_with_receipt",
    "validate_output_path",
    "write_create_once",
]

"""部署输入枚举与只读 content-addressed input capsule（逐字迁自原单文件）。

``ROOT`` 经包属性（``_pkg.``）消费，保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

import quwoquan_ops.cli.lib.package_reuse as _pkg

from .constants import (
    _CAPSULE_ENTRY_FIELDS,
    _CAPSULE_FIELDS,
    PACKAGE_INPUT_CAPSULE_SCHEMA,
)


def _digest_record(
    entries: Iterable[tuple[str, str, bytes]],
) -> tuple[str, int]:
    """Digest logical path, entry kind and bytes without relying on mtimes."""

    digest = hashlib.sha256()
    count = 0
    for logical_path, kind, content in entries:
        path_bytes = logical_path.encode("utf-8")
        kind_bytes = kind.encode("ascii")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(kind_bytes).to_bytes(8, "big"))
        digest.update(kind_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        count += 1
    return f"sha256:{digest.hexdigest()}", count


def _path_entry(path: Path) -> tuple[str, bytes]:
    if path.is_symlink():
        return "symlink", os.readlink(path).encode("utf-8")
    if path.is_file():
        return "file", path.read_bytes()
    if not path.exists():
        return "missing", b""
    raise ValueError(f"deployment input is not a file or symlink: {path}")


def _normalized_input_roots(values: Sequence[str]) -> list[str]:
    roots = sorted({str(value).strip() for value in values if str(value).strip()})
    if not roots:
        raise ValueError("deployment input closure is empty")
    for value in roots:
        path = Path(value)
        if not path.is_absolute() and (
            not path.parts or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("deployment input closure path is unsafe")
    return roots


def _enumerated_deployment_inputs(
    roots: Sequence[str],
) -> tuple[list[str], list[tuple[str, Path, str]]]:
    normalized_roots = _normalized_input_roots(roots)
    repo_roots = [
        value for value in normalized_roots if not Path(value).is_absolute()
    ]
    external_roots = [
        Path(value) for value in normalized_roots if Path(value).is_absolute()
    ]
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            *repo_roots,
        ],
        cwd=_pkg.ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "cannot enumerate managed deployment inputs"
            + (f": {detail}" if detail else "")
        )
    entries: list[tuple[str, Path, str]] = []
    for encoded in sorted(value for value in result.stdout.split(b"\0") if value):
        relative = os.fsdecode(encoded)
        path = _pkg.ROOT / relative
        # ``git ls-files --cached`` also reports tracked files deleted from the
        # live worktree.  A package capsule represents the bytes that actually
        # exist at capture time; keeping a deleted index entry here makes an
        # unrelated deletion fail before the real compiler can decide whether
        # that path is required.  The deletion is still reflected by the tree
        # digest (the bytes are absent) and by workspaceStatusDigest.
        if not path.exists() and not path.is_symlink():
            continue
        entries.append((relative, path, f"repo/{relative}"))
    for index, path in enumerate(external_roots):
        if path.exists() or path.is_symlink():
            entries.append(
                (
                    f"external:{path}",
                    path,
                    f"external/{index:04d}-{hashlib.sha256(str(path).encode()).hexdigest()}",
                )
            )
    if not entries:
        raise ValueError("managed deployment input set is empty")
    return normalized_roots, entries


def _safe_capsule_source(path: Path, *, logical_path: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"deployment input is unavailable: {logical_path}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        resolved = path.resolve(strict=True)
        if logical_path.startswith("external:"):
            raise ValueError(
                f"external deployment input symlink is forbidden: {logical_path}"
            )
        if not resolved.is_relative_to(_pkg.ROOT.resolve()):
            raise ValueError(f"deployment input symlink escapes repository: {logical_path}")
        return metadata
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(
            f"deployment input is not a regular file or safe symlink: {logical_path}"
        )
    if not logical_path.startswith("external:"):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(_pkg.ROOT.resolve()):
            raise ValueError(f"deployment input escapes repository: {logical_path}")
    return metadata


def _copy_regular_capsule_input(
    source: Path,
    destination: Path,
    *,
    logical_path: str,
) -> tuple[bytes, int]:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise RuntimeError("package input capsule requires O_NOFOLLOW")
    descriptor = os.open(
        source,
        os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"deployment input is not regular: {logical_path}")
        content = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise ValueError(f"deployment input changed during capsule copy: {logical_path}")
    finally:
        os.close(descriptor)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
    output = os.open(destination, flags, 0o700)
    try:
        view = memoryview(content)
        while view:
            written = os.write(output, view)
            if written <= 0:
                raise OSError("package capsule write made no progress")
            view = view[written:]
        os.fsync(output)
        copied = os.fstat(output)
    finally:
        os.close(output)
    if (before.st_dev, before.st_ino) == (copied.st_dev, copied.st_ino):
        raise ValueError(f"package capsule hardlink is forbidden: {logical_path}")
    mode = 0o555 if before.st_mode & 0o111 else 0o444
    os.chmod(destination, mode, follow_symlinks=False)
    return bytes(content), mode


def _capsule_identity_payload(
    *,
    roots: Sequence[str],
    input_digest: str,
    input_count: int,
) -> dict[str, object]:
    return {
        "deploymentInputRoots": list(roots),
        "deploymentInputDigest": input_digest,
        "deploymentInputFileCount": input_count,
    }


def _baseline_id(identity: dict[str, object]) -> str:
    encoded = json.dumps(
        identity,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def materialize_package_input_capsule(
    roots: Sequence[str],
    *,
    capsule_root: Path,
) -> dict[str, object]:
    """Copy one source closure into a read-only, content-addressed capsule."""

    normalized_roots, source_entries = _enumerated_deployment_inputs(roots)
    capsule_root = capsule_root.expanduser()
    if not capsule_root.is_absolute() or capsule_root.exists() or capsule_root.is_symlink():
        raise ValueError("package input capsule root must be a new absolute path")
    capsule_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{capsule_root.name}.", dir=str(capsule_root.parent))
    )
    published = False
    try:
        records: list[dict[str, object]] = []
        digest_entries: list[tuple[str, str, bytes]] = []
        for logical_path, source, relative in source_entries:
            metadata = _safe_capsule_source(source, logical_path=logical_path)
            destination = staging / relative
            if stat.S_ISLNK(metadata.st_mode):
                target = os.readlink(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(target)
                content = target.encode("utf-8")
                kind = "symlink"
                mode = 0
            else:
                content, mode = _copy_regular_capsule_input(
                    source,
                    destination,
                    logical_path=logical_path,
                )
                kind = "file"
            digest_entries.append((logical_path, kind, content))
            records.append(
                {
                    "logicalPath": logical_path,
                    "capsulePath": relative,
                    "kind": kind,
                    "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                    "mode": mode,
                }
            )
        input_digest, input_count = _digest_record(digest_entries)
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_pkg.ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        source_revision = revision.stdout.strip()
        if revision.returncode != 0 or len(source_revision) != 40:
            raise ValueError("cannot resolve workspace source revision")
        repo_roots = [
            value for value in normalized_roots if not Path(value).is_absolute()
        ]
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v2",
                "-z",
                "--untracked-files=all",
                "--",
                *repo_roots,
            ],
            cwd=_pkg.ROOT,
            capture_output=True,
            check=False,
        )
        if status.returncode != 0:
            raise ValueError("cannot resolve workspace index/worktree state")
        identity = _capsule_identity_payload(
            roots=normalized_roots,
            input_digest=input_digest,
            input_count=input_count,
        )
        baseline_id = _baseline_id(identity)
        manifest = {
            "schema": PACKAGE_INPUT_CAPSULE_SCHEMA,
            "baselineId": baseline_id,
            "sourceRevision": source_revision,
            "workspaceStatusDigest": "sha256:"
            + hashlib.sha256(status.stdout).hexdigest(),
            **identity,
            "entries": records,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        head = staging / "repo/.git/HEAD"
        head.parent.mkdir(parents=True, exist_ok=True)
        head.write_text(source_revision + "\n", encoding="ascii")
        os.chmod(head, 0o444)
        for directory in sorted(
            (path for path in staging.rglob("*") if path.is_dir() and not path.is_symlink()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o555)
        os.chmod(staging / "manifest.json", 0o444)
        os.chmod(staging, 0o555)
        staging.replace(capsule_root)
        published = True
        return {**manifest, "capsuleRoot": str(capsule_root)}
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _read_capsule_manifest(capsule_root: Path) -> dict[str, object]:
    if capsule_root.is_symlink() or not capsule_root.is_dir():
        raise ValueError("package input capsule root is missing or unsafe")
    path = capsule_root / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("package input capsule manifest is missing or unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != _CAPSULE_FIELDS:
        raise ValueError("package input capsule manifest fields mismatch")
    if value.get("schema") != PACKAGE_INPUT_CAPSULE_SCHEMA:
        raise ValueError("package input capsule schema mismatch")
    return value


def verify_package_input_capsule(
    capsule_root: Path,
    *,
    expected_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    """Verify capsule bytes only; never re-read the mutable workspace."""

    manifest = _read_capsule_manifest(capsule_root)
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("package input capsule entry set is empty")
    entries: list[tuple[str, str, bytes]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or set(raw) != _CAPSULE_ENTRY_FIELDS:
            raise ValueError("package input capsule entry fields mismatch")
        relative = Path(str(raw.get("capsulePath") or ""))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("package input capsule path is unsafe")
        path = capsule_root / relative
        kind = str(raw.get("kind") or "")
        metadata = path.lstat()
        if kind == "file":
            if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
                raise ValueError("package input capsule file kind drifted")
            content = path.read_bytes()
            mode = 0o555 if metadata.st_mode & 0o111 else 0o444
            if metadata.st_mode & 0o222 or int(raw.get("mode") or -1) != mode:
                raise ValueError("package input capsule file is writable or mode drifted")
        elif kind == "symlink":
            if not stat.S_ISLNK(metadata.st_mode):
                raise ValueError("package input capsule symlink kind drifted")
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(capsule_root.resolve()):
                raise ValueError("package input capsule symlink escapes capsule")
            content = os.readlink(path).encode("utf-8")
        else:
            raise ValueError("package input capsule entry kind is invalid")
        if (
            int(raw.get("size") or -1) != len(content)
            or raw.get("digest") != "sha256:" + hashlib.sha256(content).hexdigest()
        ):
            raise ValueError("package input capsule entry CAS mismatch")
        entries.append((str(raw.get("logicalPath") or ""), kind, content))
    digest, count = _digest_record(entries)
    identity = _capsule_identity_payload(
        roots=_normalized_input_roots(
            list(manifest.get("deploymentInputRoots") or [])
        ),
        input_digest=digest,
        input_count=count,
    )
    if (
        digest != manifest.get("deploymentInputDigest")
        or count != manifest.get("deploymentInputFileCount")
        or _baseline_id(identity) != manifest.get("baselineId")
    ):
        raise ValueError("package input capsule identity CAS mismatch")
    if expected_snapshot is not None:
        for field in (
            "baselineId",
            "sourceRevision",
            "workspaceStatusDigest",
            "deploymentInputRoots",
            "deploymentInputDigest",
            "deploymentInputFileCount",
        ):
            if expected_snapshot.get(field) != manifest.get(field):
                raise ValueError(f"package input capsule {field} mismatch")
    return manifest

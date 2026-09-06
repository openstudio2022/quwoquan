"""Immutable local-readiness source identity and capsule materialization."""
from __future__ import annotations

import contextlib
import os
import posixpath
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterator

from . import core as _core


def _parse_name_status_z(output: bytes, repo_root: Path) -> list[dict[str, str | None]]:
    records = output.split(b"\0")
    entries: list[dict[str, str | None]] = []
    index = 0
    while index < len(records) and records[index]:
        status = records[index].decode("utf-8")
        index += 1
        if index >= len(records) or not records[index]:
            raise _core.LocalReadinessError(f"git name-status 缺 path: {status}")
        source = _core.normalize_repo_relative_path(records[index].decode("utf-8"), repo_root)
        index += 1
        destination: str | None = None
        if status[:1] in {"R", "C"}:
            if index >= len(records) or not records[index]:
                raise _core.LocalReadinessError(f"git rename/copy 缺 destination: {source}")
            destination = _core.normalize_repo_relative_path(records[index].decode("utf-8"), repo_root)
            index += 1
        entries.append({"status": status, "source": source, "destination": destination})
    return entries


def _staged_changes(repo_root: Path) -> list[dict[str, str | None]]:
    return _core._parse_name_status_z(
        _core._git_bytes(repo_root, "diff", "--cached", "--name-status", "-z", "--find-renames", "--diff-filter=ACDMRTUXB"),
        repo_root,
    )


def workspace_paths(repo_root: Path) -> list[str]:
    output = _core._git_bytes(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = output.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(records) and records[index]:
        decoded = records[index].decode("utf-8")
        code = decoded[:2]
        current = _core.normalize_repo_relative_path(decoded[3:], repo_root)
        paths.add(current)
        if "R" in code or "C" in code:
            index += 1
            if index >= len(records) or not records[index]:
                raise _core.LocalReadinessError(f"git status rename 缺 source: {current}")
            paths.add(_core.normalize_repo_relative_path(records[index].decode("utf-8"), repo_root))
        index += 1
    return sorted(paths)


def staged_paths(repo_root: Path) -> list[str]:
    paths: set[str] = set()
    for entry in _core._staged_changes(repo_root):
        paths.add(str(entry["source"]))
        if entry["destination"]:
            paths.add(str(entry["destination"]))
    return sorted(paths)


def _index_entries(repo_root: Path, paths: list[str]) -> dict[str, dict[str, str]]:
    if not paths:
        return {}
    output = _core._git_bytes(repo_root, "ls-files", "--stage", "-z", "--", *paths)
    entries: dict[str, dict[str, str]] = {}
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, separator, raw_path = raw.partition(b"\t")
        fields = metadata.decode("utf-8").split()
        if not separator or len(fields) != 3:
            raise _core.LocalReadinessError("git index entry 格式非法")
        mode, blob, stage = fields
        if stage != "0":
            raise _core.LocalReadinessError(f"unmerged index stage 禁止生成 readiness: {raw_path!r}")
        relative = _core.normalize_repo_relative_path(raw_path.decode("utf-8"), repo_root)
        entries[relative] = {"mode": mode, "blob": blob}
    return entries


def _staged_identity(repo_root: Path, paths: list[str]) -> dict[str, str]:
    selected = set(paths)
    changes = _core._staged_changes(repo_root)
    index_entries = _core._index_entries(repo_root, paths)
    records: list[dict[str, Any]] = []
    for change in changes:
        source = str(change["source"])
        destination = str(change["destination"]) if change["destination"] else None
        if source not in selected and (destination is None or destination not in selected):
            continue
        index_path = destination or source
        index = index_entries.get(index_path)
        records.append({**change, "index_path": index_path, "index_mode": index.get("mode") if index else None, "index_blob": index.get("blob") if index else None})
    covered = {str(record["source"]) for record in records} | {str(record["destination"]) for record in records if record["destination"]}
    for relative in sorted(selected - covered):
        index = index_entries.get(relative)
        records.append({"status": "INDEX", "source": relative, "destination": None, "index_path": relative, "index_mode": index.get("mode") if index else None, "index_blob": index.get("blob") if index else None})
    deleted = [record for record in records if str(record["status"]).startswith("D")]
    renamed = [record for record in records if str(record["status"]).startswith(("R", "C"))]
    symlink = [record for record in records if record.get("index_mode") == "120000"]
    tracked = [record for record in records if record not in deleted and record not in renamed and record not in symlink]
    return {
        "tracked_digest": _core.canonical_digest(tracked),
        "deleted_digest": _core.canonical_digest(deleted),
        "renamed_digest": _core.canonical_digest(renamed),
        "symlink_digest": _core.canonical_digest(symlink),
    }


def _source_path(raw_path: str, repo_root: Path) -> str:
    if any(character in raw_path for character in ("\x00", "\n", "\r")):
        raise _core.LocalReadinessError("source tree path 含控制字符")
    normalized = _core.normalize_repo_relative_path(raw_path, repo_root)
    if normalized in {"", "."}:
        raise _core.LocalReadinessError("source tree path 非法")
    return normalized


def _index_source_entries(repo_root: Path) -> list[dict[str, str]]:
    output = _core._git_bytes(repo_root, "ls-files", "--stage", "-z")
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, separator, raw_path = raw.partition(b"\t")
        fields = metadata.decode("ascii").split()
        if not separator or len(fields) != 3:
            raise _core.LocalReadinessError("git index source entry 格式非法")
        mode, blob, stage = fields
        if stage != "0":
            raise _core.LocalReadinessError(f"unmerged index stage 禁止物化 readiness capsule: {raw_path!r}")
        relative = _core._source_path(raw_path.decode("utf-8"), repo_root)
        if relative in seen:
            raise _core.LocalReadinessError(f"git index source path 重复: {relative}")
        if mode not in {"100644", "100755", "120000"} or not re.fullmatch(r"[0-9a-f]{40,64}", blob):
            raise _core.LocalReadinessError(f"readiness capsule 不支持 index entry: mode={mode} path={relative}")
        seen.add(relative)
        entries.append({"path": relative, "mode": mode, "blob": blob})
    return sorted(entries, key=lambda item: item["path"].encode("utf-8"))


def _tree_source_entries(repo_root: Path, commit_sha: str) -> list[dict[str, str]]:
    output = _core._git_bytes(repo_root, "ls-tree", "-r", "-z", commit_sha)
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, separator, raw_path = raw.partition(b"\t")
        fields = metadata.decode("ascii").split()
        if not separator or len(fields) != 3:
            raise _core.LocalReadinessError("git commit tree entry 格式非法")
        mode, object_type, blob = fields
        relative = _core._source_path(raw_path.decode("utf-8"), repo_root)
        if relative in seen:
            raise _core.LocalReadinessError(f"git commit tree path 重复: {relative}")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"} or not re.fullmatch(r"[0-9a-f]{40,64}", blob):
            raise _core.LocalReadinessError(f"readiness capsule 不支持 commit tree entry: mode={mode} type={object_type} path={relative}")
        seen.add(relative)
        entries.append({"path": relative, "mode": mode, "blob": blob})
    return sorted(entries, key=lambda item: item["path"].encode("utf-8"))


def _immutable_workspace(entries: list[dict[str, str]], changes: list[dict[str, str | None]]) -> dict[str, str]:
    regular = [entry for entry in entries if entry["mode"] != "120000"]
    symlinks = [entry for entry in entries if entry["mode"] == "120000"]
    deleted = [change for change in changes if str(change["status"]).startswith("D")]
    renamed = [change for change in changes if str(change["status"]).startswith(("R", "C"))]
    return {
        "tracked_digest": _core.canonical_digest(regular),
        "untracked_digest": _core.canonical_digest([]),
        "deleted_digest": _core.canonical_digest(deleted),
        "renamed_digest": _core.canonical_digest(renamed),
        "symlink_digest": _core.canonical_digest(symlinks),
    }


def _worktree_workspace(
    repo_root: Path,
    paths: list[str],
    *,
    state_root: Path | None = None,
) -> dict[str, str]:
    """Fingerprint only mutable bytes selected by the current focused plan."""

    excluded: list[str] = [".qwq_output"]
    if state_root is not None:
        canonical_state = _core._canonical_absolute(state_root)
        try:
            relative_state = canonical_state.relative_to(
                _core._canonical_absolute(repo_root)
            )
        except ValueError:
            relative_state = None
        if relative_state is not None and relative_state.parts:
            excluded.append(relative_state.as_posix())

    normalized = {
        _core.normalize_repo_relative_path(path, repo_root) for path in paths
    }
    focused_paths = sorted(
        (
            relative
            for relative in normalized
            if not any(
                relative == prefix or relative.startswith(prefix + "/")
                for prefix in excluded
            )
        ),
        key=lambda item: item.encode("utf-8"),
    )
    return _core.workspace_digests(focused_paths, repo_root=repo_root)


def parse_push_updates(text: str) -> list[dict[str, str]]:
    updates: list[dict[str, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 4:
            raise _core.LocalReadinessError("push update 必须包含 local_ref local_sha remote_ref remote_sha")
        local_ref, local_sha, remote_ref, remote_sha = fields
        if not (_core._SHA_RE.fullmatch(local_sha) and _core._SHA_RE.fullmatch(remote_sha)):
            raise _core.LocalReadinessError("push update SHA 必须为 40 位小写十六进制")
        updates.append({"local_ref": local_ref, "local_sha": local_sha, "remote_ref": remote_ref, "remote_sha": remote_sha})
    return sorted(updates, key=lambda item: (item["remote_ref"], item["local_ref"]))


def _validated_push_identity(repo_root: Path, updates: list[dict[str, str]]) -> tuple[str, str]:
    active = [update for update in updates if update["local_sha"] != _core._ZERO_SHA]
    if not active:
        raise _core.LocalReadinessError("push updates 不含可验证 local commit")
    heads: set[str] = set()
    bases: set[str] = set()
    for update in active:
        local_sha = update["local_sha"]
        proc = subprocess.run(["git", "cat-file", "-e", f"{local_sha}^{{commit}}"], cwd=repo_root, capture_output=True, check=False)
        if proc.returncode != 0:
            raise _core.LocalReadinessError(f"push local sha 不存在或非 commit: {local_sha}")
        resolved = _core._git_text(repo_root, "rev-parse", update["local_ref"]).strip()
        if resolved != local_sha:
            raise _core.LocalReadinessError(f"push local ref/sha mismatch: {update['local_ref']}")
        remote_sha = update["remote_sha"]
        if remote_sha == _core._ZERO_SHA:
            base = _core._merge_base(repo_root, local_sha)
        else:
            proc = subprocess.run(["git", "cat-file", "-e", f"{remote_sha}^{{commit}}"], cwd=repo_root, capture_output=True, check=False)
            if proc.returncode != 0:
                raise _core.LocalReadinessError(f"push remote base 不存在或非 commit: {remote_sha}")
            base = _core._git_text(repo_root, "merge-base", remote_sha, local_sha).strip()
            if base != remote_sha:
                raise _core.LocalReadinessError(f"push local sha 非 remote base 的 fast-forward 后继: {update['remote_ref']}")
        heads.add(local_sha)
        bases.add(base)
    if len(heads) != 1 or len(bases) != 1:
        raise _core.LocalReadinessError("一次 readiness receipt 只接受同一 local sha/base 的 push updates")
    return next(iter(heads)), next(iter(bases))


def push_paths(repo_root: Path, updates: list[dict[str, str]]) -> list[str]:
    head, base = _core._validated_push_identity(repo_root, updates)
    output = _core._git_bytes(repo_root, "diff", "--name-status", "-z", "--find-renames", base, head)
    paths: set[str] = set()
    for entry in _core._parse_name_status_z(output, repo_root):
        paths.add(str(entry["source"]))
        if entry["destination"]:
            paths.add(str(entry["destination"]))
    return sorted(paths)


def _commit_workspace(repo_root: Path, *, head: str, base: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    changes = _core._parse_name_status_z(
        _core._git_bytes(repo_root, "diff", "--name-status", "-z", "--find-renames", base, head),
        repo_root,
    )
    entries = _core._tree_source_entries(repo_root, head)
    return _core._immutable_workspace(entries, changes), entries


def _push_workspace(repo_root: Path, paths: list[str], updates: list[dict[str, str]]) -> tuple[dict[str, str], str, str]:
    del paths  # The receipt owns the complete immutable commit tree, not selected path bytes only.
    head, base = _core._validated_push_identity(repo_root, updates)
    workspace, _entries = _core._commit_workspace(repo_root, head=head, base=base)
    return workspace, head, base


def _capsule_symlink_target(entry_path: str, target: str) -> str:
    if not target or "\x00" in target or "\n" in target or "\r" in target:
        raise _core.LocalReadinessError(f"capsule symlink target 非法: {entry_path}")
    normalized_target = target.replace("\\", "/")
    if normalized_target.startswith("/") or re.match(r"^[A-Za-z]:/", normalized_target):
        raise _core.LocalReadinessError(f"capsule symlink target 越出仓库: {entry_path} -> {target}")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(entry_path), normalized_target))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        raise _core.LocalReadinessError(f"capsule symlink target 越出仓库: {entry_path} -> {target}")
    return target


def _safe_capsule_destination(capsule_root: Path, relative: str) -> Path:
    normalized = _core._source_path(relative, capsule_root)
    current = capsule_root
    for part in Path(normalized).parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            metadata = current.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise _core.LocalReadinessError(f"capsule parent 非安全 directory: {relative}")
    destination = capsule_root / normalized
    if destination.exists() or destination.is_symlink():
        raise _core.LocalReadinessError(f"capsule destination 重复或已存在: {relative}")
    return destination


def _materialize_capsule_entry(repo_root: Path, capsule_root: Path, entry: dict[str, str]) -> None:
    relative, mode, blob = entry["path"], entry["mode"], entry["blob"]
    if relative == ".qwq_output" or relative.startswith(".qwq_output/"):
        raise _core.LocalReadinessError("capsule source tree 不得占用受管 QWQ_OUTPUT_ROOT")
    destination = _core._safe_capsule_destination(capsule_root, relative)
    content = _core._git_bytes(repo_root, "cat-file", "blob", blob)
    if mode == "120000":
        try:
            target = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _core.LocalReadinessError(f"capsule symlink target 非 UTF-8: {relative}") from exc
        os.symlink(_core._capsule_symlink_target(relative, target), destination)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(destination, flags, 0o700 if mode == "100755" else 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


def _capsule_entries(repo_root: Path, *, mode: str, push_updates: list[dict[str, str]] | None) -> tuple[list[dict[str, str]], str]:
    if mode == "staged":
        return _core._index_source_entries(repo_root), _core._head_sha(repo_root)
    if mode == "commit":
        head = _core._head_sha(repo_root)
        return _core._tree_source_entries(repo_root, head), head
    if mode == "push":
        head, _base = _core._validated_push_identity(repo_root, push_updates or [])
        return _core._tree_source_entries(repo_root, head), head
    raise _core.LocalReadinessError(f"mode={mode} 不使用 immutable capsule")


@contextlib.contextmanager
def source_execution_root(
    *,
    repo_root: Path,
    mode: str,
    state_root: Path,
    fingerprint: dict[str, Any],
    push_updates: list[dict[str, str]] | None = None,
) -> Iterator[tuple[Path, dict[str, str], list[dict[str, str]]]]:
    if mode == "workspace":
        yield repo_root, {}, []
        return
    entries, source_sha = _core._capsule_entries(repo_root, mode=mode, push_updates=push_updates)
    process_root = _core._ensure_secure_directory(
        state_root / "process/materializations",
        label="local readiness materialization root",
    )
    container = Path(tempfile.mkdtemp(prefix=f"{fingerprint['digest'].removeprefix('sha256:')[:16]}-", dir=process_root))
    capsule = container / "worktree"
    git_dir = container / "git"
    try:
        os.chmod(container, 0o700)
        capsule.mkdir(mode=0o700)
        for entry in entries:
            _core._materialize_capsule_entry(repo_root, capsule, entry)

        initialized = subprocess.run(
            ["git", "init", "--bare", str(git_dir)],
            cwd=container,
            capture_output=True,
            check=False,
        )
        if initialized.returncode != 0:
            raise _core.LocalReadinessError(initialized.stderr.decode("utf-8", errors="replace").strip() or "capsule isolated Git 初始化失败")
        os.chmod(git_dir, 0o700)
        raw_objects = _core._git_text(repo_root, "rev-parse", "--git-path", "objects").strip()
        source_objects = Path(raw_objects)
        if not source_objects.is_absolute():
            source_objects = repo_root / source_objects
        try:
            source_objects = source_objects.resolve(strict=True)
        except OSError as exc:
            raise _core.LocalReadinessError(f"capsule source object database 不存在: {exc}") from exc
        if not source_objects.is_dir():
            raise _core.LocalReadinessError("capsule source object database 必须为 directory")
        alternates = git_dir / "objects/info/alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(alternates, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                handle.write(str(source_objects) + "\n")
        finally:
            if fd >= 0:
                os.close(fd)

        # capsule 通过 gitfile（capsule/.git → git_dir）按 cwd 发现仓库，而不是把 GIT_DIR/GIT_WORK_TREE
        # 导出给检查进程：那两个变量会把测试自建的临时仓库、Flutter SDK 自身的 `git describe` 等
        # 一切 git 调用都劫持到 capsule（"a branch named 'dev1.0' already exists"、Flutter 版本 0.0.0-unknown）。
        setup_env = {"GIT_DIR": str(git_dir), "GIT_WORK_TREE": str(capsule), "GIT_OPTIONAL_LOCKS": "0"}
        execution_env = {
            "GIT_OPTIONAL_LOCKS": "0",
            "QWQ_OUTPUT_ROOT": str(capsule / ".qwq_output"),
            "QWQ_LOCAL_READINESS_SOURCE_MODE": mode,
            "QWQ_LOCAL_READINESS_SOURCE_SHA": source_sha,
            # 只供检查借用源工作树的安装产物（如 portal node_modules），不是源码读取入口。
            "QWQ_LOCAL_READINESS_REPO_ROOT": str(repo_root),
        }
        for command in (
            ["git", "config", "core.bare", "false"],
            ["git", "config", "core.worktree", str(capsule)],
            ["git", "symbolic-ref", "HEAD", "refs/heads/dev1.0"],
            ["git", "update-ref", "refs/heads/dev1.0", source_sha],
            ["git", "read-tree", "--empty"],
        ):
            proc = subprocess.run(command, cwd=capsule, env={**os.environ, **setup_env}, capture_output=True, check=False)
            if proc.returncode != 0:
                raise _core.LocalReadinessError(proc.stderr.decode("utf-8", errors="replace").strip() or f"capsule Git identity 初始化失败: {' '.join(command)}")
        gitfile_fd = os.open(capsule / ".git", os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(gitfile_fd, "w", encoding="utf-8") as handle:
            handle.write(f"gitdir: {git_dir}\n")
        index_info = b"".join(
            f"{entry['mode']} {entry['blob']}\t{entry['path']}".encode("utf-8") + b"\0"
            for entry in entries
        )
        indexed = subprocess.run(
            ["git", "update-index", "-z", "--index-info"],
            cwd=capsule,
            env={**os.environ, **setup_env},
            input=index_info,
            capture_output=True,
            check=False,
        )
        if indexed.returncode != 0:
            raise _core.LocalReadinessError(indexed.stderr.decode("utf-8", errors="replace").strip() or "capsule isolated index 写入失败")
        yield capsule, execution_env, entries
    finally:
        _core._reject_symlink_components(container.parent, label="local readiness materialization cleanup")
        try:
            metadata = container.lstat()
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise _core.LocalReadinessError("local readiness materialization cleanup 拒绝非安全目录")
            shutil.rmtree(container)

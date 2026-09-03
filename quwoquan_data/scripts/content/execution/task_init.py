"""从两份 AI 已准备输入确定性创建最小 execution 工作包。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import shutil
import stat
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from content.execution.identity import parse_execution_id, validate_execution_id
from core import paths
from core.schema import assert_valid

REQUEST_REF = "0.plan/request.json"
TARGET_SET_REF = "0.plan/target_set.json"


class TaskInitError(ValueError):
    """初始化输入或目标工作包不合法。"""


class TaskInitConflict(TaskInitError):
    """create-once 目标已存在且字节不同。"""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _absolute(path: Path) -> Path:
    expanded = path.expanduser()
    return Path(os.path.abspath(expanded))


def _relative_ref(path: Path, *, root: Path, label: str) -> str:
    absolute = _absolute(path)
    absolute_root = _absolute(root)
    try:
        value = absolute.relative_to(absolute_root).as_posix()
    except ValueError as exc:
        raise TaskInitError(f"{label} 必须位于 {absolute_root} 内：{absolute}") from exc
    parsed = PurePosixPath(value)
    if not value or parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise TaskInitError(f"{label} 不是安全相对引用：{value!r}")
    return value


def _open_root(path: Path, *, label: str, create: bool = False) -> int:
    absolute = _absolute(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    parts = absolute.parts
    descriptor = os.open(parts[0], flags | nofollow)
    try:
        for part in parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            try:
                next_descriptor = os.open(part, flags | nofollow, dir_fd=descriptor)
            except OSError as exc:
                raise TaskInitError(f"{label} 必须是无 symlink 的目录：{absolute}") from exc
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_child_directory(parent_fd: int, name: str, *, label: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise TaskInitError(f"{label} 必须是无 symlink 的目录：{name}") from exc


def _mkdirs_at(root_fd: int, ref: str) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in PurePosixPath(ref).parts:
            try:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                os.fsync(descriptor)
            except FileExistsError:
                pass
            next_descriptor = _open_child_directory(descriptor, part, label="初始化写入目录")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_relative_directory(root_fd: int, ref: str, *, label: str) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in PurePosixPath(ref).parts:
            next_descriptor = _open_child_directory(descriptor, part, label=label)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_at(root_fd: int, ref: str, *, label: str) -> bytes:
    parts = PurePosixPath(ref).parts
    descriptor = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_descriptor = _open_child_directory(descriptor, part, label=f"{label} 父目录")
            os.close(descriptor)
            descriptor = next_descriptor
        try:
            file_fd = os.open(
                parts[-1],
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
        except OSError as exc:
            raise TaskInitError(f"{label} 不可读取：{ref}") from exc
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise TaskInitError(f"{label} 必须是 regular file：{ref}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(file_fd)
    finally:
        os.close(descriptor)


def _load_bound_document(
    path: Path,
    *,
    root: Path,
    root_fd: int,
    schema_name: str,
) -> tuple[dict[str, Any], str, bytes]:
    ref = _relative_ref(path, root=root, label=f"{schema_name} 输入")
    raw = _read_regular_at(root_fd, ref, label=schema_name)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskInitError(f"{schema_name} 必须是合法 JSON") from exc
    if not isinstance(value, dict):
        raise TaskInitError(f"{schema_name} 必须是 JSON 对象")
    assert_valid(value, "execution", schema_name, label=f"task init {schema_name}")
    canonical = _canonical_bytes(value)
    return value, ref, canonical


def _target_ref(target: Mapping[str, Any], *, carrier: str) -> str:
    name = str(target.get("name") or "").strip()
    entity_type = str(target.get("entityType") or "").strip().strip("/")
    if not name or len(entity_type.split("/")) != 2:
        raise TaskInitError(f"候选 target 非法：{entity_type}/{name}")
    if carrier == "homepage":
        return f"entities/{entity_type}/{name}"
    angle = str(target.get("publishAngle") or "").strip()
    title = str(target.get("publishTitle") or "").strip()
    sequence = target.get("publishSeq", 1)
    if not angle or not title or isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise TaskInitError(f"候选缺少合法的发布坐标：{name}")
    return f"posts/{carrier}/{angle}/{title}/{sequence}"


def _normalized_targets(value: object, *, carrier: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list) or not value:
        raise TaskInitError("immutable candidate bindings 必须包含 targets")
    pairs: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise TaskInitError("每个 candidate target 必须是对象")
        target = dict(raw)
        target["name"] = str(target.get("name") or "").strip()
        target["entityType"] = str(target.get("entityType") or "").strip().strip("/")
        if carrier != "homepage":
            target["publishAngle"] = str(target.get("publishAngle") or "").strip()
            target["publishTitle"] = str(target.get("publishTitle") or "").strip()
            target["publishSeq"] = target.get("publishSeq", 1)
        ref = _target_ref(target, carrier=carrier)
        if ref in seen:
            raise TaskInitError(f"targetRef 重复：{ref}")
        seen.add(ref)
        pairs.append((ref, target))
    pairs.sort(key=lambda pair: pair[0])
    return [target for _, target in pairs], [ref for ref, _ in pairs]


def _validate_retry(execution_id: str, retry_of: object) -> str | None:
    if retry_of is None:
        return None
    previous_id = validate_execution_id(str(retry_of))
    current = parse_execution_id(execution_id)
    previous = parse_execution_id(previous_id)
    if (
        previous_id == execution_id
        or previous.run_date != current.run_date
        or previous.vertical != current.vertical
        or previous.content_type != current.content_type
        or previous.intent != current.intent
        or previous.scope != current.scope
        or previous.phase != current.phase
        or previous.sequence >= current.sequence
    ):
        raise TaskInitError("retryOf 必须是同一 execution scope 的更早 sequence")
    return previous_id


@contextmanager
def _init_lock(execution_id: str) -> Iterator[None]:
    output_fd = _open_root(paths.OUTPUT_ROOT, label="output 根", create=True)
    try:
        lock_ref = _relative_ref(
            paths.DATA_LOCAL_ROOT / "runs/locks/task-init",
            root=paths.OUTPUT_ROOT,
            label="task-init lock 根",
        )
        lock_fd = _mkdirs_at(output_fd, lock_ref)
        try:
            handle_fd = os.open(
                f"{execution_id}.lock",
                os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=lock_fd,
            )
            with os.fdopen(handle_fd, "a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
    finally:
        os.close(output_fd)


def _write_file_at(root_fd: int, ref: str, data: bytes) -> None:
    path = PurePosixPath(ref)
    directory_ref = path.parent.as_posix()
    directory_fd = os.dup(root_fd) if directory_ref == "." else _mkdirs_at(root_fd, directory_ref)
    try:
        file_fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            view = memoryview(data)
            while view:
                written = os.write(file_fd, view)
                view = view[written:]
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _documents_match(root_fd: int, documents: Mapping[str, Mapping[str, Any]]) -> bool:
    try:
        return all(_read_regular_at(root_fd, ref, label="existing task init") == _canonical_bytes(value) for ref, value in documents.items())
    except TaskInitError:
        return False


def initialize_task(*, carrier_demand_path: Path, candidate_bindings_path: Path) -> dict[str, Any]:
    output_fd = _open_root(paths.OUTPUT_ROOT, label="output 根")
    try:
        demand, demand_ref, demand_canonical = _load_bound_document(
            carrier_demand_path,
            root=paths.OUTPUT_ROOT,
            root_fd=output_fd,
            schema_name="carrier_demand",
        )
        bindings, bindings_ref, bindings_canonical = _load_bound_document(
            candidate_bindings_path,
            root=paths.OUTPUT_ROOT,
            root_fd=output_fd,
            schema_name="immutable_candidate_bindings",
        )
    finally:
        os.close(output_fd)

    execution_id = validate_execution_id(str(demand["executionId"]))
    carrier = parse_execution_id(execution_id).content_type.value
    if demand["carrier"] != carrier or bindings["carrier"] != carrier:
        raise TaskInitError("carrier 与 executionId 不一致")
    if bindings["executionId"] != execution_id:
        raise TaskInitError("两份初始化输入的 executionId 不一致")

    family_ref = str(demand["familyRef"]).strip().strip("/")
    family_parts = PurePosixPath(family_ref).parts
    if not family_ref or PurePosixPath(family_ref).is_absolute() or any(part in {"", ".", ".."} for part in family_parts):
        raise TaskInitError("familyRef 必须是安全相对引用")
    if f"/{carrier}/" not in f"/{family_ref}/":
        raise TaskInitError("familyRef 与 carrier 不一致")
    repo_fd = _open_root(paths.REPO_ROOT, label="repo 根")
    try:
        families_ref = _relative_ref(paths.FAMILIES_ROOT, root=paths.REPO_ROOT, label="families 根")
        families_fd = _open_relative_directory(repo_fd, families_ref, label="families 根")
        try:
            family_bytes = _read_regular_at(families_fd, f"{family_ref}.recipe.yaml", label="familyRef")
        finally:
            os.close(families_fd)
    finally:
        os.close(repo_fd)

    targets, target_refs = _normalized_targets(bindings["targets"], carrier=carrier)
    candidate_count = int(bindings["candidateCount"])
    quota = int(demand["quota"])
    if candidate_count != len(targets):
        raise TaskInitError("candidateCount 必须等于 targets 数量")
    if candidate_count < quota:
        raise TaskInitError("candidateCount 不得小于 quota")
    retry_of = _validate_retry(execution_id, demand.get("retryOf"))

    demand_binding = {"scope": "output", "ref": demand_ref, "digest": _sha256(demand_canonical)}
    candidate_binding = {"scope": "output", "ref": bindings_ref, "digest": _sha256(bindings_canonical)}
    submitted_inputs = {"carrierDemand": demand, "immutableCandidateBindings": bindings}
    request: dict[str, Any] = {
        "schema": "quwoquan_data.task_init_request",
        "executionId": execution_id,
        "carrier": carrier,
        "familyRef": family_ref,
        "quota": quota,
        "candidateCount": candidate_count,
        "carrierDemand": demand_binding,
        "immutableCandidateBindings": candidate_binding,
        "submittedInputs": submitted_inputs,
        "retryOf": retry_of,
    }
    target_set: dict[str, Any] = {
        "schema": "quwoquan_data.target_set",
        "executionId": execution_id,
        "carrier": carrier,
        "selectionPolicy": "frozen",
        "entityCatalogDigest": bindings["entityCatalogDigest"],
        "candidateBinding": {**candidate_binding, "candidateCount": candidate_count},
        "targetCount": candidate_count,
        "targetRefs": target_refs,
        "targets": targets,
    }
    manifest: dict[str, Any] = {
        "schema": "quwoquan_data.content_execution_manifest",
        "executionId": execution_id,
        "carrier": carrier,
        "familyRef": {"ref": family_ref, "digest": _sha256(family_bytes)},
        "initInputs": {"carrierDemand": demand_binding, "immutableCandidateBindings": candidate_binding},
        "submittedInputs": submitted_inputs,
        "request": {"ref": REQUEST_REF, "digest": _sha256(_canonical_bytes(request))},
        "targetSet": {"ref": TARGET_SET_REF, "digest": _sha256(_canonical_bytes(target_set))},
        "retryOf": retry_of,
    }
    assert_valid(request, "execution", "task_init_request", label=f"task init request:{execution_id}")
    assert_valid(target_set, "execution", "target_set", label=f"task init target set:{execution_id}")
    assert_valid(manifest, "execution", "content_execution_manifest", label=f"task init manifest:{execution_id}")

    documents = {"execution_manifest.json": manifest, REQUEST_REF: request, TARGET_SET_REF: target_set}
    target_root = paths.DATA_EXECUTIONS_ROOT / execution_id
    with _init_lock(execution_id):
        output_fd = _open_root(paths.OUTPUT_ROOT, label="output 根")
        tasks_ref = _relative_ref(paths.DATA_EXECUTIONS_ROOT, root=paths.OUTPUT_ROOT, label="execution 父根")
        tasks_fd = _mkdirs_at(output_fd, tasks_ref)
        os.close(output_fd)
        staging_name = f".{execution_id}.init-{secrets.token_hex(16)}"
        staging_fd: int | None = None
        try:
            try:
                target_fd = _open_child_directory(tasks_fd, execution_id, label="execution 根")
            except TaskInitError as exc:
                if not isinstance(exc.__cause__, FileNotFoundError):
                    raise TaskInitConflict("executionId 已存在但不是可信目录") from exc
            else:
                try:
                    if _documents_match(target_fd, documents):
                        return {"executionId": execution_id, "status": "replayed", "artifacts": list(documents)}
                    raise TaskInitConflict("executionId 已存在且内容不同")
                finally:
                    os.close(target_fd)
            os.mkdir(staging_name, mode=0o700, dir_fd=tasks_fd)
            os.fsync(tasks_fd)
            staging_fd = _open_child_directory(tasks_fd, staging_name, label="task-init staging")
            for ref, value in documents.items():
                _write_file_at(staging_fd, ref, _canonical_bytes(value))
            os.fsync(staging_fd)
            os.rename(staging_name, execution_id, src_dir_fd=tasks_fd, dst_dir_fd=tasks_fd)
            os.fsync(tasks_fd)
        except BaseException:
            if staging_fd is not None:
                os.close(staging_fd)
                staging_fd = None
            shutil.rmtree(paths.DATA_EXECUTIONS_ROOT / staging_name, ignore_errors=True)
            try:
                os.fsync(tasks_fd)
            except OSError:
                pass
            raise
        finally:
            if staging_fd is not None:
                os.close(staging_fd)
            os.close(tasks_fd)
    return {"executionId": execution_id, "status": "created", "artifacts": list(documents)}


__all__ = ["TaskInitConflict", "TaskInitError", "initialize_task"]

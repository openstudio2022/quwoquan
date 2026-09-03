"""最小 stage open/close execution 内核。

本模块只冻结调用方声明的引用及其实际字节摘要；不查找候选、不运行业务命令、
不派生 verdict/recovery/next，也不写任何状态投影。``verifierFacts`` 只是宿主对
已执行显式 verifier 的证明声明；内核不能证明命令确实执行过。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from content.execution.identity import validate_execution_id
from core import paths
from core.control_types import RECEIPT_STAGE_SEQUENCE
from core.schema import assert_valid

RECEIPT_STAGES: tuple[str, ...] = tuple(stage.value for stage in RECEIPT_STAGE_SEQUENCE)
_STAGE_INDEX = {stage: index for index, stage in enumerate(RECEIPT_STAGES)}
_OPEN_DIRECTORY = "_shared/stage-open"
_RECEIPT_DIRECTORY = "_shared/receipts"


class StageProtocolError(ValueError):
    """stage 请求违反协议。"""


class StageConflict(StageProtocolError):
    """create-once 文件已存在且输入不同。"""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _parse_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageProtocolError(f"{label} 不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise StageProtocolError(f"{label} 必须是 JSON 对象")
    return value


def _load_input(path: Path, *, schema_name: str | None = None) -> tuple[dict[str, Any], bytes]:
    raw = path.expanduser().read_bytes()
    value = _parse_json_object(raw, label="input")
    if schema_name:
        try:
            assert_valid(value, "execution", schema_name, label=f"stage {schema_name}")
        except ValueError as exc:
            raise StageProtocolError(str(exc)) from exc
    canonical = _canonical_bytes(value)
    return value, canonical


def _stage(stage: str) -> tuple[str, int]:
    normalized = str(stage or "").strip()
    if normalized not in _STAGE_INDEX:
        raise StageProtocolError(f"未知 stage：{normalized}")
    return normalized, _STAGE_INDEX[normalized] + 1


def _safe_ref(ref: object) -> str:
    value = str(ref or "")
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise StageProtocolError(f"ref 必须是安全相对路径：{value!r}")
    return value


def _open_root(path: Path, *, label: str) -> int:
    expanded = path.expanduser()
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    parts = expanded.parts
    descriptor = os.open(parts[0], flags | nofollow)
    try:
        for part in parts[1:]:
            next_descriptor = os.open(part, flags | nofollow, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except (OSError, ValueError) as exc:
        os.close(descriptor)
        raise StageProtocolError(f"{label} 必须是无 symlink 的目录：{expanded}") from exc


def _open_child_directory(parent_fd: int, name: str, *, label: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise StageProtocolError(f"{label} 必须是无 symlink 的目录：{name}") from exc


def _read_regular_at(root_fd: int, ref: str, *, label: str) -> bytes:
    parts = PurePosixPath(_safe_ref(ref)).parts
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
            raise StageProtocolError(f"{label} 不可读取：{ref}") from exc
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise StageProtocolError(f"{label} 必须是 regular file：{ref}")
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


def _mkdirs_at(root_fd: int, ref: str) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in PurePosixPath(_safe_ref(ref)).parts:
            try:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                os.fsync(descriptor)
            except FileExistsError:
                pass
            next_descriptor = _open_child_directory(descriptor, part, label="execution 写入目录")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_optional_at(root_fd: int, directory: str, name: str, *, label: str) -> bytes | None:
    directory_fd = os.dup(root_fd)
    try:
        for part in directory.split("/"):
            try:
                next_fd = _open_child_directory(directory_fd, part, label=label)
            except StageProtocolError as exc:
                if isinstance(exc.__cause__, FileNotFoundError):
                    return None
                raise
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            file_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StageProtocolError(f"{label} 不可读取：{name}") from exc
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise StageProtocolError(f"{label} 必须是 regular file：{name}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(file_fd, 1024 * 1024)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


def _atomic_create_once(root_fd: int, directory: str, name: str, data: bytes) -> None:
    directory_fd = _mkdirs_at(root_fd, directory)
    temporary = f".tmp-{secrets.token_hex(16)}"
    created = False
    try:
        temp_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            view = memoryview(data)
            while view:
                written = os.write(temp_fd, view)
                view = view[written:]
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        try:
            os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
            created = True
        except FileExistsError as exc:
            existing = _read_regular_at(directory_fd, name, label="create-once 目标")
            if existing != data:
                raise StageConflict(f"create-once 冲突：{directory}/{name}") from exc
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory_fd)
    if not created:
        return


def _execution_root_fd(execution_id: str) -> tuple[Path, int]:
    normalized = validate_execution_id(execution_id)
    output_fd = _open_root(paths.OUTPUT_ROOT, label="output 根")
    try:
        tasks_ref = _relative_to_output(paths.DATA_EXECUTIONS_ROOT, label="execution 父根")
        tasks_fd = os.dup(output_fd)
        try:
            for part in PurePosixPath(tasks_ref).parts:
                next_fd = _open_child_directory(tasks_fd, part, label="execution 父根")
                os.close(tasks_fd)
                tasks_fd = next_fd
            root_fd = _open_child_directory(tasks_fd, normalized, label="execution 根")
        finally:
            os.close(tasks_fd)
    finally:
        os.close(output_fd)
    try:
        _read_regular_at(root_fd, "execution_manifest.json", label="execution manifest")
    except BaseException:
        os.close(root_fd)
        raise StageProtocolError(f"execution 不存在、未初始化或不可信：{normalized}")
    return paths.DATA_EXECUTIONS_ROOT / normalized, root_fd


def _scope_fd(scope: str, execution_fd: int) -> int:
    if scope == "execution":
        return os.dup(execution_fd)
    if scope == "output":
        return _open_root(paths.OUTPUT_ROOT, label="output 根")
    if scope == "repo":
        return _open_root(paths.REPO_ROOT, label="repo 根")
    raise StageProtocolError(f"未知 ref scope：{scope}")


def _resolve_ref(binding: dict[str, Any], *, execution_fd: int) -> dict[str, str]:
    scope = str(binding.get("scope") or "")
    ref = _safe_ref(binding.get("ref"))
    root_fd = _scope_fd(scope, execution_fd)
    try:
        raw = _read_regular_at(root_fd, ref, label=f"{scope} ref")
    finally:
        os.close(root_fd)
    return {"scope": scope, "ref": ref, "digest": _sha256(raw)}


def _freeze_refs(value: object, *, execution_fd: int, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise StageProtocolError(f"{label} 必须是数组")
    frozen: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"scope", "ref"}:
            raise StageProtocolError(f"{label} 元素只能包含 scope/ref")
        binding = _resolve_ref(raw, execution_fd=execution_fd)
        key = (binding["scope"], binding["ref"])
        if key in seen:
            raise StageProtocolError(f"{label} 含重复引用：{key[0]}:{key[1]}")
        seen.add(key)
        frozen.append(binding)
    return frozen


def _validate_review_close_actor(
    request: dict[str, Any],
    *,
    execution_fd: int,
) -> None:
    """5.review CLOSE 必须复用独立 reviewer 的真实 actor，而非作者身份。"""
    close_actor = request.get("actor")
    close_actor = close_actor if isinstance(close_actor, dict) else {}
    close_invocation = close_actor.get("invocation")
    if not isinstance(close_invocation, dict):
        raise StageProtocolError("5.review actor.invocation 必须记录真实 provider/model/runId")

    reviewer_actors: list[dict[str, Any]] = []
    for binding in request.get("resultRefs") or []:
        if not isinstance(binding, dict):
            continue
        scope = str(binding.get("scope") or "")
        ref = str(binding.get("ref") or "")
        if not ref.endswith("5.review/reviewer_result.json"):
            continue
        if scope != "execution":
            raise StageProtocolError("5.review reviewer_result 必须使用 execution ref")
        raw = _read_regular_at(execution_fd, ref, label="5.review reviewer_result")
        reviewer_result = _parse_json_object(raw, label="5.review reviewer_result")
        try:
            assert_valid(
                reviewer_result,
                "content",
                "reviewer_result",
                label="5.review reviewer_result",
            )
        except ValueError as exc:
            raise StageProtocolError(str(exc)) from exc
        reviewer_actors.append(dict(reviewer_result["actor"]))
    if not reviewer_actors:
        raise StageProtocolError("5.review resultRefs 必须包含 reviewer_result.json")
    if any(actor != close_actor for actor in reviewer_actors):
        raise StageProtocolError("5.review CLOSE actor 与 reviewer_result.actor 不一致")
    draft_receipt = _load_artifact(
        execution_fd,
        _RECEIPT_DIRECTORY,
        _expected_name("4.draft"),
        label="4.draft stage receipt",
        schema_name="stage_receipt",
    )
    if draft_receipt is None:
        raise StageProtocolError("5.review 缺少 4.draft receipt")
    author_actor = draft_receipt[0].get("actor")
    author_actor = author_actor if isinstance(author_actor, dict) else {}
    if (close_actor.get("host"), close_actor.get("sessionId")) == (
        author_actor.get("host"),
        author_actor.get("sessionId"),
    ):
        raise StageProtocolError("5.review reviewer 与 4.draft 作者使用同一 host/sessionId")
    author_invocation = author_actor.get("invocation")
    author_invocation = author_invocation if isinstance(author_invocation, dict) else {}
    author_run_id = str(author_invocation.get("runId") or "").strip()
    reviewer_run_id = str(close_invocation.get("runId") or "").strip()
    if not author_run_id or author_run_id == reviewer_run_id:
        raise StageProtocolError("5.review reviewer 必须使用不同于作者的真实 invocation.runId")


def _load_artifact(root_fd: int, directory: str, name: str, *, label: str, schema_name: str) -> tuple[dict[str, Any], bytes] | None:
    raw = _read_optional_at(root_fd, directory, name, label=label)
    if raw is None:
        return None
    value = _parse_json_object(raw, label=label)
    try:
        assert_valid(value, "execution", schema_name, label=label)
    except ValueError as exc:
        raise StageProtocolError(str(exc)) from exc
    if raw != _canonical_bytes(value):
        raise StageProtocolError(f"{label} 不是 canonical JSON：{name}")
    return value, raw


def _artifact_names(root_fd: int, directory: str) -> set[str]:
    descriptor = os.dup(root_fd)
    try:
        for part in directory.split("/"):
            try:
                next_fd = _open_child_directory(descriptor, part, label=directory)
            except StageProtocolError as exc:
                if isinstance(exc.__cause__, FileNotFoundError):
                    return set()
                raise
            os.close(descriptor)
            descriptor = next_fd
        try:
            names = set(os.listdir(descriptor))
        except OSError as exc:
            raise StageProtocolError(f"无法扫描 {directory}") from exc
        for name in names:
            try:
                mode = os.stat(name, dir_fd=descriptor, follow_symlinks=False).st_mode
            except OSError as exc:
                raise StageProtocolError(f"无法检查 {directory}/{name}") from exc
            if not stat.S_ISREG(mode):
                raise StageProtocolError(f"{directory} 只能包含 regular files：{name}")
        return names
    finally:
        os.close(descriptor)


def _expected_name(stage: str) -> str:
    return f"{_STAGE_INDEX[stage] + 1:03d}-{stage}.json"


def _validate_progress(
    root_fd: int,
    execution_id: str,
    *,
    stage: str,
    sequence: int,
    include_current_receipt: bool = False,
) -> dict[str, Any] | None:
    receipt_count = sequence if include_current_receipt else sequence - 1
    expected_receipts = {_expected_name(item) for item in RECEIPT_STAGES[:receipt_count]}
    actual_receipts = _artifact_names(root_fd, _RECEIPT_DIRECTORY)
    if actual_receipts != expected_receipts:
        missing = sorted(expected_receipts - actual_receipts)
        extra = sorted(actual_receipts - expected_receipts)
        raise StageProtocolError(f"receipt 必须是严格连续前缀；missing={missing} extra={extra}")
    predecessor: dict[str, Any] | None = None
    direct_predecessor: dict[str, Any] | None = None
    for index, prior_stage in enumerate(RECEIPT_STAGES[:receipt_count], start=1):
        if index == sequence:
            direct_predecessor = predecessor
        loaded = _load_artifact(
            root_fd,
            _RECEIPT_DIRECTORY,
            _expected_name(prior_stage),
            label=f"receipt:{prior_stage}",
            schema_name="stage_receipt",
        )
        assert loaded is not None
        receipt, raw = loaded
        if receipt.get("executionId") != execution_id or receipt.get("stage") != prior_stage or receipt.get("sequence") != index:
            raise StageProtocolError(f"receipt 身份漂移：{prior_stage}")
        if receipt.get("verdict") != "pass":
            raise StageProtocolError(f"已有 blocked receipt，不得继续：{prior_stage}")
        expected_predecessor = None if predecessor is None else predecessor
        if receipt.get("predecessor") != expected_predecessor:
            raise StageProtocolError(f"receipt predecessor 链漂移：{prior_stage}")
        predecessor = {
            "scope": "execution",
            "ref": f"{_RECEIPT_DIRECTORY}/{_expected_name(prior_stage)}",
            "digest": _sha256(raw),
        }
    return direct_predecessor if include_current_receipt else predecessor


def _reject_if_blocked(root_fd: int, execution_id: str) -> None:
    actual = _artifact_names(root_fd, _RECEIPT_DIRECTORY)
    expected_names = {_expected_name(item) for item in RECEIPT_STAGES}
    if not actual.issubset(expected_names):
        raise StageProtocolError(f"receipt 含非法命名：{sorted(actual - expected_names)}")
    for index, receipt_stage in enumerate(RECEIPT_STAGES, start=1):
        name = _expected_name(receipt_stage)
        if name not in actual:
            continue
        try:
            loaded = _load_artifact(
                root_fd,
                _RECEIPT_DIRECTORY,
                name,
                label=f"receipt:{receipt_stage}",
                schema_name="stage_receipt",
            )
        except StageProtocolError:
            # 拓扑校验负责报告 future/缺口；任意合法 blocked receipt 即使位于坏拓扑中也终止。
            continue
        assert loaded is not None
        receipt, _raw = loaded
        if (
            receipt.get("executionId") != execution_id
            or receipt.get("stage") != receipt_stage
            or receipt.get("sequence") != index
        ):
            raise StageProtocolError(f"receipt 身份漂移：{receipt_stage}")
        if receipt.get("verdict") == "blocked":
            raise StageProtocolError(f"已有 blocked receipt，不得继续：{receipt_stage}")


def _validate_open_topology(root_fd: int, *, stage: str, sequence: int, allow_current: bool) -> None:
    current_name = _expected_name(stage)
    allowed = {_expected_name(item) for item in RECEIPT_STAGES[: sequence - 1]}
    if allow_current:
        allowed.add(current_name)
    actual = _artifact_names(root_fd, _OPEN_DIRECTORY)
    if actual != allowed:
        missing = sorted(allowed - actual)
        extra = sorted(actual - allowed)
        raise StageProtocolError(f"stage open 必须是严格连续前缀；missing={missing} extra={extra}")


def _validate_open(root_fd: int, execution_id: str, *, stage: str, sequence: int) -> tuple[dict[str, Any], bytes]:
    loaded = _load_artifact(
        root_fd,
        _OPEN_DIRECTORY,
        _expected_name(stage),
        label=f"stage-open:{stage}",
        schema_name="stage_open_request",
    )
    if loaded is None:
        raise StageProtocolError(f"stage 尚未 open：{stage}")
    value, raw = loaded
    if value.get("executionId") != execution_id or value.get("stage") != stage or value.get("sequence") != sequence:
        raise StageProtocolError("stage open 身份漂移")
    return value, raw


def _revalidate_open_inputs(root_fd: int, open_value: dict[str, Any]) -> None:
    for binding in open_value["inputRefs"]:
        current = _resolve_ref({"scope": binding["scope"], "ref": binding["ref"]}, execution_fd=root_fd)
        if current != binding:
            raise StageProtocolError(f"stage-open input exact bytes 漂移：{binding['scope']}:{binding['ref']}")


_RFC3339 = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)


def _observed_at(value: object) -> None:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise StageProtocolError("verifierFacts.observedAt 必须是含 timezone 的 RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StageProtocolError("verifierFacts.observedAt 必须是含 timezone 的 RFC3339") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StageProtocolError("verifierFacts.observedAt 必须是含 timezone 的 RFC3339")


def _validate_verifier_facts(value: list[dict[str, Any]], *, root_fd: int) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for fact in value:
        copied = dict(fact)
        _observed_at(copied.get("observedAt"))
        evidence_ref = copied.get("evidenceRef")
        evidence_digest = copied.get("evidenceDigest")
        if evidence_digest is not None and evidence_ref is None:
            raise StageProtocolError("verifierFacts.evidenceDigest 必须与 evidenceRef 同时出现")
        if evidence_ref is not None:
            if not isinstance(evidence_ref, dict):
                raise StageProtocolError("verifierFacts.evidenceRef 必须是 ref 对象")
            frozen = _resolve_ref(evidence_ref, execution_fd=root_fd)
            if evidence_digest is not None and evidence_digest != frozen["digest"]:
                raise StageProtocolError("verifier evidence digest 不匹配实际字节")
            copied["evidenceRef"] = {"scope": frozen["scope"], "ref": frozen["ref"]}
            copied["evidenceDigest"] = frozen["digest"]
        facts.append(copied)
    return facts


def _relative_to_output(path: Path, *, label: str) -> str:
    absolute = Path(os.path.abspath(path.expanduser()))
    output = Path(os.path.abspath(paths.OUTPUT_ROOT.expanduser()))
    try:
        return _safe_ref(absolute.relative_to(output).as_posix())
    except ValueError as exc:
        raise StageProtocolError(f"{label} 必须位于 output 根内") from exc


@contextmanager
def _stage_lock(execution_id: str) -> Iterator[None]:
    output_fd = _open_root(paths.OUTPUT_ROOT, label="output 根")
    try:
        lock_ref = _relative_to_output(
            paths.DATA_LOCAL_ROOT / "runs/locks/stage-receipt",
            label="stage lock 根",
        )
        lock_fd = _mkdirs_at(output_fd, lock_ref)
        try:
            try:
                handle_fd = os.open(
                    f"{execution_id}.lock",
                    os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=lock_fd,
                )
            except OSError as exc:
                raise StageProtocolError("stage lock 必须是无 symlink 的 regular file") from exc
            if not stat.S_ISREG(os.fstat(handle_fd).st_mode):
                os.close(handle_fd)
                raise StageProtocolError("stage lock 必须是 regular file")
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


def open_stage(execution_id: str, stage: str, input_path: Path) -> Path:
    normalized_stage, sequence = _stage(stage)
    request, canonical_input = _load_input(input_path)
    if set(request) != {"inputRefs"} or not isinstance(request.get("inputRefs"), list):
        raise StageProtocolError("stage-open input 只能包含 inputRefs 数组")
    normalized_id = validate_execution_id(execution_id)
    with _stage_lock(normalized_id):
        root, root_fd = _execution_root_fd(normalized_id)
        try:
            _reject_if_blocked(root_fd, normalized_id)
            receipt = _load_artifact(root_fd, _RECEIPT_DIRECTORY, _expected_name(normalized_stage), label="stage receipt", schema_name="stage_receipt")
            if receipt is not None:
                if receipt[0].get("verdict") == "blocked":
                    raise StageProtocolError(f"已有 blocked receipt，不得继续：{normalized_stage}")
                raise StageProtocolError(f"stage 已关闭：{normalized_stage}")
            predecessor = _validate_progress(root_fd, normalized_id, stage=normalized_stage, sequence=sequence)
            current = _load_artifact(root_fd, _OPEN_DIRECTORY, _expected_name(normalized_stage), label="stage open", schema_name="stage_open_request")
            _validate_open_topology(root_fd, stage=normalized_stage, sequence=sequence, allow_current=current is not None)
            frozen_refs = _freeze_refs(request["inputRefs"], execution_fd=root_fd, label="inputRefs")
            value = {
                "schema": "quwoquan_data.stage_open_request",
                "executionId": normalized_id,
                "stage": normalized_stage,
                "sequence": sequence,
                "predecessor": predecessor,
                "input": {"digest": _sha256(canonical_input)},
                "submittedInput": request,
                "inputRefs": frozen_refs,
            }
            assert_valid(value, "execution", "stage_open_request", label=f"stage-open:{normalized_stage}")
            encoded = _canonical_bytes(value)
            if current is not None:
                if current[1] == encoded:
                    return root / _OPEN_DIRECTORY / _expected_name(normalized_stage)
                raise StageConflict(f"stage-open 输入或引用字节冲突：{normalized_stage}")
            _atomic_create_once(root_fd, _OPEN_DIRECTORY, _expected_name(normalized_stage), encoded)
            return root / _OPEN_DIRECTORY / _expected_name(normalized_stage)
        finally:
            os.close(root_fd)


def close_stage(execution_id: str, stage: str, input_path: Path) -> Path:
    normalized_stage, sequence = _stage(stage)
    request, canonical_input = _load_input(input_path, schema_name="stage_close_input")
    verdict = request["verdict"]
    issues = request["typedIssues"]
    results = request["resultRefs"]
    facts = request["verifierFacts"]
    if any(_STAGE_INDEX[issue["recoveryStage"]] > sequence - 1 for issue in issues):
        raise StageProtocolError("typedIssues.recoveryStage 只能是当前或已完成 stage")
    if verdict == "pass":
        if (
            issues
            or not results
            or not facts
            or any(
                fact.get("status") != "passed"
                or fact.get("exitCode") != 0
                or fact.get("evidenceRef") is None
                or fact.get("evidenceDigest") is None
                for fact in facts
            )
        ):
            raise StageProtocolError("pass 必须 resultRefs 非空、typedIssues 为空，且 verifierFacts 全部 passed/exitCode=0 并绑定 evidence")
    elif not issues:
        raise StageProtocolError("blocked 必须包含 typedIssues")

    normalized_id = validate_execution_id(execution_id)
    with _stage_lock(normalized_id):
        root, root_fd = _execution_root_fd(normalized_id)
        try:
            _reject_if_blocked(root_fd, normalized_id)
            if normalized_stage == "5.review" and verdict == "pass":
                _validate_review_close_actor(request, execution_fd=root_fd)
            facts = _validate_verifier_facts(facts, root_fd=root_fd)
            if verdict == "pass" and any(
                fact.get("status") != "passed"
                or fact.get("exitCode") != 0
                or fact.get("evidenceRef") is None
                or fact.get("evidenceDigest") is None
                for fact in facts
            ):
                raise StageProtocolError("pass verifierFacts 必须全部 passed/exitCode=0 并绑定有效 evidence")
            current = _load_artifact(root_fd, _RECEIPT_DIRECTORY, _expected_name(normalized_stage), label="stage receipt", schema_name="stage_receipt")
            if current is not None and current[0].get("verdict") == "blocked":
                raise StageProtocolError(f"已有 blocked receipt，不得继续：{normalized_stage}")
            predecessor = _validate_progress(
                root_fd,
                normalized_id,
                stage=normalized_stage,
                sequence=sequence,
                include_current_receipt=current is not None,
            )
            _validate_open_topology(root_fd, stage=normalized_stage, sequence=sequence, allow_current=True)
            open_value, open_raw = _validate_open(root_fd, normalized_id, stage=normalized_stage, sequence=sequence)
            if open_value.get("predecessor") != predecessor:
                raise StageProtocolError("stage open predecessor 漂移")
            _revalidate_open_inputs(root_fd, open_value)
            frozen_results = _freeze_refs(results, execution_fd=root_fd, label="resultRefs")
            frozen_facts = facts
            value = {
                "schema": "quwoquan_data.stage_receipt",
                "executionId": normalized_id,
                "stage": normalized_stage,
                "sequence": sequence,
                "predecessor": predecessor,
                "openRequest": {
                    "scope": "execution",
                    "ref": f"{_OPEN_DIRECTORY}/{_expected_name(normalized_stage)}",
                    "digest": _sha256(open_raw),
                },
                "closeInput": {"digest": _sha256(canonical_input)},
                "submittedClose": request,
                "actor": request["actor"],
                "verdict": verdict,
                "typedIssues": issues,
                "inputRefs": open_value["inputRefs"],
                "resultRefs": frozen_results,
                "verifierFacts": frozen_facts,
            }
            assert_valid(value, "execution", "stage_receipt", label=f"stage-close:{normalized_stage}")
            encoded = _canonical_bytes(value)
            if current is not None:
                if current[1] == encoded:
                    return root / _RECEIPT_DIRECTORY / _expected_name(normalized_stage)
                raise StageConflict(f"stage-close 输入或引用字节冲突：{normalized_stage}")
            _atomic_create_once(root_fd, _RECEIPT_DIRECTORY, _expected_name(normalized_stage), encoded)
            return root / _RECEIPT_DIRECTORY / _expected_name(normalized_stage)
        finally:
            os.close(root_fd)


__all__ = [
    "RECEIPT_STAGES",
    "StageConflict",
    "StageProtocolError",
    "close_stage",
    "open_stage",
]

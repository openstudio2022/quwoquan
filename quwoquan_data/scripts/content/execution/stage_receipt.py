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


def _freeze_refs(
    value: object,
    *,
    execution_fd: int,
    label: str,
    allow_actor: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise StageProtocolError(f"{label} 必须是数组")
    frozen: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise StageProtocolError(f"{label} 元素必须是对象")
        allowed = ({"scope", "ref"}, {"scope", "ref", "actor"})
        if set(raw) not in (allowed if allow_actor else allowed[:1]):
            raise StageProtocolError(f"{label} 元素字段非法")
        binding: dict[str, Any] = _resolve_ref(raw, execution_fd=execution_fd)
        if "actor" in raw:
            binding["actor"] = raw["actor"]
        key = (binding["scope"], binding["ref"])
        if key in seen:
            raise StageProtocolError(f"{label} 含重复引用：{key[0]}:{key[1]}")
        seen.add(key)
        frozen.append(binding)
    return frozen


def _target_refs(execution_fd: int) -> list[str]:
    raw = _read_regular_at(execution_fd, "0.plan/target_set.json", label="target_set")
    target_set = _parse_json_object(raw, label="target_set")
    try:
        assert_valid(target_set, "execution", "target_set", label="target_set")
    except ValueError as exc:
        raise StageProtocolError(str(exc)) from exc
    refs = target_set.get("targetRefs")
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise StageProtocolError("target_set.targetRefs 必须是字符串数组")
    return list(refs)


def _actor_identity(actor: object, *, label: str) -> tuple[str, str, str]:
    value = actor if isinstance(actor, dict) else {}
    invocation = value.get("invocation")
    if not isinstance(invocation, dict):
        raise StageProtocolError(f"{label}.invocation 必须记录真实 provider/model/runId")
    host = str(value.get("host") or "").strip()
    session_id = str(value.get("sessionId") or "").strip()
    run_id = str(invocation.get("runId") or "").strip()
    if not host or not session_id or not run_id:
        raise StageProtocolError(f"{label} 必须记录真实 host/sessionId/invocation.runId")
    return host, session_id, run_id


def _result_bindings(request: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("ref") or ""): row
        for row in request.get("resultRefs") or []
        if isinstance(row, dict) and row.get("scope") == "execution"
    }


def _binding_actor(
    binding: dict[str, Any], *, fallback: object, label: str
) -> dict[str, Any]:
    actor = binding.get("actor", fallback)
    _actor_identity(actor, label=label)
    if not isinstance(actor, dict):
        raise StageProtocolError(f"{label} 必须是对象")
    return actor


def _validate_draft_close(
    request: dict[str, Any], *, execution_fd: int
) -> None:
    fallback = request.get("actor")
    _actor_identity(fallback, label="4.draft actor")
    expected: set[str] = set()
    for target_ref in _target_refs(execution_fd):
        carrier = "homepage" if target_ref.startswith("entities/") else target_ref.split("/", 2)[1]
        name = {
            "homepage": "page.md",
            "article": "draft.article.md",
            "image": "image_work.json",
            "video": "video_script.json",
        }[carrier]
        expected.add(f"{target_ref}/4.draft/{name}")
    bindings = _result_bindings(request)
    if set(bindings) != expected:
        raise StageProtocolError("4.draft resultRefs 必须 exact 包含每对象唯一 carrier 主产物")
    for ref, binding in bindings.items():
        _binding_actor(binding, fallback=fallback, label=f"4.draft author:{ref}")


def _author_by_object(draft_receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fallback = draft_receipt.get("actor")
    authors: dict[str, dict[str, Any]] = {}
    for raw in draft_receipt.get("resultRefs") or []:
        if not isinstance(raw, dict) or raw.get("scope") != "execution":
            continue
        ref = str(raw.get("ref") or "")
        marker = "/4.draft/"
        if marker not in ref:
            continue
        object_ref = ref.split(marker, 1)[0]
        if object_ref in authors:
            raise StageProtocolError(f"4.draft 对象 author binding 重复：{object_ref}")
        authors[object_ref] = _binding_actor(
            raw, fallback=fallback, label=f"4.draft author:{object_ref}"
        )
    return authors


def _independent_actor_pair(
    author: object, reviewer: object, *, object_ref: str
) -> None:
    author_host, author_session, author_run = _actor_identity(
        author, label=f"4.draft author:{object_ref}"
    )
    reviewer_host, reviewer_session, reviewer_run = _actor_identity(
        reviewer, label=f"5.review reviewer:{object_ref}"
    )
    if (author_host, author_session) == (reviewer_host, reviewer_session):
        raise StageProtocolError(
            f"5.review reviewer 与对应 4.draft 作者使用同一 host/sessionId：{object_ref}"
        )
    if author_run == reviewer_run:
        raise StageProtocolError(
            f"5.review reviewer 与对应 4.draft 作者使用同一 invocation.runId：{object_ref}"
        )


def _validate_review_close(
    request: dict[str, Any], *, execution_fd: int, execution_id: str
) -> None:
    fallback = request.get("actor")
    _actor_identity(fallback, label="5.review actor")
    expected_refs = {
        f"{target_ref}/5.review/content_review.json"
        for target_ref in _target_refs(execution_fd)
    }
    bindings = _result_bindings(request)
    if set(bindings) != expected_refs:
        raise StageProtocolError("5.review resultRefs 必须 exact 包含每对象 content_review.json")

    draft_loaded = _load_artifact(
        execution_fd, _RECEIPT_DIRECTORY, _expected_name("4.draft"),
        label="4.draft stage receipt", schema_name="stage_receipt",
    )
    if draft_loaded is None:
        raise StageProtocolError("5.review 缺少 4.draft receipt")
    authors = _author_by_object(draft_loaded[0])

    approved = 0
    for ref in sorted(expected_refs):
        target_ref = ref.removesuffix("/5.review/content_review.json")
        author = authors.get(target_ref)
        if author is None:
            raise StageProtocolError(f"5.review 缺少对应 4.draft author binding：{target_ref}")
        reviewer = _binding_actor(
            bindings[ref], fallback=fallback, label=f"5.review reviewer:{target_ref}"
        )
        _independent_actor_pair(author, reviewer, object_ref=target_ref)
        raw = _read_regular_at(execution_fd, ref, label="5.review content_review")
        review = _parse_json_object(raw, label="5.review content_review")
        try:
            assert_valid(review, "content", "content_review", label=ref)
        except ValueError as exc:
            raise StageProtocolError(str(exc)) from exc
        if review.get("executionId") != execution_id:
            raise StageProtocolError("content_review executionId 与 execution 漂移")
        if str(review.get("objectRef") or "").strip("/") != target_ref:
            raise StageProtocolError("content_review objectRef 与 target_set 漂移")
        approved += review.get("decision") == "approved"
    if approved == 0:
        raise StageProtocolError("5.review pass 必须至少包含一个 approved 对象")


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
    if verdict == "pass":
        if (
            not results
            or not facts
            or any(
                fact.get("status") != "passed"
                or fact.get("exitCode") != 0
                or fact.get("evidenceRef") is None
                or fact.get("evidenceDigest") is None
                for fact in facts
            )
        ):
            raise StageProtocolError("pass 必须 resultRefs 非空，且 verifierFacts 全部 passed/exitCode=0 并绑定 evidence")
    elif not issues:
        raise StageProtocolError("blocked 必须包含 typedIssues")

    normalized_id = validate_execution_id(execution_id)
    with _stage_lock(normalized_id):
        root, root_fd = _execution_root_fd(normalized_id)
        try:
            _reject_if_blocked(root_fd, normalized_id)
            if normalized_stage == "4.draft" and verdict == "pass":
                _validate_draft_close(request, execution_fd=root_fd)
            if normalized_stage == "5.review" and verdict == "pass":
                _validate_review_close(
                    request,
                    execution_fd=root_fd,
                    execution_id=normalized_id,
                )
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
            frozen_results = _freeze_refs(
                results,
                execution_fd=root_fd,
                label="resultRefs",
                allow_actor=normalized_stage in {"4.draft", "5.review"},
            )
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

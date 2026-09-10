"""从一份 round spec 确定性创建一轮内全部 carrier 的最小 execution 工作包。"""
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
from content.execution.receipt_chain import (
    ReceiptChainError,
    validate_live_receipt_chain,
)
from core import paths
from core.schema import assert_valid

REQUEST_REF = "0.plan/request.json"
TARGET_SET_REF = "0.plan/target_set.json"
# AI 提交的两份输入按 canonical 字节复制到 execution 内，binding ref 指向该副本而不是提交路径。
INPUTS_REF = "0.plan/inputs"
# 候选绑定省略 entityCatalogDigest 时，从受版本控制的实体目录实际计算，不再要求 AI 手写。
ENTITY_CATALOG_SOURCE_REF = "quwoquan_data/reference/travel"


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


def _load_submitted_document(path: Path, *, schema_name: str) -> dict[str, Any]:
    """读取 AI 提交的输入：任意路径、任意 JSON 排版；只要求是对象且过 schema。"""
    raw = _assert_regular_bytes(path, label=f"{schema_name} 输入")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskInitError(f"{schema_name} 必须是合法 JSON") from exc
    if not isinstance(value, dict):
        raise TaskInitError(f"{schema_name} 必须是 JSON 对象")
    assert_valid(value, "execution", schema_name, label=f"task init {schema_name}")
    return value


def _region_tag_exists(region: str) -> bool:
    taxonomy_root = Path(os.environ.get("QWQ_TAGS_ROOT") or paths.CONTROL_PLANE_TAXONOMY_ROOT)
    parts = PurePosixPath(region).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return False
    return (taxonomy_root / "Topic" / "地理" / "行政区" / region / "_definition.json").is_file()


def execution_target_ref(target: Mapping[str, Any], *, carrier: str) -> str:
    """从 schema 合法的冻结 target 生成 execution 相对过程路径，不生成逻辑身份。

    homepage 叶子只取显式 entityRef 的摘要；post 需要完整的 publishAngle/Title/Seq。
    不读取地域目录或 publish 树，输入非法时抛 TaskInitError；调用方不得另写路径算法。
    """
    name = str(target.get("name") or "").strip()
    entity_type = str(target.get("entityType") or "").strip().strip("/")
    if not name or len(entity_type.split("/")) != 2:
        raise TaskInitError(f"候选 target 非法：{entity_type}/{name}")
    if carrier == "homepage":
        entity_ref = target.get("entityRef")
        if not isinstance(entity_ref, str) or not entity_ref.startswith("/entity/"):
            raise TaskInitError("DATA.EXECUTION.TARGET_IDENTITY_REQUIRED: entityRef")
        # 只生成 execution 物理叶子，不生成业务 ID，也不读取当前 publish locator。
        token = hashlib.sha256(entity_ref.encode("utf-8")).hexdigest()
        return f"entities/{entity_type}/entity-{token}"
    angle = str(target.get("publishAngle") or "").strip()
    title = str(target.get("publishTitle") or "").strip()
    sequence = target.get("publishSeq")
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
        if carrier == "homepage":
            # region 在 publish 派生 geoTagRef；缺失或不可解析在这里就判否，不留到第 5 步。
            region = str(target.get("region") or "").strip()
            if not region or not _region_tag_exists(region):
                raise TaskInitError(f"homepage target 缺少可解析的 region（Topic/地理/行政区/<region>）：{target['name']}")
            target["region"] = region
        else:
            target["publishAngle"] = str(target.get("publishAngle") or "").strip()
            target["publishTitle"] = str(target.get("publishTitle") or "").strip()
            target.setdefault("publishSeq", 1)
        ref = execution_target_ref(target, carrier=carrier)
        if ref in seen:
            raise TaskInitError(f"targetRef 重复：{ref}")
        seen.add(ref)
        pairs.append((ref, target))
    pairs.sort(key=lambda pair: pair[0])
    targets = [target for _, target in pairs]
    _validate_entity_bindings(targets)
    return targets, [ref for ref, _ in pairs]


def _validate_entity_bindings(targets: list[dict[str, Any]]) -> None:
    """同一显式 ref/ID 必须一一绑定；分类与已声明地域不能在同一输入里相互矛盾。"""
    by_ref: dict[str, dict[str, Any]] = {}
    by_id: dict[str, str] = {}
    for target in targets:
        entity_ref, entity_id = target["entityRef"], target["entityId"]
        previous = by_ref.setdefault(entity_ref, {})
        if by_id.setdefault(entity_id, entity_ref) != entity_ref:
            raise TaskInitError(f"DATA.EXECUTION.TARGET_IDENTITY_CONFLICT: entityId={entity_id}")
        for field in ("entityId", "entityType", "region"):
            value = target.get(field)
            if field != "entityId" and isinstance(value, str):
                value = value.strip()
            if value and previous.setdefault(field, value) != value:
                raise TaskInitError(f"DATA.EXECUTION.TARGET_IDENTITY_CONFLICT: {entity_ref}/{field}")


def _assert_regular_bytes(path: Path, *, label: str) -> bytes:
    absolute = _absolute(path)
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise TaskInitError(f"{label} 不得包含 symlink：{path}")
    except FileNotFoundError as exc:
        raise TaskInitError(f"{label} 不存在：{path}") from exc
    if not absolute.is_file():
        raise TaskInitError(f"{label} 必须是 regular file：{path}")
    return absolute.read_bytes()

def _retry_binding(execution_id: str, retry_of: object) -> dict[str, Any] | None:
    """Validate the caller-selected blocked execution and freeze its terminal receipt."""

    if retry_of is None:
        return None
    previous_id = validate_execution_id(str(retry_of))
    if previous_id == execution_id:
        raise TaskInitError("retryOf 不得引用当前 executionId")

    previous_root = paths.DATA_EXECUTIONS_ROOT / previous_id
    try:
        manifest_raw = _assert_regular_bytes(
            previous_root / "execution_manifest.json",
            label="retryOf execution manifest",
        )
        manifest = json.loads(manifest_raw)
        assert_valid(
            manifest,
            "execution",
            "content_execution_manifest",
            label="retryOf execution manifest",
        )
        if (
            not isinstance(manifest, dict)
            or manifest.get("executionId") != previous_id
            or manifest_raw != _canonical_bytes(manifest)
        ):
            raise TaskInitError("retryOf execution manifest 身份或 canonical bytes 非法")
        chain = validate_live_receipt_chain(
            execution_id=previous_id,
            execution_root=previous_root,
            repo_root=paths.REPO_ROOT,
            output_root=paths.OUTPUT_ROOT,
            terminal_verdict="blocked",
        )
    except TaskInitError:
        raise
    except ReceiptChainError as exc:
        raise TaskInitError(f"retryOf receipt 链不可信：{exc}") from exc
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise TaskInitError(f"retryOf execution 不存在或 receipt 链不可信：{previous_id}") from exc

    terminal_name = (
        f"{len(chain.receipts):03d}-{chain.terminal_receipt['stage']}.json"
    )
    receipt_ref = _relative_ref(
        previous_root / "_shared/receipts" / terminal_name,
        root=paths.OUTPUT_ROOT,
        label="retryOf terminal receipt",
    )
    return {
        "executionId": previous_id,
        "terminalReceipt": {
            "scope": "output",
            "ref": receipt_ref,
            "digest": _sha256(chain.terminal_raw),
        },
    }


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


def _normalized_inputs(
    demand: dict[str, Any], bindings: dict[str, Any], *, target_count: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """把 AI 可省略的机械字段补成确定值；语义字段原样保留。"""
    demand = dict(demand)
    bindings = dict(bindings)
    demand.setdefault("status", "confirmed")
    demand.setdefault("quota", target_count)
    demand.setdefault("retryOf", None)
    bindings.setdefault("candidateCount", target_count)
    if not bindings.get("entityCatalogDigest"):
        from content.execution.workspace import entity_catalog_digest

        bindings["entityCatalogDigest"] = entity_catalog_digest(ENTITY_CATALOG_SOURCE_REF)
    return demand, bindings


_CARRIERS = ("homepage", "article", "image", "video")
_TARGET_IDENTITY_FIELDS = ("entityRef", "entityId", "entityType", "name", "region", "publishAngle", "publishTitle", "publishSeq")


def _round_documents(round_spec: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """把一份 round spec 展开为逐 carrier 的 (carrier_demand, candidate_bindings)。

    familyRef 固定为 `content/travel/<carrier>/<carrier>`；只为实际有 target 的 carrier 建 execution。
    """
    _validate_entity_bindings(round_spec["targets"])
    executions = round_spec["executions"]
    retry_of = round_spec.get("retryOf") or {}
    by_carrier: dict[str, list[dict[str, Any]]] = {}
    for raw in round_spec["targets"]:
        carrier = str(raw["carrier"])
        if carrier not in executions:
            raise TaskInitError(f"target 的 carrier 没有对应 executionId：{carrier}/{raw.get('name')}")
        target = {key: raw[key] for key in _TARGET_IDENTITY_FIELDS if key in raw}
        by_carrier.setdefault(carrier, []).append(target)
    missing = sorted(set(executions) - set(by_carrier))
    if missing:
        raise TaskInitError(f"executions 声明了没有任何 target 的 carrier：{missing}")
    documents: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for carrier in _CARRIERS:
        if carrier not in by_carrier:
            continue
        execution_id = str(executions[carrier])
        demand: dict[str, Any] = {
            "schema": "quwoquan_data.carrier_demand",
            "executionId": execution_id,
            "carrier": carrier,
            "familyRef": f"content/travel/{carrier}/{carrier}",
        }
        if carrier in retry_of:
            demand["retryOf"] = str(retry_of[carrier])
        bindings: dict[str, Any] = {
            "schema": "quwoquan_data.immutable_candidate_bindings",
            "executionId": execution_id,
            "carrier": carrier,
            "targets": by_carrier[carrier],
        }
        documents.append((demand, bindings))
    return documents


def initialize_round(*, round_spec_path: Path) -> dict[str, Any]:
    """从一份 round spec 原子创建该轮全部 carrier execution；逐 execution 结果独立报告。

    单阶段批量：只在 init 这一步对显式输入做展开，不读 receipt、不推进、不恢复。
    """
    round_spec = _load_submitted_document(round_spec_path, schema_name="round_spec")
    results: list[dict[str, Any]] = []
    for demand, bindings in _round_documents(round_spec):
        assert_valid(demand, "execution", "carrier_demand", label="round spec derived carrier_demand")
        assert_valid(bindings, "execution", "immutable_candidate_bindings", label="round spec derived candidate_bindings")
        results.append(initialize_execution(submitted_demand=demand, submitted_bindings=bindings))
    return {"executions": results}


def initialize_task(*, carrier_demand_path: Path, candidate_bindings_path: Path) -> dict[str, Any]:
    submitted_demand = _load_submitted_document(carrier_demand_path, schema_name="carrier_demand")
    submitted_bindings = _load_submitted_document(
        candidate_bindings_path, schema_name="immutable_candidate_bindings"
    )
    return initialize_execution(submitted_demand=submitted_demand, submitted_bindings=submitted_bindings)


def initialize_execution(*, submitted_demand: dict[str, Any], submitted_bindings: dict[str, Any]) -> dict[str, Any]:
    assert_valid(submitted_demand, "execution", "carrier_demand", label="task init carrier demand")
    assert_valid(submitted_bindings, "execution", "immutable_candidate_bindings", label="task init candidate bindings")
    execution_id = validate_execution_id(str(submitted_demand["executionId"]))
    carrier = parse_execution_id(execution_id).content_type.value
    if submitted_demand["carrier"] != carrier or submitted_bindings["carrier"] != carrier:
        raise TaskInitError("carrier 与 executionId 不一致")
    if submitted_bindings["executionId"] != execution_id:
        raise TaskInitError("两份初始化输入的 executionId 不一致")
    targets, target_refs = _normalized_targets(submitted_bindings["targets"], carrier=carrier)
    demand, bindings = _normalized_inputs(submitted_demand, submitted_bindings, target_count=len(targets))
    bindings["targets"] = targets
    demand_canonical = _canonical_bytes(demand)
    bindings_canonical = _canonical_bytes(bindings)
    inputs_root = paths.DATA_EXECUTIONS_ROOT / execution_id / INPUTS_REF
    demand_ref = _relative_ref(inputs_root / "carrier_demand.json", root=paths.OUTPUT_ROOT, label="carrier_demand 输入")
    bindings_ref = _relative_ref(
        inputs_root / "candidate_bindings.json", root=paths.OUTPUT_ROOT, label="candidate_bindings 输入"
    )

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

    candidate_count = int(bindings["candidateCount"])
    quota = int(demand["quota"])
    if candidate_count != len(targets):
        raise TaskInitError("candidateCount 必须等于 targets 数量")
    retry_of = _retry_binding(execution_id, demand.get("retryOf"))

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

    documents = {
        "execution_manifest.json": manifest,
        REQUEST_REF: request,
        TARGET_SET_REF: target_set,
        f"{INPUTS_REF}/carrier_demand.json": demand,
        f"{INPUTS_REF}/candidate_bindings.json": bindings,
    }
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


__all__ = ["TaskInitConflict", "TaskInitError", "execution_target_ref", "initialize_execution", "initialize_round", "initialize_task"]

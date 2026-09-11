from __future__ import annotations

import contextlib
import fcntl
import os
import re
import socket
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from quwoquan_ops.cli.lib.common import relpath
from quwoquan_ops.cli.lib.output_paths import (
    _read_secure_json_object, _atomic_write_secure_json_object,
)
from quwoquan_ops.cli.lib.host_locks import (
    current_lock_owner,
    local_runtime_lock_path,
    parse_holder_record,
)


PortProbe = Callable[[str, int], bool]
LOCAL_RUNTIME_RESOURCE_GROUP = "workstation-commercial-runtime"


class LocalOperationLockBusyError(RuntimeError):
    """另一持有者正占用本地操作锁。

    保持 `RuntimeError` 子类，既有 `except RuntimeError` 的调用方语义不变；单独
    命名是为了让调用方能把「锁被占用，等持有者结束」与「锁内操作自身失败」分开
    判否——两者的恢复动作不同，混在一条 `except RuntimeError` 里会把后者的阻断
    错误归因为前者。
    """


LOCAL_RUNTIME_TARGETS = ("alpha-local", "beta-local", "gamma-local", "prod-sim")


def local_runtime_operation_lock_path(target: str = "") -> Path:
    """目标运行锁与宿主维护锁分离；空 target 只用于全局维护。"""
    if target and target not in LOCAL_RUNTIME_TARGETS:
        raise ValueError(f"unknown local runtime target: {target!r}")
    return local_runtime_lock_path(target or LOCAL_RUNTIME_RESOURCE_GROUP)


def _owner_record(**fields: str) -> str:
    return current_lock_owner(worktree_path=Path(__file__)).record(fields=fields)


@contextlib.contextmanager
def local_stack_operation_lock(
    target_name: str,
    *,
    lock_path: Path | None = None,
    wait_seconds: float = 0,
) -> Any:
    target = str(target_name).strip()
    if target not in LOCAL_RUNTIME_TARGETS:
        raise ValueError(f"local stack operation lock does not support {target!r}")
    if wait_seconds < 0:
        raise ValueError("wait_seconds cannot be negative")
    # 固定顺序：host shared -> target exclusive。全局维护只拿 host exclusive，
    # 不反向申请 target，因此不存在锁顺序环。显式路径仅供隔离测试 seam。
    with contextlib.ExitStack() as scope:
        if lock_path is None:
            guard = acquire_local_runtime_use_lock(
                target=target, purpose="target-operation",
                lock_path=local_runtime_operation_lock_path(),
            )
            scope.callback(guard.close)
        path = lock_path or local_runtime_operation_lock_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        owner = _owner_record(target=target)
        handle = scope.enter_context(path.open("a+", encoding="utf-8"))
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as error:
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(0.05, remaining))
                    continue
                handle.seek(0)
                holder = "\n".join(_live_holder_records(handle.read())) or "unknown"
                raise LocalOperationLockBusyError(
                    f"local stack operation is already running: {holder}"
                ) from error
        if lock_path is None:
            from quwoquan_ops.cli.lib.output_paths import deployment_target_path
            slot = _read_secure_json_object(
                deployment_target_path(target, "process", "environment-execution", "execution-slot.json"),
                label="environment execution slot",
            )
            if slot is not None and (
                slot.get("claimId") != os.environ.get("QWQ_ENVIRONMENT_EXECUTION_CLAIM_ID")
                or slot.get("executorStarted") is not True
            ):
                raise LocalOperationLockBusyError("OPS.RUNTIME.execution_claim_in_use: target reserved by scheduler")
            if slot is not None:
                try:
                    descriptor = int(os.environ.get("QWQ_ENVIRONMENT_EXECUTION_FD", ""))
                    actual = os.fstat(descriptor)
                    expected = deployment_target_path(target, "process", "environment-execution", ".claim.lock").stat()
                    if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                        raise ValueError("executor descriptor identity mismatch")
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, ValueError) as exc:
                    raise LocalOperationLockBusyError("OPS.RUNTIME.execution_fence_missing: inherited claim descriptor required") from exc
        # flock 本身在父进程死亡时释放，不能证明它启动的子进程已经终止。
        # durable fence 只有正常返回才关闭；崩溃/取消/异常保留，禁止 PID/TTL 接管。
        fence_path = path.with_suffix(".executor.json")
        if _read_secure_json_object(fence_path, label="target executor fence") is not None:
            raise LocalOperationLockBusyError(
                "OPS.RUNTIME.executor_reconcile_required: prior target executor has no verified closure"
            )
        nonce = uuid.uuid4().hex
        fence = {"target": target, "executorNonce": nonce, "owner": owner,
                 "executionClaimId": os.environ.get("QWQ_ENVIRONMENT_EXECUTION_CLAIM_ID", "")}
        _atomic_write_secure_json_object(fence_path, fence, label="target executor fence")
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        except BaseException:
            # 包括 KeyboardInterrupt：上层可报告失败，但不能把未知子进程变成可接管。
            raise
        else:
            current = _read_secure_json_object(fence_path, label="target executor fence")
            if current != fence:
                raise RuntimeError("OPS.RUNTIME.executor_fence_conflict")
            fence_path.unlink()
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def global_local_operation_lock(
    *,
    scope: str,
    affected_targets: Sequence[str],
    lock_path: Path | None = None,
) -> Any:
    canonical_host_lock = lock_path is None
    lock_path = lock_path or local_runtime_operation_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = _owner_record(scope=scope, mode="exclusive")
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            # 同上：本轮实测到的死记录事故（`purpose=runtime-package-build` 的 pid 已死）
            # 走的正是这条路径，故与共享租约路径同源过滤。
            holder = "\n".join(_live_holder_records(handle.read())) or "unknown"
            raise LocalOperationLockBusyError(
                "local runtime operation is already running: " + holder
            ) from error
        if canonical_host_lock:
            from quwoquan_ops.cli.lib.output_paths import deployment_target_path
            for target in LOCAL_RUNTIME_TARGETS:
                fence = local_runtime_operation_lock_path(target).with_suffix(".executor.json")
                slot = deployment_target_path(target, "process", "environment-execution", "execution-slot.json")
                if (_read_secure_json_object(fence, label="target executor fence") is not None
                        or _read_secure_json_object(slot, label="environment execution slot") is not None):
                    raise LocalOperationLockBusyError(f"OPS.RUNTIME.executor_reconcile_required: {target} still owns host resources")
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield {
                "path": relpath(lock_path),
                "mode": "exclusive",
                "scope": scope,
                "owner": owner,
                "affectedTargets": list(affected_targets),
            }
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _holder_list_mutation_lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".holders-mutate")


_HOLDER_PID = re.compile(r"\bpid=(?P<pid>[1-9][0-9]*)\b")


def _holder_is_live(record: str) -> bool:
    """记录里的 pid 是否还存在。

    进程被硬杀或异常退出时不会走 `close()`，那条记录就永久留在清单里。此后排他方每次
    被阻塞都会把这条死记录当成持有者报出来，操作员去等一个早已不存在的进程 —— 与清单
    互相覆盖同类，都是把「谁在占用」答错。无法解析出 pid 的记录按存活处理，宁可多报也
    不静默丢弃事实。
    """
    matched = _HOLDER_PID.search(record)
    if matched is None:
        return True
    try:
        os.kill(int(matched.group("pid")), 0)
    except ProcessLookupError:
        return False
    except (OSError, OverflowError, ValueError):
        # 权限错误说明进程存在但不属当前用户；其余读不出来的情形一律按存活处理。
        return True
    return True


def _live_holder_records(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip() and _holder_is_live(line)
    ]


@contextlib.contextmanager
def _holder_list_mutation(path: Path) -> Any:
    """把持有者清单的 read-modify-write 串行化到一个独立排他锁上。

    清单文件本身由持有者以 `LOCK_SH` 共享持有，所以不能靠它自己互斥；而把该 fd 从
    `LOCK_SH` 升级到 `LOCK_EX` 会在两个持有者同时释放时互等成死锁。用独立锁文件既能
    互斥重写，又不触碰持有者们对清单文件的共享锁语义。
    """
    mutation_path = _holder_list_mutation_lock_path(path)
    mutation_path.parent.mkdir(parents=True, exist_ok=True)
    handle = mutation_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            with contextlib.suppress(OSError, ValueError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class LocalRuntimeUseLock:
    """一个共享租约持有者，只写自己那条记录，释放时也只删自己那条。

    共享锁允许多个 UAT/Patrol 同时持有，所以持有者清单必须是追加式的：写入前
    `truncate()` 会把并发持有者的记录抹掉，让排他方在被阻塞时读到空清单或错误的
    持有者，从而把「谁在占用」报错成 unknown。释放时只按自己的记号删除对应行，
    不整体清空，否则同样会误删仍在运行的其他持有者。

    追加写入靠 `O_APPEND` 本身原子，但释放时的删除是 read-modify-write，在共享锁下
    并不互斥：读到重写之间另一持有者追加的记录会落在 `truncate()` 之外被抹掉，两个
    持有者同时释放也会互相覆盖。故重写整段由独立排他锁串行化。
    """

    def __init__(self, path: Path, handle: Any, record: str) -> None:
        self._path = path
        self._handle = handle
        self._record = record
        self._closed = False
        self._host_guard: LocalRuntimeUseLock | None = None

    @property
    def record(self) -> str:
        return self._record

    def fileno(self) -> int:
        return self._handle.fileno()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            with _holder_list_mutation(self._path):
                self._handle.seek(0)
                remaining = [
                    line
                    for line in _live_holder_records(self._handle.read())
                    if line != self._record
                ]
                self._handle.seek(0)
                self._handle.truncate()
                if remaining:
                    self._handle.write("\n".join(remaining) + "\n")
                self._handle.flush()
                os.fsync(self._handle.fileno())
        finally:
            with contextlib.suppress(OSError, ValueError):
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            if self._host_guard is not None:
                self._host_guard.close()


def acquire_local_runtime_use_lock(
    *,
    target: str,
    purpose: str,
    lock_path: Path | None = None,
) -> LocalRuntimeUseLock:
    """按 host shared -> target shared 顺序保护使用者及全局维护边界。"""
    if target not in LOCAL_RUNTIME_TARGETS:
        raise ValueError(f"unknown local runtime target: {target!r}")
    if lock_path is None:
        guard = acquire_local_runtime_use_lock(
            target=target, purpose=purpose,
            lock_path=local_runtime_operation_lock_path(),
        )
        try:
            lease = acquire_local_runtime_use_lock(
                target=target, purpose=purpose,
                lock_path=local_runtime_operation_lock_path(target),
            )
            fence_path = local_runtime_operation_lock_path(target).with_suffix(".executor.json")
            if _read_secure_json_object(fence_path, label="target executor fence") is not None:
                lease.close()
                raise LocalOperationLockBusyError("OPS.RUNTIME.executor_reconcile_required: consumer cannot attach to an unclosed executor")
        except BaseException:
            guard.close()
            raise
        lease._host_guard = guard
        return lease
    path = lock_path
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.seek(0)
        holder = "\n".join(_live_holder_records(handle.read())) or "unknown"
        handle.close()
        raise LocalOperationLockBusyError(
            f"local runtime operation is already running: {holder}"
        ) from error
    record = _owner_record(
        target=target.strip(),
        purpose=purpose.strip(),
        lease=uuid.uuid4().hex,
    )
    # 死持有者的记录顺带回收：硬杀的持有者不会走 close()，其记录会永久留在清单里，
    # 让后来的阻塞诊断指向一个不存在的进程。回收与追加一起串行在同一互斥区内。
    with _holder_list_mutation(path):
        handle.seek(0)
        live = _live_holder_records(handle.read())
        live.append(record)
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(live) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return LocalRuntimeUseLock(path, handle, record)


def local_runtime_lock_holders(
    *, lock_path: Path | None = None
) -> list[dict[str, str]]:
    """Read live host-level runtime holders for status diagnostics."""
    path = lock_path or local_runtime_operation_lock_path()
    try:
        records = _live_holder_records(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        records = []
    except OSError:
        records = []
    return [
        {"path": str(path), "record": record, **parse_holder_record(record)}
        for record in records
    ]


def _tcp_port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except OSError:
        return False


def local_runtime_peer_targets(
    topology: Mapping[str, Any],
    requested_target: str,
) -> tuple[str, ...]:
    """返回与目标共享同一本机资源组的其他 local target。"""
    targets = topology.get("targets")
    if not isinstance(targets, Mapping):
        raise RuntimeError("environment topology targets must be a mapping")
    requested = targets.get(requested_target)
    if not isinstance(requested, Mapping):
        raise RuntimeError(f"unknown local runtime target: {requested_target}")
    resource_group = str(requested.get("localResourceGroup") or "").strip()
    if not resource_group:
        return ()
    return tuple(
        sorted(
            str(candidate_name)
            for candidate_name, candidate in targets.items()
            if candidate_name != requested_target
            and isinstance(candidate, Mapping)
            and str(candidate.get("backend") or "").strip() == "local"
            and str(candidate.get("localResourceGroup") or "").strip()
            == resource_group
        )
    )


def active_conflicting_local_targets(
    topology: Mapping[str, Any],
    requested_target: str,
    *,
    port_probe: PortProbe = _tcp_port_is_open,
) -> tuple[str, ...]:
    """容量共享组不授予跨 target 排他权；端口不作为占用权威。"""
    targets = topology.get("targets")
    if not isinstance(targets, Mapping) or requested_target not in targets:
        raise RuntimeError(f"unknown local runtime target: {requested_target}")
    return ()


def assert_local_runtime_available(
    topology: Mapping[str, Any],
    requested_target: str,
    *,
    port_probe: PortProbe = _tcp_port_is_open,
) -> None:
    conflicts = active_conflicting_local_targets(
        topology,
        requested_target,
        port_probe=port_probe,
    )
    if not conflicts:
        return
    shutdowns = ", ".join(
        f"`python3 quwoquan_ops/cli/stackctl.py down --target {target}`"
        for target in conflicts
    )
    raise RuntimeError(
        f"{requested_target} cannot start while local runtime "
        f"{', '.join(conflicts)} is active; stop it with {shutdowns}"
    )


def assert_no_running_mutable_runtime(
    mutable_attempt: Mapping[str, Any] | None,
    requested_target: str,
) -> None:
    """同一 target 的 mutable test_live 栈与 immutable candidate 栈共享同一
    canonical 端口段；test_live 未释放时启动 candidate 栈只会在 Compose 中途
    以隐晦的 "port is already allocated" 失败并回收现场。receipt 是 test_live
    资源占用的单一真相源：prepared/partial/running 都可能持有容器与端口
    （partial 尤其常见于 dev-session 中断后容器仍在运行），只有 stopped 表示
    资源已确认释放。启动前 fail-fast，把互斥事实与修复动作显式交还调用方。"""
    if not isinstance(mutable_attempt, Mapping):
        return
    status = str(mutable_attempt.get("status") or "")
    if status == "stopped":
        return
    attempt_id = str(mutable_attempt.get("attemptId") or "unknown")
    raise RuntimeError(
        f"{requested_target} mutable test_live runtime is not released "
        f"(status={status or 'unknown'}, attemptId={attempt_id}) and may own "
        "the shared canonical port range; stop the dev-session first with "
        f"`python3 quwoquan_ops/cli/stackctl.py down --target {requested_target}` "
        "before starting the immutable candidate runtime"
    )

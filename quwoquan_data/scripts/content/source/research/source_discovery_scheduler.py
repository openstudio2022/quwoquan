"""来源发现阶段的有界并发调度器。

调度语义由 `REQ-001` 拥有：任一时刻在跑的 worker 数不超过 execution 冻结的
`autoResearchMaxConcurrentWorkers`，单实体失败或超时只终结该实体并立刻把它占用的
额度让给下一个待处理实体，其余实体继续跑到各自终态。每个实体恰好得到一个 typed
终态，规模增长只增加排队长度，不增加同时在跑的 worker 数。

运行时（线程池、时钟、等待原语）整体从外部注入。生产装配注入
`ThreadPoolSchedulerRuntime`；`local_contract` 注入可控 runtime，用虚拟时钟表达
挂起与超时，因此调度断言不依赖真实 sleep 或真实网络。
"""
from __future__ import annotations

import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

# 报告中的耗时与每分钟实体数只是这一次运行的观测事实。字段自带该声明位，
# 读者不需要从数值形态去猜它是不是稳态吞吐或容量结论。
SINGLE_RUN_OBSERVATION = "single_run_observation"


class SourceDiscoveryOutcome(str, Enum):
    """单个实体的来源发现终态闭集。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class EntityTerminalOutcome:
    """一个实体的终态。`report` 只在 `SUCCEEDED` 时在场。"""

    entity_id: str
    outcome: SourceDiscoveryOutcome
    report: Mapping[str, Any] | None
    failure_text: str

    def __post_init__(self) -> None:
        if self.outcome is SourceDiscoveryOutcome.SUCCEEDED:
            if self.report is None:
                raise ValueError(
                    "source discovery succeeded outcome requires an entity report"
                )
            if self.failure_text:
                raise ValueError(
                    "source discovery succeeded outcome must not carry failure text"
                )
        else:
            if self.report is not None:
                raise ValueError(
                    "source discovery non-terminal-success outcome must not carry a report"
                )
            if not self.failure_text:
                raise ValueError(
                    "source discovery failure outcome requires typed failure text"
                )


@dataclass(frozen=True, slots=True)
class StageProgressSnapshot:
    """某一时刻的阶段进度事实，与任何单个实体是否得出终态无关。

    心跳按冻结间隔携带它；某个实体得出终态时也随终态一并交出同一时刻的快照，
    因此进度面上的实测峰值和在跑实体身份始终是被观测到的事实，不是事后补的数。
    """

    candidate_entity_count: int
    terminal_entity_count: int
    running_entity_ids: tuple[str, ...]
    measured_peak_concurrent_workers: int
    elapsed_seconds: float


class SourceDiscoveryStopReason(str, Enum):
    """一次排程为什么停下来的闭集。停下来的原因决定剩余实体怎么被交回。"""

    ALL_ENTITIES_TERMINAL = "all_entities_terminal"
    STAGE_NO_PROGRESS = "stage_no_progress"
    ADMISSION_DEADLINE_REACHED = "admission_deadline_reached"


@dataclass(frozen=True, slots=True)
class SourceDiscoveryRun:
    """一次来源发现排程的闭合结果。

    `abandoned_entity_ids` 只在阶段级无进展 watchdog 触发或冻结准入截止到点时非空：
    那些实体尚未得出终态，交由 resume 续跑，因此它们不出现在 `outcomes` 里，也不被
    记成任何终态。
    """

    frozen_max_concurrent_workers: int
    measured_peak_concurrent_workers: int
    outcomes: tuple[EntityTerminalOutcome, ...]
    elapsed_seconds: float
    stop_reason: SourceDiscoveryStopReason
    abandoned_entity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.stop_reason is SourceDiscoveryStopReason.ALL_ENTITIES_TERMINAL:
            if self.abandoned_entity_ids:
                raise ValueError(
                    "a fully terminal source discovery run cannot abandon entities"
                )
        elif not self.abandoned_entity_ids:
            raise ValueError(
                "an interrupted source discovery run must name the entities it "
                "hands back for resume"
            )

    def outcome_of(self, entity_id: str) -> SourceDiscoveryOutcome:
        for row in self.outcomes:
            if row.entity_id == entity_id:
                return row.outcome
        raise KeyError(entity_id)

    def throughput_facts(
        self,
        *,
        scope_entity_count: int,
        elapsed_seconds: float,
    ) -> dict[str, Any]:
        """阶段报告里的本次运行事实。

        冻结上限与实测峰值是两个词元，各自如实呈现，不互换也不合并成一个 worker 数。
        `factKind` 就是那一处显式声明位：耗时与每分钟实体数只是这一次运行的观测，
        读者不需要从数值形态去猜它是不是稳态吞吐或容量结论。
        """
        elapsed = max(float(elapsed_seconds), 0.001)
        return {
            "factKind": SINGLE_RUN_OBSERVATION,
            "frozenMaxConcurrentWorkers": self.frozen_max_concurrent_workers,
            "peakConcurrentWorkers": self.measured_peak_concurrent_workers,
            "entityCount": scope_entity_count,
            "elapsedSeconds": round(elapsed, 3),
            "entitiesPerMinute": round(scope_entity_count / elapsed * 60.0, 3),
        }


class SchedulerFuture(Protocol):
    """调度器对在跑工作单元的最小依赖面。"""

    def cancel(self) -> bool: ...

    def result(self) -> Mapping[str, Any]: ...


class SchedulerRuntime(Protocol):
    """线程池、时钟与等待原语的注入面。"""

    def monotonic(self) -> float: ...

    def submit(self, entity_id: str) -> SchedulerFuture: ...

    def wait_first_completed(
        self,
        futures: Iterable[SchedulerFuture],
        *,
        timeout: float,
    ) -> tuple[set[SchedulerFuture], set[SchedulerFuture]]: ...

    def shutdown(self, *, cancel_futures: bool) -> None: ...


class ThreadPoolSchedulerRuntime:
    """生产装配：固定大小线程池 + 真实单调时钟。

    池大小等于冻结上限，因此实测峰值与冻结上限同源。线程不可抢占：某实体超时后调度器
    账上的额度立刻释放并交给下一个待处理实体，但那条工作线程要等自身返回才回到池里，
    所以下一个实体的实际起跑时刻受制于线程返回。这是运行时事实，不是调度语义。
    """

    def __init__(
        self,
        run_entity: Callable[[str], Mapping[str, Any]],
        *,
        max_workers: int,
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError(
                "source discovery runtime requires a positive frozen worker ceiling"
            )
        self._run_entity = run_entity
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def monotonic(self) -> float:
        return time.monotonic()

    def submit(self, entity_id: str) -> SchedulerFuture:
        return self._executor.submit(self._run_entity, entity_id)

    def wait_first_completed(
        self,
        futures: Iterable[SchedulerFuture],
        *,
        timeout: float,
    ) -> tuple[set[SchedulerFuture], set[SchedulerFuture]]:
        return wait(set(futures), timeout=timeout, return_when=FIRST_COMPLETED)

    def shutdown(self, *, cancel_futures: bool) -> None:
        self._executor.shutdown(wait=not cancel_futures, cancel_futures=cancel_futures)


def _positive(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"source discovery scheduler requires a positive {field}")
    return float(value)


def run_bounded_source_discovery(
    entity_ids: Sequence[str],
    *,
    frozen_max_concurrent_workers: int,
    entity_timeout_seconds: float,
    heartbeat_interval_seconds: float,
    runtime: SchedulerRuntime,
    on_heartbeat: Callable[[StageProgressSnapshot], None],
    on_terminal: Callable[[EntityTerminalOutcome, StageProgressSnapshot], None]
    | None = None,
    stage_no_progress_timeout_seconds: float | None = None,
    admission_deadline_seconds: float | None = None,
    fatal_exceptions: tuple[type[BaseException], ...] = (),
) -> SourceDiscoveryRun:
    """把全部实体一次排程到冻结额度上，逐实体收敛到 typed 终态。

    `admission_deadline_seconds` 是冻结批次截止时刻在本 runtime 单调时钟上的读数：
    到点后不再准入新实体，已在跑的实体继续跑到各自终态，未准入的实体原样交回。
    """
    if (
        isinstance(frozen_max_concurrent_workers, bool)
        or not isinstance(frozen_max_concurrent_workers, int)
        or frozen_max_concurrent_workers < 1
    ):
        raise ValueError(
            "source discovery concurrency ceiling must come from the frozen "
            "executionPolicy as a positive integer"
        )
    entity_timeout_seconds = _positive(entity_timeout_seconds, "entity timeout")
    heartbeat_interval_seconds = _positive(
        heartbeat_interval_seconds,
        "heartbeat interval",
    )
    ordered = [str(entity_id).strip() for entity_id in entity_ids]
    if any(not entity_id for entity_id in ordered):
        raise ValueError("source discovery target set contains an empty entity id")
    if len(set(ordered)) != len(ordered):
        raise ValueError("source discovery target set contains a duplicate entity id")

    if stage_no_progress_timeout_seconds is not None:
        stage_no_progress_timeout_seconds = _positive(
            stage_no_progress_timeout_seconds,
            "stage no-progress budget",
        )

    pending = deque(ordered)
    running: dict[Any, tuple[str, float]] = {}
    outcomes: list[EntityTerminalOutcome] = []
    measured_peak = 0
    started = runtime.monotonic()
    last_heartbeat: float | None = None
    last_progress_at = started
    abandoned: list[str] = []
    stop_reason = SourceDiscoveryStopReason.ALL_ENTITIES_TERMINAL

    def snapshot(now: float) -> StageProgressSnapshot:
        return StageProgressSnapshot(
            candidate_entity_count=len(ordered),
            terminal_entity_count=len(outcomes),
            running_entity_ids=tuple(
                entity_id for entity_id, _started_at in running.values()
            ),
            measured_peak_concurrent_workers=measured_peak,
            elapsed_seconds=max(now - started, 0.0),
        )

    def record(outcome: EntityTerminalOutcome) -> None:
        nonlocal last_progress_at
        outcomes.append(outcome)
        last_progress_at = runtime.monotonic()
        if on_terminal is not None:
            on_terminal(outcome, snapshot(last_progress_at))

    def beat(now: float) -> None:
        nonlocal last_heartbeat
        on_heartbeat(snapshot(now))
        last_heartbeat = now

    try:
        while pending or running:
            now = runtime.monotonic()
            # 超时只终结当前这个实体；额度在同一轮就回到池子里。
            for future, (entity_id, started_at) in list(running.items()):
                if now - started_at >= entity_timeout_seconds:
                    future.cancel()
                    del running[future]
                    record(
                        EntityTerminalOutcome(
                            entity_id=entity_id,
                            outcome=SourceDiscoveryOutcome.TIMED_OUT,
                            report=None,
                            failure_text=(
                                f"{entity_id}: source discovery exceeded the frozen "
                                f"per-entity budget of {entity_timeout_seconds:g}s"
                            ),
                        )
                    )
            if (
                pending
                and admission_deadline_seconds is not None
                and now >= admission_deadline_seconds
            ):
                # 冻结批次截止：停止准入，未准入实体原样交回；在跑的继续跑到终态。
                stop_reason = SourceDiscoveryStopReason.ADMISSION_DEADLINE_REACHED
                abandoned.extend(pending)
                pending.clear()
            while pending and len(running) < frozen_max_concurrent_workers:
                entity_id = pending.popleft()
                running[runtime.submit(entity_id)] = (entity_id, runtime.monotonic())
            measured_peak = max(measured_peak, len(running))
            now = runtime.monotonic()
            if last_heartbeat is None or now - last_heartbeat >= heartbeat_interval_seconds:
                beat(now)
            if not running:
                continue
            deadlines = [
                (now if last_heartbeat is None else last_heartbeat)
                + heartbeat_interval_seconds,
                min(
                    started_at + entity_timeout_seconds
                    for _entity_id, started_at in running.values()
                ),
            ]
            if stage_no_progress_timeout_seconds is not None:
                deadlines.append(last_progress_at + stage_no_progress_timeout_seconds)
            if pending and admission_deadline_seconds is not None:
                deadlines.append(admission_deadline_seconds)
            budget = max(0.0, min(deadlines) - now)
            done, _not_done = runtime.wait_first_completed(
                set(running),
                timeout=budget,
            )
            for future in done:
                if future not in running:
                    continue
                entity_id, _started_at = running.pop(future)
                try:
                    report = future.result()
                except fatal_exceptions:
                    raise
                except Exception as exc:  # noqa: BLE001 - 任一实体故障只终结该实体
                    record(
                        EntityTerminalOutcome(
                            entity_id=entity_id,
                            outcome=SourceDiscoveryOutcome.FAILED,
                            report=None,
                            failure_text=(
                                f"{entity_id}: source discovery worker raised "
                                f"{type(exc).__name__}: {exc}"
                            ),
                        )
                    )
                    continue
                record(
                    EntityTerminalOutcome(
                        entity_id=entity_id,
                        outcome=SourceDiscoveryOutcome.SUCCEEDED,
                        report=report,
                        failure_text="",
                    )
                )
            if (
                stage_no_progress_timeout_seconds is not None
                and runtime.monotonic() - last_progress_at
                >= stage_no_progress_timeout_seconds
            ):
                # 阶段级无进展：这些实体尚未得出终态，交回队列续跑而不是判终态。
                stop_reason = SourceDiscoveryStopReason.STAGE_NO_PROGRESS
                for future, (entity_id, _started_at) in running.items():
                    future.cancel()
                    abandoned.append(entity_id)
                abandoned.extend(pending)
                running.clear()
                pending.clear()
                break
    finally:
        runtime.shutdown(cancel_futures=bool(running) or bool(abandoned))

    return SourceDiscoveryRun(
        frozen_max_concurrent_workers=frozen_max_concurrent_workers,
        measured_peak_concurrent_workers=measured_peak,
        outcomes=tuple(outcomes),
        elapsed_seconds=max(runtime.monotonic() - started, 0.0),
        stop_reason=stop_reason,
        abandoned_entity_ids=tuple(abandoned),
    )


__all__ = [
    "SINGLE_RUN_OBSERVATION",
    "EntityTerminalOutcome",
    "SchedulerFuture",
    "SchedulerRuntime",
    "SourceDiscoveryOutcome",
    "SourceDiscoveryRun",
    "SourceDiscoveryStopReason",
    "StageProgressSnapshot",
    "ThreadPoolSchedulerRuntime",
    "run_bounded_source_discovery",
]

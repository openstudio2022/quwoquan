"""来源发现调度器的可控 runtime：虚拟时钟 + 可控 future。

这是注入面 `SchedulerRuntime` 的测试实现，用来在没有真实 sleep、没有真实线程调度、
没有真实网络的前提下表达挂起、失败、超时与额度接管。它同时充当并发探针：任何时刻
在跑的工作单元数都被记录，因此「峰值不超过冻结上限」是被观测到的事实。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class WorkerScript:
    """一个实体在可控 runtime 上的剧本。"""

    __slots__ = ("duration_seconds", "raises")

    def __init__(
        self,
        *,
        duration_seconds: float | None,
        raises: BaseException | None = None,
    ) -> None:
        # duration 缺席表示这个实体永不自行返回，只能由 per-entity 超时终结。
        self.duration_seconds = duration_seconds
        self.raises = raises


def completes(duration_seconds: float) -> WorkerScript:
    return WorkerScript(duration_seconds=duration_seconds)


def fails(duration_seconds: float, message: str) -> WorkerScript:
    return WorkerScript(duration_seconds=duration_seconds, raises=RuntimeError(message))


def hangs() -> WorkerScript:
    return WorkerScript(duration_seconds=None)


@dataclass(slots=True, eq=False)
class ControlledFuture:
    """可控 future：完成时刻由剧本给出，取消只影响未完成的工作单元。"""

    entity_id: str
    finishes_at: float | None
    raises: BaseException | None
    cancelled: bool = False

    def cancel(self) -> bool:
        if self.finishes_at is None or self.cancelled:
            self.cancelled = True
            return True
        return False

    def result(self) -> Mapping[str, Any]:
        if self.raises is not None:
            raise self.raises
        return {"updated": [{"entityId": self.entity_id}]}


class ControlledRuntime:
    """虚拟时钟 + 可控 future 的注入式 runtime。"""

    def __init__(self, scripts: Mapping[str, WorkerScript], *, started_at: float = 1_000.0) -> None:
        self._scripts = dict(scripts)
        self._now = started_at
        self.started_at = started_at
        self.live: set[str] = set()
        self.observed_live_counts: list[int] = []
        self.submission_order: list[str] = []
        self.submission_instants: dict[str, float] = {}
        self.shutdown_cancelled_futures: bool | None = None

    def monotonic(self) -> float:
        return self._now

    def submit(self, entity_id: str) -> ControlledFuture:
        script = self._scripts[entity_id]
        self.submission_order.append(entity_id)
        self.submission_instants[entity_id] = self._now
        self.live.add(entity_id)
        self.observed_live_counts.append(len(self.live))
        return ControlledFuture(
            entity_id=entity_id,
            finishes_at=(
                None
                if script.duration_seconds is None
                else self._now + script.duration_seconds
            ),
            raises=script.raises,
        )

    def wait_first_completed(
        self,
        futures: Iterable[ControlledFuture],
        *,
        timeout: float,
    ) -> tuple[set[ControlledFuture], set[ControlledFuture]]:
        pending = set(futures)
        finishable = [
            future
            for future in pending
            if future.finishes_at is not None and not future.cancelled
        ]
        deadline = self._now + timeout
        if not finishable:
            self._now = deadline
            return set(), pending
        earliest = min(future.finishes_at for future in finishable)
        if earliest > deadline:
            self._now = deadline
            return set(), pending
        self._now = earliest
        done = {future for future in finishable if future.finishes_at == earliest}
        for future in done:
            self.live.discard(future.entity_id)
        return done, pending - done

    def shutdown(self, *, cancel_futures: bool) -> None:
        self.shutdown_cancelled_futures = cancel_futures

    def release_slot_on_timeout(self, entity_id: str) -> None:
        """超时终结的实体在生产 runtime 上不可抢占，这里显式表达额度已还回调度器。"""
        self.live.discard(entity_id)


__all__ = [
    "ControlledFuture",
    "ControlledRuntime",
    "WorkerScript",
    "completes",
    "fails",
    "hangs",
]

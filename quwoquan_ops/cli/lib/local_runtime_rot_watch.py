"""本地运行期腐烂的状态跃迁观测。

启动前判一次健康，只能证明那一刻可用。真实故障里 mongodb 在启动 5 小时后
才因磁盘写满退出，而当时唯一被信任的信号（startup receipt）仍是 `running`，
于是「环境可用」这个结论在无人复验的情况下保持了 20 小时。

本模块把运行期健康表达为一个只读状态机：每次观测都重新查容器现况与容量
水位，只有状态**发生跃迁**时才产出事件。这样既不刷屏，也不会让降级静默。

规格归属：`observability-and-alerting/local-runtime-rot-notification`。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from quwoquan_ops.cli.lib.common import utc_now
from quwoquan_ops.cli.lib.local_runtime_capacity import (
    local_runtime_capacity_evidence,
)
from quwoquan_ops.cli.lib.runtime_container_liveness import (
    ComposeProjectAbsent,
    verify_running_receipt_liveness,
)

HEALTHY = "healthy"
DEGRADED = "degraded"
UNAVAILABLE = "unavailable"
UNOBSERVED = "unobserved"

# 严重程度序，用于把容器与容量两路观测合并成一个会话级状态。
_SEVERITY = {HEALTHY: 0, UNOBSERVED: 1, DEGRADED: 2, UNAVAILABLE: 3}


@dataclass(frozen=True)
class RotObservation:
    """一次运行期观测的合并结论。"""

    status: str
    details: tuple[str, ...] = ()

    @property
    def degraded(self) -> bool:
        return self.status in {DEGRADED, UNAVAILABLE}


@dataclass(frozen=True)
class RotTransition:
    """一次状态跃迁。只在状态真的变了的时候产生。"""

    at: str
    from_status: str
    to_status: str
    details: tuple[str, ...] = ()

    @property
    def recovered(self) -> bool:
        return self.to_status == HEALTHY

    def describe(self) -> str:
        head = (
            f"local runtime recovered to {self.to_status} "
            f"(was {self.from_status})"
            if self.recovered
            else f"local runtime degraded from {self.from_status} "
            f"to {self.to_status}"
        )
        if not self.details:
            return head
        return head + ": " + "; ".join(self.details)

    def as_evidence(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "from": self.from_status,
            "to": self.to_status,
            "details": list(self.details),
        }


def observe_local_runtime(
    *,
    target: Mapping[str, Any],
    startup: Mapping[str, Any] | None,
    runner: Any,
) -> RotObservation:
    """合并必需容器现况与容量水位，得到一个运行期状态。"""
    details: list[str] = []
    statuses = [HEALTHY]

    try:
        liveness = verify_running_receipt_liveness(startup, runner=runner)
    except ComposeProjectAbsent:
        liveness = None
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        liveness = None
        statuses.append(UNOBSERVED)
        details.append(f"container liveness is unverifiable: {exc}")
    if liveness is not None and liveness.status != HEALTHY:
        statuses.append(liveness.status)
        details.extend(liveness.issues())

    capacity = local_runtime_capacity_evidence(target, runner=runner)
    if capacity["issues"]:
        statuses.append(DEGRADED)
        details.extend(capacity["issues"])
    elif capacity["warnings"]:
        statuses.append(UNOBSERVED)
        details.extend(capacity["warnings"])

    status = max(statuses, key=lambda item: _SEVERITY.get(item, 0))
    return RotObservation(status=status, details=tuple(details))


@dataclass
class LocalRuntimeRotWatch:
    """运行期状态跃迁观测器。

    `status` 的初始值由调用方给出：dev-session 在 preflight 已经证明过健康，
    因此以 `healthy` 起步，随后的任何降级都是真实跃迁而不是首次观测噪音。
    """

    target: Mapping[str, Any]
    startup: Mapping[str, Any] | None
    runner: Any
    status: str = HEALTHY
    transitions: list[RotTransition] = field(default_factory=list)

    def observe(self) -> RotTransition | None:
        """复验一次；状态未变时返回 `None`（在场为空，不是失败）。"""
        observation = observe_local_runtime(
            target=self.target,
            startup=self.startup,
            runner=self.runner,
        )
        if observation.status == self.status:
            return None
        transition = RotTransition(
            at=utc_now(),
            from_status=self.status,
            to_status=observation.status,
            details=observation.details,
        )
        self.status = observation.status
        self.transitions.append(transition)
        return transition

    def as_evidence(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "transitions": [item.as_evidence() for item in self.transitions],
        }

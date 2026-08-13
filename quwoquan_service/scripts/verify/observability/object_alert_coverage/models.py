"""ContractGraph 派生的契约模型与报告数据类。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import _number_label


class ContractInputError(RuntimeError):
    """ContractGraph 或 domain.yaml 无法作为唯一真相源使用。"""


def _number(value: Any, field: str, operation_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractInputError(f"{operation_id} 缺少数值 {field}")
    return float(value)


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    domain: str
    service: str
    object_name: str
    method: str
    path_template: str
    commercial_status: str
    block_reason: str
    metric: str
    latency_p95_ms: float
    availability_percent: float

    @property
    def ready(self) -> bool:
        return self.commercial_status == "ready"

    def record_labels(self) -> dict[str, str]:
        return {
            "service": self.service,
            "operation": self.operation_id,
            "contract_metric": self.metric,
            "commercial_status": self.commercial_status,
            "slo_latency_p95_ms": _number_label(self.latency_p95_ms),
            "slo_availability_percent": _number_label(self.availability_percent),
        }


@dataclass(frozen=True)
class RuleExpression:
    source: Path
    name: str
    expression: str
    record: str = ""
    alert: str = ""
    labels: dict[str, str] | None = None


OBJECT_SURFACE_READY = "ready"
OBJECT_SURFACE_PENDING = "pending_commercial"
OBJECT_SURFACE_RUNTIME_ONLY = "runtime_surface_only"
OBJECT_SURFACE_NONE = "no_contract_surface"


@dataclass(frozen=True)
class ObjectSurface:
    object_id: str
    domain: str
    kind: str
    operations: int
    ready_operations: int
    runtime_entrypoints: tuple[str, ...]
    runtime_metrics: tuple[str, ...]

    @property
    def classification(self) -> str:
        if self.ready_operations:
            return OBJECT_SURFACE_READY
        if self.operations:
            return OBJECT_SURFACE_PENDING
        if self.runtime_entrypoints:
            return OBJECT_SURFACE_RUNTIME_ONLY
        return OBJECT_SURFACE_NONE


@dataclass(frozen=True)
class DomainReport:
    domain: str
    service: str
    operations: int
    ready: int
    blocked_by_gap: tuple[tuple[str, int], ...]
    objects: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class VerificationReport:
    operations: int
    ready_operations: int
    domains: tuple[DomainReport, ...]
    object_surfaces: tuple[ObjectSurface, ...]
    issues: tuple[str, ...]
    declared_metrics: int = 0
    emitted_metrics: tuple[str, ...] = ()

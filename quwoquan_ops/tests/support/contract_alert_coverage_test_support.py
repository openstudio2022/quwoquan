"""按 ContractGraph 声明的 SLO 断言某个 operation 的告警覆盖。

HTTP operation 的可用性与 P95 口径由 `verify_object_alert_coverage.py --write` 与
`verify_contract_alert_overlay.py --write` 从 ContractGraph 派生；等价的手写 PromQL 会被
`verify_contract_alert_overlay.py` 判为可派生残留并 BLOCK。业务侧可观测性测试因此不再断言
手写告警名，而是断言「契约声明的 SLO 档位确有派生告警承载」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quwoquan_service.scripts.verify.observability import (
    verify_object_alert_coverage as coverage,
)


ROOT = Path(__file__).resolve().parents[3]
ALERTS_ROOT = ROOT / "quwoquan_ops/observability/monitoring/alerts"
READY_COVERAGE_ALERTS = ALERTS_ROOT / "contract_object_coverage.yaml"
PENDING_COVERAGE_ALERTS = ALERTS_ROOT / "contract_pending_commercial_coverage.yaml"


def contract_operation(operation_id: str) -> coverage.OperationContract:
    """ContractGraph 里该 operation 的契约事实；缺席即断言失败。"""

    domain_services = coverage.load_domain_services()
    for operation in coverage.load_operations(domain_services=domain_services):
        if operation.operation_id == operation_id:
            return operation
    raise AssertionError(f"{operation_id} 不在 ContractGraph 内")


def _rules(path: Path) -> list[dict[str, Any]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        rule
        for group in document["groups"] or []
        for rule in group.get("rules") or []
        if isinstance(rule, dict) and "alert" in rule
    ]


def _coverage_rules(operation: coverage.OperationContract) -> list[dict[str, Any]]:
    path = READY_COVERAGE_ALERTS if operation.ready else PENDING_COVERAGE_ALERTS
    return [
        rule
        for rule in _rules(path)
        if rule.get("labels", {}).get("domain") == operation.domain
    ]


def _selects_operation(
    expression: str, operation: coverage.OperationContract, tier_selector: str
) -> bool:
    if f'service="{operation.service}"' not in expression:
        return False
    if f'commercial_status="{operation.commercial_status}"' not in expression:
        return False
    if operation.ready:
        # ready 覆盖按 SLO 档位分组，用域通配 selector 收拢同档位的全部 operation。
        return tier_selector in expression
    # 待商用覆盖显式枚举 operation id，不假设 metric 前缀。
    return operation.operation_id.replace(".", "\\\\.") in expression


def latency_p95_alert(operation_id: str) -> dict[str, Any]:
    """承载该 operation `slo.latencyP95Milliseconds` 的派生告警。"""

    operation = contract_operation(operation_id)
    threshold = operation.latency_p95_ms / 1000
    tier_selector = f'slo_latency_p95_ms="{operation.latency_p95_ms:g}"'
    for rule in _coverage_rules(operation):
        expression = rule["expr"]
        if "histogram_quantile(0.95" not in "".join(expression.split()):
            continue
        if f"> {threshold:g}" not in expression:
            continue
        if _selects_operation(expression, operation, tier_selector):
            return rule
    raise AssertionError(
        f"{operation_id} 的 P95 SLO（{operation.latency_p95_ms:g}ms）没有派生告警承载"
    )


def availability_alert(operation_id: str) -> dict[str, Any]:
    """承载该 operation `slo.availabilityPercent` 5xx 错误预算的派生告警。"""

    operation = contract_operation(operation_id)
    budget = round((100.0 - operation.availability_percent) / 100.0, 6)
    tier_selector = f'slo_availability_percent="{operation.availability_percent:g}"'
    for rule in _coverage_rules(operation):
        expression = rule["expr"]
        if 'status=~"5.."' not in expression or f"> {budget:g}" not in expression:
            continue
        if _selects_operation(expression, operation, tier_selector):
            return rule
    raise AssertionError(
        f"{operation_id} 的可用性 SLO（{operation.availability_percent:g}%）没有派生告警承载"
    )

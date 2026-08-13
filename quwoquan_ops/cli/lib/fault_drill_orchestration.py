"""受控故障演练编排：闭集故障 profile 的注入、观测与恢复。

故障 profile 是闭集枚举（bandwidth / disconnect / error / latency）；注入面只允许
环境边缘（当前经受控容器编排实现 disconnect），production `lib/**` 与服务装配
保持零注入开关。演练只允许 alpha/beta/gamma 本地 target，Prod 在注入前拒绝。

尚未在环境层实现的 profile 返回结构化 unavailable，不合成伪成功；告警命中
readback 在无 Prometheus/Alertmanager 的 target 上如实标注 unavailable
（缺口由 alert-drill-closure OPEN-001 登记）。

spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/alert-drill-closure/spec.md#gwt-001
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import utc_now, write_json
from quwoquan_ops.cli.lib.local_controlled_edge_fault import (
    LOCAL_TARGETS,
    ControlledEdgeFault,
    begin_controlled_edge_fault,
)

DRILL_SCHEMA = "quwoquan_ops.fault_drill.receipt"
FAULT_PROFILES = ("bandwidth", "disconnect", "error", "latency")
IMPLEMENTED_PROFILES = frozenset({"disconnect"})

FaultFactory = Callable[[str], ControlledEdgeFault]


def run_drill(
    *,
    env_name: str,
    target_name: str,
    profile: str,
    hold_seconds: float,
    report_dir: Path,
    fault_factory: FaultFactory = begin_controlled_edge_fault,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if env_name == "prod" or target_name.startswith("prod"):
        raise ValueError("drill refuses prod targets; prod only keeps post-rollout soak observation")
    if profile not in FAULT_PROFILES:
        raise ValueError(
            f"fault profile must be one of {', '.join(FAULT_PROFILES)}; got {profile!r}"
        )
    if target_name not in LOCAL_TARGETS:
        raise ValueError("drill accepts only alpha-local/beta-local/gamma-local targets")
    if hold_seconds < 0 or hold_seconds > 300:
        raise ValueError("drill hold seconds must be within 0..300")

    report_dir.mkdir(parents=True, exist_ok=True)
    if profile not in IMPLEMENTED_PROFILES:
        payload: dict[str, Any] = {
            "schema": DRILL_SCHEMA,
            "status": "unavailable",
            "profile": profile,
            "environment": env_name,
            "target": target_name,
            "generatedAt": utc_now(),
            "reason": (
                f"fault profile {profile!r} is declared in the harness contract closed set "
                "but has no environment-edge implementation for this target yet; "
                "only 'disconnect' is currently injectable"
            ),
        }
        write_json(report_dir / "receipt.json", payload)
        return payload

    fault = fault_factory(target_name)
    try:
        injected_at = fault.started_at
        fault_confirmed = not fault.health_probe(fault.health_url)
        fault_confirmed_at = utc_now()
        if hold_seconds:
            sleep(hold_seconds)
        restore_receipt = fault.restore()
    except Exception:
        if not fault.restored:
            fault.restore()
        raise
    recovered = fault.health_probe(fault.health_url)
    payload = {
        "schema": DRILL_SCHEMA,
        "status": "restored" if recovered else "restore_unhealthy",
        "profile": profile,
        "environment": env_name,
        "target": target_name,
        "generatedAt": utc_now(),
        "injectedAt": injected_at,
        "faultConfirmedAt": fault_confirmed_at,
        "restoredAt": restore_receipt.get("restoredAt"),
        "holdSeconds": hold_seconds,
        "healthEvidence": {
            "healthUrl": fault.health_url,
            "unavailableDuringFault": fault_confirmed,
            "healthyAfterRestore": recovered,
        },
        "edgeFaultReceipt": restore_receipt,
        "alertReadback": {
            "status": "unavailable",
            "reason": (
                "no prometheus/alertmanager stack is bound to this target; "
                "alert-hit readback tracked by alert-drill-closure OPEN-001"
            ),
        },
    }
    write_json(report_dir / "receipt.json", payload)
    if not recovered:
        raise RuntimeError(
            "drill restore did not regain API health; receipt written to "
            + str(report_dir / "receipt.json")
        )
    return payload

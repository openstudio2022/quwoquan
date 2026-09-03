"""App Debug 预检的 OTP 公共读回与运行容器现况证据。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

_OTP_DELIVERY_READINESS_OPERATION_ID = (
    "user.authentication_challenge.GetOtpDeliveryReadiness"
)


def _read_otp_delivery_readiness(
    *,
    api_base_url: str,
) -> dict[str, Any]:
    """Fresh, secret-free readback through the canonical public operation."""
    import quwoquan_ops.cli.stackctl as _stackctl

    from quwoquan_ops.cli.lib.test_data.operations import ContractOperationCatalog

    operation = ContractOperationCatalog().require(
        _OTP_DELIVERY_READINESS_OPERATION_ID
    )
    if operation.method != "GET":
        raise RuntimeError("canonical OTP delivery readiness operation is not GET")
    if not api_base_url:
        raise RuntimeError("canonical OTP delivery readiness has no API base URL")
    path = operation.path()
    ok, status_code, body, _content_type = _stackctl.fetch_url(
        api_base_url.rstrip("/") + path,
        timeout=1.2,
        retry_attempts=1,
        retry_sleep_seconds=0.0,
    )
    if not ok or status_code != 200:
        raise RuntimeError(
            "canonical OTP delivery readiness HTTP is not ready: "
            + str(status_code or "network_error")
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "canonical OTP delivery readiness returned non-JSON"
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {
        "availability",
        "retryAfterSeconds",
    }:
        raise RuntimeError(
            "canonical OTP delivery readiness payload shape is invalid"
        )
    availability = payload.get("availability")
    retry_after_seconds = payload.get("retryAfterSeconds")
    if not isinstance(availability, str) or type(retry_after_seconds) is not int:
        raise RuntimeError(
            "canonical OTP delivery readiness payload types are invalid"
        )
    evidence = {
        "operationId": operation.operation_id,
        "path": path,
        "statusCode": status_code,
        "availability": availability,
        "retryAfterSeconds": retry_after_seconds,
        "ready": availability == "ready" and retry_after_seconds == 0,
    }
    return evidence


def _runtime_container_liveness_evidence(
    startup: Mapping[str, Any],
) -> dict[str, Any]:
    """复验 running receipt 声明的容器现况，供编译安装前阻断使用。"""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.runtime_container_liveness import (
        RUNTIME_DEPENDENCY_BLOCKER,
        ComposeProjectAbsent,
        verify_running_receipt_liveness,
    )

    empty = {
        "status": "not_applicable",
        "composeProject": str(startup.get("composeProject") or ""),
        "blocker": "",
        "containers": [],
        "issues": [],
        "warnings": [],
    }
    try:
        report = verify_running_receipt_liveness(startup, runner=_stackctl.run)
    except ComposeProjectAbsent:
        # receipt 合法性归 startup receipt 契约（composeProject 是必填非空），
        # 这里不重复判定，只如实记为未命中，避免建立第二真相源。
        return empty
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            **empty,
            "status": "unavailable",
            "blocker": RUNTIME_DEPENDENCY_BLOCKER,
            "issues": [f"runtime container liveness is unverifiable: {exc}"],
        }
    if report is None:
        return empty
    return {
        "status": report.status,
        "composeProject": report.compose_project,
        "blocker": report.blocker,
        "containers": [
            {
                "service": item.service or item.name,
                "state": item.state,
                "health": item.health,
                "exitCode": item.exit_code,
                "live": item.is_live,
                "completedTask": item.is_completed_task,
            }
            for item in report.containers
        ],
        "issues": report.issues(),
        "warnings": [],
    }

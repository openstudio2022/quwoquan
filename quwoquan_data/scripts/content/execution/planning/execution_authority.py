"""Mutually exclusive execution authority for campaign envelopes.

`bounded_explicit` 只授权 M1–M10 explicit 单 worker 小批执行，限制全部来自
受版本控制的 policy 文件，且永不作为 capacity qualification 证据；
`governed_calibration` 携带受治理容量标定，是 M100+ 的唯一路径。两种模式
互斥 oneOf，执行层容量投影由 authority 确定性派生，不存在旧
capacityCalibration 双读。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths

BOUNDED_MODE = "bounded_explicit"
GOVERNED_MODE = "governed_calibration"
BOUNDED_POLICY_REF = (
    "quwoquan_data/control_plane/_shared/catalogs/"
    "bounded_execution_authority_policy.json"
)
_BOUNDED_POLICY_SCHEMA = "quwoquan_data.bounded_execution_authority_policy"


class ExecutionAuthorityError(ValueError):
    """One typed blocked reason for an invalid or out-of-bounds authority."""


def load_bounded_authority_policy(
    *, repo_root: Path | None = None
) -> dict[str, Any]:
    """Load and validate the versioned bounded-authority policy with its digest."""
    root = (repo_root or paths.REPO_ROOT).resolve()
    path = root / BOUNDED_POLICY_REF
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_UNREADABLE: "
            f"{BOUNDED_POLICY_REF}: {exc}"
        ) from exc
    try:
        policy = json.loads(raw)
    except ValueError as exc:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            f"{BOUNDED_POLICY_REF} is not valid JSON"
        ) from exc
    if not isinstance(policy, Mapping):
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            "policy document must be an object"
        )
    if str(policy.get("schema")) != _BOUNDED_POLICY_SCHEMA:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            f"policy schema must be {_BOUNDED_POLICY_SCHEMA}"
        )
    policy_id = str(policy.get("policyId") or "").strip()
    if not policy_id:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            "policyId is missing"
        )
    if str(policy.get("workloadMode")) != "explicit":
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            "bounded authority only covers explicit workloads"
        )
    if policy.get("maxWorkers") != 1:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            "bounded authority must pin maxWorkers to 1"
        )
    values: dict[str, int] = {}
    for field in (
        "maxTotalObjects",
        "objectWallClockSeconds",
        "completionGraceSeconds",
        "sourceDiscoveryHeartbeatIntervalSeconds",
        "sourceDiscoveryHeartbeatStaleAfterSeconds",
    ):
        value = policy.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ExecutionAuthorityError(
                "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
                f"{field} must be a positive integer"
            )
        values[field] = value
    if (
        values["sourceDiscoveryHeartbeatStaleAfterSeconds"]
        <= values["sourceDiscoveryHeartbeatIntervalSeconds"]
    ):
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            "sourceDiscoveryHeartbeatStaleAfterSeconds must exceed "
            "sourceDiscoveryHeartbeatIntervalSeconds"
        )
    if values["maxTotalObjects"] > 10:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_POLICY_INVALID: "
            "bounded authority never exceeds ten objects"
        )
    return {
        "policyId": policy_id,
        "policyRef": BOUNDED_POLICY_REF,
        "policyDigest": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "maxWorkers": 1,
        **values,
    }


def build_bounded_execution_authority(
    *,
    total_objects: int,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Freeze one bounded authority after proving the workload fits the policy."""
    if isinstance(total_objects, bool) or not isinstance(total_objects, int):
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_OUT_OF_BOUNDS: "
            "total object count must be an integer"
        )
    policy = load_bounded_authority_policy(repo_root=repo_root)
    if total_objects < 1 or total_objects > policy["maxTotalObjects"]:
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_OUT_OF_BOUNDS: "
            f"bounded authority covers 1..{policy['maxTotalObjects']} objects, "
            f"requested {total_objects}"
        )
    return {
        "mode": BOUNDED_MODE,
        "policyId": policy["policyId"],
        "policyRef": policy["policyRef"],
        "policyDigest": policy["policyDigest"],
        "maxTotalObjects": policy["maxTotalObjects"],
        "maxWorkers": 1,
        "objectWallClockSeconds": policy["objectWallClockSeconds"],
        "completionGraceSeconds": policy["completionGraceSeconds"],
        "sourceDiscoveryHeartbeatIntervalSeconds": policy[
            "sourceDiscoveryHeartbeatIntervalSeconds"
        ],
        "sourceDiscoveryHeartbeatStaleAfterSeconds": policy[
            "sourceDiscoveryHeartbeatStaleAfterSeconds"
        ],
    }


def governed_execution_authority(
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Wrap one governed calibration source binding as the exclusive authority."""
    return {"mode": GOVERNED_MODE, "calibration": dict(calibration)}


def assert_execution_authority(value: object) -> dict[str, Any]:
    """Validate one authority document against the mutually exclusive schema."""
    from core.schema import assert_valid

    if not isinstance(value, Mapping):
        raise ExecutionAuthorityError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_INVALID: "
            "execution authority must be an object"
        )
    authority = dict(value)
    assert_valid(
        authority,
        "execution",
        "execution_authority",
        label="execution authority",
    )
    return authority


def capacity_binding_from_authority(
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Project the execution-layer capacity source binding from one authority.

    governed 模式原样解包 calibration；bounded 模式由 policy 事实确定性派生
    单 worker 绑定，calibrationId/ref/digest 直接指向 policy 文件本身，可回溯
    且不冒充任何 governed receipt。
    """
    mode = str(authority.get("mode") or "")
    if mode == GOVERNED_MODE:
        calibration = authority.get("calibration")
        if not isinstance(calibration, Mapping):
            raise ExecutionAuthorityError(
                "GATE_BLOCK DATA.EXECUTION.AUTHORITY_INVALID: "
                "governed authority calibration is missing"
            )
        return dict(calibration)
    if mode == BOUNDED_MODE:
        return {
            "calibrationId": str(authority["policyId"]),
            "calibrationReceiptRef": str(authority["policyRef"]),
            "calibrationReceiptDigest": str(authority["policyDigest"]),
            "applicability": {"hostClass": "any", "providerTier": "any"},
            "frozenCapacity": {
                "autoResearchMaxConcurrentWorkers": 1,
                "fleetMaxConcurrentWorkers": 1,
                "objectWallClockSeconds": int(
                    authority["objectWallClockSeconds"]
                ),
                "completionGraceSeconds": int(
                    authority["completionGraceSeconds"]
                ),
            },
            "frozenLiveness": {
                "sourceDiscoveryHeartbeatIntervalSeconds": int(
                    authority["sourceDiscoveryHeartbeatIntervalSeconds"]
                ),
                "sourceDiscoveryHeartbeatStaleAfterSeconds": int(
                    authority["sourceDiscoveryHeartbeatStaleAfterSeconds"]
                ),
            },
        }
    raise ExecutionAuthorityError(
        "GATE_BLOCK DATA.EXECUTION.AUTHORITY_INVALID: "
        f"unknown execution authority mode {mode!r}"
    )


__all__ = [
    "BOUNDED_MODE",
    "BOUNDED_POLICY_REF",
    "GOVERNED_MODE",
    "ExecutionAuthorityError",
    "assert_execution_authority",
    "build_bounded_execution_authority",
    "capacity_binding_from_authority",
    "governed_execution_authority",
    "load_bounded_authority_policy",
]

#!/usr/bin/env python3
"""Verify App→cloud real-launch closed-loop evidence for one exact merge candidate.

owner spec: specs/feature-tree/runtime/runtime-test-pyramid/three-layer-evidence/spec.md#req-005
本 gate 只消费三项结果证据（受管真实启动回执、真实 Service api_integration
CaseResult、Journey App→Service→readback），全部必须绑定同一 exact merge
candidate digest；analyzer/widget/编译/替身 API 属结构或本地证据，不得计入。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True

ERROR_CODE_BLOCKED = "EVIDENCE.APP_CLOUD_CLOSURE_BLOCKED"
ERROR_CODE_CONTRACT = "EVIDENCE.APP_CLOUD_CONTRACT_INVALID"

BLOCKER_LAUNCH_RECEIPT_MISSING = "APP_LAUNCH_RECEIPT_MISSING"
BLOCKER_REAL_SERVICE_CASE_MISSING = "REAL_SERVICE_CASE_RESULT_MISSING"
BLOCKER_REQUIRED_CASE_SKIPPED = "REQUIRED_CASE_SKIPPED"
BLOCKER_REQUIRED_CASE_FAILED = "REQUIRED_CASE_FAILED"
BLOCKER_JOURNEY_READBACK_MISSING = "JOURNEY_READBACK_MISSING"
BLOCKER_CANDIDATE_DIGEST_MISMATCH = "CANDIDATE_DIGEST_MISMATCH"

# 顺序即输出顺序，保持确定性。
ALL_BLOCKERS = (
    BLOCKER_LAUNCH_RECEIPT_MISSING,
    BLOCKER_REAL_SERVICE_CASE_MISSING,
    BLOCKER_REQUIRED_CASE_SKIPPED,
    BLOCKER_REQUIRED_CASE_FAILED,
    BLOCKER_JOURNEY_READBACK_MISSING,
    BLOCKER_CANDIDATE_DIGEST_MISMATCH,
)

# gate 只对需要真实集成的档位有意义；no_live 候选不得调用本 gate 冒充闭环证据。
APPLICABLE_DEPTHS = ("alpha_integration", "abg_release_sensitive")
DEVICE_CLASSES = ("real_device", "simulator")
REAL_SERVICE_TRANSPORT = "real_service"
CASE_STATUSES = ("passed", "failed", "error")
RECOVERY_BY_BLOCKER = {
    BLOCKER_LAUNCH_RECEIPT_MISSING: "collect_managed_launch_receipt",
    BLOCKER_REAL_SERVICE_CASE_MISSING: "run_required_real_service_cases",
    BLOCKER_REQUIRED_CASE_SKIPPED: "rerun_required_cases_without_skip",
    BLOCKER_REQUIRED_CASE_FAILED: "fix_and_rerun_required_cases",
    BLOCKER_JOURNEY_READBACK_MISSING: "run_journey_readback",
    BLOCKER_CANDIDATE_DIGEST_MISMATCH: "regenerate_exact_candidate_evidence",
}

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ClosureContractError(ValueError):
    """Fail-closed malformed evidence bundle."""


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ClosureContractError(f"{label} 必须为对象")
    return value


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ClosureContractError(f"{label} 必须为 sha256:64hex candidate digest")
    return value


def _require_count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ClosureContractError(f"{label} 必须为非负整数")
    return value


def _require_nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClosureContractError(f"{label} 必须为非空字符串")
    return value


def _require_unique_strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ClosureContractError(f"{label} 必须为非空列表")
    items = tuple(
        _require_nonempty_string(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(items)) != len(items):
        raise ClosureContractError(f"{label} 不得重复")
    return items


def evaluate_app_cloud_closure(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """评估一个 exact merge candidate 的端云真启闭环证据，返回 typed 结果。"""

    _require_mapping(bundle, "evidence bundle")
    candidate_digest = _require_digest(bundle.get("candidate_digest"), "candidate_digest")
    depth = bundle.get("integration_depth")
    if depth not in APPLICABLE_DEPTHS:
        raise ClosureContractError(
            "integration_depth 必须为 typed impact 派生的 alpha_integration 或 abg_release_sensitive"
        )

    blockers: set[str] = set()
    digest_mismatch = False

    def bound_digest(evidence: Mapping[str, Any], label: str) -> bool:
        nonlocal digest_mismatch
        digest = _require_digest(evidence.get("candidate_digest"), f"{label}.candidate_digest")
        if digest != candidate_digest:
            digest_mismatch = True
            return False
        return True

    receipt = bundle.get("launch_receipt")
    promotable = False
    if receipt is None:
        blockers.add(BLOCKER_LAUNCH_RECEIPT_MISSING)
    else:
        receipt = _require_mapping(receipt, "launch_receipt")
        device_class = receipt.get("device_class")
        if device_class not in DEVICE_CLASSES:
            raise ClosureContractError("launch_receipt.device_class 必须为 real_device 或 simulator")
        closed = (
            receipt.get("status") == "launched"
            and receipt.get("runtimeHealthStatus") == "healthy"
            and receipt.get("configurationState") == "complete"
        )
        if not closed or not bound_digest(receipt, "launch_receipt"):
            blockers.add(BLOCKER_LAUNCH_RECEIPT_MISSING)
        else:
            # 模拟器证据可支撑集成合入，但必须标记 nonPromotable（REQ-005）。
            promotable = device_class == "real_device"

    required_case_ids = _require_unique_strings(
        bundle.get("required_case_ids"), "required_case_ids"
    )
    cases = bundle.get("api_integration_cases")
    if not isinstance(cases, list):
        raise ClosureContractError("api_integration_cases 必须为列表")
    real_cases_by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw_case in enumerate(cases):
        case = _require_mapping(raw_case, f"api_integration_cases[{index}]")
        transport = _require_nonempty_string(
            case.get("transport"), f"api_integration_cases[{index}].transport"
        )
        if transport != REAL_SERVICE_TRANSPORT:
            # analyzer/widget/进程内替身等结构证据不计入闭环。
            continue
        case_id = _require_nonempty_string(
            case.get("case_id"), f"api_integration_cases[{index}].case_id"
        )
        status = case.get("status")
        if status not in CASE_STATUSES:
            raise ClosureContractError(
                f"api_integration_cases[{index}].status 必须为 {CASE_STATUSES}"
            )
        if case_id in real_cases_by_id:
            raise ClosureContractError(f"real service CaseResult 重复: {case_id}")
        if not bound_digest(case, f"api_integration_cases[{index}]"):
            continue
        real_cases_by_id[case_id] = case

    missing_required = [
        case_id for case_id in required_case_ids if case_id not in real_cases_by_id
    ]
    if missing_required:
        blockers.add(BLOCKER_REAL_SERVICE_CASE_MISSING)
    for case_id in required_case_ids:
        case = real_cases_by_id.get(case_id)
        if case is None:
            continue
        executed = _require_count(case.get("executed"), f"{case_id}.executed")
        failed = _require_count(case.get("failed"), f"{case_id}.failed")
        skipped = _require_count(case.get("skipped"), f"{case_id}.skipped")
        if executed == 0 or skipped > 0:
            blockers.add(BLOCKER_REQUIRED_CASE_SKIPPED)
        if case.get("status") != "passed" or failed > 0:
            blockers.add(BLOCKER_REQUIRED_CASE_FAILED)

    required_journey_ids = _require_unique_strings(
        bundle.get("required_journey_ids"), "required_journey_ids"
    )
    readbacks = bundle.get("journey_readbacks")
    if not isinstance(readbacks, list):
        raise ClosureContractError("journey_readbacks 必须为列表")
    seen_journey_ids: set[str] = set()
    verified_journeys_by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw_readback in enumerate(readbacks):
        readback = _require_mapping(raw_readback, f"journey_readbacks[{index}]")
        journey_id = _require_nonempty_string(
            readback.get("journey_id"), f"journey_readbacks[{index}].journey_id"
        )
        if journey_id in seen_journey_ids:
            raise ClosureContractError(f"Journey readback 重复: {journey_id}")
        seen_journey_ids.add(journey_id)
        if readback.get("readback_verified") is not True:
            continue
        if not bound_digest(readback, f"journey_readbacks[{index}]"):
            continue
        verified_journeys_by_id[journey_id] = readback
    required_journey_id_set = set(required_journey_ids)
    if (
        seen_journey_ids != required_journey_id_set
        or set(verified_journeys_by_id) != required_journey_id_set
    ):
        blockers.add(BLOCKER_JOURNEY_READBACK_MISSING)

    if digest_mismatch:
        blockers.add(BLOCKER_CANDIDATE_DIGEST_MISMATCH)

    ordered = [blocker for blocker in ALL_BLOCKERS if blocker in blockers]
    return {
        "status": "blocked" if ordered else "pass",
        "candidate_digest": candidate_digest,
        "integration_depth": depth,
        "blockers": ordered,
        "promotable": bool(promotable and not ordered),
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            f"[app-cloud-closure] GATE_BLOCK: code={ERROR_CODE_CONTRACT} "
            "detail=usage: verify_app_cloud_closure.py <evidence-bundle.json> "
            "recovery=repair_evidence_bundle_contract",
            file=sys.stderr,
        )
        return 1
    try:
        bundle = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        result = evaluate_app_cloud_closure(bundle)
    except (OSError, json.JSONDecodeError, ClosureContractError) as error:
        detail = " ".join(str(error).split()) or type(error).__name__
        print(
            f"[app-cloud-closure] GATE_BLOCK: code={ERROR_CODE_CONTRACT} "
            f"detail={detail} recovery=repair_evidence_bundle_contract",
            file=sys.stderr,
        )
        return 1
    if result["status"] != "pass":
        for blocker in result["blockers"]:
            print(
                f"[app-cloud-closure] GATE_BLOCK: code={ERROR_CODE_BLOCKED} "
                f"blocker={blocker} candidate={result['candidate_digest']} "
                f"recovery={RECOVERY_BY_BLOCKER[blocker]}",
                file=sys.stderr,
            )
        return 1
    promotion = "promotable" if result["promotable"] else "nonPromotable"
    print(
        f"[app-cloud-closure] OK: closed-loop evidence verified "
        f"candidate={result['candidate_digest']} promotion={promotion}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

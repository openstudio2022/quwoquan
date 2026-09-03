#!/usr/bin/env python3
"""Read-only canonical handoff freshness consumer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import evidence_runner  # noqa: E402
from lib import handoff_store  # noqa: E402
import review_dispatch  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    canonical_bytes_sha256,
    contract_schema_version,
    contract_section,
    validate_declared_fields,
    validate_required_fields,
)
from lib.human_agent_delivery.runtime_bridge import (  # noqa: E402
    HumanDecisionBridgeError,
    project_runtime_decision,
)
from lib.evidence_fingerprint import (  # noqa: E402
    canonical_digest,
    normalize_repo_relative_path,
    snapshot_path,
    validate_evidence_fingerprint,
    workspace_digests,
)

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"
GENERATOR_PATH = "quwoquan_ops/cli/handoff_manifest.py"


class HandoffConsumerError(ValueError):
    pass


def _load_json_ref(raw: str, *, label: str) -> tuple[str, dict[str, Any]]:
    relative = normalize_repo_relative_path(raw, ROOT)
    path = ROOT / relative
    if path.is_symlink():
        raise HandoffConsumerError(f"{label} ref 不得为 symlink：{relative}")
    if not path.is_file():
        raise HandoffConsumerError(f"{label} 不存在：{relative}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffConsumerError(f"{label} 无法读取：{relative}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HandoffConsumerError(f"{label} 必须为 JSON object：{relative}")
    return relative, payload


def _registry() -> dict[str, Any]:
    value = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise HandoffConsumerError("canonical workflow registry 必须为 mapping")
    return value


def _same_receipt(actual: dict[str, Any], expected: dict[str, Any], *, label: str) -> None:
    for field in ("ref", "digest", "digest_payload"):
        if actual[field] != expected[field]:
            raise HandoffConsumerError(
                f"REVIEW.FINGERPRINT_CHANGED: {label} {field} 已 stale"
            )


def _plan_evidence(plan: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in plan.get("evidence") or []:
        evidence_id = str(raw.get("id") or "")
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        results.append(
            {
                "id": evidence_id,
                "command": str(raw["command"]),
                "command_digest": str(raw["command_digest"]),
                "required": bool(raw["required"]),
                "timeout_seconds": int(raw["timeout_seconds"]),
            }
        )
    return results


def validate_named_evidence_ref_payload(
    receipt: dict[str, Any],
    *,
    plan: dict[str, Any],
    registry: dict[str, Any],
    label: str = "named evidence receipt",
    require_admission: bool = False,
) -> dict[str, Any]:
    evidence_runner.validate_named_evidence_receipt(receipt)
    terminal = receipt["terminal"]
    if terminal != {
        "status": "PASS",
        "code": "EVIDENCE.PASSED",
        "failed_evidence": None,
    }:
        raise HandoffConsumerError(f"named evidence receipt 非 PASS terminal：{label}")
    plan_receipt = validate_evidence_fingerprint(plan["fingerprint_receipt"])
    if (
        receipt["plan_fingerprint_ref"] != plan_receipt["ref"]
        or receipt["plan_fingerprint_digest"] != plan_receipt["digest"]
    ):
        raise HandoffConsumerError(f"named evidence receipt plan identity 不匹配：{label}")
    if require_admission:
        evidence_runner.require_admission_eligible(receipt, label=label)
    evidence = _plan_evidence(plan)
    if not evidence:
        raise HandoffConsumerError("handoff 不接受零命令 named evidence receipt")
    expected_ids = [item["id"] for item in evidence]
    actual_ids = [item["id"] for item in receipt["evidence"]]
    if actual_ids != expected_ids:
        raise HandoffConsumerError(
            f"named evidence receipt 未完整投影 plan evidence：{label}"
        )
    by_id = {item["id"]: item for item in evidence}
    for result in receipt["evidence"]:
        planned = by_id[result["id"]]
        for field in (
            "command",
            "command_digest",
            "required",
            "timeout_seconds",
        ):
            if result[field] != planned[field]:
                raise HandoffConsumerError(
                    f"named evidence receipt {result['id']} {field} 与 plan 不一致"
                )
        if result["exit_code"] != 0:
            raise HandoffConsumerError(
                f"named evidence receipt {result['id']} exit_code 非零"
            )
    actual_execution = validate_evidence_fingerprint(receipt["execution_fingerprint"])
    metadata = actual_execution.get("captured_metadata") or {}
    plan_input_ref = metadata.get("plan_input_ref")
    plan_bytes_sha256 = metadata.get("plan_bytes_sha256")
    if not isinstance(plan_input_ref, str) or not plan_input_ref or not isinstance(plan_bytes_sha256, str):
        raise HandoffConsumerError(f"named evidence receipt 缺 exact plan bytes identity：{label}")
    current_execution = evidence_runner._fingerprint(
        plan=plan,
        evidence=evidence,
        results=[],
        phase="execution_input",
        registry=registry,
        source=dict(receipt["source"]),
        plan_bytes_sha256=plan_bytes_sha256,
        plan_input_ref=plan_input_ref,
    )
    _same_receipt(actual_execution, current_execution, label=label)
    actual_result = validate_evidence_fingerprint(receipt["result_fingerprint"])
    current_result = evidence_runner._fingerprint(
        plan=plan,
        evidence=evidence,
        results=receipt["evidence"],
        phase="execution_result",
        registry=registry,
        source=dict(receipt["source"]),
        plan_bytes_sha256=plan_bytes_sha256,
        plan_input_ref=plan_input_ref,
    )
    _same_receipt(actual_result, current_result, label=label)
    return receipt


def validate_named_evidence_ref(
    raw_ref: str,
    *,
    plan: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    relative, receipt = _load_json_ref(raw_ref, label="named evidence receipt")
    if (ROOT / relative).is_symlink():
        raise HandoffConsumerError(
            f"named evidence receipt ref 不得为 symlink：{relative}"
        )
    validate_named_evidence_ref_payload(
        receipt, plan=plan, registry=registry, label=relative, require_admission=True
    )
    return relative, receipt



def named_evidence_identity_from_raw(
    receipt_ref: str, raw: bytes, receipt: dict[str, Any]
) -> dict[str, Any]:
    execution = validate_evidence_fingerprint(receipt["execution_fingerprint"])
    result = validate_evidence_fingerprint(receipt["result_fingerprint"])
    identity = {
        "receipt_ref": receipt_ref,
        "canonical_bytes_sha256": "sha256:" + __import__("hashlib").sha256(raw).hexdigest(),
        "run_id": receipt["run_id"],
        "generation_id": receipt["generation_id"],
        "evidence_class": receipt["evidence_class"],
        "admission_eligible": receipt["admission_eligible"],
        "plan_fingerprint_ref": receipt["plan_fingerprint_ref"],
        "plan_fingerprint_digest": receipt["plan_fingerprint_digest"],
        "execution_fingerprint_ref": execution["ref"],
        "execution_fingerprint_digest": execution["digest"],
        "result_fingerprint_ref": result["ref"],
        "result_fingerprint_digest": result["digest"],
        "finished_at": receipt["finished_at"],
    }
    validate_declared_fields(
        identity, "review_consolidation", "evidence_identity_fields"
    )
    return identity


def named_evidence_identity(
    receipt_ref: str, receipt: dict[str, Any]
) -> dict[str, Any]:
    return named_evidence_identity_from_raw(
        receipt_ref, (ROOT / receipt_ref).read_bytes(), receipt
    )


def validate_review_result_ref_payload(
    result_ref: str,
    result_raw: bytes,
    result: dict[str, Any],
    *,
    plan: dict[str, Any],
    evidence_identities: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_required_fields(result, "review_result")
    if result.get("schema_version") != contract_schema_version("review_result"):
        raise HandoffConsumerError("review result schema_version 非法")
    if result.get("status") not in contract_section("review_result")["statuses"]:
        raise HandoffConsumerError("review result status 非法")
    if not evidence_identities:
        raise HandoffConsumerError("review result 缺 exact named evidence identity")
    matches = [
        identity
        for identity in evidence_identities
        if result.get("evidence_receipt_ref") == identity["receipt_ref"]
    ]
    if len(matches) != 1:
        raise HandoffConsumerError("review result evidence receipt ref mismatch")
    evidence = matches[0]
    comparisons = {
        "plan_fingerprint_ref": evidence["plan_fingerprint_ref"],
        "plan_fingerprint_digest": evidence["plan_fingerprint_digest"],
        "evidence_receipt_canonical_bytes_sha256": evidence["canonical_bytes_sha256"],
        "evidence_run_id": evidence["run_id"],
        "evidence_generation_id": evidence["generation_id"],
        "execution_fingerprint_ref": evidence["execution_fingerprint_ref"],
        "execution_fingerprint_digest": evidence["execution_fingerprint_digest"],
        "result_fingerprint_ref": evidence["result_fingerprint_ref"],
        "result_fingerprint_digest": evidence["result_fingerprint_digest"],
    }
    for field, expected in comparisons.items():
        if result.get(field) != expected:
            raise HandoffConsumerError(f"review result {field} 与 exact evidence 不一致")
    started = str(result.get("started_at") or "")
    finished = str(result.get("finished_at") or "")
    evidence_finished = str(evidence["finished_at"])
    if not started or not finished or started > finished:
        raise HandoffConsumerError("review result started_at/finished_at 非法")
    try:
        from datetime import datetime

        started_value = datetime.fromisoformat(started.replace("Z", "+00:00"))
        evidence_finished_value = datetime.fromisoformat(
            evidence_finished.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise HandoffConsumerError("review/evidence timestamp 非 ISO-8601") from exc
    if started_value < evidence_finished_value:
        raise HandoffConsumerError("review result pre-evidence")
    assembled_count = result.get("assembled_input_byte_count")
    assembled_digest = result.get("assembled_input_digest")
    assembled_compression = result.get("assembled_input_compression")
    if (
        not isinstance(assembled_count, int)
        or isinstance(assembled_count, bool)
        or assembled_count <= 0
        or not isinstance(assembled_digest, str)
        or not __import__("re").fullmatch(r"sha256:[0-9a-f]{64}", assembled_digest)
        or not isinstance(assembled_compression, dict)
    ):
        raise HandoffConsumerError("review result assembled input receipt metadata 非法")
    identity = {
        "result_ref": result_ref,
        "canonical_bytes_sha256": "sha256:" + __import__("hashlib").sha256(
            result_raw
        ).hexdigest(),
        "role": result["role"],
        "assembled_input_byte_count": assembled_count,
        "assembled_input_digest": assembled_digest,
        "assembled_input_compression": assembled_compression,
    }
    validate_declared_fields(
        identity, "review_consolidation", "reviewer_result_identity_fields"
    )
    return identity


def validate_review_result_ref(
    raw_ref: str, *, plan: dict[str, Any], evidence_identities: list[dict[str, Any]]
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    relative, result = _load_json_ref(raw_ref, label="review result")
    raw = (ROOT / relative).read_bytes()
    identity = validate_review_result_ref_payload(
        relative, raw, result, plan=plan, evidence_identities=evidence_identities
    )
    return relative, result, identity

def build_handoff_fingerprint(
    identity: dict[str, Any],
    *,
    evidence_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    managed_paths = [
        *identity["artifacts"],
        *([identity["human_decision_ref"]] if identity.get("human_decision_ref") else []),
        identity["owner_identity_ref"],
        identity["candidate_evidence_ref"],
        identity["review_plan_ref"],
        *identity["evidence_receipt_refs"],
        *identity["reviewer_result_refs"],
        identity["review_consolidation_ref"],
    ]
    head = review_dispatch._head_sha()
    return evidence_runner.build_evidence_fingerprint(
        {
            "git": {"head_sha": head, "merge_base_sha": review_dispatch._merge_base_sha()},
            "workspace": workspace_digests(managed_paths, repo_root=ROOT),
            "assets": {
                "canonical_assets_digest": canonical_digest(identity),
                "review_assets_digest": canonical_digest(
                    [snapshot_path(path, repo_root=ROOT) for path in managed_paths]
                ),
            },
            "execution": {
                "commands_digest": canonical_digest(
                    [
                        {
                            "id": item["id"],
                            "command_digest": item["command_digest"],
                            "exit_code": item["exit_code"],
                        }
                        for receipt in evidence_receipts
                        for item in receipt["evidence"]
                    ]
                ),
                "toolchain_digest": canonical_digest(
                    {
                        "python": list(sys.version_info[:3]),
                        "handoff_schema": contract_schema_version("handoff_manifest"),
                    }
                ),
                "provider_digest": canonical_digest("canonical-named-evidence-receipts"),
                "generator_digest": canonical_digest(
                    snapshot_path(GENERATOR_PATH, repo_root=ROOT)
                ),
            },
        },
        captured_at=max(str(receipt["finished_at"]) for receipt in evidence_receipts),
        captured_by="handoff_manifest",
        captured_metadata={"consumer": "handoff_manifest"},
    )


def validate_handoff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_required_fields(payload, "handoff_manifest")
    if payload["schema_version"] != contract_schema_version("handoff_manifest"):
        raise HandoffConsumerError("handoff manifest schema_version 非法")
    contract = contract_section("handoff_manifest")
    if any(trigger not in contract["triggers"] for trigger in payload["triggers"]):
        raise HandoffConsumerError("handoff manifest trigger 非法")
    human_projection = payload["human_decision_projection"]
    if not isinstance(human_projection, dict):
        raise HandoffConsumerError("handoff human_decision_projection 必须为 mapping")
    validate_declared_fields(
        human_projection, "handoff_manifest", "human_decision_projection_fields"
    )
    try:
        current_human_projection = project_runtime_decision(
            target_kind="handoff",
            admission_class=str(human_projection["admission_class"]),
            human_decision_ref=payload["human_decision_ref"],
        )
    except HumanDecisionBridgeError as exc:
        raise HandoffConsumerError(f"{exc.code}: {exc.detail}") from exc
    if human_projection != current_human_projection:
        raise HandoffConsumerError("handoff human decision projection/ref drifted")
    if current_human_projection["blocks_execution"]:
        raise HandoffConsumerError(
            f"{current_human_projection['terminal']}: human decision 阻止 handoff"
        )
    registry = _registry()
    if payload["downstream"] not in (registry.get("workflows") or {}):
        raise HandoffConsumerError(
            f"handoff downstream 不属于 canonical workflow registry：{payload['downstream']}"
        )
    if "owner_manifest_ref" in payload:
        raise HandoffConsumerError("IDENTITY.MIGRATION_REQUIRED: owner_manifest_ref 已退役")
    owner_identity_ref = normalize_repo_relative_path(payload["owner_identity_ref"], ROOT)
    candidate_evidence_ref = normalize_repo_relative_path(payload["candidate_evidence_ref"], ROOT)
    plan_ref, plan = _load_json_ref(payload["review_plan_ref"], label="review plan")
    if owner_identity_ref != (plan.get("owner_identity") or {}).get("ref") or candidate_evidence_ref != (plan.get("candidate_evidence_identity") or {}).get("ref"):
        raise HandoffConsumerError("handoff owner/candidate refs 与 plan 不一致")
    try:
        review_dispatch.validate_current_review_plan(plan, registry, phase="handoff")
    except review_dispatch.ReviewDispatchError as exc:
        raise HandoffConsumerError(f"{exc.code}: {exc.message}") from exc
    artifacts: list[str] = []
    for raw in payload["artifacts"]:
        relative = normalize_repo_relative_path(raw, ROOT)
        snapshot = snapshot_path(relative, repo_root=ROOT)
        if not snapshot["exists"]:
            raise HandoffConsumerError(f"handoff artifact 不存在：{relative}")
        artifacts.append(relative)
    evidence_refs: list[str] = []
    receipts: list[dict[str, Any]] = []
    for raw in payload["evidence_receipt_refs"]:
        relative, receipt = validate_named_evidence_ref(
            raw, plan=plan, registry=registry
        )
        evidence_refs.append(relative)
        receipts.append(receipt)
    reviewer_result_refs: list[str] = []
    reviewer_results: list[dict[str, Any]] = []
    reviewer_identities: list[dict[str, Any]] = []
    evidence_identities = [
        named_evidence_identity(ref, receipt)
        for ref, receipt in zip(evidence_refs, receipts)
    ]
    for raw in payload["reviewer_result_refs"]:
        relative, result, identity_item = validate_review_result_ref(
            raw, plan=plan, evidence_identities=evidence_identities
        )
        reviewer_result_refs.append(relative)
        reviewer_results.append(result)
        reviewer_identities.append(identity_item)
    consolidation_ref, consolidation = _load_json_ref(
        payload["review_consolidation_ref"], label="review consolidation"
    )
    try:
        import review_consolidator

        review_consolidator.validate_exact_consolidation(
            consolidation,
            plan=plan,
            evidence_pairs=list(zip(evidence_refs, receipts)),
            reviewer_pairs=list(zip(reviewer_result_refs, reviewer_results)),
            registry=registry,
            exact_bytes_by_ref={
                ref: (ROOT / ref).read_bytes()
                for ref in [*evidence_refs, *reviewer_result_refs]
            },
        )
    except (TypeError, ValueError) as exc:
        raise HandoffConsumerError(str(exc)) from exc
    identity = {
        "intent": payload["intent"],
        "triggers": payload["triggers"],
        "artifacts": artifacts,
        "pending_dispositions": payload["pending_dispositions"],
        "downstream": payload["downstream"],
        "human_decision_ref": payload["human_decision_ref"],
        "human_decision_projection": human_projection,
        "owner_identity_ref": owner_identity_ref,
        "candidate_evidence_ref": candidate_evidence_ref,
        "review_plan_ref": plan_ref,
        "evidence_receipt_refs": evidence_refs,
        "reviewer_result_refs": reviewer_result_refs,
        "review_consolidation_ref": consolidation_ref,
        "recovery_token": payload["recovery_token"],
    }
    current = build_handoff_fingerprint(identity, evidence_receipts=receipts)
    actual = validate_evidence_fingerprint(payload["fingerprint_receipt"])
    _same_receipt(actual, current, label="handoff manifest")
    return payload


def validate_published_bytes(
    handoff_ref: str, exact_bytes: bytes, *, validate_current: bool = True
) -> dict[str, Any]:
    """Validate explicit portable bytes; optionally prove current-workspace freshness."""

    try:
        payload = handoff_store.validate_ref_bytes(handoff_ref, exact_bytes)
    except handoff_store.HandoffStoreError as exc:
        raise HandoffConsumerError(str(exc)) from exc
    return validate_handoff_payload(payload) if validate_current else payload


def consume_ref(handoff_ref: str) -> dict[str, Any]:
    """Consume one explicit authoritative ref; latest scanning and env truth are forbidden."""

    try:
        exact_bytes = handoff_store.read(handoff_ref, repo_root=ROOT)
    except handoff_store.HandoffStoreError as exc:
        raise HandoffConsumerError(str(exc)) from exc
    return validate_published_bytes(handoff_ref, exact_bytes)


def consume(path: Path) -> dict[str, Any]:
    raise HandoffConsumerError(
        "HANDOFF.EXPLICIT_REF_REQUIRED: 请使用 consume_ref(handoff_ref)"
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-ref", required=True)
    args = parser.parse_args(argv)
    try:
        consume_ref(args.handoff_ref)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[handoff_consumer] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(args.handoff_ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

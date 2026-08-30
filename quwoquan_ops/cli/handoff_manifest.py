#!/usr/bin/env python3
"""Produce the sole canonical on-demand handoff manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import handoff_consumer  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    contract_section,
)
from lib.evidence_fingerprint import validate_evidence_fingerprint  # noqa: E402

OUTPUT_ROOT = ROOT / ".qwq_output/env/repo/runs/handoff"


class HandoffManifestError(ValueError):
    pass


def _validated_run_id(value: object) -> str:
    run_id = str(value or "")
    if not run_id or "/" in run_id or run_id in {".", ".."}:
        raise HandoffManifestError("run_id 必须为单一安全 path segment")
    return run_id


def _pending(data: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, str]]:
    pending = data.get("pending_dispositions") or []
    if not isinstance(pending, list):
        raise HandoffManifestError("pending_dispositions 必须为列表")
    allowed = set(contract["pending_dispositions"])
    normalized: list[dict[str, str]] = []
    for item in pending:
        if not isinstance(item, dict) or item.get("disposition") not in allowed:
            raise HandoffManifestError(
                "pending disposition 必须属于 open/out_of_scope/downstream"
            )
        if item.get("generalization") not in {"孤例", "一类"}:
            raise HandoffManifestError("pending generalization 必须为孤例或一类")
        normalized_item = {
            "summary": str(item.get("summary") or ""),
            "disposition": str(item["disposition"]),
            "target": str(item.get("target") or ""),
            "generalization": str(item["generalization"]),
        }
        if not normalized_item["summary"] or not normalized_item["target"]:
            raise HandoffManifestError("pending summary/target 必须为非空字符串")
        normalized.append(normalized_item)
    return normalized


def produce(data: dict[str, Any]) -> Path | str:
    contract = contract_section("handoff_manifest")
    triggers = data.get("triggers") or []
    if not isinstance(triggers, list) or not all(
        isinstance(item, str) and item for item in triggers
    ):
        raise HandoffManifestError("triggers 必须为字符串列表")
    unknown = sorted(set(triggers) - set(contract["triggers"]))
    if unknown:
        raise HandoffManifestError(f"未知 handoff trigger：{unknown}")
    if not triggers:
        return str(contract["no_persistent_handoff"])

    run_id = _validated_run_id(data.get("run_id"))
    intent = str(data.get("intent") or "")
    downstream = str(data.get("downstream") or "")
    owner_manifest_ref = str(data.get("owner_manifest_ref") or "")
    review_plan_ref = str(data.get("review_plan_ref") or "")
    review_consolidation_ref = str(data.get("review_consolidation_ref") or "")
    recovery_token = str(data.get("recovery_token") or "")
    expected_recovery = contract_section("evidence_fingerprint")["handoff"][
        "recovery_token"
    ]
    if not intent or not downstream or not owner_manifest_ref or not review_plan_ref or not review_consolidation_ref:
        raise HandoffManifestError(
            "intent、downstream、owner_manifest_ref、review_plan_ref 与 review_consolidation_ref 必须为非空字符串"
        )
    if recovery_token != expected_recovery:
        raise HandoffManifestError(f"recovery_token 必须为 {expected_recovery}")

    artifacts = data.get("artifacts") or []
    evidence_refs = data.get("evidence_receipt_refs") or []
    reviewer_result_refs = data.get("reviewer_result_refs") or []
    if not isinstance(artifacts, list) or not artifacts or not all(
        isinstance(item, str) and item for item in artifacts
    ):
        raise HandoffManifestError("触发持久交接时 artifacts 必须为非空字符串列表")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(
        isinstance(item, str) and item for item in evidence_refs
    ):
        raise HandoffManifestError(
            "触发持久交接时 evidence_receipt_refs 必须为非空字符串列表"
        )
    if not isinstance(reviewer_result_refs, list) or not reviewer_result_refs or not all(
        isinstance(item, str) and item for item in reviewer_result_refs
    ):
        raise HandoffManifestError(
            "触发持久交接时 reviewer_result_refs 必须为非空字符串列表"
        )
    pending = _pending(data, contract)

    registry = handoff_consumer._registry()
    if downstream not in (registry.get("workflows") or {}):
        raise HandoffManifestError(
            f"downstream 不属于 canonical workflow registry：{downstream}"
        )
    try:
        plan_ref, plan = handoff_consumer._load_json_ref(
            review_plan_ref, label="review plan"
        )
    except (TypeError, ValueError) as exc:
        raise HandoffManifestError(str(exc)) from exc
    try:
        handoff_consumer.review_dispatch.validate_current_review_plan(
            plan, registry, phase="handoff"
        )
    except handoff_consumer.review_dispatch.ReviewDispatchError as exc:
        raise HandoffManifestError(f"{exc.code}: {exc.message}") from exc

    normalized_owner_manifest_ref = handoff_consumer.normalize_repo_relative_path(
        owner_manifest_ref, ROOT
    )
    if normalized_owner_manifest_ref != plan["owner_manifest_identity"]["ref"]:
        raise HandoffManifestError("owner_manifest_ref 与 plan identity 不一致")
    normalized_artifacts: list[str] = []
    for raw in artifacts:
        relative = handoff_consumer.normalize_repo_relative_path(raw, ROOT)
        snapshot = handoff_consumer.snapshot_path(relative, repo_root=ROOT)
        if not snapshot["exists"]:
            raise HandoffManifestError(f"handoff artifact 不存在：{relative}")
        normalized_artifacts.append(relative)
    normalized_refs: list[str] = []
    receipts: list[dict[str, Any]] = []
    for raw in evidence_refs:
        try:
            relative, receipt = handoff_consumer.validate_named_evidence_ref(
                raw, plan=plan, registry=registry
            )
        except (TypeError, ValueError) as exc:
            raise HandoffManifestError(str(exc)) from exc
        normalized_refs.append(relative)
        receipts.append(receipt)

    evidence_identities = [
        handoff_consumer.named_evidence_identity(ref, receipt)
        for ref, receipt in zip(normalized_refs, receipts)
    ]
    normalized_result_refs: list[str] = []
    reviewer_results: list[dict[str, Any]] = []
    reviewer_identities: list[dict[str, Any]] = []
    for raw in reviewer_result_refs:
        try:
            relative, result, result_identity = handoff_consumer.validate_review_result_ref(
                raw, plan=plan, evidence_identities=evidence_identities
            )
        except (TypeError, ValueError) as exc:
            raise HandoffManifestError(str(exc)) from exc
        normalized_result_refs.append(relative)
        reviewer_results.append(result)
        reviewer_identities.append(result_identity)
    try:
        consolidation_ref, consolidation = handoff_consumer._load_json_ref(
            review_consolidation_ref, label="review consolidation"
        )
    except (TypeError, ValueError) as exc:
        raise HandoffManifestError(str(exc)) from exc
    if consolidation.get("terminal", {}).get("status") != "PASS":
        raise HandoffManifestError("review consolidation 非 PASS")
    if (
        consolidation.get("plan_fingerprint_ref") != plan["fingerprint_receipt"]["ref"]
        or consolidation.get("plan_fingerprint_digest") != plan["fingerprint_receipt"]["digest"]
        or consolidation.get("evidence_identities") != evidence_identities
        or consolidation.get("reviewer_result_identities") != reviewer_identities
        or consolidation.get("reviewer_results") != reviewer_results
    ):
        raise HandoffManifestError("review consolidation exact identity chain mismatch")
    identity = {
        "intent": intent,
        "triggers": list(dict.fromkeys(triggers)),
        "artifacts": normalized_artifacts,
        "pending_dispositions": pending,
        "downstream": downstream,
        "owner_manifest_ref": normalized_owner_manifest_ref,
        "review_plan_ref": plan_ref,
        "evidence_receipt_refs": normalized_refs,
        "reviewer_result_refs": normalized_result_refs,
        "review_consolidation_ref": consolidation_ref,
        "recovery_token": recovery_token,
    }
    fingerprint = handoff_consumer.build_handoff_fingerprint(
        identity, evidence_receipts=receipts
    )
    payload = {
        "schema_version": contract_schema_version("handoff_manifest"),
        **identity,
        "fingerprint_receipt": fingerprint,
    }
    try:
        handoff_consumer.validate_handoff_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HandoffManifestError(str(exc)) from exc

    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_path = output_dir / "payload.json"
    payload_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    labels = {"open": "转", "out_of_scope": "Out of Scope", "downstream": "下一工作流承接"}
    pending_lines = ["- 无未决项"] if not pending else [
        f"- {item['summary']}（泛化判定：{item['generalization']}）："
        + (
            f"{labels[item['disposition']]} `{item['target']}`"
            if item["disposition"] != "out_of_scope"
            else f"Out of Scope `{item['target']}`"
        )
        for item in pending
    ]
    source_head = fingerprint["digest_payload"]["git"]["head_sha"]
    evidence_lines = [
        f"- `{result['command']}` exit={result['exit_code']} "
        f"{result['started_at']}..{result['finished_at']} {source_head} "
        f"receipt=`{ref}` evidence=`{result['id']}`"
        for ref, receipt in zip(normalized_refs, receipts)
        for result in receipt["evidence"]
    ]
    payload_ref = payload_path.relative_to(ROOT).as_posix()
    metadata = {
        "captured_at": fingerprint["captured_at"],
        "captured_by": fingerprint["captured_by"],
    }
    text = "\n".join(
        [
            "# 轮次交接单",
            "",
            f"- intent 终版：{intent}",
            f"- 新轮触发判定：触发（{', '.join(identity['triggers'])}）",
            "",
            "## EvidenceFingerprint",
            "",
            f"- payload_ref: `{payload_ref}`",
            f"- ref: `{fingerprint['ref']}`",
            f"- digest: `{fingerprint['digest']}`",
            f"- source_head: `{source_head}`",
            f"- source_fingerprint: `{fingerprint['digest']}`",
            f"- captured_metadata: `{json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))}`",
            "- freshness: `fresh`",
            f"- recovery_token: `{recovery_token}`",
            f"- digest_payload: `{json.dumps(fingerprint['digest_payload'], ensure_ascii=False, separators=(',', ':'))}`",
            "",
            "## 产出物",
            "",
            *[f"- `{artifact}`" for artifact in normalized_artifacts],
            "",
            "## 未决项去向",
            "",
            *pending_lines,
            "",
            "## 唯一合法下游",
            "",
            f"- {downstream}",
            "",
            "## 证据链",
            "",
            *evidence_lines,
            "",
        ]
    )
    manifest_path = output_dir / "manifest.md"
    manifest_path.write_text(text, encoding="utf-8")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise HandoffManifestError("input 必须为 JSON object")
        result = produce(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[handoff_manifest] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(result.relative_to(ROOT) if isinstance(result, Path) else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

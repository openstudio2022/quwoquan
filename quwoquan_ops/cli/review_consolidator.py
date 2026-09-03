#!/usr/bin/env python3
"""Pure deterministic Review result and finding consolidator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import evidence_runner  # noqa: E402
import handoff_consumer  # noqa: E402
import review_dispatch  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    contract_section,
    validate_declared_fields,
    validate_required_fields,
)
from lib.evidence_fingerprint import validate_evidence_fingerprint  # noqa: E402

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"


class ReviewConsolidationError(ValueError):
    pass


def _registry() -> dict[str, Any]:
    value = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ReviewConsolidationError("review registry 必须为 mapping")
    return value


def _terminal(codes: list[str], findings: list[dict[str, Any]]) -> dict[str, Any]:
    unique = list(dict.fromkeys(codes))
    definitions = contract_section("terminal_codes")
    unknown = [code for code in unique if code not in definitions]
    if unknown:
        raise ReviewConsolidationError(f"terminal code 未注册：{unknown}")
    severities = {finding["severity"] for finding in findings}
    rules = {
        "malformed_unknown_stale_or_required_incomplete": (
            any(definitions[code]["severity"] == "GATE_BLOCK" for code in unique),
            "GATE_BLOCK",
        ),
        "gate_block_finding": ("GATE_BLOCK" in severities, "GATE_BLOCK"),
        "optional_incomplete_or_pr_warn_finding": (
            any(definitions[code]["severity"] == "PR_WARN" for code in unique)
            or "PR_WARN" in severities,
            "PR_WARN",
        ),
        "advisory_or_pass": (True, "PASS"),
    }
    precedence = contract_section("review_consolidation").get("terminal_precedence")
    if not isinstance(precedence, list) or set(precedence) != set(rules):
        raise ReviewConsolidationError("review consolidation terminal precedence 非法")
    for rule in precedence:
        matches, status = rules[rule]
        if matches:
            return {"status": status, "codes": unique}
    raise ReviewConsolidationError("review consolidation terminal 无可用终态")


def consolidate(
    plan: dict[str, Any],
    evidence_receipt: dict[str, Any] | list[tuple[str, dict[str, Any]]],
    reviewer_results: list[dict[str, Any] | tuple[str, dict[str, Any]]],
    *,
    evidence_receipt_ref: str | None = None,
    registry: dict[str, Any] | None = None,
    generated_at: str | None = None,
    exact_bytes_by_ref: dict[str, bytes] | None = None,
) -> dict[str, Any]:
    active_registry = registry or _registry()
    try:
        current_plan = review_dispatch.validate_current_review_plan(
            plan, active_registry, phase="consolidation"
        )
    except review_dispatch.ReviewDispatchError as exc:
        raise ReviewConsolidationError(f"{exc.code}: {exc.message}") from exc
    if isinstance(evidence_receipt, list):
        evidence_pairs = evidence_receipt
    else:
        evidence_pairs = [(evidence_receipt_ref or "", evidence_receipt)]
    if len(evidence_pairs) != 1 or not evidence_pairs[0][0]:
        raise ReviewConsolidationError("named evidence receipt exact ref 必填且当前只允许一份")
    evidence_ref, exact_evidence = evidence_pairs[0]
    evidence_runner.validate_named_evidence_receipt(exact_evidence)
    if exact_evidence["terminal"] != {
        "status": "PASS",
        "code": "EVIDENCE.PASSED",
        "failed_evidence": None,
    }:
        raise ReviewConsolidationError("REVIEW.EVIDENCE_FAILED: named evidence 非 PASS")
    if (
        exact_evidence["plan_fingerprint_ref"] != current_plan["ref"]
        or exact_evidence["plan_fingerprint_digest"] != current_plan["digest"]
    ):
        raise ReviewConsolidationError(
            "REVIEW.FINGERPRINT_CHANGED: evidence 与 current plan identity 不一致"
        )
    handoff_consumer.validate_named_evidence_ref_payload(
        exact_evidence, plan=plan, registry=active_registry, label=evidence_ref
    )
    evidence_raw = (exact_bytes_by_ref or {}).get(evidence_ref)
    evidence_identity = (
        handoff_consumer.named_evidence_identity_from_raw(
            evidence_ref, evidence_raw, exact_evidence
        )
        if evidence_raw is not None
        else handoff_consumer.named_evidence_identity(evidence_ref, exact_evidence)
    )

    expected = {item["role"]: item for item in plan["reviewers"]}
    by_role: dict[str, dict[str, Any]] = {}
    reviewer_identities: list[dict[str, Any]] = []
    for item in reviewer_results:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ReviewConsolidationError("reviewer result exact ref 必填")
        result_ref, raw = item
        if not isinstance(raw, dict):
            raise ReviewConsolidationError("reviewer result 必须为 mapping")
        try:
            result_raw = (exact_bytes_by_ref or {}).get(result_ref)
            if result_raw is None:
                _, raw, result_identity = handoff_consumer.validate_review_result_ref(
                    result_ref, plan=plan, evidence_identities=[evidence_identity]
                )
            else:
                result_identity = handoff_consumer.validate_review_result_ref_payload(
                    result_ref,
                    result_raw,
                    raw,
                    plan=plan,
                    evidence_identities=[evidence_identity],
                )
        except (TypeError, ValueError) as exc:
            raise ReviewConsolidationError(str(exc)) from exc
        reviewer_identities.append(result_identity)
        role = str(raw["role"])
        if role not in expected or role in by_role:
            raise ReviewConsolidationError(f"review result role 非法或重复：{role}")
        if raw["status"] not in contract_section("review_result")["statuses"]:
            raise ReviewConsolidationError(f"review result status 非法：{raw['status']}")
        if (
            raw["plan_fingerprint_ref"] != current_plan["ref"]
            or raw["plan_fingerprint_digest"] != current_plan["digest"]
        ):
            raise ReviewConsolidationError(
                f"REVIEW.FINGERPRINT_CHANGED: reviewer={role} result stale"
            )
        findings: list[dict[str, Any]] = []
        for finding in raw["findings"]:
            if not isinstance(finding, dict):
                raise ReviewConsolidationError("review finding 必须为 mapping")
            validate_declared_fields(finding, "review_finding", "required_fields")
            for field, value in finding.items():
                if not isinstance(value, str) or not value:
                    raise ReviewConsolidationError(
                        f"review finding {field} 必须为非空字符串"
                    )
            severity = finding["severity"]
            if severity not in contract_section("review_finding")["severities"]:
                raise ReviewConsolidationError(
                    f"review finding severity 非法：{severity}"
                )
            findings.append(finding)
        by_role[role] = {**raw, "findings": findings}

    incomplete: list[dict[str, Any]] = []
    codes: list[str] = []
    for role, reviewer in expected.items():
        result = by_role.get(role)
        if result is None or result["status"] != "completed":
            required = bool(reviewer["required"])
            code = (
                "REVIEW.REQUIRED_REVIEWER_INCOMPLETE"
                if required
                else "REVIEW.OPTIONAL_REVIEWER_INCOMPLETE"
            )
            codes.append(code)
            incomplete.append(
                {
                    "role": role,
                    "required": required,
                    "reason": "missing" if result is None else str(result["status"]),
                    "code": code,
                }
            )

    deduped: dict[str, dict[str, Any]] = {}
    for role in expected:
        result = by_role.get(role)
        if not result or result["status"] != "completed":
            continue
        for finding in result["findings"]:
            finding_id = str(finding["id"])
            prior = deduped.get(finding_id)
            if prior is None:
                deduped[finding_id] = finding
            elif prior != finding:
                raise ReviewConsolidationError(
                    f"finding id 冲突且内容不一致：{finding_id}"
                )
    findings = [deduped[key] for key in sorted(deduped)]
    terminal = _terminal(codes, findings)
    identity_by_role = {item["role"]: item for item in reviewer_identities}
    result = {
        "schema_version": contract_schema_version("review_consolidation"),
        "plan_fingerprint_ref": current_plan["ref"],
        "plan_fingerprint_digest": current_plan["digest"],
        "evidence_identities": [evidence_identity],
        "reviewer_result_identities": [
            identity_by_role[role] for role in expected if role in identity_by_role
        ],
        "reviewer_results": [by_role[role] for role in expected if role in by_role],
        "findings": findings,
        "incomplete_roles": incomplete,
        "terminal": terminal,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    validate_required_fields(result, "review_consolidation")
    return result


def validate_exact_consolidation(
    consolidation: dict[str, Any],
    *,
    plan: dict[str, Any],
    evidence_pairs: list[tuple[str, dict[str, Any]]],
    reviewer_pairs: list[tuple[str, dict[str, Any]]],
    registry: dict[str, Any] | None = None,
    exact_bytes_by_ref: dict[str, bytes] | None = None,
    require_pass: bool = True,
) -> dict[str, Any]:
    """Recompute the sole exact Review chain; no partial field comparison is valid."""

    validate_required_fields(consolidation, "review_consolidation")
    if require_pass and consolidation.get("terminal") != {
        "status": "PASS",
        "codes": [],
    }:
        raise ReviewConsolidationError("review consolidation 非 PASS")
    recomputed = consolidate(
        plan,
        evidence_pairs,
        reviewer_pairs,
        registry=registry,
        generated_at=str(consolidation.get("generated_at") or ""),
        exact_bytes_by_ref=exact_bytes_by_ref,
    )
    if recomputed != consolidation:
        raise ReviewConsolidationError(
            "review consolidation does not match exact plan/owner/candidate/"
            "human/evidence/reviewer chain recomputation"
        )
    if any(
        item.get("severity") == "GATE_BLOCK"
        for item in consolidation.get("findings") or []
    ):
        raise ReviewConsolidationError("review consolidation 含 GATE_BLOCK finding")
    return consolidation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--reviewer-result", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        evidence_path = Path(args.evidence)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        results = [
            (path, json.loads(Path(path).read_text(encoding="utf-8")))
            for path in args.reviewer_result
        ]
        output = consolidate(
            plan,
            evidence,
            results,
            evidence_receipt_ref=args.evidence,
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[review_consolidator] GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["terminal"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

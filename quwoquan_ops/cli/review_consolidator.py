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
sys.path.insert(0, str(ROOT))
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

from lib.review_fingerprint import repository_inputs, source_root, dependency_root

REGISTRY_PATH = ROOT / ".agents/skills/review/references/registry.yaml"


class ReviewConsolidationError(ValueError):
    pass


def _registry() -> dict[str, Any]:
    value = yaml.safe_load((source_root(ROOT) / ".agents/skills/review/references/registry.yaml").read_text(encoding="utf-8")) or {}
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


def _closure_error(message: str) -> None:
    raise ReviewConsolidationError(f"candidate closure: {message}")


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _closure_error(f"{label} 必须为非空字符串")
    return value


def _items(value: Any, label: str, *, required: bool = False) -> list:
    if not isinstance(value, list) or (required and not value):
        _closure_error(f"{label} 必须为{'非空' if required else ''}列表")
    return value


def _closure_fields(value: Any, declaration: str) -> None:
    if not isinstance(value, dict):
        _closure_error(f"{declaration} 必须为 mapping")
    validate_declared_fields(value, "candidate_review_closure", declaration)


def _relative(value: Any) -> str:
    from lib.evidence_fingerprint import normalize_repo_relative_path

    raw = _nonempty(value, "path")
    normalized = normalize_repo_relative_path(raw, source_root(ROOT))
    if normalized != raw or raw.startswith(".qwq_output/"):
        _closure_error("path 必须为 canonical repository source path")
    return normalized


def _evidence_ids(ids: Any, receipt: dict, label: str) -> list[dict]:
    ids = _items(ids, label, required=True)
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        _closure_error(f"{label} 不得重复或为空")
    entries = receipt["evidence"]
    selected = []
    for evidence_id in ids:
        matches = [item for item in entries if item["id"] == evidence_id]
        if len(matches) != 1 or matches[0]["exit_code"] != 0 or matches[0]["timed_out"]:
            _closure_error(f"{label} 未绑定当前成功命名 evidence: {evidence_id}")
        selected.append(matches[0])
    return selected


def _health_findings(artifact: dict) -> None:
    if artifact["terminal"] == "GATE_BLOCK":
        _closure_error("健康 GATE_BLOCK 不可由 disposition 抵消")
    seen = set()
    terminals = set()
    for finding in _items(artifact["findings"], "health findings"):
        if not isinstance(finding, dict):
            _closure_error("health finding 必须为 mapping")
        finding_id = _nonempty(finding.get("findingId"), "findingId")
        _nonempty(finding.get("code"), "health code")
        _nonempty(finding.get("path"), "health path")
        if finding_id in seen:
            _closure_error("原始 health findingId 重复")
        seen.add(finding_id)
        if finding.get("terminal") not in {"PASS", "PR_WARN"}:
            _closure_error("health finding terminal 非法或健康 GATE_BLOCK 不可由 OPEN 抵消")
        terminals.add(finding["terminal"])
    if artifact["terminal"] == "PR_WARN" and "PR_WARN" not in terminals:
        _closure_error("PR_WARN artifact 缺原始 warning")


def _health_identity(artifact: dict, candidate: dict) -> None:
    expected = {
        "candidate_evidence_ref": candidate["ref"],
        "candidate_evidence_sha256": candidate["canonical_bytes_sha256"],
        "changed_paths_digest": candidate["changed_paths_digest"],
        "impact_plan_ref": candidate["impact_plan_ref"],
        "impact_plan_digest": candidate["impact_plan_digest"],
    }
    for field, value in expected.items():
        if artifact.get(field) != value:
            _closure_error(f"health artifact {field} stale")


def _health_artifacts(plan: dict, receipt: dict) -> list[tuple[dict, dict]]:
    from lib.named_evidence_artifact import _report, _assert_report_summary

    kind = contract_section("candidate_review_closure")["health_artifact_kind"]
    reports = []
    for entry in receipt["evidence"]:
        artifact = entry.get("artifact")
        if not artifact or artifact.get("kind") != kind:
            continue
        _health_identity(artifact, plan["candidate_evidence_identity"])
        if "git_range" in plan and (artifact["head_sha"] != plan["head_sha"] or artifact["base_sha"] != plan["merge_base_sha"]):
            _closure_error("health report 与 explicit source range 不一致")
        report = _report(artifact, repo_root=source_root(ROOT), evidence_id=entry["id"])
        _assert_report_summary(report, artifact, entry["id"])
        _health_findings(artifact)
        reports.append((entry, artifact))
    return reports


def _owner_open(finding: dict, disposition: dict, plan: dict) -> None:
    from lib.feature_tree.commands import discover_nodes
    from lib.feature_tree.ownership import resolve_target_details
    from lib.feature_tree.parsing import open_item_details, headings

    nodes = discover_nodes()
    target = plan["owner_identity"]["resolved_owner"] if finding["path"] == "<candidate>" else _relative(finding["path"])
    owner = resolve_target_details(target, nodes).node
    expected_path = owner.spec.relative_to(source_root(ROOT)).as_posix()
    ref = _nonempty(disposition["open_ref"], "open_ref")
    path, separator, anchor = ref.partition("#")
    if path != expected_path or not separator or anchor not in headings(owner.spec):
        _closure_error("OPEN 必须为当前最低 owner 有效 anchor")
    if path not in {item["path"] for item in plan["contexts"] if item.get("exists")}:
        _closure_error("OPEN spec 未绑定 current plan context")
    matches = [item for item in open_item_details(owner) if item["id"].lower() == anchor]
    if len(matches) != 1 or not matches[0]["completion"] or matches[0]["releaseImpact"] != "track":
        _closure_error("OPEN 失效、缺完成判定或阻断准出")


def _warning_index(reports: list) -> dict:
    warnings = {}
    for entry, artifact in reports:
        for finding in artifact["findings"]:
            if finding["terminal"] != "PR_WARN":
                continue
            prior = warnings.get(finding["findingId"])
            if prior and prior[1] != finding:
                _closure_error("原始 finding identity 内容冲突")
            warnings.setdefault(finding["findingId"], (entry, finding))
    return warnings


def _disposition_index(dispositions: Any) -> dict:
    by_id = {}
    for disposition in _items(dispositions, "health_dispositions"):
        _closure_fields(disposition, "disposition_fields")
        finding_id = _nonempty(disposition["finding_id"], "finding_id")
        if finding_id in by_id:
            _closure_error("disposition 重复")
        by_id[finding_id] = disposition
    return by_id


def _outside_candidate(finding: dict, plan: dict) -> None:
    from lib.feature_tree.commands import discover_nodes
    from lib.feature_tree.ownership import resolve_target_details

    nodes = discover_nodes()
    if finding["path"] == "<candidate>":
        _closure_error("candidate 级 finding 不得 out-of-scope")
    path = _relative(finding["path"])
    owners = {resolve_target_details(item, nodes).node.rel for item in plan["changed_paths"]}
    if path in plan["changed_paths"] or resolve_target_details(path, nodes).node.rel in owners:
        _closure_error("out-of-scope 的 path/owner 在 candidate 内")


def _report_finished(pair: tuple) -> datetime:
    return datetime.fromisoformat(pair[0]["finished_at"].replace("Z", "+00:00"))


def _fix_now(original: dict, finding: dict, selected: list, reports: list) -> None:
    """核对声明，不把同 immutable candidate 的虚构变化当作源码修复。"""
    latest_entry, latest_report = max(reports, key=_report_finished)
    started = datetime.fromisoformat(latest_entry["started_at"].replace("Z", "+00:00"))
    finished = datetime.fromisoformat(original["finished_at"].replace("Z", "+00:00"))
    if latest_entry not in selected or started <= finished:
        _closure_error("fix-now 缺后续健康验证")
    active_ids = {
        item["findingId"] for item in latest_report["findings"]
        if item["terminal"] in {"PR_WARN", "GATE_BLOCK"}
    }
    if finding["findingId"] in active_ids:
        _closure_error("fix-now 原有效 warning 仍存在")


def _adjudicate_health(disposition: dict, original: dict, finding: dict,
                       plan: dict, receipt: dict, reports: list) -> None:
    _nonempty(disposition["reason"], "reason")
    selected = _evidence_ids(disposition["evidence_ids"], receipt, "disposition evidence")
    action = disposition["disposition"]
    if action == "owner-open":
        _owner_open(finding, disposition, plan)
    elif action == "out-of-scope":
        _outside_candidate(finding, plan)
    elif action == "fix-now":
        _fix_now(original, finding, selected, reports)
    else:
        _closure_error("disposition 非法")
    if action != "owner-open" and disposition["open_ref"] is not None:
        _closure_error("非 OPEN disposition 不得填写 open_ref")


def _health_dispositions(closure: dict, plan: dict, receipt: dict, reports: list) -> None:
    warnings = _warning_index(reports)
    by_id = _disposition_index(closure["health_dispositions"])
    if set(by_id) != set(warnings):
        _closure_error("health disposition 漏项或多项")
    for finding_id, disposition in by_id.items():
        original, finding = warnings[finding_id]
        _adjudicate_health(disposition, original, finding, plan, receipt, reports)


def _replacement_entry(replacement: dict, plan: dict, seen: set) -> str:
    _closure_fields(replacement, "replacement_fields")
    old = _relative(replacement["old_path"])
    successor = _relative(replacement["successor_path"])
    if old in seen or not (source_root(ROOT) / successor).is_file():
        _closure_error("replacement 重复或接替入口不存在")
    seen.add(old)
    if not {old, successor}.intersection(plan["changed_paths"]):
        _closure_error("replacement 未绑定 candidate path")
    for field in ("old_symbols", "successor_symbols"):
        for symbol in _items(replacement[field], field, required=True):
            _nonempty(symbol, field)
    return old


def _consumer_migration(replacement: dict, definition: dict) -> bool:
    state = replacement["dynamic_entry_status"]
    if state not in definition["dynamic_entry_statuses"]:
        _closure_error("dynamic_entry_status 非法")
    unknown = state == "unknown"
    consumer_paths = set()
    for consumer in _items(replacement["consumers"], "consumers", required=True):
        _closure_fields(consumer, "consumer_fields")
        path = _relative(consumer["path"])
        if path in consumer_paths or not (source_root(ROOT) / path).is_file():
            _closure_error("consumer 重复或不存在")
        consumer_paths.add(path)
        _nonempty(consumer["reason"], "consumer reason")
        if consumer["status"] not in definition["consumer_statuses"]:
            _closure_error("consumer status 非法")
        unknown = unknown or consumer["status"] == "unknown"
    return unknown


def _cleanup_path(item: dict, definition: dict) -> str | None:
    _closure_fields(item, "cleanup_fields")
    _nonempty(item["reason"], "cleanup reason")
    if item["kind"] not in definition["cleanup_kinds"] or item["action"] not in definition["cleanup_actions"]:
        _closure_error("cleanup kind/action 非法")
    if item["action"] == "not-applicable":
        if item["kind"] == "implementation" or item["path"] is not None:
            _closure_error("not-applicable 仅限 config/test，path 必须 null")
        return None
    return _relative(item["path"])


def _cleanup_state(item: dict, path: str | None, plan: dict, unknown: bool) -> None:
    if path is None:
        return
    exists = (source_root(ROOT) / path).exists() or (source_root(ROOT) / path).is_symlink()
    if item["action"] == "removed" and (unknown or exists or path not in plan["changed_paths"]):
        _closure_error("unknown 不可自动删除，或 removed path 仍存在/不在 candidate")
    if item["action"] == "retained" and not exists:
        _closure_error("retained path 不存在")


def _cleanup_inventory(replacement: dict, old: str, plan: dict, unknown: bool) -> None:
    definition = contract_section("candidate_review_closure")
    cleanup_paths = set()
    by_kind: dict[str, list] = {}
    for item in _items(replacement["cleanup"], "cleanup", required=True):
        path = _cleanup_path(item, definition)
        if (path, item["kind"]) in cleanup_paths:
            _closure_error("cleanup 重复")
        cleanup_paths.add((path, item["kind"]))
        by_kind.setdefault(item["kind"], []).append(path)
        _cleanup_state(item, path, plan, unknown)
    if set(by_kind) != set(definition["cleanup_kinds"]) or (old, "implementation") not in cleanup_paths:
        _closure_error("缺旧实现/config/test 清理或保留依据")
    for paths in by_kind.values():
        if None in paths and len(paths) != 1:
            _closure_error("not-applicable 不得与同 kind 的路径清单并存")


def _replacements(closure: dict, plan: dict, receipt: dict) -> None:
    definition = contract_section("candidate_review_closure")
    seen = set()
    for replacement in _items(closure["replacements"], "replacements"):
        old = _replacement_entry(replacement, plan, seen)
        _evidence_ids(replacement["scan_evidence_ids"], receipt, "scan evidence")
        _evidence_ids(replacement["test_evidence_ids"], receipt, "test evidence")
        unknown = _consumer_migration(replacement, definition)
        _cleanup_inventory(replacement, old, plan, unknown)


def _requires_health(plan: dict) -> bool:
    from quwoquan_ops.gate.code_health_delta.classification import classify_path
    from quwoquan_ops.gate.code_health_delta.policy import load_policy

    if plan["workflow"] != "dev":
        return False
    policy = load_policy(source_root(ROOT) / "quwoquan_ops/policies/code_health_policy.yaml")
    return any(classify_path(path, policy) == "handwritten-production" for path in plan["changed_paths"])


def _primary_closure(plan: dict, by_role: dict) -> dict | None:
    primary = {item["role"] for item in plan["reviewers"] if item["kind"] == "primary"}
    closures = [(role, result) for role, result in by_role.items() if "candidate_closure" in result]
    if not closures:
        return None
    if len(closures) != 1 or closures[0][0] not in primary or closures[0][1]["status"] != "completed":
        _closure_error("candidate_closure 只允许 completed primary 唯一提供")
    closure = closures[0][1]["candidate_closure"]
    _closure_fields(closure, "required_fields")
    candidate = plan["candidate_evidence_identity"]
    if closure["candidate_fingerprint_ref"] != candidate["fingerprint_ref"] or closure["candidate_fingerprint_digest"] != candidate["fingerprint_digest"]:
        _closure_error("candidate fingerprint stale")
    return closure


def validate_candidate_closure(plan: dict, receipt: dict, by_role: dict) -> None:
    """内部语义校验；外部准出必须调用 validate_exact_consolidation 完整链。"""
    reports = _health_artifacts(plan, receipt)
    if _requires_health(plan) and not reports:
        _closure_error("手写 dev 准出缺健康 artifact")
    closure = _primary_closure(plan, by_role)
    if closure is None:
        if any(item["findings"] or item["terminal"] == "PR_WARN" for _, item in reports):
            _closure_error("原始健康 findings 缺 primary candidate_closure")
        return
    _health_dispositions(closure, plan, receipt, reports)
    _replacements(closure, plan, receipt)


@repository_inputs
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

    validate_candidate_closure(plan, exact_evidence, by_role)

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


def _exact_result_pairs(pairs: Any, section: str, exact_bytes: dict) -> None:
    from lib.descriptor_safe_io import read_repo_relative_regular_single_link

    refs = set()
    for pair in _items(pairs, section, required=section == "named_evidence_receipt"):
        if not isinstance(pair, tuple) or len(pair) != 2:
            _closure_error(f"{section} 必须为 exact (ref, payload) pair")
        ref, payload = pair
        _nonempty(ref, "exact ref")
        if Path(ref).is_absolute() or ".." in Path(ref).parts:
            _closure_error("exact ref 路径逃逸")
        if ref in refs or not isinstance(payload, dict):
            _closure_error(f"{section} ref 重复或 payload 非 mapping")
        refs.add(ref)
        validate_required_fields(payload, section)
        raw = exact_bytes.get(ref)
        if raw is None:
            raw = read_repo_relative_regular_single_link(dependency_root(ROOT), ref)
        if json.loads(raw) != payload:
            _closure_error(f"{section} exact bytes 与 payload 不一致")


def _exact_plan_dependency(plan: dict, evidence_pairs: list, exact_bytes: dict) -> None:
    from lib.descriptor_safe_io import read_repo_relative_regular_single_link
    import hashlib

    for _, receipt in evidence_pairs:
        metadata = receipt["execution_fingerprint"]["captured_metadata"]
        ref = metadata["plan_input_ref"]
        if Path(ref).is_absolute() or ".." in Path(ref).parts:
            _closure_error("plan ref 路径逃逸")
        raw = exact_bytes.get(ref)
        if raw is None:
            raw = read_repo_relative_regular_single_link(dependency_root(ROOT), ref)
        if json.loads(raw) != plan or "sha256:" + hashlib.sha256(raw).hexdigest() != metadata["plan_bytes_sha256"]:
            _closure_error("exact plan dependency 与 receipt 不一致")


@repository_inputs
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
    """外部准出复用入口：完整 current 链重算；不接受裁剪的健康投影。

    evidence_pairs/reviewer_pairs 为 exact (ref, payload)；可移植调用传入
    exact_bytes_by_ref，否则读取仓内 single-link regular exact 文件。
    plan 的 owner/candidate 闭包仍由现有 current-plan validator 完整校验。
    """
    validate_required_fields(plan, "review_plan")
    _exact_result_pairs(evidence_pairs, "named_evidence_receipt", exact_bytes_by_ref or {})
    _exact_result_pairs(reviewer_pairs, "review_result", exact_bytes_by_ref or {})
    if dependency_root(ROOT) != source_root(ROOT):
        _exact_plan_dependency(plan, evidence_pairs, exact_bytes_by_ref or {})
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

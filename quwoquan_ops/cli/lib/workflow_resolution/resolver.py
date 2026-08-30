"""Contract-driven resolver for explicit and structured natural-language inputs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from ..agent_governance_contract import validate_feature_context_manifest
from ..evidence_fingerprint import (
    EvidenceFingerprintError,
    canonical_digest,
    normalize_repo_relative_path,
)
from ..feature_context_fingerprint import validate_current_feature_context_fingerprint
from ..feature_tree import discover_nodes, parent_chain, resolve_target_details
from .contract import REPO_ROOT, load_contract

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_AUDIT_REF_RE = re.compile(r"[A-Za-z0-9._:/#-]{1,256}\Z")


class ResolutionError(ValueError):
    """Typed input or receipt validation failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _clean_detail(detail: object) -> str:
    return " ".join(str(detail).replace("\x00", "\\x00").split())


def _typed_error(contract: Mapping[str, Any], code: str, detail: str) -> dict[str, Any]:
    actual = code if code in contract["errors"] else "WFR.CONTRACT_INVALID"
    descriptor = contract["errors"][actual]
    return {
        "result": "typed_blocker",
        "error_code": actual,
        "terminal": descriptor["terminal"],
        "recovery": descriptor["recovery"],
        "detail": _clean_detail(detail),
    }


def contract_failure(detail: str) -> dict[str, Any]:
    return {
        "result": "typed_blocker",
        "error_code": "WFR.CONTRACT_INVALID",
        "terminal": "hold",
        "recovery": "repair_canonical_workflow_resolution_contract",
        "detail": _clean_detail(detail),
    }


def input_failure(code: str, detail: str) -> dict[str, Any]:
    try:
        return _typed_error(load_contract(), code, detail)
    except Exception:
        return contract_failure(detail)


def receipt_failure(detail: str) -> dict[str, Any]:
    try:
        return _typed_error(load_contract(), "WFR.RECEIPT_INVALID", detail)
    except Exception:
        return contract_failure(detail)


def _exact_mapping(value: object, fields: list[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResolutionError("WFR.INPUT_INVALID", f"{label} must be an object")
    actual = set(value)
    expected = set(fields)
    if actual != expected:
        raise ResolutionError(
            "WFR.INPUT_INVALID",
            f"{label} fields drifted: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}",
        )
    return value


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    def normalize(item: object) -> object:
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, str):
            return unicodedata.normalize("NFC", item)
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, Mapping):
            normalized = {unicodedata.normalize("NFC", str(key)): normalize(child) for key, child in item.items()}
            return {key: normalized[key] for key in sorted(normalized, key=lambda candidate: candidate.encode("utf-8"))}
        raise ResolutionError("WFR.RECEIPT_INVALID", f"unsupported value type: {type(item).__name__}")

    return json.dumps(normalize(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _receipt_digest(value: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _skill_digest(skill_ref: str) -> str:
    path = REPO_ROOT / skill_ref
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("not a regular file")
        return _sha256_bytes(path.read_bytes())
    except OSError as error:
        raise ResolutionError("WFR.CONTRACT_INVALID", f"skill could not be read: {skill_ref}: {error}") from error


def _normalized_repo_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or value.startswith(("/", "\\")):
        raise ResolutionError("WFR.INPUT_INVALID", f"{label} must be a non-empty repo-relative path")
    try:
        normalized = normalize_repo_relative_path(value, REPO_ROOT)
    except EvidenceFingerprintError as error:
        raise ResolutionError("WFR.INPUT_INVALID", f"{label} is unsafe: {error}") from error
    if normalized != unicodedata.normalize("NFC", value.replace("\\", "/")):
        raise ResolutionError("WFR.INPUT_INVALID", f"{label} must not contain dot segments or alternate separators")
    return normalized


def _safe_regular_repo_file(ref: str) -> Path:
    current = REPO_ROOT
    for part in ref.split("/"):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            raise
        except OSError as error:
            raise ResolutionError("WFR.OWNER_MANIFEST_UNSAFE", f"owner manifest path cannot be inspected: {error}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ResolutionError("WFR.OWNER_MANIFEST_UNSAFE", "owner manifest path contains a symlink")
    if not stat.S_ISREG(current.lstat().st_mode):
        raise ResolutionError("WFR.OWNER_MANIFEST_UNSAFE", "owner manifest ref is not a regular file")
    try:
        if current.resolve(strict=True) != REPO_ROOT.joinpath(ref).absolute():
            raise ResolutionError("WFR.OWNER_MANIFEST_UNSAFE", "owner manifest physical path drifted")
    except OSError as error:
        raise ResolutionError("WFR.OWNER_MANIFEST_UNSAFE", f"owner manifest path cannot be resolved: {error}") from error
    return current


def _manifest_owner_chain(target: str) -> tuple[str, list[dict[str, Any]]]:
    nodes = discover_nodes()
    resolution = resolve_target_details(target, nodes)
    by_dir = {node.directory.resolve(): node for node in nodes}
    chain = [
        {"level": node.level, "node_id": node.node_id, "path": node.rel}
        for node in parent_chain(resolution.node, by_dir)
    ]
    return resolution.node.rel, chain


def _manifest_binding(value: object) -> dict[str, Any]:
    empty = {
        "ref": None,
        "expected_target": None,
        "expected_scope": None,
        "status": "missing",
        "fingerprint": None,
        "code": "WFR.OWNER_MANIFEST_REQUIRED",
    }
    if value is None:
        return empty
    manifest_input = _exact_mapping(value, ["ref", "expected_target", "expected_scope"], "owner_manifest")
    ref = _normalized_repo_relative(manifest_input["ref"], "owner_manifest.ref")
    expected_target = _normalized_repo_relative(manifest_input["expected_target"], "owner_manifest.expected_target")
    raw_scope = manifest_input["expected_scope"]
    expected_scope = None if raw_scope is None else _normalized_repo_relative(raw_scope, "owner_manifest.expected_scope")
    binding = {
        "ref": ref,
        "expected_target": expected_target,
        "expected_scope": expected_scope,
        "status": "stale",
        "fingerprint": None,
        "code": "WFR.OWNER_MANIFEST_INVALID",
    }
    try:
        path = _safe_regular_repo_file(ref)
    except FileNotFoundError:
        binding.update(status="missing", code="WFR.OWNER_MANIFEST_REQUIRED")
        return binding
    except ResolutionError as error:
        binding["code"] = error.code
        return binding
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        binding["code"] = "WFR.OWNER_MANIFEST_INVALID"
        return binding
    if not isinstance(manifest, dict):
        return binding
    try:
        validate_feature_context_manifest(manifest)
    except (KeyError, TypeError, ValueError):
        return binding
    try:
        manifest_target = normalize_repo_relative_path(manifest["target"], REPO_ROOT)
    except (EvidenceFingerprintError, TypeError):
        return binding
    if manifest_target != expected_target or (expected_scope is not None and manifest_target != expected_scope):
        binding["code"] = "WFR.OWNER_MANIFEST_TARGET_MISMATCH"
        return binding
    try:
        expected_owner, expected_chain = _manifest_owner_chain(manifest_target)
    except ValueError:
        binding["code"] = "WFR.OWNER_MANIFEST_OWNER_MISMATCH"
        return binding
    if manifest.get("resolved_owner") != expected_owner or manifest.get("owner_chain") != expected_chain:
        binding["code"] = "WFR.OWNER_MANIFEST_OWNER_MISMATCH"
        return binding
    try:
        fingerprint = validate_current_feature_context_fingerprint(manifest, repo_root=REPO_ROOT)
    except (EvidenceFingerprintError, KeyError, TypeError, ValueError):
        binding["code"] = "WFR.OWNER_MANIFEST_STALE"
        return binding
    binding.update(status="fresh", fingerprint=fingerprint, code=None)
    return binding


def _host_audit(contract: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    claimed_host = payload.get("host_label", "unknown")
    adapter = payload.get("host_adapter", "unknown")
    evidence_ref = payload.get("discovery_evidence_ref")
    if claimed_host not in contract["closed_sets"]["host_label"]:
        raise ResolutionError("WFR.INPUT_INVALID", "host_label is outside declared audit labels")
    if adapter not in contract["closed_sets"]["host_adapter"]:
        raise ResolutionError("WFR.INPUT_INVALID", "host_adapter is outside declared audit adapters")
    if evidence_ref is not None and (not isinstance(evidence_ref, str) or not _AUDIT_REF_RE.fullmatch(evidence_ref)):
        raise ResolutionError("WFR.INPUT_INVALID", "discovery_evidence_ref must be a safe opaque reference")
    return {
        "claimed_host": claimed_host,
        "adapter": adapter,
        "discovery_status": "proven" if evidence_ref else "unproven",
        "discovery_evidence_ref": evidence_ref,
    }


def _candidate(
    *, workflow: str, source: str, confidence_basis: str, evidence_kind: str, evidence_digest: str, evidence_ref: str
) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "source": source,
        "confidence_basis": confidence_basis,
        "evidence_kind": evidence_kind,
        "evidence_digest": evidence_digest,
        "evidence_ref": evidence_ref,
    }


def _rejection(workflow: str, code: str, confidence_basis: str) -> dict[str, str]:
    return {"workflow": workflow, "code": code, "confidence_basis": confidence_basis}


def _term_quoted(text: str, term: str, quote_pairs: list[str]) -> bool:
    start = text.casefold().find(term.casefold())
    if start < 0:
        return False
    end = start + len(term)
    for pair in quote_pairs:
        left, right = pair[0], pair[1]
        before = text.rfind(left, 0, start)
        after = text.find(right, end)
        if before >= 0 and after >= end:
            return True
    return False


def _natural_candidates(
    contract: Mapping[str, Any], payload: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any], str]:
    text = payload.get("text", "")
    if not isinstance(text, str):
        raise ResolutionError("WFR.INPUT_INVALID", "natural text must be a string")
    raw_candidates = payload.get("candidates", [])
    if not isinstance(raw_candidates, list):
        raise ResolutionError("WFR.INPUT_INVALID", "natural candidates must be a list")
    matches: dict[str, dict[str, Any]] = {}
    rejections: list[dict[str, str]] = []
    normalized_evidence: list[dict[str, Any]] = []
    workflows = contract["workflows"]
    evidence_kinds = contract["closed_sets"]["evidence_kind"]
    evidence_refs = contract["closed_sets"]["evidence_reference"]
    for index, raw in enumerate(raw_candidates):
        candidate = _exact_mapping(raw, ["workflow", "evidence"], f"candidates[{index}]")
        workflow = candidate["workflow"]
        evidence = _exact_mapping(candidate["evidence"], ["kind", "digest", "reference"], f"candidates[{index}].evidence")
        if not isinstance(workflow, str) or not workflow:
            raise ResolutionError("WFR.INPUT_INVALID", f"candidates[{index}].workflow must be non-empty")
        kind, digest, reference = evidence["kind"], evidence["digest"], evidence["reference"]
        if kind not in evidence_kinds or reference not in evidence_refs or not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ResolutionError("WFR.INPUT_INVALID", f"candidates[{index}].evidence is outside the enumerated evidence contract")
        normalized_evidence.append({"workflow": workflow, "kind": kind, "digest": digest, "reference": reference})
        if workflow not in workflows:
            rejections.append(_rejection("*", "WFR.UNKNOWN_CANDIDATE", "unknown_candidate"))
            continue
        matches.setdefault(workflow, _candidate(
            workflow=workflow,
            source="structured_candidate",
            confidence_basis="structured_enumerated_evidence",
            evidence_kind=kind,
            evidence_digest=digest,
            evidence_ref=reference,
        ))

    folded = text.casefold()
    policy = contract["resolution_policy"]
    mutation_workflows = set(policy["mutation_workflows"])
    has_negation = any(marker.casefold() in folded for marker in policy["negation_markers"])
    has_meta = any(marker.casefold() in folded for marker in policy["meta_markers"])
    for workflow, definition in workflows.items():
        for rule in definition["natural_rules"]:
            selector = "all_terms" if "all_terms" in rule else "any_terms"
            terms = rule[selector]
            hits = [term for term in terms if term.casefold() in folded]
            hit = len(hits) == len(terms) if selector == "all_terms" else bool(hits)
            if not hit:
                continue
            quoted = any(_term_quoted(text, term, policy["quote_pairs"]) for term in hits)
            if workflow in mutation_workflows and (has_negation or has_meta or quoted):
                basis = "negated_mutation" if has_negation else "quoted_or_meta_mutation"
                rejections.append(_rejection(workflow, "WFR.MUTATION_INTENT_UNCERTAIN", basis))
                continue
            matches.setdefault(workflow, _candidate(
                workflow=workflow,
                source="rule",
                confidence_basis="contract_rule_match",
                evidence_kind="contract_rule",
                evidence_digest=canonical_digest({"workflow": workflow, "rule_id": rule["id"]}),
                evidence_ref="host_classifier",
            ))
    normalized = {
        "text_digest": _sha256_bytes(text.encode("utf-8")),
        "text_length": len(text.encode("utf-8")),
        "structured_evidence": normalized_evidence,
    }
    category = "natural_mixed" if text and raw_candidates else ("natural_structured_candidate" if raw_candidates else "natural_text")
    return list(matches.values()), rejections, normalized, category


def _resolution_identity(selected: str, skill_digest: str, profile: str) -> str:
    return canonical_digest({
        "workflow": selected,
        "skill_digest": skill_digest,
        "readiness_profile": profile,
        "canonical_next_segment": "PRE",
        "authorization_effect": "none",
    })


def _input_length(normalized_input: Mapping[str, Any]) -> int:
    return len(_canonical_json_bytes(normalized_input))


def _base_receipt(
    contract: Mapping[str, Any], input_mode: str, input_category: str, normalized_input: Mapping[str, Any], host_audit: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_id": "workflow-resolve-receipt",
        "schema_version": 2,
        "result": "hold",
        "terminal_code": "WFR.INPUT_INVALID",
        "recovery": contract["errors"]["WFR.INPUT_INVALID"]["recovery"],
        "input_mode": input_mode,
        "input_category": input_category,
        "input_digest": canonical_digest({"input_mode": input_mode, "normalized_input": normalized_input}),
        "input_length": _input_length(normalized_input),
        "selected_workflow": None,
        "candidates": [],
        "rejections": [],
        "skill_ref": None,
        "skill_digest": None,
        "semantic_identity": None,
        "owner_manifest_ref": None,
        "owner_manifest_expected_target": None,
        "owner_manifest_expected_scope": None,
        "owner_manifest_status": "missing",
        "ambiguity_terminal": "hold",
        "readiness_profile": None,
        "next_segment": "terminal",
        "authorization_effect": "none",
        "human_interaction_binding_ref": contract["human_interaction_binding_ref"],
        "evidence_fingerprint": None,
        "host_audit": host_audit,
        "receipt_digest": "",
    }


def _set_terminal(receipt: dict[str, Any], contract: Mapping[str, Any], code: str, *, next_segment: str | None = None) -> None:
    descriptor = contract["errors"][code]
    terminal = descriptor["terminal"]
    receipt["result"] = terminal
    receipt["terminal_code"] = code
    receipt["recovery"] = descriptor["recovery"]
    receipt["ambiguity_terminal"] = "none" if terminal == "selected" else terminal
    receipt["next_segment"] = next_segment or ("PRE" if terminal == "selected" else "terminal")


def _finalize(receipt: dict[str, Any]) -> dict[str, Any]:
    payload = dict(receipt)
    payload["receipt_digest"] = _receipt_digest({key: value for key, value in payload.items() if key != "receipt_digest"})
    return payload


def _candidate_terminal(candidates: list[dict[str, Any]], rejections: list[dict[str, str]]) -> str:
    codes = {item["code"] for item in rejections}
    if "WFR.UNKNOWN_CANDIDATE" in codes:
        return "WFR.UNKNOWN_CANDIDATE"
    if "WFR.MUTATION_INTENT_UNCERTAIN" in codes:
        return "WFR.MUTATION_INTENT_UNCERTAIN"
    if len(candidates) > 1:
        return "WFR.AMBIGUOUS"
    if not candidates:
        return "WFR.LOW_CONFIDENCE"
    return "WFR.SELECTED"


def resolve(payload: object) -> dict[str, Any]:
    contract = load_contract()
    if not isinstance(payload, Mapping):
        raise ResolutionError("WFR.INPUT_INVALID", "input must be a JSON object")
    allowed = {
        "input_mode", "command", "text", "candidates", "owner_manifest",
        "host_label", "host_adapter", "discovery_evidence_ref",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ResolutionError("WFR.INPUT_INVALID", f"input has unknown fields: {unknown}")
    input_mode = payload.get("input_mode")
    if input_mode not in contract["closed_sets"]["input_mode"]:
        raise ResolutionError("WFR.INPUT_INVALID", "input_mode must be explicit or natural_structured")
    host_audit = _host_audit(contract, payload)
    manifest = _manifest_binding(payload.get("owner_manifest"))

    if input_mode == "explicit":
        if set(payload) & {"text", "candidates"}:
            raise ResolutionError("WFR.INPUT_INVALID", "explicit input must not include natural fields")
        command = payload.get("command")
        if not isinstance(command, str) or not command:
            raise ResolutionError("WFR.INPUT_INVALID", "explicit command must be non-empty")
        normalized_input = {"command_digest": _sha256_bytes(command.encode("utf-8")), "command_length": len(command.encode("utf-8"))}
        input_category = "explicit_command"
        selected = next((name for name, definition in contract["workflows"].items() if definition["canonical_command"] == command), None)
        if selected is None:
            candidates: list[dict[str, Any]] = []
            rejections = [_rejection("*", "WFR.UNKNOWN_EXPLICIT_COMMAND", "unknown_candidate")]
            candidate_code = "WFR.UNKNOWN_EXPLICIT_COMMAND"
        else:
            candidates = [_candidate(
                workflow=selected,
                source="explicit_command",
                confidence_basis="exact_canonical_command",
                evidence_kind="exact_command",
                evidence_digest=canonical_digest({"canonical_command": command}),
                evidence_ref="canonical_command",
            )]
            rejections = []
            candidate_code = "WFR.SELECTED"
    else:
        if "command" in payload:
            raise ResolutionError("WFR.INPUT_INVALID", "natural_structured input must not include command")
        candidates, rejections, normalized_input, input_category = _natural_candidates(contract, payload)
        candidate_code = _candidate_terminal(candidates, rejections)
        selected = candidates[0]["workflow"] if candidate_code == "WFR.SELECTED" else None

    receipt = _base_receipt(contract, input_mode, input_category, normalized_input, host_audit)
    receipt.update({
        "owner_manifest_ref": manifest["ref"],
        "owner_manifest_expected_target": manifest["expected_target"],
        "owner_manifest_expected_scope": manifest["expected_scope"],
        "owner_manifest_status": manifest["status"],
        "evidence_fingerprint": manifest["fingerprint"],
        "candidates": candidates,
        "rejections": rejections,
    })

    if selected is not None:
        definition = contract["workflows"][selected]
        readiness = contract["readiness_profiles"][selected]
        skill_digest = _skill_digest(definition["skill_ref"])
        receipt.update({
            "selected_workflow": selected,
            "skill_ref": definition["skill_ref"],
            "skill_digest": skill_digest,
            "semantic_identity": _resolution_identity(selected, skill_digest, readiness["profile"]),
            "readiness_profile": readiness["profile"],
        })

    if manifest["code"] is not None:
        _set_terminal(receipt, contract, manifest["code"], next_segment="hold")
        if selected is not None:
            receipt["rejections"].append(_rejection(selected, manifest["code"], "no_high_confidence_match"))
    elif candidate_code == "WFR.SELECTED":
        _set_terminal(receipt, contract, "WFR.SELECTED")
    else:
        _set_terminal(receipt, contract, candidate_code)
        if candidate_code == "WFR.LOW_CONFIDENCE":
            receipt["rejections"].append(_rejection("*", candidate_code, "no_high_confidence_match"))
    return _finalize(receipt)


def _validate_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ResolutionError("WFR.RECEIPT_INVALID", f"{label} must be sha256 digest")


def _current_manifest_from_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    ref = value["owner_manifest_ref"]
    target = value["owner_manifest_expected_target"]
    scope = value["owner_manifest_expected_scope"]
    if ref is None:
        if target is not None or scope is not None:
            raise ResolutionError("WFR.RECEIPT_INVALID", "missing manifest ref carries expected target/scope")
        return _manifest_binding(None)
    return _manifest_binding({"ref": ref, "expected_target": target, "expected_scope": scope})


def verify_receipt(receipt: object) -> dict[str, Any]:
    contract = load_contract()
    fields = contract["schemas"]["workflow_resolve_receipt"]["required_fields"]
    if not isinstance(receipt, Mapping) or set(receipt) != set(fields):
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt fields drifted")
    value = dict(receipt)
    if value.get("schema_id") != "workflow-resolve-receipt" or value.get("schema_version") != 2:
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt identity/version is invalid")
    for field, closed_name in (
        ("input_mode", "input_mode"), ("input_category", "input_category"),
        ("result", "resolution_status"), ("ambiguity_terminal", "ambiguity_terminal"),
        ("next_segment", "next_segment"), ("owner_manifest_status", "owner_manifest_status"),
        ("authorization_effect", "authorization_effect"),
    ):
        if value.get(field) not in contract["closed_sets"][closed_name]:
            raise ResolutionError("WFR.RECEIPT_INVALID", f"receipt {field} invalid")
    if value.get("terminal_code") not in contract["errors"]:
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt terminal code invalid")
    descriptor = contract["errors"][value["terminal_code"]]
    if value.get("result") != descriptor["terminal"] or value.get("recovery") != descriptor["recovery"]:
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt terminal descriptor drifted")
    _validate_digest(value.get("input_digest"), "input_digest")
    if not isinstance(value.get("input_length"), int) or value["input_length"] < 0:
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt input_length invalid")

    candidate_fields = set(contract["schemas"]["candidate"]["required_fields"])
    rejection_fields = set(contract["schemas"]["rejection"]["required_fields"])
    candidates = value.get("candidates")
    rejections = value.get("rejections")
    if not isinstance(candidates, list) or any(not isinstance(item, Mapping) or set(item) != candidate_fields for item in candidates):
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt candidates invalid")
    if not isinstance(rejections, list) or any(not isinstance(item, Mapping) or set(item) != rejection_fields for item in rejections):
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt rejections invalid")
    if len({item["workflow"] for item in candidates}) != len(candidates):
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt candidates duplicate workflow")
    for item in candidates:
        if item["workflow"] not in contract["workflows"] or item["source"] not in contract["closed_sets"]["candidate_source"]:
            raise ResolutionError("WFR.RECEIPT_INVALID", "receipt candidate outside closed set")
        if item["confidence_basis"] not in contract["closed_sets"]["confidence_basis"] or item["evidence_kind"] not in contract["closed_sets"]["evidence_kind"] or item["evidence_ref"] not in contract["closed_sets"]["evidence_reference"]:
            raise ResolutionError("WFR.RECEIPT_INVALID", "receipt candidate confidence evidence invalid")
        _validate_digest(item["evidence_digest"], "candidate evidence_digest")
    for item in rejections:
        if item["code"] not in contract["errors"] or item["confidence_basis"] not in contract["closed_sets"]["confidence_basis"]:
            raise ResolutionError("WFR.RECEIPT_INVALID", "receipt rejection outside closed set")

    host_fields = set(contract["schemas"]["host_audit"]["required_fields"])
    audit = value.get("host_audit")
    if not isinstance(audit, Mapping) or set(audit) != host_fields:
        raise ResolutionError("WFR.RECEIPT_INVALID", "host audit fields drifted")
    if audit["claimed_host"] not in contract["closed_sets"]["host_label"] or audit["adapter"] not in contract["closed_sets"]["host_adapter"] or audit["discovery_status"] not in contract["closed_sets"]["discovery_status"]:
        raise ResolutionError("WFR.RECEIPT_INVALID", "host audit closed set drifted")
    evidence_ref = audit["discovery_evidence_ref"]
    if evidence_ref is not None and (not isinstance(evidence_ref, str) or not _AUDIT_REF_RE.fullmatch(evidence_ref)):
        raise ResolutionError("WFR.RECEIPT_INVALID", "host audit evidence ref invalid")
    if (evidence_ref is None) != (audit["discovery_status"] == "unproven"):
        raise ResolutionError("WFR.RECEIPT_INVALID", "host audit discovery status/ref mismatch")

    selected = value.get("selected_workflow")
    if selected is not None:
        if selected not in contract["workflows"] or len(candidates) != 1 or candidates[0]["workflow"] != selected:
            raise ResolutionError("WFR.RECEIPT_INVALID", "selected workflow/candidate matrix invalid")
        definition = contract["workflows"][selected]
        readiness = contract["readiness_profiles"][selected]
        expected_skill_digest = _skill_digest(definition["skill_ref"])
        if value.get("skill_ref") != definition["skill_ref"] or value.get("skill_digest") != expected_skill_digest:
            raise ResolutionError("WFR.RECEIPT_INVALID", "skill identity is stale or drifted")
        if value.get("readiness_profile") != readiness["profile"]:
            raise ResolutionError("WFR.RECEIPT_INVALID", "readiness profile drifted")
        if value.get("semantic_identity") != _resolution_identity(selected, expected_skill_digest, readiness["profile"]):
            raise ResolutionError("WFR.RECEIPT_INVALID", "semantic identity drifted")
    elif any(value.get(field) is not None for field in ("skill_ref", "skill_digest", "semantic_identity", "readiness_profile")):
        raise ResolutionError("WFR.RECEIPT_INVALID", "unselected receipt carries selected semantics")

    current_manifest = _current_manifest_from_receipt(value)
    if value["owner_manifest_status"] != current_manifest["status"] or value.get("evidence_fingerprint") != current_manifest["fingerprint"]:
        raise ResolutionError("WFR.RECEIPT_INVALID", "owner manifest status/fingerprint is not current")
    manifest_code = current_manifest["code"]
    rejection_codes = {item["code"] for item in rejections}
    if manifest_code is not None:
        expected_code = manifest_code
        expected_next = "hold"
    elif "WFR.UNKNOWN_EXPLICIT_COMMAND" in rejection_codes:
        expected_code = "WFR.UNKNOWN_EXPLICIT_COMMAND"
        expected_next = "terminal"
    else:
        expected_code = _candidate_terminal(candidates, rejections)
        expected_next = "PRE" if expected_code == "WFR.SELECTED" else "terminal"
    expected_descriptor = contract["errors"][expected_code]
    expected_ambiguity = "none" if expected_descriptor["terminal"] == "selected" else expected_descriptor["terminal"]
    if (
        value["terminal_code"] != expected_code
        or value["result"] != expected_descriptor["terminal"]
        or value["recovery"] != expected_descriptor["recovery"]
        or value["ambiguity_terminal"] != expected_ambiguity
        or value["next_segment"] != expected_next
    ):
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt terminal matrix is impossible")
    if value["result"] == "selected" and (selected is None or current_manifest["status"] != "fresh"):
        raise ResolutionError("WFR.RECEIPT_INVALID", "selected/PRE requires one candidate and fresh manifest")

    expected_digest = _receipt_digest({key: item for key, item in value.items() if key != "receipt_digest"})
    if value.get("receipt_digest") != expected_digest:
        raise ResolutionError("WFR.RECEIPT_INVALID", "receipt digest mismatch")
    return {
        "schema_id": "workflow-resolve-verification",
        "schema_version": 2,
        "result": "valid",
        "receipt_digest": value["receipt_digest"],
        "semantic_identity": value["semantic_identity"],
        "selected_workflow": selected,
        "terminal_code": value["terminal_code"],
        "recovery": value["recovery"],
        "next_segment": value["next_segment"],
    }

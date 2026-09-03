"""Agent context 与 Review plan 的受版本控制 schema 契约读取器。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "quwoquan_ops/policies/agent_governance_contract.yaml"
)


@lru_cache(maxsize=1)
def load_agent_governance_contract() -> dict[str, Any]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("agent governance contract schema_version 必须为 1")
    for section in (
        "feature_context_manifest",
        "candidate_evidence_manifest",
        "review_plan",
        "named_evidence_receipt",
        "review_finding",
        "reviewer_input",
        "review_result",
        "review_consolidation",
        "handoff_manifest",
        "evidence_fingerprint",
    ):
        definition = value.get(section)
        if not isinstance(definition, dict):
            raise TypeError(f"agent governance contract 缺映射段 {section}")
        version = definition.get("schema_version")
        if not isinstance(version, int) or version <= 0:
            raise ValueError(
                f"agent governance contract {section}.schema_version 必须为正整数"
            )
    _validate_terminal_codes(value.get("terminal_codes"))
    _validate_evidence_fingerprint_contract(value["evidence_fingerprint"])
    return value


def _validate_string_list(value: object, *, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        raise ValueError(f"agent governance contract {label} 必须为无重复非空字符串列表")
    return value


def _validate_exact_mapping(
    value: object,
    expected: dict[str, object],
    *,
    label: str,
) -> None:
    if not isinstance(value, dict) or value != expected:
        raise ValueError(f"agent governance contract {label} 未遵守 frozen canonical 值")



def _validate_terminal_codes(value: object) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError("agent governance contract terminal_codes 必须为非空 mapping")
    recoveries: dict[str, str] = {}
    for code, raw in value.items():
        if not isinstance(code, str) or not code.startswith(("REVIEW.", "IDENTITY.", "CANDIDATE.")):
            raise ValueError(f"terminal code 非 canonical REVIEW/IDENTITY/CANDIDATE：{code!r}")
        if not isinstance(raw, dict) or set(raw) != {
            "severity",
            "automatic_retry",
            "recovery",
        }:
            raise ValueError(f"terminal code {code} 字段闭集漂移")
        if raw["severity"] not in {"GATE_BLOCK", "PR_WARN"}:
            raise ValueError(f"terminal code {code} severity 非法")
        if raw["automatic_retry"] is not False:
            raise ValueError(f"terminal code {code} 不得自动重试")
        recovery = raw["recovery"]
        if not isinstance(recovery, str) or not recovery:
            raise ValueError(f"terminal code {code} recovery 必须唯一且非空")
        prior = recoveries.get(recovery)
        if prior is not None:
            raise ValueError(
                f"terminal recovery 必须一对一：{prior}/{code} -> {recovery}"
            )
        recoveries[recovery] = code

def _validate_evidence_fingerprint_contract(definition: dict[str, Any]) -> None:
    """Strongly validate the identity algorithm before any consumer can run."""

    required_keys = {
        "schema_version",
        "serialization_version",
        "digest_algorithm",
        "digest_format",
        "ref_format",
        "digest_payload_top_level_fields",
        "digest_payload_fields",
        "receipt_fields",
        "digest_excludes_receipt",
        "unknown_fields",
        "missing_field_encoding",
        "reserved_missing_member",
        "canonical_serialization",
        "paths",
        "symlink",
        "workspace_category_order",
        "path_snapshot_fields",
        "handoff",
        "required_fixtures",
    }
    if set(definition) != required_keys:
        raise ValueError(
            "agent governance contract evidence_fingerprint 顶层字段漂移："
            f"missing={sorted(required_keys - set(definition))}, "
            f"extra={sorted(set(definition) - required_keys)}"
        )
    exact_scalars = {
        "schema_version": 2,
        "serialization_version": "evidence-fingerprint-v1",
        "digest_algorithm": "sha256",
        "digest_format": "sha256:<64-lowercase-hex>",
        "ref_format": "evidence-fingerprint-v1:sha256:<64-lowercase-hex>",
        "digest_excludes_receipt": True,
        "unknown_fields": "reject",
        "reserved_missing_member": "$evidenceFingerprintMissing",
    }
    for field, expected in exact_scalars.items():
        if definition.get(field) != expected:
            raise ValueError(
                f"agent governance contract evidence_fingerprint.{field} 必须为 {expected!r}"
            )
    _validate_exact_mapping(
        definition.get("missing_field_encoding"),
        {"$evidenceFingerprintMissing": True},
        label="evidence_fingerprint.missing_field_encoding",
    )
    group_fields = {
        "git": ["head_sha", "merge_base_sha"],
        "workspace": [
            "tracked_digest",
            "untracked_digest",
            "deleted_digest",
            "renamed_digest",
            "symlink_digest",
        ],
        "assets": ["canonical_assets_digest", "review_assets_digest"],
        "execution": [
            "commands_digest",
            "toolchain_digest",
            "provider_digest",
            "generator_digest",
        ],
    }
    _validate_exact_mapping(
        definition.get("digest_payload_fields"),
        group_fields,
        label="evidence_fingerprint.digest_payload_fields",
    )
    expected_top = [
        "schema_version",
        "serialization_version",
        "git",
        "workspace",
        "assets",
        "execution",
    ]
    if definition.get("digest_payload_top_level_fields") != expected_top:
        raise ValueError(
            "agent governance contract evidence_fingerprint.digest_payload_top_level_fields 非法"
        )
    expected_receipt = [
        "schema_version",
        "serialization_version",
        "ref",
        "digest",
        "digest_payload",
        "captured_at",
        "captured_by",
        "captured_metadata",
    ]
    if definition.get("receipt_fields") != expected_receipt:
        raise ValueError("agent governance contract evidence_fingerprint.receipt_fields 非法")
    _validate_exact_mapping(
        definition.get("canonical_serialization"),
        {
            "character_encoding": "utf-8",
            "unicode_normalization": "NFC",
            "json_encoding": "compact-json-no-bom-no-trailing-newline",
            "map_key_order": "bytewise-utf8-after-NFC",
            "string_escaping": "json-required-only",
            "numbers": "integers-only-canonical-base10-no-plus-no-leading-zero-negative-zero-is-zero",
            "booleans": "json-lowercase-true-false",
            "null": "json-lowercase-null",
            "missing_null_empty": "distinct",
            "list_order": "preserve-declared-semantic-order",
            "set_like_lists": "sort-by-canonical-json-bytewise-utf8",
        },
        label="evidence_fingerprint.canonical_serialization",
    )
    _validate_exact_mapping(
        definition.get("paths"),
        {
            "separator": "slash",
            "input_separators": ["slash", "backslash"],
            "identity": "repository-relative-lexical-no-dot-segments",
            "unicode_normalization": "NFC",
            "ordering": "bytewise-utf8",
            "outside_repository": "reject",
        },
        label="evidence_fingerprint.paths",
    )
    _validate_exact_mapping(
        definition.get("symlink"),
        {
            "identity": "normalized-path-plus-normalized-target-plus-target-content",
            "broken_target": "explicit-broken-true-and-null-target-content-digest",
            "target_outside_repository": "reject",
            "cycle": "explicit-cycle-content-marker",
            "directory_snapshot_includes_symlinks": True,
            "follow_directory_symlink": False,
        },
        label="evidence_fingerprint.symlink",
    )
    if definition.get("workspace_category_order") != [
        "tracked",
        "untracked",
        "deleted",
        "renamed",
        "symlink",
    ]:
        raise ValueError(
            "agent governance contract evidence_fingerprint.workspace_category_order 非法"
        )
    _validate_string_list(
        definition.get("path_snapshot_fields"),
        label="evidence_fingerprint.path_snapshot_fields",
    )
    _validate_exact_mapping(
        definition.get("handoff"),
        {
            "freshness_values": ["fresh", "stale"],
            "required_freshness": "fresh",
            "recovery_token": "rerun_evidence_for_new_fingerprint",
            "source_head_format": "<40-or-64-lowercase-hex>",
            "captured_metadata_fields": ["captured_at", "captured_by"],
        },
        label="evidence_fingerprint.handoff",
    )
    fixtures = _validate_string_list(
        definition.get("required_fixtures"),
        label="evidence_fingerprint.required_fixtures",
    )
    expected_fixtures = {
        "same-input-different-captured-at-same-digest",
        "path-order-invariance",
        "any-payload-byte-change-different-digest",
        "unicode-NFC-equivalence",
        "missing-null-empty-distinct",
        "windows-separator-normalization",
        "symlink-target-content-and-broken-target",
        "review-tracked-untracked-deleted",
        "retired-review-algorithm-not-consumed",
        "handoff-stale-missing-fingerprint-and-recovery-failure",
        "feature-manifest-v4-content-addressed-owner-identity-and-budget",
        "named-evidence-dedup-drift-failure-and-result",
        "handoff-six-trigger-producer-and-ordinary-noop",
        "human-decision-create-once-tamper-ref-drift",
        "human-decision-pause-redirect-stable-terminal",
        "human-decision-ordinary-missing-nonblocking",
        "human-decision-formal-prod-rejects-self-attested",
    }
    if set(fixtures) != expected_fixtures:
        raise ValueError("agent governance contract evidence_fingerprint.required_fixtures 非法")



def canonical_bytes_sha256(value: Any) -> str:
    """Return the exact canonical JSON byte identity used by cross-phase refs."""

    import hashlib
    import json

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

def contract_section(name: str) -> dict[str, Any]:
    value = load_agent_governance_contract().get(name)
    if not isinstance(value, dict):
        raise TypeError(f"agent governance contract 缺映射段 {name}")
    return value


def contract_schema_version(section: str) -> int:
    version = contract_section(section).get("schema_version")
    if not isinstance(version, int) or version <= 0:
        raise ValueError(
            f"agent governance contract {section}.schema_version 必须为正整数"
        )
    return version


def declared_fields(section: str, declaration: str) -> tuple[str, ...]:
    definition = contract_section(section)
    fields = definition.get(declaration)
    if (
        not isinstance(fields, list)
        or not fields
        or not all(isinstance(item, str) and item for item in fields)
        or len(fields) != len(set(fields))
    ):
        raise ValueError(f"agent governance contract {section}.{declaration} 非法")
    return tuple(fields)


def validate_declared_fields(
    payload: dict[str, Any],
    section: str,
    declaration: str,
) -> None:
    expected = declared_fields(section, declaration)
    missing = [field for field in expected if field not in payload]
    extra = sorted(set(payload) - set(expected))
    if missing or extra:
        raise ValueError(
            f"{section}.{declaration} 字段漂移："
            f"missing={missing or []}, extra={extra or []}"
        )


def declared_object(
    payload: dict[str, Any],
    section: str,
    declaration: str,
) -> dict[str, Any]:
    validate_declared_fields(payload, section, declaration)
    return {field: payload[field] for field in declared_fields(section, declaration)}


def validate_required_fields(payload: dict[str, Any], section: str) -> None:
    validate_declared_fields(payload, section, "required_fields")


def validate_schema_version(payload: dict[str, Any], section: str) -> None:
    expected = contract_schema_version(section)
    actual = payload.get("schema_version")
    if actual != expected:
        raise ValueError(
            f"{section}.schema_version 必须为 {expected}，实际为 {actual!r}"
        )


def validate_feature_context_manifest(payload: dict[str, Any]) -> None:
    """Validate one manifest at the producer and every consumer boundary."""

    validate_schema_version(payload, "feature_context_manifest")
    validate_required_fields(payload, "feature_context_manifest")
    for field, declaration in (
        ("owner_chain", "owner_chain_fields"),
        ("canonical_contexts", "context_fields"),
        ("open_items", "open_item_fields"),
    ):
        values = payload[field]
        if not isinstance(values, list):
            raise TypeError(f"feature_context_manifest.{field} 必须为列表")
        for value in values:
            if not isinstance(value, dict):
                raise TypeError(f"feature_context_manifest.{field} 项必须为映射")
            validate_declared_fields(
                value,
                "feature_context_manifest",
                declaration,
            )
    for field in ("applicable_agents",):
        values = payload[field]
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise TypeError(f"feature_context_manifest.{field} 必须为非空字符串列表")
    for field in ("target", "resolved_owner"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise TypeError(f"feature_context_manifest.{field} 必须为非空字符串")
    binding = payload["evidence_fingerprint"]
    if not isinstance(binding, dict):
        raise TypeError("feature_context_manifest.evidence_fingerprint 必须为映射")
    validate_declared_fields(
        binding, "feature_context_manifest", "fingerprint_binding_fields"
    )
    modes = contract_section("feature_context_manifest")["fingerprint_binding_modes"]
    if binding["mode"] not in modes:
        raise ValueError("feature_context_manifest.evidence_fingerprint.mode 非法")


def validate_candidate_evidence_manifest(payload: dict[str, Any]) -> None:
    """Validate exact candidate evidence at every producer/consumer boundary."""

    validate_schema_version(payload, "candidate_evidence_manifest")
    validate_required_fields(payload, "candidate_evidence_manifest")
    for field, declaration in (("owner_chain", "owner_chain_fields"), ("context_snapshots", "context_snapshot_fields")):
        values = payload[field]
        if not isinstance(values, list):
            raise TypeError(f"candidate_evidence_manifest.{field} 必须为列表")
        for value in values:
            if not isinstance(value, dict):
                raise TypeError(f"candidate_evidence_manifest.{field} 项必须为映射")
            validate_declared_fields(value, "candidate_evidence_manifest", declaration)
    paths = payload["changed_paths"]
    if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item for item in paths):
        raise TypeError("candidate_evidence_manifest.changed_paths 必须为非空字符串列表")
    if paths != sorted(set(paths), key=lambda item: item.encode("utf-8")):
        raise ValueError("candidate_evidence_manifest.changed_paths 必须规范排序且无重复")
    for field in ("owner_identity_ref", "owner_identity_canonical_bytes_sha256", "target", "resolved_owner", "impact_plan_identity"):
        if field != "impact_plan_identity" and (not isinstance(payload[field], str) or not payload[field]):
            raise TypeError(f"candidate_evidence_manifest.{field} 必须为非空字符串")
    if not isinstance(payload["workspace_digests"], dict) or not isinstance(payload["impact_plan"], dict):
        raise TypeError("candidate evidence workspace_digests/impact_plan 必须为映射")
    identity = payload["impact_plan_identity"]
    if not isinstance(identity, dict):
        raise TypeError("candidate evidence impact_plan_identity 必须为映射")
    validate_declared_fields(identity, "candidate_evidence_manifest", "impact_plan_identity_fields")
    if not isinstance(payload["evidence_fingerprint"], dict):
        raise TypeError("candidate evidence fingerprint 必须为映射")

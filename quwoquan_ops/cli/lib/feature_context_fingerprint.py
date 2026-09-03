"""Shared feature-context manifest EvidenceFingerprint producer/consumer."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .agent_governance_contract import (
    contract_schema_version,
    declared_object,
)
from .evidence_fingerprint import (
    EvidenceFingerprintError,
    build_evidence_fingerprint,
    canonical_digest,
    canonical_json_bytes,
    normalize_repo_relative_path,
    snapshot_path,
    validate_evidence_fingerprint,
    workspace_digests,
)
from .descriptor_safe_io import read_repo_relative_regular_single_link

GENERATOR_PATH = "quwoquan_ops/cli/lib/feature_tree/commands.py"
CONTRACT_PATH = "quwoquan_ops/policies/agent_governance_contract.yaml"

_CONTENT_ADDRESSED_REF_RE = re.compile(
    r"^\.qwq_output/env/repo/runs/feature-tree/by-fingerprint/"
    r"(?P<receipt>receipts/)?(?P<digest>[0-9a-f]{64})\.json$"
)


def validate_content_addressed_ref(
    raw_ref: str,
    *,
    raw_bytes: bytes,
    repo_root: Path,
    receipt: bool = False,
) -> str:
    """验证 immutable ref 的物理位置、raw bytes 摘要与 canonical bytes。"""

    relative = normalize_repo_relative_path(raw_ref, repo_root)
    match = _CONTENT_ADDRESSED_REF_RE.fullmatch(relative)
    if match is None or bool(match.group("receipt")) is not receipt:
        kind = "receipt" if receipt else "manifest"
        raise EvidenceFingerprintError(
            f"feature context {kind} ref 不是 canonical content-addressed path：{relative}"
        )
    actual = hashlib.sha256(raw_bytes).hexdigest()
    if actual != match.group("digest"):
        raise EvidenceFingerprintError(
            "feature context ref filename 与 exact raw bytes sha256 不一致"
        )
    try:
        value = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceFingerprintError(f"feature context ref 不是有效 UTF-8 JSON：{exc}") from exc
    if canonical_json_bytes(value) != raw_bytes:
        raise EvidenceFingerprintError("feature context ref 不是 exact canonical JSON bytes")
    return relative



def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        raise EvidenceFingerprintError(f"无法读取 git {' '.join(args)}")
    return value


def _head_sha(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "HEAD")


def _merge_base_sha(repo_root: Path, head_sha: str) -> str:
    for base in ("dev1.0", "main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", base],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return head_sha


def owner_identity_projection(payload: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    """Return the stable PRE identity, excluding snapshots and volatile bytes."""

    return {
        "schema_version": payload["schema_version"],
        "target": normalize_repo_relative_path(str(payload["target"]), repo_root),
        "resolved_owner": normalize_repo_relative_path(str(payload["resolved_owner"]), repo_root),
        "owner_chain": [
            {
                "level": item["level"],
                "node_id": item["node_id"],
                "path": normalize_repo_relative_path(str(item["path"]), repo_root),
            }
            for item in payload["owner_chain"]
        ],
        "generator_identity": GENERATOR_PATH,
        "contract_identity": CONTRACT_PATH,
    }


def build_feature_context_fingerprint(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    captured_by: str = "feature_tree",
) -> dict[str, Any]:
    identity = owner_identity_projection(payload, repo_root=repo_root)
    return build_evidence_fingerprint(
        {
            "git": {
                "head_sha": canonical_digest("owner-identity-head-independent"),
                "merge_base_sha": canonical_digest("owner-identity-merge-base-independent"),
            },
            "workspace": workspace_digests([], repo_root=repo_root),
            "assets": {
                "canonical_assets_digest": canonical_digest(identity),
                "review_assets_digest": canonical_digest(
                    {
                        "generator": snapshot_path(GENERATOR_PATH, repo_root=repo_root),
                        "contract": snapshot_path(CONTRACT_PATH, repo_root=repo_root),
                    }
                ),
            },
            "execution": {
                "commands_digest": canonical_digest([]),
                "toolchain_digest": canonical_digest(
                    {
                        "feature_context_manifest_schema": contract_schema_version(
                            "feature_context_manifest"
                        )
                    }
                ),
                "provider_digest": canonical_digest("feature_tree.owner_identity"),
                "generator_digest": canonical_digest(
                    {
                        "generator": snapshot_path(GENERATOR_PATH, repo_root=repo_root),
                        "contract": snapshot_path(CONTRACT_PATH, repo_root=repo_root),
                    }
                ),
            },
        },
        captured_at="owner-identity-v4",
        captured_by=captured_by,
        captured_metadata={"consumer": "feature_context_owner_identity"},
    )


def validate_current_feature_context_fingerprint(
    payload: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    """Validate stable owner identity; current workspace bytes are intentionally ignored."""

    actual = resolve_fingerprint_binding(
        payload.get("evidence_fingerprint"), repo_root=repo_root
    )
    expected = build_feature_context_fingerprint(
        payload, repo_root=repo_root, captured_by="feature_context_consumer"
    )
    for field in ("ref", "digest", "digest_payload"):
        if actual[field] != expected[field]:
            raise EvidenceFingerprintError(
                f"feature context owner identity EvidenceFingerprint {field} invalid"
            )
    return actual


def embedded_fingerprint_binding(receipt: dict[str, Any]) -> dict[str, Any]:
    canonical = validate_evidence_fingerprint(receipt)
    return declared_object(
        {
            "mode": "embedded",
            "ref": canonical["ref"],
            "digest": canonical["digest"],
            "receipt": canonical,
            "receipt_ref": None,
        },
        "feature_context_manifest",
        "fingerprint_binding_fields",
    )


def referenced_fingerprint_binding(
    receipt: dict[str, Any], *, receipt_ref: str
) -> dict[str, Any]:
    canonical = validate_evidence_fingerprint(receipt)
    return declared_object(
        {
            "mode": "referenced",
            "ref": canonical["ref"],
            "digest": canonical["digest"],
            "receipt": None,
            "receipt_ref": receipt_ref,
        },
        "feature_context_manifest",
        "fingerprint_binding_fields",
    )


def resolve_fingerprint_binding(
    binding: object, *, repo_root: Path
) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise EvidenceFingerprintError("feature context fingerprint binding 必须为 mapping")
    canonical = declared_object(
        binding, "feature_context_manifest", "fingerprint_binding_fields"
    )
    mode = canonical["mode"]
    if mode == "embedded":
        if canonical["receipt_ref"] is not None:
            raise EvidenceFingerprintError("embedded fingerprint binding 不得带 receipt_ref")
        receipt = validate_evidence_fingerprint(canonical["receipt"])
    elif mode == "referenced":
        if canonical["receipt"] is not None:
            raise EvidenceFingerprintError("referenced fingerprint binding 不得内嵌 receipt")
        raw_ref = canonical["receipt_ref"]
        if not isinstance(raw_ref, str) or not raw_ref:
            raise EvidenceFingerprintError("referenced fingerprint binding 缺 receipt_ref")
        relative = normalize_repo_relative_path(raw_ref, repo_root)
        try:
            raw_bytes = read_repo_relative_regular_single_link(
                repo_root,
                relative,
                expected_directory_parts=(
                    ".qwq_output",
                    "env",
                    "repo",
                    "runs",
                    "feature-tree",
                    "by-fingerprint",
                    "receipts",
                ),
            )
            validate_content_addressed_ref(
                relative, raw_bytes=raw_bytes, repo_root=repo_root, receipt=True
            )
            value = json.loads(raw_bytes.decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceFingerprintError(
                f"feature context fingerprint receipt 无法读取：{exc}"
            ) from exc
        receipt = validate_evidence_fingerprint(value)
    else:
        raise EvidenceFingerprintError(f"feature context fingerprint mode 非法：{mode!r}")
    if canonical["ref"] != receipt["ref"] or canonical["digest"] != receipt["digest"]:
        raise EvidenceFingerprintError("feature context fingerprint binding 与 receipt 不一致")
    return receipt

"""Shared feature-context manifest EvidenceFingerprint producer/consumer."""

from __future__ import annotations

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
    normalize_repo_relative_path,
    snapshot_path,
    validate_evidence_fingerprint,
    workspace_digests,
)

GENERATOR_PATH = "quwoquan_ops/cli/lib/feature_tree/commands.py"
CONTRACT_PATH = "quwoquan_ops/policies/agent_governance_contract.yaml"


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


def managed_paths(payload: dict[str, Any], *, repo_root: Path) -> list[str]:
    paths = {
        normalize_repo_relative_path(str(payload["target"]), repo_root),
        normalize_repo_relative_path(str(payload["resolved_owner"]), repo_root),
        *[normalize_repo_relative_path(str(item["path"]), repo_root) for item in payload["owner_chain"]],
        *[normalize_repo_relative_path(str(item["path"]), repo_root) for item in payload["canonical_contexts"]],
        *[normalize_repo_relative_path(str(item), repo_root) for item in payload["applicable_agents"]],
        GENERATOR_PATH,
        CONTRACT_PATH,
    }
    return sorted(paths, key=lambda item: item.encode("utf-8"))


def build_feature_context_fingerprint(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    captured_by: str = "feature_tree",
) -> dict[str, Any]:
    identity = {key: value for key, value in payload.items() if key != "evidence_fingerprint"}
    paths = managed_paths(identity, repo_root=repo_root)
    head_sha = _head_sha(repo_root)
    return build_evidence_fingerprint(
        {
            "git": {
                "head_sha": head_sha,
                "merge_base_sha": _merge_base_sha(repo_root, head_sha),
            },
            "workspace": workspace_digests(paths, repo_root=repo_root),
            "assets": {
                "canonical_assets_digest": canonical_digest(identity),
                "review_assets_digest": canonical_digest(
                    [snapshot_path(path, repo_root=repo_root) for path in paths]
                ),
            },
            "execution": {
                "commands_digest": canonical_digest([]),
                "toolchain_digest": canonical_digest(
                    {
                        "python": list(sys.version_info[:3]),
                        "feature_context_manifest_schema": contract_schema_version(
                            "feature_context_manifest"
                        ),
                    }
                ),
                "provider_digest": canonical_digest("feature_tree"),
                "generator_digest": canonical_digest(
                    snapshot_path(GENERATOR_PATH, repo_root=repo_root)
                ),
            },
        },
        captured_by=captured_by,
        captured_metadata={"consumer": "feature_context_manifest"},
    )


def validate_current_feature_context_fingerprint(
    payload: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    actual = resolve_fingerprint_binding(
        payload.get("evidence_fingerprint"), repo_root=repo_root
    )
    expected = build_feature_context_fingerprint(
        payload, repo_root=repo_root, captured_by="feature_context_consumer"
    )
    for field in ("ref", "digest", "digest_payload"):
        if actual[field] != expected[field]:
            raise EvidenceFingerprintError(
                f"feature context manifest EvidenceFingerprint {field} stale"
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
        path = repo_root / relative
        if not path.is_file():
            raise EvidenceFingerprintError(f"feature context fingerprint receipt 不存在：{relative}")
        import json

        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceFingerprintError(
                f"feature context fingerprint receipt 无法读取：{exc}"
            ) from exc
        receipt = validate_evidence_fingerprint(value)
    else:
        raise EvidenceFingerprintError(f"feature context fingerprint mode 非法：{mode!r}")
    if canonical["ref"] != receipt["ref"] or canonical["digest"] != receipt["digest"]:
        raise EvidenceFingerprintError("feature context fingerprint binding 与 receipt 不一致")
    return receipt

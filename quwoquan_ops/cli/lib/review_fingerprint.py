"""Canonical Review plan fingerprint construction and path identity helpers."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

from lib.agent_governance_contract import contract_schema_version
from lib.evidence_fingerprint import (
    EvidenceFingerprintError,
    build_evidence_fingerprint,
    canonical_digest,
    normalize_repo_relative_path,
    snapshot_path,
    workspace_digests,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCES_DIR = REPO_ROOT / ".agents/skills/review/references"
REGISTRY_PATH = REFERENCES_DIR / "registry.yaml"
GRADING_PATH = REFERENCES_DIR / "grading.md"

def snapshot(relative: str) -> dict[str, Any]:
    return snapshot_path(relative, repo_root=REPO_ROOT)

def normalize_path(raw_path: str) -> str:
    return normalize_repo_relative_path(raw_path, REPO_ROOT)

def head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"

def merge_base_sha() -> str:
    for base in ("dev1.0", "main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", base], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return head_sha()

def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

def build_review_fingerprint(
    *, workflow: str, deliverable: str, scope: str,
    owner_manifest_identity: dict[str, Any], terminal: dict[str, Any],
    changed_paths: list[str], profiles: list[str], contexts: list[dict[str, Any]],
    initial_reviewers: list[dict[str, Any]], evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    assets = [snapshot(REGISTRY_PATH.relative_to(REPO_ROOT).as_posix())]
    if GRADING_PATH.is_file():
        assets.append(snapshot(GRADING_PATH.relative_to(REPO_ROOT).as_posix()))
    for reviewer in initial_reviewers:
        assets.extend((
            snapshot(f".agents/skills/review/references/roles/{reviewer['role']}/ROLE.md"),
            snapshot((REFERENCES_DIR / reviewer["checklist"]).relative_to(REPO_ROOT).as_posix()),
        ))
    review_identity = {
        "workflow": workflow, "deliverable": deliverable, "scope": scope,
        "owner_manifest_identity": owner_manifest_identity,
        "terminal": terminal,
        "changed_paths": changed_paths, "profiles": profiles, "contexts": contexts,
        "reviewers": [
            {key: item[key] for key in ("role", "kind", "required", "profile", "checklist")}
            for item in initial_reviewers
        ],
        "evidence": [
            {
                key: item[key]
                for key in (
                    "id",
                    "required",
                    "covers",
                    "timeout_seconds",
                    "command_digest",
                )
            }
            for item in evidence
        ],
    }
    return build_evidence_fingerprint(
        {
            "git": {"head_sha": head_sha(), "merge_base_sha": merge_base_sha()},
            "workspace": workspace_digests(
                changed_paths + [item["path"] for item in contexts], repo_root=REPO_ROOT,
            ),
            "assets": {
                "canonical_assets_digest": canonical_digest(contexts),
                "review_assets_digest": canonical_digest(
                    {"assets": assets, "review_identity": review_identity}
                ),
            },
            "execution": {
                "commands_digest": canonical_digest(
                    [item["command_digest"] for item in evidence]
                ),
                "toolchain_digest": canonical_digest({
                    "python": list(sys.version_info[:3]),
                    "review_plan_schema": contract_schema_version("review_plan"),
                }),
                "provider_digest": canonical_digest([
                    {key: item[key] for key in ("role", "kind", "required")}
                    for item in initial_reviewers
                ]),
                "generator_digest": canonical_digest(
                    snapshot("quwoquan_ops/cli/review_dispatch.py")
                ),
            },
        },
        captured_by="review_dispatch",
        captured_metadata={"consumer": "review_plan.fingerprint"},
    )

__all__ = [
    "EvidenceFingerprintError", "build_review_fingerprint", "head_sha",
    "merge_base_sha", "normalize_path", "sha256_text", "snapshot",
]

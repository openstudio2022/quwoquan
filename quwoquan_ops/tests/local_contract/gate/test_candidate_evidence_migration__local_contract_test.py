"""A0 dual identity ordinary development cross-component contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import review_dispatch  # noqa: E402
from lib.candidate_evidence import (  # noqa: E402
    CandidateEvidenceError, build_candidate_evidence, validate_candidate_ref,
)
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.feature_tree.commands import _context_manifest  # noqa: E402
from lib.feature_tree.content_addressed_writer import _write_content_addressed_bytes  # noqa: E402
from lib.feature_tree.nodes import discover_nodes  # noqa: E402
from lib.feature_tree.ownership import resolve_target_details  # noqa: E402

TARGET = "quwoquan_ops/cli/review_dispatch.py"
CHANGED = ["quwoquan_ops/cli/review_dispatch.py", "quwoquan_ops/cli/lib/review_fingerprint.py"]


def _owner_ref() -> str:
    nodes = discover_nodes()
    manifest = _context_manifest(TARGET, resolve_target_details(TARGET, nodes), nodes)
    path = _write_content_addressed_bytes(canonical_json_bytes(manifest))
    return path.relative_to(ROOT).as_posix()


def _candidate_ref(owner_ref: str, paths: list[str]) -> str:
    payload = build_candidate_evidence(owner_ref, paths, repo_root=ROOT)
    path = _write_content_addressed_bytes(canonical_json_bytes(payload), subdirectory="candidates/by-fingerprint")
    return path.relative_to(ROOT).as_posix()


def test_pre_owner_survives_mutation_then_candidate_drives_review() -> None:
    owner_ref = _owner_ref()
    candidate_ref = _candidate_ref(owner_ref, CHANGED)
    plan = review_dispatch.build_plan(
        __import__("yaml").safe_load((ROOT / ".agents/skills/review/references/registry.yaml").read_text()),
        "dev", "POST", None, CHANGED,
        context_manifest=json.loads((ROOT / owner_ref).read_text()),
        context_manifest_ref=owner_ref, candidate_evidence_ref=candidate_ref, scope=TARGET,
    )
    assert plan["owner_identity"]["ref"] == owner_ref
    assert plan["candidate_evidence_identity"]["ref"] == candidate_ref
    assert review_dispatch.validate_current_review_plan(
        plan, __import__("yaml").safe_load((ROOT / ".agents/skills/review/references/registry.yaml").read_text())
    )["digest"] == plan["fingerprint"]


def test_candidate_stale_after_bytes_change(tmp_path: Path) -> None:
    owner_ref = _owner_ref()
    candidate_ref = _candidate_ref(owner_ref, CHANGED)
    target = ROOT / CHANGED[0]
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n")
        with pytest.raises(CandidateEvidenceError) as stale:
            validate_candidate_ref(candidate_ref, repo_root=ROOT)
        assert stale.value.code == "CANDIDATE.STALE"
    finally:
        target.write_bytes(original)


def test_cross_owner_candidate_requires_split() -> None:
    owner_ref = _owner_ref()
    with pytest.raises(CandidateEvidenceError) as split:
        build_candidate_evidence(
            owner_ref, [TARGET, "quwoquan_app/scripts/device/dev_launch.sh"], repo_root=ROOT
        )
    assert split.value.code == "CANDIDATE.SPLIT_REQUIRED"


def test_absolute_and_relative_target_share_owner_ref_and_outside_rejected() -> None:
    nodes = discover_nodes()
    relative = _context_manifest(TARGET, resolve_target_details(TARGET, nodes), nodes)
    absolute = _context_manifest(str(ROOT / TARGET), resolve_target_details(str(ROOT / TARGET), nodes), nodes)
    assert canonical_json_bytes(relative) == canonical_json_bytes(absolute)
    with pytest.raises(ValueError, match="越出仓库"):
        resolve_target_details("/tmp/outside.py", nodes)


def test_legacy_cli_is_typed_migration_required() -> None:
    result = subprocess.run([sys.executable, "-B", "quwoquan_ops/cli/review_dispatch.py",
        "--workflow", "dev", "--segment", "POST", "--context-manifest", "legacy.json"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "IDENTITY.MIGRATION_REQUIRED" in result.stderr

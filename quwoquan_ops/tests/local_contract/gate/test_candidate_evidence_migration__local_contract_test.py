"""Candidate v2 atomic cross-Feature-owner local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t5
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t6
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t7
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t8
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t9
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

import review_dispatch  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version, validate_candidate_evidence_manifest,
)
from lib.candidate_evidence import (  # noqa: E402
    CandidateEvidenceError, build_candidate_evidence, validate_candidate_ref,
)
from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.feature_tree.commands import _context_manifest  # noqa: E402
from lib.feature_tree.content_addressed_writer import _write_content_addressed_bytes  # noqa: E402
from lib.feature_tree.nodes import discover_nodes  # noqa: E402
from lib.feature_tree.ownership import resolve_target_details  # noqa: E402

TARGET = "quwoquan_ops/cli/review_dispatch.py"
APP_PATH = "quwoquan_app/scripts/device/dev_launch.sh"
CHANGED = [TARGET, APP_PATH]


def _owner_ref(target: str = TARGET) -> str:
    nodes = discover_nodes()
    manifest = _context_manifest(target, resolve_target_details(target, nodes), nodes)
    path = _write_content_addressed_bytes(canonical_json_bytes(manifest))
    return path.relative_to(ROOT).as_posix()


def _candidate_ref(owner_ref: str, paths: list[str]) -> str:
    payload = build_candidate_evidence(owner_ref, paths, repo_root=ROOT)
    path = _write_content_addressed_bytes(
        canonical_json_bytes(payload), subdirectory="candidates/by-fingerprint"
    )
    return path.relative_to(ROOT).as_posix()


def _write_tampered_candidate(payload: dict) -> str:
    raw = canonical_json_bytes(payload)
    path = (
        ROOT
        / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/candidates/by-fingerprint"
        / f"{hashlib.sha256(raw).hexdigest()}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path.relative_to(ROOT).as_posix()


def test_detached_github_pull_request_uses_reviewed_head_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_HEAD_REF", "lane/engineering")
    owner_ref = _owner_ref()
    original_run = subprocess.run

    def detached_symbolic_ref(*args: object, **kwargs: object):
        command = args[0]
        if isinstance(command, list) and "symbolic-ref" in command:
            return subprocess.CompletedProcess(
                args=command, returncode=1, stdout="", stderr=""
            )
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", detached_symbolic_ref)

    candidate = build_candidate_evidence(owner_ref, CHANGED, repo_root=ROOT)

    assert candidate["delivery_owner"] == "lane/engineering"
    assert candidate["lead_lane"] == "lane/engineering"


def test_detached_non_pull_request_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    owner_ref = _owner_ref()
    original_run = subprocess.run

    def detached_symbolic_ref(*args: object, **kwargs: object):
        command = args[0]
        if isinstance(command, list) and "symbolic-ref" in command:
            return subprocess.CompletedProcess(
                args=command, returncode=1, stdout="", stderr=""
            )
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", detached_symbolic_ref)

    with pytest.raises(CandidateEvidenceError) as detached:
        build_candidate_evidence(owner_ref, CHANGED, repo_root=ROOT)

    assert detached.value.code == "CANDIDATE.OWNER_DRIFT"


def test_cross_owner_candidate_is_one_atomic_review_identity() -> None:
    owner_ref = _owner_ref()
    candidate_ref = _candidate_ref(owner_ref, CHANGED)
    _, _, candidate, _ = validate_candidate_ref(
        candidate_ref,
        repo_root=ROOT,
        expected_owner_identity_ref=owner_ref,
        expected_changed_paths=CHANGED,
    )
    assert candidate["schema_version"] == 2
    assert candidate["delivery_owner"] == "lane/engineering"
    assert candidate["lead_lane"] == "lane/engineering"
    assert "changed_paths" not in candidate
    assert "owner_chain" not in candidate
    groups = candidate["impacted_owner_groups"]
    assert len(groups) == 2
    assert [group["owner_identity"]["resolved_owner"] for group in groups] == sorted(
        [group["owner_identity"]["resolved_owner"] for group in groups],
        key=lambda item: item.encode("utf-8"),
    )
    assert all(set(group) == {"owner_identity", "paths"} for group in groups)
    assert all(
        set(group["owner_identity"]) == {"resolved_owner", "owner_chain_digest"}
        and group["owner_identity"]["owner_chain_digest"].startswith("sha256:")
        for group in groups
    )
    assert sorted(path for group in groups for path in group["paths"]) == sorted(CHANGED)
    assert candidate["resolved_owner"] in {
        group["owner_identity"]["resolved_owner"] for group in groups
    }
    assert "impact_plan" not in candidate
    assert candidate["impact_plan_identity"]["digest"].startswith("sha256:")

    plan = review_dispatch.build_plan(
        __import__("yaml").safe_load(
            (ROOT / ".agents/skills/review/references/registry.yaml").read_text()
        ),
        "dev", "POST", None, CHANGED,
        context_manifest=json.loads((ROOT / owner_ref).read_text()),
        context_manifest_ref=owner_ref,
        candidate_evidence_ref=candidate_ref,
        scope=TARGET,
    )
    identity = plan["candidate_evidence_identity"]
    assert identity["schema_version"] == 2
    assert identity["delivery_owner"] == "lane/engineering"
    assert identity["lead_lane"] == "lane/engineering"
    assert identity["impacted_owner_groups_digest"].startswith("sha256:")
    assert identity["changed_paths_digest"].startswith("sha256:")
    assert review_dispatch.validate_current_review_plan(
        plan,
        __import__("yaml").safe_load(
            (ROOT / ".agents/skills/review/references/registry.yaml").read_text()
        ),
    )["digest"] == plan["fingerprint"]


def test_empty_changed_paths_has_independent_terminal() -> None:
    with pytest.raises(CandidateEvidenceError) as empty:
        build_candidate_evidence(_owner_ref(), [], repo_root=ROOT)
    assert empty.value.code == "CANDIDATE.EMPTY_CHANGED_PATHS"


def test_no_owner_and_owner_ambiguity_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_ref = _owner_ref()
    with pytest.raises(CandidateEvidenceError) as missing:
        build_candidate_evidence(owner_ref, ["unowned-candidate-v2.txt", TARGET], repo_root=ROOT)
    assert missing.value.code == "CANDIDATE.OWNER_RESOLUTION_FAILED"

    from lib.feature_tree import ownership
    original = ownership.resolve_target_details

    def ambiguous(raw: str | Path, nodes):
        if str(raw) == APP_PATH:
            raise ValueError("GATE_BLOCK: fixture owner ambiguity")
        return original(raw, nodes)

    monkeypatch.setattr(ownership, "resolve_target_details", ambiguous)
    with pytest.raises(CandidateEvidenceError) as ambiguity:
        build_candidate_evidence(owner_ref, CHANGED, repo_root=ROOT)
    assert ambiguity.value.code == "CANDIDATE.OWNER_RESOLUTION_FAILED"


def test_primary_owner_must_be_impacted() -> None:
    with pytest.raises(CandidateEvidenceError) as drift:
        build_candidate_evidence(_owner_ref(), [APP_PATH], repo_root=ROOT)
    assert drift.value.code == "CANDIDATE.OWNER_DRIFT"


def test_group_path_omission_duplicate_and_tamper_are_rejected() -> None:
    owner_ref = _owner_ref()
    candidate = build_candidate_evidence(owner_ref, CHANGED, repo_root=ROOT)
    omitted = json.loads(json.dumps(candidate))
    omitted["impacted_owner_groups"] = [
        group for group in omitted["impacted_owner_groups"]
        if group["owner_identity"]["resolved_owner"] == omitted["resolved_owner"]
    ]
    omitted_ref = _write_tampered_candidate(omitted)
    with pytest.raises(CandidateEvidenceError) as missing:
        validate_candidate_ref(
            omitted_ref, repo_root=ROOT, expected_changed_paths=CHANGED
        )
    assert missing.value.code == "CANDIDATE.STALE"

    duplicate = json.loads(json.dumps(candidate))
    duplicate["impacted_owner_groups"][1]["paths"].append(
        duplicate["impacted_owner_groups"][0]["paths"][0]
    )
    duplicate["impacted_owner_groups"][1]["paths"].sort()
    with pytest.raises(ValueError, match="无重复覆盖"):
        validate_candidate_evidence_manifest(duplicate)

    tampered = json.loads(json.dumps(candidate))
    tampered["impacted_owner_groups"][0]["owner_identity"]["owner_chain_digest"] = (
        "sha256:" + "0" * 64
    )
    ref = _write_tampered_candidate(tampered)
    with pytest.raises(CandidateEvidenceError) as stale:
        validate_candidate_ref(ref, repo_root=ROOT)
    assert stale.value.code == "CANDIDATE.OWNER_DRIFT"

def test_candidate_stale_after_bytes_change() -> None:
    owner_ref = _owner_ref()
    candidate_ref = _candidate_ref(owner_ref, CHANGED)
    target = ROOT / TARGET
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n")
        with pytest.raises(CandidateEvidenceError) as stale:
            validate_candidate_ref(candidate_ref, repo_root=ROOT)
        assert stale.value.code == "CANDIDATE.STALE"
    finally:
        target.write_bytes(original)


def test_old_candidate_schema_is_rejected() -> None:
    payload = build_candidate_evidence(_owner_ref(), CHANGED, repo_root=ROOT)
    payload["schema_version"] = 1
    ref = _write_tampered_candidate(payload)
    with pytest.raises(CandidateEvidenceError) as migration:
        validate_candidate_ref(ref, repo_root=ROOT)
    assert migration.value.code == "IDENTITY.MIGRATION_REQUIRED"


def test_absolute_and_relative_target_share_owner_ref_and_outside_rejected() -> None:
    nodes = discover_nodes()
    relative = _context_manifest(TARGET, resolve_target_details(TARGET, nodes), nodes)
    absolute = _context_manifest(
        str(ROOT / TARGET), resolve_target_details(str(ROOT / TARGET), nodes), nodes
    )
    assert canonical_json_bytes(relative) == canonical_json_bytes(absolute)
    with pytest.raises(ValueError, match="越出仓库"):
        resolve_target_details("/tmp/outside.py", nodes)


def test_legacy_cli_is_typed_migration_required() -> None:
    result = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/cli/review_dispatch.py",
         "--workflow", "dev", "--segment", "POST", "--context-manifest", "legacy.json"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "IDENTITY.MIGRATION_REQUIRED" in result.stderr

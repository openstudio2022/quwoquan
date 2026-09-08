"""Candidate v3 atomic cross-Feature-owner lossless closure contract.

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
    CandidateEvidenceError, _delivery_identity, build_candidate_evidence,
    validate_candidate_ref, load_candidate_path_set, _path_set_identity,
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
    assert candidate["schema_version"] == 3
    # 最小 v2 中 delivery owner 与 lead lane 同为 current logical lane；hosted
    # PR job 与本地 lane worktree 都可能是六条 lane 中任一条，断言不得钉死某条 lane。
    current_lane, current_lead, _ = _delivery_identity(repo_root=ROOT)
    assert current_lane.startswith("lane/") and current_lane == current_lead
    assert candidate["delivery_owner"] == current_lane
    assert candidate["lead_lane"] == current_lane
    assert "changed_paths" not in candidate
    assert "owner_chain" not in candidate
    groups = load_candidate_path_set(candidate, repo_root=ROOT)["impacted_owner_groups"]
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
    assert identity["schema_version"] == 3
    assert identity["delivery_owner"] == current_lane
    assert identity["lead_lane"] == current_lane
    assert identity["impacted_owner_groups_digest"].startswith("sha256:")
    assert identity["changed_paths_digest"].startswith("sha256:")
    assert review_dispatch.validate_current_review_plan(
        plan,
        __import__("yaml").safe_load(
            (ROOT / ".agents/skills/review/references/registry.yaml").read_text()
        ),
    )["digest"] == plan["fingerprint"]


def test_lossless_reference_closure_is_required_and_portable() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    from lib.candidate_evidence import export_candidate_closure, validate_candidate_closure

    owner_ref = _owner_ref()
    ref = _candidate_ref(owner_ref, CHANGED)
    closure = export_candidate_closure(ref, repo_root=ROOT)
    candidate, paths = validate_candidate_closure(
        closure, candidate_ref=ref, owner_identity_ref=owner_ref,
    )
    assert paths == sorted(CHANGED)
    assert candidate["schema_version"] == 3
    assert "impacted_owner_groups" not in candidate
    assert candidate["path_set_identity"]["path_count"] == len(CHANGED)
    missing = [item for item in closure if item["ref"] != candidate["path_set_identity"]["ref"]]
    with pytest.raises(CandidateEvidenceError, match="closure"):
        validate_candidate_closure(missing, candidate_ref=ref, owner_identity_ref=owner_ref)


@pytest.mark.parametrize("fault", ["missing", "tamper", "oversized", "symlink", "hardlink", "directory-symlink"])
def test_path_object_storage_faults_fail_closed(tmp_path: Path, fault: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    import os
    owner_ref = _owner_ref()
    candidate = build_candidate_evidence(owner_ref, CHANGED, repo_root=ROOT)
    ref = _write_tampered_candidate(candidate)
    original = ROOT / candidate["path_set_identity"]["ref"]
    copied = tmp_path / candidate["path_set_identity"]["ref"]
    copied.parent.mkdir(parents=True)
    if fault != "missing":
        copied.write_bytes(original.read_bytes())
    if fault == "tamper":
        copied.write_bytes(b"{}")
    elif fault == "oversized":
        with copied.open("ab") as stream:
            stream.write(b"x")
    elif fault in ("symlink", "hardlink"):
        target = tmp_path / "external.json"
        target.write_bytes(original.read_bytes())
        copied.unlink()
        copied.symlink_to(target) if fault == "symlink" else os.link(target, copied)
    elif fault == "directory-symlink":
        directory = copied.parent
        relocated = tmp_path / "relocated"
        directory.rename(relocated)
        directory.symlink_to(relocated, target_is_directory=True)
    candidate_path = tmp_path / ref
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_bytes(canonical_json_bytes(candidate))
    with pytest.raises(CandidateEvidenceError) as failure:
        validate_candidate_ref(ref, repo_root=tmp_path)
    assert failure.value.code == "CANDIDATE.STALE"


@pytest.mark.parametrize("field", ["path_count", "byte_count", "changed_paths_digest", "impacted_owner_groups_digest"])
def test_path_object_identity_tamper_is_rejected(field: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    candidate = build_candidate_evidence(_owner_ref(), CHANGED, repo_root=ROOT)
    identity = candidate["path_set_identity"]
    identity[field] = identity[field] + 1 if isinstance(identity[field], int) else "sha256:" + "0" * 64
    with pytest.raises(CandidateEvidenceError):
        validate_candidate_ref(_write_tampered_candidate(candidate), repo_root=ROOT)


def test_large_candidate_preserves_all_paths_under_manifest_budget() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    # 确定性大路径集合（可表示已删除路径），不依赖运行测试时PR大小。
    # 正式准出仍另由当前完整merge-base→HEAD范围生成，不能以本fixture替代。
    paths = [TARGET, *[f"quwoquan_ops/cli/{'long-path-' * 10}{index:04}.py" for index in range(1700)]]
    assert len(canonical_json_bytes(sorted(paths))) > 65536
    owner_ref = _owner_ref()
    result = subprocess.run([sys.executable, "-B", str(ROOT / "quwoquan_ops/cli/feature_tree.py"), "candidate-evidence", "--owner-identity", owner_ref,
                             *[arg for path in paths for arg in ("--changed-path", path)]],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    ref = result.stdout.strip()
    _, raw, candidate, _ = validate_candidate_ref(ref, repo_root=ROOT, expected_changed_paths=paths)
    document = load_candidate_path_set(candidate, repo_root=ROOT)
    restored = sorted(p for group in document["impacted_owner_groups"] for p in group["paths"])
    assert restored == sorted(paths)
    assert len(raw) <= 65536
    assert candidate["path_set_identity"]["byte_count"] > len(raw)


def test_path_object_predecessor_and_escape_rejected() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    from lib.candidate_evidence import _validate_path_set
    candidate = build_candidate_evidence(_owner_ref(), CHANGED, repo_root=ROOT)
    document = load_candidate_path_set(candidate, repo_root=ROOT)
    document["owner_identity_canonical_bytes_sha256"] = "sha256:" + "0" * 64
    candidate["path_set_identity"] = _path_set_identity(document)
    with pytest.raises(CandidateEvidenceError, match="predecessor"):
        _validate_path_set(canonical_json_bytes(document), candidate)
    document["owner_identity_canonical_bytes_sha256"] = candidate["owner_identity_canonical_bytes_sha256"]
    document["impacted_owner_groups"][0]["paths"] = ["../escape"]
    candidate["path_set_identity"] = _path_set_identity(document)
    with pytest.raises(CandidateEvidenceError, match="路径非法"):
        _validate_path_set(canonical_json_bytes(document), candidate)


def test_path_object_concurrent_publish_and_consumer_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    from concurrent.futures import ThreadPoolExecutor
    from lib.feature_tree import content_addressed_writer
    candidate = build_candidate_evidence(_owner_ref(), CHANGED, repo_root=ROOT)
    document = load_candidate_path_set(candidate, repo_root=ROOT)
    raw = canonical_json_bytes(document)
    with ThreadPoolExecutor(max_workers=4) as pool:
        refs = list(pool.map(lambda _: _write_content_addressed_bytes(raw, subdirectory="candidate-paths"), range(4)))
    assert len(set(refs)) == 1
    ref = _write_tampered_candidate(candidate)
    def reject_write(*args: object, **kwargs: object) -> None:
        raise AssertionError("consumer must not publish")
    monkeypatch.setattr(content_addressed_writer, "_write_content_addressed_bytes", reject_write)
    validate_candidate_ref(ref, repo_root=ROOT)


def test_owner_batch_rejects_rule_drift_and_does_not_cache_between_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    from lib.feature_tree import nodes as node_module, ownership
    node = node_module.Node(1, "batch", tmp_path)
    node.spec.write_text("first")
    monkeypatch.setattr(node_module, "discover_nodes", lambda: [node])
    monkeypatch.setattr(ownership, "engineering_roots", lambda n: [n.spec.read_text()])
    with pytest.raises(ValueError, match="漂移"):
        with ownership.ownership_batch([node]):
            assert ownership._engineering_roots(node) == ["first"]
            node.spec.write_text("second")
    with ownership.ownership_batch([node]):
        assert ownership._engineering_roots(node) == ["second"]


@pytest.mark.parametrize("fault", ["missing", "tamper"])
def test_review_and_runner_require_path_object_before_evidence(monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    import evidence_runner
    import lib.candidate_evidence as candidate_module
    import yaml
    owner_ref = _owner_ref()
    candidate_ref = _candidate_ref(owner_ref, CHANGED)
    registry = yaml.safe_load((ROOT / ".agents/skills/review/references/registry.yaml").read_text())
    def plan():
        return review_dispatch.build_plan(
            registry, "dev", "POST", None, CHANGED,
            context_manifest=json.loads((ROOT / owner_ref).read_text()),
            context_manifest_ref=owner_ref, candidate_evidence_ref=candidate_ref, scope=TARGET,
        )
    current_plan = plan()
    original_read = candidate_module.read_repo_relative_regular_single_link
    def faulty_read(root, ref, **kwargs):
        if "/candidate-paths/" in ref:
            if fault == "missing":
                raise FileNotFoundError(ref)
            return b"{}"
        return original_read(root, ref, **kwargs)
    def no_command(*args, **kwargs):
        raise AssertionError("缺失闭包不得进入named evidence执行")
    monkeypatch.setattr(candidate_module, "read_repo_relative_regular_single_link", faulty_read)
    monkeypatch.setattr(evidence_runner, "run_command", no_command)
    with pytest.raises(review_dispatch.ReviewDispatchError) as refusal:
        plan()
    assert refusal.value.code == "CANDIDATE.STALE"
    with pytest.raises(evidence_runner.EvidenceRunnerError, match="CANDIDATE.STALE"):
        evidence_runner.run_plan(current_plan, registry=registry, cwd=ROOT,
                                 plan_bytes=canonical_json_bytes(current_plan), plan_ref="test-fixture:exact-plan")
    from lib.local_readiness.admission import owner_manifest_assets
    from lib.local_readiness.core import LocalReadinessError
    with pytest.raises(LocalReadinessError, match="candidate evidence 非 current"):
        owner_manifest_assets(ROOT / owner_ref, repo_root=ROOT, candidate_evidence=ROOT / candidate_ref)


def test_referenced_owner_receipt_is_bounded_and_portable(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    from lib.agent_governance_contract import contract_section
    from lib.candidate_evidence import export_candidate_closure, validate_candidate_closure
    from lib.feature_context_fingerprint import referenced_fingerprint_binding, resolve_fingerprint_binding
    from lib.evidence_fingerprint import EvidenceFingerprintError
    owner = json.loads((ROOT / _owner_ref()).read_text())
    receipt = owner["evidence_fingerprint"]["receipt"]
    receipt_path = _write_content_addressed_bytes(canonical_json_bytes(receipt), subdirectory="receipts")
    receipt_ref = receipt_path.relative_to(ROOT).as_posix()
    owner["evidence_fingerprint"] = referenced_fingerprint_binding(receipt, receipt_ref=receipt_ref)
    owner_ref = _write_content_addressed_bytes(canonical_json_bytes(owner)).relative_to(ROOT).as_posix()
    candidate_ref = _candidate_ref(owner_ref, CHANGED)
    closure = export_candidate_closure(candidate_ref, repo_root=ROOT)
    assert len(closure) == 4
    assert validate_candidate_closure(closure, candidate_ref=candidate_ref, owner_identity_ref=owner_ref)[1] == sorted(CHANGED)
    hostile = tmp_path / receipt_ref
    hostile.parent.mkdir(parents=True)
    with hostile.open("wb") as stream:
        stream.truncate(contract_section("feature_context_manifest")["fingerprint_receipt_max_bytes"] + 1)
    with pytest.raises(EvidenceFingerprintError, match="读取字节边界"):
        resolve_fingerprint_binding(owner["evidence_fingerprint"], repo_root=tmp_path)


def test_review_cli_owner_read_rejects_oversized_before_json(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    from lib.review_dispatch_cli import _load_json
    owner_ref = _owner_ref()
    hostile = tmp_path / owner_ref
    hostile.parent.mkdir(parents=True)
    with hostile.open("wb") as stream:
        stream.truncate(8193)
    def refuse(code, message):
        raise review_dispatch.ReviewDispatchError(code, message)
    with pytest.raises(review_dispatch.ReviewDispatchError) as failure:
        _load_json(owner_ref, label="owner_identity", refuse=refuse, repo_root=tmp_path)
    assert failure.value.code == "REVIEW.OWNER_MANIFEST_INVALID"
    assert "读取字节边界" in failure.value.message


@pytest.mark.parametrize("fault", ["oversized", "symlink", "hardlink", "directory-symlink"])
def test_readiness_owner_read_rejects_unsafe_before_json(tmp_path: Path, fault: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t10
    import os
    from lib.agent_governance_contract import contract_section
    from lib.local_readiness.admission import owner_manifest_assets
    from lib.local_readiness.core import LocalReadinessError

    owner_ref = _owner_ref()
    hostile = tmp_path / owner_ref
    hostile.parent.mkdir(parents=True)
    original = tmp_path / "original.json"
    original.write_bytes((ROOT / owner_ref).read_bytes())
    if fault == "oversized":
        with hostile.open("wb") as stream:
            stream.truncate(contract_section("feature_context_manifest")["max_bytes"] + 1)
    elif fault == "symlink":
        hostile.symlink_to(original)
    elif fault == "hardlink":
        os.link(original, hostile)
    else:
        directory = tmp_path / "redirected"
        hostile.parent.rename(directory)
        hostile.parent.symlink_to(directory, target_is_directory=True)
        hostile.write_bytes(original.read_bytes())
    with pytest.raises(LocalReadinessError, match="owner manifest 非 current"):
        owner_manifest_assets(hostile, repo_root=tmp_path)


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
    document = load_candidate_path_set(candidate, repo_root=ROOT)
    def with_document(value: dict) -> str:
        updated = json.loads(json.dumps(candidate))
        updated["path_set_identity"] = _path_set_identity(value)
        _write_content_addressed_bytes(canonical_json_bytes(value), subdirectory="candidate-paths")
        return _write_tampered_candidate(updated)
    omitted = json.loads(json.dumps(document))
    omitted["impacted_owner_groups"] = [
        group for group in omitted["impacted_owner_groups"]
        if group["owner_identity"]["resolved_owner"] == candidate["resolved_owner"]
    ]
    omitted_ref = with_document(omitted)
    with pytest.raises(CandidateEvidenceError) as missing:
        validate_candidate_ref(
            omitted_ref, repo_root=ROOT, expected_changed_paths=CHANGED
        )
    assert missing.value.code == "CANDIDATE.STALE"

    duplicate = json.loads(json.dumps(document))
    duplicate["impacted_owner_groups"][1]["paths"].append(
        duplicate["impacted_owner_groups"][0]["paths"][0]
    )
    duplicate["impacted_owner_groups"][1]["paths"].sort()
    with pytest.raises(ValueError, match="无重复覆盖"):
        from lib.agent_governance_contract import validate_candidate_path_set
        validate_candidate_path_set(duplicate)

    tampered = json.loads(json.dumps(document))
    tampered["impacted_owner_groups"][0]["owner_identity"]["owner_chain_digest"] = (
        "sha256:" + "0" * 64
    )
    ref = with_document(tampered)
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


def test_context_batch_preserves_anchors_and_refreshes_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib import candidate_evidence
    from lib.evidence_fingerprint import snapshot_path, snapshot_paths

    (tmp_path / "context.md").write_text("before", encoding="utf-8")
    contexts = [
        {"path": "context.md", "anchor": "REQ-002", "kind": "spec"},
        {"path": "missing.md", "anchor": None, "kind": "design"},
        {"path": "context.md", "anchor": "GWT-002", "kind": "spec"},
    ]
    expected = [
        {**item, **{key: snapshot_path(item["path"], repo_root=tmp_path)[key]
                   for key in ("exists", "content_digest")}}
        for item in contexts
    ]
    calls = []

    def batch(paths, *, repo_root):
        calls.append(list(paths))
        return snapshot_paths(paths, repo_root=repo_root)

    monkeypatch.setattr(candidate_evidence, "snapshot_paths", batch)
    current = {"canonical_contexts": contexts}
    assert candidate_evidence._context_snapshots(current, repo_root=tmp_path) == expected
    assert calls == [[item["path"] for item in contexts]]
    (tmp_path / "context.md").write_text("after", encoding="utf-8")
    refreshed = candidate_evidence._context_snapshots(current, repo_root=tmp_path)
    assert len(calls) == 2
    assert refreshed[0]["content_digest"] != expected[0]["content_digest"]
    assert refreshed[0]["content_digest"] == refreshed[2]["content_digest"]
    assert [item["anchor"] for item in refreshed] == [item["anchor"] for item in contexts]


def test_owner_assets_batch_is_equivalent_and_rejects_later_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib import feature_context_fingerprint as owner_fingerprint
    from lib.evidence_fingerprint import EvidenceFingerprintError, canonical_digest, snapshot_path, snapshot_paths

    owner = json.loads((ROOT / _owner_ref()).read_bytes())
    generator, contract = owner_fingerprint.GENERATOR_PATH, owner_fingerprint.CONTRACT_PATH
    expected = canonical_digest({
        "generator": snapshot_path(generator, repo_root=ROOT),
        "contract": snapshot_path(contract, repo_root=ROOT),
    })
    calls = []

    def batch(paths, *, repo_root):
        calls.append(list(paths))
        values = snapshot_paths(paths, repo_root=repo_root)
        if len(calls) > 1:
            values[0]["content_digest"] = canonical_digest("changed canonical asset")
        return values

    monkeypatch.setattr(owner_fingerprint, "snapshot_paths", batch)
    actual = owner_fingerprint.validate_current_feature_context_fingerprint(owner, repo_root=ROOT)
    assert calls == [[generator, contract]]
    assert actual["digest_payload"]["assets"]["review_assets_digest"] == expected
    assert actual["digest_payload"]["execution"]["generator_digest"] == expected
    with pytest.raises(EvidenceFingerprintError, match="owner identity EvidenceFingerprint"):
        owner_fingerprint.validate_current_feature_context_fingerprint(owner, repo_root=ROOT)
    assert len(calls) == 2


def test_review_assets_batch_matches_single_reads_and_rechecks_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib import review_fingerprint
    from lib.evidence_fingerprint import canonical_digest, snapshot_path, snapshot_paths

    reviewer = {
        "role": "developer", "kind": "primary", "required": True, "profile": None,
        "checklist": "roles/developer/checklists/dev/base.md",
    }
    inputs = dict(
        workflow="dev", deliverable="implementation", scope=TARGET, owner_identity={},
        candidate_evidence_identity={}, human_decision_projection={}, terminal={},
        changed_paths=[], profiles=[], contexts=[], initial_reviewers=[reviewer, reviewer], evidence=[],
    )
    calls = []

    def single_reads(paths, *, repo_root):
        return [snapshot_path(path, repo_root=repo_root) for path in paths]

    monkeypatch.setattr(review_fingerprint, "snapshot_paths", single_reads)
    expected = review_fingerprint.build_review_fingerprint(**inputs)

    def batch(paths, *, repo_root):
        calls.append(list(paths))
        values = snapshot_paths(paths, repo_root=repo_root)
        if len(calls) > 1:
            values[0]["content_digest"] = canonical_digest("changed review asset")
        return values

    monkeypatch.setattr(review_fingerprint, "snapshot_paths", batch)
    actual = review_fingerprint.build_review_fingerprint(**inputs)
    assert actual["digest_payload"] == expected["digest_payload"]
    assert len(calls) == 1
    assert len(calls[0]) > len(set(calls[0]))
    assert review_fingerprint.build_review_fingerprint(**inputs)["digest"] != actual["digest"]
    assert len(calls) == 2


@pytest.mark.parametrize("state", ["clean", "ignored", "nested-untracked", "modified", "deleted", "renamed", "symlink"])
def test_runner_clean_query_preserves_whole_tree_truth(tmp_path: Path, state: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-007.t1
    import evidence_runner as runner

    def git(*args: str) -> bytes:
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, check=True).stdout

    git("init", "-q")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("original", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    git("add", "tracked.txt", ".gitignore")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    clean = runner._workspace_source_classification(tmp_path)
    assert clean["repository_clean"] is True
    if state in {"nested-untracked", "ignored"}:
        path = tmp_path / ("ignored" if state == "ignored" else "outside-candidate") / "nested/file.txt"
        path.parent.mkdir(parents=True)
        path.write_text("untracked", encoding="utf-8")
    elif state == "modified":
        tracked.write_text("modified", encoding="utf-8")
    elif state == "deleted":
        tracked.unlink()
    elif state == "renamed":
        git("mv", "tracked.txt", "renamed.txt")
    elif state == "symlink":
        (tmp_path / "broken-link").symlink_to("missing-target")
    exhaustive_clean = git("--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all") == b""
    index = tmp_path / ".git/index"
    before = index.read_bytes()
    # 只读查询即使存在 writer 锁也不得删除、改写或抢占它。
    lock = tmp_path / ".git/index.lock"
    lock.write_bytes(b"other-writer")
    actual = runner._workspace_source_classification(tmp_path)
    assert actual["repository_clean"] is exhaustive_clean
    assert actual["repository_clean"] is (state in {"clean", "ignored"})
    assert index.read_bytes() == before
    assert lock.read_bytes() == b"other-writer"
    if exhaustive_clean:
        runner._assert_source_head(clean, tmp_path)
    else:
        with pytest.raises(runner.EvidenceRunnerError, match="workspace 在命令后变脏"):
            runner._assert_source_head(clean, tmp_path)


def test_old_candidate_schema_is_rejected() -> None:
    payload = build_candidate_evidence(_owner_ref(), CHANGED, repo_root=ROOT)
    payload["schema_version"] = 2
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

# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from content.execution import task_init
from content.source import atomic_source_cli
from core import paths
from core.schema import assert_valid, load_schema, validate_strict
from verify import stage_artifacts, verify_source_plan, verify_task_init_contract

EXECUTION_ID = "20260903--travel-video-hard-cut--test-region-a--pilot-001"
FAMILY_REF = "content/travel/video/video"
TARGET_REF = "posts/video/风光/西湖秋色/1"


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


@pytest.fixture
def initialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    output = tmp_path / ".qwq_output"
    tasks = output / "data/tasks"
    local = output / "data/local"
    repo = tmp_path / "repo"
    families = repo / "families"
    family_path = families / f"{FAMILY_REF}.recipe.yaml"
    family_path.parent.mkdir(parents=True)
    family_path.write_text("name: video\n", encoding="utf-8")
    for owner in (paths, task_init.paths, verify_task_init_contract.paths, verify_source_plan.paths):
        monkeypatch.setattr(owner, "OUTPUT_ROOT", output)
        monkeypatch.setattr(owner, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", local)
    monkeypatch.setattr(task_init.paths, "DATA_LOCAL_ROOT", local)
    monkeypatch.setattr(paths, "REPO_ROOT", repo)
    monkeypatch.setattr(task_init.paths, "REPO_ROOT", repo)
    monkeypatch.setattr(paths, "FAMILIES_ROOT", families)
    monkeypatch.setattr(task_init.paths, "FAMILIES_ROOT", families)
    monkeypatch.setattr(verify_task_init_contract.paths, "FAMILIES_ROOT", families)

    demand = {
        "schema": "quwoquan_data.carrier_demand",
        "status": "confirmed",
        "executionId": EXECUTION_ID,
        "carrier": "video",
        "familyRef": FAMILY_REF,
        "quota": 1,
        "retryOf": None,
    }
    candidates = {
        "schema": "quwoquan_data.immutable_candidate_bindings",
        "executionId": EXECUTION_ID,
        "carrier": "video",
        "entityCatalogDigest": "sha256:" + "a" * 64,
        "candidateCount": 1,
        "targets": [{
            "name": "西湖",
            "entityType": "地点/景区",
            "publishAngle": "风光",
            "publishTitle": "西湖秋色",
            "publishSeq": 1,
        }],
    }
    demand_path = output / "inputs/demand.json"
    candidate_path = output / "inputs/candidates.json"
    _write(demand_path, demand)
    _write(candidate_path, candidates)
    task_init.initialize_task(
        carrier_demand_path=demand_path,
        candidate_bindings_path=candidate_path,
    )
    return tasks / EXECUTION_ID, candidate_path


def test_task_init_contract_validates_current_three_file_bytes(initialized: tuple[Path, Path]) -> None:
    root, candidate_path = initialized
    assert verify_task_init_contract.issues(EXECUTION_ID) == []

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["targets"][0]["publishTitle"] = "漂移"
    _write(candidate_path, candidate)
    failures = verify_task_init_contract.issues(EXECUTION_ID)
    assert any("immutableCandidateBindings exact digest drift" in item for item in failures)
    assert any("candidate projection drift" in item for item in failures)

    manifest = json.loads((root / "execution_manifest.json").read_text(encoding="utf-8"))
    manifest["targetSet"]["digest"] = "sha256:" + "b" * 64
    _write(root / "execution_manifest.json", manifest)
    assert any("targetSet exact digest drift" in item for item in verify_task_init_contract.issues(EXECUTION_ID))


def _source_plan() -> dict[str, object]:
    return {
        "schema": "quwoquan_data.source_plan",
        "executionId": EXECUTION_ID,
        "targetRef": TARGET_REF,
        "carrier": "video",
        "candidates": [{
            "sourceId": "west-lake-video",
            "title": "西湖视频底稿",
            "url": "https://example.com/video",
            "purpose": "视频底稿",
            "sourceClass": "official",
            "sourceUseMode": "licensed_adaptation",
            "rightsClue": "terms page",
        }],
    }


def test_source_plan_uses_exact_hashed_target_layout(initialized: tuple[Path, Path]) -> None:
    root, _ = initialized
    relative = verify_source_plan.plan_ref(TARGET_REF)
    assert relative == f"sources/plans/{hashlib.sha256(TARGET_REF.encode()).hexdigest()}.json"
    _write(root / relative, _source_plan())
    assert verify_source_plan.issues(EXECUTION_ID) == []

    wrong = dict(_source_plan(), targetRef="posts/video/风光/其它/1")
    _write(root / relative, wrong)
    assert any("targetRef drift" in item for item in verify_source_plan.issues(EXECUTION_ID))

    _write(root / relative, _source_plan())
    _write(root / "sources/plans/" / ("f" * 64 + ".json"), _source_plan())
    assert any("undeclared source plan" in item for item in verify_source_plan.issues(EXECUTION_ID))


def test_source_plan_writer_binds_target_set_and_is_create_once(
    initialized: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = initialized
    monkeypatch.setattr(atomic_source_cli, "execution_root", lambda _execution_id: root)
    plan_path = tmp_path / "plan.json"
    _write(plan_path, _source_plan())
    args = type("Args", (), {"input": str(plan_path)})()

    atomic_source_cli.handle_write_source_plan(args)
    expected = root / verify_source_plan.plan_ref(TARGET_REF)
    assert expected.read_bytes() == _canonical_bytes(_source_plan())
    assert not (root / "source_plans").exists()
    atomic_source_cli.handle_write_source_plan(args)

    drift_cases = (
        dict(_source_plan(), carrier="article"),
        dict(_source_plan(), targetRef="posts/video/风光/其它/1"),
    )
    for index, drifted in enumerate(drift_cases):
        drift_path = tmp_path / f"drift-{index}.json"
        _write(drift_path, drifted)
        args.input = str(drift_path)
        with pytest.raises(SystemExit, match="GATE_BLOCK"):
            atomic_source_cli.handle_write_source_plan(args)

    changed = _source_plan()
    changed["candidates"][0]["title"] = "冲突"
    conflict_path = tmp_path / "conflict.json"
    _write(conflict_path, changed)
    args.input = str(conflict_path)
    with pytest.raises(SystemExit, match="create-once collision"):
        atomic_source_cli.handle_write_source_plan(args)

    target_set = json.loads((root / "0.plan/target_set.json").read_text(encoding="utf-8"))
    target_set["executionId"] = "20260903--travel-video-other--test-region-a--pilot-001"
    _write(root / "0.plan/target_set.json", target_set)
    args.input = str(plan_path)
    with pytest.raises(SystemExit, match="target_set executionId"):
        atomic_source_cli.handle_write_source_plan(args)


def test_source_plan_writer_rejects_symlinked_plan_directory(
    initialized: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = initialized
    monkeypatch.setattr(atomic_source_cli, "execution_root", lambda _execution_id: root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "sources").mkdir()
    (root / "sources/plans").symlink_to(outside, target_is_directory=True)

    plan_path = tmp_path / "plan.json"
    _write(plan_path, _source_plan())
    args = type("Args", (), {"input": str(plan_path)})()

    with pytest.raises(SystemExit, match="GATE_BLOCK"):
        atomic_source_cli.handle_write_source_plan(args)
    assert list(outside.iterdir()) == []


def test_entity_page_input_base_draft_one_of_is_exclusive() -> None:
    schema = load_schema("content", "entity_page_input")
    base_draft_schema = schema["properties"]["payload"]["properties"]["baseDraft"]
    complete = {
        "sourceRef": "sources/west-lake/source.md",
        "primaryEvidenceRef": "entities/地点/景区/西湖/2.quality/quality_analysis.json",
        "entityName": "西湖",
        "sourceKind": "wikipedia",
        "extractor": "wikipedia_api",
        "canonicalUrl": "https://zh.wikipedia.org/wiki/西湖",
        "sourceTitle": "西湖（维基百科）",
        "policyRevision": "encyclopedia-primary",
        "text": "西湖位于杭州。",
    }

    empty_branch, complete_branch = base_draft_schema["oneOf"]
    assert validate_strict({}, empty_branch, _root_schema=schema) == []
    assert validate_strict({}, complete_branch, _root_schema=schema)
    assert validate_strict(complete, empty_branch, _root_schema=schema)
    assert validate_strict(complete, complete_branch, _root_schema=schema) == []
    assert validate_strict({}, base_draft_schema, _root_schema=schema) == []
    assert validate_strict(complete, base_draft_schema, _root_schema=schema) == []


def test_video_script_schema_and_stage_gate_require_execution_identity(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    valid = {
        "schema": "quwoquan_data.video_script",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "title": "西湖秋色",
        "caption": "一分钟看西湖秋色",
        "scriptLines": ["远景：湖面与群山。"],
    }
    assert_valid(valid, "content", "video_script")
    invalid = dict(valid)
    invalid.pop("executionId")
    with pytest.raises(ValueError, match="executionId"):
        assert_valid(invalid, "content", "video_script")

    object_root = root / TARGET_REF
    _write(object_root / "4.draft/video_script.json", valid)
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=root / "publish",
        release_root=root / "release",
        commercial=False,
        through="4.draft",
    )
    assert not any("video_script.json: executionId" in item for item in report["issues"])
    wrong = dict(valid, executionId="20260903--travel-video-other--test-region-a--pilot-001")
    _write(object_root / "4.draft/video_script.json", wrong)
    report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=root / "publish",
        release_root=root / "release",
        commercial=False,
        through="4.draft",
    )
    assert any("video_script.json: executionId drift" in item for item in report["issues"])


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t12
def test_review_identity_gate_allows_same_model_family(tmp_path: Path) -> None:
    actor = {
        "host": "cursor",
        "sessionId": "review-session",
        "modelFamily": "gpt",
        "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "review-run"},
    }
    author = {
        "actor": {
            "host": "cursor",
            "sessionId": "author-session",
            "modelFamily": "gpt",
            "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "author-run"},
        }
    }
    _write(tmp_path / "_shared/receipts/006-4.draft.json", author)
    assert stage_artifacts._review_identity_issues(
        tmp_path,
        object_ref=TARGET_REF,
        reviewer_result={"objectRef": TARGET_REF, "actor": actor},
        attestation={"objectRef": TARGET_REF, "independentReviewer": {"actor": actor}},
    ) == []


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t13
def test_review_identity_gate_rejects_author_self_review(tmp_path: Path) -> None:
    actor = {
        "host": "cursor",
        "sessionId": "same-session",
        "modelFamily": "gpt",
        "invocation": {"provider": "host", "model": "gpt-5.6", "runId": "same-run"},
    }
    _write(tmp_path / "_shared/receipts/006-4.draft.json", {"actor": actor})
    issues = stage_artifacts._review_identity_issues(
        tmp_path,
        object_ref=TARGET_REF,
        reviewer_result={"objectRef": TARGET_REF, "actor": actor},
        attestation={"objectRef": TARGET_REF, "independentReviewer": {"actor": actor}},
    )
    assert any("同一 host/sessionId" in issue for issue in issues)
    assert any("runId 相同" in issue for issue in issues)


def test_media_review_schema_owns_rights_fields() -> None:
    document = {
        "schema": "quwoquan_data.media_ref_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "passed": True,
        "mediaIssues": [],
        "referenceIssues": [],
        "rightsReviews": [{
            "assetRef": "sources/unit-1/video.mp4",
            "sourceUrl": "https://example.com/video",
            "license": "licensed",
            "termsUrl": "https://example.com/terms",
            "authorizationProof": None,
            "usageScope": "research",
            "passed": True,
            "issues": [],
        }],
    }
    assert_valid(document, "content", "media_ref_review")
    document.pop("rightsReviews")
    with pytest.raises(ValueError, match="rightsReviews"):
        assert_valid(document, "content", "media_ref_review")


@pytest.mark.parametrize("command", ["task-init-contract", "source-plan"])
def test_execution_verifier_help_requires_execution_id(command: str) -> None:
    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "verify", command, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--execution-id" in result.stdout


def test_source_digest_facade_remains_no_arg() -> None:
    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "verify", "source-digest", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--execution-id" not in result.stdout


def test_stage_artifact_skill_commands_bind_each_object_stage_cut() -> None:
    repo_root = next(
        parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()
    )
    contract_root = repo_root / ".agents/skills/content-production/references/stage-contracts"
    for stage in paths.OBJECT_STAGES:
        contract = (contract_root / f"{stage}.md").read_text(encoding="utf-8")
        expected = (
            "python3 quwoquan_data/scripts/cli.py verify stage-artifacts "
            f"--execution-id <id> --through {stage}"
        )
        commands = [
            line.strip()
            for line in contract.splitlines()
            if "verify stage-artifacts" in line
        ]
        assert commands == [expected]

    publish_contract = (contract_root / "publish.md").read_text(encoding="utf-8")
    publish_commands = [
        line.strip()
        for line in publish_contract.splitlines()
        if "verify stage-artifacts" in line
    ]
    assert publish_commands == [
        "python3 quwoquan_data/scripts/cli.py verify stage-artifacts --execution-id <id>"
    ]


def test_stage_artifact_help_declares_final_closure_default() -> None:
    result = subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", "verify", "stage-artifacts", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--through" in result.stdout
    assert "省略表示 publish 后 final closure" in result.stdout


def test_review_stage_cut_does_not_require_publish_final_artifacts(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    object_root = root / TARGET_REF
    required = stage_artifacts.required_stage_artifacts("video")
    for stage in paths.OBJECT_STAGES:
        for name in required[stage]:
            path = object_root / stage / name
            if path.suffix == ".json":
                _write(path, {})
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("draft\n", encoding="utf-8")

    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    review_report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=root / "publish",
        release_root=root / "release",
        commercial=False,
        through="5.review",
    )
    final_report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=root / "publish",
        release_root=root / "release",
        commercial=False,
    )

    assert not any("missing final/" in issue for issue in review_report["issues"])
    assert any("missing final/" in issue for issue in final_report["issues"])
    assert review_report["through"] == "5.review"
    assert final_report["through"] is None

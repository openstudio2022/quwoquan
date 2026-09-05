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


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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


def _freeze_retry_package(root: Path, candidate_path: Path) -> dict[str, object]:
    predecessor_id = "20260902--travel-video-hard-cut--test-region-a--pilot-999"
    output = candidate_path.parent.parent
    terminal_path = (
        output
        / "data/tasks"
        / predecessor_id
        / "_shared/receipts/001-0.plan.json"
    )
    _write(terminal_path, {"verdict": "blocked"})
    retry_binding = {
        "executionId": predecessor_id,
        "terminalReceipt": {
            "scope": "output",
            "ref": terminal_path.relative_to(output).as_posix(),
            "digest": _digest(terminal_path),
        },
    }

    demand_path = candidate_path.with_name("demand.json")
    demand = json.loads(demand_path.read_text(encoding="utf-8"))
    demand["retryOf"] = predecessor_id
    _write(demand_path, demand)

    request_path = root / "0.plan/request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["retryOf"] = retry_binding
    request["carrierDemand"]["digest"] = _digest(demand_path)
    request["submittedInputs"]["carrierDemand"] = demand
    _write(request_path, request)

    manifest_path = root / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["retryOf"] = retry_binding
    manifest["initInputs"]["carrierDemand"] = request["carrierDemand"]
    manifest["submittedInputs"]["carrierDemand"] = demand
    manifest["request"]["digest"] = _digest(request_path)
    _write(manifest_path, manifest)
    return retry_binding


def _rewrite_request(root: Path, request: dict[str, object]) -> None:
    request_path = root / "0.plan/request.json"
    _write(request_path, request)
    manifest_path = root / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["request"]["digest"] = _digest(request_path)
    _write(manifest_path, manifest)


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


def test_task_init_contract_projects_frozen_retry_execution_id(
    initialized: tuple[Path, Path],
) -> None:
    root, candidate_path = initialized
    retry_binding = _freeze_retry_package(root, candidate_path)

    assert verify_task_init_contract.issues(EXECUTION_ID) == []

    request = json.loads((root / "0.plan/request.json").read_text(encoding="utf-8"))
    request["retryOf"] = {
        **retry_binding,
        "executionId": "20260901--travel-video-drift--test-region-a--pilot-998",
    }
    _rewrite_request(root, request)
    assert "task-init carrier demand projection drift" in verify_task_init_contract.issues(
        EXECUTION_ID
    )

    request["retryOf"] = {}
    _rewrite_request(root, request)
    assert any(
        "0.plan/request.json is invalid" in failure
        for failure in verify_task_init_contract.issues(EXECUTION_ID)
    )


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
def test_content_review_schema_owns_one_decision_and_asset_rights() -> None:
    document = {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "decision": "approved",
        "draft": {"ref": "4.draft/video_script.json", "digest": "sha256:" + "1" * 64},
        "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
        "blockingIssues": [],
        "assetRights": [{
            "assetRef": "sources/unit-1/video.mp4",
            "sourceUrl": "https://example.com/video",
            "license": "licensed",
            "termsUrl": "https://example.com/terms",
            "authorizationProof": None,
            "usageScope": "research",
            "decision": "approved",
            "issues": [],
        }],
    }
    assert_valid(document, "content", "content_review")
    for retired in ("actor", "model", "score", "repair", "verdict"):
        invalid = dict(document, **{retired: "forbidden"})
        with pytest.raises(ValueError):
            assert_valid(invalid, "content", "content_review")


def test_rejected_content_review_is_schema_valid() -> None:
    document = {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "decision": "rejected",
        "draft": {"ref": "4.draft/video_script.json", "digest": "sha256:" + "1" * 64},
        "dimensions": [{"name": "content", "decision": "rejected", "issues": ["weak"]}],
        "blockingIssues": ["weak"],
        "assetRights": [],
    }
    assert_valid(document, "content", "content_review")



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


def test_stage_contract_has_single_draft_and_review_artifacts() -> None:
    retired = {
        "source.clean.md", "source.layout.json", "source.quality.json",
        "draft_meta.json", "author_self_check.json", "agent_result_envelope.json",
        "rubric_review.json", "reviewer_result.json", "media_ref_review.json", "attestation.json",
    }
    for lane in ("homepage", "article", "image", "video"):
        required = stage_artifacts.required_stage_artifacts(lane)
        assert len(required["4.draft"]) == 1
        assert required["5.review"] == ("content_review.json",)
        assert retired.isdisjoint({name for names in required.values() for name in names})




def _set_review_target(root: Path, *, target_ref: str, carrier: str) -> Path:
    target_set_path = root / "0.plan/target_set.json"
    target_set = json.loads(target_set_path.read_text(encoding="utf-8"))
    target_set.update({
        "carrier": carrier,
        "targetCount": 1,
        "targetRefs": [target_ref],
        "targets": [{
            "name": "西湖",
            "entityType": "地点/景区",
            "publishAngle": "风光",
            "publishTitle": "西湖秋色",
            "publishSeq": 1,
        }],
    })
    _write(target_set_path, target_set)
    return root / target_ref


def _write_source_assets(
    root: Path,
    *,
    object_ref: str,
    rows: list[dict[str, object]],
) -> None:
    unit_ref = "sources/review-source"
    meta: dict[str, object] = {}
    poster_rows = [row for row in rows if row.get("assetRole") == "poster"]
    if len(poster_rows) == 1:
        meta = {"acquisition": {"posterAssetRef": f"assets/{poster_rows[0]['fileName']}"}}
    _write(root / f"{unit_ref}/meta.json", meta)
    _write(root / f"{unit_ref}/assets/index.json", {"assets": rows})
    for row in rows:
        asset_path = root / unit_ref / "assets" / str(row["fileName"])
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(str(row["fileName"]).encode())
    _write(root / object_ref / "1.download/source_refs.json", {
        "schema": "quwoquan_data.object_source_refs",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "sources": [{
            "sourceUnitId": "review-source",
            "sourceRef": f"{unit_ref}/source.md",
            "metaRef": f"{unit_ref}/meta.json",
            "sourcePlanRef": "sources/plans/" + "a" * 64 + ".json",
            "sourcePlanDigest": "sha256:" + "b" * 64,
            "chosenCandidateDigest": "sha256:" + "c" * 64,
            "sourceId": "review-source",
            "sourceClass": "open_license_media",
            "targetRefs": [object_ref],
        }],
    })


_REVIEW_RIGHTS_FACTS = {
    "sourceUrl": "https://example.com/source",
    "license": "CC BY 4.0",
    "termsUrl": "https://creativecommons.org/licenses/by/4.0",
    "authorizationProof": "https://example.com/proof",
}


def _review_rights_row(asset_ref: str) -> dict[str, object]:
    return {
        "assetRef": asset_ref,
        **_REVIEW_RIGHTS_FACTS,
        "usageScope": "research",
        "decision": "approved",
        "issues": [],
    }


def _write_content_review(
    object_root: Path,
    *,
    object_ref: str,
    draft_name: str,
    asset_refs: list[str],
    decision: str = "approved",
) -> Path:
    draft = object_root / "4.draft" / draft_name
    review_path = object_root / "5.review/content_review.json"
    _write(review_path, {
        "schema": "quwoquan_data.content_review",
        "stage": "5.review",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "decision": decision,
        "draft": {"ref": f"4.draft/{draft_name}", "digest": _digest(draft)},
        "dimensions": [{
            "name": "content",
            "decision": decision,
            "issues": [] if decision == "approved" else ["weak"],
        }],
        "blockingIssues": [] if decision == "approved" else ["weak"],
        "assetRights": [_review_rights_row(ref) for ref in asset_refs],
    })
    return review_path


def _verify_review(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    return stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=root / "publish",
        release_root=root / "release",
        through="5.review",
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-020.t12
def test_review_stage_uses_image_draft_asset_set_without_manifest(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    object_ref = "posts/image/风光/西湖秋色/1"
    object_root = _set_review_target(root, target_ref=object_ref, carrier="image")
    selected_ref = "sources/review-source/assets/selected.jpg"
    unselected_ref = "sources/review-source/assets/unselected.jpg"
    source_rows = [
        {"fileName": "selected.jpg", "assetRole": "image", **_REVIEW_RIGHTS_FACTS},
        {"fileName": "unselected.jpg", "assetRole": "image", **_REVIEW_RIGHTS_FACTS},
    ]
    _write_source_assets(root, object_ref=object_ref, rows=source_rows)
    _write(object_root / "3.compose/writing_pack.json", {"carrier": "image"})
    _write(object_root / "4.draft/image_work.json", {
        "schema": "quwoquan_data.image_work",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "assetRefs": [selected_ref],
        "caption": "西湖秋色",
    })
    _write_content_review(
        object_root,
        object_ref=object_ref,
        draft_name="image_work.json",
        asset_refs=[selected_ref],
    )

    report = _verify_review(root, monkeypatch)

    assert report["passed"], report["issues"]
    assert not (object_root / "manifest.json").exists()
    assert unselected_ref not in json.dumps(report, ensure_ascii=False)


@pytest.mark.parametrize("failure", ["missing", "extra", "rights-drift"])
def test_review_stage_rejects_asset_rights_set_or_fact_drift(
    initialized: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root, _ = initialized
    object_ref = "posts/image/风光/西湖秋色/1"
    object_root = _set_review_target(root, target_ref=object_ref, carrier="image")
    selected_ref = "sources/review-source/assets/selected.jpg"
    extra_ref = "sources/review-source/assets/extra.jpg"
    _write_source_assets(root, object_ref=object_ref, rows=[
        {"fileName": "selected.jpg", "assetRole": "image", **_REVIEW_RIGHTS_FACTS},
        {"fileName": "extra.jpg", "assetRole": "image", **_REVIEW_RIGHTS_FACTS},
    ])
    _write(object_root / "3.compose/writing_pack.json", {"carrier": "image"})
    _write(object_root / "4.draft/image_work.json", {
        "schema": "quwoquan_data.image_work",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "assetRefs": [selected_ref],
        "caption": "西湖秋色",
    })
    review_path = _write_content_review(
        object_root,
        object_ref=object_ref,
        draft_name="image_work.json",
        asset_refs=([] if failure == "missing" else [selected_ref, extra_ref] if failure == "extra" else [selected_ref]),
    )
    if failure == "rights-drift":
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["assetRights"][0]["license"] = "drifted"
        _write(review_path, review)

    report = _verify_review(root, monkeypatch)

    assert not report["passed"]
    expected = "asset set differs" if failure != "rights-drift" else "source rights facts drift"
    assert any(expected in issue for issue in report["issues"])


def test_review_stage_rejects_selected_asset_outside_object_source_refs(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    object_ref = "posts/image/风光/西湖秋色/1"
    object_root = _set_review_target(root, target_ref=object_ref, carrier="image")
    selected_ref = "sources/review-source/assets/selected.jpg"
    other_ref = "sources/other-source/assets/other.jpg"
    _write_source_assets(root, object_ref=object_ref, rows=[
        {"fileName": "selected.jpg", "assetRole": "image", **_REVIEW_RIGHTS_FACTS},
    ])
    _write(root / "sources/other-source/assets/index.json", {"assets": [
        {"fileName": "other.jpg", "assetRole": "image", **_REVIEW_RIGHTS_FACTS},
    ]})
    other_path = root / other_ref
    other_path.parent.mkdir(parents=True, exist_ok=True)
    other_path.write_bytes(b"other")
    _write(object_root / "3.compose/writing_pack.json", {"carrier": "image"})
    _write(object_root / "4.draft/image_work.json", {
        "schema": "quwoquan_data.image_work",
        "executionId": EXECUTION_ID,
        "objectRef": object_ref,
        "assetRefs": [other_ref],
        "caption": "西湖秋色",
    })
    _write_content_review(
        object_root,
        object_ref=object_ref,
        draft_name="image_work.json",
        asset_refs=[other_ref],
    )

    report = _verify_review(root, monkeypatch)

    assert not report["passed"]
    assert any("outside object source units" in issue for issue in report["issues"])
    assert selected_ref not in json.dumps(report, ensure_ascii=False)


def test_review_stage_derives_exact_video_and_poster_refs_from_compose(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    object_root = _set_review_target(root, target_ref=TARGET_REF, carrier="video")
    video_ref = "sources/review-source/assets/video.mp4"
    poster_ref = "sources/review-source/assets/poster.png"
    _write_source_assets(root, object_ref=TARGET_REF, rows=[
        {
            "fileName": "video.mp4",
            "assetRole": "video",
            "sourceAssetId": "source-video:video",
            **_REVIEW_RIGHTS_FACTS,
        },
        {
            "fileName": "poster.png",
            "assetRole": "poster",
            "sourceAssetId": "source-video:poster",
            "derivedFromSourceAssetId": "source-video:video",
            **_REVIEW_RIGHTS_FACTS,
        },
    ])
    _write(object_root / "3.compose/writing_pack.json", {
        "carrier": "video",
        "sourceVideo": {"assetRef": video_ref},
    })
    _write(object_root / "4.draft/video_script.json", {
        "schema": "quwoquan_data.video_script",
        "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF,
        "title": "西湖",
        "caption": "西湖",
        "scriptLines": ["西湖"],
    })
    review_path = _write_content_review(
        object_root,
        object_ref=TARGET_REF,
        draft_name="video_script.json",
        asset_refs=[video_ref, poster_ref],
    )

    report = _verify_review(root, monkeypatch)
    assert report["passed"], report["issues"]

    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["assetRights"] = review["assetRights"][:1]
    _write(review_path, review)
    report = _verify_review(root, monkeypatch)
    assert any("asset set differs" in issue for issue in report["issues"])


@pytest.mark.parametrize(
    ("carrier", "object_ref", "compose_name", "compose", "draft_name", "draft"),
    [
        (
            "article",
            "posts/article/攻略/西湖一日游/1",
            "writing_pack.json",
            {"carrier": "article", "assets": []},
            "draft.article.md",
            "# 西湖一日游\n",
        ),
        (
            "homepage",
            "entities/地点/景区/西湖",
            "entity_page_input.json",
            {"payload": {"imagePlaceholderBindings": []}},
            "page.md",
            "# 西湖\n",
        ),
    ],
)
def test_review_stage_allows_explicit_text_only_object_without_manifest(
    initialized: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    carrier: str,
    object_ref: str,
    compose_name: str,
    compose: dict[str, object],
    draft_name: str,
    draft: str,
) -> None:
    root, _ = initialized
    object_root = _set_review_target(root, target_ref=object_ref, carrier=carrier)
    _write(object_root / f"3.compose/{compose_name}", compose)
    draft_path = object_root / "4.draft" / draft_name
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(draft, encoding="utf-8")
    _write_content_review(
        object_root,
        object_ref=object_ref,
        draft_name=draft_name,
        asset_refs=[],
    )

    report = _verify_review(root, monkeypatch)

    assert report["passed"], report["issues"]
    assert not (object_root / "manifest.json").exists()


def test_final_artifact_closure_still_requires_manifest(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    object_ref = "posts/article/攻略/西湖一日游/1"
    object_root = _set_review_target(root, target_ref=object_ref, carrier="article")
    _write(object_root / "3.compose/writing_pack.json", {"carrier": "article", "assets": []})
    draft = object_root / "4.draft/draft.article.md"
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text("# 西湖一日游\n", encoding="utf-8")
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)

    report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID,
        publish_root=root / "publish",
        release_root=root / "release",
    )

    assert not report["passed"]
    assert any("missing final/manifest.json" in issue for issue in report["issues"])


def test_rejected_review_does_not_fail_stage_artifacts_for_semantic_decision(
    initialized: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = initialized
    object_root = root / TARGET_REF
    draft = object_root / "4.draft/video_script.json"
    _write(draft, {
        "schema": "quwoquan_data.video_script", "executionId": EXECUTION_ID,
        "objectRef": TARGET_REF, "title": "西湖", "caption": "西湖",
        "scriptLines": ["西湖"],
    })
    _write(object_root / "manifest.json", {
        "contentType": "article", "publishMediaMode": "text_only", "assets": [],
    })
    _write(object_root / "5.review/content_review.json", {
        "schema": "quwoquan_data.content_review", "stage": "5.review",
        "executionId": EXECUTION_ID, "objectRef": TARGET_REF, "decision": "rejected",
        "draft": {"ref": "4.draft/video_script.json", "digest": _digest(draft)},
        "dimensions": [{"name": "content", "decision": "rejected", "issues": ["weak"]}],
        "blockingIssues": ["weak"], "assetRights": [],
    })
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda _execution_id: root)
    report = stage_artifacts.verify_stage_artifacts(
        execution_id=EXECUTION_ID, publish_root=root / "publish",
        release_root=root / "release", through="5.review",
    )
    assert not any("review decision" in issue or "not approved" in issue for issue in report["issues"])

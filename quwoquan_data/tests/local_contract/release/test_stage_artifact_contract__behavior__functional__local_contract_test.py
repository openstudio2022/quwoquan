from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import verify.stage_artifacts as stage_artifacts  # noqa: E402
import core.prompt_render as prompt_render  # noqa: E402
import content.execution.prompt_snapshot as prompt_snapshot  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from core.stage_artifact_contract import (  # noqa: E402
    SOURCE_UNIT_ARTIFACTS,
    required_final_artifacts,
    required_stage_artifacts,
)


def _touch(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_stage_gate_requires_complete_five_stage_object_and_blocks_process_release(
    tmp_path: Path, monkeypatch
) -> None:
    batch = tmp_path / "runtime/batch"
    obj = batch / "entities/地点/景区/西湖"
    compose = obj / "3.compose/entity_page_input.json"
    compose.parent.mkdir(parents=True)
    compose.write_text(json.dumps({"placeholder": True}), encoding="utf-8")
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda *_args: batch)
    publish_root = tmp_path / "publish"
    release_root = tmp_path / "release"

    report = stage_artifacts.verify_stage_artifacts(
        execution_id="20260711--travel-homepage-stage-gate--test-region-a--pilot-001",
        publish_root=publish_root,
        release_root=release_root,
        commercial=False,
    )
    assert report["passed"] is False
    assert any("missing 1.download/source_refs.json" in issue for issue in report["issues"])

    (release_root / "rel-1").mkdir(parents=True)
    (release_root / "rel-1/prompt.md").write_text("forbidden", encoding="utf-8")
    report = stage_artifacts.verify_stage_artifacts(
        execution_id="20260711--travel-homepage-stage-gate--test-region-a--pilot-001",
        publish_root=publish_root,
        release_root=release_root,
        commercial=False,
    )
    assert any("process artifact forbidden" in issue for issue in report["issues"])


def test_prompt_snapshot_is_replayable_and_rejects_secret_vars(
    tmp_path: Path, monkeypatch
) -> None:
    prompts = tmp_path / "prompts"
    (prompts / "article").mkdir(parents=True)
    (prompts / "_shared/partials").mkdir(parents=True)
    (prompts / "article/demo.system.md").write_text(
        "<role>作者</role>\n{{> _shared/partials/common.md}}\n", encoding="utf-8"
    )
    (prompts / "article/demo.task.md").write_text("对象：{{name}}\n", encoding="utf-8")
    (prompts / "_shared/partials/common.md").write_text("只依据证据。\n", encoding="utf-8")
    monkeypatch.setattr(prompt_render, "PROMPTS_ROOT", prompts)
    monkeypatch.setitem(prompt_render._PROMPT_FAMILY, "demo", "article")
    monkeypatch.setattr(prompt_snapshot, "prompt_template_material", prompt_render.prompt_template_material)
    monkeypatch.setattr(
        prompt_snapshot,
        "stage_execution_context",
        lambda *_args: {
            "executionId": "20260711--travel-article-prompt-audit--test-region-a--pilot-001",
            "executionBinding": "frozen",
        },
    )
    prompt = "<role>作者</role>\n只依据证据。\n\n---\n\n对象：西湖\n"
    snapshot = prompt_snapshot.build_prompt_snapshot(
        execution_id="20260711--travel-article-prompt-audit--test-region-a--pilot-001",
        stage="4.draft",
        template_family="demo",
        variables={"name": "西湖"},
        rendered_prompt=prompt,
        host_actor={"host": "external_host_agent", "role": "author"},
        run_id="run-1",
        output_refs=["4.draft/page.md"],
    )
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    assert prompt_snapshot.prompt_snapshot_issues(snapshot, prompt_path) == []
    assert_valid(snapshot, "execution", "prompt_snapshot")
    assert snapshot["templateRefs"]["partials"] == ["_shared/partials/common.md"]
    assert snapshot["hostRuntime"] == "external_host_agent"
    assert snapshot["hostActor"] == {
        "host": "external_host_agent",
        "role": "author",
    }
    assert "provider" not in snapshot
    assert "model" not in snapshot

    with pytest.raises(ValueError, match="secret-like"):
        prompt_snapshot.build_prompt_snapshot(
            execution_id="20260711--travel-article-prompt-audit--test-region-a--pilot-001",
            stage="4.draft",
            template_family="demo",
            variables={"apiToken": "do-not-store"},
            rendered_prompt=prompt,
            host_actor={"host": "external_host_agent", "role": "author"},
            run_id="run-2",
            output_refs=["4.draft/page.md"],
        )
    assert prompt_snapshot.prompt_snapshot_paths(
        role="author", run_id="author-1", stage_dir=tmp_path / "4.draft"
    ) == (
        tmp_path / "4.draft/prompt.md",
        tmp_path / "4.draft/prompt_snapshot.json",
    )
    assert prompt_snapshot.prompt_snapshot_paths(
        role="reviewer", run_id="review-1", stage_dir=tmp_path / "5.review"
    )[0] == tmp_path / "5.review/prompts/review-1/prompt.md"
    assert prompt_snapshot.prompt_snapshot_paths(
        role="controller",
        run_id="controller-1",
        execution_root=tmp_path,
        checkpoint="author",
    )[1] == tmp_path / "_shared/prompt_snapshots/author/controller-1/prompt_snapshot.json"


def test_through_cuts_stage_scope_and_discovers_pre_compose_objects(
    tmp_path: Path, monkeypatch
) -> None:
    """进行式验收（--through）契约：早期对象可见、下游缺失不误报、
    完成型默认行为不变（无 compose 锚点即不可见）。"""
    batch = tmp_path / "runtime/batch"
    obj = batch / "entities/地点/景区/西湖"
    _touch(obj / "1.download/source_refs.json", json.dumps({"sources": []}))
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda *_args: batch)
    common = dict(
        execution_id="20260823--travel-homepage-through-gate--test-region-a--pilot-001",
        publish_root=tmp_path / "publish",
        release_root=tmp_path / "release",
        commercial=False,
    )

    report = stage_artifacts.verify_stage_artifacts(**common, through="1.download")
    assert report["through"] == "1.download"
    assert report["objectCount"] == 1
    assert not any("missing 2.quality" in issue for issue in report["issues"])
    assert not any("missing 3.compose" in issue for issue in report["issues"])
    assert not any("missing final/" in issue for issue in report["issues"])

    report = stage_artifacts.verify_stage_artifacts(**common, through="2.quality")
    assert any(
        "missing 2.quality/quality_analysis.json" in issue
        for issue in report["issues"]
    )
    assert not any("missing 3.compose" in issue for issue in report["issues"])

    report = stage_artifacts.verify_stage_artifacts(**common)
    assert report["through"] is None
    assert report["objectCount"] == 0

    with pytest.raises(ValueError, match="unsupported --through stage"):
        stage_artifacts.verify_stage_artifacts(**common, through="9.bogus")


def test_through_before_review_ignores_stale_reject_attestation(
    tmp_path: Path, monkeypatch
) -> None:
    """return_to_stage 回退契约：重做 4.draft 期间磁盘留有上一轮 reject 的
    5.review 产物，--through 4.draft 不得用完成型 review 断言拦截；
    截止含 5.review 时断言必须恢复生效。"""
    batch = tmp_path / "runtime/batch"
    obj = batch / "entities/地点/景区/西湖"
    _touch(obj / "3.compose/writing_pack.json", json.dumps({"placeholder": True}))
    _touch(
        obj / "5.review/attestation.json",
        json.dumps(
            {
                "independentReviewer": {"status": "failed"},
                "decision": "rejected",
            }
        ),
    )
    monkeypatch.setattr(stage_artifacts, "execution_root", lambda *_args: batch)
    common = dict(
        execution_id="20260823--travel-article-through-review--test-region-a--pilot-001",
        publish_root=tmp_path / "publish",
        release_root=tmp_path / "release",
        commercial=True,
    )

    report = stage_artifacts.verify_stage_artifacts(**common, through="4.draft")
    assert not any("review decision" in issue for issue in report["issues"])
    assert not any("independent reviewer" in issue for issue in report["issues"])

    report = stage_artifacts.verify_stage_artifacts(**common, through="5.review")
    assert any("review decision is not approved" in issue for issue in report["issues"])
    assert any("independent reviewer not passed" in issue for issue in report["issues"])


@pytest.mark.parametrize("lane", ["homepage", "article", "image", "video"])
def test_four_lanes_share_complete_five_stage_contract(tmp_path: Path, lane: str) -> None:
    object_root = tmp_path / lane
    for stage, rels in required_stage_artifacts(lane).items():
        for rel in rels:
            _touch(object_root / stage / rel, "{}" if rel.endswith(".json") else "content")
    for rel in SOURCE_UNIT_ARTIFACTS:
        _touch(
            object_root / "1.download/source_units/source-1" / rel,
            "{}" if rel.endswith(".json") else "source",
        )
    for rel in required_final_artifacts(lane):
        _touch(object_root / rel, "{}" if rel.endswith(".json") else "final")

    assert stage_artifacts.object_stage_contract_issues(object_root, lane) == []
    (object_root / "5.review/evidence_index.json").unlink()
    assert f"{lane}.5.review.evidence_index.json 缺失" in stage_artifacts.object_stage_contract_issues(
        object_root, lane
    )

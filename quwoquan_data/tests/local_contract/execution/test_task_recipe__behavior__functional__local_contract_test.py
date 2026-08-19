# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-001
"""Contract tests for the generic single-work-package content facade."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.campaign import request_envelope_io
from content.execution.campaign import submission as campaign_submission
from content.execution.identity import (
    build_execution_id,
    parse_execution_id,
    validate_execution_id,
)
from content.execution.model_contract import execution_model_pair
from content.execution.planning.recipe import checkpoint as recipe_checkpoint
from content.execution.planning.recipe import model as recipe
from content.execution.planning.recipe import request as recipe_request
from core.control_types import ExecutionStateStatus
from core.paths import FAMILIES_ROOT, iter_family_files
from core.runtime_policy import load_runtime_policy
from core.schema import assert_valid

EXECUTION_ID = "20260722--travel-homepage-coverage--test-region-a--pilot-001"


def test_execution_id_is_readable_and_strict() -> None:
    identity = parse_execution_id(EXECUTION_ID)

    assert identity.vertical == "travel"
    assert identity.content_type.value == "homepage"
    assert identity.scope == "test-region-a"
    assert identity.phase.value == "pilot"
    assert identity.sequence == 1
    assert build_execution_id(
        run_date="20260722",
        vertical="travel",
        content_type="homepage",
        intent="coverage",
        scope="test-region-b",
        phase="scale",
        sequence=3,
    ) == "20260722--travel-homepage-coverage--test-region-b--scale-003"
    assert build_execution_id(
        run_date="20260722",
        vertical="travel",
        content_type="video",
        intent="supply",
        scope="test-region-b",
        phase="full",
        sequence=4,
    ) == "20260722--travel-video-supply--test-region-b--full-004"
    try:
        validate_execution_id("task-a__batch-b")
    except ValueError:
        pass
    else:
        raise AssertionError("retired task/batch identity must fail")


def test_all_family_recipes_lint_clean() -> None:
    refs = [
        str(path.relative_to(FAMILIES_ROOT))[: -len(".recipe.yaml")]
        for path in iter_family_files(".recipe.yaml")
    ]
    assert refs
    for ref in refs:
        assert recipe.load_recipe(ref)["recipeId"] == ref


def test_travel_recipes_explicitly_select_research_lifecycle() -> None:
    refs = (
        "content/travel/homepage/homepage",
        "content/travel/article/article",
        "content/travel/image/image",
        "content/travel/video/video",
    )

    assert {
        recipe.load_recipe(ref)["readiness"]["mode"] for ref in refs
    } == {"research"}


def test_recipe_schema_rejects_missing_or_unknown_lifecycle() -> None:
    payload = json.loads(
        json.dumps(recipe.load_recipe("content/travel/article/article"))
    )
    payload["readiness"]["mode"] = "environment_default"
    with pytest.raises(ValueError, match="不在枚举"):
        assert_valid(payload, "execution", "content_recipe")

    payload.pop("readiness")
    with pytest.raises(ValueError, match="缺 required 字段 'readiness'"):
        assert_valid(payload, "execution", "content_recipe")


def test_travel_recipes_do_not_narrow_selection_to_scenic_subtype() -> None:
    refs = (
        "content/travel/homepage/homepage",
        "content/travel/article/article",
        "content/travel/image/image",
        "content/travel/video/video",
    )

    assert {
        recipe.load_recipe(ref)["selection"]["category"] for ref in refs
    } == {"地点"}


def test_travel_video_recipe_uses_the_governed_codex_terra_binding() -> None:
    video = recipe.load_recipe("content/travel/video/video")
    author = execution_model_pair(video).author
    runtime = load_runtime_policy(str(video["runtimeProfile"]))
    expected_parameters: list[dict[str, str]] = []

    assert author.model_id == "gpt-5.6-terra"
    assert author.family.value == "gpt"
    assert author.selection.parameters_document() == expected_parameters
    assert runtime.semantic_agent_model_selection.to_sdk_document() == {
        "id": author.model_id,
        "params": expected_parameters,
    }


def test_travel_image_recipe_uses_the_governed_codex_terra_binding() -> None:
    image = recipe.load_recipe("content/travel/image/image")
    author = execution_model_pair(image).author
    runtime = load_runtime_policy(str(image["runtimeProfile"]))
    expected_parameters: list[dict[str, str]] = []

    assert author.model_id == "gpt-5.6-terra"
    assert author.family.value == "gpt"
    assert author.selection.parameters_document() == expected_parameters
    assert runtime.semantic_agent_model_selection.to_sdk_document() == {
        "id": author.model_id,
        "params": expected_parameters,
    }


def test_review_only_keeps_lane_alive_across_managed_agent_yield(
    monkeypatch,
) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def execute(*_args, **_kwargs) -> None:
        calls.append("execute")

    def state(_execution_id: str):
        if len(calls) == 1:
            return SimpleNamespace(
                completed=[],
                status=ExecutionStateStatus.WAITING_AGENT,
                waiting_checkpoint="post_author",
                failed_objects=[],
            )
        return SimpleNamespace(
            completed=["post_review"],
            status=ExecutionStateStatus.STOPPED_AT_UNTIL,
            waiting_checkpoint=None,
            failed_objects=[],
        )

    monkeypatch.setattr(recipe_checkpoint, "load_execution_state", state)
    monkeypatch.setattr(
        recipe_checkpoint,
        "active_runtime_policy",
        lambda: SimpleNamespace(
            agent_future_poll_timeout_seconds=0.2,
        ),
    )
    monkeypatch.setattr(recipe_checkpoint.time, "sleep", sleeps.append)

    recipe_checkpoint.execute_until_checkpoint(
        {},
        EXECUTION_ID,
        until="post_review",
        execute=execute,
    )

    assert calls == ["execute", "execute"]
    assert sleeps == [0.2]


def test_execution_facade_invokes_the_canonical_data_cli() -> None:
    assert recipe._CLI_PATH == SCRIPTS_ROOT / "cli.py"
    assert recipe._CLI_PATH.is_file()


def test_readiness_calls_only_single_execution_gate() -> None:
    calls: list[list[str]] = []
    recipe._readiness(
        {"readiness": {"requireReviewed": True, "mode": "research"}},
        EXECUTION_ID,
        lambda argv: calls.append(list(argv)) or 0,
    )

    assert calls == [[
        "verify", "execution-readiness", "--execution-id", EXECUTION_ID,
        "--require-reviewed",
        "--mode", "research",
    ]]


def test_readiness_has_no_rate_or_veto_knob() -> None:
    """比率与 veto 开关不再是准出输入，recipe 不得再传任何速率旗标。"""
    calls: list[list[str]] = []
    recipe._readiness(
        {
            "readiness": {
                "requireReviewed": True,
                "mode": "research",
                "minPassRate": 0.5,
                "failOnNoGo": False,
            }
        },
        EXECUTION_ID,
        lambda argv: calls.append(list(argv)) or 0,
    )

    assert calls == [[
        "verify", "execution-readiness", "--execution-id", EXECUTION_ID,
        "--require-reviewed",
        "--mode", "research",
    ]]


def test_execution_readiness_cli_registers_recipe_contract_options() -> None:
    import argparse

    from verify.handler import register_parser

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser(commands)
    args = parser.parse_args(
        [
            "verify",
            "execution-readiness",
            "--execution-id",
            EXECUTION_ID,
            "--require-reviewed",
            "--mode",
            "commercial",
        ]
    )

    assert args.execution_id == EXECUTION_ID
    assert args.require_reviewed is True
    assert args.mode == "commercial"

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "verify",
                "execution-readiness",
                "--execution-id",
                EXECUTION_ID,
            ]
        )
    for removed in ("--min-pass-rate", "--fail-on-no-go"):
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "verify",
                    "execution-readiness",
                    "--execution-id",
                    EXECUTION_ID,
                    "--require-reviewed",
                    "--mode",
                    "commercial",
                    removed,
                    "0.9" if removed == "--min-pass-rate" else "",
                ]
            )


def test_preflight_evidence_belongs_to_execution_work_package() -> None:
    argv = recipe._runtime_preflight_argv(EXECUTION_ID, "cursor_auto")
    report_path = Path(argv[argv.index("--report-out") + 1])

    assert argv[:2] == ["task", "preflight"]
    assert argv[argv.index("--semantic-selection-id") + 1] == "cursor_auto"
    assert report_path == recipe.execution_root(EXECUTION_ID) / "evidence" / "runtime_preflight.json"


def test_campaign_publish_resume_does_not_recheck_cursor_network() -> None:
    assert recipe._requires_runtime_preflight(
        campaign_bound=True,
        stage="run",
    ) is False
    assert recipe._requires_runtime_preflight(
        campaign_bound=True,
        stage="review-only",
    ) is True
    assert recipe._requires_runtime_preflight(
        campaign_bound=False,
        stage="run",
    ) is True


def test_execute_freezes_generic_runtime_request(monkeypatch, tmp_path: Path) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    received: dict[str, object] = {}
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe, "_run_execution", lambda args, invoke=None: received.update(vars(args)))

    recipe.handle_execute(
        argparse.Namespace(
            execution_id=EXECUTION_ID,
            retry_of=None,
            family="content/travel/homepage/homepage",
            region_ref="test-region-a",
            selector="source-ready-priority",
            count=2,
            quota=2,
            target_names=["测试实体甲", "测试实体乙"],
            topic=None,
            source_providers=[],
            stage="plan-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert received["family"] == "content/travel/homepage/homepage"
    assert received["region_ref"] == "test-region-a"
    assert received["count"] == 2
    assert received["target_names"] == ("测试实体甲", "测试实体乙")
    assert received["vertical"] == "travel"
    assert received["content_type"] == "homepage"
    assert received["intent"] == "coverage"
    assert "rollout" not in received


def test_retry_inherits_the_previous_frozen_target_set(monkeypatch, tmp_path: Path) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    received: dict[str, object] = {}
    retry_of = "20260722--travel-homepage-coverage--test-region-a--pilot-001"
    execution_id = "20260722--travel-homepage-coverage--test-region-a--pilot-002"
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        recipe,
        "load_frozen_target_set",
        lambda _execution_id: {
            "targets": [
                {"name": "测试实体乙"},
                {"name": "测试实体甲"},
            ]
        },
    )
    monkeypatch.setattr(recipe, "_run_execution", lambda args, invoke=None: received.update(vars(args)))

    recipe.handle_execute(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=retry_of,
            family="content/travel/homepage/homepage",
            region_ref="test-region-a",
            selector="source-ready-priority",
            count=2,
            quota=2,
            target_names=[],
            topic=None,
            source_providers=[],
            stage="plan-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert received["target_names"] == ("测试实体乙", "测试实体甲")


def _frozen_image_external_refs(asset_count: int) -> list[dict[str, object]]:
    blobs = [
        {
            "blobRef": f"objects/image-{index:02d}.jpg",
            "contentSha256": "sha256:" + f"{index:064x}",
            "sizeBytes": index,
        }
        for index in range(1, asset_count + 1)
    ]
    return [
        {
            "kind": "professional_image_acquisition",
            "carrier": "image",
            "blobRefs": blobs[:8],
        },
        {
            "kind": "professional_image_acquisition",
            "carrier": "image",
            "blobRefs": blobs[8:],
        },
    ]


def test_external_image_retry_keeps_empty_envelope_targets_for_eleven_assets_across_six_entities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/china"
    reference_root.mkdir(parents=True)
    envelope_path = tmp_path / "image-envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    retry_of = "20260814--travel-image-workload-image-12--china--scale-001"
    execution_id = "20260814--travel-image-workload-image-12--china--scale-007"
    refs = _frozen_image_external_refs(11)
    captured: dict[str, object] = {}

    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe.store, "spec_exists", lambda _execution_id: False)
    monkeypatch.setattr(
        request_envelope_io,
        "load_campaign_envelope",
        lambda _path: {
            "executionId": execution_id,
            "rootExecutionId": execution_id,
            "carrier": "image",
            "retryOf": retry_of,
            "targetNames": [],
            "externalInputRefs": refs,
        },
    )
    monkeypatch.setattr(
        recipe,
        "_retry_target_names",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("external media retry must not inherit predecessor targets")
        ),
    )
    monkeypatch.setattr(
        recipe,
        "load_frozen_target_set",
        lambda _execution_id: (_ for _ in ()).throw(
            AssertionError("external media retry must not load predecessor target rows")
        ),
    )
    monkeypatch.setattr(
        recipe,
        "_run_execution",
        lambda args, **_kwargs: captured.update(vars(args)),
    )

    recipe.handle_execute(
        argparse.Namespace(
            execution_id=execution_id,
            campaign_root_execution_id=execution_id,
            campaign_envelope=str(envelope_path),
            retry_of=retry_of,
            family="content/travel/image/image",
            region_ref="china",
            selector="all",
            count=6,
            quota=12,
            target_names=[],
            topic="image-12",
            source_providers=[],
            stage="submit-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert sum(len(row["blobRefs"]) for row in refs) == 11
    assert captured["count"] == 6
    assert captured["quota"] == 12
    assert captured["target_names"] == ()
    assert captured["inherited_targets"] == ()
    assert captured["retry_external_media_scope"] is True


def test_external_image_retry_lane_reloads_exact_submission_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/china"
    reference_root.mkdir(parents=True)
    retry_of = "20260814--travel-image-workload-image-12--china--scale-001"
    execution_id = "20260814--travel-image-workload-image-12--china--scale-007"
    refs = _frozen_image_external_refs(11)
    captured: dict[str, object] = {}

    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe.store, "spec_exists", lambda _execution_id: False)
    monkeypatch.setattr(
        campaign_submission,
        "load_submissions",
        lambda _root_execution_id: {
            "image": {
                "executionId": execution_id,
                "rootExecutionId": execution_id,
                "carrier": "image",
                "retryOf": retry_of,
                "targetNames": [],
                "externalInputRefs": refs,
            }
        },
    )
    monkeypatch.setattr(
        recipe,
        "_retry_target_names",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("external media lane must not inherit predecessor targets")
        ),
    )
    monkeypatch.setattr(
        recipe,
        "_run_execution",
        lambda args, **_kwargs: captured.update(vars(args)),
    )

    recipe.handle_execute(
        argparse.Namespace(
            execution_id=execution_id,
            campaign_root_execution_id=execution_id,
            campaign_envelope=None,
            retry_of=retry_of,
            family="content/travel/image/image",
            region_ref="china",
            selector="all",
            count=6,
            quota=12,
            target_names=[],
            topic="image-12",
            source_providers=[],
            stage="review-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert captured["target_names"] == ()
    assert captured["inherited_targets"] == ()
    assert captured["retry_external_media_scope"] is True


def test_external_media_retry_rejects_envelope_digest_tamper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "image-envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        request_envelope_io,
        "load_campaign_envelope",
        lambda _path: (_ for _ in ()).throw(
            ValueError("campaign envelope requestDigest drift")
        ),
    )

    with pytest.raises(
        SystemExit,
        match="EXTERNAL_MEDIA_RETRY_SCOPE_INVALID.*requestDigest drift",
    ):
        recipe_request.external_media_retry_target_names(
            "20260814--travel-image-workload-image-12--china--scale-001",
            execution_id="20260814--travel-image-workload-image-12--china--scale-007",
            carrier="image",
            requested_target_names=(),
            campaign_envelope=str(envelope_path),
            campaign_root_execution_id=None,
        )


def test_reconciled_campaign_retry_uses_exact_envelope_subset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "article-envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    retry_of = "20260815--travel-article-workload-article-6--china--scale-001"
    monkeypatch.setattr(
        request_envelope_io,
        "load_campaign_envelope",
        lambda _path: {
            "executionId": "20260815--travel-article-workload-article-1--china--scale-008",
            "carrier": "article",
            "retryOf": retry_of,
            "count": 2,
            "quota": 1,
            "targetNames": ["青城山"],
            "predecessorReconciliation": {
                "predecessorRootExecutionId": "20260815--travel-homepage-root--china--scale-001",
                "receiptDigest": "sha256:" + "a" * 64,
            },
        },
    )

    assert recipe_request.reconciled_campaign_retry_target_names(
        retry_of,
        execution_id="20260815--travel-article-workload-article-1--china--scale-008",
        carrier="article",
        count=2,
        quota=1,
        requested_target_names=("青城山",),
        campaign_envelope=str(envelope_path),
    ) == ("青城山",)


def test_retry_rejects_target_or_count_drift(monkeypatch, tmp_path: Path) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    retry_of = "20260722--travel-homepage-coverage--test-region-a--pilot-001"
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        recipe,
        "load_frozen_target_set",
        lambda _execution_id: {
            "targets": [
                {"name": "测试实体乙"},
                {"name": "测试实体甲"},
            ]
        },
    )
    monkeypatch.setattr(
        recipe,
        "_run_execution",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    base = {
        "execution_id": "20260722--travel-homepage-coverage--test-region-a--pilot-002",
        "retry_of": retry_of,
        "family": "content/travel/homepage/homepage",
        "region_ref": "test-region-a",
        "selector": "source-ready-priority",
        "count": 2,
        "quota": 2,
        "target_names": ["测试实体甲", "测试实体乙"],
        "topic": None,
        "source_providers": [],
        "stage": "plan-only",
        "recover_stage": None,
        "recovery_reason": None,
    }
    with pytest.raises(SystemExit, match="previous frozen target order exactly"):
        recipe.handle_execute(argparse.Namespace(**base))

    base["count"] = 1
    base["quota"] = 1
    base["target_names"] = []
    with pytest.raises(SystemExit, match=r"inherited entity pool 2 exceeds --count 1"):
        recipe.handle_execute(argparse.Namespace(**base))


def test_retry_without_predecessor_requires_explicit_targets(monkeypatch) -> None:
    def missing_target_set(_execution_id: str) -> dict[str, object]:
        raise FileNotFoundError("disposed predecessor")

    monkeypatch.setattr(recipe, "load_frozen_target_set", missing_target_set)

    with pytest.raises(SystemExit, match="provide every exact --target"):
        recipe._retry_target_names(
            "20260722--travel-homepage-coverage--test-region-a--pilot-001",
            count=2,
            quota=2,
            requested_target_names=(),
        )

    assert recipe._retry_target_names(
        "20260722--travel-homepage-coverage--test-region-a--pilot-001",
        count=2,
        quota=2,
        requested_target_names=("测试实体乙", "测试实体甲"),
    ) == ("测试实体乙", "测试实体甲")


def test_retry_unfinished_scope_narrows_exact_target_and_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/china"
    reference_root.mkdir(parents=True)
    captured: dict[str, object] = {}
    retry_of = "20260812--travel-article-m100--china--scale-010"
    object_ref = "剑门关__article-source-e9057f23e3d3ebb5c74f"
    scope = SimpleNamespace(
        target_names=("剑门关",),
        target_rows=({"entityType": "地点/景区", "name": "剑门关"},),
    )
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(
        recipe_request,
        "load_retry_unfinished_scope",
        lambda *_args, **_kwargs: scope,
    )
    monkeypatch.setattr(
        recipe,
        "_retry_target_names",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("broad predecessor target set must not be consumed")
        ),
    )
    monkeypatch.setattr(
        recipe,
        "_run_execution",
        lambda args, **_kwargs: captured.update(vars(args)),
    )

    recipe.handle_execute(
        argparse.Namespace(
            execution_id="20260812--travel-article-m100--china--scale-011",
            retry_of=retry_of,
            retry_unfinished_refs=[object_ref],
            family="content/travel/article/article",
            region_ref="china",
            selector="all",
            count=1,
            quota=1,
            target_names=["剑门关"],
            topic="m100-article-wave",
            source_providers=[],
            stage="plan-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert captured["retry_of"] == retry_of
    assert captured["retry_unfinished_refs"] == (object_ref,)
    assert captured["target_names"] == ("剑门关",)
    assert captured["inherited_targets"] == scope.target_rows


def test_existing_homepage_retry_does_not_reopen_predecessor_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    captured: dict[str, object] = {}

    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe.store, "spec_exists", lambda _execution_id: True)
    monkeypatch.setattr(
        recipe,
        "load_frozen_target_set",
        lambda _execution_id: (_ for _ in ()).throw(FileNotFoundError("discarded")),
    )
    monkeypatch.setattr(
        recipe,
        "_run_execution",
        lambda args, **_kwargs: captured.update(vars(args)),
    )

    recipe.handle_execute(
        argparse.Namespace(
            execution_id="20260722--travel-homepage-coverage--test-region-a--pilot-002",
            retry_of="20260722--travel-homepage-coverage--test-region-a--pilot-001",
            semantic_selection_id="cursor_auto",
            semantic_preflight_receipt="data/local/cache/cursor-auto-receipt.json",
            family="content/travel/homepage/homepage",
            region_ref="test-region-a",
            selector="source-ready-priority",
            count=1,
            quota=1,
            target_names=["测试实体甲"],
            topic=None,
            source_providers=[],
            stage="submit-only",
            recover_stage=None,
            recovery_reason=None,
        )
    )

    assert captured["inherited_targets"] == ()
    assert captured["semantic_selection_id"] == "cursor_auto"
    assert (
        captured["semantic_preflight_receipt"]
        == "data/local/cache/cursor-auto-receipt.json"
    )


def test_plan_only_checks_workspace_before_creating_a_work_package(
    monkeypatch, tmp_path: Path
) -> None:
    from core import paths as core_paths
    from support.capacity_calibration_fixture import write_synthetic_capacity_receipt

    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", tmp_path)
    receipt_ref = "data/local/tests/capacity/capacity.json"
    write_synthetic_capacity_receipt(tmp_path / receipt_ref)
    args = argparse.Namespace(
        execution_id=EXECUTION_ID,
        retry_of=None,
        family="content/travel/homepage/homepage",
        region_ref="test-region-a",
        selector="source-ready-priority",
        count=1,
        quota=1,
        capacity_calibration_receipt=receipt_ref,
        semantic_selection_id="default",
        topic=None,
        source_providers=(),
        stage="plan-only",
        recover_stage=None,
        recovery_reason=None,
    )
    from content.execution.agent import agent_conflicts
    from content.execution.planning import semantic_selection

    def _blocked(*_args, **_kwargs) -> None:
        raise agent_conflicts.ManagedWorkspaceConflictError("execution_output_cleanup pid=42")

    monkeypatch.setattr(
        semantic_selection,
        "assert_managed_workspace_available",
        _blocked,
    )
    try:
        recipe._run_execution(args)
    except SystemExit as exc:
        assert "execution_output_cleanup pid=42" in str(exc)
    else:
        raise AssertionError("plan-only must reject an active output cleanup")


def test_post_execute_uses_its_own_frozen_entity_targets(monkeypatch, tmp_path: Path) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-b"
    reference_root.mkdir(parents=True)
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    captured: dict[str, object] = {}

    def _capture(args, **_kwargs) -> None:
        captured.update(vars(args))

    monkeypatch.setattr(recipe, "_run_execution", _capture)
    args = argparse.Namespace(
        execution_id="20260722--travel-article-supply--test-region-b--pilot-001",
        retry_of=None,
        family="content/travel/article/article",
        region_ref="test-region-b",
        selector="all",
        count=1,
        quota=1,
        target_names=["测试实体甲"],
        topic="test-topic-a",
        source_providers=[],
        stage="plan-only",
        recover_stage=None,
        recovery_reason=None,
    )

    recipe.handle_execute(args)

    assert captured["target_names"] == ("测试实体甲",)


def test_homepage_execute_requires_source_ready_selection(monkeypatch, tmp_path: Path) -> None:
    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe, "_run_execution", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not execute")))

    args = argparse.Namespace(
        execution_id=EXECUTION_ID,
        retry_of=None,
        family="content/travel/homepage/homepage",
        region_ref="test-region-a",
        selector="all",
        count=1,
        quota=1,
        target_names=[],
        topic=None,
        source_providers=[],
        stage="plan-only",
        recover_stage=None,
        recovery_reason=None,
    )

    try:
        recipe.handle_execute(args)
    except SystemExit as exc:
        assert "source-ready-priority" in str(exc)
    else:
        raise AssertionError("homepage execution must require source-ready selection")


def test_execute_rejects_an_unpaired_recovery_request() -> None:
    try:
        recipe._run_execution(
            argparse.Namespace(
                execution_id=EXECUTION_ID,
                family="content/travel/homepage/homepage",
                recover_stage="download_fetch",
                recovery_reason=None,
            )
        )
    except SystemExit as exc:
        assert "recover-stage" in str(exc)
    else:
        raise AssertionError("unpaired recovery request must fail")


# `task` 门面的完整子命令闭包由 test_cli_environment__behavior__functional 断言，
# 这里不再保留第二份同样的字面清单：两份清单意味着同一契约两处记录。



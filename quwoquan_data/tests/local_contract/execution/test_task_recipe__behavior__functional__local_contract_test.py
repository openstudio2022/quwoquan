# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#sit-001
"""Contract tests for the generic single-work-package content facade."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

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

from content.execution import recipe  # noqa: E402
from content.execution.model_contract import execution_model_pair  # noqa: E402
from content.execution.identity import (  # noqa: E402
    build_execution_id,
    parse_execution_id,
    validate_execution_id,
)
from core.paths import FAMILIES_ROOT, iter_family_files  # noqa: E402
from core.runtime_policy import load_runtime_policy  # noqa: E402


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


def test_article_recipe_does_not_narrow_selection_to_scenic_subtype() -> None:
    article = recipe.load_recipe("content/travel/article/article")

    assert article["selection"]["category"] == "地点"


def test_travel_video_recipe_uses_the_verified_auto_binding() -> None:
    video = recipe.load_recipe("content/travel/video/video")
    author = execution_model_pair(video).author
    runtime = load_runtime_policy(str(video["runtimeProfile"]))
    expected_parameters: list[dict[str, str]] = []

    assert author.model_id == "auto"
    assert author.family.value == "auto"
    assert author.selection.parameters_document() == expected_parameters
    assert runtime.cursor_model_selection.to_sdk_document() == {
        "id": author.model_id,
        "params": expected_parameters,
    }


def test_travel_image_recipe_uses_the_verified_auto_binding() -> None:
    image = recipe.load_recipe("content/travel/image/image")
    author = execution_model_pair(image).author
    runtime = load_runtime_policy(str(image["runtimeProfile"]))
    expected_parameters: list[dict[str, str]] = []

    assert author.model_id == "auto"
    assert author.family.value == "auto"
    assert author.selection.parameters_document() == expected_parameters
    assert runtime.cursor_model_selection.to_sdk_document() == {
        "id": author.model_id,
        "params": expected_parameters,
    }


def test_execution_facade_invokes_the_canonical_data_cli() -> None:
    assert recipe._CLI_PATH == SCRIPTS_ROOT / "cli.py"
    assert recipe._CLI_PATH.is_file()


def test_readiness_calls_only_single_execution_gate() -> None:
    calls: list[list[str]] = []
    recipe._readiness(
        {"readiness": {"requireReviewed": True, "minPassRate": 0.9, "mode": "commercial", "failOnNoGo": True}},
        EXECUTION_ID,
        lambda argv: calls.append(list(argv)) or 0,
    )

    assert calls == [[
        "verify", "execution-readiness", "--execution-id", EXECUTION_ID,
        "--require-reviewed",
        "--min-pass-rate", "0.9",
        "--mode", "commercial",
        "--fail-on-no-go",
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
            "--min-pass-rate",
            "0.9",
            "--mode",
            "commercial",
            "--fail-on-no-go",
        ]
    )

    assert args.execution_id == EXECUTION_ID
    assert args.require_reviewed is True
    assert args.min_pass_rate == 0.9
    assert args.mode == "commercial"
    assert args.fail_on_no_go is True


def test_preflight_evidence_belongs_to_execution_work_package() -> None:
    argv = recipe._runtime_preflight_argv(EXECUTION_ID)
    report_path = Path(argv[argv.index("--report-out") + 1])

    assert argv[:2] == ["task", "preflight"]
    assert report_path == recipe.execution_root(EXECUTION_ID) / "evidence" / "runtime_preflight.json"


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
    with pytest.raises(SystemExit, match=r"inherited candidate pool 2 must stay inside"):
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


def test_plan_only_checks_workspace_before_creating_a_work_package(monkeypatch) -> None:
    args = argparse.Namespace(
        execution_id=EXECUTION_ID,
        retry_of=None,
        family="content/travel/homepage/homepage",
        region_ref="test-region-a",
        selector="source-ready-priority",
        count=1,
        quota=1,
        topic=None,
        source_providers=(),
        stage="plan-only",
        recover_stage=None,
        recovery_reason=None,
    )
    monkeypatch.setattr(recipe, "load_recipe", lambda _ref: {"recipeId": args.family})

    from content.execution.agent import agent_conflicts

    def _blocked(*_args, **_kwargs) -> None:
        raise agent_conflicts.ManagedWorkspaceConflictError("execution_output_cleanup pid=42")

    monkeypatch.setattr(agent_conflicts, "assert_managed_workspace_available", _blocked)
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


def test_frozen_runtime_request_rejects_unknown_or_unordered_fields() -> None:
    request = {
        "familyRef": "content/travel/homepage/homepage",
        "regionRef": "test-region-a",
        "selector": "all",
        "count": 1,
        "quota": 1,
        "topic": None,
        "sourceProviders": ["provider-b", "provider-a"],
        "targetNames": [],
    }
    try:
        recipe.RuntimeExecutionRequest.from_document(request)
    except SystemExit as exc:
        assert "deduplicated and sorted" in str(exc)
    else:
        raise AssertionError("unordered frozen provider IDs must fail")
    request["sourceProviders"] = []
    request["unexpected"] = "value"
    try:
        recipe.RuntimeExecutionRequest.from_document(request)
    except SystemExit as exc:
        assert "keys must be exactly" in str(exc)
    else:
        raise AssertionError("unknown frozen request keys must fail")


def test_execute_rejects_a_provider_outside_the_vertical_policy(monkeypatch, tmp_path: Path) -> None:
    class RejectingProviderPolicy:
        def require_declared(self, provider_ids: tuple[str, ...]) -> None:
            raise ValueError(f"undeclared provider IDs: {provider_ids}")

    reference_root = tmp_path / "quwoquan_data/reference/travel/entities/test-region-a"
    reference_root.mkdir(parents=True)
    monkeypatch.setattr(recipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(recipe, "load_provider_policy", lambda _vertical: RejectingProviderPolicy())
    args = argparse.Namespace(
        execution_id=EXECUTION_ID,
        retry_of=None,
        family="content/travel/homepage/homepage",
        region_ref="test-region-a",
        selector="source-ready-priority",
        count=1,
        quota=1,
        topic=None,
        source_providers=["provider-a"],
        stage="plan-only",
        recover_stage=None,
        recovery_reason=None,
    )
    try:
        recipe.handle_execute(args)
    except SystemExit as exc:
        assert "undeclared provider IDs" in str(exc)
    else:
        raise AssertionError("undeclared provider must fail before execution")


def test_task_facade_exposes_only_durable_commands() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / "cli.py"), "task", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    choices = re.search(r"^  \{([^}]+)\}$", result.stdout, flags=re.MULTILINE)
    assert choices is not None
    assert choices.group(1).split(",") == ["preflight", "execute", "discard"]


def test_execute_cli_accepts_only_explicit_generic_request_parameters() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_ROOT / "cli.py"), "task", "execute", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for option in (
        "--family",
        "--region-ref",
        "--selector",
        "--count",
        "--target",
        "--campaign-envelope",
        "--image-scale-promotion",
        "--video-scale-promotion",
    ):
        assert option in result.stdout
    assert "promote-scale" in result.stdout
    for retired in ("--rollout", "--province", "--mandatory", "--max-workers"):
        assert retired not in result.stdout

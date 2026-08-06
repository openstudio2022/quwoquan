from __future__ import annotations

import shutil

import pytest

from content.execution import workspace
from core.runtime_policy import runtime_profile_digest
from support.execution_manifest_fixture import build_execution_fixture
from support.semantic_preflight_fixture import ready_semantic_preflight


EXECUTION_ID = "20260716--travel-article-manifest-fixture--test-region-b--pilot-991"


@pytest.fixture(autouse=True)
def clean_execution() -> None:
    shutil.rmtree(workspace.execution_root(EXECUTION_ID), ignore_errors=True)
    yield
    shutil.rmtree(workspace.execution_root(EXECUTION_ID), ignore_errors=True)


def test_existing_manifest_is_revalidated_not_accepted_by_existence() -> None:
    targets = [{"name": "测试实体甲", "entityType": "地点/景区"}]
    first = build_execution_fixture(EXECUTION_ID, targets=targets)
    resumed = build_execution_fixture(EXECUTION_ID, targets=targets)

    assert resumed == first
    assert first["modelBinding"] == {
        "provider": "codex_sdk",
        "authorModel": "gpt-5.6-terra",
        "authorModelFamily": "gpt",
        "authorModelParameters": [],
        "reviewerModel": "gpt-5.6-terra",
        "reviewerModelFamily": "gpt",
        "reviewerModelParameters": [],
    }
    assert first["requestRef"] == "0.plan/request.json"
    assert first["runtimeProfileId"] == "semantic_agent_local_calibrated"
    assert first["runtimeProfileDigest"] == runtime_profile_digest(
        "semantic_agent_local_calibrated"
    )
    assert first["semanticSelectionId"] == "default"
    assert first["semanticRuntime"] == "local"
    assert first["targetSetRef"] == "0.plan/target_set.json"
    assert len(first["familyRef"]["sha256"]) == 64
    with pytest.raises(ValueError, match="different frozen target set"):
        build_execution_fixture(
            EXECUTION_ID,
            targets=[{"name": "测试实体乙", "entityType": "地点/景区"}],
        )


@pytest.mark.parametrize(
    ("execution_id", "expected_recipe"),
    (
        ("20260716--travel-homepage-fixture--test-region-a--pilot-992", "content/travel/homepage/homepage"),
        ("20260716--travel-article-fixture--test-region-a--pilot-993", "content/travel/article/article"),
        ("20260716--travel-image-fixture--test-region-a--pilot-994", "content/travel/image/image"),
        ("20260716--travel-video-fixture--test-region-a--pilot-995", "content/travel/video/video"),
    ),
)
def test_fixture_recipe_is_derived_from_content_type(
    execution_id: str,
    expected_recipe: str,
) -> None:
    try:
        manifest = build_execution_fixture(execution_id)
        assert manifest["familyRef"]["ref"] == expected_recipe
    finally:
        shutil.rmtree(workspace.execution_root(execution_id), ignore_errors=True)


def test_cursor_auto_manifest_requires_retry_and_freezes_exact_binding() -> None:
    execution_id = "20260716--travel-article-cursor-auto--test-region-b--pilot-997"
    predecessor = "20260716--travel-article-cursor-auto--test-region-b--pilot-996"
    try:
        with pytest.raises(ValueError, match="requires a new execution with retryOf"):
            build_execution_fixture(
                execution_id,
                semantic_selection_id="cursor_auto",
            )
        _receipt_path, preflight_binding = ready_semantic_preflight("cursor_auto")
        manifest = build_execution_fixture(
            execution_id,
            retry_of=predecessor,
            semantic_selection_id="cursor_auto",
            semantic_preflight_binding=preflight_binding,
        )
        assert manifest["semanticSelectionId"] == "cursor_auto"
        assert manifest["semanticRuntime"] == "local"
        assert manifest["semanticPreflightReceipt"] == preflight_binding
        assert manifest["modelBinding"] == {
            "provider": "cursor_sdk",
            "authorModel": "auto",
            "authorModelFamily": "auto",
            "authorModelParameters": [],
            "reviewerModel": "auto",
            "reviewerModelFamily": "auto",
            "reviewerModelParameters": [],
        }
        with pytest.raises(ValueError, match="does not match expected selection"):
            build_execution_fixture(
                execution_id,
                retry_of=predecessor,
                semantic_selection_id="default",
            )
    finally:
        shutil.rmtree(workspace.execution_root(execution_id), ignore_errors=True)

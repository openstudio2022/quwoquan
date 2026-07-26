from __future__ import annotations

import shutil

import pytest

from content.execution import workspace
from support.execution_manifest_fixture import build_execution_fixture


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
        "provider": "cursor_sdk",
        "authorModel": "grok-4.5",
        "authorModelFamily": "grok",
        "authorModelParameters": [
            {"id": "effort", "value": "high"},
            {"id": "fast", "value": "false"},
        ],
        "reviewerModel": "composer-2.5",
        "reviewerModelFamily": "composer",
        "reviewerModelParameters": [],
    }
    assert first["requestRef"] == "0.plan/request.json"
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

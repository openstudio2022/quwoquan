from __future__ import annotations

import shutil

import pytest

from content.execution import workspace
from support.execution_manifest_fixture import build_execution_fixture


EXECUTION_ID = "20260716--travel-article-manifest-fixture--cn-sichuan--canary-991"


@pytest.fixture(autouse=True)
def clean_execution() -> None:
    shutil.rmtree(workspace.execution_root(EXECUTION_ID), ignore_errors=True)
    yield
    shutil.rmtree(workspace.execution_root(EXECUTION_ID), ignore_errors=True)


def test_existing_manifest_is_revalidated_not_accepted_by_existence() -> None:
    targets = [{"name": "九寨沟", "entityType": "地点/景区"}]
    first = build_execution_fixture(EXECUTION_ID, targets=targets)
    resumed = build_execution_fixture(EXECUTION_ID, targets=targets)

    assert resumed == first
    assert first["modelBinding"] == {
        "provider": "cursor_sdk",
        "authorModel": "composer-2.5",
        "authorModelFamily": "composer",
        "reviewerModel": "gpt-5.5",
        "reviewerModelFamily": "gpt",
    }
    assert first["pricingRevision"]
    assert first["rolloutContract"]["path"].endswith(
        "two_province_homepage_rollout.yaml"
    )
    assert len(first["rolloutContract"]["sha256"]) == 64
    with pytest.raises(ValueError, match="different frozen target set"):
        build_execution_fixture(
            EXECUTION_ID,
            targets=[{"name": "黄龙", "entityType": "地点/景区"}],
        )


@pytest.mark.parametrize(
    ("execution_id", "expected_recipe"),
    (
        ("20260716--travel-homepage-fixture--cn-zhejiang--canary-992", "content/travel/homepage/homepage"),
        ("20260716--travel-article-fixture--cn-zhejiang--canary-993", "content/travel/article/article"),
        ("20260716--travel-image-fixture--cn-zhejiang--canary-994", "content/travel/image/image"),
        ("20260716--travel-video-fixture--cn-zhejiang--canary-995", "content/travel/video/video"),
    ),
)
def test_fixture_recipe_is_derived_from_content_type(
    execution_id: str,
    expected_recipe: str,
) -> None:
    try:
        manifest = build_execution_fixture(execution_id)
        assert manifest["recipe"]["ref"] == expected_recipe
    finally:
        shutil.rmtree(workspace.execution_root(execution_id), ignore_errors=True)

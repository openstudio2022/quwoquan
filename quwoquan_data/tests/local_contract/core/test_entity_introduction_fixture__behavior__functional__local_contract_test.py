"""Immutable release entity introduction projection contract.

The local contract uses one frozen, typed object snapshot.  It never creates an
environment fixture, writes a database seed, or owns importer lifecycle state.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-001.t2
"""
from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
if str(DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_ROOT))

from tests.support.entity_introduction_fixture import (
    EntityIntroductionProjection,
    ImmutableReleaseEntityIntroduction,
    IntroductionAsset,
    project_entity_introduction,
)

PAGE_MARKDOWN = """---
title: 测试山
coverImage: asset://测试山_cover_雪峰全景_1_aabbccdd
---

# 测试山

测试山位于测试省，是三段结构投影的合约样本，导语必须成为概况章节与摘要来源。

## 历史沿革

早期开凿，持续演进。

:::figure id="fig_01" layout="fullWidth" caption="山门旧照"
asset://测试山_detail_山门_2_11223344
:::

## 相关图片

:::gallery ids="测试山_related_远眺_3_55667788,测试山_detail_山门_2_11223344" layout="grid"
:::
"""


def immutable_release_snapshot(
    *,
    media_resolved: bool = True,
) -> ImmutableReleaseEntityIntroduction:
    def release_url(asset_id: str) -> str:
        if not media_resolved:
            return ""
        return (
            "https://cdn.example.invalid/media/image/s/asset/"
            f"{asset_id}/v1/source.webp"
        )

    return ImmutableReleaseEntityIntroduction(
        entity_ref="地点/景区/测试山",
        display_name="测试山",
        page_markdown=PAGE_MARKDOWN,
        fallback_summary="测试山 fallback 摘要",
        assets=(
            IntroductionAsset(
                asset_id="测试山_cover_雪峰全景_1_aabbccdd",
                url=release_url("测试山_cover_雪峰全景_1_aabbccdd"),
                caption="雪峰全景",
                role="cover",
                source_ref="sources/测试山/source.md",
            ),
            IntroductionAsset(
                asset_id="测试山_detail_山门_2_11223344",
                url=release_url("测试山_detail_山门_2_11223344"),
                caption="山门旧照",
                role="inline",
                source_ref="sources/测试山/source.md",
            ),
            IntroductionAsset(
                asset_id="测试山_related_远眺_3_55667788",
                url=release_url("测试山_related_远眺_3_55667788"),
                caption="",
                role="related",
                source_ref="sources/测试山/source.md",
            ),
        ),
    )


def test_projection_three_segments_and_release_asset_binding() -> None:
    snapshot = immutable_release_snapshot()

    projection, issues = project_entity_introduction(snapshot)

    assert isinstance(projection, EntityIntroductionProjection)
    assert issues == ()
    assert projection.entity_ref == "地点/景区/测试山"
    assert projection.display_name == "测试山"
    assert projection.cover_url.endswith(
        "/测试山_cover_雪峰全景_1_aabbccdd/v1/source.webp"
    )
    assert "三段结构投影的合约样本" in projection.summary

    assert [section.kind for section in projection.sections] == [
        "overview",
        "body",
        "relatedImages",
    ]

    body = projection.sections[1]
    assert body.title == "历史沿革"
    assert body.body_markdown is not None
    assert ':::figure id="fig_01"' in body.body_markdown
    assert [asset.asset_id for asset in body.assets] == [
        "测试山_detail_山门_2_11223344"
    ]
    assert body.assets[0].role == "inline"

    related = projection.sections[2]
    assert [asset.asset_id for asset in related.assets] == [
        "测试山_related_远眺_3_55667788",
        "测试山_detail_山门_2_11223344",
    ]
    assert all(asset.role == "related" for asset in related.assets)
    assert related.body_markdown is None


def test_projection_is_deterministic_and_does_not_mutate_release_object() -> None:
    snapshot = immutable_release_snapshot()

    first = project_entity_introduction(snapshot)
    second = project_entity_introduction(snapshot)

    assert first == second
    assert snapshot.assets[1].role == "inline"
    with pytest.raises(FrozenInstanceError):
        snapshot.display_name = "不可变"  # type: ignore[misc]


def test_unresolved_release_assets_are_reported_and_not_projected() -> None:
    snapshot = immutable_release_snapshot(media_resolved=False)

    projection, issues = project_entity_introduction(snapshot)

    assert len(issues) == 3
    assert all("release media authority" in issue for issue in issues)
    assert projection.cover_url == ""
    assert [section.kind for section in projection.sections] == [
        "overview",
        "body",
    ]
    assert projection.sections[1].assets == ()


def test_projection_contract_contains_only_introduction_read_model_fields() -> None:
    assert tuple(field.name for field in fields(ImmutableReleaseEntityIntroduction)) == (
        "entity_ref",
        "display_name",
        "page_markdown",
        "assets",
        "fallback_summary",
    )
    assert tuple(field.name for field in fields(EntityIntroductionProjection)) == (
        "entity_ref",
        "display_name",
        "cover_url",
        "summary",
        "sections",
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

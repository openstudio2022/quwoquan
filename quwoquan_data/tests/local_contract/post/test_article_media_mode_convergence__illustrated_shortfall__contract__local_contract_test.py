"""来源 `illustrated` 失去派生依据时只允许单向收敛为 `text_only`。

来源 meta 的 `illustrated` 本身由「同源可发布图片 >= 2」派生。发布评估把图剔到
不足两张后该派生失去依据，packet 收敛为 `text_only` 与来源 meta 之间必然出现
差异；把这个差异当成漂移会连合格正文一起丢弃，把它无条件放过又等于允许 packet
随意改写媒体形态。本测试把「只接受空素材集合的单向收敛」钉住。
"""
from __future__ import annotations

from content.post.article.article_media_contract import (
    article_media_mode_converges_to_text_only,
    article_plan_media_binding_issues,
)

_SOURCE_FREEZE = {"sourceUnitRef": "sources/article-unit", "assetCount": 2}


def _binding_issues(
    *,
    mode: str,
    source_mode: str,
    asset_refs: tuple[str, ...],
    source_unit_freeze: object = None,
) -> list[str]:
    return article_plan_media_binding_issues(
        ref="/post/article/攻略/示例/1",
        publish_media_mode=mode,
        source_publish_media_mode=source_mode,
        asset_refs=asset_refs,
        source_unit_freeze=source_unit_freeze,
    )


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-004.t3
def test_converged_text_only_packet_is_accepted_against_an_illustrated_source() -> None:
    assert _binding_issues(mode="text_only", source_mode="illustrated", asset_refs=()) == []


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-004.t3
def test_convergence_requires_an_empty_asset_set() -> None:
    """留着素材引用就不是收敛，而是 text_only 契约违反 + 形态漂移。"""
    issues = _binding_issues(
        mode="text_only",
        source_mode="illustrated",
        asset_refs=("sources/article-unit/assets/a.jpg",),
    )
    assert any("assetRefs must be empty" in issue for issue in issues)
    assert any("does not match source meta" in issue for issue in issues)


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-004.t3
def test_converged_packet_must_not_keep_the_source_unit_freeze() -> None:
    issues = _binding_issues(
        mode="text_only",
        source_mode="illustrated",
        asset_refs=(),
        source_unit_freeze=_SOURCE_FREEZE,
    )
    assert any("must not bind articleSourceUnitFreeze" in issue for issue in issues)


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-004.t4
def test_reverse_direction_is_never_a_convergence() -> None:
    """text_only 来源升为 illustrated 等于凭空造图。"""
    issues = _binding_issues(
        mode="illustrated",
        source_mode="text_only",
        asset_refs=(
            "sources/article-unit/assets/a.jpg",
            "sources/article-unit/assets/b.jpg",
        ),
        source_unit_freeze=_SOURCE_FREEZE,
    )
    assert any("does not match source meta" in issue for issue in issues)
    assert not article_media_mode_converges_to_text_only(
        source_publish_media_mode="text_only",
        publish_media_mode="illustrated",
        asset_count=2,
    )


# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-004.t3
def test_matching_illustrated_modes_still_require_cover_and_body() -> None:
    """收敛的放宽不得削弱 illustrated 自身的同源双图硬门。"""
    issues = _binding_issues(
        mode="illustrated",
        source_mode="illustrated",
        asset_refs=("sources/article-unit/assets/a.jpg",),
        source_unit_freeze=_SOURCE_FREEZE,
    )
    assert any("requires at least two assetRefs" in issue for issue in issues)

"""RC6 形态自适应字数门契约：长文≥600 / 图文混排≥200+图 单一真相源。

唯一真相源 = _common.base_draft.base_draft_readiness；verify/review/run.py 预检
都必须经此消费，禁止固定 600 raw 第二真相源误杀图多文少的真·图文底稿。
"""
from __future__ import annotations

from _common import base_draft
from _common import content_review


def _rich_mixed_article(*, figures: int = 3, prose_chars: int = 240, caption_chars: int = 120) -> str:
    prose = "这是一段以底稿为骨架的真实图文混排正文叙述，描述沿途见闻与体验细节。" * 1
    prose = (prose * ((prose_chars // len(prose)) + 1))[:prose_chars]
    blocks = []
    for i in range(figures):
        cap = ("湖水在晨光里呈现层叠的蓝绿色，栈道沿着水岸延伸。" * 1)
        cap = (cap * ((caption_chars // len(cap)) + 1))[:caption_chars]
        blocks.append(f":::figure\n![{cap}](asset://source-inline-{i:03d})\n{cap}\n:::")
    return prose + "\n\n" + "\n\n".join(blocks) + "\n"


def test_long_form_text_needs_600_chars():
    short = "短文" * 100  # 200 chars, no figures
    long = "长文正文叙述内容。" * 80  # >600 chars
    assert base_draft.base_draft_readiness(short)["ready"] is False
    long_readiness = base_draft.base_draft_readiness(long)
    assert long_readiness["ready"] is True
    assert long_readiness["sourceForm"] == "text"


def test_rich_mixed_passes_with_200_prose_and_figures():
    # 图多文少：正文≥200 + ≥3 图 + 图注，但总 compact<600（不是长文）
    article = _rich_mixed_article(figures=3, prose_chars=210, caption_chars=30)
    readiness = base_draft.base_draft_readiness(article)
    assert readiness["effectiveChars"] < base_draft.ARTICLE_MIN_BASE_DRAFT_CHARS
    assert readiness["ready"] is True
    assert readiness["sourceForm"] == "rich_mixed"
    assert readiness["inlineFigureCount"] >= 3
    assert readiness["proseChars"] >= base_draft.RICH_MIXED_MIN_TEXT_CHARS


def test_rich_mixed_min_text_chars_is_200_per_authoritative_spec():
    assert base_draft.RICH_MIXED_MIN_TEXT_CHARS == 200


def test_rich_mixed_blocked_when_text_only_media_mode():
    # 同一图多文少底稿，声明 text_only 时不得借图文形态绕过长文门
    article = _rich_mixed_article(figures=3, prose_chars=210, caption_chars=30)
    assert base_draft.base_draft_readiness(article)["sourceForm"] == "rich_mixed"
    readiness = base_draft.base_draft_readiness(article, publish_media_mode="text_only")
    assert readiness["ready"] is False


def test_too_few_figures_does_not_qualify_as_rich_mixed():
    article = _rich_mixed_article(figures=1, prose_chars=240, caption_chars=120)
    readiness = base_draft.base_draft_readiness(article)
    assert readiness["ready"] is False


def test_content_review_word_gate_is_form_adaptive():
    # 图文混排 article carrier：正文≥200且有图 → 不应判 too short
    mixed = _rich_mixed_article(figures=3, prose_chars=240, caption_chars=120)
    issues = content_review.check_narrative_quality(mixed, {"carrier": "article"})
    assert not any("adaptive word gate" in issue for issue in issues)

    # 纯短文 article carrier：<600 且无图 → 必须判失败
    short = "短文正文。" * 20  # ~100 chars
    issues_short = content_review.check_narrative_quality(short, {"carrier": "article"})
    assert any("adaptive word gate" in issue for issue in issues_short)

    # image/gallery 图片作品：不受正文长度门约束
    issues_gallery = content_review.check_narrative_quality(short, {"carrier": "gallery"})
    assert not any("adaptive word gate" in issue for issue in issues_gallery)

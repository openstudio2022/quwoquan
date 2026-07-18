"""开篇门语义化 + 跨篇相似度门 红绿契约 ——「美·破千篇一律」。

覆盖：
- 套路化开头（评审痛点原句）在所选体裁下判 revision；落地体裁允许的开篇策略则放行。
- draft_meta 声明的 openingStrategy 与正文开篇不符时记录 observation，不触发重写。
- 同批多篇开篇雷同（换实体名不换句式）被跨篇相似度门拦截；切换角度则放行。

可直接运行：python3 quwoquan_data/tests/local_contract/post/test_style_gates__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))


from content.post.article.draft_io import write_agent_draft  # noqa: E402
from content.post.object_index import register_content_object  # noqa: E402
from content.post.content_review import check_narrative_quality  # noqa: E402
from core.paths import ensure_execution_command_layout, ensure_execution_layout  # noqa: E402
from content.post.article.route_review_checks import (  # noqa: E402
    _check_cross_article_similarity,
    _check_travelogue_density,
)
from verify.verify_content_quality import forbidden_phrase_hits  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402

# 隔离开篇校验：关闭 like/dislike/decision/tips，仅观察开篇钩子是否落地。
DENSITY_BRIEF = {
    "openingTension": {"required": True},
    "explicitFeelings": {"requireLike": False, "requireDislike": False},
    "decisionPoints": {"required": False, "minPoints": 0},
    "tipsEmbeddingPolicy": {"forbidStandaloneBlock": False},
}

MONOTONOUS_OPENING = "九寨沟的水，我在屏幕上看了无数遍，总怕亲眼一看会不过如此。\n\n## 正文\n后续。"


def test_monotonous_opening_blocked_for_guide_family():
    res = _check_travelogue_density(MONOTONOUS_OPENING, DENSITY_BRIEF, style_family="实用攻略风")
    assert not res["passed"], res
    assert any("opening lacks a real hook" in i for i in res["issues"]), res["issues"]


def test_conclusion_first_opening_passes_for_guide_family():
    article = "先说结论：淡季来九寨沟最值，人少水更干净。\n\n## 正文\n后续。"
    res = _check_travelogue_density(article, DENSITY_BRIEF, style_family="实用攻略风")
    assert res["passed"], res["issues"]


def test_negative_tradeoff_markers_include_short_risk_words():
    article = (
        "先说结论：旺季去都江堰要错峰。\n\n"
        "## 正文\n"
        "鱼嘴这一段很打动人，也值得慢慢看；但桥头排队很久，酒店价格翻倍，"
        "带老人时不建议硬排，放弃硬排反而更稳。如果你只能国庆去，我会建议住成都早出晚归。"
    )
    res = _check_travelogue_density(article, {}, style_family="实用攻略风")
    assert res["passed"], res["issues"]


def test_opening_after_title_figure_and_heading_is_detected():
    article = (
        "# 九寨沟·值不值得去\n\n"
        ':::figure id="cover" layout="fullWidth" caption="水色"\n'
        "asset://jiuzhaigou_cover\n"
        ":::\n\n"
        "## 先说结论\n\n"
        "直接说：淡季来九寨沟最值，人少水更干净，预算也更稳。\n\n"
        "## 正文\n后续。"
    )
    res = _check_travelogue_density(article, DENSITY_BRIEF, style_family="实用攻略风")
    assert res["passed"], res["issues"]


def test_scene_immersion_passes_for_journal_family():
    article = "清晨我推开客栈木门，雾还压在山脊上，脚下的石板沁着凉。\n\n## 正文\n后续。"
    res = _check_travelogue_density(article, DENSITY_BRIEF, style_family="旅途随笔风")
    assert res["passed"], res["issues"]


def test_declared_opening_strategy_mismatch_is_observation_not_revision():
    # 声明 scene_immersion，实际开篇是 conclusion_first；记录审计观察，不为元数据分类差异重写正文。
    article = "先说结论：值得专门来一趟。\n\n## 正文\n后续。"
    res = _check_travelogue_density(
        article, DENSITY_BRIEF, style_family="实用攻略风", opening_strategy="scene_immersion"
    )
    assert res["passed"], res
    assert any("not reflected" in i for i in res["observations"]), res


_EXECUTION_ID = "20260711--travel-article-style-gates--cn-sichuan--canary-001"


def _seed_draft(ref: str, article: str) -> None:
    build_execution_fixture(_EXECUTION_ID)
    register_content_object(_EXECUTION_ID, ref, content_type="article", angle="体验", title=ref)
    write_agent_draft(
        _EXECUTION_ID,
        ref,
        article,
        model="test-agent/style-gate",
        cited_source_paths=[],
        covered_facts=[],
        agent_run_id=f"run-{ref}",
        agent_id=f"agent-{ref}",
    )


def test_cross_article_similarity_blocks_cloned_opening():
    ensure_execution_layout(_EXECUTION_ID)
    ensure_execution_command_layout(_EXECUTION_ID, "post")
    a = "清晨我推开客栈木门，雾还压在山脊上，风从谷底一阵阵涌上来。\n\n## 正文\n海螺沟的内容。"
    # 换地名不换句式的克隆开篇（量产千篇一律的典型）。
    b = "清晨我推开客栈木门，雾还压在山脊上，风从河谷一阵阵涌上来。\n\n## 正文\n四姑娘山的内容。"
    _seed_draft("海螺沟_体验", a)
    _seed_draft("四姑娘山_体验", b)
    res = _check_cross_article_similarity(_EXECUTION_ID, "四姑娘山_体验", b)
    assert not res["passed"], res
    assert any("too similar to sibling" in i for i in res["issues"]), res["issues"]


def test_cross_article_similarity_passes_distinct_opening():
    ensure_execution_layout(_EXECUTION_ID)
    ensure_execution_command_layout(_EXECUTION_ID, "post")
    c = "先说结论：这条线淡季来最划算，预算能省一半，还完全避开了排队和人挤人的扫兴时刻。\n\n## 正文\n稻城亚丁的完全不同的展开内容与判断。"
    _seed_draft("稻城亚丁_攻略", c)
    res = _check_cross_article_similarity(_EXECUTION_ID, "稻城亚丁_攻略", c)
    assert res["passed"], res["issues"]


def test_cross_article_similarity_ignores_frontmatter_only_overlap():
    ensure_execution_layout(_EXECUTION_ID)
    ensure_execution_command_layout(_EXECUTION_ID, "post")
    article = (
        "---\n"
        "title: 峨眉山·攻略\n"
        "template: journal\n"
        "fontPreset: clean\n"
        "markdownDialect: qwq-rich-md\n"
        "---\n\n"
        "先说结论：报国寺到清音阁适合作为第一天，金顶放到第二天清晨更稳妥。\n\n"
        "## 正文\n"
        "攻略展开。"
    )
    gallery = (
        "---\n"
        "title: 峨眉山·金顶图集\n"
        "template: journal\n"
        "fontPreset: clean\n"
        "markdownDialect: qwq-rich-md\n"
        "---\n\n"
        "站上金顶时，先撞进视线的是华藏寺、普贤像和被风推开的云海。\n\n"
        "## 正文\n"
        "图集展开。"
    )
    _seed_draft("峨眉山_攻略_frontmatter", article)
    _seed_draft("峨眉山_画报_frontmatter", gallery)
    res = _check_cross_article_similarity(_EXECUTION_ID, "峨眉山_攻略_frontmatter", article)
    assert res["passed"], res["issues"]


def test_forbidden_placeholder_gate_does_not_block_normal_occupy_word():
    assert forbidden_phrase_hits("凌晨到金顶占位，等到八点仍只见大雾。") == []
    assert "占位稿" in forbidden_phrase_hits("这是一段占位稿，不能发布。")


def test_review_blocks_batch_boundary_terms_before_release_gate():
    issues = check_narrative_quality("同批次另一篇提到了雨季经验。", {"template": "travel.entity.guide"})
    assert any("批次" in issue for issue in issues), issues


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"style gates tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

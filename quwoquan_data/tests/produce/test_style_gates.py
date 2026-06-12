"""开篇门语义化 + 跨篇相似度门 红绿契约 ——「美·破千篇一律」。

覆盖：
- 套路化开头（评审痛点原句）在所选体裁下判 revision；落地体裁允许的开篇策略则放行。
- draft_meta 声明的 openingStrategy 与正文开篇不符时判 revision（诚信校验）。
- 同批多篇开篇雷同（换实体名不换句式）被跨篇相似度门拦截；切换角度则放行。

可直接运行：python3 quwoquan_data/tests/produce/test_style_gates.py
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

os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.draft_io import write_agent_draft  # noqa: E402
from _common.content_object import register_content_object  # noqa: E402
from _common.paths import ensure_batch_layout, ensure_task_layout  # noqa: E402
from produce.route_workflow import (  # noqa: E402
    _check_cross_article_similarity,
    _check_travelogue_density,
)

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


def test_scene_immersion_passes_for_journal_family():
    article = "清晨我推开客栈木门，雾还压在山脊上，脚下的石板沁着凉。\n\n## 正文\n后续。"
    res = _check_travelogue_density(article, DENSITY_BRIEF, style_family="旅途随笔风")
    assert res["passed"], res["issues"]


def test_declared_opening_strategy_must_match_body():
    # 声明 scene_immersion，实际开篇是 conclusion_first → 诚信门拦截。
    article = "先说结论：值得专门来一趟。\n\n## 正文\n后续。"
    res = _check_travelogue_density(
        article, DENSITY_BRIEF, style_family="实用攻略风", opening_strategy="scene_immersion"
    )
    assert not res["passed"], res
    assert any("not reflected" in i for i in res["issues"]), res["issues"]


_TASK = "风格门_gwt"
_BATCH = "pilot"


def _seed_draft(ref: str, article: str) -> None:
    register_content_object(_TASK, _BATCH, ref, content_type="article", angle="体验", title=ref)
    write_agent_draft(
        _TASK,
        _BATCH,
        ref,
        article,
        model="test-agent/style-gate",
        cited_source_paths=[],
        covered_facts=[],
        agent_run_id=f"run-{ref}",
        agent_id=f"agent-{ref}",
    )


def test_cross_article_similarity_blocks_cloned_opening():
    ensure_task_layout(_TASK)
    ensure_batch_layout(_TASK, _BATCH, "produce")
    a = "清晨我推开客栈木门，雾还压在山脊上，风从谷底一阵阵涌上来。\n\n## 正文\n海螺沟的内容。"
    # 换地名不换句式的克隆开篇（量产千篇一律的典型）。
    b = "清晨我推开客栈木门，雾还压在山脊上，风从河谷一阵阵涌上来。\n\n## 正文\n四姑娘山的内容。"
    _seed_draft("海螺沟_体验", a)
    _seed_draft("四姑娘山_体验", b)
    res = _check_cross_article_similarity(_TASK, _BATCH, "四姑娘山_体验", b)
    assert not res["passed"], res
    assert any("too similar to sibling" in i for i in res["issues"]), res["issues"]


def test_cross_article_similarity_passes_distinct_opening():
    ensure_task_layout(_TASK)
    ensure_batch_layout(_TASK, _BATCH, "produce")
    c = "先说结论：这条线淡季来最划算，预算能省一半，还完全避开了排队和人挤人的扫兴时刻。\n\n## 正文\n稻城亚丁的完全不同的展开内容与判断。"
    _seed_draft("稻城亚丁_攻略", c)
    res = _check_cross_article_similarity(_TASK, _BATCH, "稻城亚丁_攻略", c)
    assert res["passed"], res["issues"]


def test_cross_article_similarity_ignores_frontmatter_only_overlap():
    ensure_task_layout(_TASK)
    ensure_batch_layout(_TASK, _BATCH, "produce")
    article = (
        "---\n"
        "title: 峨眉山·攻略\n"
        "template: journal\n"
        "fontPreset: clean\n"
        "articleMarkdownVersion: qwq-rich-md/1\n"
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
        "articleMarkdownVersion: qwq-rich-md/1\n"
        "---\n\n"
        "站上金顶时，先撞进视线的是华藏寺、普贤像和被风推开的云海。\n\n"
        "## 正文\n"
        "图集展开。"
    )
    _seed_draft("峨眉山_攻略_frontmatter", article)
    _seed_draft("峨眉山_画报_frontmatter", gallery)
    res = _check_cross_article_similarity(_TASK, _BATCH, "峨眉山_攻略_frontmatter", article)
    assert res["passed"], res["issues"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"style gates tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

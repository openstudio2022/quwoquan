"""Content plan article candidate ordering is quality-driven."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from task.run import _article_source_quality_sort_key  # noqa: E402
from _common.entity_focus import (  # noqa: E402
    entity_focus_score as _entity_focus_score,
    entity_focus_aliases as _entity_focus_aliases,
)


def test_article_source_quality_sort_has_no_qunar_prefix_bias():
    candidates = [
        {
            "sourceId": "article_qunar_base_1",
            "sourceQualityScore": 0,
            "textLen": 3000,
            "rows": [{"fileName": "a.jpg"}],
        },
        {
            "sourceId": "article_xiaohongshu_base_1",
            "sourceQualityScore": 0,
            "textLen": 4800,
            "rows": [{"fileName": "b.jpg"}, {"fileName": "c.jpg"}],
        },
    ]
    ordered = sorted(candidates, key=_article_source_quality_sort_key)
    assert ordered[0]["sourceId"] == "article_xiaohongshu_base_1"


def test_article_source_quality_sort_prefers_entity_focus_over_length():
    """R-CS01: 聚焦单实体的短游记必须压过聚焦极低的长篇多城游记，避免 fidelity 门被源错配拖垮。"""
    candidates = [
        {
            "sourceId": "article_qunar_multicity",  # 长、质量同，但只 8% 聚焦目标实体
            "sourceQualityScore": 3,
            "textLen": 6000,
            "entityFocusScore": 0.08,
            "rows": [{"fileName": "a.jpg"}],
        },
        {
            "sourceId": "article_qunar_focused",  # 短，但 61% 聚焦目标实体
            "sourceQualityScore": 3,
            "textLen": 1100,
            "entityFocusScore": 0.61,
            "rows": [{"fileName": "b.jpg"}],
        },
    ]
    ordered = sorted(candidates, key=_article_source_quality_sort_key)
    assert ordered[0]["sourceId"] == "article_qunar_focused"


def test_entity_focus_score_counts_alias_lines():
    aliases = _entity_focus_aliases("青城山")
    assert "青城山" in aliases and "青城" in aliases
    # 聚焦游记：多数信号行复述实体名（含短名别名）
    focused = "青城山是道教圣山\n问道青城，左上经天师洞\n青城山下住一晚最方便"
    off_topic = "钵钵鸡很好吃\n五粮液博物馆\n酒店点评一般"
    assert _entity_focus_score(focused, "青城山") > 0.6
    assert _entity_focus_score(off_topic, "青城山") == 0.0


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content plan quality sort tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

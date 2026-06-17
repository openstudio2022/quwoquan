"""Unified content source registry and prompt contracts."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.content_source_registry import (  # noqa: E402
    build_content_source_guidance,
    render_lane_source_prompt,
    verify_content_source_registry,
)


def test_content_source_registry_is_valid_and_covers_all_lanes():
    assert verify_content_source_registry() == []
    guidance = build_content_source_guidance("travel")
    assert set(guidance["lanes"]) == {"homepage", "article", "image", "video"}
    homepage = guidance["lanes"]["homepage"]["sources"]
    image = guidance["lanes"]["image"]["sources"]
    article = guidance["lanes"]["article"]["sources"]
    assert any(row["platform"] == "Wikipedia" for row in homepage)
    assert any(row["platform"] == "Pinterest" for row in image)
    assert any(row["platform"] == "图虫" for row in image)
    assert any(row["sourceClass"] == "ugc_longform" for row in article)


def test_lane_prompt_is_rendered_from_registry_policy():
    article_prompt = render_lane_source_prompt(
        "article",
        vertical="travel",
        per_target_articles=3,
        article_intents=["planning_consultation", "decision_experience", "route_transport"],
    )
    image_prompt = render_lane_source_prompt("image", vertical="travel", per_target_image_works=2)
    homepage_prompt = render_lane_source_prompt("homepage", vertical="travel")
    assert "不得因 UGC/垂类专业/平台文章类别天然升降级" in article_prompt
    assert "去哪儿攻略" in article_prompt and "马蜂窝" in article_prompt
    assert "Pinterest" in image_prompt and "图虫" in image_prompt
    assert "逐图授权链" in image_prompt
    assert "最多保留 5 个核心来源" in homepage_prompt


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content source registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

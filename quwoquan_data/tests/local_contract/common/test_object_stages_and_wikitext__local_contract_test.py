"""ensure_object_stages + wiki wikitext 解析 local_contract。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.paths import OBJECT_STAGES, ensure_object_stages  # noqa: E402
from _common.wiki_wikitext import parse_wikitext_placements  # noqa: E402


def test_ensure_object_stages_creates_full_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        obj = Path(tmp) / "entities/地点/景区/测试"
        ensure_object_stages(obj)
        for stage in OBJECT_STAGES:
            assert (obj / stage).is_dir(), f"missing {stage}"


def test_wikitext_parse_outline_and_placements() -> None:
    text = """== 历史变迁 ==

第一段正文足够长以计入章节统计阈值之下仍会被 outline 解析模块识别为独立章节内容。

[[File:Dujiangyan.jpg|thumb|都江堰鸟瞰]]

=== 技术变革 ===

技术段落。[[File:Iron_turtle.jpg|铁龟遗迹]]
"""
    outline, placements = parse_wikitext_placements(text, min_section_body_chars=10)
    titles = [row["title"] for row in outline]
    assert "技术变革" in titles
    assert len(placements) >= 2
    assert any(p.get("caption") == "都江堰鸟瞰" for p in placements)


def _run() -> None:
    test_ensure_object_stages_creates_full_tree()
    test_wikitext_parse_outline_and_placements()
    print("OK: object stages + wikitext contract passed")


if __name__ == "__main__":
    _run()

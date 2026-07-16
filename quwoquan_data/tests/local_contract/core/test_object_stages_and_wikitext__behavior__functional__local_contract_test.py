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

from core.paths import OBJECT_STAGES, ensure_object_stages  # noqa: E402
from core.wiki_wikitext import parse_wikitext_placements  # noqa: E402


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


def test_putuoshan_snapshot_keeps_all_17_images_and_cleans_dimension_caption() -> None:
    gallery_rows = "\n".join(
        f"File:普陀山图集_{index:02d}.jpg|普陀山图集说明{index:02d}"
        for index in range(1, 13)
    )
    text = f"""[[File:南海观音像.jpg|thumb|[[普陀山南海观音立像|普陀山“南海观音”]]|291x291px]]

== 地理生态 ==
[[File:Model_of_Putuo_Shan_island.JPG|thumb|普陀山全貌模型]]
正文。
[[File:Putuo_Shan_2006_1.JPG|thumb|普陀山海景]]

== 人文景观 ==
{{{{Infobox
| name = 普陀山牌坊
| image = 2013年普陀山牌坊.jpg
| caption = 普陀山海岸牌坊
}}}}
=== 南海观音像 ===
[[File:Statue_of_Guanyin,_Mt_Putuo,_China.jpg|thumb|南海观音像]]

== 图集 ==
<gallery>
{gallery_rows}
</gallery>
"""
    _outline, placements = parse_wikitext_placements(text)
    assert len(placements) == 17
    assert placements[0]["placementType"] == "lead"
    assert placements[0]["caption"] == "普陀山“南海观音”"
    assert "291x291px" not in placements[0]["caption"]
    assert len([row for row in placements if row["placementType"] == "groupMember"]) == 12


def test_dongqianlake_snapshot_keeps_infobox_and_four_gallery_members() -> None:
    text = """{{Infobox
| name = 东钱湖
| image = 20240730_Dongqian_Hu.jpg
| caption = Dongqian Lake
}}

== 图片 ==
{{Gallery
|File:Xiaoputuo Shuishangguanyin 1.jpg|小普陀水上观音
|File:Xiaoputuo Shuishangguanyin 2.jpg|小普陀水上观音
|File:Butuodongtian 1.jpg|补陀洞天石窟
|File:Butuodongtian 2.jpg|补陀洞天石窟
}}
"""
    _outline, placements = parse_wikitext_placements(text)
    assert len(placements) == 5
    assert placements[0]["placementType"] == "infoboxLead"
    assert [row["placementType"] for row in placements[1:]] == ["groupMember"] * 4
    assert len({row["groupId"] for row in placements[1:]}) == 1


def _run() -> None:
    test_ensure_object_stages_creates_full_tree()
    test_wikitext_parse_outline_and_placements()
    print("OK: object stages + wikitext contract passed")


if __name__ == "__main__":
    _run()

"""单一门库 quality_gates contract tests。

可直接运行：python3 quwoquan_data/tests/common/test_quality_gates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common import quality_gates as qg  # noqa: E402


def test_writing_intent_contract():
    assert qg.writing_intent_issues("planning_consultation") == []
    assert qg.writing_intent_issues("") and "missing" in qg.writing_intent_issues("")[0]
    assert qg.writing_intent_issues("foo") and "invalid" in qg.writing_intent_issues("foo")[0]


def test_image_reference_closure_blocks_cover_only():
    assets = [{"assetId": "a1"}, {"assetId": "a2"}]
    body_no_img = "# 标题\n\n正文里没有任何图片引用。"
    issues = qg.image_reference_closure_issues(body_no_img, assets)
    assert issues and "references none" in issues[0]
    body_with_img = "# 标题\n\n看这里 asset://a1 \n\n再看 asset://a2"
    assert qg.image_reference_closure_issues(body_with_img, assets) == []
    # gallery 载体不由本门管控
    assert qg.image_reference_closure_issues(body_no_img, assets, carrier="gallery") == []


def test_image_reference_closure_route_nodes():
    assets = [{"assetId": f"a{i}"} for i in range(4)]
    body_one = "正文 asset://a0 只插一张。"
    issues = qg.image_reference_closure_issues(body_one, assets, route_node_count=4)
    assert issues and "bind images to nodes" in issues[0]
    body_two = "节点一 asset://a0 节点二 asset://a1"
    assert qg.image_reference_closure_issues(body_two, assets, route_node_count=4) == []


def test_writing_intent_consistency():
    guide = "第一天先到，怎么去看高铁，门票要预约，如果你赶时间建议避开旺季。"
    assert qg.writing_intent_consistency_issues(guide, "planning_consultation") == []
    # 游记主线但写成攻略口吻：缺时间线/现场/情绪桶
    journal_as_guide = "门票多少钱，怎么坐车，开放时间，预约方式，停车在哪。"
    assert qg.writing_intent_consistency_issues(journal_as_guide, "post_trip_journal")


def test_skeleton_similarity():
    mine = "## 初见\n\n第一段。\n\n## 不足\n\n第二段。\n\n相同的结尾段落写在这里。"
    peer = "## 初见\n\n别的内容。\n\n## 不足\n\n别的段落。\n\n相同的结尾段落写在这里。"
    assert qg.skeleton_similarity_issues(mine, [peer])
    distinct = "## 抵达那天\n\n完全不同的开头叙述当时的天气。\n\n截然不同的收尾感受与判断。"
    assert qg.skeleton_similarity_issues(distinct, []) == []


def test_register_lexicon():
    assert qg.register_lexicon_issues("我们去看展厅展陈讲解", ["看展", "展厅"])
    assert qg.register_lexicon_issues("我们去爬山看云海", ["看展", "展厅"]) == []
    assert qg.register_lexicon_issues("任意正文", []) == []


def test_source_reject_block():
    assert qg.source_reject_block_issues(["s/1", "s/2"], ["s/2"])
    assert qg.source_reject_block_issues(["s/1"], ["s/2"]) == []
    assert qg.source_reject_block_issues(["s/1"], []) == []


def test_semantic_duplicate_simhash():
    gd = DATA_ROOT / "tests" / "fixtures" / "golden_set"
    a = (gd / "bad_template_a.md").read_text(encoding="utf-8")
    b = (gd / "bad_template_b.md").read_text(encoding="utf-8")
    c = (gd / "good_guide.md").read_text(encoding="utf-8")
    assert qg.semantic_duplicate_issues(a, [b]), "换实体名同骨架应被 simhash 拦截"
    assert qg.semantic_duplicate_issues(a, [c]) == [], "不同内容不应误判语义重复"


def test_rubric_consistency():
    assert qg.rubric_consistency_issues([8.0, 8.0, 8.0]) == []
    assert qg.rubric_consistency_issues([2.0, 9.0, 5.0])  # 方差过大判官不可信
    assert qg.rubric_consistency_issues([8.0]) == []  # 单次不评判稳定性


def test_contact_info_blocks_private_phone_and_im():
    from _common import public_contacts as pc

    allowed = pc.allowed_numbers([])
    # 私人座机/手机 → 拦截
    assert qg.contact_info_issues("咨询电话：0836-6966022。", allowed_numbers=allowed)
    assert qg.contact_info_issues("联系手机 13912345678", allowed_numbers=allowed)
    # 微信/QQ → 一律拦截
    assert qg.contact_info_issues("加微信 abc12345 咨询", allowed_numbers=allowed)
    assert qg.contact_info_issues("QQ：123456789", allowed_numbers=allowed)
    # 紧急/公共短号 → 放行
    assert qg.contact_info_issues("遇险拨打110或120", allowed_numbers=allowed) == []
    assert qg.contact_info_issues("全国旅游服务热线12301", allowed_numbers=allowed) == []
    # 经核实的景区官方电话经 extra 放行
    allow_extra = pc.allowed_numbers(["0836-6966022"])
    assert qg.contact_info_issues("景区官方接待电话：0836-6966022", allowed_numbers=allow_extra) == []


def test_mechanical_heading_blocks_listy_titles():
    listy = "## 节点顺序：为什么建议四姑娘山 → 海螺沟 → 亚丁\n\n正文。\n\n## 实用信息\n\n更多。"
    assert qg.mechanical_heading_issues(listy)
    humanized = "## 先去哪后去哪：我推荐的顺序\n\n正文。\n\n## 去之前我踩过的坑\n\n更多。"
    assert qg.mechanical_heading_issues(humanized) == []
    # extra 词可扩展
    assert qg.mechanical_heading_issues("## 行程速览\n\n正文", extra_terms=["行程速览"])


def test_public_contacts_catalog_loads():
    from _common import public_contacts as pc

    nums = pc.default_public_numbers()
    assert "110" in nums and "12301" in nums
    assert pc.normalize_number("0836-6966022") == "08366966022"


def test_goldenset_calibration():
    from verify.measure_gate_goldenset import evaluate_goldenset

    report = evaluate_goldenset()
    assert report["confusion"]["FP"] == 0, report["perItem"]
    assert report["confusion"]["FN"] == 0, report["perItem"]
    assert report["interceptRate"] >= 0.95
    assert report["falsePositiveRate"] <= 0.05


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"quality_gates tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

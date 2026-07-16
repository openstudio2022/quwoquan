"""单一门库 quality_gates contract tests。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_quality_gates__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.post import content_review as cr  # noqa: E402
from core import quality_gates as qg  # noqa: E402


def test_writing_intent_contract():
    # 底稿中心 1:1：writingIntent 是底稿派生的可选标签——合法值与"缺失"都不报错，仅非法取值报错。
    assert qg.writing_intent_issues("planning_consultation") == []
    assert qg.writing_intent_issues("") == []
    assert qg.writing_intent_issues(None) == []
    assert qg.writing_intent_issues("foo") and "invalid" in qg.writing_intent_issues("foo")[0]


def test_derive_writing_intent_from_text():
    # 底稿正文派生 writingIntent：命中结构桶最多者；任何输入都返回合法顶层标签且不抛错。
    valid = {"planning_consultation", "decision_experience", "post_trip_journal"}
    assert qg.derive_writing_intent("", default="post_trip_journal") == "post_trip_journal"
    assert qg.derive_writing_intent("九寨沟交通怎么去 门票预约 行前安排攻略") in valid
    assert qg.derive_writing_intent("随便一段没有明显信号的文字") in valid


def test_image_reference_closure_blocks_cover_only():
    assets = [{"assetId": "a1"}, {"assetId": "a2"}]
    body_no_img = "# 标题\n\n正文里没有任何图片引用。"
    issues = qg.image_reference_closure_issues(body_no_img, assets)
    assert issues and "references none" in issues[0]
    body_with_img = "# 标题\n\n看这里 asset://a1 \n\n再看 asset://a2"
    assert qg.image_reference_closure_issues(body_with_img, assets) == []
    # gallery 载体不由本门管控
    assert qg.image_reference_closure_issues(body_no_img, assets, carrier="image") == []


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
    gd = DATA_ROOT / "tests" / "support" / "fixtures" / "golden_set"
    a = (gd / "bad_template_a.md").read_text(encoding="utf-8")
    b = (gd / "bad_template_b.md").read_text(encoding="utf-8")
    c = (gd / "good_guide.md").read_text(encoding="utf-8")
    assert qg.semantic_duplicate_issues(a, [b]), "换实体名同骨架应被 simhash 拦截"
    assert qg.semantic_duplicate_issues(a, [c]) == [], "不同内容不应误判语义重复"


def test_intra_doc_repetition_blocks_padding_loops():
    repeated_para = "另外，碧峰峡在碧峰峡_a2这篇里强调慢看与错峰，别用赶场心态压缩体验。"
    article = (
        "# 碧峰峡慢游一日体验\n\n"
        "先写一段正常引入。\n\n"
        "再写一段正常判断。\n\n"
        f"{repeated_para}\n\n"
        f"{repeated_para}\n\n"
        f"{repeated_para}\n\n"
        f"{repeated_para}\n"
    )
    issues = qg.intra_doc_repetition_issues(article)
    assert issues, "复读 padding 应被拦截"
    assert any("repeated paragraph" in issue or "duplicated paragraphs occupy" in issue for issue in issues), issues


def test_intra_doc_repetition_allows_normal_reuse():
    article = (
        "# 青城山\n\n"
        "清晨上山时路边潮气很重，但风一吹就觉得值回票价。\n\n"
        "午后人流明显增多，我更建议把主景线放在前半程。\n\n"
        "如果你带老人同行，摆渡和步道的取舍要先想好。\n\n"
        "回头看这趟行程，最值得复盘的是节奏，而不是打卡数量。"
    )
    assert qg.intra_doc_repetition_issues(article) == []


def test_rubric_consistency():
    assert qg.rubric_consistency_issues([8.0, 8.0, 8.0]) == []
    assert qg.rubric_consistency_issues([2.0, 9.0, 5.0])  # 方差过大判官不可信
    assert qg.rubric_consistency_issues([8.0]) == []  # 单次不评判稳定性


def test_contact_info_blocks_private_phone_and_im():
    from core import public_contacts as pc

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
    from core import public_contacts as pc

    nums = pc.default_public_numbers()
    assert "110" in nums and "12301" in nums
    assert pc.normalize_number("0836-6966022") == "08366966022"


def test_numeric_traceability_normalizes_thousand_separators():
    issues = cr.numeric_traceability_issues(
        "峨眉山最高峰万佛顶海拔3099米，金顶海拔3077米。",
        ["最高峰万佛顶海拔3,099米，金顶（3,077米）是旅游高点。"],
    )
    assert issues == []


def test_goldenset_calibration():
    from verify.measure_gate_goldenset import evaluate_goldenset

    report = evaluate_goldenset()
    assert report["confusion"]["FP"] == 0, report["perItem"]
    assert report["confusion"]["FN"] == 0, report["perItem"]
    assert report["interceptRate"] >= 0.95
    assert report["falsePositiveRate"] <= 0.05


def test_section_balance_blocks_dominant_section():
    filler = "这是真实可信的描述性正文段落，用于撑起章节篇幅且不重复。" * 6
    short = "这是一段简短的章节正文。"
    balanced = (
        f"# 某地\n\n## 概况\n\n{filler}\n\n## 地理\n\n{filler}\n\n## 看点\n\n{filler}\n"
    )
    assert qg.section_balance_issues(balanced, max_ratio=qg.SECTION_BALANCE_MAX_RATIO_HOMEPAGE) == []
    dominant = (
        f"# 某地\n\n## 概况\n\n{short}\n\n## 地理\n\n{short}\n\n## 历史沿革\n\n{filler * 4}\n"
    )
    issues = qg.section_balance_issues(dominant, max_ratio=qg.SECTION_BALANCE_MAX_RATIO_HOMEPAGE)
    assert issues and "历史沿革" in issues[0] and "sectionBalance" in issues[0]


def test_timeline_monotonicity_blocks_backward_jump():
    spliced = (
        "# 某地\n\n## 历史沿革\n\n"
        "1956年开始勘查，1966年建场，1978年停伐，1992年列入世界遗产，2007年评为5A。"
        "1979年迁出林场，1983年视察，1984年开放，1989年设镇，1998年更名。\n"
    )
    issues = qg.timeline_monotonicity_issues(spliced)
    assert issues and "timelineOrder" in issues[0]
    chronological = (
        "# 某地\n\n## 历史沿革\n\n"
        "1956年勘查，1966年建场，1978年停伐，1984年开放，1989年设镇，1992年列入遗产，2007年评5A。\n"
    )
    assert qg.timeline_monotonicity_issues(chronological) == []


def test_out_of_draft_and_cross_source_overlap():
    from content.post import fidelity

    base = (
        "毕棚沟位于四川省阿坝州理县，是国家级风景名胜区，"
        "以高山彩林、红叶和雪山瀑布闻名，秋季景色最为壮丽。"
    )
    light = (
        "# 毕棚沟\n\n## 概况\n\n毕棚沟位于四川省阿坝州理县，是国家级风景名胜区，"
        "以高山彩林、红叶和雪山瀑布闻名，秋季的景色最为壮丽迷人。"
    )
    assert fidelity.out_of_draft_issues(light, base, source_use_mode="factual_reference_only") == []
    block = (
        "从成都出发自驾约四小时即可抵达毕棚沟景区门口沿途经过都江堰和卧龙自然保护区建议清晨出发避开堵车"
        "景区内有观光车直达上海子和磐羊湖等核心景点票价另算游客中心提供讲解服务旺季排队较久请预留时间"
    )
    other = {"entities/x/sources/09.article_qunar_base_6/source.md": block}
    spliced = light + "\n\n## 交通\n\n" + block
    assert fidelity.cross_source_overlap_issues(spliced, base, other), "拼接非底稿长串应被拦"
    assert fidelity.cross_source_overlap_issues(light, base, other) == [], "纯轻改不应误判拼接"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"quality_gates tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()

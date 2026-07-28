"""主页商用质量硬门合同（P2 重建 + SCALE 污染样本回归夹具）。

夹具取自 SCALE 实测 P0 逃逸样本的特征片段：
- 罗泉古镇：360 百科编辑壳「折叠编辑本段」+ infobox 键值堆穿透 approved；
- 隆昌石牌坊/泸沽湖：`[[IMG:fig_NN]]` 行尾追加图注违反独占行协议；
- 浙江多成品缺 H1；
- factual_reference_only 近逐字复用（旧 99.5% fidelity 上限形同虚设）。
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

import json
import inspect

from content.homepage import homepage_release, homepage_release_validation
from content.homepage.commercial_gate import (
    FACTUAL_REFERENCE_MAX_FIDELITY,
    copyright_mode_issues,
    draft_placeholder_issues,
    evaluate_commercial_page,
    final_page_hard_issues,
    independent_review_issues,
    map_like_asset_issues,
    source_fidelity,
)
from content.homepage.quality_policy import (
    homepage_body_char_minimum,
    homepage_section_char_minimum,
)

# 字数口径由 vertical content supply policy 唯一持有；测试与生产读同一真相源。
_POLICY_EXECUTION_ID = (
    "20260727--travel-homepage-commercial-gate--test-region-a--pilot-001"
)
_MIN_BODY_CHARS = homepage_body_char_minimum(_POLICY_EXECUTION_ID)
_MIN_SECTION_CHARS = homepage_section_char_minimum(_POLICY_EXECUTION_ID)
_CHAR_LIMITS = {
    "minimum_body_chars": _MIN_BODY_CHARS,
    "minimum_section_chars": _MIN_SECTION_CHARS,
}

# ---------------------------------------------------------------------------
# 夹具：SCALE 污染样本特征片段（罗泉古镇 360 百科壳 + infobox 键值堆）
# ---------------------------------------------------------------------------
_LUOQUAN_POLLUTED = """---
coverImage: asset://罗泉古镇_cover_x
---

# 罗泉古镇

罗泉镇，位于资中城北约50公里，地处资中、仁寿、威远三县交界地区，1992年已被批准为test-region-b首批历史文化名镇。

## 基本信息
中文名
罗泉古镇
外文名
Luoquan
电话区号
0832
车牌代码
川k
邮政编码
641212

## 折叠编辑本段简介
位于资中县西部，该镇以古建筑的集中分布为特色，古镇的建筑大部分是明朝末年清代和民国年间的建筑，珠溪河水质良好流向球溪河。

## 折叠编辑本段名称由来
三国时蜀丞相孔明兴师南征曾扎营罗泉镇营盘山，因连续干旱无雨派兵在珠溪河畔挖井取水，井中泉水清澈鲜美透明，即命名此井为箩泉井。
"""

_GOOD_PAGE = """---
coverImage: asset://示例景区_cover_main
---

# 示例景区

示例景区位于test-region-a杭州市西湖区，是集山水风光与人文历史于一体的国家级风景名胜区，全年适宜游览，尤以春秋两季景色最佳，是杭州周边周末出行的热门选择。

## 景观特色
景区以奇峰、幽谷、飞瀑三绝著称，主峰海拔约九百米，山间步道贯穿多处观景平台，晴日可远眺钱塘江；谷内溪流常年不断，夏季平均气温比市区低五度左右，是避暑纳凉的好去处。

## 游览建议
建议清晨从东门入园，沿主步道上行约两小时抵达山顶，午后经西侧索道下山；带儿童的家庭可选择环湖木栈道，全程平缓无台阶，约一小时可走完，沿途设有休息亭与补给点。

## 交通与门票
市区乘坐地铁三号线至终点站后换乘景区接驳车约二十分钟直达东门；旺季门票八十元、淡季六十元，索道单程四十元，官方小程序提前一天购票可享九折优惠。自驾可走绕城高速西线，东门与南门各设停车场，节假日建议九点前抵达。
"""


def test_luoquan_polluted_sample_is_rejected():
    """罗泉古镇态回归：百科编辑壳 + infobox 键值堆必须 BLOCK（历史逃逸态）。"""
    issues = final_page_hard_issues(_LUOQUAN_POLLUTED, entity_name="罗泉古镇", label="罗泉古镇", **_CHAR_LIMITS)
    text = "\n".join(issues)
    assert "折叠编辑本段" in text, "百科编辑壳必须命中"
    assert "infobox 键值堆" in text, "infobox 键值堆必须命中"


def test_missing_h1_and_shell_pages_are_rejected():
    """浙江缺 H1 态 + 导航/登录残留态回归。"""
    no_h1 = "---\ncoverImage: asset://x\n---\n\n## 概况\n" + "内容充足" * 60
    issues = final_page_hard_issues(no_h1, label="缺H1样本", **_CHAR_LIMITS)
    assert any("H1 必须恰好一个" in i for i in issues)

    shell = _GOOD_PAGE + "\n有用+1\n登录后查看更多\n"
    issues2 = final_page_hard_issues(shell, entity_name="示例景区", **_CHAR_LIMITS)
    assert any("有用+1" in i for i in issues2)


def test_commercial_gate_is_bound_to_materialization_and_validation() -> None:
    materialize_source = inspect.getsource(homepage_release.materialize_entity_page)
    validation_source = inspect.getsource(homepage_release_validation.validate_entity_page)

    assert "evaluate_commercial_page" in materialize_source
    assert "issues=commercial_issues" in materialize_source
    assert "final_page_hard_issues" in validation_source


def test_html_entity_footnote_and_mojibake_rejected():
    page = _GOOD_PAGE.replace(
        "## 交通与门票",
        "## 交通与门票\n古镇&nbsp;历史[1]悠久[2]，字符\ufffd异常。\n",
    )
    issues = final_page_hard_issues(page, entity_name="示例景区", **_CHAR_LIMITS)
    text = "\n".join(issues)
    assert "HTML 实体" in text
    assert "脚注标记" in text
    assert "乱码字符" in text


def test_empty_reference_section_and_thin_section_rejected():
    page = _GOOD_PAGE + "\n## 参考资料\n\n## 短章节\n略。\n"
    issues = final_page_hard_issues(page, entity_name="示例景区", **_CHAR_LIMITS)
    text = "\n".join(issues)
    assert "空壳章节" in text
    assert "信息量不足" in text


def test_good_page_passes_final_hard_gate():
    assert final_page_hard_issues(_GOOD_PAGE, entity_name="示例景区", **_CHAR_LIMITS) == []


# ---------------------------------------------------------------------------
# 占位符协议硬门（隆昌石牌坊/泸沽湖态）
# ---------------------------------------------------------------------------

def test_placeholder_trailing_caption_rejected():
    """占位符行尾追加图注 = 违反独占行协议（隆昌石牌坊/泸沽湖历史违规态）。"""
    draft = "# 隆昌石牌坊\n\n正文段落。\n\n[[IMG:fig_01]] 隆昌石牌坊全景图\n\n更多正文。\n[[IMG:fig_02]]\n"
    issues = draft_placeholder_issues(draft, ["fig_01", "fig_02"], label="隆昌石牌坊")
    assert any("未独占一行" in i for i in issues)


def test_placeholder_id_set_and_order_frozen():
    draft_reordered = "# 页\n\n[[IMG:fig_02]]\n\n[[IMG:fig_01]]\n"
    issues = draft_placeholder_issues(draft_reordered, ["fig_01", "fig_02"])
    assert any("ID 序列漂移" in i for i in issues)

    draft_dropped = "# 页\n\n[[IMG:fig_01]]\n"
    issues2 = draft_placeholder_issues(draft_dropped, ["fig_01", "fig_02"])
    assert any("ID 序列漂移" in i for i in issues2)

    draft_ok = "# 页\n\n[[IMG:fig_01]]\n\n正文。\n\n[[IMG:fig_02]]\n"
    assert draft_placeholder_issues(draft_ok, ["fig_01", "fig_02"]) == []


# ---------------------------------------------------------------------------
# 版权模式分离硬门
# ---------------------------------------------------------------------------

def test_factual_reference_only_near_verbatim_rejected():
    """factual_reference_only 近逐字复用必须 BLOCK（旧 99.5% 上限废止）。"""
    source = "罗泉古镇历史悠久，" + "盐业开发始于秦代，清光绪年间有盐井五百余眼，所产井盐获巴黎世界博览会金奖。" * 30
    page = "---\ncoverImage: asset://x\n---\n\n# 罗泉古镇\n\n" + source
    fidelity = source_fidelity(page, source)
    assert fidelity > FACTUAL_REFERENCE_MAX_FIDELITY
    issues = copyright_mode_issues(page, source, "factual_reference_only", label="罗泉古镇")
    assert any("抄写超限" in i for i in issues)


def test_factual_reference_only_compression_tiers():
    """>2000 字来源必须压缩约 50%（ratio ≤0.65）。"""
    source = "这是一段关于古镇独特历史沿革与盐业文明发展的详细叙述材料。" * 90  # 2520 字 >2000
    rewritten = "古镇以盐业闻名，历史可以追溯到秦代时期。" * 90  # 1800 字，ratio≈0.71 > 0.65
    page = "---\ncoverImage: asset://x\n---\n\n# 古镇\n\n" + rewritten
    issues = copyright_mode_issues(page, source, "factual_reference_only")
    assert any("压缩不足" in i for i in issues)

    compact_page = "---\ncoverImage: asset://x\n---\n\n# 古镇\n\n" + "古镇以盐业闻名于世。" * 30
    assert copyright_mode_issues(compact_page, source, "factual_reference_only") == []


def test_licensed_adaptation_allows_light_polish_and_unknown_mode_fail_closed():
    source = "允许署名转载的官方介绍正文。" * 50
    page = "---\ncoverImage: asset://x\n---\n\n# 景区\n\n" + source
    assert copyright_mode_issues(page, source, "licensed_adaptation") == []
    issues = copyright_mode_issues(page, source, "marketing_copy")
    assert any("未知 sourceUseMode" in i for i in issues)


# ---------------------------------------------------------------------------
# isMapLike 兜底 + 独立 review
# ---------------------------------------------------------------------------

def test_map_like_asset_final_backstop():
    manifest = {
        "assets": [
            {"assetId": "a1", "role": "cover", "isMapLike": True},
            {"assetId": "a2", "role": "inline", "originalCaption": "景区导览图"},
            {"assetId": "a3", "role": "related", "originalCaption": "盐神庙立面"},
        ]
    }
    issues = map_like_asset_issues(manifest, label="样本")
    text = "\n".join(issues)
    assert "a1" in text and "isMapLike" in text
    assert "a2" in text and "疑似地图态" in text
    assert "a3" not in text


def test_independent_review_hard_gate():
    """review 必须独立 run + 异模型族 + 自带 findings（禁同源 issues 自证）。"""
    author = {"runId": "run_author_1", "modelFamily": "composer"}
    same_run = {"runId": "run_author_1", "modelFamily": "gpt", "findings": []}
    issues = independent_review_issues(same_run, author)
    assert any("非独立 run" in i for i in issues)

    same_family = {"runId": "run_rev_2", "modelFamily": "composer", "findings": []}
    issues2 = independent_review_issues(same_family, author)
    assert any("异模型族" in i for i in issues2)

    bool_only = {"runId": "run_rev_3", "modelFamily": "gpt"}
    issues3 = independent_review_issues(bool_only, author)
    assert any("findings" in i for i in issues3)

    ok = {"runId": "run_rev_4", "modelFamily": "gpt", "findings": [{"kind": "none"}]}
    assert independent_review_issues(ok, author) == []

    missing_author = {"modelFamily": "composer"}
    issues4 = independent_review_issues(ok, missing_author)
    assert any("author 缺独立 runId" in i for i in issues4)


# ---------------------------------------------------------------------------
# finalize checksum / provenance 漂移（隆昌石牌坊/泸沽湖态）
# ---------------------------------------------------------------------------

def test_provenance_checksum_drift_rejected():
    from core.article_package import compute_document_sha256
    from content.homepage.commercial_gate import provenance_checksum_issues

    page = _GOOD_PAGE
    good_prov = {"final": {"articleDigest": compute_document_sha256(page)}}
    assert provenance_checksum_issues(page, good_prov) == []

    drifted_prov = {"final": {"articleDigest": "0" * 64}}
    issues = provenance_checksum_issues(page, drifted_prov, label="隆昌石牌坊")
    assert any("digest 与 provenance 漂移" in i for i in issues)

    assert any("缺 provenance" in i for i in provenance_checksum_issues(page, None))
    assert any(
        "缺 final.articleDigest" in i for i in provenance_checksum_issues(page, {"final": {}})
    )


# ---------------------------------------------------------------------------
# 综合入口（entity_dir 级）
# ---------------------------------------------------------------------------

def test_evaluate_commercial_page_end_to_end(tmp_path):
    entity = tmp_path / "示例景区"
    assets = entity / "assets"
    assets.mkdir(parents=True)
    page = _GOOD_PAGE.replace("asset://示例景区_cover_main", "asset://cover_main")
    (entity / "page.md").write_text(page, encoding="utf-8")
    (assets / "cover_main.jpg").write_bytes(b"\xff\xd8fake")
    manifest = {
        "assets": [
            {
                "assetId": "cover_main",
                "fileName": "cover_main.jpg",
                "role": "cover",
                "sourceRef": "sources/u1/source.md",
                "sourceAssetRef": "sources/u1/assets/orig.jpg",
                "authorizationProof": "CC BY-SA 4.0",
            }
        ],
        "textSourceRefs": ["sources/u1"],
        "imageSourceRefs": ["sources/u1"],
    }
    (entity / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    verdict = evaluate_commercial_page(entity,
        entity_name="示例景区",
        source_text="示例景区官方资料原文。" * 100,
        source_use_mode="factual_reference_only", **_CHAR_LIMITS)
    assert verdict["passed"], verdict["issues"]

    # 同一入口对污染页必须 BLOCK。
    bad_entity = tmp_path / "罗泉古镇"
    bad_entity.mkdir()
    (bad_entity / "page.md").write_text(_LUOQUAN_POLLUTED, encoding="utf-8")
    bad = evaluate_commercial_page(bad_entity, entity_name="罗泉古镇", **_CHAR_LIMITS)
    assert not bad["passed"]
    assert any("折叠编辑本段" in i for i in bad["issues"])

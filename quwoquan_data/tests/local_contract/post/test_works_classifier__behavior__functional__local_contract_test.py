"""WorksClassifier 红绿契约 + 行为测试（作品 vs 随记判定）。

T1 契约：verdict 结构/枚举/thresholdsVersion 与 schema 对齐。
T2 行为：专业长文→work/article、社交碎片→moment、探针/推广→abandoned、
        图片集合→work/image、图不足→abandoned、权利受阻→abandoned。
"""
from __future__ import annotations

from content.post.image.works_classifier import classify_works, load_works_classification_config

_AUTHORITATIVE = """# 九寨沟旅游全攻略

九寨沟位于test-region-b阿坝州，是著名的自然风景区。最佳游览时间为秋季十月。

## 交通与门票
门票旺季169元，观光车90元。从成都出发约8小时车程。

## 核心景点
五花海、诺日朗瀑布、长海等海子色彩斑斓，值得细细游览。海拔约2000米，注意高反。
"""
_CASUAL = "今天天气真好，随手拍了张照片，开心！这家店还不错下次再来。"
_PROMO = "http://x.com 来源平台：小红书 @user 转载推广 加微信领券"
_QUNAR_LONGFORM = (
    "北京寒假带娃16天半月游攻略 前言 说说这次旅行 "
    "我是提前1个月开始购买机票、订酒店、规划行程，不断完善行程。"
    "事实证明，酒店绝对是要提前1个月预订的，不然现场订酒店很贵。"
    "各类博物馆需要提前7天准时抢票，没有预约进不了馆。"
    "第1天 飞机转地铁到酒店。第2天 天安门广场、故宫博物院、景山公园。"
    "交通 从北京大兴国际机场进城，地铁换乘约1小时。住宿 推荐住二环内或地铁站附近。"
    "门票 故宫、国家博物馆、天坛公园都要提前预约，长城周一人多，建议错峰。"
)
_QUNAR_SHORT_MOMENT = (
    "1日游 前言 第1天 北京胡同随便逛逛，天气不错，拍拍照，吃点小吃。"
    "现在对文字要求越来越低，不想长篇大论，也没啥好说的。"
)

_VALID_DECISIONS = {"work", "moment", "abandoned"}
_VALID_TIERS = {
    "tier1_authoritative", "tier2_professional", "tier3_quality_ugc", "tier4_casual", "tier5_reject",
}


def test_professional_longform_is_work_article():
    v = classify_works(
        "art_pro", source_class="vertical_professional", source_text=_AUTHORITATIVE,
        entity_name="九寨沟", narrative_volume=4, image_count=2,
    )
    assert v["decision"] == "work"
    assert v["carrier"] == "article"
    assert v["abandonReason"] is None


def test_unknown_source_longform_self_proves_work():
    """来源元数据缺失(source_class 空)的高质量长文应内容自证为 work，不被低来源先验误杀。"""
    v = classify_works(
        "unknown_long", source_class="", source_text=_AUTHORITATIVE,
        entity_name="九寨沟", narrative_volume=3, image_count=2,
    )
    assert v["decision"] == "work"
    assert v["carrier"] == "article"


def test_ugc_plaintext_travel_guide_self_proves_work():
    v = classify_works(
        "qunar_longform",
        source_class="ugc_longform",
        source_text=_QUNAR_LONGFORM,
        entity_name="北京",
        declared_carrier="article",
    )
    assert v["decision"] == "work"
    assert v["carrier"] == "article"
    assert v["signals"]["sectionCount"] >= 1
    assert v["abandonReason"] is None


def test_ugc_short_plaintext_stays_out_of_production():
    v = classify_works(
        "qunar_short",
        source_class="ugc_longform",
        source_text=_QUNAR_SHORT_MOMENT,
        entity_name="北京",
        declared_carrier="article",
    )
    assert v["decision"] == "abandoned"
    assert v["carrier"] is None
    assert v["abandonReason"] == "insufficient_evidence"


def test_social_casual_is_moment_not_produced():
    v = classify_works(
        "moment_social", source_class="social_feed", source_text=_CASUAL,
        narrative_volume=0, image_count=1,
    )
    assert v["decision"] == "moment"
    assert v["carrier"] is None
    assert v["abandonReason"] == "casual_moment"


def test_promo_probe_is_abandoned():
    v = classify_works(
        "promo", source_class="media_article", source_text=_PROMO,
        narrative_volume=0, image_count=0,
    )
    assert v["decision"] == "abandoned"
    assert v["abandonReason"] == "insufficient_evidence"


def test_image_collection_is_work_image():
    v = classify_works(
        "img_work", source_class="photography_community", source_text="黄山日出",
        entity_name="黄山", narrative_volume=0, image_count=6, declared_carrier="image",
    )
    assert v["decision"] == "work"
    assert v["carrier"] == "image"


def test_explicit_single_image_carrier_is_work():
    v = classify_works(
        "img_few", source_class="photography_community", source_text="黄山",
        narrative_volume=0, image_count=1, declared_carrier="image",
    )
    assert v["decision"] == "work"
    assert v["carrier"] == "image"


def test_explicit_image_carrier_with_zero_images_is_abandoned():
    v = classify_works(
        "img_zero", source_class="photography_community", source_text="黄山",
        narrative_volume=0, image_count=0, declared_carrier="image",
    )
    assert v["decision"] == "abandoned"
    assert v["abandonReason"] == "insufficient_evidence"


def test_rights_blocked_is_abandoned():
    v = classify_works(
        "rights", source_class="vertical_professional", source_text=_AUTHORITATIVE,
        entity_name="九寨沟", narrative_volume=4, image_count=6, rights_blocked=True,
    )
    assert v["decision"] == "abandoned"
    assert v["abandonReason"] == "rights_blocked"


def test_verdict_conforms_contract():
    cfg = load_works_classification_config()
    v = classify_works(
        "art_pro", source_class="vertical_professional", source_text=_AUTHORITATIVE,
        entity_name="九寨沟", narrative_volume=4, image_count=2,
    )
    assert v["schema"] == "quwoquan_data.works_classification"
    assert v["decision"] in _VALID_DECISIONS
    assert v["sourceTier"] in _VALID_TIERS
    assert v["thresholdsVersion"] == int(cfg["version"])
    assert isinstance(v["reasons"], list) and v["reasons"]
    sig = v["signals"]
    for key in ("sourceClass", "sourceQualityTier", "sourceQualityScore", "worksAffinity"):
        assert key in sig
    assert v["decidedAt"]

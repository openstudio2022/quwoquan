"""底稿 writingIntent 主线对齐 contract test（R-CS01）。

`intent_aligned_base_text` 是 prompt 侧 baseDraftText 与 review 门 baseDraftFidelity
分母的唯一真相源：聚焦文章不应因整篇多主题游记作分母而被误杀，同时收窄结果不得
跌破发布门 600 有效字下限。

可直接运行：python3 quwoquan_data/tests/common/test_base_draft_intent_align.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.base_draft import (  # noqa: E402
    base_draft_fidelity_issues,
    base_draft_similarity,
    extract_base_draft_body,
    intent_aligned_base_text,
)


def _compact(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


# 多主题游记底稿：本实体 planning 段（足够长以触发收窄）+ 大量无关主题段（他城历史/茶文化/广告/餐饮）。
# 无关段刻意避开 planning 桶词（先/再/然后/交通/门票/预约/建议/注意/排队…）与实体名"峨眉山"。
_PLANNING_PARAS = [
    "从成都市区出发自驾前往峨眉山大约一个半小时车程，建议早上七点前出发进山，这样能避开旅游大巴扎堆的排队高峰；"
    "若赶高铁可以先到峨眉山站再换乘景区班车，整体衔接顺一些，不至于把宝贵时间都浪费在停车和等待大巴上；"
    "私家车不能开进核心景区，建议停在报国寺游客中心，再统一换乘景区观光车上山，停车和接驳都更省心。",
    "峨眉山门票旺季160元、淡季110元，金顶往返索道约120元，景区开放时间是早上六点到下午六点；"
    "强烈建议提前一天在官方公众号预约购票，旺季现场排队动辄一个多小时，提前预约能省下大量等待时间；"
    "学生和老人凭有效证件可享半价优惠，购票时记得勾选对应人群，入园直接刷身份证就能核验通行。",
    "进山后先到报国寺片区，再坐观光车一路上到雷洞坪，然后步行接金顶索道，第二天清晨在金顶看日出云海；"
    "这样的动线比较顺，不用走回头路，行程安排上也更从容，带着老人和孩子跟着走也不会太累；"
    "全程大致需要两天一夜，第一天主攻中山区的清音阁和一线天，第二天再专心冲金顶，节奏松弛不赶时间。",
    "如果你带着老人和小孩，建议直接放弃徒步全程登顶的念头，宁可多花一点索道钱也别赶夜路下山；"
    "注意峨眉山金顶气温常年偏低，务必提前备好厚外套，天气不好时能见度很差，要做好看不到日出的心理准备；"
    "雨季石阶湿滑一定要穿防滑鞋，山间猴群偶尔会抢食，背包拉链记得拉好，零食也别拿在手上更稳妥。",
    "想看金顶日出最好避开雨季的七八月，秋天十月前后能见度更高、彩林也好看；旺季节假日人多，淡季工作日清净，"
    "景区开放时间会随季节微调，出发前务必再核对一次官方公告别白跑一趟，提前查好班车末班时刻也很关键。",
]
_OFFTOPIC_PARAS = [
    "乐山大佛开凿于唐代开元年间，前后历经约九十年才最终完工，是世界上最高的一尊石刻弥勒坐像，"
    "依凌云山栖霞峰临江峭壁凿成，佛像与山体浑然一体，历经千年风雨依旧庄严肃穆，令无数游人叹为观止。",
    "成都的盖碗茶文化由来已久，老茶客们偏爱在竹椅上消磨整个午后，配上掏耳朵和摆龙门阵，"
    "慢悠悠地体味巴蜀特有的闲适生活节奏，茶馆里人声鼎沸却又自成一种松弛恬淡的市井意趣。",
    "本平台正在为新注册用户发放专属礼包，下载客户端完成实名即可领取多张满减券与会员体验权益，"
    "名额有限请尽快参与，更多细则可到个人中心的活动专区查看，分享给好友还能额外解锁惊喜奖励。",
    "宽窄巷子一带的串串香和钵钵鸡是本地夜宵的热门之选，人均消费大概六十元上下，周末晚上常常要等位；"
    "喜欢热闹烟火气的年轻人尤其偏爱这种边吃边聊的氛围，巷子深处还藏着不少颇有格调的小酒馆。",
    "青羊宫一带的老成都民俗市集很有烟火气，糖油果子和三大炮是孩子们的最爱，逛累了还能在街边听一段清音，"
    "市集里手艺人现做现卖，老茶客捧着盖碗坐成一排，把巴蜀慢生活的松弛劲儿展现得淋漓尽致。",
]


def _multi_topic_base() -> str:
    rows: list[str] = []
    for plan, off in zip(_PLANNING_PARAS, _OFFTOPIC_PARAS):
        rows.append(plan)
        rows.append(off)
    return "\n\n".join(rows)


def test_planning_intent_drops_offtopic_and_keeps_mainline() -> None:
    base = _multi_topic_base()
    aligned = intent_aligned_base_text(base, writing_intent="planning_consultation", entity_name="峨眉山")
    # 主线 planning 段保留。
    assert "金顶往返索道" in aligned and "提前一天在官方公众号预约" in aligned
    assert "观光车一路上到雷洞坪" in aligned
    # 无关他城/茶文化/广告/餐饮段被剔除。
    assert "乐山大佛开凿" not in aligned
    assert "盖碗茶文化" not in aligned
    assert "专属礼包" not in aligned
    assert "串串香和钵钵鸡" not in aligned
    # 对齐底稿确实做了收窄（短于整篇正文）。
    assert _compact(aligned) < _compact(extract_base_draft_body(base))
    print("[ok] planning intent keeps mainline, drops off-topic")


def test_focused_article_passes_gate_against_aligned_base() -> None:
    base = _multi_topic_base()
    aligned = intent_aligned_base_text(base, writing_intent="planning_consultation", entity_name="峨眉山")
    # 聚焦 planning 文章：以对齐底稿为骨架轻改 —— 保留主体句群，仅删掉每段最后一个分句
    # （模拟去平台痕迹/精简），不碰无关主题。贴合度应落在 55%~99.5% 安全区
    # （既非从零另写，也非逐字照搬）。
    light_edited = [para.rsplit("；", 1)[0] + "。" for para in _PLANNING_PARAS]
    article = "# 峨眉山行前安排\n\n" + "\n\n".join(light_edited)
    sim_align = base_draft_similarity(article, aligned)
    assert 0.55 <= sim_align <= 0.995, f"simAlign={sim_align*100:.1f}% 应在 55%~99.5% 安全区"
    assert not base_draft_fidelity_issues(article, aligned, source_use_mode="licensed_adaptation")
    print(f"[ok] focused article passes gate against aligned base: simAlign={sim_align*100:.1f}%")


def test_unknown_intent_returns_full_body_unchanged() -> None:
    base = _multi_topic_base()
    body = extract_base_draft_body(base)
    assert intent_aligned_base_text(base, writing_intent=None) == body[:4000]
    assert intent_aligned_base_text(base, writing_intent="not_a_real_intent") == body[:4000]
    print("[ok] unknown/missing intent returns full body unchanged")


def test_thin_relevant_falls_back_to_full_body_no_offtopic_padding() -> None:
    # 仅 1 段强 planning（不足 640 有效字），其余为无关长段：
    # 不得用无关段补长把聚焦底稿撑过 600，而应原样回退整篇（薄源由源采集门处置）。
    strong = "峨眉山门票160元，金顶索道往返约120元，建议提前在公众号预约，先到报国寺再上金顶，注意山顶低温。"
    fillers = [
        f"这是与本篇出行主线完全无关的第{i}段地方风物背景介绍，仅用于把底稿正文撑长，验证不会被错误补入聚焦底稿。" * 2
        for i in range(8)
    ]
    base = "\n\n".join([strong, *fillers])
    body = extract_base_draft_body(base)
    aligned = intent_aligned_base_text(base, writing_intent="planning_consultation", entity_name="峨眉山")
    # 薄相关 → 回退整篇（等于完整正文），既不跌破 600，也不混入无关段做"伪聚焦"。
    assert aligned == body[:4000]
    assert _compact(aligned) >= 600
    print(f"[ok] thin-relevant falls back to full body (len={_compact(aligned)})")


def _run_all() -> None:
    test_planning_intent_drops_offtopic_and_keeps_mainline()
    test_focused_article_passes_gate_against_aligned_base()
    test_unknown_intent_returns_full_body_unchanged()
    test_thin_relevant_falls_back_to_full_body_no_offtopic_padding()
    print("\nALL PASS: test_base_draft_intent_align")


if __name__ == "__main__":
    _run_all()

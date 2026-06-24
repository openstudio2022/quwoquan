from __future__ import annotations



from support.content_plan_source_reject_fixtures import *  # noqa: F401,F403



def test_base_draft_candidates_exclude_reject_sources():
    obj = resolve_entity_object_dir(TASK, BATCH, "九寨沟", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="reject_probe",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "reject_probe", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r",
        title="探针页",
        target_ref="/entity/地点/景区/九寨沟",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="good_story",
        source_md="# 九寨沟\n\n真实正文，含开放时间与体验判断。",
        quality={"sourceId": "good_story", "quality": "A-story", "score": 8},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/g",
        title="可用正文",
        target_ref="/entity/地点/景区/九寨沟",
    )
    brief = {"entityRefs": ["地点/景区/九寨沟"]}
    candidates = base_draft_candidates(TASK, BATCH, brief)
    refs = [row["sourceRef"] for row in candidates]
    assert any("good_story" in ref for ref in refs), refs
    assert not any("reject_probe" in ref for ref in refs), refs

def test_assign_base_draft_rejects_declared_reject_source():
    obj = resolve_entity_object_dir(TASK, BATCH, "黄龙", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="reject_probe",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "reject_probe", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r2",
        title="探针页",
        target_ref="/entity/地点/景区/黄龙",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="good_story",
        source_md="# 黄龙\n\n真实正文，含体验判断与出行信息。",
        quality={"sourceId": "good_story", "quality": "A-story", "score": 9},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/g2",
        title="可用正文",
        target_ref="/entity/地点/景区/黄龙",
    )
    chosen = assign_base_draft(
        TASK,
        BATCH,
        "post://黄龙",
        {
            "entityRefs": ["地点/景区/黄龙"],
            "baseSourceRef": "entities/地点/景区/黄龙/1.download/sources/01.reject_probe/source.md",
        },
    )
    assert chosen and "good_story" in chosen, chosen

def test_assign_base_draft_reassigns_when_declared_source_taken_by_peer():
    obj = resolve_entity_object_dir(TASK, BATCH, "都江堰", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="wiki_dujiangyan",
        source_md="# 都江堰\n\n概述底稿，含基础事实。",
        quality={"sourceId": "wiki_dujiangyan", "quality": "A", "score": 9},
        platform="wikipedia",
        source_category="overview_baike",
        url="https://example.com/wiki",
        title="都江堰概述",
        target_ref="/entity/地点/景区/都江堰",
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="ctrip_dujiangyan",
        source_md="# 都江堰游记\n\n长篇游记底稿，保留现场叙事。",
        quality={"sourceId": "ctrip_dujiangyan", "quality": "A-story", "score": 8},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/ctrip",
        title="都江堰游记",
        target_ref="/entity/地点/景区/都江堰",
    )
    first = assign_base_draft(
        TASK,
        BATCH,
        "post://都江堰_画报",
        {"entityRefs": ["地点/景区/都江堰"], "baseSourceRef": "wiki_dujiangyan"},
    )
    second = assign_base_draft(
        TASK,
        BATCH,
        "post://都江堰_攻略",
        {"entityRefs": ["地点/景区/都江堰"], "baseSourceRef": "wiki_dujiangyan"},
    )
    assert first and "wiki_dujiangyan" in first, first
    assert second and "ctrip_dujiangyan" in second, second
    assert first != second

def test_load_base_draft_text_prefers_source_clean():
    obj = resolve_entity_object_dir(TASK, BATCH, "峨眉山", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=1,
        source_id="wiki_emeishan",
        source_md="raw source with frontmatter-ish noise\nmanual_source_plan_note: 不该优先命中",
        clean_md="clean source body only",
        quality={"sourceId": "wiki_emeishan", "quality": "A", "score": 9},
        platform="wikipedia",
        source_category="overview_baike",
        url="https://example.com/emeishan",
        title="峨眉山概述",
        target_ref="/entity/地点/景区/峨眉山",
    )
    text = load_base_draft_text(
        TASK,
        BATCH,
        "entities/地点/景区/峨眉山/1.download/sources/01.wiki_emeishan/source.md",
    )
    assert text == "clean source body only"

def test_load_base_draft_text_extracts_signal_body_from_noisy_clean_source():
    obj = resolve_entity_object_dir(TASK, BATCH, "都江堰", etype_hint="景区")
    write_source_unit(
        obj,
        ordinal=2,
        source_id="ctrip_noisy",
        source_md="raw fallback",
        clean_md=(
            "登录\n注册\n我的订单\n"
            "都江堰景区，位于都江堰市城西岷江干流上，由秦国蜀郡太守李冰及其子于西元前256年左右修建，是目前中国保存完整的古代水利工程。\n"
            "工程由鱼嘴分水堤、飞沙堰溢洪道、宝瓶口引水口三大主体工程和百丈堤、人字堤等附属工程构成，把岷江分隔成外江和内江。\n"
            "用户点评\n"
            "附近景点\n"
            "都江堰真的很值得一看，古人的智慧太了不起了。\n"
        ),
        quality={"sourceId": "ctrip_noisy", "quality": "B-fact", "score": 4},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/ctrip-noisy",
        title="都江堰 noisy",
        target_ref="/entity/地点/景区/都江堰",
    )
    text = load_base_draft_text(
        TASK,
        BATCH,
        "entities/地点/景区/都江堰/1.download/sources/02.ctrip_noisy/source.md",
    )
    assert "登录" not in text
    assert "附近景点" not in text
    assert "都江堰景区，位于都江堰市城西岷江干流上" in text
    assert "工程由鱼嘴分水堤、飞沙堰溢洪道、宝瓶口引水口三大主体工程" in text

def test_base_draft_fidelity_gallery_uses_leading_excerpt_window():
    tail = "\\n\\n".join(
        f"尾段延伸事实{i:03d}：这一段只用于拉长底稿窗口，不应要求画报全文覆盖。"
        for i in range(120)
    )
    base = (
        "第一段先写景区概况与主景。\\n\\n"
        "第二段继续写最核心的观看顺序与现场感。\\n\\n"
        "第三段补充一些延伸事实。\\n\\n"
        + tail
    )
    article = (
        "# 图集\\n\\n"
        "第一段先写景区概况和主要景观。\\n\\n"
        "第二段继续写最核心的游览顺序与现场感。\\n\\n"
        "第三段补充一些延伸事实。\\n"
    )
    assert base_draft_fidelity_issues(
        article, base, source_use_mode="licensed_adaptation"
    )  # 授权改编的 article 口径仍会被长尾底稿拉低
    assert base_draft_fidelity_issues(
        article,
        base,
        carrier="gallery",
        source_use_mode="licensed_adaptation",
    ) == []

def test_base_draft_extraction_drops_advertorial_insurance_noise():
    text = (
        "体验更流畅，还能赢积分换大奖\n\n"
        "如果和朋友家人来乐山旅行，时间比较长，张公桥和上中顺都值得慢慢走。\n\n"
        "购买PICC中国人民保险的优游保境内自驾游保险，还可享受在线理赔和在线客服。\n\n"
        "从成都自驾2h便可以达到乐山，第一站当然是吃，油炸串串和江边夜色都很打动人。\n"
    )

    body = extract_base_draft_body(text)

    assert "PICC" not in body
    assert "在线理赔" not in body
    assert "赢积分换大奖" not in body
    assert "张公桥和上中顺" in body
    assert "从成都自驾2h" in body

def test_factual_reference_only_enforces_base_draft_fidelity_gate():
    """产品裁定 full light-edit：factual_reference_only 同样受底稿贴合度门约束。"""
    off_base = base_draft_fidelity_issues(
        "完全独立组织的正文，只复述可核验事实。",
        "普通网页的原始叙述和作者表达。",
        source_use_mode="factual_reference_only",
    )
    assert off_base

def test_base_draft_fidelity_ignores_platform_ads_when_body_retained():
    base = """
    你选择的每条路，都有人保守护。
    体验更流畅，还能赢积分换大奖。
    如果和朋友家人来成都旅行，你的时间周期比较长那成都周边城市是值得一去的，像乐山和眉山这样。
    自驾游的安全重视一定是每个家庭需要了解的，购买PICC中国人民保险的优游保境内自驾游保险。
    从成都自驾2h便可以达到乐山，第一站当然是张公桥，这里夜幕降临下街灯亮起，热闹又浪漫。
    来乐山不吃油炸等于白来，余记油炸菜品新鲜，配上海椒面很绝。
    上中顺在乐山港旁边，也就是游船看乐山大佛的码头这里，古色古香。
    东方佛都就在乐山大佛旁，刻画和还原都比较棒，值得参观。
    第二天可以早起感受乐山早市氛围，再慢悠悠逛乐山大佛。
    门票：本地人10员；外地人80元。
    眉山三苏祠博物馆，逛完之后旁边的东坡酒楼还能来上一份东坡肘子体验。
    下载中国人保APP，优游出行每一天。
    """
    article = """
    直接说，乐山大佛值得留一晚，但不适合只为打卡匆忙往返。
    从成都自驾2h便可以达到乐山，第一站当然是张公桥；夜幕降临下街灯亮起，小吃街热闹又浪漫。
    来乐山不吃油炸等于白来，余记油炸菜品新鲜，配上海椒面很绝。
    上中顺在乐山港旁边，也就是游船看乐山大佛的码头这里，古色古香。
    东方佛都就在乐山大佛旁，刻画和还原都比较棒，值得参观。
    第二天可以早起感受乐山早市氛围，再慢悠悠逛乐山大佛。
    门票只保留外地人80元这个确定信息。
    """
    assert base_draft_fidelity_issues(article, base) == []

def test_base_draft_extraction_keeps_late_signal_lines():
    early = "\n".join(f"成都前置信号段{i}，这里有足够长的游记描述和现场判断。" for i in range(24))
    text = f"""
    {early}
    乐山大佛-虔诚的向往
    虽然乐山大佛并不在成都，但也不妨碍我要去看一看啊。依然是很早就起床，还好是自驾游，起码不用赶地铁，换乘各种车子。
    到了大佛那里，我们站在大佛脚下抬头仰望着大佛。
    """

    body = extract_base_draft_body(text)

    assert "成都前置信号段23" in body
    assert "到了大佛那里" in body

def test_base_draft_fidelity_still_blocks_keyword_only_rewrite():
    base = """
    从成都自驾2h便可以达到乐山，第一站当然是张公桥，这里夜幕降临下街灯亮起，热闹又浪漫。
    来乐山不吃油炸等于白来，余记油炸菜品新鲜，配上海椒面很绝。
    上中顺在乐山港旁边，也就是游船看乐山大佛的码头这里，古色古香。
    东方佛都就在乐山大佛旁，刻画和还原都比较棒，值得参观。
    第二天可以早起感受乐山早市氛围，再慢悠悠逛乐山大佛。
    """
    article = "乐山大佛适合旅行，张公桥、上中顺、东方佛都都可以安排，整体体验不错。"
    assert base_draft_fidelity_issues(article, base)


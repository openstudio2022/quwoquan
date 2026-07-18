"""Render immutable article writing packs into agent prompts."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from content.post.article.base_draft import base_draft_is_adaptable
from content.post.article.base_draft_analysis import FIDELITY_MAX, FIDELITY_MIN
from content.post.article.writing_pack import _asset_figure_id, primary_entity_name
from core.prompt_render import render
from core.quality_gates import WRITING_INTENTS
from core.style_catalog import opening_guidance

def _fmt_list(items: Sequence[str], bullet: str = "-") -> str:
    return "\n".join(f"{bullet} {x}" for x in items if x) or "（无）"

def _base_fidelity_range_label() -> str:
    return f"{int(FIDELITY_MIN * 100)}%~{int(FIDELITY_MAX * 100)}%"

def _source_use_mode(pack: Mapping[str, Any]) -> str:
    return str(pack.get("sourceUseMode") or "factual_reference_only").strip()

def _adapt_base_draft(pack: Mapping[str, Any]) -> bool:
    """是否以底稿为骨架轻改：licensed_adaptation 与 factual_reference_only 统一为 True。"""
    return base_draft_is_adaptable(_source_use_mode(pack))

def _persona_block(persona: Any, *, adapt_base: bool) -> str:
    """渲染「作者人设（轻量化适配）」块：把匹配到的虚拟创作者人设注入 prompt。

    适配仅作用于用词用语/语气/写作手法等表层风格，严禁为贴合人设而改事实、
    或虚构亲历/资质。adapt_base 为底稿轻改模式（licensed/factual 统一），否则为纯事实证据模式。
    返回空串表示无人设。
    """
    if not isinstance(persona, Mapping) or not persona:
        return ""
    lines: list[str] = ["### 作者人设（语气适配，不改事实）", ""]
    who = " · ".join(str(x) for x in [persona.get("displayName"), persona.get("creatorArchetype")] if x)
    if who:
        lines.append(f"- **作者**：{who}")
    if persona.get("headline"):
        lines.append(f"- **定位**：{persona.get('headline')}")
    voice = persona.get("voiceStyle") if isinstance(persona.get("voiceStyle"), Mapping) else {}
    voice_bits = " · ".join(
        str(x) for x in [voice.get("narrativePointOfView") or voice.get("pointOfView"), voice.get("tone")] if x
    )
    if voice_bits:
        lines.append(f"- **视角与语气**：{voice_bits}")
    expertise = [str(x) for x in (persona.get("expertiseClaims") or []) if x]
    if expertise:
        lines.append(f"- **擅长**：{' / '.join(expertise)}")
    if persona.get("coverageScopeLabel"):
        lines.append(f"- **题材与范围**：{persona.get('coverageScopeLabel')}")
    mustnot = [str(x) for x in (persona.get("mustNotClaim") or []) if x]
    if mustnot:
        lines.append(f"- **禁止宣称**：{' / '.join(mustnot)}")
    if adapt_base:
        lines.append(
            "- **适配方式**：在底稿基础上按该作者的视角、语气、用词用语与写作手法做表层调整；"
            "**严禁为贴合人设而改变事实、改动结构到面目全非，或虚构该作者的亲身经历、资质与商业合作**。"
        )
    else:
        lines.append(
            "- **适配方式**：先基于事实证据独立表达，再按该作者的视角、语气、用词用语做表层调整；"
            "**严禁为贴合人设而复刻来源句群、改变事实，或虚构该作者的亲身经历、资质与商业合作**。"
        )
    return "\n".join(lines)

def _creator_lock_line(pack: Mapping[str, Any]) -> str:
    if pack.get("creatorProfileId") or pack.get("authorId"):
        return (
            f"- 发布作者锁定: creatorProfileId=`{pack.get('creatorProfileId')}` ｜ "
            f"authorId=`{pack.get('authorId')}`；禁止改写、替换或把来源网页作者当作发布作者。"
        )
    return ""

def _primary_entity_contract_line(pack: Mapping[str, Any]) -> str:
    name = primary_entity_name(pack)
    if not name:
        return ""
    return f"- 主实体: **{name}**；正文必须至少自然出现一次完整名称，禁止只写泛称或只写别名。"

def _creative_brief_block(creative: Mapping[str, Any]) -> str:
    if not creative:
        return ""
    lines = ["### 创作自治边界（creativeBrief）", ""]
    lines.append(f"- **readerPromise**：{creative.get('readerPromise')}")
    lines.append(f"- **contentAngle**：{creative.get('contentAngle')}")
    lines.append(f"- **voiceStyle**：{creative.get('voiceStyle')}")
    allowed_moves = [str(x) for x in (creative.get("allowedMoves") or []) if x]
    if allowed_moves:
        lines.append(f"- **你可以自主选择的表达动作**：{(' / '.join(allowed_moves))}")
    quality_targets = [str(x) for x in (creative.get("qualityTargets") or []) if x]
    if quality_targets:
        lines.append(f"- **创作质量目标**：{(' / '.join(quality_targets))}")
    must_not_do = [str(x) for x in (creative.get("mustNotDo") or []) if x]
    if must_not_do:
        lines.append("- **不可越界**：")
        for item in must_not_do:
            lines.append(f"  - {item}")
    lines.append(
        "- 写正文前先在心里形成 2-3 个内容构思，选择最能兑现 readerPromise 的结构；"
        "正文写完后自检标题兑现、信息密度、图文节奏、证据边界与作者可信边界。"
    )
    return "\n".join(lines)

def _writing_intent_line(pack: Mapping[str, Any]) -> str:
    intent = pack.get("writingIntent")
    if intent and intent in WRITING_INTENTS:
        spec = WRITING_INTENTS[intent]
        return (
            f"- **写作主线（writingIntent=`{intent}` · {spec['label']}）**：{spec['desc']} "
            "全篇只服务这一条主线，禁止把攻略/咨询、决策体验、游后游记三类混写。"
        )
    return ""

def _preferred_opening_index(ref: str, option_count: int) -> int:
    """按 ref 确定性轮转开篇策略，避免同实体多篇独立自选后开篇/骨架趋同。"""
    if option_count <= 0:
        return 0
    import zlib

    return zlib.crc32(str(ref or "").encode("utf-8")) % option_count

def _narrative_block(pack: Mapping[str, Any]) -> str:
    """叙事载体的开篇 / 情感 / 取舍创作引导（非 gate 复述，仅创作方向）。"""
    nc = pack.get("narrativeContract") or {}
    lines: list[str] = []
    og = pack.get("openingGuidance") or opening_guidance(str(pack.get("styleFamily") or ""))
    opening_opts = og.get("openingStrategies") or []
    if opening_opts:
        preferred = opening_opts[_preferred_opening_index(str(pack.get("ref") or ""), len(opening_opts))]
        lines.append(
            f"- **开篇方式（styleFamily=`{og.get('styleFamily') or pack.get('styleFamily')}`，"
            "从下列任选一种真正落地，禁止千篇一律的套路开头）**："
        )
        for opt in opening_opts:
            mark = "（本篇优先）" if opt is preferred else ""
            lines.append(f"  - `{opt.get('id')}`{mark}（{opt.get('label')}）：{opt.get('hint')}")
        lines.append(
            f"  默认采用本篇优先策略 `{preferred.get('id')}`（仅当底稿体裁明显不适配时才改选并在 draft_meta 说明）；"
            "首段必须直接体现所选策略（结论先行 / 设问悬念 / 场景沉浸 / 对比并置），"
            "并在 draft_meta 写明最终 styleFamily 与 openingStrategy。"
        )
        lines.append(
            "- **同实体差异化**：同一实体可能有多篇文章各配不同底稿；你的开篇措辞与章节小标题"
            "必须从**本篇底稿自身的叙事**中生长出来，禁止使用「交通/住宿/门票/贴士」式通用模板骨架，"
            "禁止与其它文章共用同一套开场白或标题序列。"
        )
    elif nc.get("requireMotivation"):
        lines.append("- 开篇写出**出发动机/心情铺垫**（为什么想去、出发前的犹豫或期待），不要一上来就罗列行程。")
    if nc.get("requireLike"):
        lines.append(
            "- 正文写出**具体喜欢/打动你的点**（来自素材，有画面感），"
            "并显式出现“喜欢/打动/值得/治愈/松弛/心动”等可识别表达。"
        )
    if nc.get("requireDislike"):
        lines.append(
            "- 也要诚实写出**不足/劝退点**（来自素材），"
            "并显式出现“不足/遗憾/劝退/不建议/失望/踩雷”等可识别表达。"
        )
    lines.append(f"- 给出至少 {nc.get('minDecisionPoints', 2)} 处**取舍判断**（如「如果你…我会建议…」「宁可…也别…」）。")
    if nc.get("forbidStandaloneTips"):
        lines.append("- 注意事项**就地融入**叙述，禁止另起「实用信息/来源平台」清单块。")
    lines.append(
        "- **章节结构合同**：正文至少 3 个叙事型 `## ` 章节，每章节以成段散文为主（图/列表只作穿插）；"
        "任一章节篇幅不得超过全文 60%——底稿单日流水过长时按场景/地点拆成多章。"
        "底稿含多次出行或平行时间线时，归并为**单一时间顺序**叙事，禁止年代来回跳跃。"
    )
    return "\n".join(lines)

def _base_source_line(pack: Mapping[str, Any], *, adapt_base: bool) -> str:
    base = pack.get("baseSourceRef")
    if not base:
        return ""
    lines: list[str] = []
    if adapt_base:
        lines.append(
            f"- **底稿来源**：`{base}` 作为本篇表达骨架，在其上做**适度润色 + 人设适配**"
            "（去语病/错字、私人信息脱敏替代、按作者人设微调用词用语与写作手法），优质原文与自然段可保留；"
            "禁止脱离底稿大修/重写/编故事或改到面目全非。"
        )
    else:
        lines.append(
            f"- **事实参考来源**：`{base}` 只作为事实、路线顺序、条件和可核验数字的证据池；"
            "正文必须独立表达，禁止复用连续长句、自然段、作者表达或原文结构。"
        )
    lines.append(
        "- **禁止暴露内部标识**：底稿/来源路径仅供内部参考；"
        "禁止把底稿文件名、目录名、source 编号（如 `…_base_1`、`source.md`、`sources/…`）或任何采集来源痕迹写进正文、标题或配文。"
    )
    return "\n".join(lines)

def _banned_terms_line(pack: Mapping[str, Any]) -> str:
    banned = pack.get("bannedRegisterTerms") or []
    forb = pack.get("forbiddenPhrases") or []
    lines: list[str] = []
    if banned:
        lines.append(f"- **禁用语域**：本主体禁止出现 {', '.join(str(x) for x in banned)} 等错配语域词。")
    if forb:
        lines.append(f"- **禁用词**：{', '.join(str(x) for x in forb)}")
    return "\n".join(lines)

def _style_candidates_block(pack: Mapping[str, Any]) -> str:
    og = pack.get("openingGuidance") or opening_guidance(str(pack.get("styleFamily") or ""))
    candidates = og.get("styleFamilyCandidates") or []
    if not candidates:
        return ""
    lines = ["### 体裁候选（默认已按路由选定；仅当原文体裁明显更贴合另一种时改选，并在 draft_meta 写明）", ""]
    for c in candidates:
        mark = "（默认）" if c.get("styleFamily") == og.get("styleFamily") else ""
        lines.append(f"- `{c.get('styleFamily')}`{mark}：{c.get('writingGenre')}")
    return "\n".join(lines)

def _base_draft_block(pack: Mapping[str, Any], *, adapt_base: bool) -> str:
    """底稿 / 事实参考材料块：编辑硬合同（创作方向，不复述 gate 数值）+ 原文。"""
    base_text = str(pack.get("baseDraftText") or "")
    if not base_text:
        return (
            "## 创作素材\n\n"
            "- 无底稿，综合下方证据点独立组织内容，不要把多个来源机械拼成清单，也不要每篇都用相同章节套路。"
        )
    lines: list[str] = []
    if adapt_base:
        lines.append(f"## 底稿（以此为骨架适度润色 + 人设适配；贴合度 {_base_fidelity_range_label()}）")
        lines.append("")
        lines.append("### 底稿编辑硬合同")
        lines.append("")
        lines.append(
            "- 先把下方底稿当作初稿骨架处理：保留原叙述顺序、主要自然段与核心句群，"
            "再做去语病、去平台痕迹、私人信息脱敏、事实校正与人设适配。"
        )
        lines.append(
            "- **逐句沿用底稿原有措辞与短语**，多数句子做最小改动而非整句同义改写；"
            "与主题相关、无广告/隐私/平台痕迹的句群尽量原句保留（单底稿零参考，"
            "禁止用百科/官网/其它来源或其它文章补全、校正、拼接段落）。"
        )
        lines.append(
            "- 删除仅限广告、保险、App 下载/积分、平台活动等**非内容噪声**；底稿写到的所有目的地/行程/景点段落都是正文内容，必须整篇保留"
            "（多目的地路书照样保留全部站点），禁止以「与本篇实体无关」为由删掉其它城市/景点段落（实体只是标签，不是裁剪边界）。"
        )
        lines.append(
            "- **底稿内重复去重**：底稿中逐日重复出现的同一段落/句群（如每天复制粘贴的住宿、集合、交通模板句）"
            "只保留一次或合并改写，禁止把同一段落原样保留 2 次以上。"
        )
        lines.append(
            "- `draft_meta.selfCritique.baseDraftFidelityStrategy`：说明保留了哪些底稿段落、删除了哪些平台/广告信息。"
        )
    else:
        lines.append("## 事实参考材料（只取事实，不保留表达）")
        lines.append("")
        lines.append("### 事实引用硬合同")
        lines.append("")
        lines.append(
            "- 从下方材料提取可核验事实、路线顺序、约束条件、取舍依据与带单位数字，再用自己的句子重新组织。"
        )
        lines.append(
            "- 禁止逐段同义改写、禁止保留来源连续长句、禁止复用原小标题/原段落结构；可保留专有名词、地点名、公开数字与必要短事实短语。"
        )
        lines.append(
            "- `draft_meta.selfCritique.sourceUseModeBoundary`：说明哪些内容只取事实、哪些表达已独立改写。"
        )
    lines.append("")
    lines.append(base_text)
    return "\n".join(lines)

def _numeric_whitelist_block(pack: Mapping[str, Any]) -> str:
    base_text = str(pack.get("baseDraftText") or "")
    if not base_text:
        return ""
    from content.post.content_review import _NUMERIC_FACT_RE

    numeric_tokens = sorted({m.group(0).strip() for m in _NUMERIC_FACT_RE.finditer(base_text)})
    if not numeric_tokens:
        return ""
    return (
        "## 带单位数字白名单（正文仅允许复用底稿已出现的带单位数字）\n\n"
        + _fmt_list(numeric_tokens)
    )

def _section_intents_block(pack: Mapping[str, Any], *, adapt_base: bool) -> str:
    section_intents = [str(item) for item in (pack.get("sectionIntents") or [])]
    if adapt_base:
        head = "## 章节意图（仅参考；结构以底稿为准，可自然调整，不要照抄为标题）"
    else:
        head = "## 章节意图（仅参考；结构按 writingIntent 独立组织，不要照抄为标题）"
    base_source_ref = str(pack.get("baseSourceRef") or "").strip()
    blocks: list[str] = []
    if base_source_ref:
        blocks.append(
            "## 唯一底稿来源（全文只能来自这一份，禁止引用其它来源）\n\n" + _fmt_list([base_source_ref])
        )
    blocks.append(head + "\n\n" + _fmt_list(section_intents))
    return "\n\n".join(blocks)

def _evidence_block(pack: Mapping[str, Any]) -> str:
    points = pack.get("evidencePoints") or []
    if not points:
        return ""
    lines = ["## 证据点（逐实体，按此创作，引用其中信息）", ""]
    for p in points:
        lines.append(f"### {p.get('entityName')}")
        if p.get("topExcerpt"):
            lines.append(f"- 摘录: {p['topExcerpt']}")
        if p.get("mainline"):
            lines.append(f"- 主线: {' / '.join(p['mainline'][:4])}")
        if p.get("likes"):
            lines.append(f"- 喜欢线索: {' / '.join(p['likes'][:3])}")
        if p.get("pains"):
            lines.append(f"- 不足线索: {' / '.join(p['pains'][:3])}")
        fact_texts = [f["text"] for f in (p.get("facts") or []) if f.get("text")]
        if fact_texts:
            lines.append(f"- 事实: {' / '.join(fact_texts)}")
        lines.append("")
    return "\n".join(lines).rstrip()

def _assets_block(pack: Mapping[str, Any]) -> str:
    assets = list(pack.get("assets") or [])
    lines = [
        "> 每轮创作/修改前**重新读取本 writing_pack 的 assets**；`asset://` 只能引用下方 assetId，"
        "禁止沿用旧 assetId（recompose 后 id 可能变化，引用旧 id 会被 generatorProvenance 门拦截）。",
        "",
    ]
    if not assets:
        lines.append("（本篇无可用配图素材）")
        return "\n".join(lines)
    for index, img in enumerate(assets, start=1):
        lines.append(
            f"- figureId=`{_asset_figure_id(img, index)}` assetId=`{img.get('assetId')}` "
            f"实体={img.get('entityName')} 版面={img.get('imageLayout')} 建议说明={img.get('caption')}"
        )
    return "\n".join(lines)

def _image_assets_block(pack: Mapping[str, Any]) -> str:
    assets = [a for a in (pack.get("assets") or []) if isinstance(a, Mapping)]
    source_title = str(pack.get("title") or "").strip()
    source_caption = str(pack.get("caption") or "").strip()
    if not assets:
        rows = [
            (
                f"- 底稿标题：{source_title}（只可原样保留或轻润色）"
                if source_title
                else "- 底稿标题：无；公开标题必须留空。"
            ),
            (
                f"- 底稿配文：{source_caption}（只可原样保留或轻润色）"
                if source_caption
                else "- 底稿配文：无；公开配文必须留空。"
            ),
            "",
            "（无可用图片素材）",
        ]
        return "\n".join(rows)
    rows: list[str] = []
    rows.extend(
        [
            (
                f"- 底稿标题：{source_title}（只可原样保留或轻润色）"
                if source_title
                else "- 底稿标题：无；公开标题必须留空。"
            ),
            (
                f"- 底稿配文：{source_caption}（只可原样保留或轻润色）"
                if source_caption
                else "- 底稿配文：无；公开配文必须留空。"
            ),
            "",
        ]
    )
    for index, asset in enumerate(assets[:20], start=1):
        parts = [f"`{asset.get('assetId')}`"]
        if asset.get("role"):
            parts.append(f"role={asset.get('role')}")
        if asset.get("entityName"):
            parts.append(str(asset.get("entityName")))
        if asset.get("imageLayout"):
            parts.append(f"layout={asset.get('imageLayout')}")
        existing_caption = str(asset.get("caption") or "").strip()
        if existing_caption:
            parts.append(f"参考配文：{existing_caption[:60]}")
        rows.append(f"{index}. " + " ｜ ".join(parts))
    return "\n".join(rows)

def _render_image_task_prompt(pack: Mapping[str, Any]) -> str:
    """图片作品/画报：结构化图集 + 短配文（模板渲染，不走长文叙事与证据点）。"""
    caption = pack.get("captionPolicy") if isinstance(pack.get("captionPolicy"), Mapping) else {}
    title_max = int(caption.get("titleMaxChars") or 80)
    caption_max = int(caption.get("captionMaxChars") or 300)
    creator_lock = ""
    if pack.get("creatorProfileId") or pack.get("authorId"):
        creator_lock = (
            f"- 发布作者锁定: creatorProfileId=`{pack.get('creatorProfileId')}` ｜ "
            f"authorId=`{pack.get('authorId')}`；禁止改写或把来源网页作者当作发布作者。"
        )
    return render(
        "image_curation",
        system_vars={"title_max_chars": title_max, "caption_max_chars": caption_max},
        task_vars={
            "title": pack.get("title"),
            "ref": pack.get("ref"),
            "carrier": pack.get("carrier"),
            "source_collection": pack.get("sourceCollectionId"),
            "byline": pack.get("byline"),
            "creator_lock_line": creator_lock,
            "assets_block": _image_assets_block(pack),
        },
    )

def render_prompt_md(pack: Mapping[str, Any]) -> str:
    """渲染给创作 agent 的人类可读写作指令（指令区来自模板，本函数只构造动态数据块）。"""
    carrier = pack.get("carrier")
    if str(carrier or "").lower() == "image":
        return _render_image_task_prompt(pack)
    wc = pack.get("wordCount") or {}
    adapt_base = _adapt_base_draft(pack)
    creative = pack.get("creativeBrief") if isinstance(pack.get("creativeBrief"), Mapping) else {}
    persona_block = _persona_block(creative.get("persona"), adapt_base=adapt_base) if creative else ""
    return render(
        "article_author",
        task_vars={
            "title": pack.get("title"),
            "ref": pack.get("ref"),
            "kind": pack.get("kind"),
            "carrier": carrier,
            "template_id": pack.get("templateId"),
            "byline": pack.get("byline"),
            "word_count_min": wc.get("min", "?"),
            "word_count_max": wc.get("max", "?"),
            "creator_lock_line": _creator_lock_line(pack),
            "primary_entity_contract_line": _primary_entity_contract_line(pack),
            "creative_brief_block": _creative_brief_block(creative),
            "persona_block": persona_block,
            "writing_intent_line": _writing_intent_line(pack),
            "narrative_block": _narrative_block(pack),
            "base_source_line": _base_source_line(pack, adapt_base=adapt_base),
            "banned_terms_line": _banned_terms_line(pack),
            "opening_guidance_block": _style_candidates_block(pack),
            "base_draft_block": _base_draft_block(pack, adapt_base=adapt_base),
            "numeric_whitelist_block": _numeric_whitelist_block(pack),
            "must_include_facts_block": _fmt_list(pack.get("mustIncludeFacts") or []),
            "section_intents_block": _section_intents_block(pack, adapt_base=adapt_base),
            "evidence_block": _evidence_block(pack),
            "assets_block": _assets_block(pack),
        },
    )

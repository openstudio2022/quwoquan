"""Writing pack：CLI prepare 产出的"写作契约"，供会话模型创作正文。

writing_pack 把证据、选好的图、必须覆盖的事实、约束、章节意图等结构化下发；
prompt.md 是其人类可读版本（会话模型据此创作）。CLI 不再拼接任何正文句子。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from _common.base_draft import FIDELITY_MAX, FIDELITY_MIN, base_draft_is_adaptable
from _common.content_object import require_title_hint
from _common.creative_brief import build_creative_brief
from _common.creator_assignment import creator_from_payload
from _common.quality_gates import WRITING_INTENTS
from _common.style_catalog import opening_guidance


def primary_entity_name(obj: Mapping[str, Any]) -> str:
    """从 brief/writing_pack 提取本篇主实体名，作为底稿主线对齐的强信号。

    软信号：缺失不致命（writingIntent 桶匹配仍可独立工作）。优先级
    entityRefs 末段 -> evidencePoints[0].entityName -> title 分隔符前缀。
    route/entity 两条 article 审稿管线共用本入口，避免重复实现（R24）。
    """
    refs = obj.get("entityRefs") or []
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
        for ref in refs:
            name = str(ref or "").rstrip("/").rsplit("/", 1)[-1].strip()
            if name:
                return name
    for point in obj.get("evidencePoints") or []:
        if isinstance(point, Mapping):
            name = str(point.get("entityName") or "").strip()
            if name:
                return name
    title = str(obj.get("title") or "")
    for sep in ("·", "|", "-"):
        if sep in title:
            head = title.split(sep, 1)[0].strip()
            if head:
                return head
    return title.strip()


def _evidence_points(evidence_bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for node in evidence_bundle.get("routeNodes") or []:
        name = str(node.get("entityName") or "")
        if not name:
            continue
        emotion = node.get("emotionEvidence") or {}
        points.append(
            {
                "entityName": name,
                "sequence": node.get("sequence"),
                "topExcerpt": node.get("topExcerpt") or "",
                "mainline": [str(x) for x in (node.get("mainlineEvidence") or []) if x],
                "likes": [str(x) for x in (emotion.get("likes") or []) if x],
                "pains": [str(x) for x in (emotion.get("painPoints") or []) if x],
                "facts": [
                    {"category": str(e.get("category") or ""), "text": str(e.get("text") or e.get("sentence") or "")}
                    for e in (node.get("factEvidence") or [])
                ][:6],
            }
        )
    return points


def _compact_assets(assets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "assetId",
        "fileName",
        "caption",
        "kind",
        "role",
        "entityName",
        "sourcePath",
        "sourceRef",
        "sourceAssetRef",
        "researchLane",
        "imageLayout",
        "sourceCollectionId",
        "creator",
        "collectionPageUrl",
        "license",
        "termsUrl",
        "authorizationProof",
    )
    rows: list[dict[str, Any]] = []
    for asset in assets:
        row = {key: asset.get(key) for key in keep if asset.get(key)}
        if row.get("assetId"):
            rows.append(row)
    return rows


def _asset_figure_id(asset: Mapping[str, Any], index: int) -> str:
    role = str(asset.get("role") or "")
    if role == "cover":
        return "cover"
    if role == "closing":
        return "closing"
    return f"fig{index}"


def build_writing_pack(
    *,
    ref: str,
    kind: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
    carrier: str,
    byline: str,
    publish_layout: str,
    section_intents: Sequence[str],
    source_urls: Sequence[str],
    source_paths: Sequence[str],
) -> dict[str, Any]:
    title = require_title_hint(brief, ref=ref)
    narrative = {
        "requireMotivation": bool((brief.get("openingTension") or {}).get("required", True)),
        "requireLike": bool((brief.get("explicitFeelings") or {}).get("requireLike", True)),
        "requireDislike": bool((brief.get("explicitFeelings") or {}).get("requireDislike", True)),
        "minDecisionPoints": int((brief.get("decisionPoints") or {}).get("minPoints", 2)),
        "forbidStandaloneTips": bool((brief.get("tipsEmbeddingPolicy") or {}).get("forbidStandaloneBlock", True)),
    }
    style_family = str(brief.get("styleFamily") or "")
    creative_brief = build_creative_brief(
        brief,
        title=title,
        carrier=carrier,
        byline=byline,
        writing_intent=brief.get("writingIntent"),
        style_family=style_family,
    )
    creator_assignment = creator_from_payload(brief)
    # 图片作品/画报是结构化图集 + 短配文，不携带长文叙事的章节意图与证据点。
    is_image_carrier = str(carrier or "").lower() in ("image", "gallery")
    return {
        "schemaVersion": "quwoquan_data.writing_pack",
        "ref": ref,
        "kind": kind,
        "title": title,
        "byline": byline,
        "carrier": carrier,
        "publishLayout": publish_layout,
        "publishMediaMode": brief.get("publishMediaMode"),
        "sourceCollectionId": brief.get("sourceCollectionId"),
        # 图片作品的标题/配文长度策略，与 handoff 图片草稿契约同源（短配文，非长文）。
        "captionPolicy": {"titleMaxChars": 80, "captionMaxChars": 300} if is_image_carrier else {},
        "templateId": brief.get("templateId"),
        "wordCount": brief.get("wordCount") or {"min": 700, "max": 1600},
        "forbiddenPhrases": [str(x) for x in (brief.get("forbiddenPhrases") or []) if x],
        "mustIncludeFacts": [str(x) for x in (brief.get("mustIncludeFacts") or []) if x],
        "sectionIntents": [] if is_image_carrier else list(section_intents),
        "narrativeContract": narrative,
        "styleFamily": style_family,
        "creativeBrief": creative_brief,
        **creator_assignment,
        "evidencePoints": [] if is_image_carrier else _evidence_points(evidence_bundle),
        "assets": _compact_assets(assets),
        "sourceUrls": [str(x) for x in source_urls if x],
        "sourcePaths": [str(x) for x in source_paths if x],
        "writingIntent": brief.get("writingIntent"),
        "baseSourceRef": brief.get("baseSourceRef"),
        "baseSourceReusePolicy": brief.get("baseSourceReusePolicy"),
        "sourceUseMode": brief.get("sourceUseMode"),
        "bannedRegisterTerms": [str(x) for x in (brief.get("bannedRegisterTerms") or []) if x],
    }


def _fmt_list(items: Sequence[str], bullet: str = "-") -> str:
    return "\n".join(f"{bullet} {x}" for x in items if x) or "（无）"


def _base_fidelity_range_label() -> str:
    return f"{int(FIDELITY_MIN * 100)}%~{int(FIDELITY_MAX * 100)}%"


def _source_use_mode(pack: Mapping[str, Any]) -> str:
    return str(pack.get("sourceUseMode") or "factual_reference_only").strip()


def _adapt_base_draft(pack: Mapping[str, Any]) -> bool:
    """是否以底稿为骨架轻改：licensed_adaptation 与 factual_reference_only 统一为 True。"""
    return base_draft_is_adaptable(_source_use_mode(pack))


def _append_persona_block(lines: list[str], persona: Any, *, adapt_base: bool) -> None:
    """渲染「作者人设（轻量化适配）」块：把匹配到的虚拟创作者人设注入 prompt。

    适配仅作用于用词用语/语气/写作手法等表层风格，严禁为贴合人设而改事实、
    或虚构亲历/资质。adapt_base 为底稿轻改模式（licensed/factual 统一），否则为纯事实证据模式。
    """
    if not isinstance(persona, Mapping) or not persona:
        return
    lines.append("### 作者人设（语气适配，不改事实）")
    lines.append("")
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
    lines.append("")


def _render_image_task_prompt(pack: Mapping[str, Any]) -> str:
    """图片作品/画报的精简任务指令：结构化图集 + 短配文，不走长文叙事与证据点。"""
    caption = pack.get("captionPolicy") if isinstance(pack.get("captionPolicy"), Mapping) else {}
    title_max = int(caption.get("titleMaxChars") or 80)
    caption_max = int(caption.get("captionMaxChars") or 300)
    lines: list[str] = []
    lines.append(f"# 图片作品任务：{pack.get('title')}")
    lines.append("")
    lines.append(
        f"- ref: `{pack.get('ref')}` ｜ 载体: `{pack.get('carrier')}` ｜ "
        f"来源集合: `{pack.get('sourceCollectionId')}`"
    )
    lines.append(f"- 署名口吻: {pack.get('byline')}")
    if pack.get("creatorProfileId") or pack.get("authorId"):
        lines.append(
            f"- 发布作者锁定: creatorProfileId=`{pack.get('creatorProfileId')}` ｜ "
            f"authorId=`{pack.get('authorId')}`；禁止改写或把来源网页作者当作发布作者。"
        )
    lines.append("")
    lines.append("## 图片作品契约（结构化图集，不是长文）")
    lines.append("")
    lines.append(
        f"- 只交付同一来源集合的 1..20 张已授权图片；标题可空且不超过 {title_max} 字，"
        f"整组配文可空且不超过 {caption_max} 字。"
    )
    lines.append(
        "- 配文独立显示在图片浏览器底部，禁止写成长文、二级标题、长段落或自检表格；不输出 article 正文。"
    )
    lines.append(
        "- 去除原平台名/原作者署名/水印/来源痕迹（以虚拟创作者身份发布）；"
        "不得编造图片中不存在的事实，配文只描述画面与可核验信息。"
    )
    assets = [a for a in (pack.get("assets") or []) if isinstance(a, Mapping)]
    if assets:
        lines.append("")
        lines.append("## 可用图片素材（同一来源集合，按顺序选用）")
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
            lines.append(f"{index}. " + " ｜ ".join(parts))
    return "\n".join(lines)


def render_prompt_md(pack: Mapping[str, Any]) -> str:
    """渲染给会话模型的人类可读写作指令。"""
    carrier = pack.get("carrier")
    if str(carrier or "").lower() in ("image", "gallery"):
        return _render_image_task_prompt(pack)
    nc = pack.get("narrativeContract") or {}
    wc = pack.get("wordCount") or {}
    adapt_base = _adapt_base_draft(pack)
    lines: list[str] = []
    lines.append(f"# 写作任务：{pack.get('title')}")
    lines.append("")
    lines.append(f"- ref: `{pack.get('ref')}` ｜ 类型: `{pack.get('kind')}` ｜ 载体: `{carrier}` ｜ 模板: `{pack.get('templateId')}`")
    lines.append(f"- 署名口吻: {pack.get('byline')}")
    if pack.get("creatorProfileId") or pack.get("authorId"):
        lines.append(
            f"- 发布作者锁定: creatorProfileId=`{pack.get('creatorProfileId')}` ｜ "
            f"authorId=`{pack.get('authorId')}` ｜ 禁止改写、替换或把来源网页作者当作发布作者"
        )
    lines.append(f"- 字数区间: {wc.get('min', '?')}–{wc.get('max', '?')} 字（去空白）")
    lines.append("")
    lines.append("## 创作要求（必须由你——会话模型——基于下方真实素材创作，禁止套用固定句式/槽位拼接）")
    lines.append("")
    creative = pack.get("creativeBrief") if isinstance(pack.get("creativeBrief"), Mapping) else {}
    if creative:
        lines.append("### 创作自治边界（creativeBrief）")
        lines.append("")
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
        lines.append("")
        _append_persona_block(lines, creative.get("persona"), adapt_base=adapt_base)
    intent = pack.get("writingIntent")
    if intent and intent in WRITING_INTENTS:
        spec = WRITING_INTENTS[intent]
        lines.append(
            f"- **写作主线（writingIntent=`{intent}` · {spec['label']}）**：{spec['desc']} "
            "全篇只服务这一条主线，禁止把攻略/咨询、决策体验、游后游记三类混写。"
        )
    base = pack.get("baseSourceRef")
    base_text = str(pack.get("baseDraftText") or "")
    if base:
        if adapt_base:
            lines.append(
                f"- **底稿来源**：`{base}` 作为本篇表达骨架。在底稿基础上做**适度润色 + 人设适配**"
                "（去语病/错字、私人信息脱敏替代、按作者人设微调用词用语与写作手法），"
                f"优质原文与自然段可保留，贴合度 {_base_fidelity_range_label()}。"
                "禁止脱离底稿大修/重写/编故事或改到面目全非；去除原平台名/原作者署名/水印（以虚拟创作者身份发布）。"
            )
        else:
            lines.append(
                f"- **事实参考来源**：`{base}` 只作为事实、路线顺序、条件和可核验数字的证据池。"
                "正文必须独立表达，禁止复用连续长句、自然段、作者表达或原文结构；"
                "不得把事实参考材料当成可改编底稿。"
            )
        lines.append(
            "- **禁止暴露内部标识**：上面的底稿/来源路径仅供你内部参考；"
            "禁止把底稿文件名、目录名、source 编号（如 `…_base_1`、`source.md`、`sources/…`）"
            "或任何采集来源痕迹写进正文、标题或配文。"
        )
    banned = pack.get("bannedRegisterTerms") or []
    if banned:
        lines.append(f"- **禁用语域**：本主体禁止出现 {', '.join(banned)} 等错配语域词。")
    lines.append("")
    if carrier in ("image", "gallery"):
        lines.append(
            "- 载体=image：只提交同一来源集合的 1..20 张图片。标题可空且不超过 80 字；"
            "整组配文可空且不超过 300 字。配文独立显示在图片浏览器底部，不得写成长文或与图片混排；"
            "建议正文配文控制在 260 个中文字符以内，不写二级标题、不写长段落、不输出自检表格。"
        )
    else:
        og = pack.get("openingGuidance") or opening_guidance(str(pack.get("styleFamily") or ""))
        opening_opts = og.get("openingStrategies") or []
        if opening_opts:
            lines.append(f"- **开篇方式（styleFamily=`{og.get('styleFamily') or pack.get('styleFamily')}`，从下列任选一种真正落地，禁止千篇一律的套路开头）**：")
            for opt in opening_opts:
                lines.append(f"  - `{opt.get('id')}`（{opt.get('label')}）：{opt.get('hint')}")
            lines.append("  按原文体裁与证据择一；若该默认体裁与原文体裁不符，可改选下方候选体裁，并在 draft_meta 写明最终 styleFamily 与 openingStrategy。")
            lines.append(
                "  首段必须直接体现所选策略：结论先行就用「先说结论/直接说/一句话」开头；"
                "设问悬念就提出一个真实问题；场景沉浸就用具体时间、天气、动作或身体位置进入现场；"
                "对比并置就明确写出两种选择/两类人/两个时刻。禁止使用「我在屏幕上看了无数遍/总怕亲眼一看不过如此」这类旧套路。"
            )
        elif nc.get("requireMotivation"):
            lines.append("- 开篇写出**出发动机/心情铺垫**（为什么想去、出发前的犹豫或期待），不要一上来就罗列行程。")
        if nc.get("requireLike"):
            lines.append("- 正文写出**具体喜欢/打动你的点**（来自素材，有画面感），并显式出现“喜欢/打动/值得/治愈/松弛/心动”等可识别表达。")
        if nc.get("requireDislike"):
            lines.append("- 也要诚实写出**不足/劝退点**（来自素材），并显式出现“不足/遗憾/劝退/不建议/失望/踩雷”等可识别表达。")
        lines.append(f"- 给出至少 {nc.get('minDecisionPoints', 2)} 处**取舍判断**（如「如果你…我会建议…」「宁可…也别…」）。")
        if nc.get("forbidStandaloneTips"):
            lines.append("- 注意事项**就地融入**叙述，禁止另起「实用信息/来源平台」清单块。")
        lines.append(
            "- 取舍判断必须自然融入正文收尾或段内判断，禁止使用「它到底适合谁 / 这条线适合谁 / "
            "这趟适合谁 / 到底适合谁 / 适合谁」作为固定小标题。"
        )
        lines.append("")
        lines.append("### 体裁结构与 Review Gate 硬门槛（必须全部满足，否则审稿驳回）")
        lines.append(
            "- **分节硬要求**：正文必须用**至少 3 个自然的 `## ` 小标题**分节，每节至少 2 个散文段落；"
            "标题用场景 / 视角 / 判断式命名（贴合本篇主线与实体），但**不得**写成 `## 节点顺序`"
            "`## 实用信息` 这类机械清单标题。禁止整篇无小标题的连续散文，也禁止整篇靠图块 / 短句 / 清单堆叠。"
        )
        lines.append(
            "- **禁止伪装真实亲历**：本文以虚拟创作者 / 平台编辑口吻发布，正文严禁出现"
            "「我亲自 / 亲眼看到 / 亲眼看见 / 我去了 / 我去过 / 我住了 / 我拍到 / 我拍了 / 真实走过 / 去过…之后」"
            "等第一人称真人亲历表达；改用观察、资料整理、读者代入或「据到访者反馈 / 从现场记录看」等不伪装亲历的表达。"
        )
        lines.append(
            "- **情感标记硬要求**：正文必须**显式**出现至少一个正向情感词"
            "（喜欢 / 打动 / 值得 / 治愈 / 松弛 / 心动 之一）和至少一个负向 / 劝退词"
            "（不足 / 遗憾 / 劝退 / 不建议 / 失望 / 踩雷 之一），且必须落在与素材相符的具体情境里，不能空贴标签。"
        )
        lines.append(
            "- **结尾差异化**：结尾段必须与本篇主线 / 实体强绑定给出具体判断，"
            "禁止「无论你是…都值得…」「总之 / 总而言之，…值得一去」这类与同批其它文章雷同的通用收尾。"
        )
        lines.append("")
        if base_text and adapt_base:
            lines.append("- 以下方底稿为基底做适度润色与人设适配，并用其它证据补全/校正事实；底稿合理的标题、小标题与结构可保留。")
        elif base_text:
            lines.append("- 以下方事实参考材料只用于抽取可核验事实、路线顺序、条件和数字；正文结构按 writingIntent 独立组织，禁止照搬来源段落。")
        else:
            lines.append("- 综合证据点独立组织内容，不要把多个来源机械拼成清单，也不要每篇都用相同章节套路。")
    lines.append("- 信息必须来自下方素材；**禁止编造**票价/时长/海拔/里程等数字（拿不准就写区间或定性，别杜撰精确值）。")
    if adapt_base:
        lines.append("- 去除原平台名/原作者署名/水印/来源痕迹（本文以虚拟创作者身份发布）；可在底稿基础上保留优质原文。")
    else:
        lines.append("- 去除原平台名/原作者署名/水印/来源痕迹（本文以虚拟创作者身份发布）；事实参考来源不得复用原文长句或段落表达。")
    lines.append(
        "- **私人联系方式脱敏替代**：正文不得出现私人电话/手机/微信/QQ（做脱敏替代，而非整段删除）；"
        "仅可保留紧急或公共服务短号（如 110/120/12301）或 source 证据中核实的景区官方接待电话。"
    )
    lines.append(
        "- **小标题自然、避免机械清单标题**：禁止 `## 节点顺序` `## 实用信息` `## 注意事项` `## 门票信息` 这类纯功能清单标题；"
        "**不要套用统一标题模板**；底稿合理的标题与小标题可保留。"
    )
    forb = pack.get("forbiddenPhrases") or []
    if forb:
        lines.append(f"- 禁用词: {', '.join(forb)}")
    lines.append("")
    if base_text:
        if adapt_base:
            lines.append(f"## 底稿（以此为骨架适度润色 + 人设适配；贴合度 {_base_fidelity_range_label()}）")
        else:
            lines.append("## 事实参考材料（只取事实，不保留表达）")
        lines.append("")
        if adapt_base:
            lines.append(
                "> 在底稿基础上做适度润色与人设用词语气适配，优质原文与自然段可保留；"
                "去除原平台名/原作者署名/水印，禁止重写到面目全非或改变事实。"
            )
        else:
            lines.append(
                "> 只抽取事实、顺序、条件、数字和可回溯判断。不要保留来源连续长句、自然段、作者表达或原文结构。"
            )
        lines.append("")
        lines.append("### 底稿编辑硬合同" if adapt_base else "### 事实引用硬合同")
        lines.append("")
        if adapt_base:
            lines.append(
                "- 先把下方底稿当作初稿骨架处理：保留原有叙述顺序、主要自然段和核心句群，"
                "再做去语病、去平台痕迹、私人信息脱敏、事实校正和人设适配。"
            )
            lines.append(
                "- 不要把底稿逐段同义改写成新文；与主题相关、没有广告/隐私/平台痕迹的句群应尽量原句保留，"
                "只在必要处微调语序、错字和语气。"
            )
            lines.append(
                f"- Review Gate 会检查 `baseDraftFidelity`，目标区间 {_base_fidelity_range_label()}；"
                "不要用百科/官网/其它来源重新写一篇新文章，补充证据只能用于校正或补一句上下文。"
            )
            lines.append(
                "- **保真硬底线（连续 3 字重合度，低于 55% 直接驳回）**：必须**逐句沿用底稿原有措辞与短语**，"
                "多数句子在底稿原句上做最小改动（去平台痕迹/脱敏/错字/语气微调），而**不是**整句同义改写。"
                "判断标准：把你的成稿与底稿逐句比对，应有过半句子能在底稿里找到几乎相同的连续片段；"
                "若你发现自己在‘换一种说法重写’，立即停手改回保留原句。宁可少删，也不要为求新而重写。"
            )
            lines.append(
                "- 如果为了删除广告、保险、平台活动或无关城市段落导致正文变短，必须优先保留与本篇标题、"
                "writingIntent 和景区体验直接相关的底稿段落，而不是改写成全新的攻略结构。"
            )
            lines.append(
                "- `draft_meta.selfCritique` 需写入 `baseDraftFidelityStrategy`，说明保留了哪些底稿段落、"
                "删除了哪些平台/广告/无关信息以及为什么仍满足贴合度。"
            )
        else:
            lines.append(
                "- 先从下方材料提取可核验事实、路线顺序、约束条件、取舍依据和带单位数字，再用自己的句子重新组织。"
            )
            lines.append(
                "- 禁止逐段同义改写、禁止保留来源连续长句、禁止复用原小标题/原段落结构；"
                "可以保留专有名词、地点名、公开数字和必要短事实短语。"
            )
            lines.append(
                "- Review Gate 会检查事实回溯、证据边界、来源痕迹、标题兑现和写作主线；"
                "不要为了模仿材料表达而牺牲权利边界。"
            )
            lines.append(
                "- `draft_meta.selfCritique` 需写入 `sourceUseModeBoundary`，说明哪些内容只取事实、"
                "哪些表达已独立改写，以及为什么没有复用未授权长句。"
            )
        lines.append("")
        lines.append(base_text)
        lines.append("")
        from _common.content_review import _NUMERIC_FACT_RE

        numeric_tokens = sorted(
            {match.group(0).strip() for match in _NUMERIC_FACT_RE.finditer(base_text)}
        )
        if numeric_tokens:
            lines.append("## 带单位数字白名单（正文仅允许复用底稿已出现的带单位数字）")
            lines.append("")
            lines.append(_fmt_list(numeric_tokens))
            lines.append("")
    og = pack.get("openingGuidance") or opening_guidance(str(pack.get("styleFamily") or ""))
    candidates = og.get("styleFamilyCandidates") or []
    if candidates and carrier not in ("image", "gallery"):
        lines.append("## 体裁候选（默认已按路由选定；仅当原文体裁明显更贴合另一种时改选，并在 draft_meta 写明）")
        lines.append("")
        for c in candidates:
            mark = "（默认）" if c.get("styleFamily") == og.get("styleFamily") else ""
            lines.append(f"- `{c.get('styleFamily')}`{mark}：{c.get('writingGenre')}")
        lines.append("")
    lines.append("## 必须覆盖的事实")
    lines.append("")
    lines.append(_fmt_list(pack.get("mustIncludeFacts") or []))
    lines.append("")
    source_paths = [str(x) for x in (pack.get("sourcePaths") or []) if x]
    if source_paths:
        lines.append("## 允许引用的来源路径")
        lines.append("")
        lines.append(_fmt_list(source_paths))
        lines.append("")
    if adapt_base:
        lines.append("## 章节意图（仅参考；结构以底稿为准，可自然调整，不要照抄为标题）")
    else:
        lines.append("## 章节意图（仅参考；结构按 writingIntent 独立组织，不要照抄为标题）")
    lines.append("")
    section_intents = [str(item) for item in (pack.get("sectionIntents") or [])]
    lines.append(_fmt_list(section_intents))
    lines.append("")
    lines.append("## 证据点（逐实体，按此创作，引用其中信息）")
    lines.append("")
    for p in pack.get("evidencePoints") or []:
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
    lines.append("## 配图（在正文中用 figure 块插入，按 figureId 与 assetId 对应）")
    lines.append("")
    lines.append(
        "> 每轮创作/修改前**重新读取本 writing_pack 的 assets**，`asset://` 只能引用下方列出的 assetId；"
        "禁止沿用会话记忆里的旧 assetId（recompose 后 id 可能变化，引用旧 id 会被 generatorProvenance 门拦截）。"
    )
    lines.append("")
    for index, img in enumerate(pack.get("assets") or [], start=1):
        lines.append(
            f"- figureId=`{_asset_figure_id(img, index)}` assetId=`{img.get('assetId')}` "
            f"实体={img.get('entityName')} 版面={img.get('imageLayout')} 建议说明={img.get('caption')}"
        )
    lines.append("")
    lines.append("### figure 块写法")
    lines.append("")
    lines.append('```')
    lines.append(':::figure id="cover" layout="fullWidth" caption="你的自然说明"')
    lines.append("asset://<assetId>")
    lines.append(":::")
    lines.append('```')
    lines.append("")
    lines.append("## Review Gate 硬检查（reviewGateChecklist）")
    lines.append("")
    lines.append(
        "- `draft_meta.creativePlan`：至少 2 个候选构思 concepts、selectedPlanId、selectionReason、"
        "readerPromise、unusedFacts。"
    )
    lines.append(
        "- `draft_meta.selfCritique`：必须自评 readerPromise、titlePromise、informationDensity、"
        "evidenceBoundary、personaBoundary。"
    )
    lines.append(
        "- 禁止伪装亲历：平台编辑 / 虚拟作者口吻不得写「我亲自 / 亲眼看到 / 我去了 / 我去过 / 我住了 / "
        "我拍到 / 真实走过」等真人亲历表达；数字不得超出底稿 / 证据白名单。"
    )
    if carrier not in ("image", "gallery"):
        lines.append(
            "- 体裁结构：至少 3 个自然 `## ` 小标题、每节 ≥2 段散文；显式正向情感词 + 负向 / 劝退词各 ≥1；"
            "结尾与本篇主线强绑定、不与同批雷同。"
        )
    lines.append("")
    lines.append("## 产出方式")
    lines.append("")
    lines.append("- 把创作的正文写回同目录 `draft.article.md`（覆盖占位）。")
    lines.append(
        "- 在同目录 `draft_meta.json` 标注 generator=agent、model、styleFamily、openingStrategy（所选开篇策略 id）、"
        "引用了哪些 sourcePath、覆盖了哪些 fact。"
    )
    lines.append(
        "- `draft_meta.creativePlan` 必须包含至少 2 个候选构思 concepts、selectedPlanId、selectionReason、"
        "readerPromise、unusedFacts；`draft_meta.selfCritique` 必须说明 readerPromise、titlePromise、"
        "informationDensity、evidenceBoundary、personaBoundary。"
    )
    lines.append("- 之后运行 `produce --stage review` 过门禁；**失败按 repair report 修改正文重跑（Ralph 自纠环），直到 ref_review_gate 全绿（approved）或超墙钟上限**；不得在未过门时宣称完成。")
    return "\n".join(lines) + "\n"

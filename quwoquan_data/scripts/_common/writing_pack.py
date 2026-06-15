"""Writing pack：CLI prepare 产出的"写作契约"，供会话模型创作正文。

writing_pack 把证据、选好的图、必须覆盖的事实、约束、章节意图等结构化下发；
prompt.md 是其人类可读版本（会话模型据此创作）。CLI 不再拼接任何正文句子。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from _common.base_draft import FIDELITY_MAX, FIDELITY_MIN
from _common.content_object import require_title_hint
from _common.quality_gates import WRITING_INTENTS
from _common.style_catalog import opening_guidance


def _load_sop_fewshot(sop_example_ref: str | None) -> dict[str, str] | None:
    """按 sopExampleRef（相对 DATA_ROOT，如 sop/主页/地点/景区/example.md）读范例 + 同目录 guide。

    sop 是全局单一真相源（按实体类型），这里只读注入做 few-shot，不写不拷；
    缺失或读失败时返回 None（render 优雅跳过，不报错）。
    """
    if not sop_example_ref:
        return None
    from _common import paths

    example_path = paths.DATA_ROOT / sop_example_ref
    try:
        example = example_path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    guide_path = example_path.parent / "guide.md"
    try:
        guide = guide_path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        guide = ""
    if not example and not guide:
        return None
    return {"ref": sop_example_ref, "example": example[:1800], "guide": guide[:1200]}


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


def _compact_condition_context(brief: Mapping[str, Any]) -> dict[str, Any]:
    context = brief.get("conditionContext") or {}
    if not isinstance(context, Mapping):
        return {}
    region = context.get("region")
    if isinstance(region, Mapping):
        return {
            "region": {
                "label": region.get("label") or region.get("name"),
                "name": region.get("name") or region.get("label"),
            }
        }
    return {}


def _compact_assets(assets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "assetId",
        "fileName",
        "caption",
        "kind",
        "role",
        "entityName",
        "sourcePath",
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
    return {
        "schemaVersion": "quwoquan_data.writing_pack",
        "ref": ref,
        "kind": kind,
        "title": title,
        "byline": byline,
        "carrier": carrier,
        "publishLayout": publish_layout,
        "templateId": brief.get("templateId"),
        "wordCount": brief.get("wordCount") or {"min": 700, "max": 1600},
        "forbiddenPhrases": [str(x) for x in (brief.get("forbiddenPhrases") or []) if x],
        "mustIncludeFacts": [str(x) for x in (brief.get("mustIncludeFacts") or []) if x],
        "conditionContext": _compact_condition_context(brief),
        "sectionIntents": list(section_intents),
        "narrativeContract": narrative,
        "styleFamily": style_family,
        "evidencePoints": _evidence_points(evidence_bundle),
        "assets": _compact_assets(assets),
        "sourceUrls": [str(x) for x in source_urls if x],
        "sourcePaths": [str(x) for x in source_paths if x],
        "sopExampleRef": brief.get("sopExampleRef"),
        "writingIntent": brief.get("writingIntent"),
        "baseSourceRef": brief.get("baseSourceRef"),
        "sourceUseMode": brief.get("sourceUseMode"),
        "bannedRegisterTerms": [str(x) for x in (brief.get("bannedRegisterTerms") or []) if x],
    }


def _fmt_list(items: Sequence[str], bullet: str = "-") -> str:
    return "\n".join(f"{bullet} {x}" for x in items if x) or "（无）"


def _base_fidelity_range_label() -> str:
    return f"{int(FIDELITY_MIN * 100)}%~{int(FIDELITY_MAX * 100)}%"


def render_prompt_md(pack: Mapping[str, Any]) -> str:
    """渲染给会话模型的人类可读写作指令。"""
    nc = pack.get("narrativeContract") or {}
    carrier = pack.get("carrier")
    wc = pack.get("wordCount") or {}
    lines: list[str] = []
    lines.append(f"# 写作任务：{pack.get('title')}")
    lines.append("")
    lines.append(f"- ref: `{pack.get('ref')}` ｜ 类型: `{pack.get('kind')}` ｜ 载体: `{carrier}` ｜ 模板: `{pack.get('templateId')}`")
    lines.append(f"- 署名口吻: {pack.get('byline')}")
    lines.append(f"- 字数区间: {wc.get('min', '?')}–{wc.get('max', '?')} 字（去空白）")
    lines.append("")
    lines.append("## 创作要求（必须由你——会话模型——基于下方真实素材创作，禁止套用固定句式/槽位拼接）")
    lines.append("")
    intent = pack.get("writingIntent")
    if intent and intent in WRITING_INTENTS:
        spec = WRITING_INTENTS[intent]
        lines.append(
            f"- **写作主线（writingIntent=`{intent}` · {spec['label']}）**：{spec['desc']} "
            "全篇只服务这一条主线，禁止把攻略/咨询、决策体验、游后游记三类混写。"
        )
    base = pack.get("baseSourceRef")
    base_text = str(pack.get("baseDraftText") or "")
    source_use_mode = str(pack.get("sourceUseMode") or "factual_reference_only")
    has_authorized_base = source_use_mode == "licensed_adaptation"
    if base:
        if has_authorized_base:
            lines.append(
                f"- **授权底稿来源**：`{base}` 可在许可范围内改编；保留事实和必要结构，"
                f"贴合度控制在 {_base_fidelity_range_label()}，同时保留署名与授权快照。"
            )
        else:
            lines.append(
                f"- **事实参考来源**：`{base}` 仅用于提取可核验事实。必须独立组织结构和表达，"
                "禁止复现连续长句、原文小标题和作者个人叙事。"
            )
    banned = pack.get("bannedRegisterTerms") or []
    if banned:
        lines.append(f"- **禁用语域**：本主体禁止出现 {', '.join(banned)} 等错配语域词。")
    lines.append("")
    if carrier in ("image", "gallery"):
        lines.append(
            "- 载体=image：只提交同一来源集合的 1..20 张图片。标题可空且不超过 80 字；"
            "整组配文可空且不超过 300 字。配文独立显示在图片浏览器底部，不得写成长文或与图片混排。"
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
            lines.append("- 正文写出**具体喜欢/打动你的点**（来自素材，有画面感）。")
        if nc.get("requireDislike"):
            lines.append("- 也要诚实写出**不足/劝退点**（来自素材）。")
        lines.append(f"- 给出至少 {nc.get('minDecisionPoints', 2)} 处**取舍判断**（如「如果你…我会建议…」「宁可…也别…」）。")
        if nc.get("forbidStandaloneTips"):
            lines.append("- 注意事项**就地融入**叙述，禁止另起「实用信息/来源平台」清单块。")
        if base_text:
            if has_authorized_base:
                lines.append("- 以下方授权底稿为基底，在许可范围内改编并用其它证据补全事实。")
            else:
                lines.append("- 以下方事实参考材料核验信息，自行重组标题、章节和叙事顺序，禁止沿用原文结构。")
        else:
            lines.append("- 综合证据点独立组织内容，不要把多个来源机械拼成清单，也不要每篇都用相同章节套路。")
    lines.append("- 信息必须来自下方素材；**禁止编造**票价/时长/海拔/里程等数字（拿不准就写区间或定性，别杜撰精确值）。")
    lines.append("- 禁止出现平台名/作者名/水印/来源痕迹；禁止逐句搬运素材原文（改写为自己的表达）。")
    lines.append(
        "- **禁止私人联系方式**：正文不得出现私人电话/手机/微信/QQ；仅可保留紧急或公共服务短号（如 110/120/12301）"
        "或 source 证据中核实的景区官方接待电话。"
    )
    lines.append(
        "- **小标题自然、避免机械清单标题**：禁止 `## 节点顺序` `## 实用信息` `## 注意事项` `## 门票信息` 这类纯功能清单标题；"
        "**不要套用统一标题模板，也不要复制普通网页的原标题或小标题**。"
    )
    forb = pack.get("forbiddenPhrases") or []
    if forb:
        lines.append(f"- 禁用词: {', '.join(forb)}")
    lines.append("")
    if base_text:
        heading = (
            f"## 授权底稿（许可范围内改编；贴合度 {_base_fidelity_range_label()}）"
            if has_authorized_base
            else "## 事实参考材料（只取可核验事实，必须独立表达）"
        )
        lines.append(heading)
        lines.append("")
        if has_authorized_base:
            lines.append("> 在许可范围内加工，保留必要署名；禁止逐句搬运超出许可或掩盖来源。")
        else:
            lines.append("> 只抽取事实，独立拟定标题、结构和句子；不得模仿原作者叙事顺序或复现连续长句。")
        lines.append("")
        lines.append(base_text)
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
    sop = pack.get("sopFewshot") or _load_sop_fewshot(str(pack.get("sopExampleRef") or "")) or {}
    if sop.get("example") or sop.get("guide"):
        if base_text:
            lines.append("## 写作范例与规范（few-shot：仅供参考其**口吻与信息颗粒度**；**结构以上方底稿为准**，禁止照搬范例结构、事实、实体与数字）")
        else:
            lines.append("## 写作范例与规范（few-shot：模仿其口吻与信息颗粒度，结构跟随底稿，禁止照搬其事实、实体与数字）")
        lines.append("")
        if sop.get("example"):
            lines.append(sop["example"])
            lines.append("")
        if sop.get("guide"):
            lines.append("### 规范要点（sop guide）")
            lines.append("")
            lines.append(sop["guide"])
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
    lines.append("## 章节意图（仅参考；结构以底稿为准，可自然调整，不要照抄为标题）")
    lines.append("")
    lines.append(_fmt_list(pack.get("sectionIntents") or []))
    lines.append("")
    cc = pack.get("conditionContext") or {}
    region = cc.get("region") if isinstance(cc, Mapping) else None
    if region:
        lines.append(f"## 地域条件：{region.get('label') or region.get('name')}（涉及海拔/高反等地域专有现象时，正文需体现该条件）")
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
    lines.append("## 产出方式")
    lines.append("")
    lines.append("- 把创作的正文写回同目录 `draft.article.md`（覆盖占位）。")
    lines.append("- 在同目录 `draft_meta.json` 标注 generator=agent、model、styleFamily、openingStrategy（所选开篇策略 id）、引用了哪些 sourcePath、覆盖了哪些 fact。")
    lines.append("- 之后运行 `produce --stage review` 过门禁；**失败按 repair report 修改正文重跑（Ralph 自纠环），直到 ref_review_gate 全绿（approved）或超墙钟上限**；不得在未过门时宣称完成。")
    return "\n".join(lines) + "\n"

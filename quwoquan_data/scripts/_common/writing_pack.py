"""Writing pack：CLI prepare 产出的"写作契约"，供会话模型创作正文。

writing_pack 把证据、选好的图、必须覆盖的事实、约束、章节意图等结构化下发；
prompt.md 是其人类可读版本（会话模型据此创作）。CLI 不再拼接任何正文句子。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

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
    keep = ("assetId", "fileName", "caption", "kind", "role", "entityName", "sourcePath", "imageLayout")
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
        "title": str(brief.get("titleHint") or ref),
        "byline": byline,
        "carrier": carrier,
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
        "sopExampleRef": brief.get("sopExampleRef"),
    }


def _fmt_list(items: Sequence[str], bullet: str = "-") -> str:
    return "\n".join(f"{bullet} {x}" for x in items if x) or "（无）"


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
    if carrier == "gallery":
        lines.append("- 载体=画报：以图为主、每图配一句自然小字说明；避免大空白；正文简短但仍要有真实感受。")
    else:
        og = pack.get("openingGuidance") or opening_guidance(str(pack.get("styleFamily") or ""))
        opening_opts = og.get("openingStrategies") or []
        if opening_opts:
            lines.append(f"- **开篇方式（styleFamily=`{og.get('styleFamily') or pack.get('styleFamily')}`，从下列任选一种真正落地，禁止千篇一律的套路开头）**：")
            for opt in opening_opts:
                lines.append(f"  - `{opt.get('id')}`（{opt.get('label')}）：{opt.get('hint')}")
            lines.append("  按原文体裁与证据择一；若该默认体裁与原文体裁不符，可改选下方候选体裁，并在 draft_meta 写明最终 styleFamily 与 openingStrategy。")
        elif nc.get("requireMotivation"):
            lines.append("- 开篇写出**出发动机/心情铺垫**（为什么想去、出发前的犹豫或期待），不要一上来就罗列行程。")
        if nc.get("requireLike"):
            lines.append("- 正文写出**具体喜欢/打动你的点**（来自素材，有画面感）。")
        if nc.get("requireDislike"):
            lines.append("- 也要诚实写出**不足/劝退点**（来自素材）。")
        lines.append(f"- 给出至少 {nc.get('minDecisionPoints', 2)} 处**取舍判断**（如「如果你…我会建议…」「宁可…也别…」）。")
        if nc.get("forbidStandaloneTips"):
            lines.append("- 注意事项**就地融入**叙述，禁止另起「实用信息/来源平台」清单块。")
        lines.append("- 以证据点里**信息最完整、最有现场感**的那条原文叙事线为基底做**深度加工**：遵从其观察顺序与思路，再用其它来源补全事实与细节；不要把多个来源平均拼接成模板化清单，也不要每篇都用相同章节套路。")
    lines.append("- 信息必须来自下方素材；**禁止编造**票价/时长/海拔/里程等数字（拿不准就写区间或定性，别杜撰精确值）。")
    lines.append("- 禁止出现平台名/作者名/水印/来源痕迹；禁止逐句搬运素材原文（改写为自己的表达）。")
    forb = pack.get("forbiddenPhrases") or []
    if forb:
        lines.append(f"- 禁用词: {', '.join(forb)}")
    lines.append("")
    og = pack.get("openingGuidance") or opening_guidance(str(pack.get("styleFamily") or ""))
    candidates = og.get("styleFamilyCandidates") or []
    if candidates and carrier != "gallery":
        lines.append("## 体裁候选（默认已按路由选定；仅当原文体裁明显更贴合另一种时改选，并在 draft_meta 写明）")
        lines.append("")
        for c in candidates:
            mark = "（默认）" if c.get("styleFamily") == og.get("styleFamily") else ""
            lines.append(f"- `{c.get('styleFamily')}`{mark}：{c.get('writingGenre')}")
        lines.append("")
    sop = pack.get("sopFewshot") or _load_sop_fewshot(str(pack.get("sopExampleRef") or "")) or {}
    if sop.get("example") or sop.get("guide"):
        lines.append("## 写作范例与规范（few-shot：模仿其口吻/结构/信息颗粒度，禁止照搬其事实、实体与数字）")
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
    lines.append("## 章节意图（建议骨架，可自然调整，不要照抄为标题）")
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
    lines.append("- 把创作的正文写回同目录 `article.md`（覆盖占位）。")
    lines.append("- 在同目录 `draft_meta.json` 标注 generator=agent、model、styleFamily、openingStrategy（所选开篇策略 id）、引用了哪些 sourcePath、覆盖了哪些 fact。")
    lines.append("- 之后运行 `produce --stage review` 过门禁；失败按 repair report 修改正文重跑直到全绿。")
    return "\n".join(lines) + "\n"

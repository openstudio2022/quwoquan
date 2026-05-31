"""Writing pack：CLI prepare 产出的"写作契约"，供会话模型创作正文。

writing_pack 把证据、选好的图、必须覆盖的事实、约束、章节意图等结构化下发；
prompt.md 是其人类可读版本（会话模型据此创作）。CLI 不再拼接任何正文句子。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _evidence_points(evidence_bundle: Mapping[str, Any], source_paths: Sequence[str]) -> list[dict[str, Any]]:
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
    story_spine = evidence_bundle.get("storySpine") or {}
    images = [
        {
            "figureId": ("cover" if a.get("role") == "cover" else ("closing" if a.get("role") == "closing" else f"fig{i}")),
            "assetId": a.get("assetId"),
            "role": a.get("role"),
            "entityName": a.get("entityName"),
            "caption": a.get("caption"),
            "imageLayout": a.get("imageLayout"),
            "sourcePath": a.get("sourcePath"),
            "imageStatus": a.get("imageStatus"),
        }
        for i, a in enumerate(assets, start=1)
    ]
    narrative = {
        "requireMotivation": bool((brief.get("openingTension") or {}).get("required", True)),
        "requireLike": bool((brief.get("explicitFeelings") or {}).get("requireLike", True)),
        "requireDislike": bool((brief.get("explicitFeelings") or {}).get("requireDislike", True)),
        "minDecisionPoints": int((brief.get("decisionPoints") or {}).get("minPoints", 2)),
        "forbidStandaloneTips": bool((brief.get("tipsEmbeddingPolicy") or {}).get("forbidStandaloneBlock", True)),
    }
    return {
        "schemaVersion": "quwoquan_data.writing_pack",
        "ref": ref,
        "kind": kind,
        "title": str(brief.get("titleHint") or ref),
        "byline": byline,
        "carrier": carrier,
        "publishLayout": publish_layout,
        "templateId": brief.get("templateId"),
        "wordCount": brief.get("wordCount") or {"min": 700, "max": 1600},
        "forbiddenPhrases": [str(x) for x in (brief.get("forbiddenPhrases") or []) if x],
        "mustIncludeFacts": [str(x) for x in (brief.get("mustIncludeFacts") or []) if x],
        "conditionContext": brief.get("conditionContext") or {},
        "sectionIntents": list(section_intents),
        "narrativeContract": narrative,
        "primaryEntity": story_spine.get("primaryEntity") or "",
        "routeEntities": story_spine.get("routeEntities") or [],
        "progression": story_spine.get("progression") or [],
        "evidencePoints": _evidence_points(evidence_bundle, source_paths),
        "images": images,
        "tagRefs": [str(x) for x in (brief.get("tagRefs") or []) if x][:6],
        "sourceUrls": list(source_urls),
        "sourcePaths": list(source_paths),
        "assets": list(assets),
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
        if nc.get("requireMotivation"):
            lines.append("- 开篇写出**出发动机/心情铺垫**（为什么想去、出发前的犹豫或期待），不要一上来就罗列行程。")
        if nc.get("requireLike"):
            lines.append("- 正文写出**具体喜欢/打动你的点**（来自素材，有画面感）。")
        if nc.get("requireDislike"):
            lines.append("- 也要诚实写出**不足/劝退点**（来自素材）。")
        lines.append(f"- 给出至少 {nc.get('minDecisionPoints', 2)} 处**取舍判断**（如「如果你…我会建议…」「宁可…也别…」）。")
        if nc.get("forbidStandaloneTips"):
            lines.append("- 注意事项**就地融入**叙述，禁止另起「实用信息/来源平台」清单块。")
    lines.append("- 信息必须来自下方素材；**禁止编造**票价/时长/海拔/里程等数字（拿不准就写区间或定性，别杜撰精确值）。")
    lines.append("- 禁止出现平台名/作者名/水印/来源痕迹；禁止逐句搬运素材原文（改写为自己的表达）。")
    forb = pack.get("forbiddenPhrases") or []
    if forb:
        lines.append(f"- 禁用词: {', '.join(forb)}")
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
    for img in pack.get("images") or []:
        lines.append(
            f"- figureId=`{img.get('figureId')}` assetId=`{img.get('assetId')}` "
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
    lines.append(f"- 把创作的正文写回 `{pack.get('ref')}.article.md`（覆盖占位）。")
    lines.append(f"- 在 `{pack.get('ref')}.draft_meta.json` 标注 generator=agent、model、引用了哪些 sourcePath、覆盖了哪些 fact。")
    lines.append("- 之后运行 `produce --stage review` 过门禁；失败按 repair report 修改正文重跑直到全绿。")
    return "\n".join(lines) + "\n"

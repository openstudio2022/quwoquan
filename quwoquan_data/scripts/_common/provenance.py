"""结构化出处记录 provenance.json ——「便于回查、区分中间过程与最终结果」单一入口。

用户诉求：中间过程文件太多、要精简；把每次「给 agent 的输入」与「最终结果」结构化记录，
原始数据源与参考补全的证据源一一登记，并区分中间过程与最终结果。

每个 post 落一份 provenance.json（取代分散的 produce_trace.json），分区：
- final           ：最终交付结果（标题/序号/generator/model/styleFamily/开篇策略/正文摘要/实体）。
- agentInput      ：本次给会话 agent 的写作契约摘要（writing_pack / prompt 引用 + 关键约束）。
- originalSources ：原始数据源（source 路径 + url）。
- evidenceSources ：参考补全证据源（检索计划 + 证据包摘要）。
- gateResults     ：各质量门结果（review decision + checks pass/fail + issues）。
- intermediate    ：调试态中间产物（story spine / 源打分），明确标注为非最终结果。

provenance_issues：强制门——每个交付 post 必须有完整且一致的 provenance.json
（存在 + schema 正确 + generator=agent + 原始源非空 + 门结果 approved + digest/引用源闭环）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.io import read_json

PROVENANCE_SCHEMA = "quwoquan_data.provenance"
PROVENANCE_FILE = "provenance.json"


def _evidence_summary(evidence_bundle: Mapping[str, Any] | None) -> dict[str, Any]:
    eb = evidence_bundle or {}
    nodes = eb.get("routeNodes") or []
    return {
        "routeNodeCount": len(nodes),
        "entityNames": [str(n.get("entityName")) for n in nodes if n.get("entityName")][:20],
        "hasStorySpine": bool(eb.get("storySpine")),
    }


def _original_sources(compose_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    paths = [str(p) for p in (compose_payload.get("sourcePaths") or []) if p]
    urls = [str(u) for u in (compose_payload.get("sourceUrls") or []) if u]
    out: list[dict[str, Any]] = []
    for index, path in enumerate(paths):
        out.append({"path": path, "url": urls[index] if index < len(urls) else None})
    for url in urls[len(paths):]:
        out.append({"path": None, "url": url})
    return out


def build_provenance(
    ref: str,
    *,
    writing_pack: Mapping[str, Any] | None,
    draft_meta: Mapping[str, Any] | None,
    review_payload: Mapping[str, Any] | None,
    compose_payload: Mapping[str, Any] | None,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    wp = writing_pack or {}
    meta = draft_meta or {}
    review = review_payload or {}
    cp = compose_payload or {}
    checks = review.get("checks") or {}
    opening_options = [
        str(o.get("id"))
        for o in ((wp.get("openingGuidance") or {}).get("openingStrategies") or [])
        if o.get("id")
    ]
    return {
        "schemaVersion": PROVENANCE_SCHEMA,
        "ref": ref,
        "final": {
            "publishTitle": manifest.get("publishTitle"),
            "publishSeq": manifest.get("publishSeq"),
            "generator": meta.get("generator") or cp.get("generator"),
            "model": meta.get("model") or cp.get("generatorModel"),
            "styleFamily": meta.get("styleFamily") or wp.get("styleFamily"),
            "openingStrategy": meta.get("openingStrategy"),
            "articleDigest": manifest.get("articleMarkdownDigest"),
            "coveredFacts": list(meta.get("coveredFacts") or []),
            "extractedEntities": list(meta.get("extractedEntities") or []),
            "entityRefs": list(manifest.get("entityRefs") or []),
        },
        "agentInput": {
            "writingPack": f"drafts/{ref}.writing_pack.json",
            "prompt": f"drafts/{ref}.prompt.md",
            "title": wp.get("title"),
            "styleFamily": wp.get("styleFamily"),
            "openingStrategyOptions": opening_options,
            "mustIncludeFacts": list(wp.get("mustIncludeFacts") or []),
            "sectionIntents": list(wp.get("sectionIntents") or []),
        },
        "originalSources": _original_sources(cp),
        "evidenceSources": {
            "relatedSearchPlan": cp.get("relatedSearchPlan"),
            "evidenceBundle": _evidence_summary(cp.get("evidenceBundle")),
        },
        "gateResults": {
            "decision": review.get("decision"),
            "qualityScore": review.get("qualityScore"),
            "checks": {name: bool(result.get("passed")) for name, result in checks.items()},
            "issues": list(review.get("issues") or []),
        },
        "citedSourcePaths": list(meta.get("citedSourcePaths") or cp.get("citedSourceRefs") or []),
        "intermediate": {
            "storySpine": cp.get("storySpine"),
            "sourceQuality": cp.get("sourceQuality") or [],
        },
    }


def provenance_issues(post_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """强制门：交付 post 必须有完整且一致的 provenance.json（存在 + 完整 + 闭环）。"""
    path = post_dir / PROVENANCE_FILE
    if not path.exists():
        return [f"{post_dir}: missing provenance.json (中间过程与最终结果必须结构化记录)"]
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"{post_dir}: provenance.json unreadable: {exc}"]
    issues: list[str] = []
    if data.get("schemaVersion") != PROVENANCE_SCHEMA:
        issues.append(f"{post_dir}: provenance.schemaVersion invalid")
    final = data.get("final") or {}
    if final.get("articleDigest") != manifest.get("articleMarkdownDigest"):
        issues.append(f"{post_dir}: provenance.final.articleDigest != manifest articleMarkdownDigest")
    if final.get("generator") != "agent":
        issues.append(f"{post_dir}: provenance.final.generator must be 'agent'")
    if not data.get("agentInput"):
        issues.append(f"{post_dir}: provenance.agentInput missing (agent 输入摘要必须记录)")
    if not data.get("originalSources"):
        issues.append(f"{post_dir}: provenance.originalSources empty (原始数据源必须一一记录)")
    if (data.get("gateResults") or {}).get("decision") != "approved":
        issues.append(f"{post_dir}: provenance.gateResults.decision must be 'approved'")
    original_paths = {str(s.get("path")) for s in (data.get("originalSources") or []) if s.get("path")}
    for cited in data.get("citedSourcePaths") or []:
        if str(cited) not in original_paths:
            issues.append(f"{post_dir}: cited source not in originalSources: {cited}")
    return issues


def provenance_completeness_issues(post_dir: Path, manifest: Mapping[str, Any]) -> list[str]:
    """兼容旧测试入口；完整性门与发布 provenance 强制门同源。"""
    return provenance_issues(post_dir, manifest)


__all__ = [
    "PROVENANCE_SCHEMA",
    "PROVENANCE_FILE",
    "build_provenance",
    "provenance_completeness_issues",
    "provenance_issues",
]

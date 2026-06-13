"""通用来源计划读取（取代任务/区域专属 curated 语料）。

来源候选由任务/Agent 在 download source_plan 输入中给出，主线不内置任何区域语料。
对象优先布局（真相源 docs/pipeline_directory_layout_spec.md §15）：
  runtime/tasks/{task}/batches/{batch}/entities/{domain}/{type}/{name}/1.download/source_plan.json
统一 payload 形态：
  {"sources": [{"source_id","platform","url","body?","imageUrls?"}], "imageUrls": [...]}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from _common.io import read_json
from _common.paths import STAGE_DOWNLOAD
from _common.source_unit import resolve_entity_object_dir

SOURCE_USE_LICENSED_ADAPTATION = "licensed_adaptation"
SOURCE_USE_FACTUAL_REFERENCE = "factual_reference_only"
SOURCE_USE_BLOCKED = "blocked"
VALID_SOURCE_USE_MODES = {
    SOURCE_USE_LICENSED_ADAPTATION,
    SOURCE_USE_FACTUAL_REFERENCE,
    SOURCE_USE_BLOCKED,
}


def _source_plan_file(task_id: str, batch_id: str, entity_id: str, entity_type: str = "") -> Path | None:
    """对象优先 source_plan 路径。"""
    obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
    object_plan = obj / STAGE_DOWNLOAD / "source_plan.json"
    if object_plan.is_file():
        return object_plan
    return None


def _extract_sources(data: Any) -> list[dict[str, Any]]:
    """读取 source_plan 的 sources（顶层或 envelope payload.sources）。"""
    if not isinstance(data, dict):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw = (
        data.get("sources")
        or payload.get("sources")
        or []
    )
    return raw if isinstance(raw, list) else []


def curated_sources_for_entity(
    task_id: str, batch_id: str, entity_id: str, entity_type: str = ""
) -> list[dict[str, Any]]:
    plan_file = _source_plan_file(task_id, batch_id, entity_id, entity_type)
    if plan_file is None:
        return []
    sources = _extract_sources(read_json(plan_file))
    out: list[dict[str, Any]] = []
    for idx, src in enumerate(sources, start=1):
        if not isinstance(src, dict):
            continue
        url = src.get("url") or src.get("link")
        if not url:
            continue
        out.append(
            {
                "source_id": src.get("source_id") or src.get("sourceId") or src.get("id") or f"source_{idx}",
                "platform": src.get("platform") or "web",
                "url": url,
                "body": src.get("body", ""),
                "title": src.get("title") or "",
                "sourceUseMode": src.get("sourceUseMode") or "",
                "license": src.get("license") or "",
                "credit": src.get("credit") or "",
                "termsUrl": src.get("termsUrl") or "",
                "licenseSnapshot": src.get("licenseSnapshot") or "",
                "authorizationProof": src.get("authorizationProof") or "",
            }
        )
    return out


def _normalize_image_specs(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            spec = {"url": item, "license": "", "credit": ""}
        elif isinstance(item, dict):
            url = item.get("url") or item.get("link") or ""
            spec = {
                "url": url,
                "license": item.get("license", ""),
                "credit": item.get("credit") or item.get("author") or "",
                "sourceUrl": item.get("sourceUrl") or url,
                "termsUrl": item.get("termsUrl", ""),
                "licenseSnapshot": item.get("licenseSnapshot", ""),
                "usageScope": item.get("usageScope", ""),
                "platform": item.get("platform") or item.get("sourcePlatform") or "",
                "modelReleaseRequired": item.get("modelReleaseRequired", ""),
                "modelReleaseStatus": item.get("modelReleaseStatus", ""),
                "authorizationProof": item.get("authorizationProof", ""),
                "generationModel": item.get("generationModel", ""),
                "generationPromptHash": item.get("generationPromptHash", ""),
                "generatedAt": item.get("generatedAt", ""),
                "syntheticDisclosure": item.get("syntheticDisclosure", ""),
                # 相关性/说明/类型/尺寸：供 relevance 门、caption 与像素门消费。
                "caption": item.get("caption", ""),
                "relevance": item.get("relevance") or item.get("caption") or "",
                "contentType": item.get("contentType", ""),
                "width": item.get("width", ""),
                "height": item.get("height", ""),
            }
        else:
            continue
        url = spec["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(spec)
    return out


def curated_images_for_entity(
    task_id: str, batch_id: str, entity_id: str, entity_type: str = ""
) -> list[dict[str, Any]]:
    """读 source_plan 中实体级 imageUrls（顶层/payload）+ 各 source 的 imageUrls，去重合并。

    每项规范化为 {url, license, credit}。Agent 在 source_plan 输入里给出真实可用图（CC/PD/授权），
    download 据此下图到来源单元 assets/，供 produce 选图与 imageGate 体检。
    """
    plan_file = _source_plan_file(task_id, batch_id, entity_id, entity_type)
    if plan_file is None:
        return []
    data = read_json(plan_file)
    if not isinstance(data, dict):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    specs = _normalize_image_specs(data.get("imageUrls") or payload.get("imageUrls") or [])
    seen = {s["url"] for s in specs}
    for src in _extract_sources(data):
        if not isinstance(src, dict):
            continue
        for extra in _normalize_image_specs(src.get("imageUrls") or []):
            if extra["url"] not in seen:
                seen.add(extra["url"])
                specs.append(extra)
    return specs


def source_frontmatter(source: dict[str, Any], entity_id: str) -> str:
    """来源 frontmatter：只记录真实抓取元信息，source.md 正文不再允许 task body 冒充。"""
    use_mode = str(source.get("sourceUseMode") or SOURCE_USE_FACTUAL_REFERENCE)
    allowed_use = (
        "licensed_adaptation"
        if use_mode == SOURCE_USE_LICENSED_ADAPTATION
        else "facts_only"
    )
    return (
        f"---\n"
        f"url: {source.get('url', '')}\n"
        f"platform: {source.get('platform', 'web')}\n"
        f"sourceUseMode: {use_mode}\n"
        f"license: {source.get('license') or 'reference-only'}\n"
        f"allowedUse: {allowed_use}\n"
        f"credit: {source.get('credit', '')}\n"
        f"termsUrl: {source.get('termsUrl', '')}\n"
        f"licenseSnapshot: {source.get('licenseSnapshot', '')}\n"
        f"authorizationProof: {source.get('authorizationProof', '')}\n"
        f"entity: {entity_id}\n"
        f"retained: false\n"
        f"taskProvidedBody: {'true' if str(source.get('body') or '').strip() else 'false'}\n"
        f"---\n\n"
    )


def source_plan_rights_issues(
    task_id: str,
    batch_id: str,
    entity_id: str,
    entity_type: str = "",
    require_explicit: bool = False,
) -> list[str]:
    """校验 source_plan 的文字来源权利分层，阻断缺模式和伪授权。"""
    issues: list[str] = []
    for source in curated_sources_for_entity(task_id, batch_id, entity_id, entity_type):
        sid = str(source.get("source_id") or "?")
        mode = str(source.get("sourceUseMode") or "").strip()
        if not mode and not require_explicit:
            mode = SOURCE_USE_FACTUAL_REFERENCE
        if mode not in VALID_SOURCE_USE_MODES:
            issues.append(f"{sid}: sourceUseMode must be one of {sorted(VALID_SOURCE_USE_MODES)}")
            continue
        if mode == SOURCE_USE_BLOCKED:
            issues.append(f"{sid}: blocked source must not enter a consumable source plan")
            continue
        if mode == SOURCE_USE_LICENSED_ADAPTATION:
            for field in ("license", "termsUrl", "licenseSnapshot"):
                if not str(source.get(field) or "").strip():
                    issues.append(f"{sid}: licensed_adaptation missing {field}")
    return issues


def manual_body_note(source: dict[str, Any], *, max_chars: int = 180) -> str:
    """task/source_plan 里的 body 仅作为人工计划备注，不得充当 source.md 正文。"""
    body = re.sub(r"\s+", " ", str(source.get("body") or "")).strip()
    if not body:
        return ""
    clipped = body[:max_chars]
    if len(body) > max_chars:
        clipped += "..."
    return f"manual_source_plan_note: {clipped}"

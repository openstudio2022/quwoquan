"""通用来源计划读取（取代任务/区域专属 curated 语料）。

来源候选由任务/Agent 在 download source_plan 输入中给出，主线不内置任何区域语料：
  runtime/tasks/{task}/batches/{batch}/download/inputs/source_plan/{entity_id}.json
  {
    "sources": [
      {"source_id": "...", "platform": "...", "url": "https://...", "body": "(可选离线兜底正文)"}
    ]
  }
"""
from __future__ import annotations

from typing import Any

from _common.io import read_json
from _common.paths import batch_inputs_dir


def _extract_sources(data: Any) -> list[dict[str, Any]]:
    """兼容三种 source_plan 形态：顶层 sources / envelope payload.sources / payload.existingSources。"""
    if not isinstance(data, dict):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw = (
        data.get("sources")
        or payload.get("sources")
        or payload.get("existingSources")
        or data.get("existingSources")
        or []
    )
    return raw if isinstance(raw, list) else []


def curated_sources_for_entity(task_id: str, batch_id: str, entity_id: str) -> list[dict[str, Any]]:
    plan_file = batch_inputs_dir(task_id, batch_id, "download", "source_plan") / f"{entity_id}.json"
    if not plan_file.is_file():
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
            }
        else:
            continue
        url = spec["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(spec)
    return out


def curated_images_for_entity(task_id: str, batch_id: str, entity_id: str) -> list[dict[str, Any]]:
    """读 source_plan 中实体级 imageUrls（顶层/payload）+ 各 source 的 imageUrls，去重合并。

    每项规范化为 {url, license, credit}。Agent 在 source_plan 输入里给出真实可用图（CC/PD/授权），
    download 据此下图到 sources/{entity}/images/，供 produce 选图与 imageGate 体检。
    """
    plan_file = batch_inputs_dir(task_id, batch_id, "download", "source_plan") / f"{entity_id}.json"
    if not plan_file.is_file():
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
    """离线兜底：fetch 失败时写最小 frontmatter + 任务提供的 body（无则空骨架）。"""
    body = source.get("body") or ""
    return (
        f"---\n"
        f"url: {source.get('url', '')}\n"
        f"platform: {source.get('platform', 'web')}\n"
        f"license: task-provided\n"
        f"allowedUse: internal_reference\n"
        f"entity: {entity_id}\n"
        f"retained: true\n"
        f"---\n\n"
        f"{body}"
    )

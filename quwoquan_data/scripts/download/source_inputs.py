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


def curated_sources_for_entity(task_id: str, batch_id: str, entity_id: str) -> list[dict[str, Any]]:
    plan_file = batch_inputs_dir(task_id, batch_id, "download", "source_plan") / f"{entity_id}.json"
    if not plan_file.is_file():
        return []
    data = read_json(plan_file)
    sources = data.get("sources", []) if isinstance(data, dict) else []
    out: list[dict[str, Any]] = []
    for idx, src in enumerate(sources, start=1):
        if not src.get("url"):
            continue
        out.append(
            {
                "source_id": src.get("source_id") or f"source_{idx}",
                "platform": src.get("platform") or "web",
                "url": src["url"],
                "body": src.get("body", ""),
            }
        )
    return out


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

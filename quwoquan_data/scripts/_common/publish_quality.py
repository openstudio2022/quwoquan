"""publish 实体质量元数据：沉淀（promote 时写入 manifest.quality）与对比替换门。

真相源链路：
  build（homepage `_write_entity_quality_stage`）在 `2.quality/quality_analysis.json`
  的 `baseDraft.primarySource` 沉淀主源 platform/authorityRank/factCount/fetchScore；
  promote 时由本模块汇总成 publish 实体 `manifest.json` 的 `quality` 节，并对
  已存在实体执行「新版不劣才覆盖」的对比门（mandatory 重做走同一通道，无旁路）。

对比键（从高位到低位，越大越好）：
  (-authorityRank, factCount, fetchScore, generatedAt)

- authorityRank 越小越权威（`homepage_primary_authority_rank` 语义），取负参与比较；
- 缺失 quality 节（历史发布物）视为最低，任何新版都可覆盖；
- generatedAt 用批次 createdAt（ISO 字符串字典序即时间序）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

PUBLISH_ENTITY_QUALITY_SCHEMA = "quwoquan_data.publish_entity_quality/1"

# 缺失 quality 的权威位哨兵：任何真实 rank 取负都大于它。
_MISSING_AUTHORITY = -(10**6)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_entity_quality_evidence(
    entity_dir: Path,
    *,
    source_task_id: str = "",
    source_batch_id: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    """从实体对象目录提炼 publish quality 节。

    优先消费过程证据（2.quality/5.review）；对象目录缺过程阶段（如 release
    树只拷成品）时回退读取自带 manifest.quality（已沉淀过的搬运场景）。
    """
    quality_analysis = _read_json(entity_dir / "2.quality" / "quality_analysis.json")
    review = _read_json(entity_dir / "5.review" / "review.json")
    if not quality_analysis and not review:
        existing = _read_json(entity_dir / "manifest.json").get("quality")
        if isinstance(existing, Mapping):
            return dict(existing)
    base_draft = quality_analysis.get("baseDraft") if isinstance(quality_analysis.get("baseDraft"), Mapping) else {}
    primary = base_draft.get("primarySource") if isinstance(base_draft.get("primarySource"), Mapping) else {}
    fetch_score = primary.get("fetchScore")
    if fetch_score is None:
        # 兼容未沉淀 primarySource 的历史批次：从 candidates 里按 sourceRef 匹配 score。
        source_ref = str(base_draft.get("sourceRef") or "")
        for row in quality_analysis.get("candidates") or []:
            if isinstance(row, Mapping) and str(row.get("sourceRef") or "") == source_ref:
                fetch_score = row.get("score")
                break
    return {
        "schemaVersion": PUBLISH_ENTITY_QUALITY_SCHEMA,
        "primarySource": {
            "platform": str(primary.get("platform") or ""),
            "sourceKind": str(primary.get("sourceKind") or ""),
            "authorityRank": (
                int(primary["authorityRank"])
                if isinstance(primary.get("authorityRank"), (int, float))
                else None
            ),
        },
        "factCount": int(primary.get("factCount") or 0),
        "fetchScore": float(fetch_score or 0.0),
        "reviewDecision": str(review.get("decision") or ""),
        "generatedAt": str(generated_at or ""),
        "sourceTaskId": str(source_task_id or ""),
        "sourceBatchId": str(source_batch_id or ""),
    }


def quality_rank_key(quality: Mapping[str, Any] | None) -> tuple[int, int, float, str]:
    """规范化对比键：逐位比较，越大越好。缺 quality 节整体视为最低。"""
    q = quality or {}
    primary = q.get("primarySource") if isinstance(q.get("primarySource"), Mapping) else {}
    rank = primary.get("authorityRank")
    authority = -int(rank) if isinstance(rank, (int, float)) else _MISSING_AUTHORITY
    return (
        authority,
        int(q.get("factCount") or 0),
        float(q.get("fetchScore") or 0.0),
        str(q.get("generatedAt") or ""),
    )


def should_replace_published_entity(
    new_quality: Mapping[str, Any] | None,
    old_quality: Mapping[str, Any] | None,
) -> bool:
    """新版不劣才覆盖（相等允许覆盖，保证幂等重跑）。"""
    return quality_rank_key(new_quality) >= quality_rank_key(old_quality)


def write_entity_quality_into_manifest(entity_dir: Path, quality: Mapping[str, Any]) -> Path:
    """把 quality 节写进（publish 侧）实体 manifest.json；无 manifest 时创建最小骨架。"""
    manifest_path = entity_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        manifest = {"schemaVersion": "quwoquan_data.entity_manifest"}
    manifest["quality"] = dict(quality)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest_path


def read_published_entity_quality(entity_dir: Path) -> dict[str, Any] | None:
    """读取 publish 实体已沉淀的 quality 节；历史无 quality 返回 None（视为最低）。"""
    quality = _read_json(entity_dir / "manifest.json").get("quality")
    return dict(quality) if isinstance(quality, Mapping) else None

"""作品判定接入闸口（compose-brief 阶段）。

在 Agent 创作之前对每个内容对象跑 WorksClassifier：
- 落 works_verdict.json 到对象 compose 阶段目录（审计全覆盖，可回溯 policyDigest）。
- article/image 作品载体下判为 moment/abandoned → 返回阻断 issue，不进入 agent_compose，
  从而在创作前拦截随记/低专业度来源，节省执行 Agent 的创作 token（主成本）。
- homepage 实体主页是独立流程，已有主页专属证据门，这里只落审计 verdict，不二次阻断。

来源专业度先验经 content_source_registry（platform/sourceId → sourceClass → baseTier/affinity），
内容实测信号经 score_source_markdown + 结构/事实/叙事/图片，禁止在本模块散落第二套阈值。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from content.post import object_index as content_object
from content.post.article.base_draft import load_base_draft_text
from content.post.article.base_draft_source import base_source_unit_meta
from core.content_source_registry import resolve_source_class
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import write_json
from core.paths import STAGE_COMPOSE
from content.post.image.works_classifier import classify_works

WORKS_VERDICT_FILE = "works_verdict.json"
_BLOCKING_CARRIERS = ("article", "image", "gallery")
_SAFE_IMAGE_STATUSES = ("safe", "text_heavy")


def _safe_image_count(assets: Sequence[Mapping[str, Any]]) -> int:
    return len([a for a in assets if str(a.get("imageStatus", "safe")) in _SAFE_IMAGE_STATUSES])


def evaluate_object_works(
    execution_id: str,
    ref: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
    *,
    carrier: str,
    narrative_volume: int,
    entity_name: str = "",
    rights_blocked: bool = False,
) -> tuple[dict[str, Any], list[DataIssue]]:
    """跑作品判定、落审计 verdict、返回 (verdict, blocking_issues)。"""
    base_source_ref = brief.get("baseSourceRef")
    source_text = load_base_draft_text(execution_id, base_source_ref)
    meta = base_source_unit_meta(execution_id, base_source_ref)
    source_class = resolve_source_class(
        source_id=str(meta.get("sourceId") or ""),
        platform=str(meta.get("platform") or ""),
    )
    carrier_l = str(carrier or "").strip().lower()
    declared_carrier = "image" if carrier_l == "image" else carrier_l or "article"

    verdict = classify_works(
        ref,
        source_class=source_class,
        source_text=source_text,
        entity_name=entity_name or str(brief.get("title") or "") or None,
        narrative_volume=int(narrative_volume or 0),
        image_count=_safe_image_count(assets),
        declared_carrier=declared_carrier,
        rights_blocked=bool(rights_blocked),
    )

    stage_dir = content_object.content_object_stage_dir(execution_id, ref, STAGE_COMPOSE)
    write_json(stage_dir / WORKS_VERDICT_FILE, verdict)

    issues: list[DataIssue] = []
    decision = str(verdict.get("decision") or "")
    if carrier_l in _BLOCKING_CARRIERS and decision != "work":
        issues.append(data_issue(
            DataIssueCode.CONTENT_CLASSIFICATION_REJECTED,
            stage=DataIssueStage.COMPOSE_BRIEF,
            ref=ref,
            recovery=DataRecoveryAction.STOP,
            message="作品分类未达到可发布作品准入标准",
            attributes={
                "decision": decision,
                "abandonReason": verdict.get("abandonReason") or "",
                "sourceTier": verdict.get("sourceTier") or "",
                "score": verdict.get("score") or "",
            },
        ))
    return verdict, issues


__all__ = ["evaluate_object_works", "WORKS_VERDICT_FILE"]
